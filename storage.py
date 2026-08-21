"""
storage.py — Capa de persistencia: una sola puerta a los datos.

Soporta dos backends, elegidos por la cadena de conexión:
  - **SQLite** (por defecto): desarrollo local y tests, sin configuración.
  - **Postgres** (si `DATABASE_URL` empieza por `postgresql://`): producción, p.ej.
    Supabase. En Render el API y el cron del collector son contenedores separados
    y no pueden compartir un archivo SQLite, así que se necesita una BD externa.

El resto del proyecto no sabe cuál se usa: sigue llamando a las mismas funciones.

Tabla `lecturas`:
    id, fuente, lugar_id, metrica, valor, unidad, procedencia, estacion, ts (ISO 8601 UTC)
Tabla `config_usuario`:
    clave (PK), valor  — preferencias por chat (ej. umbral PM2.5 por chat_id)
"""
from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from sources.base import Lectura

logger = logging.getLogger(__name__)


def _db_path() -> str:
    """
    Cadena de conexión activa. En producción es `DATABASE_URL` (Postgres); si no,
    la ruta SQLite de config. Lazy import para no exigir config ya inicializado.
    """
    try:
        from config import cfg  # noqa: PLC0415
        return os.environ.get("DATABASE_URL") or cfg.DB_PATH
    except SystemExit:
        # Durante tests, config puede no tener .env — SQLite en memoria.
        return os.environ.get("DATABASE_URL") or ":memory:"


def _es_postgres(ruta: str) -> bool:
    return ruta.startswith(("postgres://", "postgresql://"))


@contextmanager
def _conexion(db_path: str | None = None) -> Generator[tuple[object, bool], None, None]:
    """
    Abre una conexión (commit/rollback/close automáticos) y dice si es Postgres.

    Yields:
        (conexión, es_pg) — `es_pg` permite a cada función usar la sintaxis correcta
        (marcador de parámetros, upsert…).
    """
    ruta = db_path or _db_path()
    es_pg = _es_postgres(ruta)

    if es_pg:
        import psycopg  # noqa: PLC0415 — solo se necesita en producción
        from psycopg.rows import dict_row  # noqa: PLC0415
        con: object = psycopg.connect(ruta, row_factory=dict_row)
    else:
        # timeout: con el recolector, la API y el bot escribiendo a la vez, esperar
        # a que se libere el lock es mejor que fallar con "database is locked".
        con = sqlite3.connect(ruta, timeout=15)
        con.row_factory = sqlite3.Row
        if ruta != ":memory:":
            # WAL permite leer mientras se escribe (irrelevante en Postgres).
            con.execute("PRAGMA journal_mode=WAL")

    try:
        yield con, es_pg
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _ph(sql: str, es_pg: bool) -> str:
    """Traduce el marcador de parámetros: SQLite usa '?', Postgres usa '%s'."""
    return sql.replace("?", "%s") if es_pg else sql


def inicializar_bd(db_path: str | None = None) -> None:
    """Crea las tablas e índices si no existen. Seguro de llamar múltiples veces."""
    with _conexion(db_path) as (con, es_pg):
        id_col = "id BIGSERIAL PRIMARY KEY" if es_pg else "id INTEGER PRIMARY KEY AUTOINCREMENT"
        valor_col = "valor DOUBLE PRECISION NOT NULL" if es_pg else "valor REAL NOT NULL"

        sentencias = [
            f"""
            CREATE TABLE IF NOT EXISTS lecturas (
                {id_col},
                fuente      TEXT NOT NULL,
                lugar_id    TEXT NOT NULL,
                metrica     TEXT NOT NULL,
                {valor_col},
                unidad      TEXT NOT NULL DEFAULT '',
                procedencia TEXT NOT NULL DEFAULT 'local',
                estacion    TEXT          DEFAULT '',
                ts          TEXT NOT NULL
            )
            """,
            "CREATE TABLE IF NOT EXISTS config_usuario (clave TEXT PRIMARY KEY, valor TEXT NOT NULL)",
        ]
        for s in sentencias:
            con.execute(s)

        # Índice único (fuente, lugar, métrica, ts): evita que el recolector
        # duplique filas cuando la fuente aún no publica un dato nuevo. Además
        # sirve para las búsquedas por esas mismas columnas — un índice se puede
        # recorrer en cualquier dirección, así que no hace falta uno aparte con
        # `ts DESC`. Había uno y era 21 MB de pura redundancia: el planificador
        # lo eligió 4.961 veces contra 2,9 millones del único.
        ya_existe = _existe_indice_unico(con, es_pg)
        if not ya_existe:
            # Solo tiene sentido antes de crear el índice: una vez que existe,
            # los duplicados son imposibles. Correrlo en cada arranque era un
            # recorrido completo de la tabla (5,5 s con 124.000 filas) para no
            # borrar nada.
            _deduplicar(con)
            con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_lecturas_unica "
                "ON lecturas (fuente, lugar_id, metrica, ts)"
            )
        _soltar_indice_redundante(con, es_pg)

        # Se comprueba aquí, reusando esta conexión, y solo se abre otra si de
        # verdad hay que activar RLS. Abrir una conexión a Supabase cuesta ~1,2 s
        # — más que todas las consultas juntas —, así que en el caso normal
        # (RLS ya activo) el arranque se ahorra la mitad del tiempo.
        faltan_rls = _tablas_sin_rls(con, es_pg)

    # El ALTER va en su propia conexión a propósito: en Postgres un fallo aborta
    # toda la transacción, y no debe llevarse por delante la creación de tablas.
    if faltan_rls:
        _asegurar_rls(db_path)


def _asegurar_rls(db_path: str | None = None) -> None:
    """
    Activa Row-Level Security en las tablas (solo Postgres/Supabase).

    Supabase expone las tablas por su API REST con el rol público `anon`. Sin
    RLS, cualquiera con la URL del proyecto puede leer/editar/borrar todo. Como
    el backend se conecta por DATABASE_URL (rol dueño, que omite RLS), activarla
    SIN políticas bloquea el acceso público sin afectar a la app. Idempotente.

    Best-effort: si el rol no puede alterar la tabla, se registra y sigue —
    el fix autoritativo es correr el ALTER en el SQL Editor de Supabase.

    Solo altera las tablas a las que les falta: `ALTER TABLE` toma un lock
    ACCESS EXCLUSIVE aunque no cambie nada, y esto corre en cada arranque de la
    API (frecuente en Render por los cold starts). Consultar antes es una
    lectura barata y evita chocar con el recolector mientras escribe.
    """
    ruta = db_path or _db_path()
    if not _es_postgres(ruta):
        return
    try:
        with _conexion(ruta) as (con, _):
            filas = con.execute(
                "SELECT relname FROM pg_class "
                "WHERE relname IN ('lecturas', 'config_usuario') AND NOT relrowsecurity"
            ).fetchall()
            for fila in filas:
                tabla = fila["relname"]
                con.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
                logger.info("RLS activado en %s", tabla)
    except Exception as exc:  # noqa: BLE001 — la seguridad no debe tumbar el arranque
        logger.warning("No se pudo activar RLS (córrelo en el SQL Editor): %s", exc)


def _tablas_sin_rls(con: object, es_pg: bool) -> list[str]:
    """Tablas a las que les falta Row-Level Security. Vacío en SQLite."""
    if not es_pg:
        return []
    filas = con.execute(
        "SELECT relname FROM pg_class "
        "WHERE relname IN ('lecturas', 'config_usuario') AND NOT relrowsecurity"
    ).fetchall()
    return [f["relname"] for f in filas]


def _existe_indice_unico(con: object, es_pg: bool) -> bool:
    """Si el índice único ya está, no hay duplicados que limpiar."""
    if es_pg:
        sql = "SELECT 1 FROM pg_class WHERE relname = 'idx_lecturas_unica'"
    else:
        sql = "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_lecturas_unica'"
    return con.execute(sql).fetchone() is not None


def _soltar_indice_redundante(con: object, es_pg: bool) -> None:
    """
    Elimina `idx_lecturas_lookup`, que cubre las mismas columnas que el único.

    Mantener dos índices iguales cuesta espacio y, sobre todo, hace más lenta
    cada escritura del recolector: hay que actualizar los dos árboles.
    """
    try:
        if not _existe_indice_unico(con, es_pg):
            return  # sin el único, el otro todavía hace falta

        # Se consulta antes de soltar: así, una vez eliminado, los arranques
        # siguientes no ejecutan ningún DDL ni piden bloqueo alguno.
        if es_pg:
            sql = "SELECT 1 FROM pg_class WHERE relname = 'idx_lecturas_lookup'"
        else:
            sql = ("SELECT 1 FROM sqlite_master WHERE type='index' "
                   "AND name='idx_lecturas_lookup'")
        if con.execute(sql).fetchone() is None:
            return

        con.execute("DROP INDEX IF EXISTS idx_lecturas_lookup")
        logger.info("Índice redundante idx_lecturas_lookup eliminado")
    except Exception as exc:  # noqa: BLE001 — no debe impedir el arranque
        logger.warning("No se pudo soltar idx_lecturas_lookup: %s", exc)


def _deduplicar(con: object) -> None:
    """Elimina filas repetidas dejando la más antigua de cada grupo."""
    con.execute(
        """
        DELETE FROM lecturas
        WHERE id NOT IN (
            SELECT MIN(id) FROM lecturas
            GROUP BY fuente, lugar_id, metrica, ts
        )
        """
    )


def _fila(lectura: Lectura) -> tuple:
    return (
        lectura.fuente, lectura.lugar_id, lectura.metrica, lectura.valor,
        lectura.unidad, lectura.procedencia, lectura.estacion_nombre,
        lectura.ts.isoformat(),
    )


def _sql_insert(es_pg: bool) -> str:
    """INSERT que ignora duplicados por el índice único, en la sintaxis del backend."""
    cols = "(fuente, lugar_id, metrica, valor, unidad, procedencia, estacion, ts)"
    valores = "(?, ?, ?, ?, ?, ?, ?, ?)"
    if es_pg:
        sql = f"INSERT INTO lecturas {cols} VALUES {valores} ON CONFLICT DO NOTHING"
    else:
        sql = f"INSERT OR IGNORE INTO lecturas {cols} VALUES {valores}"
    return _ph(sql, es_pg)


def guardar(lectura: Lectura, db_path: str | None = None) -> bool:
    """
    Persiste una Lectura.

    Returns:
        True si se insertó una nueva; False si ya existía una con el mismo
        (fuente, lugar, métrica, ts) — la fuente aún no publicó nada nuevo.
    """
    with _conexion(db_path) as (con, es_pg):
        cur = con.execute(_sql_insert(es_pg), _fila(lectura))
        return cur.rowcount > 0


def guardar_muchas(lecturas: list[Lectura], db_path: str | None = None) -> int:
    """
    Persiste muchas lecturas en una sola transacción (para el backfill histórico,
    que inserta decenas de miles de una vez).

    Returns:
        Cuántas lecturas eran nuevas (las repetidas se ignoran).
    """
    if not lecturas:
        return 0

    filas = [_fila(lec) for lec in lecturas]

    with _conexion(db_path) as (con, es_pg):
        cur = con.cursor()
        # `rowcount` da las filas realmente insertadas (INSERT OR IGNORE / ON
        # CONFLICT DO NOTHING no cuentan las repetidas). Antes se hacían dos
        # `SELECT COUNT(*)` de toda la tabla: con cientos de miles de filas en
        # Supabase eso era un full-scan por cada fuente × ciudad → el collector
        # de 14 ciudades tardaba 15+ min y lo mataban.
        cur.executemany(_sql_insert(es_pg), filas)
        nuevas = cur.rowcount

    return nuevas if nuevas and nuevas > 0 else 0


def _row_a_lectura(row: object) -> Lectura:
    return Lectura(
        valor=row["valor"],
        unidad=row["unidad"],
        metrica=row["metrica"],
        fuente=row["fuente"],
        # Se conserva la procedencia guardada (no se fuerza a "cache"): quien la
        # sirva como respaldo la marca con Lectura.como_cache().
        procedencia=row["procedencia"],
        lugar_id=row["lugar_id"],
        estacion_nombre=row["estacion"] or "",
        ts=datetime.fromisoformat(row["ts"]).replace(tzinfo=timezone.utc),
    )


def ultimo_valor(
    fuente: str,
    lugar_id: str,
    metrica: str,
    db_path: str | None = None,
) -> Lectura | None:
    """Lectura más reciente para (fuente, lugar_id, metrica), o None si no hay."""
    with _conexion(db_path) as (con, es_pg):
        row = con.execute(
            _ph(
                "SELECT * FROM lecturas WHERE fuente = ? AND lugar_id = ? AND metrica = ? "
                "ORDER BY ts DESC LIMIT 1",
                es_pg,
            ),
            (fuente, lugar_id, metrica),
        ).fetchone()

    return _row_a_lectura(row) if row is not None else None


def historial(
    fuente: str,
    lugar_id: str,
    metrica: str,
    limite: int = 20,
    db_path: str | None = None,
) -> list[Lectura]:
    """Últimas `limite` lecturas, ordenadas de más antigua a más nueva."""
    with _conexion(db_path) as (con, es_pg):
        rows = con.execute(
            _ph(
                "SELECT * FROM lecturas WHERE fuente = ? AND lugar_id = ? AND metrica = ? "
                "ORDER BY ts DESC LIMIT ?",
                es_pg,
            ),
            (fuente, lugar_id, metrica, limite),
        ).fetchall()

    return [_row_a_lectura(r) for r in reversed(rows)]  # más antigua primero


# ── Configuración por usuario (umbral personalizado) ──────────────────────────

def obtener_config(clave: str, default: str = "", db_path: str | None = None) -> str:
    """Lee un valor de config_usuario."""
    with _conexion(db_path) as (con, es_pg):
        row = con.execute(
            _ph("SELECT valor FROM config_usuario WHERE clave = ?", es_pg),
            (clave,),
        ).fetchone()
    return row["valor"] if row else default


def guardar_config(clave: str, valor: str, db_path: str | None = None) -> None:
    """Guarda o actualiza un valor de config_usuario (upsert)."""
    with _conexion(db_path) as (con, es_pg):
        con.execute(
            _ph(
                "INSERT INTO config_usuario (clave, valor) VALUES (?, ?) "
                "ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
                es_pg,
            ),
            (clave, valor),
        )
