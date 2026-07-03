import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface ModeloInfo {
  roc_auc: number
  avg_precision: number
  n_train: number
  tasa_positivos: number
  importancia_features: { feature: string; importancia: number }[]
}

interface EstadoInvima {
  estado: string
  estado_label: string
  mes: number
  anio: number
  principio_activo: string
  forma: string
  concentracion: string
  causas: string
  atc: string | null
}

const FEATURE_LABELS: Record<string, string> = {
  invima_sev_actual:          'Severidad INVIMA actual',
  invima_sev_t3_avg:          'INVIMA sev. promedio 3m',
  invima_peor_sev_hist:       'Peor historial INVIMA',
  invima_meses_monitoreado:   'Meses monitoreado INVIMA',
  invima_tendencia:           'Tendencia INVIMA',
  tasa_inactivacion_atc5:     'Tasa inactivación ATC',
  num_competidores:           'Competidores en mercado',
  tiene_alternativas:         'Tiene alternativas',
  monopolio:                  'Monopolio de mercado',
  es_combinado:               'Fórmula combinada',
  tipo_formula_num:           'Complejidad de fórmula',
  grupo_atc_enc:              'Grupo ATC anatómico',
  num_presentaciones_activas: 'Presentaciones activas',
  busquedas_norm:             'Búsquedas recientes',
  reportes_norm:              'Reportes ciudadanos',
}

const BAR_COLORS = [
  '#1d4ed8', '#2563eb', '#3b82f6', '#60a5fa', '#93c5fd',
  '#1e3a5f', '#2d6a9f', '#4f8fbf', '#7eb6d9', '#aed4ed',
  '#bfdbfe', '#dbeafe', '#eff6ff', '#f0f9ff', '#f8fafc',
]

const ESTADO_CONFIG: Record<string, { bg: string; text: string; label: string }> = {
  DESABASTECIDO:      { bg: 'bg-red-100',    text: 'text-red-700',    label: 'Desabastecido' },
  EN_RIESGO:          { bg: 'bg-orange-100', text: 'text-orange-700', label: 'En riesgo' },
  EN_MONITORIZACION:  { bg: 'bg-amber-100',  text: 'text-amber-700',  label: 'En monitoreo' },
  NO_COMERCIALIZADO:  { bg: 'bg-slate-100',  text: 'text-slate-600',  label: 'No comercializado' },
  DESCONTINUADO:      { bg: 'bg-slate-100',  text: 'text-slate-500',  label: 'Descontinuado' },
}

const MESES = ['', 'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

function EstadoBadge({ estado }: { estado: string }) {
  const cfg = ESTADO_CONFIG[estado] ?? { bg: 'bg-slate-100', text: 'text-slate-600', label: estado }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wide ${cfg.bg} ${cfg.text}`}>
      {cfg.label}
    </span>
  )
}

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
  const [desabastecidos, setDesabastecidos] = useState<EstadoInvima[]>([])
  const [filtroEstado, setFiltroEstado] = useState<'todos' | 'DESABASTECIDO' | 'EN_RIESGO'>('todos')
  const [busquedaMed, setBusquedaMed] = useState('')

  useEffect(() => {
    fetch('/api/v1/predicciones/modelo/info')
      .then(r => r.json())
      .then(setInfo)
      .catch(() => setError('Modelo no disponible'))

    fetch('/api/v1/desabastecimiento/actual')
      .then(r => r.json())
      .then(setDesabastecidos)
      .catch(() => {})
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

  const listaFiltrada = desabastecidos
    .filter(d => filtroEstado === 'todos' || d.estado === filtroEstado)
    .filter(d => !busquedaMed || d.principio_activo.toLowerCase().includes(busquedaMed.toLowerCase()))

  const cuentaDesab = desabastecidos.filter(d => d.estado === 'DESABASTECIDO').length
  const cuentaRiesgo = desabastecidos.filter(d => d.estado === 'EN_RIESGO').length
  const refMes = desabastecidos[0]

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
          <ResponsiveContainer width="100%" height={480}>
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
                width={210}
                interval={0}
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
            { color: 'bg-emerald-500', label: 'Bajo',    desc: '< 25%' },
            { color: 'bg-amber-500',   label: 'Medio',   desc: '25–50%' },
            { color: 'bg-orange-500',  label: 'Alto',    desc: '50–75%' },
            { color: 'bg-red-500',     label: 'Crítico', desc: '> 75%' },
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

      {/* INVIMA shortage list */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              Medicamentos bajo vigilancia INVIMA
              {refMes && (
                <span className="text-xs font-normal text-slate-400">
                  {MESES[refMes.mes]} {refMes.anio}
                </span>
              )}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Listado oficial de abastecimiento publicado por INVIMA en PDF mensual
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-red-600 font-semibold bg-red-50 border border-red-100 px-2 py-0.5 rounded-full">
              {cuentaDesab} desabastecidos
            </span>
            <span className="text-xs text-orange-600 font-semibold bg-orange-50 border border-orange-100 px-2 py-0.5 rounded-full">
              {cuentaRiesgo} en riesgo
            </span>
          </div>
        </div>

        {/* Filters */}
        <div className="px-5 py-3 border-b border-slate-100 flex flex-wrap gap-2">
          {([
            ['todos',           'Todos'],
            ['DESABASTECIDO',   'Desabastecidos'],
            ['EN_RIESGO',       'En riesgo'],
          ] as const).map(([val, label]) => (
            <button
              key={val}
              onClick={() => setFiltroEstado(val)}
              className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                filtroEstado === val
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'
              }`}
            >
              {label}
            </button>
          ))}
          <input
            type="text"
            placeholder="Buscar principio activo..."
            value={busquedaMed}
            onChange={e => setBusquedaMed(e.target.value)}
            className="ml-auto text-xs border border-slate-200 rounded-full px-3 py-1 focus:outline-none focus:border-blue-400 w-52"
          />
        </div>

        {desabastecidos.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-slate-400">
            Cargando datos INVIMA...
          </div>
        ) : listaFiltrada.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-slate-400">
            No hay medicamentos con el filtro seleccionado.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-left">
                  <th className="px-4 py-2.5 font-medium text-slate-500 w-32">Estado</th>
                  <th className="px-4 py-2.5 font-medium text-slate-500">Principio activo</th>
                  <th className="px-4 py-2.5 font-medium text-slate-500 hidden sm:table-cell">Forma / Concentración</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {listaFiltrada.map((d, i) => (
                  <tr key={i} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-2.5">
                      <EstadoBadge estado={d.estado} />
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="font-medium text-slate-800">{d.principio_activo}</span>
                      {d.atc && (
                        <span className="ml-1.5 text-slate-400 font-mono text-xs">{d.atc}</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 hidden sm:table-cell text-slate-500">
                      {d.forma}{d.concentracion ? ` · ${d.concentracion}` : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="px-4 py-2.5 text-xs text-slate-400 border-t border-slate-100">
              Mostrando {listaFiltrada.length} de {desabastecidos.length} registros
            </p>
          </div>
        )}
      </div>

    </div>
  )
}
