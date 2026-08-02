import { useState, type ReactNode } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom';
import {
  Wind, Zap, Flame, ThermometerSun, Moon, Sun, Menu, X, MapPin,
} from 'lucide-react';
import AirQuality from './pages/AirQuality';
import Energy from './pages/Energy';
import Fires from './pages/Fires';
import Risk from './pages/Risk';
import { fetchEstadoFuentes, type EstadoFuente } from './api';
import { useLugar } from './LugarContext';
import { LugarProvider } from './LugarProvider';
import { useFetch } from './useFetch';
import { useTema } from './useTema';
import { TemaProvider } from './TemaProvider';
import AvisoBackend from './components/AvisoBackend';

const COLOR_SEMAFORO: Record<string, string> = {
  verde: 'bg-emerald-500',
  amarillo: 'bg-amber-500',
  rojo: 'bg-red-500',
  gris: 'bg-slate-400',
};

const NAVEGACION = [
  { ruta: '/', etiqueta: 'Aire y Clima', icono: Wind },
  { ruta: '/energia', etiqueta: 'Energía', icono: Zap },
  { ruta: '/incendios', etiqueta: 'Incendios', icono: Flame },
  { ruta: '/riesgo', etiqueta: 'Riesgo de calor', icono: ThermometerSun },
];

/** Marca: una ola bajo la Sierra Nevada. El subtítulo muestra la ciudad activa. */
function Marca() {
  const { lugarId, lugares } = useLugar();
  const activo = lugares.find((l) => l.id === lugarId);
  const ciudad = activo ? activo.nombre.split(',')[0] : 'Colombia';
  return (
    <div className="flex items-center gap-2.5">
      <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand to-sky-500 shadow-glow">
        <svg viewBox="0 0 24 24" className="h-5 w-5 text-white" fill="none">
          <path d="M3 14l4-6 3 4 4-7 3 5 4-3" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" opacity="0.9" />
          <path d="M3 18c2 0 2-1.5 4-1.5s2 1.5 4 1.5 2-1.5 4-1.5 2 1.5 4 1.5"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <div className="leading-tight">
        <div className="font-display text-lg font-bold text-heading">ClimaBot</div>
        <div className="text-[11px] font-medium text-muted">{ciudad}</div>
      </div>
    </div>
  );
}

/** Selector de ciudad. Se oculta si solo hay una (no estorba). */
function SelectorLugar() {
  const { lugarId, lugares, setLugarId } = useLugar();
  if (lugares.length <= 1) return null;
  return (
    <label className="flex items-center gap-2">
      <MapPin className="h-[18px] w-[18px] flex-shrink-0 text-muted" />
      <select
        value={lugarId ?? ''}
        onChange={(e) => setLugarId(e.target.value)}
        className="field max-w-[190px] cursor-pointer py-1.5"
        aria-label="Ciudad"
      >
        {lugares.map((l) => (
          <option key={l.id} value={l.id}>{l.nombre.split(',')[0]}</option>
        ))}
      </select>
    </label>
  );
}

function SemaforoFuentes() {
  const { lugarId } = useLugar();
  const { datos: estados, error } = useFetch<Record<string, EstadoFuente>>(
    () => fetchEstadoFuentes(lugarId!),
    [lugarId],
    { activo: !!lugarId, intervaloMs: 60_000 },
  );

  if (error && !estados) {
    return <span className="text-sm text-red-500">Sin conexión</span>;
  }

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
      {Object.entries(estados ?? {}).map(([id, e]) => (
        <div key={id} className="flex items-center gap-2" title={`${e.etiqueta}: ${e.detalle}`}>
          <span className={`dot ${COLOR_SEMAFORO[e.estado] ?? 'bg-slate-400'}`} />
          <span className="text-sm font-medium text-body">{e.etiqueta}</span>
          <span className="hidden text-xs text-muted sm:inline">{e.detalle}</span>
        </div>
      ))}
    </div>
  );
}

function BotonTema() {
  const { tema, alternar } = useTema();
  return (
    <button
      onClick={alternar}
      className="grid h-9 w-9 place-items-center rounded-xl border border-line text-muted
                 transition-colors hover:bg-surface-soft hover:text-heading"
      title={tema === 'oscuro' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'}
      aria-label="Cambiar tema"
    >
      {tema === 'oscuro' ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
    </button>
  );
}

function Sidebar({ abierto, cerrar }: { abierto: boolean; cerrar: () => void }) {
  return (
    <>
      {/* Telón en móvil */}
      {abierto && (
        <div className="fixed inset-0 z-30 bg-slate-950/40 backdrop-blur-sm lg:hidden" onClick={cerrar} />
      )}

      <aside
        className={`fixed z-40 flex h-full w-64 flex-col border-r border-line bg-surface/80 backdrop-blur-xl
                    transition-transform lg:static lg:z-0 lg:h-auto lg:translate-x-0
                    ${abierto ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <div className="flex items-center justify-between px-5 py-5">
          <Marca />
          <button className="text-muted lg:hidden" onClick={cerrar} aria-label="Cerrar menú">
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 px-3 pb-6">
          {NAVEGACION.map(({ ruta, etiqueta, icono: Icono }) => (
            <NavLink
              key={ruta}
              to={ruta}
              end={ruta === '/'}
              onClick={cerrar}
              className={({ isActive }) =>
                `group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-brand/10 text-brand-strong dark:text-brand'
                    : 'text-body hover:bg-surface-soft'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icono className={`h-5 w-5 flex-shrink-0 ${isActive ? '' : 'text-muted group-hover:text-body'}`} />
                  <span>{etiqueta}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-line px-5 py-4 text-[11px] leading-relaxed text-muted">
          Datos abiertos · Open-Meteo, XM y NASA FIRMS.
          <br />No es una alerta oficial.
        </div>
      </aside>
    </>
  );
}

function Layout({ children }: { children: ReactNode }) {
  const { error, intentos, reintentar, lugarId } = useLugar();
  const [menu, setMenu] = useState(false);
  const { pathname } = useLocation();

  return (
    <div className="flex min-h-screen">
      <Sidebar abierto={menu} cerrar={() => setMenu(false)} />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-4 border-b border-line
                           bg-app/70 px-4 py-3 backdrop-blur-xl sm:px-6">
          <button className="text-muted lg:hidden" onClick={() => setMenu(true)} aria-label="Abrir menú">
            <Menu className="h-5 w-5" />
          </button>
          <SelectorLugar />
          <div className="hidden min-w-0 flex-1 sm:block">
            <SemaforoFuentes />
          </div>
          <div className="flex-1 sm:hidden" />
          <BotonTema />
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 p-4 sm:p-6 lg:p-8">
          {error && !lugarId ? (
            <AvisoBackend error={error} intentos={intentos} onReintentar={reintentar} />
          ) : (
            <div key={pathname} className="animate-fade-up">{children}</div>
          )}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <TemaProvider>
      <BrowserRouter>
        <LugarProvider>
          <Layout>
          <Routes>
            <Route path="/" element={<AirQuality />} />
            <Route path="/energia" element={<Energy />} />
            <Route path="/incendios" element={<Fires />} />
            <Route path="/riesgo" element={<Risk />} />
            {/* Cualquier ruta desconocida (incluidas /huella y /quiz retiradas) vuelve al inicio. */}
            <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Layout>
        </LugarProvider>
      </BrowserRouter>
    </TemaProvider>
  );
}
