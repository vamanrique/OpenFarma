import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { prediccionesApi, type PrediccionMapa } from '../api/client'

const COLORES_RIESGO: Record<string, string> = {
  bajo: '#16a34a',
  medio: '#d97706',
  alto: '#ea580c',
  critico: '#dc2626',
}

export default function MapaRiesgo() {
  const [predicciones, setPredicciones] = useState<PrediccionMapa[]>([])
  const [filtro, setFiltro] = useState('')
  const [cargando, setCargando] = useState(true)

  const cargar = async (nivel?: string) => {
    setCargando(true)
    try {
      const res = await prediccionesApi.mapa(nivel || undefined)
      setPredicciones(res.data)
    } catch {
      // backend no disponible aún
    } finally {
      setCargando(false)
    }
  }

  useEffect(() => { cargar() }, [])

  const puntos = predicciones.filter(p => p.latitud && p.longitud)

  return (
    <div>
      <div className="flex gap-2 mb-4 flex-wrap">
        {['', 'bajo', 'medio', 'alto', 'critico'].map(nivel => (
          <button
            key={nivel}
            onClick={() => { setFiltro(nivel); cargar(nivel) }}
            className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
              filtro === nivel
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
            }`}
          >
            {nivel === '' ? 'Todos' : nivel.charAt(0).toUpperCase() + nivel.slice(1)}
          </button>
        ))}
      </div>

      {cargando && <p className="text-gray-500 text-sm mb-2">Cargando predicciones...</p>}
      {!cargando && puntos.length === 0 && (
        <p className="text-gray-400 text-sm mb-2">
          No hay predicciones disponibles. Genera predicciones desde la API (/api/v1/predicciones/calcular/&#123;id&#125;).
        </p>
      )}

      <div className="rounded-xl overflow-hidden border border-gray-200 shadow-sm" style={{ height: 480 }}>
        <MapContainer center={[4.5709, -74.2973]} zoom={6} style={{ height: '100%', width: '100%' }}>
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://openstreetmap.org">OpenStreetMap</a>'
          />
          {puntos.map((p, i) => (
            <CircleMarker
              key={i}
              center={[p.latitud!, p.longitud!]}
              radius={12 + p.probabilidad * 20}
              pathOptions={{
                fillColor: COLORES_RIESGO[p.nivel_riesgo] || '#6b7280',
                fillOpacity: 0.7,
                color: COLORES_RIESGO[p.nivel_riesgo] || '#6b7280',
                weight: 1,
              }}
            >
              <Popup>
                <strong>{p.region_nombre}</strong><br />
                Medicamento: {p.medicamento_nombre}<br />
                Riesgo: <strong>{p.nivel_riesgo}</strong><br />
                Probabilidad: {(p.probabilidad * 100).toFixed(1)}%
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>

      <div className="flex gap-4 mt-3 text-xs text-gray-600">
        {Object.entries(COLORES_RIESGO).map(([nivel, color]) => (
          <div key={nivel} className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
            {nivel.charAt(0).toUpperCase() + nivel.slice(1)}
          </div>
        ))}
      </div>
    </div>
  )
}
