import { useEffect, useState } from 'react';
import { ThermometerSun, FlaskConical, Database } from 'lucide-react';
import { fetchRiesgo, type Riesgo } from '../api';
import { useLugar } from '../LugarContext';
import { useFetch } from '../useFetch';
import AvisoBackend from '../components/AvisoBackend';
import PageHeader from '../components/PageHeader';

const COLOR_NIVEL: Record<string, { fondo: string; texto: string; barra: string }> = {
  bajo: { fondo: 'bg-emerald-500/12', texto: 'text-emerald-600 dark:text-emerald-400', barra: 'bg-emerald-500' },
  moderado: { fondo: 'bg-amber-500/12', texto: 'text-amber-600 dark:text-amber-400', barra: 'bg-amber-500' },
  alto: { fondo: 'bg-red-500/12', texto: 'text-red-600 dark:text-red-400', barra: 'bg-red-500' },
};

export default function Risk() {
  const { lugarId } = useLugar();

  const { datos: riesgo, error, cargando, recargar, intentos } = useFetch<Riesgo>(
    () => fetchRiesgo(lugarId!),
    [lugarId],
    { activo: !!lugarId, intervaloMs: 15 * 60_000 },
  );

  const nivel = riesgo?.nivel ?? 'bajo';
  const colores = COLOR_NIVEL[nivel];
  const pct = Math.round((riesgo?.probabilidad ?? 0) * 100);
  const modelo = riesgo?.modelo;

  // Si la carga se alarga (típico cuando el servicio free de Render venía
  // dormido), se avisa para que la espera no parezca un error.
  const [tardando, setTardando] = useState(false);
  useEffect(() => {
    if (!cargando) {
      setTardando(false);
      return;
    }
    const t = setTimeout(() => setTardando(true), 4000);
    return () => clearTimeout(t);
  }, [cargando]);

  return (
    <div>
      <PageHeader titulo="Riesgo de calor extremo" subtitulo="Modelo entrenado con el historial del proyecto" />

      {/* La advertencia va primero y siempre, incluso si no hay datos. */}
      <div className="card card-pad mb-6 flex items-start gap-3 border-amber-300/60 dark:border-amber-500/30">
        <div className="grid h-10 w-10 flex-shrink-0 place-items-center rounded-xl bg-amber-500/15">
          <FlaskConical className="h-5 w-5 text-amber-600 dark:text-amber-400" />
        </div>
        <div className="text-sm">
          <p className="font-semibold text-heading">Estimación experimental — no es una alerta oficial</p>
          <p className="mt-0.5 text-body">Es un ejercicio educativo. Para alertas reales consulta al IDEAM.</p>
        </div>
      </div>

      {error && (
        <div className="mb-6"><AvisoBackend error={error} intentos={intentos} onReintentar={recargar} /></div>
      )}

      {cargando && !riesgo ? (
        <div className="card card-pad">
          <div className="skeleton h-48 w-full" />
          {tardando && (
            <p className="mt-4 text-center text-sm text-muted">
              Reactivando el servidor… la primera carga tras un rato de inactividad
              puede tardar ~30&nbsp;s. Las siguientes son instantáneas.
            </p>
          )}
        </div>
      ) : riesgo && !riesgo.disponible && riesgo.motivo === 'sin_calor_extremo' ? (
        <div className="card card-pad text-center">
          <ThermometerSun className="mx-auto mb-3 h-8 w-8 text-muted" />
          <h2 className="font-semibold text-heading">Sin calor extremo de riesgo</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-body">{riesgo.mensaje}</p>
        </div>
      ) : riesgo && !riesgo.disponible ? (
        <div className="card card-pad text-center">
          <Database className="mx-auto mb-3 h-8 w-8 text-muted" />
          <h2 className="font-semibold text-heading">Historial insuficiente</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-body">{riesgo.mensaje}</p>
          <code className="mt-3 inline-block rounded bg-surface-soft px-3 py-1.5 text-sm">
            python backfill.py --lugar &lt;ciudad&gt; --dias 365
          </code>
        </div>
      ) : riesgo ? (
        <>
          <div className="card card-pad">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm text-muted">Probabilidad de calor extremo el {riesgo.fecha_objetivo}</p>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="font-display text-5xl font-bold tabular-nums text-heading">{pct}%</span>
                  <span className={`text-lg font-semibold ${colores.texto}`}>riesgo {nivel}</span>
                </div>
              </div>
              <div className={`grid h-12 w-12 flex-shrink-0 place-items-center rounded-xl ${colores.fondo}`}>
                <ThermometerSun className={`h-7 w-7 ${colores.texto}`} />
              </div>
            </div>

            <div className="mt-5 h-2.5 overflow-hidden rounded-full bg-surface-soft">
              <div className={`h-full ${colores.barra} transition-all duration-700`} style={{ width: `${pct}%` }} />
            </div>

            <div className={`mt-4 rounded-xl p-4 text-sm ${colores.fondo} ${colores.texto}`}>{riesgo.mensaje}</div>

            <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div className="tile">
                <p className="text-muted">Índice de calor máximo hoy</p>
                <p className="mt-0.5 font-semibold text-heading">{riesgo.ic_max_hoy?.toFixed(1)} °C</p>
              </div>
              <div className="tile">
                <p className="text-muted">Umbral de riesgo</p>
                <p className="mt-0.5 font-semibold text-heading">{riesgo.umbral_ic?.toFixed(0)} °C</p>
              </div>
            </div>

            <p className="mt-4 text-xs leading-relaxed text-muted">
              El índice de calor combina temperatura y humedad (fórmula de la NOAA). En una ciudad
              costera la humedad es la que vuelve peligroso el calor: 32 °C con 80% de humedad se
              sienten como 44 °C.
            </p>
          </div>

          {modelo && (
            <div className="card card-pad mt-4 sm:mt-6">
              <h2 className="text-base font-semibold text-heading">Qué tan bueno es el modelo</h2>
              <p className="mb-4 mt-1 text-sm text-muted">
                Evaluado en {modelo.n_prueba} días que nunca vio al entrenar, avanzando por
                ventanas sucesivas.
              </p>

              {!modelo.es_util && (
                <div className="mb-4 rounded-xl bg-amber-500/12 p-3 text-sm text-amber-700 dark:text-amber-300">
                  El modelo todavía no detecta más días de riesgo que suponer que mañana será
                  como hoy, así que su predicción no aporta información adicional.
                </div>
              )}

              <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                {[
                  { e: 'Exactitud', v: `${(modelo.exactitud * 100).toFixed(0)}%` },
                  { e: 'Precisión', v: `${(modelo.precision * 100).toFixed(0)}%` },
                  { e: 'Recall', v: `${(modelo.recall * 100).toFixed(0)}%` },
                  { e: 'F1', v: modelo.f1.toFixed(2) },
                ].map((m) => (
                  <div key={m.e} className="tile">
                    <p className="text-xs text-muted">{m.e}</p>
                    <p className="mt-0.5 font-semibold text-heading">{m.v}</p>
                  </div>
                ))}
              </div>

              {/* La comparación que decide. Acertar en promedio es fácil cuando los
                  días tranquilos son mayoría; lo que importa en una alerta es cuántos
                  días peligrosos se atrapan, y contra qué regla simple se compara. */}
              <div className="mt-4 rounded-xl border border-line p-3">
                <p className="mb-2 text-sm font-medium text-body">
                  Comparado con suponer que mañana será como hoy
                </p>
                <div className="space-y-1.5 text-sm">
                  {[
                    { e: 'Días peligrosos detectados', m: modelo.recall, p: modelo.recall_persistencia },
                    { e: 'Equilibrio (F1)', m: modelo.f1, p: modelo.f1_persistencia },
                    { e: 'Aciertos en total', m: modelo.exactitud, p: modelo.exactitud_persistencia },
                  ].map((f) => (
                    <div key={f.e} className="flex items-baseline justify-between gap-3">
                      <span className="text-muted">{f.e}</span>
                      <span className="tabular-nums">
                        <strong className={f.m > f.p ? 'text-emerald-600 dark:text-emerald-400' : 'text-body'}>
                          {(f.m * 100).toFixed(0)}%
                        </strong>
                        <span className="text-muted"> vs {(f.p * 100).toFixed(0)}%</span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <p className="mt-3 text-xs leading-relaxed text-muted">
                Entrenado con {modelo.n_entrenamiento} días. El{' '}
                {(modelo.tasa_base * 100).toFixed(0)}% de los días evaluados fueron de riesgo:
                por eso acertar en total es fácil y no basta para juzgar el modelo.
              </p>

              <div className="mt-5">
                <p className="mb-2 text-sm font-medium text-body">Qué mira más el modelo</p>
                <div className="space-y-2">
                  {Object.entries(modelo.importancias).slice(0, 5).map(([nombre, imp]) => (
                    <div key={nombre} className="flex items-center gap-3">
                      <span className="w-36 flex-shrink-0 truncate text-xs text-muted">{nombre.replace(/_/g, ' ')}</span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-soft">
                        <div className="h-full bg-brand" style={{ width: `${Math.min(imp * 300, 100)}%` }} />
                      </div>
                      <span className="w-10 text-right text-xs text-muted">{(imp * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              </div>

              <p className="mt-5 text-xs leading-relaxed text-muted">
                La validación es cronológica: se entrena con el pasado y se evalúa con los días
                siguientes. Una partición aleatoria dejaría días del futuro en el entrenamiento e
                inflaría las métricas.
              </p>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
