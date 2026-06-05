import { useState, useMemo } from 'react'
import { medicamentosApi, type MedicamentoLive, type AlternativaLive } from '../api/client'

const FORMULA_CFG: Record<string, { label: string; color: string }> = {
  monocomponente: { label: 'Mono',  color: 'bg-blue-100 text-blue-700' },
  biconjugado:    { label: 'Bi',    color: 'bg-violet-100 text-violet-700' },
  triconjugado:   { label: 'Tri',   color: 'bg-orange-100 text-orange-700' },
  tetraconjugado: { label: 'Tetra', color: 'bg-red-100 text-red-700' },
}

const ALT_CFG: Record<string, { color: string; label: string; desc: string }> = {
  MISMO_PRODUCTO_DIFERENTE_LAB: { color: 'bg-emerald-50 text-emerald-800 border-emerald-200', label: 'Mismo producto — diferente laboratorio', desc: 'Misma molécula, misma dosis, misma forma. Solo cambia el titular.' },
  MISMO_PRINCIPIO_ACTIVO:       { color: 'bg-teal-50 text-teal-800 border-teal-200',          label: 'Mismo principio activo — diferente concentración', desc: 'Misma molécula y forma, distinta dosis.' },
  EQUIVALENTE_EXACTO:           { color: 'bg-blue-50 text-blue-800 border-blue-200',           label: 'Equivalente exacto (sales / ésteres)', desc: 'Mismo ATC-7, misma forma. Distinta sal o éster del mismo compuesto.' },
  EQUIVALENTE_CLASE:            { color: 'bg-indigo-50 text-indigo-800 border-indigo-200',     label: 'Equivalente terapéutico — misma clase ATC', desc: 'Misma clase farmacológica ATC-5, misma forma. Molécula distinta.' },
  COMPONENTE_COMPARTIDO:        { color: 'bg-purple-50 text-purple-800 border-purple-200',     label: 'Combinado con componente en común', desc: 'Comparte al menos un principio activo.' },
  ALTERNATIVA_DIFERENTE_FORMA:  { color: 'bg-amber-50 text-amber-800 border-amber-200',        label: 'Misma molécula o clase — diferente vía/forma', desc: 'Oral vs vaginal, tableta vs inyectable, etc. Requiere evaluación clínica.' },
}

const ALT_ORDEN = [
  'MISMO_PRODUCTO_DIFERENTE_LAB',
  'MISMO_PRINCIPIO_ACTIVO',
  'EQUIVALENTE_EXACTO',
  'EQUIVALENTE_CLASE',
  'COMPONENTE_COMPARTIDO',
  'ALTERNATIVA_DIFERENTE_FORMA',
]

function BadgeFormula({ tipo }: { tipo: string }) {
  const cfg = FORMULA_CFG[tipo] ?? { label: tipo, color: 'bg-slate-100 text-slate-600' }
  return (
    <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${cfg.color}`}>
      {cfg.label}
    </span>
  )
}

function TagDCI({ dci, highlight }: { dci: string; highlight?: boolean }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border ${
      highlight
        ? 'bg-emerald-50 border-emerald-300 text-emerald-700 font-medium'
        : 'bg-slate-100 border-slate-200 text-slate-600'
    }`}>
      {dci}
    </span>
  )
}

function TarjetaMedicamento({
  med, onVer, activa,
}: {
  med: MedicamentoLive
  onVer: (m: MedicamentoLive) => void
  activa: boolean
}) {
  return (
    <div
      onClick={() => onVer(med)}
      className={`bg-white border rounded-xl p-4 cursor-pointer transition-all hover:shadow-sm ${
        activa
          ? 'border-blue-400 ring-2 ring-blue-100 shadow-sm'
          : 'border-slate-200 hover:border-slate-300'
      }`}
    >
      <div className="flex justify-between items-start gap-2 mb-2">
        <div className="min-w-0">
          <p className="font-semibold text-slate-900 truncate text-sm">{med.nombre_comercial}</p>
          <p className="text-xs text-slate-400 truncate">{med.laboratorio}</p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <BadgeFormula tipo={med.tipo_formula} />
          <span className={`text-xs px-1.5 py-0.5 rounded-full ${
            med.estado_cum === 'Activo'
              ? 'bg-emerald-100 text-emerald-700'
              : 'bg-red-100 text-red-600'
          }`}>
            {med.estado_cum}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap gap-1 mb-2">
        {med.principios_dci.map((dci, i) => <TagDCI key={i} dci={dci} />)}
      </div>

      <div className="text-xs text-slate-500 space-y-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-slate-500">{med.forma_farmaceutica}</span>
          <span className="px-1.5 py-0.5 bg-slate-100 border border-slate-200 rounded text-slate-500 uppercase text-[10px] font-semibold tracking-wide">
            {med.via_administracion}
          </span>
          {med.concentracion_display && (
            <span
              className="px-2 py-0.5 bg-slate-100 border border-slate-200 rounded-full font-mono font-semibold text-slate-700 truncate max-w-[180px]"
              title={med.concentracion_display}
            >
              {med.concentracion_display}
            </span>
          )}
        </div>
        <p className="text-slate-400">
          ATC: <span className="font-mono text-slate-500">{med.atc}</span> · {med.descripcion_atc}
        </p>
      </div>
    </div>
  )
}

const VIAS_PARENTERALES = new Set([
  'INTRAVENOSA', 'INTRAMUSCULAR', 'SUBCUTANEA', 'PARENTERAL',
  'INTRAARTICULAR', 'INTRATECAL', 'INTRAPERITONEAL',
])

function esInyectable(med: MedicamentoLive): boolean {
  return (
    VIAS_PARENTERALES.has(med.via_administracion.toUpperCase()) ||
    med.forma_farmaceutica.toUpperCase().includes('INYECT') ||
    med.forma_farmaceutica.toUpperCase().includes('LIOFILIZADO')
  )
}

function PanelAlternativas({
  medicamento, alternativas, cargando, error,
}: {
  medicamento: MedicamentoLive
  alternativas: AlternativaLive[]
  cargando: boolean
  error: string
}) {
  const inyectable = esInyectable(medicamento)

  const porTipo = useMemo(
    () => ALT_ORDEN.reduce<Record<string, AlternativaLive[]>>((acc, t) => {
      acc[t] = alternativas.filter(a => a.tipo === t)
      return acc
    }, {}),
    [alternativas],
  )

  const mismoProd = porTipo['MISMO_PRODUCTO_DIFERENTE_LAB'] ?? []

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
      {/* Header */}
      <div className="bg-slate-50 border-b border-slate-200 px-4 py-3">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="font-semibold text-slate-900 text-sm">{medicamento.nombre_comercial}</p>
          <BadgeFormula tipo={medicamento.tipo_formula} />
        </div>
        <div className="flex flex-wrap gap-1 mt-1.5">
          {medicamento.principios_dci.map((dci, i) => <TagDCI key={i} dci={dci} />)}
        </div>
        <div className="flex items-center gap-1.5 mt-2 flex-wrap">
          <span className="text-xs bg-white border border-slate-200 rounded-full px-2 py-0.5 text-slate-600">
            {medicamento.forma_farmaceutica}
          </span>
          {medicamento.concentracion_display && (
            <span className="text-xs bg-white border border-slate-200 rounded-full px-2 py-0.5 font-mono font-semibold text-slate-700">
              {medicamento.concentracion_display}
            </span>
          )}
          {!cargando && alternativas.length > 0 && (
            <span className="text-xs text-slate-400 ml-auto">{alternativas.length} alternativas</span>
          )}
        </div>
      </div>

      <div className="p-4">
        {cargando && (
          <div className="py-10 text-center">
            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-xs text-slate-400 mt-2">Consultando API online...</p>
          </div>
        )}
        {error && <p className="text-red-500 text-sm">{error}</p>}
        {!cargando && !error && alternativas.length === 0 && (
          <p className="text-slate-400 text-sm text-center py-6">
            No se encontraron alternativas para este medicamento.
          </p>
        )}

        {!cargando && ALT_ORDEN.map(tipo => {
          const lista = porTipo[tipo]
          if (!lista?.length) return null
          const cfg = ALT_CFG[tipo]

          // A0: render compacto — tabla de laboratorios
          if (tipo === 'MISMO_PRODUCTO_DIFERENTE_LAB') {
            return (
              <div key={tipo} className="mb-5 last:mb-0">
                <div className={`flex items-start gap-2 px-2.5 py-2 rounded-lg border mb-1 ${cfg.color}`}>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold">{cfg.label} ({lista.length})</p>
                    <p className="text-xs opacity-70 mt-0.5">{cfg.desc}</p>
                  </div>
                </div>
                <div className="border border-emerald-100 rounded-lg overflow-hidden">
                  {lista.map((alt, i) => {
                    const dest = alt.medicamento_destino
                    return (
                      <div key={i} className="flex items-center gap-3 px-3 py-2 border-b border-emerald-50 last:border-0 hover:bg-emerald-50 transition-colors">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-slate-800 truncate">{dest?.nombre_comercial ?? alt.cum_destino}</p>
                          {dest?.concentracion_display && (
                            <p className="text-xs font-mono text-slate-500 truncate">{dest.concentracion_display}</p>
                          )}
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="text-xs text-slate-600 font-medium">{dest?.laboratorio}</p>
                          {dest && (
                            <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                              dest.estado_cum === 'Activo'
                                ? 'bg-emerald-100 text-emerald-700'
                                : 'bg-red-100 text-red-600'
                            }`}>
                              {dest.estado_cum}
                            </span>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          }

          // Resto de categorías: render estándar
          return (
            <div key={tipo} className="mb-5 last:mb-0">
              <div className={`flex items-start gap-2 px-2.5 py-2 rounded-lg border mb-2 ${cfg.color}`}>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold">{cfg.label} ({lista.length})</p>
                  <p className="text-xs opacity-70 mt-0.5">{cfg.desc}</p>
                </div>
              </div>
              {/* Advertencia específica para inyectables en A1 */}
              {tipo === 'MISMO_PRINCIPIO_ACTIVO' && inyectable && (
                <div className="flex gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-2">
                  <svg className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
                  </svg>
                  <p className="text-xs text-amber-700 leading-relaxed">
                    <strong>Inyectables:</strong> la comparación usa el contenido total del envase (mcg o mg por ampolla), no la concentración por mL. Un vial de 250 mcg/5 mL y uno de 500 mcg/10 mL son la <strong>misma concentración</strong> (50 mcg/mL). Verifique mcg/mL antes de concluir que son dosis diferentes.
                  </p>
                </div>
              )}
              <div className="space-y-2">
                {lista.map((alt, i) => {
                  const dest = alt.medicamento_destino
                  return (
                    <div key={i} className="border border-slate-100 rounded-lg p-3 bg-slate-50">
                      {dest ? (
                        <>
                          <div className="flex items-start justify-between gap-2">
                            <p className="font-medium text-sm text-slate-900">{dest.nombre_comercial}</p>
                            <BadgeFormula tipo={dest.tipo_formula} />
                          </div>
                          <div className="flex flex-wrap gap-1 my-1.5">
                            {dest.principios_dci.map((dci, j) => (
                              <TagDCI
                                key={j}
                                dci={dci}
                                highlight={alt.componentes_compartidos.includes(dci)}
                              />
                            ))}
                          </div>
                          <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
                            <span>{dest.forma_farmaceutica}</span>
                            <span className="px-1.5 py-0.5 bg-slate-100 border border-slate-200 rounded uppercase text-[10px] font-semibold tracking-wide text-slate-500">
                              {dest.via_administracion}
                            </span>
                            {dest.concentracion_display && (
                              <span className="font-mono font-semibold text-slate-600 bg-white border border-slate-200 px-1.5 py-0.5 rounded">
                                {dest.concentracion_display}
                              </span>
                            )}
                            <span>· {dest.laboratorio}</span>
                          </div>
                        </>
                      ) : (
                        <p className="text-xs text-slate-500 font-mono">{alt.cum_destino}</p>
                      )}
                      {alt.componentes_compartidos.length > 0 && tipo !== 'MISMO_PRINCIPIO_ACTIVO' && (
                        <p className="text-xs text-emerald-600 mt-1.5 font-medium">
                          Compartido: {alt.componentes_compartidos.join(', ')}
                        </p>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}

        {/* Nota si solo hay A0 y ninguna otra */}
        {!cargando && mismoProd.length > 0 && alternativas.length === mismoProd.length && (
          <p className="text-xs text-slate-400 text-center pt-2">
            Solo se encontraron sustitutos del mismo producto. No hay alternativas terapéuticas en el CUM para esta clase.
          </p>
        )}

        {/* Disclaimer de fuente y limitaciones */}
        {!cargando && alternativas.length > 0 && (
          <div className="mt-4 pt-3 border-t border-slate-100 flex gap-2">
            <svg className="w-3.5 h-3.5 text-slate-300 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zm-9-3.75h.008v.008H12V8.25z" />
            </svg>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              Datos en tiempo real del <strong>CUM-INVIMA</strong> vía datos.gov.co. Las equivalencias son farmacéuticas (misma molécula, forma y dosis según el registro). <strong>No reemplazan el criterio clínico ni farmacéutico</strong> — toda sustitución debe ser validada por un profesional de salud.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

export default function BuscadorMedicamentos() {
  const [query, setQuery] = useState('')
  const [resultados, setResultados] = useState<MedicamentoLive[]>([])
  const [buscando, setBuscando] = useState(false)
  const [errorBusq, setErrorBusq] = useState('')
  const [hasBuscado, setHasBuscado] = useState(false)

  const [medSeleccionado, setMedSeleccionado] = useState<MedicamentoLive | null>(null)
  const [alternativas, setAlternativas] = useState<AlternativaLive[]>([])
  const [cargandoAlt, setCargandoAlt] = useState(false)
  const [errorAlt, setErrorAlt] = useState('')

  const buscar = async (e: React.FormEvent) => {
    e.preventDefault()
    if (query.trim().length < 2) return
    setBuscando(true)
    setErrorBusq('')
    setMedSeleccionado(null)
    setHasBuscado(true)
    try {
      const res = await medicamentosApi.buscar(query.trim(), true, 30)
      setResultados(res.data)
    } catch {
      setErrorBusq('Error de conexión. Verifica que el backend esté activo.')
    } finally {
      setBuscando(false)
    }
  }

  const verAlternativas = async (med: MedicamentoLive) => {
    setMedSeleccionado(med)
    setCargandoAlt(true)
    setErrorAlt('')
    setAlternativas([])
    try {
      const res = await medicamentosApi.alternativas(med.cum_id)
      setAlternativas(res.data)
    } catch {
      setErrorAlt('No se pudieron cargar las alternativas.')
    } finally {
      setCargandoAlt(false)
    }
  }

  const stats = resultados.reduce<Record<string, number>>((acc, m) => {
    acc[m.tipo_formula] = (acc[m.tipo_formula] ?? 0) + 1
    return acc
  }, {})

  return (
    <div className="space-y-4">

      {/* Search bar */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
        <form onSubmit={buscar} className="flex gap-2">
          <div className="relative flex-1">
            <svg className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607z" />
            </svg>
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Nombre comercial, principio activo o código ATC..."
              className="w-full border border-slate-200 rounded-lg pl-9 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <button
            type="submit"
            disabled={buscando || query.trim().length < 2}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors shrink-0"
          >
            {buscando ? 'Buscando...' : 'Buscar'}
          </button>
        </form>

        {errorBusq && <p className="text-red-500 text-sm mt-2">{errorBusq}</p>}

        {resultados.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-slate-100 items-center">
            <span className="text-xs text-slate-500">{resultados.length} resultados</span>
            {Object.entries(stats).map(([tipo, n]) => {
              const cfg = FORMULA_CFG[tipo]
              if (!cfg) return null
              return (
                <span key={tipo} className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg.color}`}>
                  {n} {tipo}
                </span>
              )
            })}
            {medSeleccionado && (
              <span className="text-xs text-blue-600 ml-auto">
                Mostrando alternativas de: <strong>{medSeleccionado.nombre_comercial}</strong>
              </span>
            )}
          </div>
        )}
      </div>

      {/* Empty state */}
      {!hasBuscado && (
        <div className="bg-white border border-slate-200 rounded-xl py-14 text-center shadow-sm">
          <svg className="w-10 h-10 text-slate-300 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 1-6.23-.693L4.2 15.3m15.6 0 1.004 4.014A1.5 1.5 0 0 1 19.35 21H4.65a1.5 1.5 0 0 1-1.454-1.686L4.2 15.3" />
          </svg>
          <p className="text-sm font-medium text-slate-600">Busca un medicamento</p>
          <p className="text-xs text-slate-400 mt-1">
            Ingresa el nombre comercial, principio activo (DCI) o código ATC
          </p>
          <p className="text-xs text-slate-300 mt-3">
            Datos en tiempo real desde INVIMA · datos.gov.co
          </p>
        </div>
      )}

      {/* Results grid */}
      {hasBuscado && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="space-y-3 max-h-[68vh] overflow-y-auto pr-1">
            {buscando && (
              <div className="bg-white border border-slate-200 rounded-xl py-12 text-center">
                <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" />
                <p className="text-xs text-slate-400 mt-2">Consultando datos.gov.co...</p>
              </div>
            )}
            {!buscando && resultados.length === 0 && (
              <div className="bg-white border border-slate-200 rounded-xl py-12 text-center">
                <p className="text-sm text-slate-500">Sin resultados para "{query}"</p>
                <p className="text-xs text-slate-400 mt-1">Intenta con otro nombre o principio activo</p>
              </div>
            )}
            {resultados.map(med => (
              <TarjetaMedicamento
                key={med.cum_id}
                med={med}
                onVer={verAlternativas}
                activa={medSeleccionado?.cum_id === med.cum_id}
              />
            ))}
          </div>

          {medSeleccionado && (
            <div className="max-h-[68vh] overflow-y-auto">
              <PanelAlternativas
                medicamento={medSeleccionado}
                alternativas={alternativas}
                cargando={cargandoAlt}
                error={errorAlt}
              />
            </div>
          )}

          {!medSeleccionado && resultados.length > 0 && (
            <div className="bg-white border border-dashed border-slate-300 rounded-xl flex items-center justify-center py-16 text-center hidden lg:flex">
              <div>
                <p className="text-sm text-slate-400">Selecciona un medicamento</p>
                <p className="text-xs text-slate-300 mt-1">para ver sus alternativas terapéuticas</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
