import request from './request'

export interface DashboardStats {
  total_archives: number
  total_ips: number
  total_platforms: number
  today_launches: number
}

export interface RecentArchiveItem {
  archive_id: string
  archive_name: string
  img: string | null
}

export interface TopIPItem {
  id: number
  ip_name: string
  archive_count: number
}

export interface DashboardResponse {
  stats: DashboardStats
  recent_archives: RecentArchiveItem[]
  top_ips: TopIPItem[]
}

export const statsApi = {
  dashboard: (): Promise<DashboardResponse> => request.get('/stats/dashboard'),
}
