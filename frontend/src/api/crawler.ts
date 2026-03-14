import request from './request'

export interface CrawlResponse {
  message: string
  status: string
}

export const crawlerApi = {
  full: (): Promise<CrawlResponse> => request.post('/crawler/full'),
}

