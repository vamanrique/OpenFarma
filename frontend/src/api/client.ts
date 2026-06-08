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
  fuente?: string             // CUM_ACTIVO | CUM_RENOVACION
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
  cum_id: string
  region_id: number
  probabilidad: number
  nivel_riesgo: string
  latitud?: number
  longitud?: number
  region_nombre?: string
  medicamento_nombre?: string
}

export interface ProductoEnGrupo {
  cum_id: string
  nombre_comercial: string
  laboratorio: string | null
  registro_sanitario: string | null
  estado_cum: string
  fuente: string
}

export interface GrupoDetalle {
  id: number
  grupo_via: string
  grupo_via_label: string
  concentracion_norm: string | null
  concentracion_valor: number | null
  concentracion_unidad: string | null
  n_productos: number
  productos: ProductoEnGrupo[]
  revisado_ia: boolean
}

export interface GruposEquivalencia {
  dci: string
  dci_key: string
  mi_grupo: GrupoDetalle | null
  misma_via: GrupoDetalle[]
  otras_vias: GrupoDetalle[]
  grupos_fallback: boolean
}

const BASE_URL = '/api/v1'

export const medicamentosApi = {
  buscar: (q: string, soloActivos = true, limit = 20) =>
    api.get<MedicamentoLive[]>('/medicamentos/buscar', {
      params: { q, solo_activos: soloActivos, limit },
    }),
  alternativas: (cumId: string) =>
    api.get<AlternativaLive[]>(`/medicamentos/${encodeURIComponent(cumId)}/alternativas`),
  gruposEquivalencia: async (cumId: string): Promise<GruposEquivalencia> => {
    const r = await fetch(`${BASE_URL}/grupos/medicamentos/${encodeURIComponent(cumId)}`)
    if (!r.ok) throw new Error('Error cargando grupos')
    return r.json()
  },
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

export default api
