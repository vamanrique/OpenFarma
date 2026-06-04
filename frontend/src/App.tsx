import { useState } from 'react'
import BuscadorMedicamentos from './components/BuscadorMedicamentos'
import MapaRiesgo from './components/MapaRiesgo'
import PanelModelo from './components/PanelModelo'
import FormularioReporte from './components/FormularioReporte'

type Tab = 'busqueda' | 'mapa' | 'modelo' | 'reportes'

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'busqueda', label: 'Consulta',            icon: '💊' },
  { id: 'mapa',    label: 'Mapa de Riesgo',       icon: '🗺️' },
  { id: 'modelo',  label: 'Modelo Predictivo',    icon: '🤖' },
  { id: 'reportes',label: 'Reportar',             icon: '⚠️' },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('busqueda')

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-blue-700 text-white shadow-md">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="text-2xl">💊</div>
            <div>
              <h1 className="text-xl font-bold leading-tight">FarmaVigia</h1>
              <p className="text-blue-200 text-xs">
                Alternativas farmacológicas · Predicción de desabastecimiento · Colombia
              </p>
            </div>
          </div>
          <div className="hidden md:flex items-center gap-2 text-xs text-blue-300">
            <span className="w-2 h-2 bg-green-400 rounded-full inline-block"></span>
            API datos.gov.co · Live
          </div>
        </div>

        <nav className="max-w-6xl mx-auto px-4 flex gap-1">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors ${
                tab === t.id
                  ? 'bg-white text-blue-700'
                  : 'text-blue-100 hover:bg-blue-600'
              }`}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        {tab === 'busqueda' && (
          <section>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-800">
                Consulta de Alternativas Farmacológicas
              </h2>
              <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded">
                Fuente: CUM · INVIMA · datos.gov.co
              </span>
            </div>
            <BuscadorMedicamentos />
          </section>
        )}

        {tab === 'mapa' && (
          <section>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-800">
                Mapa de Riesgo de Desabastecimiento por Región
              </h2>
              <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded">
                33 departamentos · Colombia
              </span>
            </div>
            <MapaRiesgo />
          </section>
        )}

        {tab === 'modelo' && (
          <section>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-800">
                Modelo Predictivo de Desabastecimiento
              </h2>
              <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded font-medium">
                Random Forest · ROC-AUC 0.79
              </span>
            </div>
            <PanelModelo />
          </section>
        )}

        {tab === 'reportes' && (
          <section>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-800">
                Reportar No Disponibilidad
              </h2>
              <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded">
                Datos colaborativos · Colombia
              </span>
            </div>
            <FormularioReporte />
          </section>
        )}
      </main>

      <footer className="text-center text-xs text-gray-400 py-6 border-t mt-8">
        FarmaVigia · Concurso Datos al Ecosistema 2026 · datos.gov.co · INVIMA
      </footer>
    </div>
  )
}
