/**
 * useFetch.ts — Carga de datos que se recupera sola.
 *
 * Por qué existe: cada página pedía sus datos UNA vez al montarse. Si el
 * backend no estaba listo en ese instante (arrancar `npm run dev` antes que
 * `python api.py`, o reiniciar la API), la página quedaba muerta para siempre
 * mostrando "Failed to fetch" o "Cargando…", aunque el backend volviera al
 * segundo siguiente. El semáforo del header sí se recuperaba porque repollaba
 * cada minuto, así que la cabecera se veía sana mientras el cuerpo estaba roto
 * — justo la combinación más confusa para el usuario.
 *
 * Además, incluso cuando todo iba bien, los datos quedaban congelados hasta que
 * alguien recargara la página a mano.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

export interface EstadoFetch<T> {
  datos: T | null;
  error: string | null;
  cargando: boolean;
  /** Fuerza una recarga inmediata (para el botón "Reintentar"). */
  recargar: () => void;
  /** Número de reintentos automáticos hechos desde el último éxito. */
  intentos: number;
}

interface Opciones {
  /** Milisegundos entre refrescos cuando todo va bien. 0 = no refrescar. */
  intervaloMs?: number;
  /** Espera inicial entre reintentos tras un fallo; crece hasta 30 s. */
  reintentoBaseMs?: number;
  /** Si es false, no se pide nada (p. ej. mientras no se sabe el lugar). */
  activo?: boolean;
}

const REINTENTO_MAXIMO_MS = 30_000;

export function useFetch<T>(
  cargar: () => Promise<T>,
  deps: unknown[],
  { intervaloMs = 120_000, reintentoBaseMs = 3_000, activo = true }: Opciones = {},
): EstadoFetch<T> {
  const [datos, setDatos] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(activo);
  const [intentos, setIntentos] = useState(0);

  // Se guarda en ref para que cambiar la función no dispare el efecto: las
  // páginas la definen inline y cambiaría en cada render.
  const cargarRef = useRef(cargar);
  cargarRef.current = cargar;

  const [gatillo, setGatillo] = useState(0);
  const recargar = useCallback(() => setGatillo((n) => n + 1), []);

  useEffect(() => {
    if (!activo) return;

    let cancelado = false;
    let temporizador: ReturnType<typeof setTimeout>;
    let fallosSeguidos = 0;

    const programar = (ms: number) => {
      if (ms <= 0 || cancelado) return;
      temporizador = setTimeout(ejecutar, ms);
    };

    const ejecutar = async () => {
      if (cancelado) return;
      try {
        const resultado = await cargarRef.current();
        if (cancelado) return;

        setDatos(resultado);
        setError(null);
        setCargando(false);
        fallosSeguidos = 0;
        setIntentos(0);
        programar(intervaloMs);
      } catch (err) {
        if (cancelado) return;

        fallosSeguidos += 1;
        setError(err instanceof Error ? err.message : String(err));
        setCargando(false);
        setIntentos(fallosSeguidos);

        // Espera creciente: no machacar un backend caído, pero recuperarse
        // rápido si solo fue un reinicio.
        const espera = Math.min(
          reintentoBaseMs * 2 ** (fallosSeguidos - 1),
          REINTENTO_MAXIMO_MS,
        );
        programar(espera);
      }
    };

    setCargando(true);
    ejecutar();

    return () => {
      cancelado = true;
      clearTimeout(temporizador);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, gatillo, activo, intervaloMs, reintentoBaseMs]);

  return { datos, error, cargando, recargar, intentos };
}
