/**
 * LugarContext.tsx — Provee el lugar activo a toda la app.
 *
 * Se resuelve desde /api/lugares. Antes se pedía una sola vez: si el backend no
 * estaba listo en ese instante, `lugarId` quedaba null para siempre y TODAS las
 * pestañas se quedaban muertas aunque la API volviera. Ahora reintenta con
 * espera creciente hasta conseguirlo.
 */
import { createContext, useContext, type ReactNode } from 'react';
import { fetchLugares, type Lugar } from './api';
import { useFetch } from './useFetch';

interface LugarState {
  lugarId: string | null;
  lugares: Lugar[];
  error: string | null;
  /** Reintentos automáticos acumulados; >0 significa que el backend no responde. */
  intentos: number;
  reintentar: () => void;
}

const Ctx = createContext<LugarState>({
  lugarId: null,
  lugares: [],
  error: null,
  intentos: 0,
  reintentar: () => {},
});

export function useLugar() {
  return useContext(Ctx);
}

export function LugarProvider({ children }: { children: ReactNode }) {
  // Los lugares casi nunca cambian: basta con reintentar si falla, sin refresco
  // periódico una vez que se obtuvieron.
  const { datos, error, intentos, recargar } = useFetch(fetchLugares, [], {
    intervaloMs: 0,
  });

  return (
    <Ctx.Provider
      value={{
        lugarId: datos?.default ?? null,
        lugares: datos?.lugares ?? [],
        error,
        intentos,
        reintentar: recargar,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}
