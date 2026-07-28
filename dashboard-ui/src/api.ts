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

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
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

/** Ids de fuente registrados en el backend (sources/registry.py). */
export const FUENTE_AIRE = 'openmeteo-aire';
export const FUENTE_CLIMA = 'openmeteo-clima';
export const FUENTE_ENERGIA = 'xm';
