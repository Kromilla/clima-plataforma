/**
 * LugarContext.tsx — Provee el lugar activo a toda la app.
 *
 * Se resuelve una sola vez desde /api/lugares. Mientras carga, las páginas no
 * hacen requests: así no se repite el bug de pedir datos con un id inventado.
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { fetchLugares, type Lugar } from './api';

interface LugarState {
  lugarId: string | null;
  lugares: Lugar[];
  error: string | null;
  setLugarId: (id: string) => void;
}

const Ctx = createContext<LugarState>({
  lugarId: null,
  lugares: [],
  error: null,
  setLugarId: () => {},
});

export function useLugar() {
  return useContext(Ctx);
}

export function LugarProvider({ children }: { children: ReactNode }) {
  const [lugarId, setLugarId] = useState<string | null>(null);
  const [lugares, setLugares] = useState<Lugar[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchLugares()
      .then((data) => {
        setLugares(data.lugares);
        setLugarId(data.default);
      })
      .catch((err) => setError(String(err)));
  }, []);

  return (
    <Ctx.Provider value={{ lugarId, lugares, error, setLugarId }}>
      {children}
    </Ctx.Provider>
  );
}
