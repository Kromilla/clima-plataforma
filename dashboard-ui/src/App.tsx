import { useEffect, useState, type ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import { Wind, Zap, Flame, Leaf, Brain, ThermometerSun } from 'lucide-react';
import AirQuality from './pages/AirQuality';
import Energy from './pages/Energy';
import Fires from './pages/Fires';
import Footprint from './pages/Footprint';
import Quiz from './pages/Quiz';
import Risk from './pages/Risk';
import { fetchEstadoFuentes, type EstadoFuente } from './api';
import { LugarProvider, useLugar } from './LugarContext';

const COLOR_SEMAFORO: Record<string, string> = {
  verde: 'bg-green-500',
  amarillo: 'bg-yellow-500',
  rojo: 'bg-red-500',
  gris: 'bg-gray-300',
};

const NAVEGACION = [
  { ruta: '/', etiqueta: 'Aire y Clima', icono: Wind },
  { ruta: '/energia', etiqueta: 'Energía', icono: Zap },
  { ruta: '/incendios', etiqueta: 'Incendios', icono: Flame },
  { ruta: '/riesgo', etiqueta: 'Riesgo de calor', icono: ThermometerSun },
  { ruta: '/huella', etiqueta: 'Mi huella', icono: Leaf },
  { ruta: '/quiz', etiqueta: 'Quiz', icono: Brain },
];

function Header() {
  const { lugarId } = useLugar();
  // Las fuentes vienen del backend (sources/registry.py). No se listan aquí:
  // agregar una fuente no debe obligar a tocar el dashboard.
  const [estados, setEstados] = useState<Record<string, EstadoFuente>>({});

  useEffect(() => {
    if (!lugarId) return;

    const cargar = () =>
      fetchEstadoFuentes(lugarId).then(setEstados).catch(console.error);

    cargar();
    const id = setInterval(cargar, 60_000); // refresca el semáforo cada minuto
    return () => clearInterval(id);
  }, [lugarId]);

  return (
    <header className="bg-white border-b border-gray-200 flex flex-wrap gap-y-2 items-center justify-between px-6 py-3 sticky top-0 z-[1000]">
      <h1 className="text-xl font-semibold text-gray-800">ClimaBot</h1>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        {Object.entries(estados).map(([id, e]) => (
          <div key={id} className="flex items-center space-x-2" title={e.detalle}>
            <span className="text-sm text-gray-500">{e.etiqueta}</span>
            <div className={`w-3 h-3 rounded-full ${COLOR_SEMAFORO[e.estado] ?? 'bg-gray-300'}`} />
            <span className="text-xs text-gray-400">{e.detalle}</span>
          </div>
        ))}
      </div>
    </header>
  );
}

function Sidebar() {
  const location = useLocation();

  return (
    <div className="w-56 bg-white border-r border-gray-200 flex-shrink-0">
      <nav className="py-6 px-3 space-y-1 sticky top-20">
        {NAVEGACION.map(({ ruta, etiqueta, icono: Icono }) => (
          <Link
            key={ruta}
            to={ruta}
            className={`flex items-center space-x-3 px-3 py-2.5 rounded-lg transition-colors ${
              location.pathname === ruta
                ? 'bg-green-50 text-green-700'
                : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            <Icono className="w-5 h-5 flex-shrink-0" />
            <span className="font-medium text-sm">{etiqueta}</span>
          </Link>
        ))}
      </nav>
    </div>
  );
}

function Layout({ children }: { children: ReactNode }) {
  const { error } = useLugar();

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <Header />
      {error && (
        <div className="bg-red-50 border-b border-red-200 text-red-700 px-6 py-3 text-sm">
          No se pudo contactar el backend ({error}). Arráncalo con{' '}
          <code className="bg-red-100 px-1.5 py-0.5 rounded">python api.py</code>
        </div>
      )}
      <div className="flex flex-1">
        <Sidebar />
        <main className="flex-1 p-8 min-w-0">{children}</main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <LugarProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<AirQuality />} />
            <Route path="/energia" element={<Energy />} />
            <Route path="/incendios" element={<Fires />} />
            <Route path="/riesgo" element={<Risk />} />
            <Route path="/huella" element={<Footprint />} />
            <Route path="/quiz" element={<Quiz />} />
          </Routes>
        </Layout>
      </LugarProvider>
    </BrowserRouter>
  );
}
