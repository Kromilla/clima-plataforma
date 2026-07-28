import { useEffect, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { Wind, Thermometer } from 'lucide-react';
import {
  fetchActual, fetchHistorial, FUENTE_AIRE, FUENTE_CLIMA,
  type Lectura, type LecturasActuales,
} from '../api';
import { useLugar } from '../LugarContext';
import MetricCard from '../components/MetricCard';

/** Escala PM2.5 — misma que usa alerts.py en el backend. */
function nivelPm25(v: number): { texto: string; clase: string } {
  if (v < 12) return { texto: 'Buena', clase: 'bg-green-100 text-green-800' };
  if (v < 35.4) return { texto: 'Moderada', clase: 'bg-yellow-100 text-yellow-800' };
  if (v < 55.4) return { texto: 'Dañina (sensibles)', clase: 'bg-orange-100 text-orange-800' };
  if (v < 150.4) return { texto: 'Dañina', clase: 'bg-red-100 text-red-800' };
  if (v < 250.4) return { texto: 'Muy dañina', clase: 'bg-purple-100 text-purple-800' };
  return { texto: 'Peligrosa', clase: 'bg-gray-800 text-white' };
}

export default function AirQuality() {
  const { lugarId, lugares } = useLugar();
  const [actual, setActual] = useState<LecturasActuales>({});
  const [historial, setHistorial] = useState<Lectura[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    if (!lugarId) return;
    setCargando(true);

    Promise.all([
      fetchActual(lugarId),
      fetchHistorial(FUENTE_AIRE, lugarId, 24),
    ])
      .then(([act, hist]) => {
        setActual(act);
        setHistorial(hist);
        setError(null);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setCargando(false));
  }, [lugarId]);

  const aire = actual[FUENTE_AIRE] ?? null;
  const clima = actual[FUENTE_CLIMA] ?? null;
  const nombreLugar = lugares.find((l) => l.id === lugarId)?.nombre ?? lugarId ?? '';

  const datosGrafica = historial.map((h) => ({
    hora: new Date(h.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    pm25: h.valor,
  }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-800">Aire y Clima</h2>
        <p className="text-gray-500 mt-1">{nombreLugar}</p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 text-sm">
          No se pudo cargar los datos: {error}
          <div className="text-red-500 mt-1">
            ¿Está corriendo el backend? <code>python api.py</code>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <MetricCard
          titulo="PM2.5"
          icono={<Wind className="w-6 h-6 text-green-600" />}
          colorIcono="bg-green-50"
          lectura={aire}
          unidadFallback="µg/m³"
          badge={aire ? nivelPm25(aire.valor) : null}
        />
        <MetricCard
          titulo="Temperatura"
          icono={<Thermometer className="w-6 h-6 text-orange-600" />}
          colorIcono="bg-orange-50"
          lectura={clima}
          unidadFallback="°C"
        />
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h3 className="text-lg font-semibold text-gray-800 mb-6">
          Tendencia PM2.5 (últimas {datosGrafica.length || 24} lecturas)
        </h3>
        <div className="h-80 w-full">
          {datosGrafica.length > 1 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={datosGrafica}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f3f4f6" />
                <XAxis
                  dataKey="hora" axisLine={false} tickLine={false}
                  tick={{ fill: '#6b7280', fontSize: 12 }} dy={10}
                />
                <YAxis
                  axisLine={false} tickLine={false}
                  tick={{ fill: '#6b7280', fontSize: 12 }} dx={-10}
                  unit=" µg"
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: '8px', border: 'none',
                    boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                  }}
                  formatter={(v) => [`${Number(v).toFixed(1)} µg/m³`, 'PM2.5']}
                />
                <Line
                  type="monotone" dataKey="pm25" stroke="#16a34a"
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
                    El historial se acumula con el recolector corriendo:{' '}
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
