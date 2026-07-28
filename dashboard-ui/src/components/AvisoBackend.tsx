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
    <div className="bg-red-50 border border-red-200 rounded-xl p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="font-medium text-red-800">No se pudo conectar con el backend</p>
          <p className="text-sm text-red-700 mt-1">
            Arráncalo con{' '}
            <code className="bg-red-100 px-1.5 py-0.5 rounded">python api.py</code>
            {' '}— la página se reconectará sola.
          </p>
          {intentos > 0 && (
            <p className="text-xs text-red-500 mt-1.5 flex items-center gap-1.5">
              <RefreshCw className="w-3 h-3 animate-spin" />
              Reintentando… ({intentos} {intentos === 1 ? 'intento' : 'intentos'})
            </p>
          )}
          <p className="text-xs text-red-400 mt-1.5 font-mono truncate" title={error}>
            {error}
          </p>
        </div>
        <button
          onClick={onReintentar}
          className="flex-shrink-0 text-sm border border-red-300 text-red-700 hover:bg-red-100 px-3 py-1.5 rounded-lg transition-colors"
        >
          Reintentar
        </button>
      </div>
    </div>
  );
}
