/**
 * PageHeader.tsx — Encabezado consistente para cada página.
 */
import type { ReactNode } from 'react';

interface Props {
  titulo: string;
  subtitulo?: string;
  acciones?: ReactNode;
}

export default function PageHeader({ titulo, subtitulo, acciones }: Props) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display text-2xl font-bold text-heading sm:text-[26px]">{titulo}</h1>
        {subtitulo && <p className="mt-1 text-sm text-muted">{subtitulo}</p>}
      </div>
      {acciones && <div className="flex items-center gap-2">{acciones}</div>}
    </div>
  );
}
