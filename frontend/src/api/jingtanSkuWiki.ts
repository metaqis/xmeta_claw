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
  homepage_detail: JingtanSkuHomepageDetail | null
}

export interface JingtanSkuHomepageDetail {
  sku_id: string
  sku_name: string
  author: string | null
  owner: string | null
  partner: string | null
  partner_name: string | null
  biz_type: string | null
  bg_conf: string | null
  bg_info: string | null
  has_item: boolean | null
  mini_file_url: string | null
  origin_file_url: string | null
  quantity_type: string | null
  sku_desc: string | null
  sku_desc_image_file_ids: string | null
  sku_issue_time_ms: number | null
  sku_producer: string | null
  sku_quantity: number | null
  sku_type: string | null
  collect_num: number | null
  user_collect_status: boolean | null
  comment_num: number | null
  mini_feed_num: number | null
  show_comment_list: boolean | null
  show_mini_feed_list: boolean | null
  producer_fans_uid: string | null
  producer_name: string | null
  producer_avatar: string | null
  producer_avatar_type: string | null
  certification_name: string | null
  certification_type: string | null
  follow_status: string | null
  produce_amount: number | null
  raw_json: string | null
  created_at: string | null
  updated_at: string | null
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

