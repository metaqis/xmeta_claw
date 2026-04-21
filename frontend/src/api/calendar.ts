import request from './request'

export interface PlatformOption {
  id: number
  name: string
}

export interface CalendarItem {
  id: number
  name: string
  sell_time: string | null
  price: number | null
  count: number | null
  platform_id: number | null
  platform_name: string | null
  ip_id: number | null
  ip_name: string | null
  img: string | null
  priority_purchase_num: number | null
  is_priority_purchase: boolean
  source_id: string | null
}

export interface CalendarListResponse {
  total: number
  items: CalendarItem[]
}

export interface CalendarParams {
  date?: string
  platform_id?: number
  ip_id?: number
  search?: string
  page?: number
  page_size?: number
}

export interface CalendarRelatedArchiveItem {
  id: number | null
  associated_archive_id: string | null
  type: number | null
  archive_name: string | null
  archive_img: string | null
  total_goods_count?: number | null
  platform_id: number | null
  platform_name: string | null
  platform_img: string | null
  ip_name: string | null
  ip_avatar: string | null
  is_transfer: boolean | null
}

export interface CalendarDetail {
  id: number
  name: string
  sell_time: string | null
  price: number | null
  count: number | null
  platform_name: string | null
  ip_name: string | null
  img: string | null
  priority_purchase_time: string | null
  context_condition: string | null
  context_condition_text: string | null
  status: string | null
  raw_json: string | null
  contain_archives: CalendarRelatedArchiveItem[]
  association_archives: CalendarRelatedArchiveItem[]
}

export const calendarApi = {
  list: (params: CalendarParams): Promise<CalendarListResponse> =>
    request.get('/calendar/', { params }),
  detail: (id: number): Promise<CalendarDetail> => request.get(`/calendar/${id}`),
  platforms: (): Promise<PlatformOption[]> => request.get('/calendar/platforms'),
}
