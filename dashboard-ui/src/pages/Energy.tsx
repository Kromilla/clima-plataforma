import { useEffect, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { Activity } from 'lucide-react';
import {
  fetchActual, fetchHistorial, FUENTE_ENERGIA,
  type Lectura, type LecturasActuales,
} from '../api';
import { useLugar } from '../LugarContext';
import MetricCard from '../components/MetricCard';

/**
 * Referencia de intensidad de carbono. La red colombiana es mayoritariamente
 * hidráulica, así que suele estar en el rango bajo (~100-250 gCO₂eq/kWh).
 */
function nivelIntensidad(v: number): { texto: string; clase: string } {
  if (v < 150) return { texto: 'Limpia', clase: 'bg-green-100 text-green-800' };
  if (v < 300) return { texto: 'Moderada', clase: 'bg-yellow-100 text-yellow-800' };
  if (v < 500) return { texto: 'Alta', clase: 'bg-orange-100 text-orange-800' };
  return { texto: 'Muy alta', clase: 'bg-red-100 text-red-800' };
}

export default function Energy() {
  const { lugarId } = useLugar();
  const [actual, setActual] = useState<LecturasActuales>({});
  const [historial, setHistorial] = useState<Lectura[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    if (!lugarId) return;
    setCargando(true);

    Promise.all([
      fetchActual(lugarId),
      fetchHistorial(FUENTE_ENERGIA, lugarId, 48),
    ])
      .then(([act, hist]) => {
        setActual(act);
        setHistorial(hist);
        setError(null);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setCargando(false));
  }, [lugarId]);

  const energia = actual[FUENTE_ENERGIA] ?? null;

  const datosGrafica = historial.map((h) => ({
    fecha: new Date(h.ts).toLocaleString([], {
      day: '2-digit', month: '2-digit', hour: '2-digit',
    }),
    intensidad: h.valor,
  }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-800">Energía y Emisiones</h2>
        <p className="text-gray-500 mt-1">Sistema Interconectado Nacional — Colombia</p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 text-sm">
          No se pudo cargar los datos: {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <MetricCard
          titulo="Intensidad de carbono"
          icono={<Activity className="w-6 h-6 text-yellow-600" />}
          colorIcono="bg-yellow-50"
          lectura={energia}
          unidadFallback="gCO₂eq/kWh"
          badge={energia ? nivelIntensidad(energia.valor) : null}
        />

        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h3 className="text-sm font-medium text-gray-500">Sobre esta fuente</h3>
          <p className="mt-3 text-sm text-gray-600 leading-relaxed">
            Datos oficiales de <strong>XM</strong>, operador del mercado eléctrico
            colombiano. Métrica <code className="bg-gray-100 px-1 rounded">factorEmisionCO2e</code>,
            horaria, para todo el sistema nacional.
          </p>
          <p className="mt-3 text-sm text-amber-600 leading-relaxed">
            XM publica con unos días de rezago. Por eso el dato no es de "ahora
            mismo" y su antigüedad se muestra siempre.
          </p>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h3 className="text-lg font-semibold text-gray-800 mb-6">
          Intensidad de carbono por hora
        </h3>
        <div className="h-80 w-full">
          {datosGrafica.length > 1 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={datosGrafica}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f3f4f6" />
                <XAxis
                  dataKey="fecha" axisLine={false} tickLine={false}
                  tick={{ fill: '#6b7280', fontSize: 11 }} dy={10}
                />
                <YAxis
                  axisLine={false} tickLine={false}
                  tick={{ fill: '#6b7280', fontSize: 12 }} dx={-10}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: '8px', border: 'none',
                    boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                  }}
                  formatter={(v) => [`${Number(v).toFixed(1)} gCO₂eq/kWh`, 'Intensidad']}
                />
                <Line
                  type="monotone" dataKey="intensidad" stroke="#ca8a04"
                  strokeWidth={3} dot={false} activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-gray-400 text-center px-6">
              {cargando ? (
                'Cargando…'
              ) : (
                <>
                  <p>Todavía no hay suficiente historial para graficar.</p>
                  <p className="text-sm mt-2">
                    Se acumula con{' '}
                    <code className="bg-gray-100 px-1.5 py-0.5 rounded">python collector.py</code>
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
