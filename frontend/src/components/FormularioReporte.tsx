import { useState, useEffect, useRef } from 'react'
import { medicamentosApi, reportesApi, type MedicamentoLive, type ReporteReciente } from '../api/client'

const TIPOS = [
  { id: 'sin_stock',      label: 'Sin stock',        desc: 'No disponible en farmacias o droguerías', badge: 'bg-red-100 text-red-700 border-red-200' },
  { id: 'precio_alto',    label: 'Precio elevado',   desc: 'Supera el valor regulado o habitual',     badge: 'bg-amber-100 text-amber-700 border-amber-200' },
  { id: 'sin_suministro', label: 'Sin suministro',   desc: 'El laboratorio no está distribuyendo',    badge: 'bg-orange-100 text-orange-700 border-orange-200' },
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

  const [tipo, setTipo]        = useState('sin_stock')
  const [descripcion, setDesc] = useState('')

  const [enviando, setEnviando] = useState(false)
  const [exito, setExito]       = useState(false)
  const [error, setError]       = useState('')

  const [recientes, setRecientes] = useState<ReporteReciente[]>([])
  const [total, setTotal]         = useState(0)

  const dropRef    = useRef<HTMLDivElement>(null)
  const qDebounced = useDebounce(query, 300)

  useEffect(() => { loadRecientes() }, [])

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
    medicamentosApi.buscar(qDebounced, true, 10)
      .then(r => { setSugerencias(r.data ?? []); setShowDrop(true) })
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
    setSugerencias([])
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
          <button onClick={nuevo} className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors">
            Reportar otro
          </button>
        </div>
        <ReportesPanel recientes={recientes} total={total} />
      </div>
    )
  }

  return (
    <div className="max-w-xl space-y-4">

      {/* Banner informativo */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 flex gap-3">
        <svg className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zm-9-3.75h.008v.008H12V8.25z" />
        </svg>
        <p className="text-xs text-blue-700 leading-relaxed">
          Reporta cuando un medicamento no está disponible. Cada reporte actualiza
          directamente el modelo de predicción de desabastecimiento nacional.
        </p>
      </div>

      <form onSubmit={enviar} className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="px-5 py-4 space-y-5">

          {/* Búsqueda de medicamento */}
          <div ref={dropRef} className="relative">
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-2">
              Medicamento <span className="text-red-500 normal-case font-normal">*</span>
            </label>

            {!medSeleccionado ? (
              <>
                <div className="relative">
                  <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607z" />
                  </svg>
                  <input
                    type="text"
                    value={query}
                    onChange={e => { setQuery(e.target.value); setMedSeleccionado(null) }}
                    onFocus={() => sugerencias.length > 0 && setShowDrop(true)}
                    placeholder="Buscar por nombre comercial, principio activo o CUM..."
                    className="w-full border border-slate-200 rounded-lg pl-9 pr-8 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                  {buscando && (
                    <div className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                  )}
                </div>

                {showDrop && sugerencias.length > 0 && (
                  <ul className="absolute z-20 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-xl shadow-lg max-h-72 overflow-y-auto divide-y divide-slate-50">
                    {sugerencias.map(med => (
                      <li
                        key={med.cum_id}
                        onMouseDown={() => seleccionar(med)}
                        className="px-4 py-3 hover:bg-slate-50 cursor-pointer"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-semibold text-slate-900 truncate">{med.nombre_comercial}</p>
                            <p className="text-xs text-slate-500 truncate mt-0.5">
                              {med.principios_dci.join(' + ')}
                            </p>
                            <div className="flex items-center gap-2 mt-1 flex-wrap">
                              <span className="text-xs text-slate-400">{med.forma_farmaceutica}</span>
                              {med.concentracion_display && (
                                <>
                                  <span className="text-slate-300 text-xs">·</span>
                                  <span className="text-xs text-slate-400">{med.concentracion_display}</span>
                                </>
                              )}
                              {med.laboratorio && (
                                <>
                                  <span className="text-slate-300 text-xs">·</span>
                                  <span className="text-xs text-slate-400 truncate">{med.laboratorio}</span>
                                </>
                              )}
                            </div>
                          </div>
                          <span className="shrink-0 text-xs font-mono text-slate-400 bg-slate-50 px-1.5 py-0.5 rounded border border-slate-100">
                            {med.cum_id.split('-')[0]}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}

                {query.length >= 2 && !buscando && sugerencias.length === 0 && (
                  <p className="text-xs text-slate-400 mt-1.5">No se encontraron resultados. Intenta con otro nombre o principio activo.</p>
                )}
              </>
            ) : (
              /* Tarjeta del medicamento seleccionado */
              <div className="border border-emerald-300 bg-emerald-50 rounded-xl p-4 relative">
                <button
                  type="button"
                  onClick={limpiar}
                  className="absolute top-3 right-3 text-slate-400 hover:text-slate-600 transition-colors"
                  aria-label="Cambiar medicamento"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>

                <div className="flex items-start gap-3 pr-6">
                  <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center shrink-0 mt-0.5">
                    <svg className="w-4 h-4 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                    </svg>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-slate-900">{medSeleccionado.nombre_comercial}</p>
                    <p className="text-xs text-slate-600 mt-0.5">{medSeleccionado.principios_dci.join(' + ')}</p>

                    <div className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1.5">
                      <div>
                        <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">CUM</p>
                        <p className="text-xs text-slate-700 font-mono">{medSeleccionado.cum_id}</p>
                      </div>
                      <div>
                        <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">Forma</p>
                        <p className="text-xs text-slate-700">{medSeleccionado.forma_farmaceutica}</p>
                      </div>
                      {medSeleccionado.concentracion_display && (
                        <div>
                          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">Concentración</p>
                          <p className="text-xs text-slate-700">{medSeleccionado.concentracion_display}</p>
                        </div>
                      )}
                      {medSeleccionado.laboratorio && (
                        <div>
                          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">Laboratorio</p>
                          <p className="text-xs text-slate-700 truncate">{medSeleccionado.laboratorio}</p>
                        </div>
                      )}
                      <div>
                        <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">Registro</p>
                        <p className="text-xs text-slate-700">{medSeleccionado.registro_sanitario || '—'}</p>
                      </div>
                      <div>
                        <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">Estado</p>
                        <span className={`inline-block text-xs px-1.5 py-0.5 rounded font-medium ${
                          medSeleccionado.estado_cum?.toLowerCase().includes('activo')
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-amber-100 text-amber-700'
                        }`}>
                          {medSeleccionado.estado_cum || medSeleccionado.estado_registro || '—'}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Tipo de problema */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-2">
              Tipo de problema <span className="text-red-500 normal-case font-normal">*</span>
            </label>
            <div className="space-y-2">
              {TIPOS.map(t => (
                <label
                  key={t.id}
                  className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    tipo === t.id ? 'border-blue-300 bg-blue-50' : 'border-slate-200 hover:border-slate-300 bg-white'
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
