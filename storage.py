"""
storage.py — Capa de persistencia: SQLite como BD y caché de respaldo.

Principio: una sola puerta a los datos. Si algún día se migra a Postgres,
solo se toca este archivo.

Tabla `lecturas`:
    id           INTEGER PK AUTOINCREMENT
    fuente       TEXT    — "openaq", "openmeteo", "electricity_maps", "firms"
    lugar_id     TEXT    — clave en LUGARES, ej. "santa-marta"
    metrica      TEXT    — "pm25", "temperatura", "intensidad_co2"
    valor        REAL
    unidad       TEXT
    procedencia  TEXT    — "local" | "fallback" | "cache"
    estacion     TEXT    — nombre de la estación (puede ser vacío)
    ts           TEXT    — ISO 8601 UTC

Tabla `config_usuario`:
    clave        TEXT PK
    valor        TEXT
    — Guarda preferencias por chat (ej. umbral PM2.5 por chat_id)
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from sources.base import Lectura


def _db_path() -> str:
    """Devuelve la ruta de la BD desde config (con lazy import para evitar
    que storage.py exija que config.py ya esté completamente inicializado)."""
    try:
        from config import cfg  # noqa: PLC0415
        return cfg.DB_PATH
    except SystemExit:
        # Durante tests, config puede no tener .env — usar BD en memoria
        return ":memory:"


@contextmanager
def _conexion(db_path: str | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager que abre, hace commit/rollback y cierra la conexión."""
    ruta = db_path or _db_path()
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def inicializar_bd(db_path: str | None = None) -> None:
    """Crea las tablas si no existen. Seguro de llamar múltiples veces."""
    with _conexion(db_path) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS lecturas (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                fuente      TEXT    NOT NULL,
                lugar_id    TEXT    NOT NULL,
                metrica     TEXT    NOT NULL,
                valor       REAL    NOT NULL,
                unidad      TEXT    NOT NULL DEFAULT '',
                procedencia TEXT    NOT NULL DEFAULT 'local',
                estacion    TEXT             DEFAULT '',
                ts          TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_lecturas_lookup
                ON lecturas (fuente, lugar_id, metrica, ts DESC);

            CREATE TABLE IF NOT EXISTS config_usuario (
                clave  TEXT PRIMARY KEY,
                valor  TEXT NOT NULL
            );
        """)

        # Una lectura queda identificada por (fuente, lugar, métrica, instante).
        # Sin esto, el recolector inserta una fila nueva en cada pasada aunque la
        # fuente siga publicando el mismo dato: XM solo actualiza cada varias
        # horas y Open-Meteo cada hora, así que consultar cada 15 min generaba
        # filas duplicadas que aplanan las gráficas y ensuciarían el
        # entrenamiento del modelo de la Fase 4.
        _deduplicar(con)
        con.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_lecturas_unica
                ON lecturas (fuente, lugar_id, metrica, ts)
        """)


def _deduplicar(con: sqlite3.Connection) -> None:
    """Elimina filas repetidas dejando la más antigua de cada grupo."""
    con.execute("""
        DELETE FROM lecturas
        WHERE id NOT IN (
            SELECT MIN(id) FROM lecturas
            GROUP BY fuente, lugar_id, metrica, ts
        )
    """)


def guardar(lectura: Lectura, db_path: str | None = None) -> bool:
    """
    Persiste una Lectura en la BD.

    Returns:
        True si se insertó una lectura nueva; False si ya existía uno con el
        mismo (fuente, lugar, métrica, ts) — la fuente aún no publicó nada nuevo.
    """
    with _conexion(db_path) as con:
        cur = con.execute(
            """
            INSERT OR IGNORE INTO lecturas
                (fuente, lugar_id, metrica, valor, unidad, procedencia, estacion, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lectura.fuente,
                lectura.lugar_id,
                lectura.metrica,
                lectura.valor,
                lectura.unidad,
                lectura.procedencia,
                lectura.estacion_nombre,
                lectura.ts.isoformat(),
            ),
        )
        return cur.rowcount > 0


def guardar_muchas(lecturas: list[Lectura], db_path: str | None = None) -> int:
    """
    Persiste muchas lecturas en una sola transacción.

    `guardar()` abre y cierra una conexión por lectura, lo que es irrelevante
    para el recolector (un puñado de filas cada 15 min) pero inviable para el
    backfill histórico, que inserta decenas de miles de una vez.

    Returns:
        Cuántas lecturas eran nuevas (las repetidas se ignoran).
    """
    if not lecturas:
        return 0

    filas = [
        (
            lec.fuente, lec.lugar_id, lec.metrica, lec.valor, lec.unidad,
            lec.procedencia, lec.estacion_nombre, lec.ts.isoformat(),
        )
        for lec in lecturas
    ]

    with _conexion(db_path) as con:
        antes = con.execute("SELECT COUNT(*) FROM lecturas").fetchone()[0]
        con.executemany(
            """
            INSERT OR IGNORE INTO lecturas
                (fuente, lugar_id, metrica, valor, unidad, procedencia, estacion, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            filas,
        )
        despues = con.execute("SELECT COUNT(*) FROM lecturas").fetchone()[0]

    return despues - antes


def ultimo_valor(
    fuente: str,
    lugar_id: str,
    metrica: str,
    db_path: str | None = None,
) -> Lectura | None:
    """
    Devuelve la lectura más reciente para (fuente, lugar_id, metrica).
    Retorna None si no hay ningún registro guardado todavía.
    """
    with _conexion(db_path) as con:
        row = con.execute(
            """
            SELECT * FROM lecturas
            WHERE fuente = ? AND lugar_id = ? AND metrica = ?
            ORDER BY ts DESC
            LIMIT 1
            """,
            (fuente, lugar_id, metrica),
        ).fetchone()

    if row is None:
        return None

    return Lectura(
        valor=row["valor"],
        unidad=row["unidad"],
        metrica=row["metrica"],
        fuente=row["fuente"],
        procedencia="cache",          # Si viene de BD ya es caché
        lugar_id=row["lugar_id"],
        estacion_nombre=row["estacion"] or "",
        ts=datetime.fromisoformat(row["ts"]).replace(tzinfo=timezone.utc),
    )


def historial(
    fuente: str,
    lugar_id: str,
    metrica: str,
    limite: int = 20,
    db_path: str | None = None,
) -> list[Lectura]:
    """Devuelve las últimas `limite` lecturas ordenadas de más antigua a más nueva."""
    with _conexion(db_path) as con:
        rows = con.execute(
            """
            SELECT * FROM lecturas
            WHERE fuente = ? AND lugar_id = ? AND metrica = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (fuente, lugar_id, metrica, limite),
        ).fetchall()

    return [
        Lectura(
            valor=r["valor"],
            unidad=r["unidad"],
            metrica=r["metrica"],
            fuente=r["fuente"],
            procedencia=r["procedencia"],
            lugar_id=r["lugar_id"],
            estacion_nombre=r["estacion"] or "",
            ts=datetime.fromisoformat(r["ts"]).replace(tzinfo=timezone.utc),
        )
        for r in reversed(rows)  # más antigua primero
    ]


# ── Configuración por usuario (umbral personalizado) ──────────────────────────

def obtener_config(clave: str, default: str = "", db_path: str | None = None) -> str:
    """Lee un valor de config_usuario."""
    with _conexion(db_path) as con:
        row = con.execute(
            "SELECT valor FROM config_usuario WHERE clave = ?", (clave,)
        ).fetchone()
    return row["valor"] if row else default


def guardar_config(clave: str, valor: str, db_path: str | None = None) -> None:
    """Guarda o actualiza un valor de config_usuario (upsert)."""
    with _conexion(db_path) as con:
        con.execute(
            """
            INSERT INTO config_usuario (clave, valor) VALUES (?, ?)
            ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
            """,
            (clave, valor),
        )
