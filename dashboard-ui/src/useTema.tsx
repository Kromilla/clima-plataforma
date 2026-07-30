/**
 * useTema.tsx — Contexto y hooks del tema claro/oscuro.
 *
 * Es un contexto (y no un hook suelto) para que al alternar el tema se
 * re-rendericen también las gráficas, que necesitan recalcular sus colores de
 * ejes y rejilla: Recharts no lee variables CSS.
 *
 * El componente `TemaProvider` vive en su propio archivo para que este módulo
 * exporte solo hooks/contexto (regla react-refresh: un archivo no debe mezclar
 * componentes con no-componentes).
 */
import { createContext, useContext } from 'react';

export type Tema = 'claro' | 'oscuro';

export interface TemaState {
  tema: Tema;
  alternar: () => void;
}

export const TemaCtx = createContext<TemaState>({ tema: 'claro', alternar: () => {} });

export function useTema() {
  return useContext(TemaCtx);
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
