import request from './request'

export interface TaskRunItem {
  id: number
  task_id: string
  status: string
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  message: string | null
  error: string | null
}

export interface TaskItem {
  task_id: string
  name: string
  description: string | null
  enabled: boolean
  schedule_type: 'interval' | 'cron'
  interval_seconds: number | null
  cron: string | null
  next_run_time: string | null
  last_run: TaskRunItem | null
}

export interface TaskListResponse {
  items: TaskItem[]
}

export interface TaskUpdateRequest {
  enabled?: boolean
  schedule_type?: 'interval' | 'cron'
  interval_seconds?: number
  cron?: string
}

export interface TaskUpdateResponse {
  message: string
  task: TaskItem
}

export interface TaskRunResponse {
  message: string
  run_id: number
}

export interface TaskCancelResponse {
  message: string
}

export interface TaskRunsResponse {
  total: number
  items: TaskRunItem[]
}

export interface TaskRunLogItem {
  id: number
  run_id: number
  level: string
  message: string
  created_at: string
}

export interface TaskRunLogsResponse {
  total: number
  items: TaskRunLogItem[]
}

export const tasksApi = {
  list: (): Promise<TaskListResponse> => request.get('/tasks/'),
  update: (taskId: string, data: TaskUpdateRequest): Promise<TaskUpdateResponse> =>
    request.put(`/tasks/${taskId}`, data),
  run: (taskId: string): Promise<TaskRunResponse> => request.post(`/tasks/${taskId}/run`),
  cancel: (taskId: string, runId: number): Promise<TaskCancelResponse> =>
    request.post(`/tasks/${taskId}/runs/${runId}/cancel`),
  runs: (taskId: string, page: number, pageSize: number): Promise<TaskRunsResponse> =>
    request.get(`/tasks/${taskId}/runs`, { params: { page, page_size: pageSize } }),
  logs: (taskId: string, runId: number, page: number, pageSize: number): Promise<TaskRunLogsResponse> =>
    request.get(`/tasks/${taskId}/runs/${runId}/logs`, { params: { page, page_size: pageSize } }),
}
