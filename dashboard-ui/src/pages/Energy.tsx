import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart,
} from 'recharts';
import { Activity, Info } from 'lucide-react';
import {
  fetchActual, fetchHistorial, FUENTE_ENERGIA,
  type Lectura, type LecturasActuales,
} from '../api';
import { useLugar } from '../LugarContext';
import { useFetch } from '../useFetch';
import { useColoresGrafica } from '../useTema';
import MetricCard from '../components/MetricCard';
import AvisoBackend from '../components/AvisoBackend';
import PageHeader from '../components/PageHeader';

/**
 * Referencia de intensidad de carbono. La red colombiana es mayoritariamente
 * hidráulica, así que suele estar en el rango bajo (~100-250 gCO₂eq/kWh).
 */
function nivelIntensidad(v: number): { texto: string; clase: string } {
  if (v < 150) return { texto: 'Limpia', clase: 'badge-good' };
  if (v < 300) return { texto: 'Moderada', clase: 'badge-warn' };
  if (v < 500) return { texto: 'Alta', clase: 'badge-bad' };
  return { texto: 'Muy alta', clase: 'badge-bad' };
}

interface Datos {
  actual: LecturasActuales;
  historial: Lectura[];
}

export default function Energy() {
  const { lugarId } = useLugar();
  const c = useColoresGrafica();

  const { datos, error, cargando, recargar, intentos } = useFetch<Datos>(
    async () => {
      const [actual, historial] = await Promise.all([
        fetchActual(lugarId!),
        fetchHistorial(FUENTE_ENERGIA, lugarId!, 48),
      ]);
      return { actual, historial };
    },
    [lugarId],
    { activo: !!lugarId },
  );

  const energia = datos?.actual[FUENTE_ENERGIA] ?? null;

  const datosGrafica = (datos?.historial ?? []).map((h) => ({
    fecha: new Date(h.ts).toLocaleString([], { day: '2-digit', month: '2-digit', hour: '2-digit' }),
    intensidad: h.valor,
  }));

  return (
    <div>
      <PageHeader titulo="Energía y Emisiones" subtitulo="Sistema Interconectado Nacional — Colombia" />

      {error && (
        <div className="mb-6">
          <AvisoBackend error={error} intentos={intentos} onReintentar={recargar} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:gap-6 md:grid-cols-2">
        <MetricCard
          titulo="Intensidad de carbono"
          icono={<Activity className="h-5 w-5 text-amber-500" />}
          colorIcono="bg-amber-500/15"
          lectura={energia}
          unidadFallback="gCO₂eq/kWh"
          badge={energia ? nivelIntensidad(energia.valor) : null}
          cargando={cargando && !datos}
        />

        <div className="card card-pad">
          <div className="flex items-center gap-2">
            <Info className="h-4 w-4 text-brand" />
            <h2 className="text-sm font-semibold text-heading">Sobre esta fuente</h2>
          </div>
          <p className="mt-3 text-sm leading-relaxed text-body">
            Datos oficiales de <strong className="text-heading">XM</strong>, operador del mercado
            eléctrico colombiano. Métrica{' '}
            <code className="rounded bg-surface-soft px-1 text-xs">factorEmisionCO2e</code>, horaria,
            para todo el sistema nacional.
          </p>
          <p className="mt-3 text-sm leading-relaxed text-amber-600 dark:text-amber-400">
            XM publica con unos días de rezago. Por eso el dato no es de "ahora mismo" y su
            antigüedad se muestra siempre.
          </p>
        </div>
      </div>

      <div className="card card-pad mt-4 sm:mt-6">
        <h2 className="mb-6 text-base font-semibold text-heading">Intensidad de carbono por hora</h2>
        <div className="h-72 w-full sm:h-80">
          {datosGrafica.length > 1 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={datosGrafica} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradEnergia" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#f59e0b" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={c.rejilla} />
                <XAxis dataKey="fecha" axisLine={false} tickLine={false}
                  tick={{ fill: c.eje, fontSize: 11 }} dy={8} minTickGap={28} />
                <YAxis axisLine={false} tickLine={false}
                  tick={{ fill: c.eje, fontSize: 12 }} width={48} />
                <Tooltip
                  contentStyle={{
                    background: c.tooltipBg, border: `1px solid ${c.tooltipBorde}`,
                    borderRadius: 12, color: c.tooltipTexto, fontSize: 13,
                  }}
                  labelStyle={{ color: c.tooltipTexto }}
                  formatter={(v) => [`${Number(v).toFixed(1)} gCO₂eq/kWh`, 'Intensidad']}
                />
                <Area type="monotone" dataKey="intensidad" stroke="#f59e0b" strokeWidth={2.5}
                  fill="url(#gradEnergia)" activeDot={{ r: 5 }} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full flex-col items-center justify-center px-6 text-center text-muted">
              {cargando && !datos ? (
                <div className="skeleton h-40 w-full max-w-lg" />
              ) : error ? (
                'Sin conexión con el backend.'
              ) : (
                <>
                  <p>Todavía no hay suficiente historial para graficar.</p>
                  <p className="mt-2 text-sm">
                    Se acumula con{' '}
                    <code className="rounded bg-surface-soft px-1.5 py-0.5">python collector.py</code>
                  </p>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
