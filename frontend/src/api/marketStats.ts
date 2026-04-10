import request from './request'

export interface DailySummaryItem {
  stat_date: string
  total_deal_count: number | null
  total_market_value: number | null
  total_deal_amount: number | null
  active_plane_count: number | null
  top_plane_name: string | null
  top_plane_deal_count: number | null
  top_ip_name: string | null
  top_ip_deal_count: number | null
}

export interface PlaneSnapshotItem {
  stat_date: string
  plane_code: string
  plane_name: string
  avg_price: number | null      // 日涨跌幅 %
  deal_price: number | null
  deal_count: number | null
  shelves_rate: number | null
  total_market_value: number | null
}

export interface IPSnapshotItem {
  stat_date: string
  community_ip_id: number
  name: string
  avatar: string | null
  rank: number | null
  archive_count: number | null
  market_amount: number | null
  market_amount_rate: number | null
  hot: number | null
  hot_rate: number | null
  avg_amount: number | null
  avg_amount_rate: number | null
  deal_count: number | null
  deal_count_rate: number | null
  publish_count: number | null
}

export interface ArchiveSnapshotItem {
  stat_date: string
  top_code: string
  top_name: string
  rank: number
  archive_id: number
  archive_name: string | null
  archive_img: string | null
  selling_count: number | null
  deal_count: number | null
  market_amount: number | null
  market_amount_rate: number | null
  min_amount: number | null
  min_amount_rate: number | null
  avg_amount: number | null
  avg_amount_rate: number | null
  up_rate: number | null
  deal_amount: number | null
  deal_amount_rate: number | null
  publish_count: number | null
  is_transfer: boolean | null
}

export interface TopCategory {
  code: string
  name: string
}

export interface UpDownBucket {
  label: string
  count: number
  type: number  // 1=涨 2=跌
}

export interface PlaneCensusItem {
  stat_date: string
  plane_code: string
  plane_name: string | null
  total_market_amount: number | null
  total_market_amount_rate: number | null
  total_deal_count: number | null
  total_deal_count_rate: number | null
  total_archive_count: number | null
  up_archive_count: number | null
  down_archive_count: number | null
  up_down_list: UpDownBucket[]
}

export interface TopCensusItem {
  stat_date: string
  top_code: string
  top_name: string | null
  total_market_amount: number | null
  total_market_amount_rate: number | null
  total_deal_count: number | null
  total_deal_count_rate: number | null
  total_archive_count: number | null
  up_archive_count: number | null
  down_archive_count: number | null
  up_down_list: UpDownBucket[]
}

export const marketStatsApi = {
  availableDates: (): Promise<{ dates: string[] }> =>
    request.get('/market-stats/available-dates'),

  summary: (params?: { start?: string; end?: string }): Promise<DailySummaryItem[]> =>
    request.get('/market-stats/summary', { params }),

  planes: (params?: { date?: string }): Promise<PlaneSnapshotItem[]> =>
    request.get('/market-stats/planes', { params }),

  ips: (params?: { date?: string; limit?: number }): Promise<IPSnapshotItem[]> =>
    request.get('/market-stats/ips', { params }),

  archives: (params?: { date?: string; top_code?: string }): Promise<ArchiveSnapshotItem[]> =>
    request.get('/market-stats/archives', { params }),

  topCategories: (params?: { date?: string }): Promise<TopCategory[]> =>
    request.get('/market-stats/top-categories', { params }),

  planeCensus: (params?: { date?: string; plane_code?: string }): Promise<PlaneCensusItem[]> =>
    request.get('/market-stats/plane-census', { params }),

  topCensus: (params?: { date?: string; top_code?: string }): Promise<TopCensusItem[]> =>
    request.get('/market-stats/top-census', { params }),
}
