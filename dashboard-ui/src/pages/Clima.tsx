import { useState } from 'react';
import {
  Sun, Moon, Cloud, CloudSun, CloudFog, CloudDrizzle, CloudRain,
  CloudSnow, CloudRainWind, CloudLightning, Wind, Droplets, Gauge,
  MapPin, LocateFixed, Loader2, Radio, Waves,
  type LucideIcon,
} from 'lucide-react';
import { fetchClimaActual, fetchClimaPorCoords, fetchNombreUbicacion, type ClimaActual } from '../api';
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

  // Modo GPS: cuando el usuario da permiso, se consulta su punto exacto en vez
  // de la ciudad del selector. `null` = seguimos la ciudad elegida.
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [nombreGps, setNombreGps] = useState<string>('');
  const [gpsCargando, setGpsCargando] = useState(false);
  const [gpsError, setGpsError] = useState<string | null>(null);

  const { datos: c, error, cargando, recargar, intentos } = useFetch<ClimaActual>(
    () => (coords ? fetchClimaPorCoords(coords.lat, coords.lon) : fetchClimaActual(lugarId!)),
    [coords?.lat, coords?.lon, lugarId],
    { activo: coords != null || !!lugarId, intervaloMs: 5 * 60_000 },
  );

  function ubicarme() {
    if (!('geolocation' in navigator)) {
      setGpsError('Tu navegador no permite geolocalización.');
      return;
    }
    setGpsCargando(true);
    setGpsError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        setCoords({ lat: latitude, lon: longitude });
        setNombreGps('');
        fetchNombreUbicacion(latitude, longitude).then(setNombreGps);
        setGpsCargando(false);
      },
      (err) => {
        setGpsError(
          err.code === err.PERMISSION_DENIED
            ? 'Permiso de ubicación denegado. Elige una ciudad arriba.'
            : 'No pudimos obtener tu ubicación.',
        );
        setGpsCargando(false);
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 },
    );
  }

  const nombreCiudad = lugares.find((l) => l.id === lugarId)?.nombre ?? '';
  const nombreLugar = coords ? (nombreGps || 'Tu ubicación') : nombreCiudad;
  const { Icono, texto } = condicion(c?.codigo, c?.es_dia ?? true);

  // Solo se muestran los tiles con dato: el respaldo del collector trae temp+
  // humedad, no viento/lluvia/presión, y un "0 km/h" inventado engañaría.
  const tiles = c && c.disponible ? [
    c.viento_kmh != null && { Icono: Wind, etiqueta: 'Viento', valor: `${c.viento_kmh.toFixed(0)} km/h ${rumbo(c.viento_dir)}`, sub: c.rachas_kmh != null ? `rachas ${c.rachas_kmh.toFixed(0)} km/h` : '' },
    c.humedad != null && { Icono: Droplets, etiqueta: 'Humedad', valor: `${c.humedad}%`, sub: '' },
    c.precipitacion != null && { Icono: CloudRain, etiqueta: 'Lluvia', valor: `${c.precipitacion.toFixed(1)} mm`, sub: 'última hora' },
    c.nubosidad != null && { Icono: Cloud, etiqueta: 'Nubosidad', valor: `${c.nubosidad}%`, sub: '' },
    c.presion != null && { Icono: Gauge, etiqueta: 'Presión', valor: `${c.presion.toFixed(0)} hPa`, sub: '' },
  ].filter(Boolean) as { Icono: LucideIcon; etiqueta: string; valor: string; sub: string }[] : [];

  return (
    <div>
      <PageHeader titulo="Clima en tiempo real" subtitulo={nombreLugar} />

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <button
          onClick={ubicarme}
          disabled={gpsCargando}
          className="flex min-h-[44px] items-center gap-2 rounded-xl border border-line px-4 text-sm
                     font-medium text-body transition-colors hover:bg-surface-soft disabled:opacity-60"
        >
          {gpsCargando
            ? <Loader2 className="h-4 w-4 animate-spin" />
            : <LocateFixed className="h-4 w-4 text-brand" />}
          {coords ? 'Actualizar mi ubicación' : 'Usar mi ubicación'}
        </button>
        {coords && (
          <button
            onClick={() => { setCoords(null); setNombreGps(''); setGpsError(null); }}
            className="flex min-h-[44px] items-center gap-2 rounded-xl px-3 text-sm text-muted
                       transition-colors hover:text-heading"
          >
            <MapPin className="h-4 w-4" /> Volver a {nombreCiudad.split(',')[0] || 'ciudad'}
          </button>
        )}

        {/* Distintivo de procedencia: que se vea de un golpe si el número lo midió
            un sensor o lo calculó un modelo. El proyecto no disfraza estimaciones. */}
        {c?.disponible && !c.cacheado && (
          <span
            className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
              c.es_estacion
                ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400'
                : 'bg-sky-500/10 text-sky-700 dark:text-sky-400'
            }`}
            title={c.origen}
          >
            {c.es_estacion
              ? <><Radio className="h-3.5 w-3.5" /> Estación real</>
              : <><Waves className="h-3.5 w-3.5" /> Modelo</>}
          </span>
        )}
      </div>

      {gpsError && (
        <p className="mb-4 text-sm text-amber-600 dark:text-amber-400">{gpsError}</p>
      )}

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
              {!c.cacheado && <p className="mt-1 text-lg font-medium text-body">{texto}</p>}
              {c.sensacion != null && (
                <p className="text-sm text-muted">Sensación {Math.round(c.sensacion)} °C</p>
              )}
            </div>
            {(() => {
              const HeroIcono = c.cacheado ? Cloud : Icono;
              return <HeroIcono className="h-24 w-24 flex-shrink-0 text-brand" strokeWidth={1.5} />;
            })()}
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
            {c.cacheado ? (
              <>
                El clima en vivo está saturado (Open-Meteo limita las consultas). Mostramos el
                último dato del monitor{c.antiguedad_min != null && `, hace ${c.antiguedad_min} min`}.
                Reintenta en un minuto para ver las condiciones completas.
              </>
            ) : (
              <>
                {c.es_estacion ? (
                  <>
                    Medición real de la {c.origen}
                    {c.estacion_km != null && `, a ${c.estacion_km} km de la ciudad`}.
                    Termómetro, anemómetro y barómetro físicos; el reporte se publica cada hora.
                  </>
                ) : (
                  <>Condiciones actuales de {c.origen ?? 'Open-Meteo (modelo global)'}: es una
                    estimación calculada para el punto exacto, no la lectura de una estación.</>
                )}
                {c.ts && ` · Dato de las ${new Date(`${c.ts}Z`).toLocaleTimeString()}.`}
              </>
            )}
          </p>
        </>
      ) : null}
    </div>
  );
}
