import { useEffect, useState } from 'react';
import { CheckCircle2, XCircle, Share2, RotateCcw, Brain } from 'lucide-react';
import {
  fetchPreguntas, calificarQuiz,
  type PreguntaQuiz, type ResultadoQuiz,
} from '../api';

export default function Quiz() {
  const [preguntas, setPreguntas] = useState<PreguntaQuiz[]>([]);
  const [elegidas, setElegidas] = useState<Record<number, number>>({});
  const [resultado, setResultado] = useState<ResultadoQuiz | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copiado, setCopiado] = useState(false);

  useEffect(() => {
    fetchPreguntas().then(setPreguntas).catch((e) => setError(String(e)));
  }, []);

  const respondidas = Object.keys(elegidas).length;
  const completo = preguntas.length > 0 && respondidas === preguntas.length;

  async function enviar() {
    try {
      setResultado(await calificarQuiz(elegidas));
      setError(null);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) {
      setError(String(e));
    }
  }

  function reiniciar() {
    setElegidas({});
    setResultado(null);
    setCopiado(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function compartir() {
    if (!resultado) return;
    try {
      await navigator.clipboard.writeText(resultado.compartir);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2500);
    } catch {
      setError('No se pudo copiar al portapapeles');
    }
  }

  const solucionPara = (id: number) =>
    resultado?.solucionario.find((s) => s.id === id);

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h2 className="text-2xl font-bold text-gray-800">Quiz de clima</h2>
        <p className="text-gray-500 mt-1">
          {preguntas.length} preguntas sobre aire, energía e incendios
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 text-sm">
          {error}
        </div>
      )}

      {resultado && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 text-center">
          <div className="text-5xl font-bold text-gray-900">
            {resultado.puntaje}
            <span className="text-2xl text-gray-400">/{resultado.total}</span>
          </div>
          <p className="text-xl mt-2">{resultado.nivel}</p>
          <p className="text-gray-500 text-sm mt-1">{resultado.mensaje}</p>

          <div className="mt-4 flex justify-center gap-1 flex-wrap">
            {preguntas.map((p) => (
              <span
                key={p.id}
                className={`w-6 h-6 rounded ${
                  resultado.correctas.includes(p.id) ? 'bg-green-500' : 'bg-red-400'
                }`}
                title={`Pregunta ${p.id}`}
              />
            ))}
          </div>

          <div className="mt-5 flex justify-center gap-3">
            <button
              onClick={compartir}
              className="flex items-center space-x-2 bg-gray-900 hover:bg-gray-800 text-white px-4 py-2 rounded-lg text-sm transition-colors"
            >
              <Share2 className="w-4 h-4" />
              <span>{copiado ? '¡Copiado!' : 'Compartir'}</span>
            </button>
            <button
              onClick={reiniciar}
              className="flex items-center space-x-2 border border-gray-200 hover:bg-gray-50 px-4 py-2 rounded-lg text-sm transition-colors"
            >
              <RotateCcw className="w-4 h-4" />
              <span>Reintentar</span>
            </button>
          </div>
        </div>
      )}

      {preguntas.length === 0 && !error ? (
        <div className="bg-white rounded-xl border border-gray-100 p-12 text-center text-gray-400">
          <Brain className="w-8 h-8 mx-auto mb-3 text-gray-300" />
          Cargando preguntas…
        </div>
      ) : (
        <div className="space-y-4">
          {preguntas.map((p, idx) => {
            const solucion = solucionPara(p.id);
            const elegida = elegidas[p.id];
            const acerto = resultado?.correctas.includes(p.id);

            return (
              <div
                key={p.id}
                className={`bg-white rounded-xl shadow-sm border p-6 ${
                  resultado
                    ? acerto ? 'border-green-200' : 'border-red-200'
                    : 'border-gray-100'
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <p className="font-medium text-gray-800">
                    {idx + 1}. {p.texto}
                  </p>
                  {resultado && (
                    acerto
                      ? <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
                      : <XCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
                  )}
                </div>
                <span className="inline-block mt-2 text-xs px-2 py-0.5 bg-gray-100 text-gray-500 rounded-full">
                  {p.categoria}
                </span>

                <div className="mt-4 space-y-2">
                  {p.opciones.map((opcion, i) => {
                    const seleccionada = elegida === i;
                    const esCorrecta = solucion?.correcta === i;

                    let clase = 'border-gray-200 hover:bg-gray-50';
                    if (resultado) {
                      if (esCorrecta) clase = 'border-green-400 bg-green-50';
                      else if (seleccionada) clase = 'border-red-300 bg-red-50';
                      else clase = 'border-gray-200 opacity-60';
                    } else if (seleccionada) {
                      clase = 'border-green-500 bg-green-50';
                    }

                    return (
                      <button
                        key={i}
                        type="button"
                        disabled={!!resultado}
                        onClick={() => setElegidas((e) => ({ ...e, [p.id]: i }))}
                        className={`w-full text-left border rounded-lg px-4 py-2.5 text-sm transition-colors ${clase} ${
                          resultado ? 'cursor-default' : 'cursor-pointer'
                        }`}
                      >
                        {opcion}
                      </button>
                    );
                  })}
                </div>

                {solucion && (
                  <div className="mt-4 bg-blue-50 border border-blue-100 rounded-lg p-4">
                    <p className="text-sm text-blue-900 leading-relaxed">
                      {solucion.explicacion}
                    </p>
                    <p className="text-xs text-blue-600 mt-2">
                      Fuente: {solucion.fuente}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {!resultado && preguntas.length > 0 && (
        <div className="sticky bottom-4">
          <button
            onClick={enviar}
            disabled={!completo}
            className="w-full bg-green-600 hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-medium py-3 rounded-lg shadow-lg transition-colors"
          >
            {completo
              ? 'Ver resultado'
              : `Faltan ${preguntas.length - respondidas} de ${preguntas.length}`}
          </button>
        </div>
      )}
    </div>
  );
}
