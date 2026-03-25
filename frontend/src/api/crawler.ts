import request from './request'

export interface CrawlResponse {
  message: string
  status: string
  run_id?: number | null
}

export const crawlerApi = {
  full: (): Promise<CrawlResponse> => request.post('/crawler/full'),
}

