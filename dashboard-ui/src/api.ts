/**
 * api.ts — Única capa de acceso al backend.
 *
 * El lugar por defecto se PIDE al backend (/api/lugares) en vez de hardcodearlo.
 * Hardcodear el id fue lo que rompió el dashboard antes: el frontend pedía
 * "CO-SMR" y "CO", pero el único id real es "santa-marta", así que cada request
 * devolvía 404 y las tarjetas quedaban en "--".
 */

export interface Lectura {
  valor: number;
  unidad: string;
  metrica: string;
  fuente: string;
  procedencia: string;
  lugar_id: string;
  estacion_nombre: string;
  ts: string;
  antiguedad_min: number;
  antiguedad_texto: string;
  etiqueta_procedencia: string;
  es_reciente: boolean;
}

export type EstadoSemaforo = 'verde' | 'amarillo' | 'rojo';

export interface EstadoFuente {
  estado: EstadoSemaforo;
  etiqueta: string;
  detalle: string;
}

export interface Lugar {
  id: string;
  nombre: string;
  lat: number;
  lon: number;
}

/** Lecturas actuales, indexadas por id de fuente (ej. "openmeteo-aire"). */
export type LecturasActuales = Record<string, Lectura | null>;

// URL base de la API. Vacía en desarrollo → rutas relativas /api/... que el proxy
// de Vite reenvía al backend local. En Vercel se define VITE_API_URL con la URL
// del backend en Render.
const BASE = import.meta.env.VITE_API_URL ?? '';

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(BASE + url);
  if (!res.ok) {
    throw new Error(`${url} respondió ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function fetchLugares() {
  return getJSON<{ default: string; lugares: Lugar[] }>('/api/lugares');
}

export function fetchActual(lugarId: string) {
  return getJSON<LecturasActuales>(
    `/api/clima/actual?lugar_id=${encodeURIComponent(lugarId)}`,
  );
}

export function fetchEstadoFuentes(lugarId: string) {
  return getJSON<Record<string, EstadoFuente>>(
    `/api/estado/fuentes?lugar_id=${encodeURIComponent(lugarId)}`,
  );
}

export function fetchHistorial(fuente: string, lugarId: string, limite = 24) {
  return getJSON<Lectura[]>(
    `/api/clima/historial?fuente=${encodeURIComponent(fuente)}` +
      `&lugar_id=${encodeURIComponent(lugarId)}&limite=${limite}`,
  );
}

/** Un foco de calor detectado por satélite (NASA FIRMS). */
export interface Foco {
  lat: number;
  lon: number;
  /** Potencia radiativa en megavatios: proxy de intensidad. */
  frp: number;
  confianza: 'baja' | 'nominal' | 'alta';
  ts: string;
  satelite: string;
  dia_noche: string;
  distancia_km: number;
}

export interface RespuestaIncendios {
  disponible: boolean;
  motivo: 'sin_clave' | 'fuente_caida' | null;
  mensaje: string | null;
  centro: { lat: number; lon: number };
  bbox?: [number, number, number, number];
  dias?: number;
  focos: Foco[];
}

export function fetchIncendios(lugarId: string, dias = 2, nacional = false) {
  const q = nacional
    ? `nacional=true&dias=${dias}`
    : `lugar_id=${encodeURIComponent(lugarId)}&dias=${dias}`;
  return getJSON<RespuestaIncendios>(`/api/incendios?${q}`);
}

// ── Predictor de riesgo (Fase 4) ─────────────────────────────────────────────

export interface Riesgo {
  disponible: boolean;
  etiqueta: string;
  /** Cuando no está disponible: por qué. */
  motivo?: 'sin_historial' | 'sin_calor_extremo';
  mensaje?: string;
  probabilidad?: number;
  nivel?: 'bajo' | 'moderado' | 'alto';
  fecha_objetivo?: string;
  ic_max_hoy?: number;
  umbral_ic?: number;
  modelo?: {
    es_util: boolean;
    exactitud: number;
    precision: number;
    recall: number;
    f1: number;
    tasa_base: number;
    mejora_sobre_base: number;
    n_entrenamiento: number;
    n_prueba: number;
    importancias: Record<string, number>;
  };
}

export function fetchRiesgo(lugarId: string) {
  return getJSON<Riesgo>(`/api/riesgo?lugar_id=${encodeURIComponent(lugarId)}`);
}

/** Ids de fuente registrados en el backend (sources/registry.py). */
export const FUENTE_AIRE = 'openmeteo-aire';
export const FUENTE_CLIMA = 'openmeteo-clima';
export const FUENTE_ENERGIA = 'xm';
