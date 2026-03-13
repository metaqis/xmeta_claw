import request from './request'

export interface IPItem {
  id: number
  ip_name: string
  ip_avatar: string | null
  platform_id: number | null
  platform_name: string | null
  archive_count: number
}

export interface IPListResponse {
  total: number
  items: IPItem[]
}

export interface IPParams {
  platform_id?: number
  search?: string
  page?: number
  page_size?: number
}

export const ipApi = {
  list: (params: IPParams): Promise<IPListResponse> => request.get('/ips/', { params }),
}
