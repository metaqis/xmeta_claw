import request from './request'

export interface ArticleItem {
  id: number
  title: string
  article_type: string
  data_date: string | null
  summary: string | null
  status: string
  cover_image_url: string | null
  created_at: string | null
}

export interface ArticleListResponse {
  items: ArticleItem[]
  total: number
  page: number
  page_size: number
}

export interface ArticleDetail {
  id: number
  title: string
  article_type: string
  data_date: string | null
  summary: string | null
  content_html: string | null
  content_markdown: string | null
  cover_image_url: string | null
  status: string
  wechat_media_id: string | null
  error_message: string | null
  created_at: string | null
  updated_at: string | null
  images: { id: number; type: string; file_path: string; wechat_url: string | null }[]
}

export function getArticles(params: {
  article_type?: string
  status?: string
  page?: number
  page_size?: number
}) {
  return request.get<any, ArticleListResponse>('/articles/', { params })
}

export function getArticle(id: number) {
  return request.get<any, ArticleDetail>(`/articles/${id}`)
}

export function generateArticle(data: { article_type: string; target_date?: string }) {
  return request.post<any, { id: number; title: string; status: string; message: string }>(
    '/articles/generate',
    data,
  )
}

export function sendToWechat(id: number) {
  return request.post<any, { id: number; status: string; wechat_media_id: string; message: string }>(
    `/articles/${id}/send_to_wechat`,
  )
}

export function updateArticle(
  id: number,
  data: { title?: string; content_markdown?: string; summary?: string },
) {
  return request.put<any, { id: number; title: string; status: string }>(
    `/articles/${id}`,
    data,
  )
}

export function deleteArticle(id: number) {
  return request.delete<any, { message: string }>(`/articles/${id}`)
}
