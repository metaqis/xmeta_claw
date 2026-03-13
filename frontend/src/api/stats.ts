import request from './request'

export interface DashboardStats {
  total_archives: number
  total_ips: number
  total_platforms: number
  today_launches: number
  hot_archives: number
}

export interface TopArchiveItem {
  archive_id: string
  archive_name: string
  goods_min_price: number | null
  img: string | null
}

export interface TopIPItem {
  id: number
  ip_name: string
  archive_count: number
}

export interface DashboardResponse {
  stats: DashboardStats
  top_price_archives: TopArchiveItem[]
  top_ips: TopIPItem[]
}

export const statsApi = {
  dashboard: (): Promise<DashboardResponse> => request.get('/stats/dashboard'),
}
