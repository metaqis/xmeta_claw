import request from './request'
import { useAuthStore } from '../store/auth'

// ── 类型 ────────────────────────────────────────

export interface ChatSession {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: number
  role: string
  content: string | null
  tool_calls: string | null
  tool_call_id: string | null
  name: string | null
  created_at: string
}

export interface SSEEvent {
  type: 'tool_call' | 'content' | 'done' | 'error'
  text?: string
  name?: string
  label?: string
  message?: string
  suggestions?: string[]
  profiling?: ChatProfiling
}

export interface ProfilingToolCall {
  name: string
  elapsed_ms: number
  result_length: number
}

export interface ProfilingTruncation {
  role: string
  tool_name?: string | null
  original_length: number
  truncated_length: number
  elapsed_ms: number
}

export interface ChatProfiling {
  stages: Record<string, number>
  tool_calls: ProfilingToolCall[]
  truncations: ProfilingTruncation[]
  selected_tool_count?: number
  calendar_intent?: boolean
  history_message_count?: number
}

// ── REST API ────────────────────────────────────

export function createSession(title = '新对话'): Promise<ChatSession> {
  return request.post('/agent/sessions', { title })
}

export function listSessions(): Promise<ChatSession[]> {
  return request.get('/agent/sessions')
}

export function deleteSession(id: number): Promise<void> {
  return request.delete(`/agent/sessions/${id}`)
}

export function getMessages(sessionId: number): Promise<ChatMessage[]> {
  return request.get(`/agent/sessions/${sessionId}/messages`)
}

// ── SSE 流式聊天 ────────────────────────────────

export async function streamChat(
  sessionId: number,
  content: string,
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = useAuthStore.getState().token

  const response = await fetch('/api/agent/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ session_id: sessionId, content }),
    signal,
  })

  if (!response.ok) {
    if (response.status === 401) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }
    throw new Error(`HTTP ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed || !trimmed.startsWith('data: ')) continue

      try {
        const data = JSON.parse(trimmed.slice(6)) as SSEEvent
        onEvent(data)
      } catch {
        // skip malformed lines
      }
    }
  }

  // Process any remaining buffer
  if (buffer.trim().startsWith('data: ')) {
    try {
      const data = JSON.parse(buffer.trim().slice(6)) as SSEEvent
      onEvent(data)
    } catch {
      // ignore
    }
  }
}
