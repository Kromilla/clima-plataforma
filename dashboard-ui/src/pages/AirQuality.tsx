import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart,
} from 'recharts';
import { Wind, Thermometer } from 'lucide-react';
import {
  fetchActual, fetchHistorial, FUENTE_AIRE, FUENTE_CLIMA,
  type Lectura, type LecturasActuales,
} from '../api';
import { useLugar } from '../LugarContext';
import { useFetch } from '../useFetch';
import { useColoresGrafica } from '../useTema';
import MetricCard from '../components/MetricCard';
import AvisoBackend from '../components/AvisoBackend';
import PageHeader from '../components/PageHeader';

/** Escala PM2.5 — misma que usa alerts.py en el backend. */
function nivelPm25(v: number): { texto: string; clase: string } {
  if (v < 12) return { texto: 'Buena', clase: 'badge-good' };
  if (v < 35.4) return { texto: 'Moderada', clase: 'badge-warn' };
  if (v < 55.4) return { texto: 'Dañina (sensibles)', clase: 'badge-warn' };
  if (v < 150.4) return { texto: 'Dañina', clase: 'badge-bad' };
  return { texto: 'Muy dañina', clase: 'badge-bad' };
}

interface Datos {
  actual: LecturasActuales;
  historial: Lectura[];
}

export default function AirQuality() {
  const { lugarId, lugares } = useLugar();
  const c = useColoresGrafica();

  const { datos, error, cargando, recargar, intentos } = useFetch<Datos>(
    async () => {
      const [actual, historial] = await Promise.all([
        fetchActual(lugarId!),
        fetchHistorial(FUENTE_AIRE, lugarId!, 24),
      ]);
      return { actual, historial };
    },
    [lugarId],
    { activo: !!lugarId },
  );

  const aire = datos?.actual[FUENTE_AIRE] ?? null;
  const clima = datos?.actual[FUENTE_CLIMA] ?? null;
  const nombreLugar = lugares.find((l) => l.id === lugarId)?.nombre ?? '';

  const datosGrafica = (datos?.historial ?? []).map((h) => ({
    hora: new Date(h.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    pm25: h.valor,
  }));

  return (
    <div>
      <PageHeader titulo="Aire y Clima" subtitulo={nombreLugar || '…'} />

      {error && (
        <div className="mb-6">
          <AvisoBackend error={error} intentos={intentos} onReintentar={recargar} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:gap-6 md:grid-cols-2">
        <MetricCard
          titulo="PM2.5"
          icono={<Wind className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />}
          colorIcono="bg-emerald-500/15"
          lectura={aire}
          unidadFallback="µg/m³"
          badge={aire ? nivelPm25(aire.valor) : null}
          cargando={cargando && !datos}
        />
        <MetricCard
          titulo="Temperatura"
          icono={<Thermometer className="h-5 w-5 text-orange-500" />}
          colorIcono="bg-orange-500/15"
          lectura={clima}
          unidadFallback="°C"
          cargando={cargando && !datos}
        />
      </div>

      <div className="card card-pad mt-4 sm:mt-6">
        <h3 className="mb-6 text-base font-semibold text-heading">
          Tendencia PM2.5 · últimas {datosGrafica.length || 24} lecturas
        </h3>
        <div className="h-72 w-full sm:h-80">
          {datosGrafica.length > 1 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={datosGrafica} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradAire" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10b981" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={c.rejilla} />
                <XAxis dataKey="hora" axisLine={false} tickLine={false}
                  tick={{ fill: c.eje, fontSize: 12 }} dy={8} minTickGap={24} />
                <YAxis axisLine={false} tickLine={false}
                  tick={{ fill: c.eje, fontSize: 12 }} width={44} unit=" µg" />
                <Tooltip
                  contentStyle={{
                    background: c.tooltipBg, border: `1px solid ${c.tooltipBorde}`,
                    borderRadius: 12, color: c.tooltipTexto, fontSize: 13,
                  }}
                  labelStyle={{ color: c.tooltipTexto }}
                  formatter={(v) => [`${Number(v).toFixed(1)} µg/m³`, 'PM2.5']}
                />
                <Area type="monotone" dataKey="pm25" stroke="#10b981" strokeWidth={2.5}
                  fill="url(#gradAire)" activeDot={{ r: 5 }} />
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
                    Se acumula con el recolector corriendo:{' '}
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
