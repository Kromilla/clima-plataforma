/**
 * TemaProvider.tsx — Provee el tema y lo persiste.
 *
 * Separado de useTema.tsx para que aquel exporte solo hooks/contexto. El tema
 * inicial ya lo aplica un script en index.html antes de pintar (sin parpadeo).
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { TemaCtx, type Tema } from './useTema';

function temaInicial(): Tema {
  return document.documentElement.classList.contains('dark') ? 'oscuro' : 'claro';
}

export function TemaProvider({ children }: { children: ReactNode }) {
  const [tema, setTema] = useState<Tema>(temaInicial);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', tema === 'oscuro');
    try {
      localStorage.setItem('tema', tema);
    } catch {
      /* almacenamiento no disponible: no es crítico */
    }
  }, [tema]);

  const alternar = useCallback(
    () => setTema((t) => (t === 'oscuro' ? 'claro' : 'oscuro')),
    [],
  );

  return <TemaCtx.Provider value={{ tema, alternar }}>{children}</TemaCtx.Provider>;
}
