import { useState, useEffect, useRef } from 'react'
import { medicamentosApi, regionesApi, reportesApi, type MedicamentoLive, type Region, type ReporteReciente } from '../api/client'

const TIPOS_REPORTE = [
  { id: 'sin_stock', label: 'Sin stock', desc: 'El medicamento no está disponible en farmacias' },
  { id: 'precio_alto', label: 'Precio elevado', desc: 'El precio supera el valor regulado o habitual' },
  { id: 'sin_suministro', label: 'Sin suministro', desc: 'El laboratorio no está distribuyendo el producto' },
]

const TIPO_BADGE: Record<string, string> = {
  sin_stock: 'bg-red-100 text-red-700',
  precio_alto: 'bg-yellow-100 text-yellow-700',
  sin_suministro: 'bg-orange-100 text-orange-700',
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

export default function FormularioReporte() {
  const [query, setQuery] = useState('')
  const [sugerencias, setSugerencias] = useState<MedicamentoLive[]>([])
  const [buscando, setBuscando] = useState(false)
  const [medSeleccionado, setMedSeleccionado] = useState<MedicamentoLive | null>(null)
  const [showSugerencias, setShowSugerencias] = useState(false)

  const [regiones, setRegiones] = useState<Region[]>([])
  const [regionId, setRegionId] = useState<number | ''>('')
  const [tipoReporte, setTipoReporte] = useState('sin_stock')
  const [descripcion, setDescripcion] = useState('')

  const [enviando, setEnviando] = useState(false)
  const [exito, setExito] = useState(false)
  const [error, setError] = useState('')

  const [recientes, setRecientes] = useState<ReporteReciente[]>([])
  const [totalReportes, setTotalReportes] = useState(0)

  const dropdownRef = useRef<HTMLDivElement>(null)
  const queryDebounced = useDebounce(query, 300)

  useEffect(() => {
    regionesApi.listar().then(r => setRegiones(r.data)).catch(() => {})
    cargarRecientes()
  }, [])

  const cargarRecientes = async () => {
    try {
      const [recRes, totRes] = await Promise.all([
        reportesApi.recientes(5),
        reportesApi.total(),
      ])
      setRecientes(recRes.data)
      setTotalReportes(totRes.data.total)
    } catch {}
  }

  useEffect(() => {
    if (queryDebounced.length < 2 || medSeleccionado) {
      setSugerencias([])
      return
    }
    setBuscando(true)
    medicamentosApi.buscar(queryDebounced, true, 8)
      .then(r => { setSugerencias(r.data); setShowSugerencias(true) })
      .catch(() => setSugerencias([]))
      .finally(() => setBuscando(false))
  }, [queryDebounced, medSeleccionado])

  // Cierra dropdown al hacer click fuera
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowSugerencias(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const seleccionarMed = (med: MedicamentoLive) => {
    setMedSeleccionado(med)
    setQuery(med.nombre_comercial)
    setShowSugerencias(false)
    setSugerencias([])
  }

  const limpiarMed = () => {
    setMedSeleccionado(null)
    setQuery('')
    setSugerencias([])
  }

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!medSeleccionado || !regionId) return
    setEnviando(true)
    setError('')
    try {
      await reportesApi.reportar(
        medSeleccionado.cum_id,
        regionId as number,
        tipoReporte,
        descripcion.trim() || undefined,
      )
      setExito(true)
      await cargarRecientes()
    } catch {
      setError('Error al enviar el reporte. Verifica la conexión con el servidor.')
    } finally {
      setEnviando(false)
    }
  }

  const nuevoReporte = () => {
    setExito(false)
    setMedSeleccionado(null)
    setQuery('')
    setRegionId('')
    setTipoReporte('sin_stock')
    setDescripcion('')
    setError('')
  }

  if (exito) {
    return (
      <div className="max-w-lg">
        <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center">
          <div className="text-4xl mb-3">✅</div>
          <h3 className="text-lg font-semibold text-green-800 mb-2">
            Reporte enviado correctamente
          </h3>
          <p className="text-green-700 text-sm mb-1">
            <strong>{medSeleccionado?.nombre_comercial}</strong> — {TIPOS_REPORTE.find(t => t.id === tipoReporte)?.label}
          </p>
          <p className="text-green-600 text-xs mb-5">
            Tu reporte alimenta el modelo predictivo de desabastecimiento de Colombia.
          </p>
          <button
            onClick={nuevoReporte}
            className="bg-green-700 hover:bg-green-800 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            Reportar otro medicamento
          </button>
        </div>

        <ReportesRecientes recientes={recientes} total={totalReportes} />
      </div>
    )
  }

  const puedeEnviar = medSeleccionado && regionId && !enviando

  return (
    <div className="max-w-lg space-y-5">
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm text-blue-800">
        <p className="font-medium mb-1">¿Cómo funciona?</p>
        <p className="text-blue-700 text-xs">
          Reporta cuando un medicamento no está disponible en tu región. Cada reporte
          actualiza el modelo de predicción de desabastecimiento nacional.
        </p>
      </div>

      <form onSubmit={enviar} className="bg-white border border-gray-200 rounded-xl p-5 space-y-4">

        {/* Búsqueda de medicamento */}
        <div ref={dropdownRef} className="relative">
          <label className="block text-sm font-medium text-gray-700 mb-1.5">
            Medicamento <span className="text-red-500">*</span>
          </label>
          <div className="relative">
            <input
              type="text"
              value={query}
              onChange={e => { setQuery(e.target.value); setMedSeleccionado(null) }}
              onFocus={() => sugerencias.length > 0 && setShowSugerencias(true)}
              placeholder="Buscar por nombre comercial, principio activo o ATC..."
              className={`w-full border rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 pr-8 ${
                medSeleccionado
                  ? 'border-green-400 bg-green-50 focus:ring-green-300'
                  : 'border-gray-300 focus:ring-blue-500'
              }`}
            />
            {medSeleccionado && (
              <button
                type="button"
                onClick={limpiarMed}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-lg leading-none"
              >
                ×
              </button>
            )}
            {buscando && !medSeleccionado && (
              <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">...</span>
            )}
          </div>

          {showSugerencias && sugerencias.length > 0 && (
            <ul className="absolute z-20 top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-56 overflow-y-auto">
              {sugerencias.map(med => (
                <li
                  key={med.cum_id}
                  onMouseDown={() => seleccionarMed(med)}
                  className="px-3 py-2.5 hover:bg-blue-50 cursor-pointer border-b border-gray-50 last:border-0"
                >
                  <p className="text-sm font-medium text-gray-900 truncate">{med.nombre_comercial}</p>
                  <p className="text-xs text-gray-500 truncate">
                    {med.principios_dci.join(' + ')} · {med.forma_farmaceutica}
                  </p>
                </li>
              ))}
            </ul>
          )}

          {medSeleccionado && (
            <div className="mt-1.5 text-xs text-gray-500">
              {medSeleccionado.principios_dci.join(' + ')} · {medSeleccionado.laboratorio}
            </div>
          )}
        </div>

        {/* Región */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">
            Departamento / Región <span className="text-red-500">*</span>
          </label>
          <select
            value={regionId}
            onChange={e => setRegionId(e.target.value ? Number(e.target.value) : '')}
            className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
          >
            <option value="">Selecciona tu departamento...</option>
            {regiones.map(r => (
              <option key={r.id} value={r.id}>{r.nombre}</option>
            ))}
          </select>
        </div>

        {/* Tipo de reporte */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Tipo de problema <span className="text-red-500">*</span>
          </label>
          <div className="space-y-2">
            {TIPOS_REPORTE.map(tipo => (
              <label
                key={tipo.id}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  tipoReporte === tipo.id
                    ? 'border-blue-400 bg-blue-50'
                    : 'border-gray-200 hover:border-gray-300 bg-white'
                }`}
              >
                <input
                  type="radio"
                  name="tipo_reporte"
                  value={tipo.id}
                  checked={tipoReporte === tipo.id}
                  onChange={() => setTipoReporte(tipo.id)}
                  className="mt-0.5 accent-blue-600"
                />
                <div>
                  <p className="text-sm font-medium text-gray-800">{tipo.label}</p>
                  <p className="text-xs text-gray-500">{tipo.desc}</p>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Descripción opcional */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">
            Descripción adicional <span className="text-gray-400 font-normal">(opcional)</span>
          </label>
          <textarea
            value={descripcion}
            onChange={e => setDescripcion(e.target.value)}
            maxLength={500}
            rows={3}
            placeholder="Ej: En todas las droguerías del centro de Bogotá, llevan 2 semanas sin stock..."
            className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
          />
          <p className="text-xs text-gray-400 text-right mt-0.5">{descripcion.length}/500</p>
        </div>

        {error && <p className="text-red-500 text-sm">{error}</p>}

        <button
          type="submit"
          disabled={!puedeEnviar}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white py-2.5 rounded-lg font-medium text-sm transition-colors"
        >
          {enviando ? 'Enviando...' : 'Enviar reporte'}
        </button>
      </form>

      <ReportesRecientes recientes={recientes} total={totalReportes} />
    </div>
  )
}

function ReportesRecientes({ recientes, total }: { recientes: ReporteReciente[]; total: number }) {
  if (total === 0 && recientes.length === 0) return null

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700">Reportes recibidos</h3>
        <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">
          {total} total{total !== 1 ? 'es' : ''}
        </span>
      </div>
      {recientes.length === 0 ? (
        <p className="text-xs text-gray-400 text-center py-2">Sé el primero en reportar.</p>
      ) : (
        <ul className="space-y-2">
          {recientes.map(r => (
            <li key={r.id} className="flex items-start gap-2 text-xs">
              <span className={`mt-0.5 px-1.5 py-0.5 rounded text-xs font-medium shrink-0 ${TIPO_BADGE[r.tipo_reporte] ?? 'bg-gray-100 text-gray-600'}`}>
                {TIPOS_REPORTE.find(t => t.id === r.tipo_reporte)?.label ?? r.tipo_reporte}
              </span>
              <div className="min-w-0">
                <p className="font-medium text-gray-800 truncate">{r.nombre_medicamento}</p>
                <p className="text-gray-400">{r.region_nombre} · {new Date(r.fecha).toLocaleDateString('es-CO')}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
