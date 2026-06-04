import { useState } from 'react'
import { medicamentosApi, type MedicamentoLive, type AlternativaLive } from '../api/client'

const TIPO_FORMULA_LABEL: Record<string, { label: string; color: string }> = {
  monocomponente:  { label: 'Mono',  color: 'bg-blue-100 text-blue-700' },
  biconjugado:     { label: 'Bi',    color: 'bg-violet-100 text-violet-700' },
  triconjugado:    { label: 'Tri',   color: 'bg-orange-100 text-orange-700' },
  tetraconjugado:  { label: 'Tetra', color: 'bg-red-100 text-red-700' },
}

const TIPO_ALT_COLOR: Record<string, string> = {
  MISMO_PRINCIPIO_ACTIVO:    'bg-green-100 text-green-800 border-green-200',
  EQUIVALENTE_EXACTO:        'bg-blue-100 text-blue-800 border-blue-200',
  EQUIVALENTE_CLASE:         'bg-indigo-100 text-indigo-800 border-indigo-200',
  COMPONENTE_COMPARTIDO:     'bg-purple-100 text-purple-800 border-purple-200',
  ALTERNATIVA_DIFERENTE_FORMA: 'bg-yellow-100 text-yellow-800 border-yellow-200',
}

const TIPO_ALT_ORDEN = [
  'MISMO_PRINCIPIO_ACTIVO',
  'EQUIVALENTE_EXACTO',
  'EQUIVALENTE_CLASE',
  'COMPONENTE_COMPARTIDO',
  'ALTERNATIVA_DIFERENTE_FORMA',
]

function BadgeFormula({ tipo }: { tipo: string }) {
  const cfg = TIPO_FORMULA_LABEL[tipo] ?? { label: tipo, color: 'bg-gray-100 text-gray-600' }
  return (
    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${cfg.color}`}>
      {cfg.label}
    </span>
  )
}

function TagDCI({ dci }: { dci: string }) {
  return (
    <span className="text-xs bg-slate-100 text-slate-700 border border-slate-200 px-2 py-0.5 rounded-full">
      {dci}
    </span>
  )
}

function TarjetaMedicamento({
  med,
  onVerAlternativas,
  activa,
}: {
  med: MedicamentoLive
  onVerAlternativas: (m: MedicamentoLive) => void
  activa: boolean
}) {
  return (
    <div
      className={`bg-white border rounded-xl p-4 shadow-sm transition-all cursor-pointer ${
        activa ? 'border-blue-500 ring-2 ring-blue-200' : 'border-gray-200 hover:border-blue-300'
      }`}
      onClick={() => onVerAlternativas(med)}
    >
      <div className="flex justify-between items-start gap-2 mb-2">
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-gray-900 truncate">{med.nombre_comercial}</p>
          <p className="text-xs text-gray-400">{med.laboratorio}</p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <BadgeFormula tipo={med.tipo_formula} />
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            med.estado_cum === 'Activo'
              ? 'bg-green-100 text-green-700'
              : 'bg-red-100 text-red-600'
          }`}>
            {med.estado_cum}
          </span>
        </div>
      </div>

      {/* Principios activos como tags */}
      <div className="flex flex-wrap gap-1 mb-2">
        {med.principios_dci.map((dci, i) => (
          <TagDCI key={i} dci={dci} />
        ))}
      </div>

      <div className="text-xs text-gray-500 space-y-0.5">
        <p>{med.forma_farmaceutica} · {med.via_administracion}</p>
        {med.concentracion_display && (
          <p className="text-gray-400 truncate" title={med.concentracion_display}>
            {med.concentracion_display}
          </p>
        )}
        <p>ATC: <span className="font-mono">{med.atc}</span> — {med.descripcion_atc}</p>
      </div>
    </div>
  )
}

function PanelAlternativas({
  medicamento,
  alternativas,
  cargando,
  error,
}: {
  medicamento: MedicamentoLive
  alternativas: AlternativaLive[]
  cargando: boolean
  error: string
}) {
  const porTipo = TIPO_ALT_ORDEN.reduce<Record<string, AlternativaLive[]>>((acc, t) => {
    acc[t] = alternativas.filter(a => a.tipo === t)
    return acc
  }, {})

  const TIPO_LABEL: Record<string, string> = {
    MISMO_PRINCIPIO_ACTIVO: 'Mismo principio activo (genérico/multifuente)',
    EQUIVALENTE_EXACTO: 'Equivalente farmacológico exacto (sales/ésteres)',
    EQUIVALENTE_CLASE: 'Equivalente terapéutico — misma clase ATC',
    COMPONENTE_COMPARTIDO: 'Combinado con componente en común',
    ALTERNATIVA_DIFERENTE_FORMA: 'Alternativa terapéutica — diferente forma',
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      <div className="bg-blue-50 border-b border-blue-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-blue-900">{medicamento.nombre_comercial}</span>
          <BadgeFormula tipo={medicamento.tipo_formula} />
        </div>
        <div className="flex flex-wrap gap-1 mt-1">
          {medicamento.principios_dci.map((dci, i) => <TagDCI key={i} dci={dci} />)}
        </div>
      </div>

      <div className="p-4">
        {cargando && (
          <div className="text-center py-8 text-gray-400">
            <div className="text-2xl mb-2">⏳</div>
            <p>Consultando API online...</p>
          </div>
        )}
        {error && <p className="text-red-500 text-sm">{error}</p>}

        {!cargando && !error && alternativas.length === 0 && (
          <p className="text-gray-400 text-sm text-center py-4">
            No se encontraron alternativas para este medicamento.
          </p>
        )}

        {!cargando && TIPO_ALT_ORDEN.map(tipo => {
          const lista = porTipo[tipo]
          if (!lista?.length) return null
          return (
            <div key={tipo} className="mb-5">
              <h4 className={`text-xs font-semibold px-2 py-1 rounded border mb-2 ${TIPO_ALT_COLOR[tipo]}`}>
                {TIPO_LABEL[tipo]} ({lista.length})
              </h4>
              <div className="space-y-2">
                {lista.map((alt, i) => {
                  const dest = alt.medicamento_destino
                  return (
                    <div key={i} className="border border-gray-100 rounded-lg p-3 bg-gray-50">
                      {dest ? (
                        <>
                          <div className="flex items-start justify-between gap-2">
                            <p className="font-medium text-sm text-gray-900">{dest.nombre_comercial}</p>
                            <BadgeFormula tipo={dest.tipo_formula} />
                          </div>
                          <div className="flex flex-wrap gap-1 my-1">
                            {dest.principios_dci.map((dci, j) => (
                              <span
                                key={j}
                                className={`text-xs px-1.5 py-0.5 rounded-full border ${
                                  alt.componentes_compartidos.includes(dci)
                                    ? 'bg-green-50 border-green-300 text-green-700 font-medium'
                                    : 'bg-gray-100 border-gray-200 text-gray-500'
                                }`}
                              >
                                {dci}
                              </span>
                            ))}
                          </div>
                          <p className="text-xs text-gray-400">
                            {dest.forma_farmaceutica} · ATC {dest.atc} · {dest.laboratorio}
                          </p>
                        </>
                      ) : (
                        <p className="text-xs text-gray-500">{alt.cum_destino}</p>
                      )}
                      {alt.componentes_compartidos.length > 0 && (
                        <p className="text-xs text-green-600 mt-1">
                          Componente(s) en común: {alt.componentes_compartidos.join(', ')}
                        </p>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function BuscadorMedicamentos() {
  const [query, setQuery] = useState('')
  const [resultados, setResultados] = useState<MedicamentoLive[]>([])
  const [buscando, setBuscando] = useState(false)
  const [errorBusq, setErrorBusq] = useState('')

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
    try {
      const res = await medicamentosApi.buscar(query.trim(), true, 30)
      setResultados(res.data)
    } catch {
      setErrorBusq('Error conectando con el servidor. Verifica que el backend esté activo.')
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

  // Agrupar por tipo_formula para el resumen
  const stats = resultados.reduce<Record<string, number>>((acc, m) => {
    acc[m.tipo_formula] = (acc[m.tipo_formula] ?? 0) + 1
    return acc
  }, {})

  return (
    <div className="space-y-4">
      {/* Buscador */}
      <form onSubmit={buscar} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Nombre comercial, principio activo, ATC o CUM..."
          className="flex-1 border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
        />
        <button
          type="submit"
          disabled={buscando}
          className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2.5 rounded-lg font-medium text-sm transition-colors disabled:opacity-50"
        >
          {buscando ? 'Buscando...' : 'Buscar'}
        </button>
      </form>

      {errorBusq && <p className="text-red-500 text-sm">{errorBusq}</p>}

      {/* Resumen de resultados */}
      {resultados.length > 0 && (
        <div className="flex flex-wrap gap-2 items-center text-sm text-gray-500">
          <span>{resultados.length} resultados</span>
          {Object.entries(stats).map(([tipo, n]) => {
            const cfg = TIPO_FORMULA_LABEL[tipo]
            if (!cfg) return null
            return (
              <span key={tipo} className={`text-xs px-2 py-0.5 rounded font-medium ${cfg.color}`}>
                {n} {tipo}
              </span>
            )
          })}
        </div>
      )}

      {/* Layout de dos columnas */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Columna izquierda: resultados */}
        <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
          {resultados.map(med => (
            <TarjetaMedicamento
              key={med.cum_id}
              med={med}
              onVerAlternativas={verAlternativas}
              activa={medSeleccionado?.cum_id === med.cum_id}
            />
          ))}
        </div>

        {/* Columna derecha: panel de alternativas */}
        {medSeleccionado && (
          <div className="max-h-[70vh] overflow-y-auto">
            <PanelAlternativas
              medicamento={medSeleccionado}
              alternativas={alternativas}
              cargando={cargandoAlt}
              error={errorAlt}
            />
          </div>
        )}
      </div>
    </div>
  )
}
