import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { prediccionesApi, type PrediccionMapa } from '../api/client'

const RIESGO = {
  bajo:    { color: '#16a34a', bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', label: 'Bajo' },
  medio:   { color: '#d97706', bg: 'bg-amber-50',   text: 'text-amber-700',   border: 'border-amber-200',   label: 'Medio' },
  alto:    { color: '#ea580c', bg: 'bg-orange-50',  text: 'text-orange-700',  border: 'border-orange-200',  label: 'Alto' },
  critico: { color: '#dc2626', bg: 'bg-red-50',     text: 'text-red-700',     border: 'border-red-200',     label: 'Crítico' },
}

function KpiCard({
  label, value, pct, colorClass, borderClass, textClass, active, onClick,
}: {
  label: string; value: number; pct: string
  colorClass: string; borderClass: string; textClass: string
  active: boolean; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 min-w-0 text-left p-4 rounded-xl border transition-all ${
        active
          ? `${colorClass} ${borderClass} shadow-sm ring-2 ring-offset-1 ring-current ${textClass}`
          : 'bg-white border-slate-200 hover:border-slate-300 text-slate-700'
      }`}
    >
      <p className="text-xs font-medium uppercase tracking-wide opacity-70 truncate">{label}</p>
      <p className="text-2xl font-bold mt-0.5 tabular-nums">{value.toLocaleString('es-CO')}</p>
      <p className="text-xs opacity-60 mt-0.5">{pct}</p>
    </button>
  )
}

export default function MapaRiesgo() {
  const [predicciones, setPredicciones] = useState<PrediccionMapa[]>([])
  const [filtro, setFiltro] = useState('')
  const [cargando, setCargando] = useState(true)

  useEffect(() => {
    prediccionesApi.mapa()
      .then(r => setPredicciones(r.data))
      .catch(() => {})
      .finally(() => setCargando(false))
  }, [])

  const total = predicciones.length
  const counts = {
    bajo:    predicciones.filter(p => p.nivel_riesgo === 'bajo').length,
    medio:   predicciones.filter(p => p.nivel_riesgo === 'medio').length,
    alto:    predicciones.filter(p => p.nivel_riesgo === 'alto').length,
    critico: predicciones.filter(p => p.nivel_riesgo === 'critico').length,
  }

  const pct = (n: number) => total > 0 ? `${((n / total) * 100).toFixed(1)}% del total` : '—'

  const mapData = filtro
    ? predicciones.filter(p => p.nivel_riesgo === filtro)
    : predicciones
  const puntos = mapData.filter(p => p.latitud && p.longitud)

  return (
    <div className="space-y-4">

      {/* KPI bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {cargando ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-white border border-slate-200 rounded-xl p-4 animate-pulse">
              <div className="h-3 bg-slate-100 rounded w-2/3 mb-2" />
              <div className="h-7 bg-slate-100 rounded w-1/2" />
            </div>
          ))
        ) : (
          <>
            <KpiCard label="Bajo riesgo"  value={counts.bajo}    pct={pct(counts.bajo)}
              colorClass="bg-emerald-50" borderClass="border-emerald-300" textClass="text-emerald-700"
              active={filtro === 'bajo'}   onClick={() => setFiltro(f => f === 'bajo'   ? '' : 'bajo')}   />
            <KpiCard label="Riesgo medio" value={counts.medio}   pct={pct(counts.medio)}
              colorClass="bg-amber-50"   borderClass="border-amber-300"   textClass="text-amber-700"
              active={filtro === 'medio'}  onClick={() => setFiltro(f => f === 'medio'  ? '' : 'medio')}  />
            <KpiCard label="Riesgo alto"  value={counts.alto}    pct={pct(counts.alto)}
              colorClass="bg-orange-50"  borderClass="border-orange-300"  textClass="text-orange-700"
              active={filtro === 'alto'}   onClick={() => setFiltro(f => f === 'alto'   ? '' : 'alto')}   />
            <KpiCard label="Crítico"      value={counts.critico} pct={pct(counts.critico)}
              colorClass="bg-red-50"     borderClass="border-red-300"     textClass="text-red-700"
              active={filtro === 'critico'} onClick={() => setFiltro(f => f === 'critico' ? '' : 'critico')} />
          </>
        )}
      </div>

      {/* Map card */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">

        {/* Map toolbar */}
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">Filtrar:</span>
            <button
              onClick={() => setFiltro('')}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                filtro === ''
                  ? 'bg-slate-800 text-white border-slate-800'
                  : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400'
              }`}
            >
              Todos
            </button>
            {Object.entries(RIESGO).map(([nivel, cfg]) => (
              <button
                key={nivel}
                onClick={() => setFiltro(f => f === nivel ? '' : nivel)}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                  filtro === nivel
                    ? `${cfg.bg} ${cfg.text} ${cfg.border}`
                    : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400'
                }`}
              >
                {cfg.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-slate-400">
            {puntos.length.toLocaleString('es-CO')} puntos visibles
          </p>
        </div>

        {!cargando && puntos.length === 0 && (
          <div className="py-8 text-center text-slate-400 text-sm">
            No hay predicciones para el filtro seleccionado.
          </div>
        )}

        <div style={{ height: 460 }}>
          <MapContainer center={[4.5709, -74.2973]} zoom={6} style={{ height: '100%', width: '100%' }}>
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution='&copy; <a href="https://openstreetmap.org">OpenStreetMap</a>'
            />
            {puntos.map((p, i) => (
              <CircleMarker
                key={i}
                center={[p.latitud!, p.longitud!]}
                radius={10 + p.probabilidad * 18}
                pathOptions={{
                  fillColor: RIESGO[p.nivel_riesgo as keyof typeof RIESGO]?.color ?? '#6b7280',
                  fillOpacity: 0.65,
                  color: RIESGO[p.nivel_riesgo as keyof typeof RIESGO]?.color ?? '#6b7280',
                  weight: 1.5,
                }}
              >
                <Popup>
                  <div className="text-sm space-y-0.5">
                    <p className="font-semibold">{p.region_nombre}</p>
                    <p className="text-slate-600">{p.medicamento_nombre}</p>
                    <p>Riesgo: <strong>{p.nivel_riesgo}</strong></p>
                    <p>Probabilidad: {(p.probabilidad * 100).toFixed(1)}%</p>
                  </div>
                </Popup>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>

        {/* Legend */}
        <div className="px-4 py-2.5 border-t border-slate-100 bg-slate-50 flex gap-4 flex-wrap">
          {Object.entries(RIESGO).map(([nivel, cfg]) => (
            <div key={nivel} className="flex items-center gap-1.5 text-xs text-slate-600">
              <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: cfg.color }} />
              {cfg.label}
            </div>
          ))}
          <span className="text-xs text-slate-400 ml-auto">
            Click en una tarjeta o botón para filtrar
          </span>
        </div>
      </div>
    </div>
  )
}
