import { useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell,
} from 'recharts';
import { Leaf, Lightbulb, Info } from 'lucide-react';
import { calcularHuella, type RespuestasHuella, type ResultadoHuella } from '../api';

const TRANSPORTES: { valor: string; etiqueta: string }[] = [
  { valor: 'auto_gasolina', etiqueta: 'Auto a gasolina' },
  { valor: 'auto_diesel', etiqueta: 'Auto diésel' },
  { valor: 'auto_hibrido', etiqueta: 'Auto híbrido' },
  { valor: 'auto_electrico', etiqueta: 'Auto eléctrico' },
  { valor: 'moto', etiqueta: 'Moto' },
  { valor: 'bus', etiqueta: 'Bus' },
  { valor: 'metro_tren', etiqueta: 'Metro o tren' },
  { valor: 'bicicleta_caminar', etiqueta: 'Bicicleta o a pie' },
];

const DIETAS: { valor: string; etiqueta: string }[] = [
  { valor: 'carne_alta', etiqueta: 'Mucha carne (>100 g/día)' },
  { valor: 'carne_media', etiqueta: 'Carne moderada (50-99 g/día)' },
  { valor: 'carne_baja', etiqueta: 'Poca carne (<50 g/día)' },
  { valor: 'pescetariano', etiqueta: 'Pescetariano' },
  { valor: 'vegetariano', etiqueta: 'Vegetariano' },
  { valor: 'vegano', etiqueta: 'Vegano' },
];

const COLORES = ['#16a34a', '#0ea5e9', '#f59e0b', '#ef4444', '#8b5cf6'];

const INICIAL: RespuestasHuella = {
  transporte: 'auto_gasolina',
  km_semana: 100,
  pasajeros_auto: 1,
  horas_vuelo_anio: 0,
  kwh_mes: 150,
  personas_hogar: 3,
  gas_m3_mes: 0,
  glp_kg_mes: 15,
  usa_factor_colombia: true,
  dieta: 'carne_media',
  residuos_kg_semana: 7,
  recicla: false,
};

function Campo({
  etiqueta, children, ayuda,
}: { etiqueta: string; children: React.ReactNode; ayuda?: string }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-gray-700">{etiqueta}</span>
      {children}
      {ayuda && <span className="block text-xs text-gray-400 mt-1">{ayuda}</span>}
    </label>
  );
}

const claseInput =
  'mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm ' +
  'focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent';

export default function Footprint() {
  const [datos, setDatos] = useState<RespuestasHuella>(INICIAL);
  const [resultado, setResultado] = useState<ResultadoHuella | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [calculando, setCalculando] = useState(false);

  const set = <K extends keyof RespuestasHuella>(k: K, v: RespuestasHuella[K]) =>
    setDatos((d) => ({ ...d, [k]: v }));

  const num = (v: string) => (v === '' ? 0 : Math.max(0, Number(v)));

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setCalculando(true);
    try {
      setResultado(await calcularHuella(datos));
      setError(null);
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
      setResultado(null);
    } finally {
      setCalculando(false);
    }
  }

  const datosGrafica = resultado
    ? Object.entries(resultado.desglose)
        .map(([categoria, valor]) => ({ categoria, valor }))
        .filter((d) => d.valor > 0)
    : [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-800">Mi huella de carbono</h2>
        <p className="text-gray-500 mt-1">
          Estimación anual en toneladas de CO₂ equivalente
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Formulario */}
        <form
          onSubmit={enviar}
          className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-5"
        >
          <h3 className="font-semibold text-gray-800">Transporte</h3>
          <Campo etiqueta="¿Cómo te mueves normalmente?">
            <select
              className={claseInput}
              value={datos.transporte}
              onChange={(e) => set('transporte', e.target.value)}
            >
              {TRANSPORTES.map((t) => (
                <option key={t.valor} value={t.valor}>{t.etiqueta}</option>
              ))}
            </select>
          </Campo>

          <div className="grid grid-cols-2 gap-4">
            <Campo etiqueta="Kilómetros por semana">
              <input
                type="number" min={0} className={claseInput}
                value={datos.km_semana}
                onChange={(e) => set('km_semana', num(e.target.value))}
              />
            </Campo>
            <Campo etiqueta="Ocupantes del auto" ayuda="Compartir divide la huella">
              <input
                type="number" min={1} className={claseInput}
                value={datos.pasajeros_auto}
                onChange={(e) => set('pasajeros_auto', Math.max(1, Number(e.target.value) || 1))}
              />
            </Campo>
          </div>

          <Campo etiqueta="Horas de vuelo al año" ayuda="Un Bogotá-Madrid son ~10 h ida y vuelta">
            <input
              type="number" min={0} className={claseInput}
              value={datos.horas_vuelo_anio}
              onChange={(e) => set('horas_vuelo_anio', num(e.target.value))}
            />
          </Campo>

          <h3 className="font-semibold text-gray-800 pt-2">Hogar</h3>
          <div className="grid grid-cols-2 gap-4">
            <Campo etiqueta="Electricidad (kWh/mes)" ayuda="Míralo en tu factura">
              <input
                type="number" min={0} className={claseInput}
                value={datos.kwh_mes}
                onChange={(e) => set('kwh_mes', num(e.target.value))}
              />
            </Campo>
            <Campo etiqueta="Personas en el hogar">
              <input
                type="number" min={1} className={claseInput}
                value={datos.personas_hogar}
                onChange={(e) => set('personas_hogar', Math.max(1, Number(e.target.value) || 1))}
              />
            </Campo>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Campo etiqueta="Gas natural (m³/mes)">
              <input
                type="number" min={0} className={claseInput}
                value={datos.gas_m3_mes}
                onChange={(e) => set('gas_m3_mes', num(e.target.value))}
              />
            </Campo>
            <Campo etiqueta="GLP en cilindro (kg/mes)">
              <input
                type="number" min={0} className={claseInput}
                value={datos.glp_kg_mes}
                onChange={(e) => set('glp_kg_mes', num(e.target.value))}
              />
            </Campo>
          </div>

          <h3 className="font-semibold text-gray-800 pt-2">Dieta y residuos</h3>
          <Campo etiqueta="Tu alimentación">
            <select
              className={claseInput}
              value={datos.dieta}
              onChange={(e) => set('dieta', e.target.value)}
            >
              {DIETAS.map((d) => (
                <option key={d.valor} value={d.valor}>{d.etiqueta}</option>
              ))}
            </select>
          </Campo>

          <Campo etiqueta="Basura por semana (kg)">
            <input
              type="number" min={0} className={claseInput}
              value={datos.residuos_kg_semana}
              onChange={(e) => set('residuos_kg_semana', num(e.target.value))}
            />
          </Campo>

          <label className="flex items-center space-x-2 cursor-pointer">
            <input
              type="checkbox" className="rounded text-green-600 focus:ring-green-500"
              checked={datos.recicla}
              onChange={(e) => set('recicla', e.target.checked)}
            />
            <span className="text-sm text-gray-700">Reciclo habitualmente</span>
          </label>

          <button
            type="submit"
            disabled={calculando}
            className="w-full bg-green-600 hover:bg-green-700 disabled:bg-gray-300 text-white font-medium py-2.5 rounded-lg transition-colors"
          >
            {calculando ? 'Calculando…' : 'Calcular mi huella'}
          </button>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">
              {error}
            </p>
          )}
        </form>

        {/* Resultado */}
        <div className="space-y-6">
          {!resultado ? (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12 text-center">
              <Leaf className="w-10 h-10 text-green-300 mx-auto mb-3" />
              <p className="text-gray-500">
                Completa el formulario para ver tu estimación.
              </p>
            </div>
          ) : (
            <>
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <p className="text-sm text-gray-500">Tu huella estimada</p>
                <div className="flex items-baseline space-x-2 mt-1">
                  <span className="text-5xl font-bold text-gray-900">
                    {resultado.total_t.toFixed(2)}
                  </span>
                  <span className="text-lg text-gray-500">t CO₂e / año</span>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-gray-500">vs. promedio Colombia</p>
                    <p className="font-semibold text-gray-900 mt-0.5">
                      {resultado.vs_colombia.toFixed(2)}×
                    </p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-gray-500">vs. promedio mundial</p>
                    <p className="font-semibold text-gray-900 mt-0.5">
                      {resultado.vs_mundial.toFixed(2)}×
                    </p>
                  </div>
                </div>

                <div
                  className={`mt-3 rounded-lg p-3 text-sm ${
                    resultado.cumple_paris
                      ? 'bg-green-50 text-green-800'
                      : 'bg-amber-50 text-amber-800'
                  }`}
                >
                  {resultado.cumple_paris
                    ? `✅ Estás dentro del objetivo de París para 2030 (${resultado.referencias.objetivo_paris_2030_t} t).`
                    : `Por encima del objetivo de París para 2030 (${resultado.referencias.objetivo_paris_2030_t} t).`}
                </div>
              </div>

              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <h3 className="font-semibold text-gray-800 mb-4">De dónde viene</h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={datosGrafica} layout="vertical" margin={{ left: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f3f4f6" />
                      <XAxis type="number" tick={{ fill: '#6b7280', fontSize: 12 }} />
                      <YAxis
                        type="category" dataKey="categoria" width={80}
                        tick={{ fill: '#6b7280', fontSize: 12 }} axisLine={false} tickLine={false}
                      />
                      <Tooltip
                        formatter={(v) => [`${Number(v).toFixed(2)} t CO₂e`, 'Emisiones']}
                        contentStyle={{ borderRadius: '8px', border: 'none' }}
                      />
                      <ReferenceLine
                        x={resultado.referencias.objetivo_paris_2030_t}
                        stroke="#dc2626" strokeDasharray="4"
                      />
                      <Bar dataKey="valor" radius={[0, 4, 4, 0]}>
                        {datosGrafica.map((_, i) => (
                          <Cell key={i} fill={COLORES[i % COLORES.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="text-xs text-gray-400 mt-2">
                  La línea roja marca el objetivo de París para 2030 ({resultado.referencias.objetivo_paris_2030_t} t/persona).
                </p>
              </div>

              {resultado.recomendaciones.length > 0 && (
                <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                  <div className="flex items-center space-x-2 mb-3">
                    <Lightbulb className="w-5 h-5 text-amber-500" />
                    <h3 className="font-semibold text-gray-800">
                      Qué tendría más impacto en tu caso
                    </h3>
                  </div>
                  <ul className="space-y-2">
                    {resultado.recomendaciones.map((r, i) => (
                      <li key={i} className="text-sm text-gray-600 flex space-x-2">
                        <span className="text-green-600 font-medium">{i + 1}.</span>
                        <span>{r}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {resultado.detalles.length > 0 && (
                <div className="bg-blue-50 border border-blue-100 rounded-xl p-5">
                  <div className="flex items-center space-x-2 mb-2">
                    <Info className="w-4 h-4 text-blue-600" />
                    <h3 className="font-medium text-blue-900 text-sm">
                      Cómo se calculó
                    </h3>
                  </div>
                  <ul className="space-y-1.5">
                    {resultado.detalles.map((d, i) => (
                      <li key={i} className="text-xs text-blue-800 leading-relaxed">• {d}</li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="text-xs text-gray-400 leading-relaxed">
                Estimación educativa con factores de EPA, DEFRA y Poore &amp; Nemecek
                (2018). No cubre bienes de consumo, servicios ni infraestructura
                pública, que pueden ser una parte importante del total.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
