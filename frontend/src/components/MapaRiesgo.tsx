import { useEffect, useState, useMemo } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { prediccionesApi, type PrediccionMapa } from '../api/client'

const RIESGO = {
  bajo:    { color: '#16a34a', bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', label: 'Bajo',    desc: 'Probabilidad < 25%' },
  medio:   { color: '#d97706', bg: 'bg-amber-50',   text: 'text-amber-700',   border: 'border-amber-200',   label: 'Medio',   desc: 'Probabilidad 25–50%' },
  alto:    { color: '#ea580c', bg: 'bg-orange-50',  text: 'text-orange-700',  border: 'border-orange-200',  label: 'Alto',    desc: 'Probabilidad 50–75%' },
  critico: { color: '#dc2626', bg: 'bg-red-50',     text: 'text-red-700',     border: 'border-red-200',     label: 'Crítico', desc: 'Probabilidad > 75%' },
}

type NivelRiesgo = keyof typeof RIESGO

interface RegionAgregada {
  region_id: number
  region_nombre: string
  latitud: number
  longitud: number
  nivel: NivelRiesgo
  probPromedio: number
  counts: Record<NivelRiesgo, number>
  total: number
  topMeds: { nombre: string; probabilidad: number; nivel: NivelRiesgo }[]
}

function nivelAgregado(counts: Record<NivelRiesgo, number>, total: number): NivelRiesgo {
  if (counts.critico / total > 0.05) return 'critico'
  if (counts.alto / total > 0.10)    return 'alto'
  if (counts.medio / total > 0.40)   return 'medio'
  return 'bajo'
}

function KpiCard({
  label, value, cfg, active, onClick,
}: {
  label: string; value: number
  cfg: typeof RIESGO[NivelRiesgo]; active: boolean; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      title={`Filtrar departamentos con riesgo ${label.toLowerCase()}`}
      className={`flex-1 min-w-0 text-left p-4 rounded-xl border transition-all ${
        active
          ? `${cfg.bg} ${cfg.border} ${cfg.text} shadow-sm ring-2 ring-offset-1`
          : 'bg-white border-slate-200 text-slate-700 hover:border-slate-300'
      }`}
    >
      <p className="text-xs font-semibold uppercase tracking-wide opacity-60 truncate">{label}</p>
      <p className="text-2xl font-bold mt-0.5 tabular-nums">{value}</p>
      <p className="text-xs opacity-50 mt-0.5">departamentos</p>
    </button>
  )
}

export default function MapaRiesgo() {
  const [predicciones, setPredicciones] = useState<PrediccionMapa[]>([])
  const [filtro, setFiltro]             = useState<NivelRiesgo | ''>('')
  const [cargando, setCargando]         = useState(true)

  useEffect(() => {
    prediccionesApi.mapa()
      .then(r => setPredicciones(r.data))
      .catch(() => {})
      .finally(() => setCargando(false))
  }, [])

  // Agrega las 6,600 predicciones en 33 puntos (1 por departamento)
  const regiones: RegionAgregada[] = useMemo(() => {
    const porRegion: Record<number, PrediccionMapa[]> = {}
    for (const p of predicciones) {
      if (!p.latitud || !p.longitud) continue
      if (!porRegion[p.region_id]) porRegion[p.region_id] = []
      porRegion[p.region_id].push(p)
    }

    return Object.entries(porRegion).map(([rid, preds]) => {
      const counts: Record<NivelRiesgo, number> = { bajo: 0, medio: 0, alto: 0, critico: 0 }
      for (const p of preds) counts[p.nivel_riesgo as NivelRiesgo]++

      const probPromedio = preds.reduce((s, p) => s + p.probabilidad, 0) / preds.length
      const nivel = nivelAgregado(counts, preds.length)

      const topMeds = [...preds]
        .sort((a, b) => b.probabilidad - a.probabilidad)
        .slice(0, 3)
        .map(p => ({
          nombre: p.medicamento_nombre ?? '—',
          probabilidad: p.probabilidad,
          nivel: p.nivel_riesgo as NivelRiesgo,
        }))

      return {
        region_id: Number(rid),
        region_nombre: preds[0].region_nombre ?? `Región ${rid}`,
        latitud: preds[0].latitud!,
        longitud: preds[0].longitud!,
        nivel,
        probPromedio,
        counts,
        total: preds.length,
        topMeds,
      }
    })
  }, [predicciones])

  const regionesFiltradas = filtro ? regiones.filter(r => r.nivel === filtro) : regiones

  const kpiCounts: Record<NivelRiesgo, number> = { bajo: 0, medio: 0, alto: 0, critico: 0 }
  for (const r of regiones) kpiCounts[r.nivel]++

  return (
    <div className="space-y-4">

      {/* Explicación */}
      <div className="bg-white border border-slate-200 rounded-xl px-5 py-4 shadow-sm">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
            <svg className="w-4 h-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 1-6.23-.693L4.2 15.3m15.6 0 1.004 4.014A1.5 1.5 0 0 1 19.35 21H4.65a1.5 1.5 0 0 1-1.454-1.686L4.2 15.3" />
          </svg>
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-800 mb-1">¿Qué muestra este mapa?</p>
            <p className="text-xs text-slate-500 leading-relaxed">
              Cada círculo representa un <strong>departamento de Colombia</strong>. El color indica el
              nivel de riesgo estimado de desabastecimiento de medicamentos en los próximos 30 días,
              calculado por un modelo de inteligencia artificial que analiza{' '}
              <strong>200 medicamentos del CUM-INVIMA</strong> y los reportes ciudadanos de cada región.
              A mayor tamaño del círculo, mayor probabilidad promedio de desabastecimiento.
            </p>
          </div>
        </div>
      </div>

      {/* KPIs por departamento */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {cargando ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-white border border-slate-200 rounded-xl p-4 animate-pulse">
              <div className="h-3 bg-slate-100 rounded w-2/3 mb-2" />
              <div className="h-7 bg-slate-100 rounded w-1/2" />
            </div>
          ))
        ) : (
          Object.entries(RIESGO).map(([nivel, cfg]) => (
            <KpiCard
              key={nivel}
              label={`Riesgo ${cfg.label}`}
              value={kpiCounts[nivel as NivelRiesgo]}
              cfg={cfg}
              active={filtro === nivel}
              onClick={() => setFiltro(f => f === nivel ? '' : nivel as NivelRiesgo)}
            />
          ))
        )}
      </div>

      {/* Mapa */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">

        {/* Toolbar */}
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
              Todos ({regiones.length})
            </button>
            {Object.entries(RIESGO).map(([nivel, cfg]) => (
              <button
                key={nivel}
                onClick={() => setFiltro(f => f === nivel ? '' : nivel as NivelRiesgo)}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                  filtro === nivel
                    ? `${cfg.bg} ${cfg.text} ${cfg.border}`
                    : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400'
                }`}
              >
                {cfg.label} ({kpiCounts[nivel as NivelRiesgo]})
              </button>
            ))}
          </div>
          <p className="text-xs text-slate-400">
            {regionesFiltradas.length} de 33 departamentos
          </p>
        </div>

        {!cargando && regiones.length === 0 && (
          <div className="py-10 text-center text-slate-400 text-sm">
            No hay predicciones cargadas aún.
          </div>
        )}

        <div style={{ height: 460 }}>
          <MapContainer center={[4.5709, -74.2973]} zoom={6} style={{ height: '100%', width: '100%' }}>
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution='&copy; <a href="https://openstreetmap.org">OpenStreetMap</a>'
            />
            {regionesFiltradas.map(r => {
              const cfg = RIESGO[r.nivel]
              return (
                <CircleMarker
                  key={r.region_id}
                  center={[r.latitud, r.longitud]}
                  radius={14 + r.probPromedio * 22}
                  pathOptions={{
                    fillColor: cfg.color,
                    fillOpacity: 0.7,
                    color: cfg.color,
                    weight: 2,
                  }}
                >
                  <Popup minWidth={220}>
                    <div className="text-sm space-y-2 py-1">
                      <div className="flex items-center justify-between gap-3">
                        <p className="font-bold text-slate-900">{r.region_nombre}</p>
                        <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${cfg.bg} ${cfg.text}`}>
                          {cfg.label}
                        </span>
                      </div>

                      <p className="text-xs text-slate-500">
                        Prob. promedio: <strong>{(r.probPromedio * 100).toFixed(1)}%</strong>
                        {' · '}{r.total} medicamentos analizados
                      </p>

                      {/* Distribución de riesgo */}
                      <div className="grid grid-cols-4 gap-1 text-center text-xs">
                        {Object.entries(RIESGO).map(([n, c]) => (
                          <div key={n} className={`rounded px-1 py-0.5 ${c.bg} ${c.text}`}>
                            <p className="font-bold">{r.counts[n as NivelRiesgo]}</p>
                            <p className="opacity-70">{c.label}</p>
                          </div>
                        ))}
                      </div>

                      {/* Top medicamentos */}
                      {r.topMeds.length > 0 && (
                        <div>
                          <p className="text-xs font-semibold text-slate-600 mb-1">Mayor riesgo:</p>
                          {r.topMeds.map((m, i) => (
                            <div key={i} className="flex items-center justify-between text-xs text-slate-600 py-0.5">
                              <span className="truncate flex-1 mr-2">{m.nombre}</span>
                              <span className={`shrink-0 px-1.5 rounded font-medium ${RIESGO[m.nivel].bg} ${RIESGO[m.nivel].text}`}>
                                {(m.probabilidad * 100).toFixed(0)}%
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </Popup>
                </CircleMarker>
              )
            })}
          </MapContainer>
        </div>

        {/* Leyenda */}
        <div className="px-4 py-3 border-t border-slate-100 bg-slate-50">
          <div className="flex flex-wrap gap-x-5 gap-y-1.5 items-center">
            {Object.entries(RIESGO).map(([nivel, cfg]) => (
              <div key={nivel} className="flex items-center gap-1.5 text-xs text-slate-600">
                <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: cfg.color }} />
                <span className="font-medium">{cfg.label}</span>
                <span className="text-slate-400">{cfg.desc}</span>
              </div>
            ))}
            <span className="text-xs text-slate-400 ml-auto hidden sm:block">
              Haz clic en un círculo para ver el detalle del departamento
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
