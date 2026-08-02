/**
 * LugarProvider.tsx — Resuelve los lugares desde /api/lugares y maneja el activo.
 *
 * Antes se pedía una sola vez: si el backend no estaba listo en ese instante,
 * `lugarId` quedaba null para siempre y TODAS las pestañas se quedaban muertas
 * aunque la API volviera. Ahora reintenta con espera creciente (useFetch).
 *
 * La ciudad activa se guarda en localStorage para que la elección persista entre
 * visitas. Si la guardada ya no existe (o no hay), cae al default del backend.
 */
import { useEffect, useState, type ReactNode } from 'react';
import { fetchLugares } from './api';
import { useFetch } from './useFetch';
import { LugarCtx } from './LugarContext';

const CLAVE = 'lugarId';

export function LugarProvider({ children }: { children: ReactNode }) {
  // Los lugares casi nunca cambian: basta con reintentar si falla, sin refresco
  // periódico una vez que se obtuvieron.
  const { datos, error, intentos, recargar } = useFetch(fetchLugares, [], {
    intervaloMs: 0,
  });

  const [elegido, setElegido] = useState<string | null>(() => localStorage.getItem(CLAVE));

  // Al cargar los lugares: si la elección guardada no es válida, usa el default.
  useEffect(() => {
    if (!datos) return;
    const valido = elegido && datos.lugares.some((l) => l.id === elegido);
    if (!valido) setElegido(datos.default);
  }, [datos, elegido]);

  const setLugarId = (id: string) => {
    setElegido(id);
    localStorage.setItem(CLAVE, id);
  };

  return (
    <LugarCtx.Provider
      value={{
        lugarId: elegido ?? datos?.default ?? null,
        lugares: datos?.lugares ?? [],
        setLugarId,
        error,
        intentos,
        reintentar: recargar,
      }}
    >
      {children}
    </LugarCtx.Provider>
  );
}
