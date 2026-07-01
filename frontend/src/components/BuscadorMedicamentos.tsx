import { useState, useMemo } from 'react'
import { medicamentosApi, type MedicamentoLive, type AlternativaLive, type GruposEquivalencia, type GrupoDetalle } from '../api/client'

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
  'EQUIVALENTE_CLASE', 'COMPONENTE_COMPARTIDO',
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
  'SUSPENSION': 'LIQUIDO_ORAL', 'SUSPENSIONES': 'LIQUIDO_ORAL',
  'SUSPENSION ORAL RECONSTITUIDA': 'LIQUIDO_ORAL', 'EMULSION ORAL': 'LIQUIDO_ORAL',
  'SOLUCION PARA ADMINISTRACION ORAL': 'LIQUIDO_ORAL',
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
  if (VIA_A_GRUPO[viaU]) return VIA_A_GRUPO[viaU]

  const f = forma.trim().toUpperCase()
  if (FORMA_A_GRUPO[f]) return FORMA_A_GRUPO[f]

  // Matching por palabras clave en orden de prioridad (específico → general).
  // Formas con calificador de vía/sitio primero, para que "UNGUENTO OFTALMICO"
  // vaya a OFTALMICO y no a TOPICO.
  if (/OFTALM/.test(f))                                                           return 'OFTALMICO'
  if (/VAGINAL/.test(f))                                                           return 'VAGINAL'
  if (/RECTAL|SUPOSITORIO/.test(f))                                                return 'RECTAL'
  if (/\bNASAL\b/.test(f))                                                         return 'NASAL'
  if (/\bOTIC|ÓTICA|OTICA\b/.test(f))                                              return 'OTICO'
  if (/INHALACI|INHALADO|INHALADOR|PULMONAR|NEBULIZACI/.test(f))                   return 'INHALADO'
  if (/PARCHE|TRANSDER/.test(f))                                                    return 'TRANSDERMICO'
  if (/SUBLINGUAL|BUCODISPERS/.test(f))                                             return 'SUBLINGUAL'
  if (/LIBERACI.N (PROLONGADA|CONTROLADA|MODIFICADA|SOSTENIDA|RETARDADA)|ACCION PROLONGADA/.test(f)) return 'SOLIDO_ORAL_LP'
  if (/LIOFILIZ|POLVO.*(INYECT|RECONSTITUIR.*INYECT)|CONCENTRADO.*PERFUS|EMULSION INYECT|SUSPENSION INYECT/.test(f)) return 'INYECTABLE'
  if (/INYECT|PARENTERAL/.test(f))                                                  return 'INYECTABLE'
  if (/TABLETA|COMPRIMIDO|GRAGEA/.test(f))                                          return 'SOLIDO_ORAL'
  if (/\bCAPSULA\b/.test(f))                                                        return 'SOLIDO_ORAL'
  if (/POLVO PARA (RECONSTITUIR|SUSPENSION)|GRANULADO ORAL|EFERVESCENTE/.test(f))   return 'ORAL_DISPERSABLE'
  if (/JARABE|SOLUCION ORAL|SUSPENSION ORAL|ELIXIR|GOTAS ORAL|EMULSION ORAL/.test(f)) return 'LIQUIDO_ORAL'
  if (/UNGÜENTO|UNGUENTO|POMADA|CREMA|GEL|LOCION|PASTA|EMULSI|ESPUMA/.test(f))     return 'TOPICO'

  return f
}

function labelGrupo(g: string): string {
  return GRUPO_LABEL[g] ?? g
}

function fmtConc(conc: string | null): string {
  if (!conc || conc === 'SIN_CONCENTRACION') return ''
  return ` · ${conc}`
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

function BadgeEstadoReg({ estado_cum, estado_registro, fuente }: {
  estado_cum: string; estado_registro?: string; fuente?: string
}) {
  if (fuente === 'CUM_RENOVACION') {
    const sufijo = estado_cum === 'Activo' ? ' · Activo' : estado_cum ? ` · ${estado_cum}` : ''
    return (
      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded border border-amber-300 bg-amber-50 text-amber-700 whitespace-nowrap shrink-0">
        En renovación{sufijo}
      </span>
    )
  }
  const vigente = (estado_registro ?? '').toLowerCase() === 'vigente'
  const activo  = estado_cum === 'Activo'
  if (vigente && activo) {
    return (
      <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-emerald-100 text-emerald-700 whitespace-nowrap shrink-0">
        Vigente · Activo
      </span>
    )
  }
  if (activo) {
    return (
      <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-emerald-100 text-emerald-700 whitespace-nowrap shrink-0">
        Activo
      </span>
    )
  }
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-red-100 text-red-600 whitespace-nowrap shrink-0">
      {estado_cum || 'Inactivo'}
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

// ─── Panel de grupos de equivalencia ─────────────────────────────────────────
function BadgeEstadoSimple({ estado_cum, fuente }: { estado_cum: string; fuente: string }) {
  if (fuente === 'CUM_RENOVACION') {
    return (
      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded border border-amber-300 bg-amber-50 text-amber-700 whitespace-nowrap shrink-0">
        Renovacion
      </span>
    )
  }
  const activo = estado_cum === 'Activo'
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium whitespace-nowrap shrink-0 ${
      activo ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'
    }`}>
      {activo ? 'Activo' : (estado_cum || 'Inactivo')}
    </span>
  )
}

function GrupoSection({
  titulo,
  subtitulo,
  grupo,
  colorClass,
  defaultOpen = false,
}: {
  titulo: string
  subtitulo?: string
  grupo: GrupoDetalle
  colorClass: string
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={`border rounded-lg overflow-hidden ${colorClass}`}>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2.5 text-left hover:opacity-80 transition-opacity"
      >
        <div className="min-w-0">
          <p className="text-xs font-bold leading-tight truncate">{titulo}</p>
          {subtitulo && <p className="text-[10px] opacity-70 mt-0.5">{subtitulo}</p>}
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <span className="text-[10px] font-semibold opacity-60">{grupo.n_productos} prod.</span>
          <svg
            className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-90' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="m9 18 6-6-6-6" />
          </svg>
        </div>
      </button>
      {open && (
        <div className="border-t border-current border-opacity-10">
          {grupo.productos.map((p, i) => (
            <div key={i} className="flex items-center gap-2 px-3 py-2 border-b border-current border-opacity-5 last:border-0 bg-white bg-opacity-50">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-slate-800 truncate">{p.nombre_comercial}</p>
                {p.laboratorio && (
                  <p className="text-[10px] text-slate-400 truncate mt-0.5">{p.laboratorio}</p>
                )}
              </div>
              <BadgeEstadoSimple estado_cum={p.estado_cum} fuente={p.fuente} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function PanelGrupos({ gruposEq, cargando }: {
  gruposEq: GruposEquivalencia | null
  cargando: boolean
}) {
  if (cargando) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6 text-center">
        <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-xs text-slate-400 mt-2">Cargando grupos...</p>
      </div>
    )
  }

  if (!gruposEq || gruposEq.grupos_fallback) return null

  const { dci, mi_grupo, misma_via, otras_vias } = gruposEq
  const hayGrupos = mi_grupo || misma_via.length > 0 || otras_vias.length > 0
  if (!hayGrupos) return null

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
      {/* Header — redesigned */}
      <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-200">
        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
          GRUPOS CUM · {dci}
        </p>
      </div>

      <div className="p-4 space-y-4">

        {/* Mi grupo: sustitutos directos */}
        {mi_grupo && (
          <div className="space-y-2">
            <p className="text-[10px] font-semibold text-emerald-700 uppercase tracking-wider border-b border-emerald-100 pb-1">
              Este grupo
            </p>
            <GrupoSection
              titulo={`${mi_grupo.grupo_via_label}${fmtConc(mi_grupo.concentracion_norm)}`}
              subtitulo={`${mi_grupo.n_productos} productos con mismo principio activo, via y concentracion`}
              grupo={mi_grupo}
              colorClass="border-emerald-200 bg-emerald-50 text-emerald-800"
              defaultOpen={true}
            />
          </div>
        )}

        {/* Misma via, otras concentraciones */}
        {misma_via.length > 0 && (
          <div className="space-y-2">
            <p className="text-[10px] font-semibold text-blue-700 uppercase tracking-wider border-b border-blue-100 pb-1">
              Misma vía · otras dosis
            </p>
            {misma_via.map(g => (
              <GrupoSection
                key={g.id}
                titulo={`${g.grupo_via_label}${fmtConc(g.concentracion_norm)}`}
                subtitulo={`${g.n_productos} ${g.n_productos === 1 ? 'producto' : 'productos'}`}
                grupo={g}
                colorClass="border-blue-200 bg-blue-50 text-blue-800"
              />
            ))}
          </div>
        )}

        {/* Otras vias */}
        {otras_vias.length > 0 && (
          <div className="space-y-2">
            <p className="text-[10px] font-semibold text-amber-700 uppercase tracking-wider border-b border-amber-100 pb-1">
              Otras vías
            </p>
            {otras_vias.map(g => (
              <GrupoSection
                key={g.id}
                titulo={`${g.grupo_via_label}${fmtConc(g.concentracion_norm)}`}
                subtitulo={`${g.n_productos} ${g.n_productos === 1 ? 'producto' : 'productos'}`}
                grupo={g}
                colorClass="border-amber-200 bg-amber-50 text-amber-800"
              />
            ))}
          </div>
        )}

      </div>
    </div>
  )
}

// ─── Helper components for tier headers ──────────────────────────────────────
function TierHeader({ icon, label, count, color }: {
  icon: React.ReactNode; label: string; count: number
  color: 'emerald' | 'teal' | 'sky' | 'amber' | 'slate'
}) {
  const bg = { emerald:'bg-emerald-100', teal:'bg-teal-100', sky:'bg-sky-100', amber:'bg-amber-100', slate:'bg-slate-100' }[color]
  const iconColor = { emerald:'text-emerald-700', teal:'text-teal-700', sky:'text-sky-600', amber:'text-amber-700', slate:'text-slate-600' }[color]
  const textColor = { emerald:'text-emerald-900', teal:'text-teal-900', sky:'text-sky-900', amber:'text-amber-900', slate:'text-slate-700' }[color]
  const pillColor = { emerald:'bg-emerald-100 text-emerald-700', teal:'bg-teal-100 text-teal-700', sky:'bg-sky-100 text-sky-700', amber:'bg-amber-100 text-amber-700', slate:'bg-slate-100 text-slate-500' }[color]
  const borderColor = { emerald:'border-emerald-100', teal:'border-teal-100', sky:'border-sky-100', amber:'border-amber-100', slate:'border-slate-200' }[color]
  return (
    <div className={`flex items-center gap-2.5 pb-2.5 border-b mb-3 ${borderColor}`}>
      <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${bg}`}>
        <span className={iconColor}>{icon}</span>
      </div>
      <p className={`text-sm font-semibold flex-1 ${textColor}`}>{label}</p>
      <span className={`text-xs font-bold tabular-nums px-2 py-0.5 rounded-full ${pillColor}`}>{count}</span>
    </div>
  )
}

function SubSection({ label, count }: { label: string; count: number }) {
  return (
    <div className="flex items-center gap-1.5 mb-2">
      <span className="text-xs font-semibold text-slate-600">{label}</span>
      <span className="text-[10px] text-slate-400 tabular-nums">({count})</span>
    </div>
  )
}

function CascadeConnector({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-0.5 select-none">
      <div className="flex-1 h-px bg-slate-100" />
      <span className="text-[10px] text-slate-400 font-medium px-2.5 py-1 rounded-full border border-slate-100 bg-slate-50 whitespace-nowrap leading-tight">
        {label ?? 'si no hay disponibilidad ↓'}
      </span>
      <div className="flex-1 h-px bg-slate-100" />
    </div>
  )
}

// ─── Panel de alternativas ────────────────────────────────────────────────────
function PanelAlternativas({ medicamento, grupoMeds, alternativas, cargando, error }: {
  medicamento: MedicamentoLive
  grupoMeds: MedicamentoLive[]
  alternativas: AlternativaLive[]
  cargando: boolean
  error: string
}) {
  const esMedNTI    = grupoMeds.some(m => esNTI(m.principios_dci)) || esNTI(medicamento.principios_dci)
  const [terapExpanded, setTerapExpanded] = useState(false)
  const dcis = medicamento.principios_dci.length > 0
    ? medicamento.principios_dci
    : [...new Set(grupoMeds.flatMap(m => m.principios_dci))]
  const totalSeleccionado = computeTotal(medicamento.concentracion_display || '', medicamento.presentacion || '')

  const sustitutos          = useMemo(() => alternativas.filter(a => a.tipo === 'SUSTITUTO_DIRECTO'),              [alternativas])
  const distCantidad        = useMemo(() => alternativas.filter(a => a.tipo === 'MISMA_CONC_DIFERENTE_CANTIDAD'), [alternativas])
  const distForma           = useMemo(() => alternativas.filter(a => a.tipo === 'MISMA_CONC_DIFERENTE_FORMA'),    [alternativas])
  const distConcentracion   = useMemo(() => alternativas.filter(a => a.tipo === 'DIFERENTE_CONCENTRACION'),       [alternativas])
  const equivalentesExactos = useMemo(() => alternativas.filter(a => a.tipo === 'EQUIVALENTE_EXACTO'),            [alternativas])
  const diferenteVia        = useMemo(() => alternativas.filter(a => a.tipo === 'ALTERNATIVA_DIFERENTE_FORMA'),   [alternativas])
  const terapeuticas        = useMemo(() => alternativas.filter(a => TIPOS_TERAPEUTICOS.includes(a.tipo)),        [alternativas])
  const porTipo      = useMemo(() => TIPOS_TERAPEUTICOS.reduce<Record<string, AlternativaLive[]>>((acc, t) => {
    acc[t] = alternativas.filter(a => a.tipo === t)
    return acc
  }, {}), [alternativas])

  const renderAlternativa = (alt: AlternativaLive, i: number, tipo: string) => {
    const dest = alt.medicamento_destino
    if (!dest) return (
      <div key={i} className="border border-slate-100 rounded-lg px-3 py-2 bg-slate-50">
        <p className="text-xs text-slate-400 font-mono">{alt.cum_destino}</p>
      </div>
    )
    const totalDest = computeTotal(dest.concentracion_display || '', dest.presentacion || '')
    const concDetail = dest.concentracion_display
      ? (dest.presentacion ? `${dest.concentracion_display} · ${dest.presentacion}` : dest.concentracion_display)
      : ''
    const mostrarCompartidos = alt.componentes_compartidos.length > 0
      && !['SUSTITUTO_DIRECTO', 'MISMA_CONC_DIFERENTE_CANTIDAD', 'DIFERENTE_CONCENTRACION'].includes(tipo)
    return (
      <div key={i} className="border border-slate-100 rounded-lg p-3 bg-slate-50 hover:bg-white transition-colors">
        {/* Fila 1: DCIs + fórmula + NTI | total clínico */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-1.5 flex-wrap min-w-0">
            {dest.principios_dci.length > 0
              ? dest.principios_dci.map((dci, j) => (
                  <TagDCI key={j} dci={dci} highlight={alt.componentes_compartidos.includes(dci)} />
                ))
              : <span className="text-xs text-slate-600 font-medium">{dest.nombre_comercial}</span>
            }
            <BadgeFormula tipo={dest.tipo_formula} />
            {esNTI(dest.principios_dci) && <BadgeNTI />}
          </div>
          {totalDest && (
            <span className="shrink-0 text-sm font-bold font-mono text-slate-800 leading-tight">{totalDest.label}</span>
          )}
        </div>
        {/* Fila 2: marca · lab · estado */}
        <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
          <span className="text-xs text-slate-600 font-medium truncate max-w-[160px]">{dest.nombre_comercial}</span>
          <span className="text-slate-300 text-xs">·</span>
          <span className="text-xs text-slate-400 truncate max-w-[130px]">{dest.laboratorio}</span>
          <BadgeEstadoReg estado_cum={dest.estado_cum} estado_registro={dest.estado_registro} fuente={dest.fuente} />
        </div>
        {/* Fila 3: forma + detalle técnico (secundario) */}
        <div className="flex items-center gap-1.5 mt-1 flex-wrap">
          <span className="text-[10px] text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">
            {labelGrupo(grupoForma(dest.forma_farmaceutica, dest.via_administracion))}
          </span>
          {concDetail && (
            <span className="text-[10px] text-slate-400 font-mono">{concDetail}</span>
          )}
        </div>
        {mostrarCompartidos && (
          <p className="text-xs text-emerald-600 mt-1.5 font-medium">
            Compartido: {alt.componentes_compartidos.join(', ')}
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
      {/* Header — redesigned */}
      <div className="px-4 py-3.5 border-b border-slate-200">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5 flex-wrap">
              {dcis.length > 0
                ? dcis.map((dci, i) => <span key={i} className="text-base font-bold text-slate-900 leading-tight">{dci}</span>)
                : <span className="text-sm font-semibold text-slate-500">{medicamento.nombre_comercial}</span>
              }
              <BadgeFormula tipo={medicamento.tipo_formula} />
              {esMedNTI && <BadgeNTI />}
            </div>
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className="text-xs text-slate-500 bg-slate-100 rounded px-2 py-0.5">
                {labelGrupo(grupoForma(medicamento.forma_farmaceutica, medicamento.via_administracion))}
              </span>
              {totalSeleccionado
                ? <span className="text-sm font-bold font-mono text-slate-800">{totalSeleccionado.label}</span>
                : medicamento.concentracion_display
                  ? <span className="text-sm font-bold font-mono text-slate-800">{medicamento.concentracion_display}</span>
                  : null
              }
              {totalSeleccionado && medicamento.concentracion_display && (
                <span className="text-xs text-slate-400 font-mono">
                  {medicamento.concentracion_display}{medicamento.presentacion && ` · ${medicamento.presentacion}`}
                </span>
              )}
            </div>
          </div>
          {!cargando && alternativas.length > 0 && (
            <span className="text-xs text-slate-400 shrink-0 tabular-nums">{alternativas.length} alt.</span>
          )}
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* NTI banner — always shown at top when relevant */}
        {esMedNTI && (
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

        {!cargando && (
          <>
            {/* Tier 1 — Sustitución directa */}
            {(sustitutos.length > 0 || distCantidad.length > 0 || equivalentesExactos.length > 0) && (
              <div className="space-y-3">
                <TierHeader
                  icon={<svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" /></svg>}
                  label="Mismo producto · dispensación directa"
                  count={sustitutos.length + distCantidad.length + equivalentesExactos.length}
                  color="emerald"
                />

                {sustitutos.length > 0 && (
                  <div>
                    <SubSection label="Mismo producto, diferente titular" count={sustitutos.length} />
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
                              {dest && <BadgeEstadoReg estado_cum={dest.estado_cum} estado_registro={dest.estado_registro} fuente={dest.fuente} />}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {distCantidad.length > 0 && (
                  <div>
                    <SubSection label="Misma concentración, diferente tamaño de envase" count={distCantidad.length} />
                    <p className="text-xs text-slate-500 mb-2 pl-4">
                      Misma concentración y forma farmacéutica, distinto volumen o número de dosis por envase.
                    </p>
                    <div className="border border-lime-200 rounded-lg overflow-hidden">
                      {distCantidad.map((alt, i) => {
                        const dest = alt.medicamento_destino
                        if (!dest) return (
                          <div key={i} className="px-3 py-2 border-b border-lime-50 last:border-0 text-xs text-slate-400 font-mono">{alt.cum_destino}</div>
                        )
                        const totalDest = computeTotal(dest.concentracion_display || '', dest.presentacion || '')
                        return (
                          <div key={i} className="flex items-center gap-3 px-3 py-2.5 border-b border-lime-50 last:border-0 hover:bg-lime-50 transition-colors">
                            <div className="shrink-0 text-right min-w-[56px]">
                              {totalDest
                                ? <p className="text-sm font-bold font-mono text-lime-700 leading-tight">{totalDest.label}</p>
                                : <p className="text-xs font-mono text-slate-600">{dest.concentracion_display}</p>
                              }
                              {dest.presentacion && (
                                <p className="text-[10px] text-slate-400 font-mono mt-0.5">{dest.presentacion}</p>
                              )}
                            </div>
                            <div className="w-px self-stretch bg-lime-100 shrink-0" />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5">
                                <p className="text-xs font-medium text-slate-700 truncate">{dest.nombre_comercial}</p>
                                {esNTI(dest.principios_dci) && <BadgeNTI />}
                              </div>
                              <p className="text-[11px] text-slate-400 truncate mt-0.5">{dest.laboratorio}</p>
                            </div>
                            <BadgeEstadoReg estado_cum={dest.estado_cum} estado_registro={dest.estado_registro} fuente={dest.fuente} />
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {equivalentesExactos.length > 0 && (
                  <div>
                    <SubSection label="Equivalente por sal o éster" count={equivalentesExactos.length} />
                    <p className="text-xs text-slate-500 mb-2 pl-4">
                      Distinta sal o éster del mismo compuesto. Clínicamente equivalentes en la mayoría de casos.
                    </p>
                    <div className="space-y-2">
                      {equivalentesExactos.map((alt, i) => renderAlternativa(alt, i, 'EQUIVALENTE_EXACTO'))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Cascade connector 1→2 */}
            {(sustitutos.length > 0 || distCantidad.length > 0 || equivalentesExactos.length > 0) &&
             (distConcentracion.length > 0 || distForma.length > 0 || diferenteVia.length > 0 || terapeuticas.length > 0) && (
              <CascadeConnector label="si no hay disponibilidad del mismo producto" />
            )}

            {/* Tier 2 — Diferente concentración (mismo PA, misma vía/forma) */}
            {distConcentracion.length > 0 && (
              <div className="space-y-3">
                <TierHeader
                  icon={<svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 3v17.25m0 0c-1.472 0-2.882.265-4.185.75M12 20.25c1.472 0 2.882.265 4.185.75M18.75 4.97A48.416 48.416 0 0 0 12 4.5c-2.291 0-4.545.16-6.75.47m13.5 0c1.01.143 2.01.317 3 .52m-3-.52 2.62 10.726c.122.499-.106 1.028-.589 1.202a5.988 5.988 0 0 1-2.031.352 5.988 5.988 0 0 1-2.031-.352c-.483-.174-.711-.703-.589-1.202L18.75 4.97Zm-16.5.52c.99-.203 1.99-.377 3-.52m0 0 2.62 10.726c.122.499-.106 1.028-.589 1.202a5.989 5.989 0 0 1-2.031.352 5.989 5.989 0 0 1-2.031-.352c-.483-.174-.711-.703-.589-1.202L5.25 4.97Z" /></svg>}
                  label="Misma molécula · diferente concentración · ajuste de dosis"
                  count={distConcentracion.length}
                  color="teal"
                />
                <p className="text-xs text-slate-500 mb-2 pl-4">
                  Mismo PA y vía de administración. La dosis varía — requiere ajuste de posología por el profesional de salud.
                </p>
                <div className="border border-teal-200 rounded-lg overflow-hidden">
                  {distConcentracion.map((alt, i) => {
                    const dest = alt.medicamento_destino
                    if (!dest) return (
                      <div key={i} className="px-3 py-2 border-b border-teal-50 last:border-0 text-xs text-slate-400 font-mono">{alt.cum_destino}</div>
                    )
                    const totalDest = computeTotal(dest.concentracion_display || '', dest.presentacion || '')
                    return (
                      <div key={i} className="flex items-center gap-3 px-3 py-2.5 border-b border-teal-50 last:border-0 hover:bg-teal-50 transition-colors">
                        <div className="shrink-0 text-right min-w-[72px]">
                          {totalDest
                            ? <p className="text-sm font-bold font-mono text-teal-700 leading-tight">{totalDest.label}</p>
                            : <p className="text-xs font-mono text-slate-600">{dest.concentracion_display}</p>
                          }
                          {dest.concentracion_display && (
                            <p className="text-[10px] text-slate-400 font-mono mt-0.5">{dest.concentracion_display}</p>
                          )}
                        </div>
                        <div className="w-px self-stretch bg-teal-100 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <p className="text-xs font-medium text-slate-700 truncate">{dest.nombre_comercial}</p>
                            {esNTI(dest.principios_dci) && <BadgeNTI />}
                          </div>
                          <div className="flex items-center gap-1 mt-0.5">
                            <span className="text-[10px] text-slate-400 bg-slate-100 px-1 py-0.5 rounded">
                              {labelGrupo(grupoForma(dest.forma_farmaceutica, dest.via_administracion))}
                            </span>
                            <span className="text-[11px] text-slate-400 truncate">{dest.laboratorio}</span>
                          </div>
                        </div>
                        <BadgeEstadoReg estado_cum={dest.estado_cum} estado_registro={dest.estado_registro} fuente={dest.fuente} />
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Cascade connector 2→3 */}
            {distConcentracion.length > 0 &&
             (distForma.length > 0 || diferenteVia.length > 0 || terapeuticas.length > 0) && (
              <CascadeConnector label="si no hay disponibilidad con ajuste de dosis" />
            )}

            {/* Tier 3 — Diferente forma farmacéutica (misma concentración) */}
            {distForma.length > 0 && (
              <div className="space-y-3">
                <TierHeader
                  icon={<svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714a2.25 2.25 0 0 0 .659 1.591L19.5 14.5M14.25 3.104c.251.023.501.05.75.082M19.5 14.5l-1.688 3.44c-.24.493-.735.82-1.288.82H7.476c-.553 0-1.048-.327-1.288-.82L4.5 14.5m15 0H4.5" /></svg>}
                  label="Misma concentración · diferente forma farmacéutica"
                  count={distForma.length}
                  color="sky"
                />
                <div>
                  <p className="text-xs text-slate-500 mb-2 pl-4">
                    Mismo PA y dosis, pero distinta forma farmacéutica (p.ej. tableta convencional vs liberación prolongada). Requiere evaluación clínica por diferencias farmacocinéticas.
                  </p>
                  <div className="space-y-2">
                    {distForma.map((alt, i) => renderAlternativa(alt, i, 'MISMA_CONC_DIFERENTE_FORMA'))}
                  </div>
                </div>
              </div>
            )}

            {/* Cascade connector 3→4 */}
            {distForma.length > 0 &&
             (diferenteVia.length > 0 || terapeuticas.length > 0) && (
              <CascadeConnector label="si no hay disponibilidad con la misma vía" />
            )}

            {/* Tier 4 — Diferente vía de administración */}
            {diferenteVia.length > 0 && (
              <div className="space-y-3">
                <TierHeader
                  icon={<svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21 3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 3M21 7.5H7.5" /></svg>}
                  label="Misma molécula · diferente vía de administración"
                  count={diferenteVia.length}
                  color="amber"
                />
                <div>
                  <p className="text-xs text-slate-500 mb-2 pl-4">
                    Oral vs. inyectable, tópico vs. sistémico, etc. La biodisponibilidad y la dosificación difieren — requiere evaluación clínica.
                  </p>
                  <div className="space-y-2">
                    {diferenteVia.map((alt, i) => renderAlternativa(alt, i, 'ALTERNATIVA_DIFERENTE_FORMA'))}
                  </div>
                </div>
              </div>
            )}

            {/* Cascade connector 4→5 */}
            {diferenteVia.length > 0 && terapeuticas.length > 0 && (
              <CascadeConnector label="si se requiere una alternativa terapéutica" />
            )}

            {/* Tier 5 — Alternativas terapéuticas · requieren CFT (colapsable) */}
            {terapeuticas.length > 0 && (
              <div>
                <button onClick={() => setTerapExpanded(v => !v)}
                  className="w-full flex items-center gap-2.5 py-2.5 border-b border-slate-200 hover:border-slate-300 transition-colors text-left">
                  <div className="w-6 h-6 rounded-full bg-slate-100 flex items-center justify-center shrink-0">
                    <svg className="w-3.5 h-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 9h16.5m-16.5 6.75h16.5" />
                    </svg>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-700">Alternativas terapéuticas · misma clase ATC</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">Molécula distinta — requieren aval del Comité de Farmacia y Terapéutica</p>
                  </div>
                  <span className="text-xs font-bold tabular-nums px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 mr-1">{terapeuticas.length}</span>
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
                          <SubSection label={cfg.label} count={lista.length} />
                          <p className="text-xs text-slate-400 mb-2">{cfg.desc}</p>
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
          </>
        )}

        {/* Disclaimer */}
        {alternativas.length > 0 && (
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


// ─── Cantidad total por unidad dispensada ────────────────────────────────────
// Convierte (concentración normalizada, presentación) → "15 mg", "50 mg", "600 000 UI", etc.
// Es la unidad clínica que el farmacéutico busca (ampolla de 15 mg, no "5 mg/mL × 3 mL").
function computeTotal(conc: string, pres: string): { label: string; valor: number } | null {
  const fmt = (n: number) =>
    n >= 10_000
      ? n.toLocaleString('es-CO', { maximumFractionDigits: 0 })
      : n % 1 === 0
        ? String(Math.round(n))
        : String(parseFloat(n.toPrecision(3)))

  // Concentración /mL × volumen en mL (inyectable / líquido normalizado)
  const mConc = conc.match(/^(\d+(?:[.,]\d+)?)\s*(mg|mcg|µg|g|UI|IU|meq)\s*\/mL$/i)
  const mVol  = pres.match(/^(\d+(?:[.,]\d+)?)\s*mL$/i)
  if (mConc && mVol) {
    const c = parseFloat(mConc[1].replace(',', '.'))
    const v = parseFloat(mVol[1].replace(',', '.'))
    const total = Math.round(c * v * 1000) / 1000
    const u = /^(UI|IU)$/i.test(mConc[2]) ? 'UI' : mConc[2]
    return { label: `${fmt(total)} ${u}`, valor: total }
  }

  // Inhalador /dosis → mostrar dosis por inhalación (no total del envase)
  const mDosis = conc.match(/^(\d+(?:[.,]\d+)?)\s*(mcg|mg|µg)\s*\/dosis$/i)
  if (mDosis) {
    const c = parseFloat(mDosis[1].replace(',', '.'))
    return { label: `${fmt(c)} ${mDosis[2]}`, valor: c }
  }

  // Ya es total por unidad: "500 mg", "15 mg", "600000 UI", "10 %"
  const mTotal = conc.match(/^(\d+(?:[.,]\d+)?)\s*(mg|mcg|µg|g|UI|IU|meq|%)$/)
  if (mTotal) {
    const v = parseFloat(mTotal[1].replace(',', '.'))
    const u = /^(UI|IU)$/i.test(mTotal[2]) ? 'UI' : mTotal[2]
    return { label: `${fmt(v)} ${u}`, valor: v }
  }

  return null
}

// ─── Normalización y agrupación de DCIs ──────────────────────────────────────
const EXCIPIENT_PREFIXES = [
  'AGUA ', 'ACIDO LACTICO', 'COLOR:', 'CUBIERTA:', 'GELATINA',
  'SOLUCION SORBITO', 'ALMIDO', 'CELULOSA ', 'POLIETILEN', 'POLIVINIL',
  'TALCO', 'ESTEARATO', 'DIOXIDO', 'SACAROSA', 'LACTOSA', 'MANITOL',
  'TITANIO', 'CARBOXIMETIL', 'CROSCARMELOS', 'CROSPOVIDON', 'HIPROMELOSA',
  'MACROGOL', 'POLISORBATO', 'SORBITOL', 'GLICOLATO', 'POVIDONA',
  'STEARATO', 'FOSFATO DE ',
]

function normalizeDCIName(raw: string): string {
  return raw
    .replace(/\s+\d[\d.,]*\s*(mg|mcg|µg|g|UI|IU|mL|meq|%|mmol)(\s*\/[\s\S]*)?$/i, '')
    .replace(/\s+-\s+\w.*$/, '')
    .replace(/^DE\s+/, '')
    // Strip pharmacopoeial specs and physical form descriptors that are not part of the INN
    // "ACICLOVIR POLVO MICRONIZADO USP" → "ACICLOVIR"
    .replace(/\s+(POLVO\s+MICRONIZADO|MICRONIZADO|NANOCRISTALES|LIPOSOMICO|LIPOSOMAL|USP|BP|EP|FCC)\b.*$/i, '')
    .replace(/\s+POLVO\s*$/i, '')
    .trim()
    .toUpperCase()
    .normalize('NFD').replace(/[̀-ͯ]/g, '')  // CODEÍNA → CODEINA
}

function isExcipient(name: string): boolean {
  if (name.length < 3) return true
  return EXCIPIENT_PREFIXES.some(p => name.toUpperCase().startsWith(p)) || name.includes(':')
}

function dciKey(m: MedicamentoLive): string {
  let dcis = m.principios_dci
    .map(normalizeDCIName)
    .filter(d => d.length >= 3 && !isExcipient(d))

  // Fallback: si principios_dci está vacío y concentracion_display contiene
  // una fórmula combinada (empieza con letra, no con número), extraer los DCIs
  if (dcis.length === 0) {
    const c = m.concentracion_display?.trim() ?? ''
    if (c && !/^\d/.test(c)) {
      dcis = c.split('+')
        .map(p => normalizeDCIName(p.trim()))
        .filter(d => d.length >= 3 && !isExcipient(d))
    }
  }

  const unique = [...new Set(dcis)].sort()
  return unique.length > 0 ? unique.join(' + ') : '(sin DCI)'
}

function chipLabel(key: string, maxLen = 38): string {
  return key.length > maxLen ? key.slice(0, maxLen - 1) + '…' : key
}

// ─── Tipos de agrupación ─────────────────────────────────────────────────────
interface PresRow {
  key: string
  forma: string
  totalLabel: string          // "15 mg" — label clínico primario
  totalValor: number          // para ordenar numéricamente
  detalles: string            // "5 mg/mL · 3 mL" — info técnica secundaria
  meds: MedicamentoLive[]     // ordenados: con DCI primero, luego por lab
}
interface FormaBlock { forma: string; total: number; rows: PresRow[] }


// ─── Componente principal ─────────────────────────────────────────────────────
export default function BuscadorMedicamentos() {
  const [query, setQuery]             = useState('')
  const [resultados, setResultados]   = useState<MedicamentoLive[]>([])
  const [buscando, setBuscando]       = useState(false)
  const [errorBusq, setErrorBusq]     = useState('')
  const [hasBuscado, setHasBuscado]   = useState(false)

  const [medSeleccionado, setMedSeleccionado]     = useState<MedicamentoLive | null>(null)
  const [selectedGroupKey, setSelectedGroupKey]   = useState<string | null>(null)
  const [selectedGroupMeds, setSelectedGroupMeds] = useState<MedicamentoLive[]>([])
  const [alternativas, setAlternativas]           = useState<AlternativaLive[]>([])
  const [cargandoAlt, setCargandoAlt]             = useState(false)
  const [errorAlt, setErrorAlt]                   = useState('')
  const [gruposEq, setGruposEq]                   = useState<GruposEquivalencia | null>(null)
  const [cargandoGrupos, setCargandoGrupos]       = useState(false)

  const [filtroDCI, setFiltroDCIRaw]     = useState<string | null>(null)
  const [showAllDCI, setShowAllDCI]      = useState(false)
  const [filtroGrupo, setFiltroGrupoRaw] = useState<string | null>(null)
  const [filtroConc, setFiltroConc]      = useState<string | null>(null)

  // Cambiar DCI limpia forma y conc; cambiar forma limpia solo conc
  const setFiltroDCI   = (d: string | null) => { setFiltroDCIRaw(d); setFiltroGrupoRaw(null); setFiltroConc(null) }
  const setFiltroGrupo = (g: string | null) => { setFiltroGrupoRaw(g); setFiltroConc(null) }

  // Combos únicos de DCI (para chips de filtro)
  const dciCombos = useMemo(() => {
    const counts = new Map<string, number>()
    for (const m of resultados) {
      const k = dciKey(m)
      counts.set(k, (counts.get(k) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1])
  }, [resultados])

  // Resultados filtrados solo por DCI (base para tipo, forma y conc)
  const resultadosPorDCI = useMemo(() =>
    filtroDCI ? resultados.filter(m => dciKey(m) === filtroDCI) : resultados
  , [resultados, filtroDCI])

  // Conteo de formas — restringido al DCI seleccionado
  const grupos = useMemo(() => {
    const counts = new Map<string, number>()
    for (const m of resultadosPorDCI) {
      const g = grupoForma(m.forma_farmaceutica, m.via_administracion)
      counts.set(g, (counts.get(g) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1])
  }, [resultadosPorDCI])

  // Concentraciones únicas reales (solo valores numéricos) — restringidas a DCI + forma
  const concentraciones = useMemo(() => {
    const base = filtroGrupo
      ? resultadosPorDCI.filter(m => grupoForma(m.forma_farmaceutica, m.via_administracion) === filtroGrupo)
      : resultadosPorDCI
    const counts = new Map<string, number>()
    for (const m of base) {
      const c = m.concentracion_display
      if (c && /^\d/.test(c.trim())) counts.set(c, (counts.get(c) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => {
      const na = parseFloat(a[0]), nb = parseFloat(b[0])
      return isNaN(na) || isNaN(nb) ? a[0].localeCompare(b[0]) : na - nb
    })
  }, [resultadosPorDCI, filtroGrupo])

  // Resultados filtrados: PA → forma/vía → concentración
  const resultadosFiltrados = useMemo(() => {
    return resultados.filter(m => {
      if (filtroDCI  && dciKey(m) !== filtroDCI) return false
      if (filtroGrupo && grupoForma(m.forma_farmaceutica, m.via_administracion) !== filtroGrupo) return false
      if (filtroConc  && m.concentracion_display !== filtroConc) return false
      return true
    })
  }, [resultados, filtroDCI, filtroGrupo, filtroConc])

  const hayFiltros = filtroDCI !== null || filtroGrupo !== null || filtroConc !== null

  // Estructura: forma farmacéutica → cantidad total por unidad dispensada (15 mg, 5 mg, 50 mg)
  const agrupados = useMemo((): FormaBlock[] => {
    // Paso 1: agrupar por (forma, totalLabel)
    const rowMap = new Map<string, { totalLabel: string; totalValor: number; detalles: string; meds: MedicamentoLive[] }>()
    for (const med of resultadosFiltrados) {
      const forma  = grupoForma(med.forma_farmaceutica, med.via_administracion)
      const pres   = med.presentacion || ''
      // Normalizar componentes "+": "B+A" → "A+B" para que el orden del CUM no rompa el agrupamiento
      const conc = (med.concentracion_display || '').includes('+')
        ? (med.concentracion_display || '').split('+').map(p => p.trim()).sort().join(' + ')
        : (med.concentracion_display || '')
      const t = computeTotal(conc, pres)

      // Si concentracion_display es una fórmula DCI (empieza con letra, no con número),
      // extraer solo los valores numéricos para el label: "CODEINA 30 mg + PARACETAMOL 325 mg" → "30 mg · 325 mg"
      const isComboDCI = conc.length > 0 && !/^\d/.test(conc.trim())
      let totalLabel: string
      let totalValor: number
      let detalles: string
      if (isComboDCI) {
        const nums = conc.match(/\d[\d.,]*\s*(?:mg|mcg|µg|g|UI|IU|mL|meq|%|mmol)/gi) ?? []
        totalLabel = nums.length > 0 ? nums.join(' · ') : '—'
        totalValor = nums.length > 0 ? parseFloat(nums[0]!) : 0
        detalles   = ''
      } else {
        totalLabel = t?.label ?? ([conc, pres].filter(Boolean).join(' · ') || '—')
        totalValor = t?.valor ?? parseFloat(conc) ?? 0
        detalles   = (conc && pres) ? `${conc} · ${pres}` : conc || pres || ''
      }
      // Agrupar por concentración normalizada (no por total clínico calculado).
      // Así, "50 mg/mL" sin presentación y "50 mg/mL · 100 mL" caen en la misma fila.
      // Normalizar tildes para que "CODEÍNA 30 mg" y "CODEINA 30 mg" formen el mismo grupo.
      const concKey = conc.normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase()
      const key = `${forma}\0${concKey}`
      const prev = rowMap.get(key)
      if (prev) {
        prev.meds.push(med)
        // Si el grupo fue creado por un med sin presentación (totalLabel = conc),
        // actualizarlo cuando llega uno con total calculado.
        if (!isComboDCI && t !== null && prev.totalLabel === conc) {
          prev.totalLabel = totalLabel
          prev.totalValor = totalValor
        }
      } else {
        rowMap.set(key, { totalLabel, totalValor, detalles, meds: [med] })
      }
    }

    // Paso 2: ordenar meds dentro de cada fila (DCI conocido primero → laboratorio)
    for (const row of rowMap.values()) {
      row.meds.sort(
        (a, b) => (b.principios_dci.length - a.principios_dci.length) || a.laboratorio.localeCompare(b.laboratorio)
      )
    }

    // Paso 3: construir bloques por forma, ordenados por totalValor asc
    const formaMap = new Map<string, PresRow[]>()
    for (const [key, { totalLabel, totalValor, detalles, meds }] of rowMap) {
      const [forma] = key.split('\0')
      const rows = formaMap.get(forma) ?? []
      rows.push({ key, forma, totalLabel, totalValor, detalles, meds })
      formaMap.set(forma, rows)
    }

    return [...formaMap.entries()]
      .map(([forma, rows]) => ({
        forma,
        total: rows.reduce((s, r) => s + r.meds.length, 0),
        rows: rows.sort((a, b) => a.totalValor - b.totalValor),
      }))
      .sort((a, b) => b.total - a.total)
  }, [resultadosFiltrados])

  const buscar = async (e: React.FormEvent) => {
    e.preventDefault()
    if (query.trim().length < 2) return
    setBuscando(true)
    setErrorBusq('')
    setMedSeleccionado(null)
    setSelectedGroupKey(null)
    setSelectedGroupMeds([])
    setHasBuscado(true)
    setFiltroDCI(null)
    setShowAllDCI(false)
    try {
      const res = await medicamentosApi.buscar(query.trim(), true, 50)
      setResultados(res.data)
    } catch {
      setErrorBusq('Error de conexión. Verifica que el backend esté activo.')
    } finally {
      setBuscando(false)
    }
  }

  const buscarQuery = async (q: string) => {
    setQuery(q)
    if (q.trim().length < 2) return
    setBuscando(true)
    setErrorBusq('')
    setMedSeleccionado(null)
    setSelectedGroupKey(null)
    setSelectedGroupMeds([])
    setHasBuscado(true)
    setFiltroDCI(null)
    setShowAllDCI(false)
    try {
      const res = await medicamentosApi.buscar(q.trim(), true, 50)
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
    setCargandoGrupos(true)
    setGruposEq(null)
    try {
      const res = await medicamentosApi.alternativas(med.cum_id)
      setAlternativas(res.data)
    } catch {
      setErrorAlt('No se pudieron cargar las alternativas.')
    } finally {
      setCargandoAlt(false)
    }
    try {
      const gEq = await medicamentosApi.gruposEquivalencia(med.cum_id)
      setGruposEq(gEq)
    } catch {
      setGruposEq(null)
    } finally {
      setCargandoGrupos(false)
    }
  }

  const seleccionarGrupo = (row: PresRow) => {
    setSelectedGroupKey(row.key)
    setSelectedGroupMeds(row.meds)
    verAlternativas(row.meds[0])
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

        {/* Filtros */}
        {resultados.length > 0 && !buscando && (
          <div className="mt-3 pt-3 border-t border-slate-100 space-y-3">

            {/* ── Filtro 1: Principio activo ── */}
            {dciCombos.length > 1 && (() => {
              const LIMIT = 8
              const visible = showAllDCI ? dciCombos : dciCombos.slice(0, LIMIT)
              const hasMore = dciCombos.length > LIMIT
              return (
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5 select-none">
                    Principio activo
                  </p>
                  <div className="flex flex-wrap gap-1.5 items-center">
                    {visible.map(([k, n]) => {
                      const isMono = !k.includes(' + ')
                      const sel    = filtroDCI === k
                      return (
                        <button
                          key={k}
                          title={k}
                          onClick={() => setFiltroDCI(sel ? null : k)}
                          className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all select-none ${
                            sel
                              ? 'bg-blue-600 text-white border-blue-600 font-semibold shadow-sm'
                              : isMono
                                ? 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100 hover:border-blue-400'
                                : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:border-slate-400'
                          }`}
                        >
                          {isMono && (
                            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${sel ? 'bg-blue-200' : 'bg-blue-400'}`} />
                          )}
                          <span>{chipLabel(k)}</span>
                          <span className={`text-[10px] tabular-nums shrink-0 ${sel ? 'text-blue-200' : 'text-slate-400'}`}>{n}</span>
                        </button>
                      )
                    })}
                    {hasMore && !showAllDCI && (
                      <button
                        onClick={() => setShowAllDCI(true)}
                        className="text-xs text-slate-400 hover:text-blue-600 px-2 py-1 rounded-full border border-dashed border-slate-200 hover:border-blue-300 transition-colors"
                      >
                        +{dciCombos.length - LIMIT} más
                      </button>
                    )}
                    {showAllDCI && dciCombos.length > LIMIT && (
                      <button
                        onClick={() => setShowAllDCI(false)}
                        className="text-xs text-slate-400 hover:text-slate-600 px-2 py-1 transition-colors"
                      >
                        Ver menos
                      </button>
                    )}
                  </div>
                </div>
              )
            })()}

            {/* ── Filtro 2: Forma farmacéutica ── */}
            {grupos.length > 1 && (
              <div>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5 select-none">
                  Forma farmacéutica
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {grupos.map(([g, n]) => {
                    const sel = filtroGrupo === g
                    return (
                      <button key={g} onClick={() => setFiltroGrupo(sel ? null : g)}
                        className={`inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full border transition-all select-none ${
                          sel ? 'bg-slate-800 text-white border-slate-800 font-semibold'
                              : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:border-slate-400'
                        }`}>
                        {labelGrupo(g)}
                        <span className={`text-[10px] tabular-nums ${sel ? 'text-slate-300' : 'text-slate-400'}`}>{n}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {/* ── Filtro 3: Concentración ── */}
            {concentraciones.length > 1 && (
              <div>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5 select-none">
                  Concentración
                </p>
                <div className="flex items-center gap-2 flex-wrap">
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

                  {hayFiltros && (
                    <button
                      onClick={() => setFiltroDCI(null)}
                      className="text-xs text-slate-400 hover:text-red-500 transition-colors px-1"
                      title="Limpiar todos los filtros"
                    >
                      × limpiar
                    </button>
                  )}

                  <span className="text-xs text-slate-400 ml-auto tabular-nums">
                    {hayFiltros
                      ? <>{resultadosFiltrados.length}<span className="text-slate-300"> / {resultados.length}</span></>
                      : resultados.length
                    }
                  </span>
                </div>
              </div>
            )}

            {/* Contador cuando no hay filtro de concentración */}
            {concentraciones.length <= 1 && (
              <div className="flex items-center gap-2">
                {hayFiltros && (
                  <button
                    onClick={() => setFiltroDCI(null)}
                    className="text-xs text-slate-400 hover:text-red-500 transition-colors"
                  >
                    × limpiar filtros
                  </button>
                )}
                <span className="text-xs text-slate-400 ml-auto tabular-nums">
                  {hayFiltros
                    ? <>{resultadosFiltrados.length}<span className="text-slate-300"> / {resultados.length}</span></>
                    : resultados.length
                  }
                </span>
              </div>
            )}

          </div>
        )}
      </div>

      {/* Pre-search — cascada clínica visible de entrada */}
      {!hasBuscado && (
        <div className="space-y-5 pt-2">

          {/* Intro + ejemplos */}
          <div className="text-center px-2">
            <p className="text-[11px] font-bold uppercase tracking-widest text-blue-600 mb-1.5">Buscador de alternativas clínicas</p>
            <h2 className="text-xl font-bold text-slate-900 leading-snug">¿Qué medicamento necesitas?</h2>
            <p className="text-sm text-slate-500 mt-1.5 max-w-lg mx-auto">
              Busca por principio activo (DCI), nombre comercial o código ATC.
              Consulta los <strong className="text-slate-700">65 000+ registros CUM-INVIMA</strong> en tiempo real.
            </p>
            <div className="flex flex-wrap justify-center gap-1.5 mt-3">
              {['paracetamol', 'enalapril', 'metformina', 'amoxicilina', 'omeprazol', 'furosemida', 'losartan', 'vancomicina'].map(ex => (
                <button key={ex} onClick={() => buscarQuery(ex)}
                  className="text-xs px-3 py-1.5 rounded-full border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 hover:border-blue-400 transition-colors">
                  {ex}
                </button>
              ))}
            </div>
          </div>

          {/* Cascada clínica — visible por defecto */}
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
            <div className="px-5 pt-4 pb-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                Orden de preferencia clínica cuando un medicamento no está disponible
              </p>
            </div>
            {/* Pasos horizontal en desktop, vertical en mobile */}
            <div className="px-4 pb-4">
              <div className="hidden sm:flex items-stretch gap-0">
                {/* Paso 1 */}
                <div className="flex-1 rounded-xl border border-emerald-200 bg-emerald-50 p-3.5">
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <span className="text-[10px] font-bold w-4.5 h-4.5 min-w-[18px] min-h-[18px] rounded-full bg-emerald-600 text-white flex items-center justify-center leading-none">1</span>
                    <span className="text-[9px] font-bold uppercase tracking-wide text-emerald-600 bg-emerald-100 px-1.5 py-0.5 rounded">Directo</span>
                  </div>
                  <p className="text-xs font-bold text-emerald-900 leading-snug">Mismo producto</p>
                  <p className="text-[11px] text-emerald-700 mt-1 leading-snug">Distinto titular o tamaño de envase. Intercambiable directamente.</p>
                </div>
                <div className="flex items-center px-1.5 text-slate-300 shrink-0">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" /></svg>
                </div>
                {/* Paso 2 */}
                <div className="flex-1 rounded-xl border border-teal-200 bg-teal-50 p-3.5">
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <span className="text-[10px] font-bold min-w-[18px] min-h-[18px] rounded-full bg-teal-600 text-white flex items-center justify-center leading-none">2</span>
                    <span className="text-[9px] font-bold uppercase tracking-wide text-teal-600 bg-teal-100 px-1.5 py-0.5 rounded">Ajuste dosis</span>
                  </div>
                  <p className="text-xs font-bold text-teal-900 leading-snug">Diferente concentración</p>
                  <p className="text-[11px] text-teal-700 mt-1 leading-snug">Mismo PA y vía. El profesional ajusta la posología.</p>
                </div>
                <div className="flex items-center px-1.5 text-slate-300 shrink-0">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" /></svg>
                </div>
                {/* Paso 3 */}
                <div className="flex-1 rounded-xl border border-sky-200 bg-sky-50 p-3.5">
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <span className="text-[10px] font-bold min-w-[18px] min-h-[18px] rounded-full bg-sky-600 text-white flex items-center justify-center leading-none">3</span>
                    <span className="text-[9px] font-bold uppercase tracking-wide text-sky-600 bg-sky-100 px-1.5 py-0.5 rounded">Eval. clínica</span>
                  </div>
                  <p className="text-xs font-bold text-sky-900 leading-snug">Diferente forma</p>
                  <p className="text-[11px] text-sky-700 mt-1 leading-snug">Misma dosis, distinta forma farmacéutica. Farmacocinética varía.</p>
                </div>
                <div className="flex items-center px-1.5 text-slate-300 shrink-0">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" /></svg>
                </div>
                {/* Paso 4 */}
                <div className="flex-1 rounded-xl border border-amber-200 bg-amber-50 p-3.5">
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <span className="text-[10px] font-bold min-w-[18px] min-h-[18px] rounded-full bg-amber-600 text-white flex items-center justify-center leading-none">4</span>
                    <span className="text-[9px] font-bold uppercase tracking-wide text-amber-600 bg-amber-100 px-1.5 py-0.5 rounded">Eval. clínica</span>
                  </div>
                  <p className="text-xs font-bold text-amber-900 leading-snug">Diferente vía</p>
                  <p className="text-[11px] text-amber-700 mt-1 leading-snug">Oral vs. inyectable, tópico vs. sistémico. Biodisponibilidad varía.</p>
                </div>
                <div className="flex items-center px-1.5 text-slate-300 shrink-0">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" /></svg>
                </div>
                {/* Paso 5 */}
                <div className="flex-1 rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <span className="text-[10px] font-bold min-w-[18px] min-h-[18px] rounded-full bg-slate-500 text-white flex items-center justify-center leading-none">5</span>
                    <span className="text-[9px] font-bold uppercase tracking-wide text-slate-500 bg-slate-200 px-1.5 py-0.5 rounded">CFT</span>
                  </div>
                  <p className="text-xs font-bold text-slate-700 leading-snug">Otra molécula</p>
                  <p className="text-[11px] text-slate-500 mt-1 leading-snug">Misma clase ATC. Requiere aval del Comité de Farmacia y Terapéutica.</p>
                </div>
              </div>

              {/* Mobile: vertical */}
              <div className="sm:hidden space-y-1.5">
                {[
                  { n:'1', tag:'Directo',     label:'Mismo producto',         desc:'Distinto titular o tamaño de envase. Intercambiable directamente.', border:'border-emerald-200 bg-emerald-50', nBg:'bg-emerald-600', tagCl:'text-emerald-600 bg-emerald-100', text:'text-emerald-900', sub:'text-emerald-700' },
                  { n:'2', tag:'Ajuste dosis',label:'Diferente concentración', desc:'Mismo PA y vía. El profesional ajusta la posología.',              border:'border-teal-200 bg-teal-50',     nBg:'bg-teal-600',     tagCl:'text-teal-600 bg-teal-100',     text:'text-teal-900',   sub:'text-teal-700' },
                  { n:'3', tag:'Eval. clínica',label:'Diferente forma',        desc:'Misma dosis, distinta forma farmacéutica. Farmacocinética varía.',  border:'border-sky-200 bg-sky-50',       nBg:'bg-sky-600',       tagCl:'text-sky-600 bg-sky-100',       text:'text-sky-900',    sub:'text-sky-700' },
                  { n:'4', tag:'Eval. clínica',label:'Diferente vía',          desc:'Oral vs. inyectable, tópico vs. sistémico.',                        border:'border-amber-200 bg-amber-50',   nBg:'bg-amber-600',     tagCl:'text-amber-600 bg-amber-100',   text:'text-amber-900',  sub:'text-amber-700' },
                  { n:'5', tag:'CFT',          label:'Otra molécula',          desc:'Misma clase ATC. Requiere aval del Comité de Farmacia y Terapéutica.',border:'border-slate-200 bg-slate-50', nBg:'bg-slate-500',     tagCl:'text-slate-500 bg-slate-200',   text:'text-slate-700',  sub:'text-slate-500' },
                ].map((s, i) => (
                  <div key={s.n}>
                    <div className={`flex items-center gap-3 rounded-xl border p-3 ${s.border}`}>
                      <span className={`text-[10px] font-bold min-w-[20px] min-h-[20px] rounded-full ${s.nBg} text-white flex items-center justify-center shrink-0`}>{s.n}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 mb-0.5">
                          <p className={`text-xs font-bold ${s.text}`}>{s.label}</p>
                          <span className={`text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded ${s.tagCl}`}>{s.tag}</span>
                        </div>
                        <p className={`text-[11px] ${s.sub} leading-snug`}>{s.desc}</p>
                      </div>
                    </div>
                    {i < 4 && (
                      <div className="flex justify-center py-0.5">
                        <svg className="w-3.5 h-3.5 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" /></svg>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Footer de la cascada */}
            <div className="border-t border-slate-100 px-5 py-2.5 bg-slate-50 flex flex-wrap items-center gap-x-4 gap-y-1.5">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-100 text-red-700 border border-red-200">MTE</span>
                <span className="text-[11px] text-slate-500">Margen terapéutico estrecho — monitoreo estricto obligatorio</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">Mono</span>
                <span className="text-[11px] text-slate-500">Mono/Bi/Tri/Tetra = número de principios activos</span>
              </div>
              <span className="text-[11px] text-slate-400 ml-auto">CUM-INVIMA · datos.gov.co</span>
            </div>
          </div>

        </div>
      )}

      {/* Grid resultados + panel */}
      {hasBuscado && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">

          {/* Lista de resultados — agrupada por forma → concentración → presentación */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            {buscando && (
              <div className="py-12 text-center">
                <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" />
                <p className="text-xs text-slate-400 mt-2">Consultando datos.gov.co...</p>
              </div>
            )}
            {!buscando && agrupados.length === 0 && (
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
            {!buscando && agrupados.length > 0 && (
              <div className="max-h-[70vh] overflow-y-auto">
                {/* INN normalizado — banner cuando hay filtro por DCI */}
                {filtroDCI && (
                  <div className="sticky top-0 z-20 px-4 py-2.5 bg-blue-600 border-b border-blue-700 flex items-center gap-2">
                    <span className="text-[10px] font-bold text-blue-300 uppercase tracking-wide shrink-0">DCI</span>
                    <span className="text-sm font-semibold text-white flex-1 min-w-0 truncate">{filtroDCI}</span>
                    <span className="text-xs text-blue-300 font-mono shrink-0">{resultadosFiltrados.length} prod.</span>
                  </div>
                )}
                {agrupados.map(({ forma, total, rows }) => (
                  <div key={forma}>
                    {/* Cabecera de forma farmacéutica */}
                    <div className="px-3 py-2 bg-slate-50 border-b border-slate-200 sticky top-0 z-10 flex items-center justify-between">
                      <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                        {labelGrupo(forma)}
                      </span>
                      <span className="text-[10px] text-slate-400">{total} productos</span>
                    </div>

                    {/* Filas seleccionables por cantidad total */}
                    {rows.map(row => {
                      const sel         = selectedGroupKey === row.key
                      const hasNTI      = row.meds.some(m => esNTI(m.principios_dci))
                      const isRenov     = row.meds.every(m => m.fuente === 'CUM_RENOVACION')
                      const allDcisFilt = [...new Set(
                        row.meds.flatMap(m => m.principios_dci)
                          .map(normalizeDCIName)
                          .filter(d => d.length >= 3 && !isExcipient(d))
                      )]
                      const dcisGrupo   = allDcisFilt.slice(0, 2)
                      const dcisExtra   = Math.max(0, allDcisFilt.length - 2)
                      const tiposDistinct = [...new Set(row.meds.map(m => m.tipo_formula))]
                      const labs = row.meds
                        .slice(0, 2)
                        .map(m => m.laboratorio.split(/[\s(]/)[0])
                        .join(', ')
                      const labsMore = row.meds.length > 2 ? ` +${row.meds.length - 2}` : ''
                      return (
                        <button
                          key={row.key}
                          onClick={() => seleccionarGrupo(row)}
                          className={`w-full flex items-stretch border-b border-slate-100 last:border-0 text-left transition-colors group ${
                            sel ? 'bg-blue-50' : 'hover:bg-slate-50'
                          }`}
                        >
                          {/* Accent bar */}
                          <div className={`w-[3px] shrink-0 transition-colors ${sel ? 'bg-blue-500' : 'bg-transparent group-hover:bg-slate-200'}`} />

                          {/* Dosis — elemento clínico principal */}
                          <div className={`shrink-0 w-[80px] text-right py-3.5 pr-3 pl-2 flex flex-col justify-center ${sel ? 'text-blue-700' : 'text-slate-800'}`}>
                            <p className="text-base font-bold font-mono leading-tight tabular-nums">{row.totalLabel}</p>
                            {row.detalles && (
                              <p className="text-[10px] text-slate-400 font-mono mt-0.5 leading-tight truncate">{row.detalles}</p>
                            )}
                          </div>

                          {/* Divider */}
                          <div className={`w-px my-3 shrink-0 ${sel ? 'bg-blue-200' : 'bg-slate-100'}`} />

                          {/* DCIs + meta */}
                          <div className="flex-1 min-w-0 px-3 py-3 flex flex-col justify-center">
                            <div className="flex items-center gap-1.5 min-w-0">
                              <span className={`text-xs font-semibold truncate ${sel ? 'text-blue-800' : 'text-slate-700'}`}>
                                {dcisGrupo.length > 0
                                  ? dcisGrupo.join(' · ')
                                  : (row.meds[0]?.nombre_comercial ?? '—')}
                              </span>
                              {dcisExtra > 0 && (
                                <span className="text-[10px] text-slate-400 shrink-0">+{dcisExtra}</span>
                              )}
                              {hasNTI && <BadgeNTI />}
                              {tiposDistinct.length === 1 && <BadgeFormula tipo={tiposDistinct[0]} />}
                              {isRenov && (
                                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded border border-amber-300 bg-amber-50 text-amber-700 shrink-0 whitespace-nowrap">
                                  Renovación
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-400 truncate mt-0.5">
                              {row.meds.length === 1 ? '1 producto' : `${row.meds.length} productos`} · {labs}{labsMore}
                            </p>
                          </div>

                          <div className="flex items-center pr-3 shrink-0">
                            <svg className={`w-3.5 h-3.5 ${sel ? 'text-blue-400' : 'text-slate-300'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="m9 18 6-6-6-6" />
                            </svg>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Panel grupos + alternativas */}
          {medSeleccionado ? (
            <div className="max-h-[70vh] overflow-y-auto space-y-3">
              {/* Grupos de equivalencia (se muestra si hay datos en la tabla) */}
              <PanelGrupos gruposEq={gruposEq} cargando={cargandoGrupos} />
              {/* Panel de alternativas clásico (siempre visible) */}
              <PanelAlternativas
                medicamento={medSeleccionado}
                grupoMeds={selectedGroupMeds}
                alternativas={alternativas}
                cargando={cargandoAlt}
                error={errorAlt}
              />
            </div>
          ) : (
            <div className="hidden lg:block bg-white border border-slate-200 rounded-xl overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-100">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Alternativas clínicas</p>
                <p className="text-sm text-slate-500 mt-0.5">Selecciona una presentación de la lista para ver sus alternativas ordenadas por cascada clínica.</p>
              </div>
              <div className="p-4 space-y-1.5">
                {[
                  { n:'1', color:'bg-emerald-500', label:'Sustituto directo', sub:'Mismo producto, distinto titular' },
                  { n:'2', color:'bg-teal-500',    label:'Diferente concentración', sub:'Ajuste de dosis por el clínico' },
                  { n:'3', color:'bg-sky-500',     label:'Diferente forma', sub:'Misma dosis, farmacocinética varía' },
                  { n:'4', color:'bg-amber-500',   label:'Diferente vía', sub:'Oral, inyectable, tópico...' },
                  { n:'5', color:'bg-slate-400',   label:'Otra molécula · misma clase ATC', sub:'Requiere aval CFT' },
                ].map(s => (
                  <div key={s.n} className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg">
                    <span className={`w-4 h-4 rounded-full ${s.color} text-white text-[9px] font-bold flex items-center justify-center shrink-0`}>{s.n}</span>
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-slate-600 leading-tight">{s.label}</p>
                      <p className="text-[10px] text-slate-400 leading-tight">{s.sub}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
