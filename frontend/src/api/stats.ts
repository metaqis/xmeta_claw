import request from './request'

export interface DashboardStats {
  total_archives: number
  total_ips: number
  total_platforms: number
  today_launches: number
}

export interface CalendarCardItem {
  id: number
  name: string
  sell_time: string | null
  price: number | null
  count: number | null
  platform_name: string | null
  ip_name: string | null
  img: string | null
}

export interface RecentArchiveItem {
  archive_id: string
  archive_name: string
  img: string | null
  issue_time: string | null
  ip_name: string | null
}

export interface TrendPoint {
  date: string
  value: number | null
}

export interface PlaneTrendItem {
  plane_code: string
  plane_name: string
  points: TrendPoint[]
}

export interface IPTrendItem {
  community_ip_id: number
  name: string
  points: TrendPoint[]
}

export interface DashboardResponse {
  stats: DashboardStats
  today_calendar: CalendarCardItem[]
  recent_archives: RecentArchiveItem[]
  market_value_trend: TrendPoint[]
  deal_count_trend: TrendPoint[]
  plane_trends: PlaneTrendItem[]
  ip_trends: IPTrendItem[]
}

export const statsApi = {
  dashboard: (days = 7): Promise<DashboardResponse> =>
    request.get('/stats/dashboard', { params: { days } }),
}
