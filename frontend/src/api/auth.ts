import request from './request'

export interface LoginParams {
  username: string
  password: string
}

export interface LoginResult {
  access_token: string
  token_type: string
  role: string
  username: string
}

export interface UserInfo {
  id: number
  username: string
  role: string
}

export const authApi = {
  login: (data: LoginParams): Promise<LoginResult> => request.post('/auth/login', data),
  me: (): Promise<UserInfo> => request.get('/auth/me'),
  logout: (): Promise<void> => request.post('/auth/logout'),
}
