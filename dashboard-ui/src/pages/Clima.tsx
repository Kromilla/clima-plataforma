import {
  Sun, Moon, Cloud, CloudSun, CloudFog, CloudDrizzle, CloudRain,
  CloudSnow, CloudRainWind, CloudLightning, Wind, Droplets, Gauge,
  type LucideIcon,
} from 'lucide-react';
import { fetchClimaActual, type ClimaActual } from '../api';
import { useLugar } from '../LugarContext';
import { useFetch } from '../useFetch';
import AvisoBackend from '../components/AvisoBackend';
import PageHeader from '../components/PageHeader';

/** Código WMO (weather_code de Open-Meteo) → ícono + texto. */
function condicion(codigo: number | undefined, esDia: boolean): { Icono: LucideIcon; texto: string } {
  const c = codigo ?? 0;
  if (c === 0) return { Icono: esDia ? Sun : Moon, texto: 'Despejado' };
  if (c <= 2) return { Icono: esDia ? CloudSun : Cloud, texto: 'Parcialmente nublado' };
  if (c === 3) return { Icono: Cloud, texto: 'Nublado' };
  if (c <= 48) return { Icono: CloudFog, texto: 'Niebla' };
  if (c <= 57) return { Icono: CloudDrizzle, texto: 'Llovizna' };
  if (c <= 67) return { Icono: CloudRain, texto: 'Lluvia' };
  if (c <= 77) return { Icono: CloudSnow, texto: 'Nieve' };
  if (c <= 82) return { Icono: CloudRainWind, texto: 'Chubascos' };
  if (c <= 86) return { Icono: CloudSnow, texto: 'Chubascos de nieve' };
  return { Icono: CloudLightning, texto: 'Tormenta' };
}

/** Grados → rumbo de la brújula. */
function rumbo(deg: number | undefined): string {
  if (deg == null) return '';
  return ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO'][Math.round(deg / 45) % 8];
}

export default function Clima() {
  const { lugarId, lugares } = useLugar();

  const { datos: c, error, cargando, recargar, intentos } = useFetch<ClimaActual>(
    () => fetchClimaActual(lugarId!),
    [lugarId],
    { activo: !!lugarId, intervaloMs: 5 * 60_000 },
  );

  const nombreLugar = lugares.find((l) => l.id === lugarId)?.nombre ?? '';
  const { Icono, texto } = condicion(c?.codigo, c?.es_dia ?? true);

  const tiles = c && c.disponible ? [
    { Icono: Wind, etiqueta: 'Viento', valor: `${(c.viento_kmh ?? 0).toFixed(0)} km/h ${rumbo(c.viento_dir)}`, sub: `rachas ${(c.rachas_kmh ?? 0).toFixed(0)} km/h` },
    { Icono: Droplets, etiqueta: 'Humedad', valor: `${c.humedad ?? '—'}%`, sub: '' },
    { Icono: CloudRain, etiqueta: 'Lluvia', valor: `${(c.precipitacion ?? 0).toFixed(1)} mm`, sub: 'última hora' },
    { Icono: Cloud, etiqueta: 'Nubosidad', valor: `${c.nubosidad ?? '—'}%`, sub: '' },
    { Icono: Gauge, etiqueta: 'Presión', valor: `${(c.presion ?? 0).toFixed(0)} hPa`, sub: '' },
  ] : [];

  return (
    <div>
      <PageHeader titulo="Clima en tiempo real" subtitulo={nombreLugar} />

      {error && (
        <div className="mb-6"><AvisoBackend error={error} intentos={intentos} onReintentar={recargar} /></div>
      )}

      {cargando && !c ? (
        <div className="card card-pad"><div className="skeleton h-40 w-full" /></div>
      ) : c && !c.disponible ? (
        <div className="card card-pad text-center">
          <CloudFog className="mx-auto mb-3 h-8 w-8 text-muted" />
          <h2 className="font-semibold text-heading">Sin datos de clima ahora mismo</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-body">{c.mensaje}</p>
        </div>
      ) : c ? (
        <>
          <div className="card card-pad flex items-center justify-between gap-4">
            <div>
              <div className="flex items-baseline">
                <span className="font-display text-6xl font-bold tabular-nums text-heading">
                  {Math.round(c.temperatura ?? 0)}
                </span>
                <span className="ml-1 text-2xl text-muted">°C</span>
              </div>
              <p className="mt-1 text-lg font-medium text-body">{texto}</p>
              <p className="text-sm text-muted">Sensación {Math.round(c.sensacion ?? 0)} °C</p>
            </div>
            <Icono className="h-24 w-24 flex-shrink-0 text-brand" strokeWidth={1.5} />
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {tiles.map((t) => (
              <div key={t.etiqueta} className="card card-pad">
                <div className="flex items-center gap-2 text-muted">
                  <t.Icono className="h-4 w-4" />
                  <span className="text-sm">{t.etiqueta}</span>
                </div>
                <p className="mt-1 font-display text-2xl font-bold tabular-nums text-heading">{t.valor}</p>
                {t.sub && <p className="text-xs text-muted">{t.sub}</p>}
              </div>
            ))}
          </div>

          <p className="mt-4 text-xs leading-relaxed text-muted">
            Condiciones actuales de Open-Meteo (modelo global). Se actualizan solas cada 5 minutos.
            {c.ts && ` · Dato de las ${new Date(`${c.ts}Z`).toLocaleTimeString()}.`}
          </p>
        </>
      ) : null}
    </div>
  );
}
