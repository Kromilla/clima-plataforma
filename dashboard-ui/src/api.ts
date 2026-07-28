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

export function fetchIncendios(lugarId: string, dias = 2) {
  return getJSON<RespuestaIncendios>(
    `/api/incendios?lugar_id=${encodeURIComponent(lugarId)}&dias=${dias}`,
  );
}

async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail ?? `${url} respondió ${res.status}`);
  }
  return data as T;
}

// ── Predictor de riesgo (Fase 4) ─────────────────────────────────────────────

export interface Riesgo {
  disponible: boolean;
  etiqueta: string;
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

// ── Huella de carbono (Módulo A) ─────────────────────────────────────────────

export interface RespuestasHuella {
  transporte: string;
  km_semana: number;
  pasajeros_auto: number;
  horas_vuelo_anio: number;
  kwh_mes: number;
  personas_hogar: number;
  gas_m3_mes: number;
  glp_kg_mes: number;
  usa_factor_colombia: boolean;
  dieta: string;
  residuos_kg_semana: number;
  recicla: boolean;
}

export interface ResultadoHuella {
  total_t: number;
  desglose: Record<string, number>;
  vs_colombia: number;
  vs_mundial: number;
  cumple_paris: boolean;
  detalles: string[];
  recomendaciones: string[];
  referencias: {
    promedio_colombia_t: number;
    promedio_mundial_t: number;
    objetivo_paris_2030_t: number;
  };
}

export function calcularHuella(datos: RespuestasHuella) {
  return postJSON<ResultadoHuella>('/api/huella/calcular', datos);
}

// ── Quiz (Módulo B) ──────────────────────────────────────────────────────────

export interface PreguntaQuiz {
  id: number;
  texto: string;
  opciones: string[];
  categoria: string;
}

export interface ResultadoQuiz {
  puntaje: number;
  total: number;
  porcentaje: number;
  nivel: string;
  mensaje: string;
  correctas: number[];
  incorrectas: number[];
  solucionario: {
    id: number;
    correcta: number;
    explicacion: string;
    fuente: string;
  }[];
  compartir: string;
}

export function fetchPreguntas() {
  return getJSON<PreguntaQuiz[]>('/api/quiz/preguntas');
}

export function calificarQuiz(respuestas: Record<number, number>) {
  return postJSON<ResultadoQuiz>('/api/quiz/calificar', { respuestas });
}

/** Ids de fuente registrados en el backend (sources/registry.py). */
export const FUENTE_AIRE = 'openmeteo-aire';
export const FUENTE_CLIMA = 'openmeteo-clima';
export const FUENTE_ENERGIA = 'xm';
