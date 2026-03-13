import request from './request'

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

export const calendarApi = {
  list: (params: CalendarParams): Promise<CalendarListResponse> =>
    request.get('/calendar/', { params }),
  detail: (id: number): Promise<any> => request.get(`/calendar/${id}`),
}
