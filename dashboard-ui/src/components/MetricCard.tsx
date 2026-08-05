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
  unidadFallback?: string;
  badge?: { texto: string; clase: string } | null;
  decimales?: number;
  cargando?: boolean;
}

export default function MetricCard({
  titulo,
  icono,
  colorIcono,
  lectura,
  unidadFallback = '',
  badge = null,
  decimales = 1,
  cargando = false,
}: Props) {
  return (
    <div className="card card-pad flex flex-col justify-between transition-shadow hover:shadow-card-hover">
      <div className="flex items-start justify-between">
        <div className={`grid h-11 w-11 place-items-center rounded-xl ${colorIcono}`}>{icono}</div>
        {badge && <span className={`badge ${badge.clase}`}>{badge.texto}</span>}
      </div>

      <div className="mt-5">
        <h2 className="text-sm font-medium text-muted">{titulo}</h2>

        {cargando && !lectura ? (
          <div className="mt-2 space-y-2">
            <div className="skeleton h-9 w-28" />
            <div className="skeleton h-3 w-40" />
          </div>
        ) : (
          <>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="font-display text-4xl font-bold tabular-nums text-heading">
                {lectura ? lectura.valor.toFixed(decimales) : '—'}
              </span>
              <span className="text-sm text-muted">
                {lectura ? lectura.unidad : unidadFallback}
              </span>
            </div>

            {lectura ? (
              <p
                className={`mt-3 text-xs leading-relaxed ${
                  lectura.es_reciente ? 'text-muted' : 'text-amber-600 dark:text-amber-400'
                }`}
                title={lectura.estacion_nombre}
              >
                {lectura.etiqueta_procedencia}
              </p>
            ) : (
              <p className="mt-3 text-xs text-muted">Sin datos todavía</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
