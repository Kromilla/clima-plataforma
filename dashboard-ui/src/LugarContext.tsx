/**
 * LugarContext.tsx — Contexto y hook del lugar activo.
 *
 * El componente `LugarProvider` vive en su propio archivo para que este módulo
 * exporte solo el contexto y el hook (regla react-refresh).
 */
import { createContext, useContext } from 'react';
import { type Lugar } from './api';

export interface LugarState {
  lugarId: string | null;
  lugares: Lugar[];
  error: string | null;
  /** Reintentos automáticos acumulados; >0 significa que el backend no responde. */
  intentos: number;
  reintentar: () => void;
}

export const LugarCtx = createContext<LugarState>({
  lugarId: null,
  lugares: [],
  error: null,
  intentos: 0,
  reintentar: () => {},
});

export function useLugar() {
  return useContext(LugarCtx);
}
