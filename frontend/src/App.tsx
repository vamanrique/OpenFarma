import { useState, Fragment } from 'react'
import BuscadorMedicamentos from './components/BuscadorMedicamentos'
import PanelModelo from './components/PanelModelo'
import FormularioReporte from './components/FormularioReporte'

type Tab = 'busqueda' | 'modelo' | 'reportes'

const TABS: {
  id: Tab
  label: string
  short: string
  icon: React.ReactElement
  meta: string
  badge?: string
  secondary?: boolean
}[] = [
  {
    id: 'busqueda',
    label: 'Alternativas farmacológicas',
    short: 'Consulta',
    icon: (
      <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607z" />
      </svg>
    ),
    meta: '65,420 medicamentos CUM · tiempo real',
  },
  {
    id: 'modelo',
    label: 'Modelo predictivo',
    short: 'Modelo',
    secondary: true,
    icon: (
      <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75zm9.75-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.625c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.25zm9.75-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V20.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V3.375z" />
      </svg>
    ),
    meta: 'Random Forest · ROC-AUC 0.87',
    badge: 'ML',
  },
  {
    id: 'reportes',
    label: 'Reportar no disponibilidad',
    short: 'Reportar',
    icon: (
      <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 3v1.5M3 21v-6m0 0 2.77-.693a9 9 0 0 1 6.208.682l.108.054a9 9 0 0 0 6.086.71l3.114-.732a48.524 48.524 0 0 1-.005-10.499l-3.11.732a9 9 0 0 1-6.085-.711l-.108-.054a9 9 0 0 0-6.208-.682L3 4.5M3 15V4.5" />
      </svg>
    ),
    meta: 'Datos colaborativos · alimenta el modelo',
  },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('busqueda')

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">

      {/* Header de marca */}
      <header className="bg-gradient-to-r from-blue-950 via-blue-900 to-slate-900 text-white shadow-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">

          {/* Logo + nombre */}
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center shrink-0 shadow-sm ring-1 ring-white/10">
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-[15px] tracking-tight text-white">OpenFarma</span>
                <span className="hidden sm:inline text-xs font-medium px-1.5 py-0.5 rounded bg-blue-800/60 text-blue-200 border border-blue-700/40">
                  Colombia
                </span>
              </div>
              <p className="text-xs text-blue-300/70 leading-none mt-0.5">
                Alternativas farmacológicas · predicción IA
              </p>
            </div>
          </div>

          {/* Indicador API vivo */}
          <div className="flex items-center gap-2 text-xs">
            <div className="flex items-center gap-1.5 bg-white/5 border border-white/10 rounded-full px-2.5 py-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-slate-300 text-xs">INVIMA · datos.gov.co</span>
            </div>
          </div>
        </div>
      </header>

      {/* Navegación por pestañas */}
      <div className="bg-white border-b border-slate-200 sticky top-0 z-10 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <nav className="flex -mb-px overflow-x-auto scrollbar-none" role="tablist" aria-label="Secciones de FarmaVigia">
            {TABS.map((t) => (
              <Fragment key={t.id}>
                <button
                  onClick={() => setTab(t.id)}
                  role="tab"
                  aria-selected={tab === t.id}
                  aria-label={t.label}
                  className={`relative flex items-center gap-2 px-4 py-3.5 text-sm font-medium border-b-2 whitespace-nowrap transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-inset ${
                    tab === t.id
                      ? 'border-blue-600 text-blue-600'
                      : 'border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300'
                  }`}
                >
                  {t.icon}
                  <span className="hidden md:inline">{t.label}</span>
                  <span className="md:hidden">{t.short}</span>
                  {t.badge && (
                    <span className="hidden sm:inline text-xs font-bold px-1 py-0.5 rounded bg-violet-100 text-violet-600 leading-none">
                      {t.badge}
                    </span>
                  )}
                </button>
              </Fragment>
            ))}
          </nav>
        </div>
      </div>

      {/* Contenido principal */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 py-4">
        {tab === 'busqueda' && <BuscadorMedicamentos />}
        {tab === 'modelo'   && <PanelModelo />}
        {tab === 'reportes' && <FormularioReporte />}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center">
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
            </div>
            <span className="text-xs text-slate-500 font-medium">OpenFarma</span>
            <span className="text-slate-300 text-xs">·</span>
            <span className="text-xs text-slate-400">Concurso Datos al Ecosistema 2026</span>
          </div>
          <span className="text-xs text-slate-400">Colombia</span>
        </div>
      </footer>

    </div>
  )
}
