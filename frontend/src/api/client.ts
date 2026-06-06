import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1' })

export interface MedicamentoLive {
  cum_id: string
  nombre_comercial: string
  principios_dci: string[]
  tipo_formula: string        // monocomponente | biconjugado | triconjugado | tetraconjugado
  concentracion_display: string
  presentacion: string
  forma_farmaceutica: string
  via_administracion: string
  atc: string
  descripcion_atc: string
  laboratorio: string
  registro_sanitario: string
  estado_registro: string
  estado_cum: string
}

export interface AlternativaLive {
  cum_origen: string
  cum_destino: string
  tipo: string
  descripcion: string
  componentes_compartidos: string[]
  medicamento_destino?: MedicamentoLive
}

export interface Region {
  id: number
  nombre: string
  codigo_dane: string
  latitud?: number
  longitud?: number
}

export interface PrediccionMapa {
  region_id: number
  medicamento_id: number
  probabilidad: number
  nivel_riesgo: string
  latitud?: number
  longitud?: number
  region_nombre?: string
  medicamento_nombre?: string
}

export const medicamentosApi = {
  buscar: (q: string, soloActivos = true, limit = 20) =>
    api.get<MedicamentoLive[]>('/medicamentos/buscar', {
      params: { q, solo_activos: soloActivos, limit },
    }),
  alternativas: (cumId: string) =>
    api.get<AlternativaLive[]>(`/medicamentos/${encodeURIComponent(cumId)}/alternativas`),
}

export const regionesApi = {
  listar: () => api.get<Region[]>('/regiones/'),
}

export const prediccionesApi = {
  mapa: (nivelRiesgo?: string) =>
    api.get<PrediccionMapa[]>('/predicciones/mapa', {
      params: nivelRiesgo ? { nivel_riesgo: nivelRiesgo } : {},
    }),
}

export interface ReporteReciente {
  id: number
  cum_id: string
  nombre_medicamento: string
  region_nombre: string
  tipo_reporte: string
  descripcion?: string
  fecha: string
}

export const reportesApi = {
  reportar: (cum_id: string, region_id: number, tipo_reporte: string, descripcion?: string) =>
    api.post('/reportes/no-disponibilidad', { cum_id, region_id, tipo_reporte, descripcion }),
  recientes: (limit = 10) =>
    api.get<ReporteReciente[]>('/reportes/recientes', { params: { limit } }),
  total: () =>
    api.get<{ total: number; por_tipo: Record<string, number> }>('/reportes/total'),
}

export const adminApi = {
  validacion: () => api.get('/admin/validacion/reporte'),
  estadisticasDb: () => api.get('/admin/estadisticas/db'),
}

export default api
