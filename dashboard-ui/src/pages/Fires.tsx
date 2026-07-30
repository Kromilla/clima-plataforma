import { useState } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup, Rectangle } from 'react-leaflet';
import { Flame, KeyRound, AlertTriangle } from 'lucide-react';
import 'leaflet/dist/leaflet.css';
import { fetchIncendios, type RespuestaIncendios, type Foco } from '../api';
import { useLugar } from '../LugarContext';
import { useFetch } from '../useFetch';
import AvisoBackend from '../components/AvisoBackend';
import PageHeader from '../components/PageHeader';

/** Color por intensidad radiativa (FRP, en megavatios). */
function colorFoco(frp: number): string {
  if (frp >= 50) return '#dc2626';
  if (frp >= 10) return '#ea580c';
  return '#f59e0b';
}

function radioFoco(frp: number): number {
  return Math.min(6 + Math.sqrt(Math.max(frp, 0)), 20);
}

function PanelSinDatos({ data }: { data: RespuestaIncendios }) {
  const sinClave = data.motivo === 'sin_clave';
  return (
    <div className="card card-pad text-center">
      <div className="mb-4 flex justify-center">
        <div className={`grid h-12 w-12 place-items-center rounded-full ${sinClave ? 'bg-sky-500/15' : 'bg-amber-500/15'}`}>
          {sinClave
            ? <KeyRound className="h-6 w-6 text-sky-600 dark:text-sky-400" />
            : <AlertTriangle className="h-6 w-6 text-amber-600 dark:text-amber-400" />}
        </div>
      </div>
      <h3 className="text-lg font-semibold text-heading">
        {sinClave ? 'Falta configurar la clave de NASA FIRMS' : 'FIRMS no está respondiendo'}
      </h3>
      {sinClave ? (
        <div className="mx-auto mt-3 max-w-lg space-y-3 text-sm text-body">
          <p>La capa de incendios necesita una MAP_KEY gratuita de la NASA. El resto del dashboard funciona sin ella.</p>
          <ol className="inline-block space-y-1.5 text-left">
            <li>1. Pídela en{' '}
              <a href="https://firms.modaps.eosdis.nasa.gov/api/map_key/" target="_blank" rel="noreferrer"
                className="text-brand hover:underline">firms.modaps.eosdis.nasa.gov</a>
            </li>
            <li>2. Añádela al <code className="rounded bg-surface-soft px-1">.env</code>:{' '}
              <code className="rounded bg-surface-soft px-1">FIRMS_MAP_KEY=tu_clave</code></li>
            <li>3. Reinicia la API</li>
          </ol>
        </div>
      ) : (
        <p className="mt-3 text-sm text-body">{data.mensaje}</p>
      )}
    </div>
  );
}

export default function Fires() {
  const { lugarId, lugares } = useLugar();
  const [dias, setDias] = useState(2);

  const { datos: data, error, cargando, recargar, intentos } = useFetch<RespuestaIncendios>(
    () => fetchIncendios(lugarId!, dias),
    [lugarId, dias],
    { activo: !!lugarId, intervaloMs: 10 * 60_000 },
  );

  const nombreLugar = lugares.find((l) => l.id === lugarId)?.nombre ?? '';
  const focos: Foco[] = data?.focos ?? [];
  const significativos = focos.filter((f) => f.confianza !== 'baja');
  const cercanos = significativos.filter((f) => f.distancia_km <= 20);

  return (
    <div>
      <PageHeader
        titulo="Focos de calor"
        subtitulo={nombreLugar}
        acciones={
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted">Últimos</span>
            <select value={dias} onChange={(e) => setDias(Number(e.target.value))}
              className="field !w-auto !py-1.5">
              <option value={1}>1 día</option>
              <option value={2}>2 días</option>
              <option value={5}>5 días</option>
            </select>
          </div>
        }
      />

      {error && (
        <div className="mb-6"><AvisoBackend error={error} intentos={intentos} onReintentar={recargar} /></div>
      )}

      {cercanos.length > 0 && (
        <div className="card card-pad mb-6 flex items-start gap-3 border-red-300/60 dark:border-red-500/30">
          <Flame className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-600 dark:text-red-400" />
          <div className="text-sm">
            <p className="font-semibold text-heading">
              {cercanos.length} foco{cercanos.length > 1 ? 's' : ''} a menos de 20 km
            </p>
            <p className="mt-0.5 text-body">
              El más cercano a {cercanos[0].distancia_km.toFixed(1)} km. Puede afectar la calidad del aire.
            </p>
          </div>
        </div>
      )}

      {cargando && !data ? (
        <div className="card card-pad"><div className="skeleton h-96 w-full" /></div>
      ) : data && !data.disponible ? (
        <PanelSinDatos data={data} />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {[
              { etiqueta: 'Focos detectados', valor: focos.length, clase: 'text-heading' },
              { etiqueta: 'Confianza nominal o alta', valor: significativos.length, clase: 'text-orange-500' },
              { etiqueta: 'A menos de 20 km', valor: cercanos.length, clase: cercanos.length ? 'text-red-500' : 'text-heading' },
            ].map((s) => (
              <div key={s.etiqueta} className="card card-pad">
                <p className="text-sm text-muted">{s.etiqueta}</p>
                <p className={`mt-1 font-display text-3xl font-bold tabular-nums ${s.clase}`}>{s.valor}</p>
              </div>
            ))}
          </div>

          <div className="card card-pad mt-4 sm:mt-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-base font-semibold text-heading">Mapa</h3>
              <div className="flex items-center gap-4 text-xs text-muted">
                {[
                  { c: '#f59e0b', t: '< 10 MW' },
                  { c: '#ea580c', t: '10-50 MW' },
                  { c: '#dc2626', t: '> 50 MW' },
                ].map((l) => (
                  <span key={l.t} className="flex items-center gap-1.5">
                    <span className="h-3 w-3 rounded-full" style={{ backgroundColor: l.c }} />{l.t}
                  </span>
                ))}
              </div>
            </div>

            <div className="h-[26rem] w-full overflow-hidden rounded-xl border border-line">
              {data && (
                <MapContainer center={[data.centro.lat, data.centro.lon]} zoom={10}
                  className="h-full w-full" scrollWheelZoom>
                  <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                  {data.bbox && (
                    <Rectangle
                      bounds={[[data.bbox[1], data.bbox[0]], [data.bbox[3], data.bbox[2]]]}
                      pathOptions={{ color: '#64748b', weight: 1, fillOpacity: 0.03, dashArray: '4' }} />
                  )}
                  {focos.map((f, i) => (
                    <CircleMarker key={`${f.lat}-${f.lon}-${i}`} center={[f.lat, f.lon]} radius={radioFoco(f.frp)}
                      pathOptions={{
                        color: colorFoco(f.frp), fillColor: colorFoco(f.frp),
                        fillOpacity: f.confianza === 'baja' ? 0.25 : 0.6, weight: 1,
                      }}>
                      <Popup>
                        <div className="space-y-0.5 text-sm">
                          <p className="font-semibold">Foco de calor</p>
                          <p>Intensidad: {f.frp.toFixed(1)} MW</p>
                          <p>Confianza: {f.confianza}</p>
                          <p>Distancia: {f.distancia_km.toFixed(1)} km</p>
                          <p>{new Date(f.ts).toLocaleString()}</p>
                        </div>
                      </Popup>
                    </CircleMarker>
                  ))}
                </MapContainer>
              )}
            </div>

            {focos.length === 0 && (
              <p className="mt-4 text-center text-sm text-muted">
                No se detectaron focos en la zona en el periodo seleccionado.
              </p>
            )}

            <p className="mt-4 text-xs leading-relaxed text-muted">
              Detecciones satelitales de NASA FIRMS (VIIRS S-NPP, 375 m). Un foco es una anomalía
              térmica: puede ser un incendio, una quema agrícola controlada o una fuente industrial.
              No confirma un incendio en tierra.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
