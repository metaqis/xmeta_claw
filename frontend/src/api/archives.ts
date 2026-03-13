import request from './request'

export interface ArchiveItem {
  archive_id: string
  archive_name: string
  platform_id: number | null
  platform_name: string | null
  ip_id: number | null
  ip_name: string | null
  issue_time: string | null
  archive_type: string | null
  is_hot: boolean
  img: string | null
  goods_min_price: number | null
  selling_count: number | null
  deal_count: number | null
}

export interface ArchiveListResponse {
  total: number
  items: ArchiveItem[]
}

export interface PriceHistoryItem {
  min_price: number | null
  sell_count: number
  buy_count: number
  deal_count: number
  record_time: string | null
}

export interface ArchiveDetail {
  archive_id: string
  archive_name: string
  platform_name: string | null
  ip_name: string | null
  issue_time: string | null
  archive_description: string | null
  archive_type: string | null
  is_hot: boolean
  is_open_auction: boolean
  is_open_want_buy: boolean
  img: string | null
  goods_min_price: number | null
  want_buy_count: number
  selling_count: number
  deal_count: number
  want_buy_max_price: number | null
  deal_price: number | null
  price_history: PriceHistoryItem[]
}

export interface ArchiveParams {
  platform_id?: number
  ip_id?: number
  search?: string
  is_hot?: boolean
  sort_by?: string
  page?: number
  page_size?: number
}

export const archiveApi = {
  list: (params: ArchiveParams): Promise<ArchiveListResponse> =>
    request.get('/archives/', { params }),
  detail: (id: string): Promise<ArchiveDetail> => request.get(`/archives/${id}`),
}
