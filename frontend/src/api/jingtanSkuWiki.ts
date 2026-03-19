import request from './request'

export interface JingtanSkuWikiItem {
  sku_id: string
  sku_name: string
  author: string | null
  owner: string | null
  partner: string | null
  partner_name: string | null
  first_category: string | null
  first_category_name: string | null
  second_category: string | null
  second_category_name: string | null
  quantity_type: string | null
  sku_quantity: number | null
  sku_type: string | null
  sku_issue_time_ms: number | null
  sku_producer: string | null
  mini_file_url: string | null
  created_at: string | null
  updated_at: string | null
}

export interface JingtanSkuWikiDetail extends JingtanSkuWikiItem {
  raw_json: string | null
}

export interface JingtanSkuWikiListResponse {
  total: number
  items: JingtanSkuWikiItem[]
}

export interface JingtanSkuWikiListParams {
  search?: string
  first_category?: string
  second_category?: string
  page?: number
  page_size?: number
}

export const jingtanSkuWikiApi = {
  list: (params: JingtanSkuWikiListParams): Promise<JingtanSkuWikiListResponse> =>
    request.get('/jingtan/sku-wikis', { params }),
  detail: (skuId: string): Promise<JingtanSkuWikiDetail> => request.get(`/jingtan/sku-wikis/${skuId}`),
}

