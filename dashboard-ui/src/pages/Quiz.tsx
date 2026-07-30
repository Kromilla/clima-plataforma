import { useEffect, useState } from 'react';
import { CheckCircle2, XCircle, Share2, RotateCcw, Brain } from 'lucide-react';
import {
  fetchPreguntas, calificarQuiz, type PreguntaQuiz, type ResultadoQuiz,
} from '../api';
import PageHeader from '../components/PageHeader';

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

  const solucionPara = (id: number) => resultado?.solucionario.find((s) => s.id === id);

  return (
    <div className="max-w-3xl">
      <PageHeader titulo="Quiz de clima" subtitulo={`${preguntas.length} preguntas sobre aire, energía e incendios`} />

      {error && (
        <div className="mb-6 rounded-xl bg-red-500/12 p-4 text-sm text-red-600 dark:text-red-400">{error}</div>
      )}

      {resultado && (
        <div className="card card-pad mb-6 text-center">
          <div className="font-display text-5xl font-bold tabular-nums text-heading">
            {resultado.puntaje}<span className="text-2xl text-muted">/{resultado.total}</span>
          </div>
          <p className="mt-2 text-xl text-heading">{resultado.nivel}</p>
          <p className="mt-1 text-sm text-muted">{resultado.mensaje}</p>
          <div className="mt-4 flex flex-wrap justify-center gap-1">
            {preguntas.map((p) => (
              <span key={p.id}
                className={`h-6 w-6 rounded ${resultado.correctas.includes(p.id) ? 'bg-emerald-500' : 'bg-red-400'}`}
                title={`Pregunta ${p.id}`} />
            ))}
          </div>
          <div className="mt-5 flex justify-center gap-3">
            <button onClick={compartir} className="btn-primary">
              <Share2 className="h-4 w-4" />{copiado ? '¡Copiado!' : 'Compartir'}
            </button>
            <button onClick={reiniciar} className="btn-ghost">
              <RotateCcw className="h-4 w-4" />Reintentar
            </button>
          </div>
        </div>
      )}

      {preguntas.length === 0 && !error ? (
        <div className="card card-pad grid place-items-center py-16 text-center text-muted">
          <div><Brain className="mx-auto mb-3 h-8 w-8 text-muted" />Cargando preguntas…</div>
        </div>
      ) : (
        <div className="space-y-4">
          {preguntas.map((p, idx) => {
            const solucion = solucionPara(p.id);
            const elegida = elegidas[p.id];
            const acerto = resultado?.correctas.includes(p.id);

            return (
              <div key={p.id}
                className={`card card-pad ${resultado ? (acerto ? '!border-emerald-400/50' : '!border-red-400/50') : ''}`}>
                <div className="flex items-start justify-between gap-4">
                  <p className="font-medium text-heading">{idx + 1}. {p.texto}</p>
                  {resultado && (acerto
                    ? <CheckCircle2 className="h-5 w-5 flex-shrink-0 text-emerald-500" />
                    : <XCircle className="h-5 w-5 flex-shrink-0 text-red-500" />)}
                </div>
                <span className="badge badge-muted mt-2">{p.categoria}</span>

                <div className="mt-4 space-y-2">
                  {p.opciones.map((opcion, i) => {
                    const seleccionada = elegida === i;
                    const esCorrecta = solucion?.correcta === i;
                    let clase = 'border-line hover:bg-surface-soft';
                    if (resultado) {
                      if (esCorrecta) clase = 'border-emerald-400/60 bg-emerald-500/10';
                      else if (seleccionada) clase = 'border-red-400/60 bg-red-500/10';
                      else clase = 'border-line opacity-60';
                    } else if (seleccionada) {
                      clase = 'border-brand bg-brand/10';
                    }
                    return (
                      <button key={i} type="button" disabled={!!resultado}
                        onClick={() => setElegidas((e) => ({ ...e, [p.id]: i }))}
                        className={`w-full rounded-xl border px-4 py-2.5 text-left text-sm text-body transition-colors ${clase} ${resultado ? 'cursor-default' : 'cursor-pointer'}`}>
                        {opcion}
                      </button>
                    );
                  })}
                </div>

                {solucion && (
                  <div className="mt-4 rounded-xl bg-sky-500/8 p-4">
                    <p className="text-sm leading-relaxed text-body">{solucion.explicacion}</p>
                    <p className="mt-2 text-xs text-muted">Fuente: {solucion.fuente}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {!resultado && preguntas.length > 0 && (
        <div className="sticky bottom-4 mt-4">
          <button onClick={enviar} disabled={!completo}
            className="btn-primary w-full shadow-card-hover">
            {completo ? 'Ver resultado' : `Faltan ${preguntas.length - respondidas} de ${preguntas.length}`}
          </button>
        </div>
      )}
    </div>
  );
}
