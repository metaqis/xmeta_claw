import request from './request'

export interface ArchiveItem {
  archive_id: string
  archive_name: string
  total_goods_count: number | null
  platform_id: number | null
  platform_name: string | null
  ip_id: number | null
  ip_name: string | null
  issue_time: string | null
  archive_type: string | null
  img: string | null
}

export interface ArchiveListResponse {
  total: number
  items: ArchiveItem[]
}

export interface PlaneItem {
  code: string
  name: string
}

export interface PlaneListResponse {
  items: PlaneItem[]
}

export interface ArchiveDetail {
  archive_id: string
  archive_name: string
  platform_name: string | null
  ip_name: string | null
  issue_time: string | null
  archive_description: string | null
  archive_type: string | null
  total_goods_count: number | null
  is_open_auction: boolean
  is_open_want_buy: boolean
  img: string | null
}

export interface ArchiveParams {
  platform_id?: number
  ip_id?: number
  plane_name?: string
  plane_code?: string
  search?: string
  sort_by?: string
  page?: number
  page_size?: number
}

export const archiveApi = {
  list: (params: ArchiveParams): Promise<ArchiveListResponse> =>
    request.get('/archives/', { params }),
  planes: (): Promise<PlaneListResponse> =>
    request.get('/archives/planes'),
  detail: (id: string): Promise<ArchiveDetail> => request.get(`/archives/${id}`),
}
