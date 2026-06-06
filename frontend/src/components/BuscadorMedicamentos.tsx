import { useState, useMemo } from 'react'
import { medicamentosApi, type MedicamentoLive, type AlternativaLive } from '../api/client'

// ─── Configuración de fórmulas ───────────────────────────────────────────────
const FORMULA_CFG: Record<string, { label: string; color: string }> = {
  monocomponente: { label: 'Mono',  color: 'bg-blue-100 text-blue-700' },
  biconjugado:    { label: 'Bi',    color: 'bg-violet-100 text-violet-700' },
  triconjugado:   { label: 'Tri',   color: 'bg-orange-100 text-orange-700' },
  tetraconjugado: { label: 'Tetra', color: 'bg-red-100 text-red-700' },
}

// ─── Configuración de alternativas ───────────────────────────────────────────
const ALT_CFG: Record<string, { color: string; label: string; desc: string }> = {
  SUSTITUTO_DIRECTO:               { color: 'bg-emerald-50 text-emerald-800 border-emerald-200', label: 'Sustituto directo', desc: 'Mismo principio activo, misma concentración, misma presentación y misma forma. Solo cambia el titular del registro.' },
  MISMA_CONC_DIFERENTE_CANTIDAD:   { color: 'bg-lime-50 text-lime-800 border-lime-200',          label: 'Misma molécula · misma concentración · diferente cantidad', desc: 'Misma concentración y forma farmacéutica, pero distinto volumen o número de dosis por envase.' },
  MISMA_CONC_DIFERENTE_FORMA:      { color: 'bg-sky-50 text-sky-800 border-sky-200',             label: 'Misma molécula · misma concentración · diferente forma', desc: 'Mismo PA y dosis, pero distinta forma farmacéutica (ej. tableta convencional vs liberación prolongada). Requiere evaluación clínica por diferencias farmacocinéticas.' },
  DIFERENTE_CONCENTRACION:         { color: 'bg-teal-50 text-teal-800 border-teal-200',          label: 'Misma molécula — diferente concentración', desc: 'Misma molécula y forma farmacéutica, distinta dosis. Requieren ajuste de posología por parte del profesional de salud.' },
  EQUIVALENTE_EXACTO:              { color: 'bg-blue-50 text-blue-800 border-blue-200',           label: 'Equivalente exacto (sales / ésteres)', desc: 'Mismo ATC-7, misma forma. Distinta sal o éster del mismo compuesto.' },
  EQUIVALENTE_CLASE:               { color: 'bg-indigo-50 text-indigo-800 border-indigo-200',     label: 'Equivalente terapéutico — misma clase ATC', desc: 'Misma clase farmacológica ATC-5, misma forma. Molécula distinta.' },
  COMPONENTE_COMPARTIDO:           { color: 'bg-purple-50 text-purple-800 border-purple-200',     label: 'Combinado con componente en común', desc: 'Comparte al menos un principio activo.' },
  ALTERNATIVA_DIFERENTE_FORMA:     { color: 'bg-amber-50 text-amber-800 border-amber-200',        label: 'Misma molécula o clase — diferente vía/forma', desc: 'Oral vs vaginal, tableta vs inyectable, etc. Requiere evaluación clínica.' },
}

const TIPOS_TERAPEUTICOS = [
  'EQUIVALENTE_EXACTO', 'EQUIVALENTE_CLASE', 'COMPONENTE_COMPARTIDO', 'ALTERNATIVA_DIFERENTE_FORMA',
]

// ─── Grupos de formas farmacéuticas (espejo del backend) ─────────────────────
const VIA_A_GRUPO: Record<string, string> = {
  'VAGINAL': 'VAGINAL', 'RECTAL': 'RECTAL',
  'SUBLINGUAL': 'SUBLINGUAL', 'BUCAL': 'SUBLINGUAL', 'SUBLINGUAL - BUCAL': 'SUBLINGUAL',
  'OFTALMICA': 'OFTALMICO', 'OCULAR': 'OFTALMICO',
  'OTICA': 'OTICO', 'AUDITIVA': 'OTICO',
  'NASAL': 'NASAL', 'INTRANASAL': 'NASAL',
  'INHALATORIA': 'INHALADO', 'PULMONAR': 'INHALADO', 'INHALACION': 'INHALADO',
  'TRANSDERMICA': 'TRANSDERMICO', 'CUTANEA': 'TRANSDERMICO',
  'INTRAVENOSA': 'INYECTABLE', 'INTRAMUSCULAR': 'INYECTABLE',
  'SUBCUTANEA': 'INYECTABLE', 'PARENTERAL': 'INYECTABLE',
  'INTRAARTICULAR': 'INYECTABLE', 'INTRATECAL': 'INYECTABLE', 'INTRAPERITONEAL': 'INYECTABLE',
}

const FORMA_A_GRUPO: Record<string, string> = {
  'TABLETA': 'SOLIDO_ORAL', 'TABLETA RECUBIERTA': 'SOLIDO_ORAL',
  'TABLETA CUBIERTA CON PELICULA': 'SOLIDO_ORAL', 'TABLETA MASTICABLE': 'SOLIDO_ORAL',
  'COMPRIMIDO': 'SOLIDO_ORAL', 'GRAGEA': 'SOLIDO_ORAL',
  'CAPSULA': 'SOLIDO_ORAL', 'CAPSULA DURA': 'SOLIDO_ORAL',
  'CAPSULA BLANDA': 'SOLIDO_ORAL', 'CAPSULA GELATINOSA': 'SOLIDO_ORAL',
  'TABLETA DE LIBERACION PROLONGADA': 'SOLIDO_ORAL_LP', 'TABLETA DE LIBERACION CONTROLADA': 'SOLIDO_ORAL_LP',
  'TABLETA DE LIBERACION MODIFICADA': 'SOLIDO_ORAL_LP', 'TABLETA DE LIBERACION SOSTENIDA': 'SOLIDO_ORAL_LP',
  'TABLETA DE LIBERACION RETARDADA': 'SOLIDO_ORAL_LP', 'TABLETA DE ACCION PROLONGADA': 'SOLIDO_ORAL_LP',
  'CAPSULA DE LIBERACION PROLONGADA': 'SOLIDO_ORAL_LP', 'CAPSULA DE LIBERACION CONTROLADA': 'SOLIDO_ORAL_LP',
  'CAPSULA DE LIBERACION MODIFICADA': 'SOLIDO_ORAL_LP', 'CAPSULA DE LIBERACION SOSTENIDA': 'SOLIDO_ORAL_LP',
  'CAPSULA DE LIBERACION RETARDADA': 'SOLIDO_ORAL_LP', 'CAPSULA DE ACCION PROLONGADA': 'SOLIDO_ORAL_LP',
  'COMPRIMIDO DE LIBERACION PROLONGADA': 'SOLIDO_ORAL_LP', 'COMPRIMIDO DE LIBERACION CONTROLADA': 'SOLIDO_ORAL_LP',
  'TABLETA DISPERSABLE': 'ORAL_DISPERSABLE', 'TABLETA EFERVESCENTE': 'ORAL_DISPERSABLE',
  'POLVO PARA SUSPENSION ORAL': 'ORAL_DISPERSABLE', 'GRANULADO ORAL': 'ORAL_DISPERSABLE',
  'JARABE': 'LIQUIDO_ORAL', 'SOLUCION ORAL': 'LIQUIDO_ORAL',
  'SUSPENSION ORAL': 'LIQUIDO_ORAL', 'ELIXIR': 'LIQUIDO_ORAL',
  'GOTAS ORALES': 'LIQUIDO_ORAL', 'SOLUCION': 'LIQUIDO_ORAL',
  'SUSPENSION': 'LIQUIDO_ORAL', 'EMULSION ORAL': 'LIQUIDO_ORAL',
  'TABLETA SUBLINGUAL': 'SUBLINGUAL', 'COMPRIMIDO SUBLINGUAL': 'SUBLINGUAL',
  'TABLETA BUCODISPERSABLE': 'SUBLINGUAL', 'FILM SUBLINGUAL': 'SUBLINGUAL',
  'SOLUCION INYECTABLE': 'INYECTABLE', 'POLVO PARA SOLUCION INYECTABLE': 'INYECTABLE',
  'SOLUCION PARA INYECCION': 'INYECTABLE', 'INYECTABLE': 'INYECTABLE',
  'POLVO LIOFILIZADO PARA RECONSTITUIR A SOLUCION INYECTABLE': 'INYECTABLE',
  'CONCENTRADO PARA SOLUCION PARA PERFUSION': 'INYECTABLE',
  'SUSPENSION INYECTABLE': 'INYECTABLE', 'EMULSION INYECTABLE': 'INYECTABLE',
  'CREMA': 'TOPICO', 'UNGÜENTO': 'TOPICO', 'GEL': 'TOPICO',
  'LOCION': 'TOPICO', 'POMADA': 'TOPICO', 'EMULSION': 'TOPICO', 'ESPUMA': 'TOPICO',
  'AEROSOL PARA INHALACION': 'INHALADO', 'POLVO PARA INHALACION': 'INHALADO',
  'SOLUCION PARA INHALACION': 'INHALADO', 'INHALADOR': 'INHALADO',
  'COLIRIO': 'OFTALMICO', 'SOLUCION OFTALMICA': 'OFTALMICO',
  'GOTAS OFTALMICAS': 'OFTALMICO', 'POMADA OFTALMICA': 'OFTALMICO', 'GEL OFTALMICO': 'OFTALMICO',
  'OVULO': 'VAGINAL', 'OVULOS': 'VAGINAL', 'CAPSULA VAGINAL': 'VAGINAL',
  'TABLETA VAGINAL': 'VAGINAL', 'COMPRIMIDO VAGINAL': 'VAGINAL',
  'CREMA VAGINAL': 'VAGINAL', 'GEL VAGINAL': 'VAGINAL',
  'SOLUCION VAGINAL': 'VAGINAL', 'ESPUMA VAGINAL': 'VAGINAL',
  'SUPOSITORIO': 'RECTAL', 'SUPOSITORIOS': 'RECTAL', 'ENEMA': 'RECTAL',
  'CREMA RECTAL': 'RECTAL', 'GEL RECTAL': 'RECTAL', 'SOLUCION RECTAL': 'RECTAL',
  'PARCHE TRANSDERMICO': 'TRANSDERMICO', 'PARCHE': 'TRANSDERMICO', 'GEL TRANSDERMICO': 'TRANSDERMICO',
  'GOTAS OTICAS': 'OTICO', 'GOTAS ÓTICAS': 'OTICO', 'SOLUCION OTICA': 'OTICO',
  'SPRAY NASAL': 'NASAL', 'GOTAS NASALES': 'NASAL', 'SOLUCION NASAL': 'NASAL', 'GEL NASAL': 'NASAL',
}

const GRUPO_LABEL: Record<string, string> = {
  SOLIDO_ORAL: 'Sólido oral', SOLIDO_ORAL_LP: 'Liberación prolongada',
  ORAL_DISPERSABLE: 'Dispersable',
  LIQUIDO_ORAL: 'Líquido oral', SUBLINGUAL: 'Sublingual/Bucal',
  INYECTABLE: 'Inyectable', TOPICO: 'Tópico', INHALADO: 'Inhalado',
  OFTALMICO: 'Oftálmico', VAGINAL: 'Vaginal', RECTAL: 'Rectal',
  TRANSDERMICO: 'Transdérmico', OTICO: 'Ótico', NASAL: 'Nasal',
}

function grupoForma(forma: string, via: string): string {
  const viaU = via.trim().toUpperCase()
  return VIA_A_GRUPO[viaU] ?? FORMA_A_GRUPO[forma.trim().toUpperCase()] ?? forma.trim().toUpperCase()
}

function labelGrupo(g: string): string {
  return GRUPO_LABEL[g] ?? g
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
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

// ─── Margen Terapéutico Estrecho ──────────────────────────────────────────────
const NTI_DCIS = new Set([
  'WARFARINA', 'ACENOCUMAROL', 'DIGOXINA',
  'AMIODARONA', 'FLECAINIDA', 'PROCAINAMIDA', 'QUINIDINA',
  'FENITOINA', 'CARBAMAZEPINA', 'ACIDO VALPROICO', 'VALPROATO',
  'FENOBARBITAL', 'LAMOTRIGINA',
  'CICLOSPORINA', 'TACROLIMUS', 'SIROLIMUS', 'EVEROLIMUS',
  'LITIO', 'CLOZAPINA',
  'TEOFILINA', 'AMINOFILINA',
  'GENTAMICINA', 'AMIKACINA', 'TOBRAMICINA', 'NETILMICINA',
  'VANCOMICINA', 'LEVOTIROXINA', 'METOTREXATO', 'MERCAPTOPURINA',
])

function esNTI(dcis: string[]): boolean {
  return dcis.some(dci => [...NTI_DCIS].some(nti => dci.toUpperCase().includes(nti)))
}

// ─── Badges ───────────────────────────────────────────────────────────────────
function BadgeFormula({ tipo }: { tipo: string }) {
  const cfg = FORMULA_CFG[tipo] ?? { label: tipo, color: 'bg-slate-100 text-slate-600' }
  return <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${cfg.color}`}>{cfg.label}</span>
}

function BadgeNTI() {
  return (
    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-100 text-red-700 border border-red-200 uppercase tracking-wide shrink-0">
      MTE
    </span>
  )
}

function BadgeEstado({ estado }: { estado: string }) {
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
      estado === 'Activo' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'
    }`}>
      {estado}
    </span>
  )
}

function TagDCI({ dci, highlight }: { dci: string; highlight?: boolean }) {
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded-full border ${
      highlight
        ? 'bg-emerald-50 border-emerald-300 text-emerald-700 font-medium'
        : 'bg-slate-100 border-slate-200 text-slate-600'
    }`}>
      {dci}
    </span>
  )
}

// ─── Fila de medicamento (compacta) ──────────────────────────────────────────
function FilaMedicamento({ med, onVer, activa }: {
  med: MedicamentoLive
  onVer: (m: MedicamentoLive) => void
  activa: boolean
}) {
  const nti = esNTI(med.principios_dci)
  const grupo = grupoForma(med.forma_farmaceutica, med.via_administracion)

  return (
    <div
      onClick={() => onVer(med)}
      className={`flex items-center gap-3 px-3 py-2.5 cursor-pointer border-b border-slate-100 last:border-0 transition-colors ${
        activa
          ? 'bg-blue-50 border-l-2 border-l-blue-500'
          : 'hover:bg-slate-50 border-l-2 border-l-transparent'
      }`}
    >
      {/* Columna principal */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          {med.principios_dci.map((d, i) => (
            <span key={i} className="text-xs font-semibold text-slate-800">{d}</span>
          ))}
          {nti && <BadgeNTI />}
          <BadgeFormula tipo={med.tipo_formula} />
        </div>
        <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
          <span className="text-xs text-slate-500 truncate max-w-[160px]">{med.nombre_comercial}</span>
          <span className="text-slate-300">·</span>
          <span className="text-xs text-slate-400 truncate max-w-[120px]">{med.laboratorio}</span>
        </div>
      </div>

      {/* Columna de concentración + presentación + forma */}
      <div className="shrink-0 text-right">
        {med.concentracion_display && (
          <p className="text-xs font-mono font-semibold text-slate-700 truncate max-w-[130px]"
             title={med.presentacion ? `${med.concentracion_display} · ${med.presentacion}` : med.concentracion_display}>
            {med.concentracion_display}
            {med.presentacion && (
              <span className="text-slate-400 font-normal"> · {med.presentacion}</span>
            )}
          </p>
        )}
        <div className="flex items-center justify-end gap-1 mt-0.5">
          <span className="text-[10px] text-slate-400">{labelGrupo(grupo)}</span>
          <BadgeEstado estado={med.estado_cum} />
        </div>
      </div>
    </div>
  )
}

// ─── Panel de alternativas ────────────────────────────────────────────────────
function PanelAlternativas({ medicamento, alternativas, cargando, error }: {
  medicamento: MedicamentoLive
  alternativas: AlternativaLive[]
  cargando: boolean
  error: string
}) {
  const inyectable  = esInyectable(medicamento)
  const esMedNTI    = esNTI(medicamento.principios_dci)
  const [terapExpanded, setTerapExpanded] = useState(false)

  const sustitutos          = useMemo(() => alternativas.filter(a => a.tipo === 'SUSTITUTO_DIRECTO'),              [alternativas])
  const distCantidad        = useMemo(() => alternativas.filter(a => a.tipo === 'MISMA_CONC_DIFERENTE_CANTIDAD'), [alternativas])
  const distForma           = useMemo(() => alternativas.filter(a => a.tipo === 'MISMA_CONC_DIFERENTE_FORMA'),    [alternativas])
  const distConcentracion   = useMemo(() => alternativas.filter(a => a.tipo === 'DIFERENTE_CONCENTRACION'),       [alternativas])
  const terapeuticas        = useMemo(() => alternativas.filter(a => TIPOS_TERAPEUTICOS.includes(a.tipo)),        [alternativas])
  const porTipo      = useMemo(() => TIPOS_TERAPEUTICOS.reduce<Record<string, AlternativaLive[]>>((acc, t) => {
    acc[t] = alternativas.filter(a => a.tipo === t)
    return acc
  }, {}), [alternativas])

  const renderAlternativa = (alt: AlternativaLive, i: number, tipo: string) => {
    const dest = alt.medicamento_destino
    return (
      <div key={i} className="border border-slate-100 rounded-lg p-3 bg-slate-50">
        {dest ? (
          <>
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-1.5 min-w-0">
                <p className="font-medium text-sm text-slate-900 truncate">{dest.nombre_comercial}</p>
                {esNTI(dest.principios_dci) && <BadgeNTI />}
              </div>
              <BadgeFormula tipo={dest.tipo_formula} />
            </div>
            <div className="flex flex-wrap gap-1 my-1.5">
              {dest.principios_dci.map((dci, j) => (
                <TagDCI key={j} dci={dci} highlight={alt.componentes_compartidos.includes(dci)} />
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
                  {dest.presentacion && (
                    <span className="text-slate-400 font-normal"> · {dest.presentacion}</span>
                  )}
                </span>
              )}
              <span>· {dest.laboratorio}</span>
            </div>
          </>
        ) : (
          <p className="text-xs text-slate-500 font-mono">{alt.cum_destino}</p>
        )}
        {alt.componentes_compartidos.length > 0 && tipo !== 'DIFERENTE_CONCENTRACION' && tipo !== 'SUSTITUTO_DIRECTO' && tipo !== 'MISMA_CONC_DIFERENTE_CANTIDAD' && (
          <p className="text-xs text-emerald-600 mt-1.5 font-medium">
            Compartido: {alt.componentes_compartidos.join(', ')}
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
      {/* Header */}
      <div className="bg-slate-50 border-b border-slate-200 px-4 py-3">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="font-semibold text-slate-900 text-sm">{medicamento.nombre_comercial}</p>
          <BadgeFormula tipo={medicamento.tipo_formula} />
          {esMedNTI && <BadgeNTI />}
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
              {medicamento.presentacion && (
                <span className="text-slate-400 font-normal"> · {medicamento.presentacion}</span>
              )}
            </span>
          )}
          {!cargando && alternativas.length > 0 && (
            <span className="text-xs text-slate-400 ml-auto">{alternativas.length} alternativas</span>
          )}
        </div>
      </div>

      <div className="p-4 space-y-4">
        {cargando && (
          <div className="py-8 text-center">
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-xs text-slate-400 mt-2">Consultando API online...</p>
          </div>
        )}
        {error && <p className="text-red-500 text-sm">{error}</p>}
        {!cargando && !error && alternativas.length === 0 && (
          <p className="text-slate-400 text-sm text-center py-6">
            No se encontraron alternativas para este medicamento.
          </p>
        )}

        {/* Banner MTE */}
        {!cargando && esMedNTI && (
          <div className="flex gap-3 bg-red-50 border border-red-200 rounded-lg px-3 py-3">
            <svg className="w-4 h-4 text-red-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
            <div>
              <p className="text-xs font-bold text-red-800 mb-0.5">Margen terapéutico estrecho (MTE)</p>
              <p className="text-xs text-red-700 leading-relaxed">
                Pequeñas diferencias en la dosis o biodisponibilidad pueden causar falla terapéutica o toxicidad. Toda sustitución requiere monitoreo clínico estricto y ajuste individualizado.
              </p>
            </div>
          </div>
        )}

        {!cargando && (
          <>
            {/* Sección 1 — Sustitutos directos */}
            {sustitutos.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                  <p className="text-xs font-bold text-emerald-800 uppercase tracking-wide">
                    Sustitutos directos — {sustitutos.length}
                  </p>
                </div>
                <p className="text-xs text-slate-500 mb-2 pl-4">
                  Mismo PA · misma concentración · misma cantidad · misma forma. Intercambiables directamente.
                </p>
                <div className="border border-emerald-200 rounded-lg overflow-hidden">
                  {sustitutos.map((alt, i) => {
                    const dest = alt.medicamento_destino
                    return (
                      <div key={i} className="flex items-center gap-3 px-3 py-2.5 border-b border-emerald-50 last:border-0 hover:bg-emerald-50 transition-colors">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <p className="text-sm font-medium text-slate-800 truncate">{dest?.nombre_comercial ?? alt.cum_destino}</p>
                            {dest && esNTI(dest.principios_dci) && <BadgeNTI />}
                          </div>
                          {dest?.concentracion_display && (
                            <p className="text-xs font-mono text-slate-500 truncate">
                              {dest.concentracion_display}
                              {dest.presentacion && <span className="text-slate-400"> · {dest.presentacion}</span>}
                            </p>
                          )}
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="text-xs text-slate-600 font-medium truncate max-w-[130px]">{dest?.laboratorio}</p>
                          {dest && <BadgeEstado estado={dest.estado_cum} />}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Sección 2 — Misma concentración, diferente cantidad */}
            {distCantidad.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 rounded-full bg-lime-500 shrink-0" />
                  <p className="text-xs font-bold text-lime-800 uppercase tracking-wide">
                    Misma molécula · misma concentración · diferente cantidad ({distCantidad.length})
                  </p>
                </div>
                <p className="text-xs text-slate-500 mb-2 pl-4">
                  Misma concentración y forma farmacéutica, distinto volumen o número de dosis por envase.
                </p>
                <div className="space-y-2">
                  {distCantidad.map((alt, i) => renderAlternativa(alt, i, 'MISMA_CONC_DIFERENTE_CANTIDAD'))}
                </div>
              </div>
            )}

            {/* Sección 3 — Misma concentración, diferente forma */}
            {distForma.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 rounded-full bg-sky-400 shrink-0" />
                  <p className="text-xs font-bold text-sky-800 uppercase tracking-wide">
                    Misma molécula · misma concentración · diferente forma ({distForma.length})
                  </p>
                </div>
                <p className="text-xs text-slate-500 mb-2 pl-4">
                  Mismo PA y dosis. La forma farmacéutica varía (ej. convencional vs liberación prolongada). Requiere evaluación clínica.
                </p>
                <div className="space-y-2">
                  {distForma.map((alt, i) => renderAlternativa(alt, i, 'MISMA_CONC_DIFERENTE_FORMA'))}
                </div>
              </div>
            )}

            {/* Sección 4 — Diferente concentración */}
            {distConcentracion.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 rounded-full bg-teal-400 shrink-0" />
                  <p className="text-xs font-bold text-teal-800 uppercase tracking-wide">
                    Misma molécula — diferente concentración ({distConcentracion.length})
                  </p>
                </div>
                <p className="text-xs text-slate-500 mb-2 pl-4">
                  Mismo PA y vía. La dosis varía — requiere ajuste de posología por el profesional de salud.
                </p>
                <div className="space-y-2">
                  {distConcentracion.map((alt, i) => renderAlternativa(alt, i, 'DIFERENTE_CONCENTRACION'))}
                </div>
              </div>
            )}

            {/* Sección 4 — Alternativas terapéuticas (colapsable) */}
            {terapeuticas.length > 0 && (
              <div>
                <button
                  onClick={() => setTerapExpanded(v => !v)}
                  className="w-full flex items-center justify-between gap-2 px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg hover:bg-slate-100 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-slate-400 shrink-0" />
                    <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">
                      Alternativas terapéuticas — {terapeuticas.length}
                    </p>
                  </div>
                  <svg className={`w-4 h-4 text-slate-400 transition-transform ${terapExpanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="m19 9-7 7-7-7" />
                  </svg>
                </button>
                <div className="flex gap-2 mt-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5">
                  <svg className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
                  </svg>
                  <p className="text-xs text-amber-800 leading-relaxed">
                    <strong>Para IPS:</strong> toda sustitución por alternativa terapéutica debe ser evaluada y aprobada por el <strong>Comité de Farmacia y Terapéutica institucional</strong> antes de implementarse, conforme a la Resolución 1403 de 2007 del Ministerio de la Protección Social.
                  </p>
                </div>
                {terapExpanded && (
                  <div className="space-y-4 mt-3">
                    {TIPOS_TERAPEUTICOS.map(tipo => {
                      const lista = porTipo[tipo]
                      if (!lista?.length) return null
                      const cfg = ALT_CFG[tipo]
                      return (
                        <div key={tipo}>
                          <div className={`flex items-start gap-2 px-2.5 py-2 rounded-lg border mb-2 ${cfg.color}`}>
                            <div className="flex-1 min-w-0">
                              <p className="text-xs font-semibold">{cfg.label} ({lista.length})</p>
                              <p className="text-xs opacity-70 mt-0.5">{cfg.desc}</p>
                            </div>
                          </div>
                          <div className="space-y-2">
                            {lista.map((alt, i) => renderAlternativa(alt, i, tipo))}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )}

            {sustitutos.length > 0 && distCantidad.length === 0 && distForma.length === 0 && distConcentracion.length === 0 && terapeuticas.length === 0 && (
              <p className="text-xs text-slate-400 text-center pt-1">
                Solo hay sustitutos directos. No se encontraron alternativas en la misma clase ATC.
              </p>
            )}
          </>
        )}

        {/* Disclaimer */}
        {!cargando && alternativas.length > 0 && (
          <div className="pt-3 border-t border-slate-100 flex gap-2">
            <svg className="w-3.5 h-3.5 text-slate-300 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zm-9-3.75h.008v.008H12V8.25z" />
            </svg>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              Datos en tiempo real del <strong>CUM-INVIMA</strong> vía datos.gov.co. <strong>No reemplazan el criterio clínico ni farmacéutico.</strong> Sustitutos directos: pueden dispensarse bajo protocolo. Alternativas terapéuticas en IPS: requieren aval del <strong>Comité de Farmacia y Terapéutica</strong> (Res. 1403/2007).
            </p>
          </div>
        )}
      </div>
    </div>
  )
}


// ─── Componente principal ─────────────────────────────────────────────────────
export default function BuscadorMedicamentos() {
  const [query, setQuery]             = useState('')
  const [resultados, setResultados]   = useState<MedicamentoLive[]>([])
  const [buscando, setBuscando]       = useState(false)
  const [errorBusq, setErrorBusq]     = useState('')
  const [hasBuscado, setHasBuscado]   = useState(false)

  const [medSeleccionado, setMedSeleccionado] = useState<MedicamentoLive | null>(null)
  const [alternativas, setAlternativas]       = useState<AlternativaLive[]>([])
  const [cargandoAlt, setCargandoAlt]         = useState(false)
  const [errorAlt, setErrorAlt]               = useState('')

  const [filtroGrupo, setFiltroGrupoRaw] = useState<string | null>(null)
  const [filtroConc, setFiltroConc]       = useState<string | null>(null)

  const setFiltroGrupo = (g: string | null) => { setFiltroGrupoRaw(g); setFiltroConc(null) }

  // Conteo de grupos en resultados
  const grupos = useMemo(() => {
    const counts = new Map<string, number>()
    for (const m of resultados) {
      const g = grupoForma(m.forma_farmaceutica, m.via_administracion)
      counts.set(g, (counts.get(g) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1])
  }, [resultados])

  // Concentraciones únicas (del grupo seleccionado o de todos)
  const concentraciones = useMemo(() => {
    const base = filtroGrupo
      ? resultados.filter(m => grupoForma(m.forma_farmaceutica, m.via_administracion) === filtroGrupo)
      : resultados
    const counts = new Map<string, number>()
    for (const m of base) {
      if (m.concentracion_display) counts.set(m.concentracion_display, (counts.get(m.concentracion_display) ?? 0) + 1)
    }
    // Ordenar por valor numérico cuando sea posible
    return [...counts.entries()].sort((a, b) => {
      const na = parseFloat(a[0]), nb = parseFloat(b[0])
      return isNaN(na) || isNaN(nb) ? a[0].localeCompare(b[0]) : na - nb
    })
  }, [resultados, filtroGrupo])

  // Resultados filtrados
  const resultadosFiltrados = useMemo(() => {
    return resultados.filter(m => {
      if (filtroGrupo && grupoForma(m.forma_farmaceutica, m.via_administracion) !== filtroGrupo) return false
      if (filtroConc && m.concentracion_display !== filtroConc) return false
      return true
    })
  }, [resultados, filtroGrupo, filtroConc])

  const hayFiltros = filtroGrupo !== null || filtroConc !== null

  const buscar = async (e: React.FormEvent) => {
    e.preventDefault()
    if (query.trim().length < 2) return
    setBuscando(true)
    setErrorBusq('')
    setMedSeleccionado(null)
    setHasBuscado(true)
    setFiltroGrupo(null)
    try {
      const res = await medicamentosApi.buscar(query.trim(), true, 50)
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

  return (
    <div className="space-y-3">

      {/* Buscador */}
      <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-sm">
        <form onSubmit={buscar} className="flex gap-2">
          <div className="relative flex-1">
            <svg className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607z" />
            </svg>
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Principio activo, nombre comercial o código ATC..."
              className="w-full border border-slate-200 rounded-lg pl-9 pr-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <button
            type="submit"
            disabled={buscando || query.trim().length < 2}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors shrink-0"
          >
            {buscando ? 'Buscando...' : 'Buscar'}
          </button>
        </form>
        {errorBusq && <p className="text-red-500 text-xs mt-2">{errorBusq}</p>}

        {/* Filtros — solo cuando hay resultados */}
        {resultados.length > 0 && !buscando && (
          <div className="mt-3 pt-3 border-t border-slate-100">
            <div className="flex items-center gap-2 flex-wrap">
              <select
                value={filtroGrupo ?? ''}
                onChange={e => setFiltroGrupo(e.target.value || null)}
                className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-blue-400 cursor-pointer"
              >
                <option value="">Todas las formas ({resultados.length})</option>
                {grupos.map(([g, n]) => (
                  <option key={g} value={g}>{labelGrupo(g)} ({n})</option>
                ))}
              </select>

              {concentraciones.length > 1 && (
                <select
                  value={filtroConc ?? ''}
                  onChange={e => setFiltroConc(e.target.value || null)}
                  className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-blue-400 cursor-pointer"
                >
                  <option value="">Todas las concentraciones</option>
                  {concentraciones.map(([c, n]) => (
                    <option key={c} value={c}>{c}{n > 1 ? ` (${n})` : ''}</option>
                  ))}
                </select>
              )}

              {hayFiltros && (
                <button
                  onClick={() => setFiltroGrupo(null)}
                  className="text-xs text-slate-400 hover:text-red-500 transition-colors px-1"
                  title="Limpiar filtros"
                >
                  × limpiar
                </button>
              )}

              <span className="text-xs text-slate-400 ml-auto">
                {hayFiltros
                  ? <>{resultadosFiltrados.length} <span className="text-slate-300">de {resultados.length}</span></>
                  : resultados.length
                } resultados
                {medSeleccionado && (
                  <span className="ml-2 text-blue-500">· {medSeleccionado.nombre_comercial}</span>
                )}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Guía de uso — visible antes de la primera búsqueda */}
      {!hasBuscado && (
        <div className="space-y-3">

          {/* Pasos */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-4">Cómo usar esta herramienta</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {[
                {
                  n: '1',
                  title: 'Busca el medicamento',
                  body: 'Escribe el principio activo (DCI), el nombre comercial o el código ATC. La búsqueda consulta los 65 000+ registros del CUM-INVIMA en tiempo real.',
                  icon: (
                    <svg className="w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607z" />
                    </svg>
                  ),
                },
                {
                  n: '2',
                  title: 'Filtra la presentación',
                  body: 'Si hay varias formas farmacéuticas (tableta, inyectable, jarabe…) o concentraciones, usa los filtros desplegables para quedarte solo con la presentación que te interesa.',
                  icon: (
                    <svg className="w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3c2.755 0 5.455.232 8.083.678.533.09.917.556.917 1.096v1.044a2.25 2.25 0 0 1-.659 1.591L15 12.75v6.177a.75.75 0 0 1-.448.686l-3 1.5a.75.75 0 0 1-1.052-.686V12.75L4.659 7.409A2.25 2.25 0 0 1 4 5.818V4.774c0-.54.384-1.006.917-1.096A48.32 48.32 0 0 1 12 3z" />
                    </svg>
                  ),
                },
                {
                  n: '3',
                  title: 'Selecciona y consulta alternativas',
                  body: 'Haz clic en cualquier resultado para ver sus alternativas ordenadas por grado de intercambiabilidad: desde sustitutos directos hasta alternativas terapéuticas de la misma clase ATC.',
                  icon: (
                    <svg className="w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15.042 21.672 13.684 16.6m0 0-2.51 2.225.569-9.47 5.227 7.917-3.286-.672Zm-7.518-.267A8.25 8.25 0 1 1 20.25 10.5M8.288 14.212A5.25 5.25 0 1 1 17.25 10.5" />
                    </svg>
                  ),
                },
              ].map(({ n, title, body, icon }) => (
                <div key={n} className="flex gap-3">
                  <div className="w-7 h-7 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
                    {n}
                  </div>
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      {icon}
                      <p className="text-sm font-semibold text-slate-800">{title}</p>
                    </div>
                    <p className="text-xs text-slate-500 leading-relaxed">{body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Niveles de alternativas */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Niveles de alternativas</p>
            <div className="space-y-2">
              <div className="flex gap-3 items-start p-3 rounded-lg border border-emerald-200 bg-emerald-50">
                <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shrink-0 mt-1" />
                <div>
                  <p className="text-xs font-bold text-emerald-800">Sustituto directo</p>
                  <p className="text-xs text-emerald-700 mt-0.5">
                    Mismo principio activo · misma concentración · misma cantidad por envase · misma forma farmacéutica. Solo difiere el titular del registro. Son intercambiables directamente en la dispensación.
                  </p>
                </div>
              </div>
              <div className="flex gap-3 items-start p-3 rounded-lg border border-lime-200 bg-lime-50">
                <div className="w-2.5 h-2.5 rounded-full bg-lime-500 shrink-0 mt-1" />
                <div>
                  <p className="text-xs font-bold text-lime-800">Misma molécula · misma concentración · diferente cantidad</p>
                  <p className="text-xs text-lime-700 mt-0.5">
                    Misma concentración y forma farmacéutica, pero distinto volumen o número de dosis por envase (ej. midazolam 5 mg/mL en ampolla de 3 mL vs 10 mL).
                  </p>
                </div>
              </div>
              <div className="flex gap-3 items-start p-3 rounded-lg border border-sky-200 bg-sky-50">
                <div className="w-2.5 h-2.5 rounded-full bg-sky-400 shrink-0 mt-1" />
                <div>
                  <p className="text-xs font-bold text-sky-800">Misma molécula · misma concentración · diferente forma</p>
                  <p className="text-xs text-sky-700 mt-0.5">
                    Mismo principio activo y dosis, pero distinta forma farmacéutica (ej. tableta convencional vs tableta de liberación prolongada). No son directamente intercambiables — el perfil farmacocinético difiere. Requieren evaluación clínica.
                  </p>
                </div>
              </div>
              <div className="flex gap-3 items-start p-3 rounded-lg border border-teal-200 bg-teal-50">
                <div className="w-2.5 h-2.5 rounded-full bg-teal-400 shrink-0 mt-1" />
                <div>
                  <p className="text-xs font-bold text-teal-800">Misma molécula — diferente concentración</p>
                  <p className="text-xs text-teal-700 mt-0.5">
                    Mismo principio activo y vía de administración, pero distinta dosis. Requieren ajuste de posología por parte del profesional de salud.
                  </p>
                </div>
              </div>
              <div className="flex gap-3 items-start p-3 rounded-lg border border-slate-200 bg-slate-50">
                <div className="w-2.5 h-2.5 rounded-full bg-slate-400 shrink-0 mt-1" />
                <div>
                  <p className="text-xs font-bold text-slate-700">Alternativas terapéuticas</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Misma clase farmacológica según la clasificación ATC. Pueden ser la misma molécula en forma diferente, una sal distinta del mismo compuesto, o una molécula distinta con efecto clínico similar. <strong className="text-slate-600">Para IPS:</strong> toda sustitución en esta categoría debe ser evaluada y aprobada por el Comité de Farmacia y Terapéutica institucional (Res. 1403/2007).
                  </p>
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {[
                      { color: 'bg-blue-100 text-blue-800 border-blue-200',       label: 'Equivalente exacto',        hint: 'misma ATC-7, distinta sal/éster' },
                      { color: 'bg-indigo-100 text-indigo-800 border-indigo-200', label: 'Equivalente clase ATC',     hint: 'misma ATC-5, molécula distinta' },
                      { color: 'bg-purple-100 text-purple-800 border-purple-200', label: 'Componente compartido',     hint: 'combinado con al menos un PA en común' },
                      { color: 'bg-amber-100 text-amber-800 border-amber-200',    label: 'Diferente vía/forma',       hint: 'oral vs inyectable, etc.' },
                    ].map(({ color, label, hint }) => (
                      <span key={label} className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${color}`} title={hint}>
                        {label}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Indicadores */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Indicadores en los resultados</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
              <div className="flex items-start gap-2">
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-100 text-red-700 border border-red-200 shrink-0 mt-0.5">MTE</span>
                <p className="text-xs text-slate-500 leading-relaxed">
                  <strong className="text-slate-700">Margen Terapéutico Estrecho.</strong> Pequeñas diferencias de dosis o biodisponibilidad pueden causar falla terapéutica o toxicidad. Toda sustitución requiere monitoreo clínico estricto (ej. warfarina, digoxina, ciclosporina, litio).
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 shrink-0 mt-0.5">Mono</span>
                <p className="text-xs text-slate-500 leading-relaxed">
                  <strong className="text-slate-700">Tipo de fórmula:</strong> Mono = un solo principio activo · Bi = dos · Tri = tres · Tetra = cuatro o más. Útil para identificar combinaciones fijas.
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0 mt-1" />
                <p className="text-xs text-slate-500 leading-relaxed">
                  <strong className="text-slate-700">Estado CUM Activo/Inactivo:</strong> refleja el estado actual del registro en el CUM-INVIMA. Un registro Inactivo no significa necesariamente desabastecimiento, pero es una señal de alerta.
                </p>
              </div>
              <div className="flex items-start gap-2">
                <svg className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 0 0 5.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 6h.008v.008H6V6z" />
                </svg>
                <p className="text-xs text-slate-500 leading-relaxed">
                  <strong className="text-slate-700">DCI resaltado en verde</strong> en el panel de alternativas indica los principios activos compartidos entre el medicamento consultado y la alternativa.
                </p>
              </div>
            </div>
            <p className="text-[11px] text-slate-300 mt-4 pt-3 border-t border-slate-100">
              Fuente: Código Único de Medicamentos (CUM) · INVIMA · datos.gov.co — actualización en tiempo real con cada consulta.
            </p>
          </div>

        </div>
      )}

      {/* Grid resultados + panel */}
      {hasBuscado && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">

          {/* Lista de resultados */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            {buscando && (
              <div className="py-12 text-center">
                <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" />
                <p className="text-xs text-slate-400 mt-2">Consultando datos.gov.co...</p>
              </div>
            )}
            {!buscando && resultadosFiltrados.length === 0 && (
              <div className="py-10 text-center px-4">
                <p className="text-sm text-slate-500">
                  {hayFiltros
                    ? 'Ningún resultado coincide con los filtros aplicados.'
                    : `Sin resultados para "${query}"`
                  }
                </p>
                {hayFiltros && (
                  <button onClick={() => setFiltroGrupo(null)} className="text-xs text-blue-600 mt-2 underline">
                    Limpiar filtros
                  </button>
                )}
              </div>
            )}
            {!buscando && resultadosFiltrados.length > 0 && (
              <div className="max-h-[70vh] overflow-y-auto">
                {resultadosFiltrados.map(med => (
                  <FilaMedicamento
                    key={med.cum_id}
                    med={med}
                    onVer={verAlternativas}
                    activa={medSeleccionado?.cum_id === med.cum_id}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Panel alternativas */}
          {medSeleccionado ? (
            <div className="max-h-[70vh] overflow-y-auto">
              <PanelAlternativas
                medicamento={medSeleccionado}
                alternativas={alternativas}
                cargando={cargandoAlt}
                error={errorAlt}
              />
            </div>
          ) : (
            <div className="hidden lg:flex bg-white border border-dashed border-slate-300 rounded-xl items-center justify-center py-16 text-center">
              <div>
                <p className="text-sm text-slate-400">Selecciona un medicamento</p>
                <p className="text-xs text-slate-300 mt-1">para ver sus sustitutos y alternativas</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
