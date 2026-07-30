/**
 * useTema.tsx — Tema claro/oscuro compartido por toda la app.
 *
 * Es un contexto (y no un hook suelto) para que al alternar el tema se
 * re-rendericen también las gráficas, que necesitan recalcular sus colores de
 * ejes y rejilla: Recharts no lee variables CSS.
 *
 * El tema inicial ya lo aplica un script en index.html antes de pintar, para
 * que no haya parpadeo.
 */
import {
  createContext, useCallback, useContext, useEffect, useState, type ReactNode,
} from 'react';

export type Tema = 'claro' | 'oscuro';

interface TemaState {
  tema: Tema;
  alternar: () => void;
}

const Ctx = createContext<TemaState>({ tema: 'claro', alternar: () => {} });

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

  return <Ctx.Provider value={{ tema, alternar }}>{children}</Ctx.Provider>;
}

export function useTema() {
  return useContext(Ctx);
}

/** Colores para las gráficas de Recharts según el tema activo. */
export function useColoresGrafica() {
  const { tema } = useTema();
  const oscuro = tema === 'oscuro';
  return {
    rejilla: oscuro ? '#1e293b' : '#eef2f7',
    eje: oscuro ? '#64748b' : '#94a3b8',
    tooltipBg: oscuro ? '#1e293b' : '#ffffff',
    tooltipBorde: oscuro ? '#334155' : '#e2e8f0',
    tooltipTexto: oscuro ? '#e2e8f0' : '#0f172a',
  };
}
