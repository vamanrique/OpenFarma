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
  // Features temporales INVIMA (señal más predictiva)
  invima_sev_actual:        'Severidad INVIMA actual',
  invima_sev_t3_avg:        'Severidad INVIMA (promedio 3 meses)',
  invima_peor_sev_hist:     'Peor historial INVIMA',
  invima_meses_monitoreado: 'Meses en seguimiento INVIMA',
  invima_tendencia:         'Tendencia INVIMA',
  // Features estructurales CUM
  tasa_inactivacion_atc5:   'Tasa inactivación ATC',
  num_competidores:         'Competidores en mercado',
  tiene_alternativas:       'Tiene alternativas',
  monopolio:                'Monopolio de mercado',
  es_combinado:             'Fórmula combinada',
  tipo_formula_num:         'Complejidad de fórmula',
  grupo_atc_enc:            'Grupo ATC anatómico',
  num_presentaciones_activas: 'Presentaciones activas',
  busquedas_norm:           'Búsquedas recientes',
  reportes_norm:            'Reportes ciudadanos',
}

const BAR_COLORS = [
  '#1d4ed8', '#2563eb', '#3b82f6', '#60a5fa', '#93c5fd',
  '#1e3a5f', '#2d6a9f', '#4f8fbf', '#7eb6d9', '#aed4ed',
  '#bfdbfe', '#dbeafe', '#eff6ff', '#f0f9ff', '#f8fafc',
]

function MetricCard({
  label, value, sub, color,
}: {
  label: string; value: string; sub: string; color: string
}) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</p>
      <p className={`text-3xl font-bold mt-1 tabular-nums ${color}`}>{value}</p>
      <p className="text-xs text-slate-400 mt-1">{sub}</p>
    </div>
  )
}

export default function PanelModelo() {
  const [info, setInfo] = useState<ModeloInfo | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/api/v1/predicciones/modelo/info')
      .then(r => r.json())
      .then(setInfo)
      .catch(() => setError('Modelo no disponible'))
  }, [])

  if (error) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 text-amber-700 text-sm">
        {error}. Ejecuta el entrenamiento primero desde el backend.
      </div>
    )
  }

  if (!info) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="bg-white border border-slate-200 rounded-xl p-4 animate-pulse">
            <div className="h-3 bg-slate-100 rounded w-2/3 mb-3" />
            <div className="h-8 bg-slate-100 rounded w-1/2" />
          </div>
        ))}
      </div>
    )
  }

  const aucColor = info.roc_auc >= 0.8 ? 'text-emerald-600' : info.roc_auc >= 0.7 ? 'text-amber-600' : 'text-red-600'

  const chartData = info.importancia_features.map(f => ({
    name: FEATURE_LABELS[f.feature] ?? f.feature,
    valor: +(f.importancia * 100).toFixed(1),
  }))

  return (
    <div className="space-y-5">

      {/* KPI metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard
          label="ROC-AUC"
          value={info.roc_auc.toFixed(3)}
          sub={info.roc_auc >= 0.8 ? 'Excelente discriminación' : 'Buena discriminación'}
          color={aucColor}
        />
        <MetricCard
          label="Avg Precision"
          value={info.avg_precision.toFixed(3)}
          sub="Precisión media ponderada"
          color="text-blue-600"
        />
        <MetricCard
          label="Muestras entrenamiento"
          value={info.n_train.toLocaleString('es-CO')}
          sub="Registros CUM usados"
          color="text-slate-700"
        />
        <MetricCard
          label="Tasa positivos"
          value={`${(info.tasa_positivos * 100).toFixed(1)}%`}
          sub="Vigentes con riesgo señalado"
          color="text-orange-600"
        />
      </div>

      {/* Feature importance chart */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100">
          <h3 className="text-sm font-semibold text-slate-800">
            Importancia de variables — Random Forest
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Qué tanto influye cada variable en la predicción de desabastecimiento
          </p>
        </div>
        <div className="p-4">
          <ResponsiveContainer width="100%" height={340}>
            <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 32, top: 4, bottom: 4 }}>
              <XAxis
                type="number"
                tickFormatter={v => `${v}%`}
                tick={{ fontSize: 11, fill: '#94a3b8' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={195}
                tick={{ fontSize: 11, fill: '#475569' }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                formatter={(v) => [`${v}%`, 'Importancia']}
                contentStyle={{
                  border: '1px solid #e2e8f0',
                  borderRadius: '8px',
                  fontSize: '12px',
                  boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
                }}
              />
              <Bar dataKey="valor" radius={[0, 4, 4, 0]} maxBarSize={22}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={BAR_COLORS[i] ?? '#3b82f6'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* How it works */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-5 text-sm text-blue-900 space-y-2">
        <p className="font-semibold text-blue-800">¿Cómo funciona el modelo?</p>
        <p className="text-blue-700 text-xs leading-relaxed">
          Utiliza un <strong>Random Forest calibrado (Platt scaling)</strong> entrenado sobre los 65,000+
          medicamentos del CUM-INVIMA, usando como ground truth el historial real de desabastecimientos
          publicado por INVIMA (17 meses, ene 2025 – may 2026). Las variables con mayor poder predictivo
          son la severidad INVIMA reciente y la tendencia histórica de alertas del principio activo.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
          {[
            { color: 'bg-emerald-500', label: 'Bajo', desc: '< 25%' },
            { color: 'bg-amber-500',   label: 'Medio',   desc: '25–50%' },
            { color: 'bg-orange-500',  label: 'Alto',  desc: '50–75%' },
            { color: 'bg-red-500',     label: 'Crítico',  desc: '> 75%' },
          ].map(n => (
            <div key={n.label} className="bg-white border border-blue-100 rounded-lg px-3 py-2 flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${n.color}`} />
              <div>
                <p className="text-xs font-semibold text-slate-700">{n.label}</p>
                <p className="text-xs text-slate-400">{n.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
