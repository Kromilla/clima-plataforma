import { useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts';
import { Leaf, Lightbulb, Info } from 'lucide-react';
import { calcularHuella, type RespuestasHuella, type ResultadoHuella } from '../api';
import { useColoresGrafica } from '../useTema';
import PageHeader from '../components/PageHeader';

const TRANSPORTES = [
  { valor: 'auto_gasolina', etiqueta: 'Auto a gasolina' },
  { valor: 'auto_diesel', etiqueta: 'Auto diésel' },
  { valor: 'auto_hibrido', etiqueta: 'Auto híbrido' },
  { valor: 'auto_electrico', etiqueta: 'Auto eléctrico' },
  { valor: 'moto', etiqueta: 'Moto' },
  { valor: 'bus', etiqueta: 'Bus' },
  { valor: 'metro_tren', etiqueta: 'Metro o tren' },
  { valor: 'bicicleta_caminar', etiqueta: 'Bicicleta o a pie' },
];

const DIETAS = [
  { valor: 'carne_alta', etiqueta: 'Mucha carne (>100 g/día)' },
  { valor: 'carne_media', etiqueta: 'Carne moderada (50-99 g/día)' },
  { valor: 'carne_baja', etiqueta: 'Poca carne (<50 g/día)' },
  { valor: 'pescetariano', etiqueta: 'Pescetariano' },
  { valor: 'vegetariano', etiqueta: 'Vegetariano' },
  { valor: 'vegano', etiqueta: 'Vegano' },
];

const COLORES = ['#0d9488', '#0ea5e9', '#f59e0b', '#ef4444', '#8b5cf6'];

const INICIAL: RespuestasHuella = {
  transporte: 'auto_gasolina', km_semana: 100, pasajeros_auto: 1, horas_vuelo_anio: 0,
  kwh_mes: 150, personas_hogar: 3, gas_m3_mes: 0, glp_kg_mes: 15,
  usa_factor_colombia: true, dieta: 'carne_media', residuos_kg_semana: 7, recicla: false,
};

function Campo({ etiqueta, children, ayuda }: { etiqueta: string; children: React.ReactNode; ayuda?: string }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-body">{etiqueta}</span>
      <div className="mt-1">{children}</div>
      {ayuda && <span className="mt-1 block text-xs text-muted">{ayuda}</span>}
    </label>
  );
}

export default function Footprint() {
  const [datos, setDatos] = useState<RespuestasHuella>(INICIAL);
  const [resultado, setResultado] = useState<ResultadoHuella | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [calculando, setCalculando] = useState(false);
  const c = useColoresGrafica();

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
    ? Object.entries(resultado.desglose).map(([categoria, valor]) => ({ categoria, valor })).filter((d) => d.valor > 0)
    : [];

  return (
    <div>
      <PageHeader titulo="Mi huella de carbono" subtitulo="Estimación anual en toneladas de CO₂ equivalente" />

      <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
        {/* Formulario */}
        <form onSubmit={enviar} className="card card-pad space-y-5">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-brand">Transporte</h3>
          <Campo etiqueta="¿Cómo te mueves normalmente?">
            <select className="field" value={datos.transporte} onChange={(e) => set('transporte', e.target.value)}>
              {TRANSPORTES.map((t) => <option key={t.valor} value={t.valor}>{t.etiqueta}</option>)}
            </select>
          </Campo>
          <div className="grid grid-cols-2 gap-4">
            <Campo etiqueta="Kilómetros por semana">
              <input type="number" min={0} className="field" value={datos.km_semana}
                onChange={(e) => set('km_semana', num(e.target.value))} />
            </Campo>
            <Campo etiqueta="Ocupantes del auto" ayuda="Compartir divide la huella">
              <input type="number" min={1} className="field" value={datos.pasajeros_auto}
                onChange={(e) => set('pasajeros_auto', Math.max(1, Number(e.target.value) || 1))} />
            </Campo>
          </div>
          <Campo etiqueta="Horas de vuelo al año" ayuda="Un Bogotá-Madrid son ~10 h ida y vuelta">
            <input type="number" min={0} className="field" value={datos.horas_vuelo_anio}
              onChange={(e) => set('horas_vuelo_anio', num(e.target.value))} />
          </Campo>

          <h3 className="pt-2 text-sm font-semibold uppercase tracking-wide text-brand">Hogar</h3>
          <div className="grid grid-cols-2 gap-4">
            <Campo etiqueta="Electricidad (kWh/mes)" ayuda="Míralo en tu factura">
              <input type="number" min={0} className="field" value={datos.kwh_mes}
                onChange={(e) => set('kwh_mes', num(e.target.value))} />
            </Campo>
            <Campo etiqueta="Personas en el hogar">
              <input type="number" min={1} className="field" value={datos.personas_hogar}
                onChange={(e) => set('personas_hogar', Math.max(1, Number(e.target.value) || 1))} />
            </Campo>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Campo etiqueta="Gas natural (m³/mes)">
              <input type="number" min={0} className="field" value={datos.gas_m3_mes}
                onChange={(e) => set('gas_m3_mes', num(e.target.value))} />
            </Campo>
            <Campo etiqueta="GLP en cilindro (kg/mes)">
              <input type="number" min={0} className="field" value={datos.glp_kg_mes}
                onChange={(e) => set('glp_kg_mes', num(e.target.value))} />
            </Campo>
          </div>

          <h3 className="pt-2 text-sm font-semibold uppercase tracking-wide text-brand">Dieta y residuos</h3>
          <Campo etiqueta="Tu alimentación">
            <select className="field" value={datos.dieta} onChange={(e) => set('dieta', e.target.value)}>
              {DIETAS.map((d) => <option key={d.valor} value={d.valor}>{d.etiqueta}</option>)}
            </select>
          </Campo>
          <Campo etiqueta="Basura por semana (kg)">
            <input type="number" min={0} className="field" value={datos.residuos_kg_semana}
              onChange={(e) => set('residuos_kg_semana', num(e.target.value))} />
          </Campo>
          <label className="flex cursor-pointer items-center gap-2">
            <input type="checkbox" className="h-4 w-4 rounded border-line text-brand focus:ring-brand/40"
              checked={datos.recicla} onChange={(e) => set('recicla', e.target.checked)} />
            <span className="text-sm text-body">Reciclo habitualmente</span>
          </label>

          <button type="submit" disabled={calculando} className="btn-primary w-full">
            {calculando ? 'Calculando…' : 'Calcular mi huella'}
          </button>
          {error && <p className="rounded-xl bg-red-500/12 p-3 text-sm text-red-600 dark:text-red-400">{error}</p>}
        </form>

        {/* Resultado */}
        <div className="space-y-4 sm:space-y-6">
          {!resultado ? (
            <div className="card card-pad grid place-items-center py-16 text-center">
              <div>
                <Leaf className="mx-auto mb-3 h-10 w-10 text-brand/40" />
                <p className="text-muted">Completa el formulario para ver tu estimación.</p>
              </div>
            </div>
          ) : (
            <>
              <div className="card card-pad">
                <p className="text-sm text-muted">Tu huella estimada</p>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="font-display text-5xl font-bold tabular-nums text-heading">
                    {resultado.total_t.toFixed(2)}
                  </span>
                  <span className="text-lg text-muted">t CO₂e / año</span>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                  <div className="tile">
                    <p className="text-muted">vs. promedio Colombia</p>
                    <p className="mt-0.5 font-semibold text-heading">{resultado.vs_colombia.toFixed(2)}×</p>
                  </div>
                  <div className="tile">
                    <p className="text-muted">vs. promedio mundial</p>
                    <p className="mt-0.5 font-semibold text-heading">{resultado.vs_mundial.toFixed(2)}×</p>
                  </div>
                </div>
                <div className={`mt-3 rounded-xl p-3 text-sm ${
                  resultado.cumple_paris ? 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300'
                    : 'bg-amber-500/12 text-amber-700 dark:text-amber-300'}`}>
                  {resultado.cumple_paris
                    ? `✅ Estás dentro del objetivo de París para 2030 (${resultado.referencias.objetivo_paris_2030_t} t).`
                    : `Por encima del objetivo de París para 2030 (${resultado.referencias.objetivo_paris_2030_t} t).`}
                </div>
              </div>

              <div className="card card-pad">
                <h3 className="mb-4 text-base font-semibold text-heading">De dónde viene</h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={datosGrafica} layout="vertical" margin={{ left: 12, right: 12 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={c.rejilla} />
                      <XAxis type="number" tick={{ fill: c.eje, fontSize: 12 }} axisLine={false} tickLine={false} />
                      <YAxis type="category" dataKey="categoria" width={78}
                        tick={{ fill: c.eje, fontSize: 12 }} axisLine={false} tickLine={false} />
                      <Tooltip
                        cursor={{ fill: c.rejilla, opacity: 0.4 }}
                        contentStyle={{ background: c.tooltipBg, border: `1px solid ${c.tooltipBorde}`, borderRadius: 12, color: c.tooltipTexto }}
                        formatter={(v) => [`${Number(v).toFixed(2)} t CO₂e`, 'Emisiones']} />
                      <ReferenceLine x={resultado.referencias.objetivo_paris_2030_t} stroke="#ef4444" strokeDasharray="4" />
                      <Bar dataKey="valor" radius={[0, 6, 6, 0]}>
                        {datosGrafica.map((_, i) => <Cell key={i} fill={COLORES[i % COLORES.length]} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-2 text-xs text-muted">
                  La línea roja marca el objetivo de París para 2030 ({resultado.referencias.objetivo_paris_2030_t} t/persona).
                </p>
              </div>

              {resultado.recomendaciones.length > 0 && (
                <div className="card card-pad">
                  <div className="mb-3 flex items-center gap-2">
                    <Lightbulb className="h-5 w-5 text-amber-500" />
                    <h3 className="text-base font-semibold text-heading">Qué tendría más impacto en tu caso</h3>
                  </div>
                  <ul className="space-y-2">
                    {resultado.recomendaciones.map((r, i) => (
                      <li key={i} className="flex gap-2 text-sm text-body">
                        <span className="font-semibold text-brand">{i + 1}.</span><span>{r}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {resultado.detalles.length > 0 && (
                <div className="card card-pad bg-sky-500/5">
                  <div className="mb-2 flex items-center gap-2">
                    <Info className="h-4 w-4 text-sky-600 dark:text-sky-400" />
                    <h3 className="text-sm font-medium text-heading">Cómo se calculó</h3>
                  </div>
                  <ul className="space-y-1.5">
                    {resultado.detalles.map((d, i) => (
                      <li key={i} className="text-xs leading-relaxed text-body">• {d}</li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="text-xs leading-relaxed text-muted">
                Estimación educativa con factores de EPA, DEFRA y Poore &amp; Nemecek (2018). No cubre
                bienes de consumo, servicios ni infraestructura pública, que pueden ser una parte
                importante del total.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
