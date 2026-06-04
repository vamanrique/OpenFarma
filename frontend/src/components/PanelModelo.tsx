import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface ModeloInfo {
  roc_auc: number
  avg_precision: number
  n_train: number
  tasa_positivos: number
  importancia_features: { feature: string; importancia: number }[]
}

const FEATURE_LABELS: Record<string, string> = {
  num_presentaciones_activas: 'Presentaciones activas',
  tasa_inactivacion_atc5: 'Tasa inactivación ATC',
  busquedas_norm: 'Búsquedas recientes',
  reportes_norm: 'Reportes no disponibilidad',
  num_competidores: 'Nro. competidores',
  grupo_atc_enc: 'Grupo ATC anatómico',
  tipo_formula_num: 'Complejidad fórmula',
  es_combinado: 'Es combinado',
  tiene_alternativas: 'Tiene alternativas',
  monopolio: 'Monopolio de mercado',
}

const BAR_COLORS = ['#1d4ed8', '#2563eb', '#3b82f6', '#60a5fa', '#93c5fd', '#bfdbfe', '#dbeafe', '#eff6ff', '#f0f9ff', '#f8fafc']

export default function PanelModelo() {
  const [info, setInfo] = useState<ModeloInfo | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/api/v1/predicciones/modelo/info')
      .then(r => r.json())
      .then(setInfo)
      .catch(() => setError('Modelo no disponible'))
  }, [])

  if (error) return (
    <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 text-yellow-700 text-sm">
      {error}. Ejecuta el entrenamiento primero.
    </div>
  )
  if (!info) return <p className="text-gray-400 text-sm">Cargando info del modelo...</p>

  const chartData = info.importancia_features.map(f => ({
    name: FEATURE_LABELS[f.feature] ?? f.feature,
    valor: +(f.importancia * 100).toFixed(1),
  }))

  const aucColor = info.roc_auc >= 0.8 ? 'text-green-600' : info.roc_auc >= 0.7 ? 'text-yellow-600' : 'text-red-600'

  return (
    <div className="space-y-6">
      {/* Métricas */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'ROC-AUC', value: info.roc_auc.toFixed(3), color: aucColor, desc: '≥0.8 = excelente' },
          { label: 'Avg Precision', value: info.avg_precision.toFixed(3), color: 'text-blue-600', desc: 'Precisión media' },
          { label: 'Muestras train', value: info.n_train.toLocaleString('es-CO'), color: 'text-gray-700', desc: 'Registros CUM' },
          { label: 'Tasa positivos', value: `${(info.tasa_positivos * 100).toFixed(1)}%`, color: 'text-orange-600', desc: 'Vigente + inactivo' },
        ].map(m => (
          <div key={m.label} className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
            <p className="text-xs text-gray-400 mb-1">{m.label}</p>
            <p className={`text-2xl font-bold ${m.color}`}>{m.value}</p>
            <p className="text-xs text-gray-400 mt-1">{m.desc}</p>
          </div>
        ))}
      </div>

      {/* Importancia de features */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
        <h3 className="font-semibold text-gray-800 mb-4 text-sm">
          Importancia de variables en el modelo (Random Forest)
        </h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 24 }}>
            <XAxis type="number" tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="name" width={190} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => [`${v}%`, 'Importancia']} />
            <Bar dataKey="valor" radius={[0, 4, 4, 0]}>
              {chartData.map((_, i) => <Cell key={i} fill={BAR_COLORS[i] ?? '#3b82f6'} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Explicación del modelo */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm text-blue-800 space-y-2">
        <p className="font-semibold">¿Cómo funciona el modelo?</p>
        <p>
          Clasifica cada medicamento como <em>en riesgo de desabastecimiento</em> usando 10 variables
          extraídas del CUM oficial (INVIMA). El target de entrenamiento son los{' '}
          <strong>35,600 medicamentos con registro vigente pero presentación inactiva</strong>{' '}
          — el patrón más consistente de desabastecimiento en el dataset.
        </p>
        <p>
          Las señales colaborativas (búsquedas y reportes por región) actualmente son simuladas.
          Al crecer con datos reales de usuarios e IPS, el recall mejorará significativamente.
        </p>
      </div>
    </div>
  )
}
