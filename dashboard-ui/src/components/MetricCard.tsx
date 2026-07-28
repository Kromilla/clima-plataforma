/**
 * MetricCard.tsx — Tarjeta de una métrica.
 *
 * Muestra SIEMPRE la procedencia y la antigüedad del dato. Es un requisito del
 * proyecto, no un detalle estético: "quiero que me diga claramente si un dato es
 * viejo o de una estación lejana, no que finja precisión que no tiene".
 */
import type { ReactNode } from 'react';
import type { Lectura } from '../api';

interface Props {
  titulo: string;
  icono: ReactNode;
  colorIcono: string;
  lectura: Lectura | null;
  /** Se muestra en vez del valor cuando aún no hay dato. */
  unidadFallback?: string;
  /** Etiqueta corta opcional (ej. calidad del aire). */
  badge?: { texto: string; clase: string } | null;
  decimales?: number;
}

export default function MetricCard({
  titulo,
  icono,
  colorIcono,
  lectura,
  unidadFallback = '',
  badge = null,
  decimales = 1,
}: Props) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 flex flex-col justify-between">
      <div className="flex justify-between items-start">
        <div className={`p-2 rounded-lg ${colorIcono}`}>{icono}</div>
        {badge && (
          <span className={`px-3 py-1 text-xs font-medium rounded-full ${badge.clase}`}>
            {badge.texto}
          </span>
        )}
      </div>

      <div className="mt-4">
        <h3 className="text-sm font-medium text-gray-500">{titulo}</h3>
        <div className="flex items-baseline mt-1 space-x-2">
          <span className="text-3xl font-bold text-gray-900">
            {lectura ? lectura.valor.toFixed(decimales) : '--'}
          </span>
          <span className="text-sm text-gray-500">
            {lectura ? lectura.unidad : unidadFallback}
          </span>
        </div>

        {lectura ? (
          <p
            className={`mt-3 text-xs leading-relaxed ${
              lectura.es_reciente ? 'text-gray-400' : 'text-amber-600'
            }`}
            title={lectura.estacion_nombre}
          >
            {lectura.etiqueta_procedencia}
          </p>
        ) : (
          <p className="mt-3 text-xs text-gray-400">Sin datos todavía</p>
        )}
      </div>
    </div>
  );
}
