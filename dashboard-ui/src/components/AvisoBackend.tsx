/**
 * AvisoBackend.tsx — Aviso cuando el backend no responde.
 *
 * Muestra que se está reintentando en vez de dejar un "Failed to fetch" seco:
 * el usuario necesita saber si debe hacer algo o solo esperar.
 */
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  error: string;
  intentos: number;
  onReintentar: () => void;
}

export default function AvisoBackend({ error, intentos, onReintentar }: Props) {
  return (
    <div className="card card-pad border-red-300/60 dark:border-red-500/30">
      <div className="flex items-start gap-3">
        <div className="grid h-10 w-10 flex-shrink-0 place-items-center rounded-xl bg-red-500/15">
          <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-heading">No se pudo conectar con el backend</p>
          <p className="mt-1 text-sm text-body">
            Arráncalo con{' '}
            <code className="rounded bg-surface-soft px-1.5 py-0.5 text-xs">python api.py</code>
            {' '}— la página se reconectará sola.
          </p>
          {intentos > 0 && (
            <p className="mt-2 flex items-center gap-1.5 text-xs text-muted">
              <RefreshCw className="h-3 w-3 animate-spin" />
              Reintentando… ({intentos} {intentos === 1 ? 'intento' : 'intentos'})
            </p>
          )}
          <p className="mt-1.5 truncate font-mono text-xs text-muted" title={error}>{error}</p>
        </div>
        <button onClick={onReintentar} className="btn-ghost flex-shrink-0 !py-1.5 text-sm">
          Reintentar
        </button>
      </div>
    </div>
  );
}
