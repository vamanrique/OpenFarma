import { useState, useEffect, useRef } from 'react'
import { medicamentosApi, reportesApi, type MedicamentoLive, type ReporteReciente } from '../api/client'

const TIPOS = [
  { id: 'sin_stock',      label: 'Sin stock',       desc: 'No disponible en farmacias',          badge: 'bg-red-100 text-red-700 border-red-200' },
  { id: 'precio_alto',    label: 'Precio elevado',  desc: 'Supera el valor regulado o habitual', badge: 'bg-amber-100 text-amber-700 border-amber-200' },
  { id: 'sin_suministro', label: 'Sin suministro',  desc: 'El laboratorio no está distribuyendo', badge: 'bg-orange-100 text-orange-700 border-orange-200' },
]

function useDebounce<T>(value: T, delay: number): T {
  const [d, setD] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setD(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return d
}

export default function FormularioReporte() {
  const [query, setQuery]                     = useState('')
  const [sugerencias, setSugerencias]         = useState<MedicamentoLive[]>([])
  const [buscando, setBuscando]               = useState(false)
  const [medSeleccionado, setMedSeleccionado] = useState<MedicamentoLive | null>(null)
  const [showDrop, setShowDrop]               = useState(false)

  const [tipo, setTipo]           = useState('sin_stock')
  const [descripcion, setDesc]    = useState('')

  const [enviando, setEnviando] = useState(false)
  const [exito, setExito]       = useState(false)
  const [error, setError]       = useState('')

  const [recientes, setRecientes]   = useState<ReporteReciente[]>([])
  const [total, setTotal]           = useState(0)

  const dropRef  = useRef<HTMLDivElement>(null)
  const qDebounced = useDebounce(query, 300)

  useEffect(() => {
    loadRecientes()
  }, [])

  const loadRecientes = async () => {
    try {
      const [r, t] = await Promise.all([reportesApi.recientes(5), reportesApi.total()])
      if (r?.data) setRecientes(r.data)
      if (t?.data?.total != null) setTotal(t.data.total)
    } catch {}
  }

  useEffect(() => {
    if (qDebounced.length < 2 || medSeleccionado) { setSugerencias([]); return }
    setBuscando(true)
    medicamentosApi.buscar(qDebounced, true, 8)
      .then(r => { setSugerencias(r.data); setShowDrop(true) })
      .catch(() => setSugerencias([]))
      .finally(() => setBuscando(false))
  }, [qDebounced, medSeleccionado])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) setShowDrop(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const seleccionar = (med: MedicamentoLive) => {
    setMedSeleccionado(med)
    setQuery(med.nombre_comercial)
    setShowDrop(false)
  }

  const limpiar = () => { setMedSeleccionado(null); setQuery(''); setSugerencias([]) }

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!medSeleccionado) return
    setEnviando(true)
    setError('')
    try {
      await reportesApi.reportar(medSeleccionado.cum_id, tipo, descripcion.trim() || undefined)
      setExito(true)
      await loadRecientes()
    } catch {
      setError('Error al enviar el reporte. Intenta de nuevo.')
    } finally {
      setEnviando(false)
    }
  }

  const nuevo = () => {
    setExito(false); setMedSeleccionado(null); setQuery(''); setTipo('sin_stock'); setDesc(''); setError('')
  }

  if (exito) {
    return (
      <div className="max-w-xl space-y-4">
        <div className="bg-white border border-slate-200 rounded-xl p-8 text-center shadow-sm">
          <div className="w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-6 h-6 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-slate-900 mb-1">Reporte enviado</h3>
          <p className="text-sm text-slate-600 mb-1">
            <strong>{medSeleccionado?.nombre_comercial}</strong>
          </p>
          <p className="text-xs text-slate-400 mb-6">
            Tu reporte alimenta el modelo predictivo de desabastecimiento de Colombia.
          </p>
          <button
            onClick={nuevo}
            className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            Reportar otro
          </button>
        </div>
        <ReportesPanel recientes={recientes} total={total} />
      </div>
    )
  }

  return (
    <div className="max-w-xl space-y-4">

      {/* Info banner */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 flex gap-3">
        <svg className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zm-9-3.75h.008v.008H12V8.25z" />
        </svg>
        <p className="text-xs text-blue-700 leading-relaxed">
          Reporta cuando un medicamento no está disponible. Cada reporte actualiza
          directamente el modelo de predicción de desabastecimiento nacional.
        </p>
      </div>

      {/* Form */}
      <form onSubmit={enviar} className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">

        <div className="px-5 py-4 space-y-5">

          {/* Medicamento */}
          <div ref={dropRef} className="relative">
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-2">
              Medicamento <span className="text-red-500 normal-case font-normal">*</span>
            </label>
            <div className="relative">
              <input
                type="text"
                value={query}
                onChange={e => { setQuery(e.target.value); setMedSeleccionado(null) }}
                onFocus={() => sugerencias.length > 0 && setShowDrop(true)}
                placeholder="Buscar por nombre, principio activo o ATC..."
                className={`w-full border rounded-lg px-3 py-2.5 text-sm pr-8 focus:outline-none focus:ring-2 transition-colors ${
                  medSeleccionado
                    ? 'border-emerald-400 bg-emerald-50 focus:ring-emerald-300'
                    : 'border-slate-200 focus:ring-blue-500 focus:border-transparent'
                }`}
              />
              {medSeleccionado && (
                <button type="button" onClick={limpiar}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-lg leading-none">
                  ×
                </button>
              )}
              {buscando && !medSeleccionado && (
                <div className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
              )}
            </div>

            {showDrop && sugerencias.length > 0 && (
              <ul className="absolute z-20 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-xl shadow-lg max-h-52 overflow-y-auto">
                {sugerencias.map(med => (
                  <li
                    key={med.cum_id}
                    onMouseDown={() => seleccionar(med)}
                    className="px-3 py-2.5 hover:bg-slate-50 cursor-pointer border-b border-slate-50 last:border-0"
                  >
                    <p className="text-sm font-medium text-slate-900 truncate">{med.nombre_comercial}</p>
                    <p className="text-xs text-slate-400 truncate">
                      {med.principios_dci.join(' + ')} · {med.forma_farmaceutica}
                    </p>
                  </li>
                ))}
              </ul>
            )}

            {medSeleccionado && (
              <p className="text-xs text-slate-500 mt-1.5">
                {medSeleccionado.principios_dci.join(' + ')} · {medSeleccionado.laboratorio}
              </p>
            )}
          </div>

          {/* Tipo */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-2">
              Tipo de problema <span className="text-red-500 normal-case font-normal">*</span>
            </label>
            <div className="space-y-2">
              {TIPOS.map(t => (
                <label
                  key={t.id}
                  className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    tipo === t.id
                      ? 'border-blue-300 bg-blue-50'
                      : 'border-slate-200 hover:border-slate-300 bg-white'
                  }`}
                >
                  <input
                    type="radio"
                    name="tipo"
                    value={t.id}
                    checked={tipo === t.id}
                    onChange={() => setTipo(t.id)}
                    className="mt-0.5 accent-blue-600"
                  />
                  <div>
                    <p className="text-sm font-medium text-slate-800">{t.label}</p>
                    <p className="text-xs text-slate-500">{t.desc}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Descripción */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-2">
              Descripción adicional
              <span className="text-slate-400 normal-case font-normal ml-1">(opcional)</span>
            </label>
            <textarea
              value={descripcion}
              onChange={e => setDesc(e.target.value)}
              maxLength={500}
              rows={3}
              placeholder="Ej: Agotado en todas las droguerías del centro desde hace 2 semanas..."
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
            />
            <p className="text-xs text-slate-400 text-right mt-0.5">{descripcion.length}/500</p>
          </div>
        </div>

        {error && (
          <div className="mx-5 mb-4 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-600">
            {error}
          </div>
        )}

        <div className="px-5 pb-5">
          <button
            type="submit"
            disabled={!medSeleccionado || enviando}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed text-white py-2.5 rounded-lg font-medium text-sm transition-colors"
          >
            {enviando ? 'Enviando...' : 'Enviar reporte'}
          </button>
        </div>
      </form>

      <ReportesPanel recientes={recientes} total={total} />
    </div>
  )
}

function ReportesPanel({ recientes, total }: { recientes: ReporteReciente[]; total: number }) {
  if (total === 0 && recientes.length === 0) return null

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
      <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">Reportes recibidos</h3>
        <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium tabular-nums">
          {total.toLocaleString('es-CO')} total
        </span>
      </div>
      <div className="divide-y divide-slate-50">
        {recientes.length === 0 ? (
          <p className="text-xs text-slate-400 text-center py-4">Sé el primero en reportar.</p>
        ) : (
          recientes.map(r => {
            const tipo = TIPOS.find(t => t.id === r.tipo_reporte)
            return (
              <div key={r.id} className="px-5 py-3 flex items-start gap-3">
                <span className={`mt-0.5 text-xs px-2 py-0.5 rounded border font-medium shrink-0 ${tipo?.badge ?? 'bg-slate-100 text-slate-600 border-slate-200'}`}>
                  {tipo?.label ?? r.tipo_reporte}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-800 truncate">{r.nombre_medicamento}</p>
                  <p className="text-xs text-slate-400">{new Date(r.fecha).toLocaleDateString('es-CO')}</p>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
