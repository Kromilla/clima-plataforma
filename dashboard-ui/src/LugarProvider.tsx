/**
 * LugarProvider.tsx — Resuelve el lugar activo desde /api/lugares.
 *
 * Antes se pedía una sola vez: si el backend no estaba listo en ese instante,
 * `lugarId` quedaba null para siempre y TODAS las pestañas se quedaban muertas
 * aunque la API volviera. Ahora reintenta con espera creciente (useFetch).
 */
import { type ReactNode } from 'react';
import { fetchLugares } from './api';
import { useFetch } from './useFetch';
import { LugarCtx } from './LugarContext';

export function LugarProvider({ children }: { children: ReactNode }) {
  // Los lugares casi nunca cambian: basta con reintentar si falla, sin refresco
  // periódico una vez que se obtuvieron.
  const { datos, error, intentos, recargar } = useFetch(fetchLugares, [], {
    intervaloMs: 0,
  });

  return (
    <LugarCtx.Provider
      value={{
        lugarId: datos?.default ?? null,
        lugares: datos?.lugares ?? [],
        error,
        intentos,
        reintentar: recargar,
      }}
    >
      {children}
    </LugarCtx.Provider>
  );
}
