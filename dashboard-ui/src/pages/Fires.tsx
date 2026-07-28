import { useEffect, useState } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup, Rectangle } from 'react-leaflet';
import { Flame, KeyRound, AlertTriangle } from 'lucide-react';
import 'leaflet/dist/leaflet.css';
import { fetchIncendios, type RespuestaIncendios, type Foco } from '../api';
import { useLugar } from '../LugarContext';

/** Color por intensidad radiativa (FRP, en megavatios). */
function colorFoco(frp: number): string {
  if (frp >= 50) return '#dc2626';
  if (frp >= 10) return '#ea580c';
  return '#f59e0b';
}

/** Radio del marcador, acotado para que un foco enorme no tape el mapa. */
function radioFoco(frp: number): number {
  return Math.min(6 + Math.sqrt(Math.max(frp, 0)), 20);
}

function PanelSinDatos({ data }: { data: RespuestaIncendios }) {
  const sinClave = data.motivo === 'sin_clave';

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-8 text-center">
      <div className="flex justify-center mb-4">
        <div className={`p-3 rounded-full ${sinClave ? 'bg-blue-50' : 'bg-amber-50'}`}>
          {sinClave ? (
            <KeyRound className="w-7 h-7 text-blue-600" />
          ) : (
            <AlertTriangle className="w-7 h-7 text-amber-600" />
          )}
        </div>
      </div>

      <h3 className="text-lg font-semibold text-gray-800">
        {sinClave ? 'Falta configurar la clave de NASA FIRMS' : 'FIRMS no está respondiendo'}
      </h3>

      {sinClave ? (
        <div className="mt-3 text-sm text-gray-600 max-w-lg mx-auto space-y-3">
          <p>
            La capa de incendios necesita una MAP_KEY gratuita de la NASA. El resto
            del dashboard funciona normalmente sin ella.
          </p>
          <ol className="text-left inline-block space-y-1.5">
            <li>
              1. Pídela en{' '}
              <a
                href="https://firms.modaps.eosdis.nasa.gov/api/map_key/"
                target="_blank"
                rel="noreferrer"
                className="text-blue-600 hover:underline"
              >
                firms.modaps.eosdis.nasa.gov
              </a>{' '}
              (llega por correo)
            </li>
            <li>
              2. Añádela al <code className="bg-gray-100 px-1 rounded">.env</code>:{' '}
              <code className="bg-gray-100 px-1 rounded">FIRMS_MAP_KEY=tu_clave</code>
            </li>
            <li>3. Reinicia la API</li>
          </ol>
        </div>
      ) : (
        <p className="mt-3 text-sm text-gray-600">{data.mensaje}</p>
      )}
    </div>
  );
}

export default function Fires() {
  const { lugarId, lugares } = useLugar();
  const [data, setData] = useState<RespuestaIncendios | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const [dias, setDias] = useState(2);

  useEffect(() => {
    if (!lugarId) return;
    setCargando(true);
    fetchIncendios(lugarId, dias)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setCargando(false));
  }, [lugarId, dias]);

  const nombreLugar = lugares.find((l) => l.id === lugarId)?.nombre ?? '';
  const focos: Foco[] = data?.focos ?? [];
  const significativos = focos.filter((f) => f.confianza !== 'baja');
  const cercanos = significativos.filter((f) => f.distancia_km <= 20);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between items-end gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-800">Focos de calor</h2>
          <p className="text-gray-500 mt-1">{nombreLugar}</p>
        </div>
        <div className="flex items-center space-x-2">
          <span className="text-sm text-gray-500">Últimos</span>
          <select
            value={dias}
            onChange={(e) => setDias(Number(e.target.value))}
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white"
          >
            <option value={1}>1 día</option>
            <option value={2}>2 días</option>
            <option value={5}>5 días</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 text-sm">
          No se pudo cargar: {error}
        </div>
      )}

      {cercanos.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start space-x-3">
          <Flame className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium text-red-800">
              {cercanos.length} foco{cercanos.length > 1 ? 's' : ''} a menos de 20 km
            </p>
            <p className="text-red-600 mt-0.5">
              El más cercano a {cercanos[0].distancia_km.toFixed(1)} km. Puede afectar
              la calidad del aire.
            </p>
          </div>
        </div>
      )}

      {cargando && !data ? (
        <div className="bg-white rounded-xl border border-gray-100 p-12 text-center text-gray-400">
          Cargando focos…
        </div>
      ) : data && !data.disponible ? (
        <PanelSinDatos data={data} />
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { etiqueta: 'Focos detectados', valor: focos.length, color: 'text-gray-900' },
              { etiqueta: 'Confianza nominal o alta', valor: significativos.length, color: 'text-orange-600' },
              { etiqueta: 'A menos de 20 km', valor: cercanos.length, color: cercanos.length ? 'text-red-600' : 'text-gray-900' },
            ].map((s) => (
              <div key={s.etiqueta} className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
                <p className="text-sm text-gray-500">{s.etiqueta}</p>
                <p className={`text-3xl font-bold mt-1 ${s.color}`}>{s.valor}</p>
              </div>
            ))}
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <div className="flex flex-wrap justify-between items-center mb-4 gap-3">
              <h3 className="text-lg font-semibold text-gray-800">Mapa</h3>
              <div className="flex items-center space-x-4 text-xs text-gray-500">
                {[
                  { c: '#f59e0b', t: '< 10 MW' },
                  { c: '#ea580c', t: '10-50 MW' },
                  { c: '#dc2626', t: '> 50 MW' },
                ].map((l) => (
                  <span key={l.t} className="flex items-center space-x-1.5">
                    <span className="w-3 h-3 rounded-full" style={{ backgroundColor: l.c }} />
                    <span>{l.t}</span>
                  </span>
                ))}
              </div>
            </div>

            <div className="h-[28rem] w-full rounded-lg overflow-hidden border border-gray-200">
              {data && (
                <MapContainer
                  center={[data.centro.lat, data.centro.lon]}
                  zoom={10}
                  className="h-full w-full"
                  scrollWheelZoom
                >
                  <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  />

                  {data.bbox && (
                    <Rectangle
                      bounds={[
                        [data.bbox[1], data.bbox[0]],
                        [data.bbox[3], data.bbox[2]],
                      ]}
                      pathOptions={{ color: '#6b7280', weight: 1, fillOpacity: 0.03, dashArray: '4' }}
                    />
                  )}

                  {focos.map((f, i) => (
                    <CircleMarker
                      key={`${f.lat}-${f.lon}-${i}`}
                      center={[f.lat, f.lon]}
                      radius={radioFoco(f.frp)}
                      pathOptions={{
                        color: colorFoco(f.frp),
                        fillColor: colorFoco(f.frp),
                        fillOpacity: f.confianza === 'baja' ? 0.25 : 0.6,
                        weight: 1,
                      }}
                    >
                      <Popup>
                        <div className="text-sm space-y-0.5">
                          <p className="font-semibold">Foco de calor</p>
                          <p>Intensidad: {f.frp.toFixed(1)} MW</p>
                          <p>Confianza: {f.confianza}</p>
                          <p>Distancia: {f.distancia_km.toFixed(1)} km</p>
                          <p>{new Date(f.ts).toLocaleString()}</p>
                          <p className="text-gray-500">
                            {f.satelite} · {f.dia_noche === 'D' ? 'día' : 'noche'}
                          </p>
                        </div>
                      </Popup>
                    </CircleMarker>
                  ))}
                </MapContainer>
              )}
            </div>

            {focos.length === 0 && (
              <p className="text-center text-gray-500 text-sm mt-4">
                No se detectaron focos en la zona en el periodo seleccionado.
              </p>
            )}

            <p className="text-xs text-gray-400 mt-4 leading-relaxed">
              Detecciones satelitales de NASA FIRMS (VIIRS S-NPP, 375 m). Un foco es
              una anomalía térmica: puede ser un incendio, una quema agrícola
              controlada o una fuente industrial. No confirma un incendio en tierra.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
