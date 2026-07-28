import { ThermometerSun, FlaskConical, Database } from 'lucide-react';
import { fetchRiesgo, type Riesgo } from '../api';
import { useLugar } from '../LugarContext';
import { useFetch } from '../useFetch';
import AvisoBackend from '../components/AvisoBackend';

const COLOR_NIVEL: Record<string, { fondo: string; texto: string; barra: string }> = {
  bajo: { fondo: 'bg-green-50', texto: 'text-green-800', barra: 'bg-green-500' },
  moderado: { fondo: 'bg-amber-50', texto: 'text-amber-800', barra: 'bg-amber-500' },
  alto: { fondo: 'bg-red-50', texto: 'text-red-800', barra: 'bg-red-500' },
};

export default function Risk() {
  const { lugarId } = useLugar();

  const {
    datos: riesgo, error, cargando, recargar, intentos,
  } = useFetch<Riesgo>(
    () => fetchRiesgo(lugarId!),
    [lugarId],
    // El modelo se cachea 1 h en el backend, no vale la pena refrescar antes.
    { activo: !!lugarId, intervaloMs: 15 * 60_000 },
  );

  const nivel = riesgo?.nivel ?? 'bajo';
  const colores = COLOR_NIVEL[nivel];
  const pct = Math.round((riesgo?.probabilidad ?? 0) * 100);
  const modelo = riesgo?.modelo;

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h2 className="text-2xl font-bold text-gray-800">Riesgo de calor extremo</h2>
        <p className="text-gray-500 mt-1">Modelo entrenado con el historial del proyecto</p>
      </div>

      {/* La advertencia va primero y siempre, incluso si no hay datos. */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start space-x-3">
        <FlaskConical className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
        <div className="text-sm">
          <p className="font-medium text-amber-900">
            Estimación experimental — no es una alerta oficial
          </p>
          <p className="text-amber-700 mt-0.5">
            Es un ejercicio educativo. Para alertas reales consulta al IDEAM.
          </p>
        </div>
      </div>

      {error && (
        <AvisoBackend error={error} intentos={intentos} onReintentar={recargar} />
      )}

      {cargando && !riesgo ? (
        <div className="bg-white rounded-xl border border-gray-100 p-12 text-center text-gray-400">
          Entrenando el modelo…
        </div>
      ) : riesgo && !riesgo.disponible ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-8 text-center">
          <Database className="w-8 h-8 text-gray-300 mx-auto mb-3" />
          <h3 className="font-semibold text-gray-800">Historial insuficiente</h3>
          <p className="text-sm text-gray-600 mt-2 max-w-md mx-auto">{riesgo.mensaje}</p>
          <code className="inline-block mt-3 bg-gray-100 px-3 py-1.5 rounded text-sm">
            python backfill.py --dias 730
          </code>
        </div>
      ) : riesgo ? (
        <>
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm text-gray-500">
                  Probabilidad de calor extremo el {riesgo.fecha_objetivo}
                </p>
                <div className="flex items-baseline space-x-2 mt-1">
                  <span className="text-5xl font-bold text-gray-900">{pct}%</span>
                  <span className={`text-lg font-medium ${colores.texto}`}>
                    riesgo {nivel}
                  </span>
                </div>
              </div>
              <div className={`p-3 rounded-lg ${colores.fondo}`}>
                <ThermometerSun className={`w-7 h-7 ${colores.texto}`} />
              </div>
            </div>

            <div className="mt-5 h-2.5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full ${colores.barra} transition-all duration-500`}
                style={{ width: `${pct}%` }}
              />
            </div>

            <div className={`mt-4 rounded-lg p-4 text-sm ${colores.fondo} ${colores.texto}`}>
              {riesgo.mensaje}
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-gray-500">Índice de calor máximo hoy</p>
                <p className="font-semibold text-gray-900 mt-0.5">
                  {riesgo.ic_max_hoy?.toFixed(1)} °C
                </p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-gray-500">Umbral de riesgo</p>
                <p className="font-semibold text-gray-900 mt-0.5">
                  {riesgo.umbral_ic?.toFixed(0)} °C
                </p>
              </div>
            </div>

            <p className="text-xs text-gray-400 mt-4 leading-relaxed">
              El índice de calor combina temperatura y humedad (fórmula de la NOAA).
              En una ciudad costera la humedad es la que vuelve peligroso el calor:
              32 °C con 80% de humedad se sienten como 44 °C.
            </p>
          </div>

          {modelo && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
              <h3 className="font-semibold text-gray-800 mb-1">Qué tan bueno es el modelo</h3>
              <p className="text-sm text-gray-500 mb-4">
                Evaluado sobre los días más recientes, que no se usaron para entrenar.
              </p>

              {!modelo.es_util && (
                <div className="mb-4 bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
                  El modelo no supera a la referencia estadística: con los datos
                  actuales su predicción no es informativa.
                </div>
              )}

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                {[
                  { e: 'Exactitud', v: `${(modelo.exactitud * 100).toFixed(0)}%` },
                  { e: 'Precisión', v: `${(modelo.precision * 100).toFixed(0)}%` },
                  { e: 'Recall', v: `${(modelo.recall * 100).toFixed(0)}%` },
                  { e: 'F1', v: modelo.f1.toFixed(2) },
                ].map((m) => (
                  <div key={m.e} className="bg-gray-50 rounded-lg p-3">
                    <p className="text-gray-500 text-xs">{m.e}</p>
                    <p className="font-semibold text-gray-900 mt-0.5">{m.v}</p>
                  </div>
                ))}
              </div>

              <div className="mt-4 text-sm text-gray-600 space-y-1.5">
                <p>
                  Mejora sobre acertar siempre la clase mayoritaria:{' '}
                  <strong className={modelo.mejora_sobre_base > 0 ? 'text-green-700' : 'text-red-700'}>
                    {modelo.mejora_sobre_base > 0 ? '+' : ''}
                    {(modelo.mejora_sobre_base * 100).toFixed(1)} puntos
                  </strong>
                </p>
                <p className="text-gray-500 text-xs">
                  Entrenado con {modelo.n_entrenamiento} días, evaluado con {modelo.n_prueba}.
                  El {(modelo.tasa_base * 100).toFixed(0)}% de los días de prueba fueron de riesgo.
                </p>
              </div>

              <div className="mt-5">
                <p className="text-sm font-medium text-gray-700 mb-2">
                  Qué mira más el modelo
                </p>
                <div className="space-y-1.5">
                  {Object.entries(modelo.importancias).slice(0, 5).map(([nombre, imp]) => (
                    <div key={nombre} className="flex items-center space-x-3">
                      <span className="text-xs text-gray-500 w-36 flex-shrink-0 truncate">
                        {nombre.replace(/_/g, ' ')}
                      </span>
                      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500"
                          style={{ width: `${Math.min(imp * 300, 100)}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-400 w-10 text-right">
                        {(imp * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <p className="text-xs text-gray-400 mt-5 leading-relaxed">
                La validación es cronológica: se entrena con el pasado y se evalúa con
                los días siguientes. Una partición aleatoria dejaría días del futuro en
                el entrenamiento e inflaría las métricas.
              </p>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
