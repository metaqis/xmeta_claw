import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Layout, Button, Input, List, Tag, Space, Popconfirm, Empty,
  Drawer, Grid, Spin, App, Card, Statistic, Progress,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, SendOutlined, RobotOutlined,
  UserOutlined, MenuFoldOutlined, LoadingOutlined, MessageOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import {
  createSession, listSessions, deleteSession, getMessages,
  streamChat, ChatSession, ChatMessage, SSEEvent, ChatProfiling,
} from '../../api/agent'

const { Sider, Content } = Layout
const { TextArea } = Input
const { useBreakpoint } = Grid

const DEFAULT_SUGGESTIONS = [
  '今天成交热榜前10是哪些',
  '查看板块统计数据',
  '近期有哪些新品发行',
]

interface DisplayMessage {
  id?: number
  role: 'user' | 'assistant' | 'tool_call'
  content: string
  toolLabel?: string
}

export default function AgentPage() {
  const { message: messageApi } = App.useApp()
  const screens = useBreakpoint()
  const isMobile = !screens.md

  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<number | null>(null)
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [siderOpen, setSiderOpen] = useState(false)
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [profiling, setProfiling] = useState<ChatProfiling | null>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const avatarSize = isMobile ? 28 : 32
  const bubbleMaxWidth = isMobile ? '88%' : '80%'

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, suggestions, scrollToBottom])

  // Load sessions on mount
  useEffect(() => {
    loadSessions()
  }, [])

  const loadSessions = async () => {
    setSessionsLoading(true)
    try {
      const data = await listSessions()
      setSessions(data)
    } catch {
      messageApi.error('加载会话列表失败')
    } finally {
      setSessionsLoading(false)
    }
  }

  const loadMessages = async (sessionId: number) => {
    try {
      const data = await getMessages(sessionId)
      const displayMsgs: DisplayMessage[] = []
      for (const m of data) {
        if (m.role === 'user') {
          displayMsgs.push({ id: m.id, role: 'user', content: m.content || '' })
        } else if (m.role === 'assistant' && m.content) {
          displayMsgs.push({ id: m.id, role: 'assistant', content: m.content })
        }
      }
      setMessages(displayMsgs)
      setSuggestions([])
      setProfiling(null)
    } catch {
      messageApi.error('加载消息失败')
    }
  }

  const handleSelectSession = (session: ChatSession) => {
    setCurrentSessionId(session.id)
    loadMessages(session.id)
    if (isMobile) setSiderOpen(false)
  }

  const handleNewSession = async () => {
    try {
      const session = await createSession()
      setSessions(prev => [session, ...prev])
      setCurrentSessionId(session.id)
      setMessages([])
      setSuggestions([])
      setProfiling(null)
      if (isMobile) setSiderOpen(false)
    } catch {
      messageApi.error('创建会话失败')
    }
  }

  const handleDeleteSession = async (id: number, e?: React.MouseEvent) => {
    e?.stopPropagation()
    try {
      await deleteSession(id)
      setSessions(prev => prev.filter(s => s.id !== id))
      if (currentSessionId === id) {
        setCurrentSessionId(null)
        setMessages([])
        setSuggestions([])
      }
    } catch {
      messageApi.error('删除失败')
    }
  }

  const handleSend = async (overrideText?: string) => {
    const text = (overrideText || input).trim()
    if (!text || streaming) return

    let sessionId = currentSessionId

    // Auto-create session if none selected
    if (!sessionId) {
      try {
        const session = await createSession(text.slice(0, 50))
        setSessions(prev => [session, ...prev])
        sessionId = session.id
        setCurrentSessionId(sessionId)
      } catch {
        messageApi.error('创建会话失败')
        return
      }
    }

    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setInput('')
    setStreaming(true)
    setLoading(true)
    setSuggestions([])
    setProfiling(null)

    const abortController = new AbortController()
    abortRef.current = abortController

    let assistantContent = ''

    try {
      await streamChat(
        sessionId,
        text,
        (event: SSEEvent) => {
          switch (event.type) {
            case 'tool_call':
              setMessages(prev => [
                ...prev,
                { role: 'tool_call', content: event.label || event.name || 'tool', toolLabel: event.label },
              ])
              break
            case 'content':
              setLoading(false)
              assistantContent += event.text || ''
              setMessages(prev => {
                const last = prev[prev.length - 1]
                if (last?.role === 'assistant' && !last.id) {
                  return [...prev.slice(0, -1), { role: 'assistant', content: assistantContent }]
                }
                return [...prev, { role: 'assistant', content: assistantContent }]
              })
              break
            case 'done':
              if (event.suggestions) setSuggestions(event.suggestions)
              if (event.profiling) setProfiling(event.profiling)
              break
            case 'error':
              messageApi.error(event.message || '请求失败')
              break
          }
        },
        abortController.signal,
      )
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== 'AbortError') {
        messageApi.error('请求失败')
      }
    } finally {
      setStreaming(false)
      setLoading(false)
      abortRef.current = null
      // Refresh session list to update title/time
      loadSessions()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleSuggestionClick = (text: string) => {
    handleSend(text)
  }

  const stageEntries = profiling
    ? Object.entries(profiling.stages || {}).sort((a, b) => a[0].localeCompare(b[0]))
    : []
  const llmRounds = stageEntries.filter(([k]) => k.startsWith('llm_round_'))
  const commitRounds = stageEntries.filter(([k]) => k.startsWith('commit_round_'))
  const totalMs = profiling?.stages?.total_ms || 0
  const totalToolMs = (profiling?.tool_calls || []).reduce((sum, item) => sum + (item.elapsed_ms || 0), 0)
  const truncationCount = profiling?.truncations?.length || 0

  // ── Suggestion chips ──

  const renderSuggestions = (items: string[]) => {
    if (!items.length) return null
    return (
      <div style={{
        display: 'flex',
        gap: 8,
        flexWrap: 'wrap',
        justifyContent: 'center',
        padding: '8px 0',
      }}>
        {items.map((s, i) => (
          <div
            key={i}
            onClick={() => handleSuggestionClick(s)}
            style={{
              cursor: 'pointer',
              borderRadius: 16,
              padding: isMobile ? '6px 12px' : '6px 14px',
              fontSize: 13,
              border: '1px solid #1677ff',
              color: '#1677ff',
              background: '#f0f5ff',
              whiteSpace: 'nowrap',
              userSelect: 'none',
            }}
          >
            {s}
          </div>
        ))}
      </div>
    )
  }

  // ── Sidebar content ──

  const siderContent = (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: '12px' }}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          block
          onClick={handleNewSession}
        >
          新对话
        </Button>
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: '0 8px' }}>
        {sessionsLoading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin size="small" />
          </div>
        ) : (
          <List
            dataSource={sessions}
            locale={{ emptyText: '暂无会话' }}
            renderItem={(session) => (
              <List.Item
                onClick={() => handleSelectSession(session)}
                style={{
                  cursor: 'pointer',
                  padding: '8px 12px',
                  borderRadius: 6,
                  marginBottom: 4,
                  background: session.id === currentSessionId ? '#e6f4ff' : 'transparent',
                }}
                extra={
                  <Popconfirm
                    title="删除此会话？"
                    onConfirm={(e) => handleDeleteSession(session.id, e as unknown as React.MouseEvent)}
                    onCancel={(e) => e?.stopPropagation()}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={(e) => e.stopPropagation()}
                      style={{ color: '#999' }}
                    />
                  </Popconfirm>
                }
              >
                <div style={{
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  fontSize: 13,
                }}>
                  <MessageOutlined style={{ marginRight: 6, color: '#999' }} />
                  {session.title}
                </div>
              </List.Item>
            )}
          />
        )}
      </div>
    </div>
  )

  // ── Main render ──

  return (
    <Layout style={{ height: 'calc(100vh - 112px)', background: '#fff', borderRadius: 8, overflow: 'hidden' }}>
      {/* Sidebar */}
      {isMobile ? (
        <Drawer
          placement="left"
          open={siderOpen}
          onClose={() => setSiderOpen(false)}
          width={280}
          styles={{ body: { padding: 0 } }}
          title="会话列表"
        >
          {siderContent}
        </Drawer>
      ) : (
        <Sider
          width={280}
          style={{
            background: '#fafafa',
            borderRight: '1px solid #f0f0f0',
          }}
        >
          {siderContent}
        </Sider>
      )}

      {/* Chat area */}
      <Content style={{ display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <div style={{
          padding: isMobile ? '6px 12px' : '8px 16px',
          borderBottom: '1px solid #f0f0f0',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          minHeight: isMobile ? 40 : 48,
        }}>
          {isMobile && (
            <Button
              type="text"
              icon={<MenuFoldOutlined />}
              onClick={() => setSiderOpen(true)}
            />
          )}
          <RobotOutlined style={{ fontSize: isMobile ? 16 : 18, color: '#1677ff' }} />
          <span style={{ fontWeight: 600, fontSize: isMobile ? 14 : 16 }}>AI 数据助手</span>
        </div>

        {/* Messages */}
        <div style={{
          flex: 1,
          overflow: 'auto',
          padding: isMobile ? '12px' : '16px',
          WebkitOverflowScrolling: 'touch',
        }}>
          {messages.length === 0 && !loading ? (
            <Empty
              image={<RobotOutlined style={{ fontSize: isMobile ? 48 : 64, color: '#d9d9d9' }} />}
              description={
                <span style={{ color: '#999', fontSize: isMobile ? 13 : 14 }}>
                  你好！我是鲸探数据助手，可以查询藏品、IP、行情等数据。
                </span>
              }
              style={{ marginTop: isMobile ? 40 : 80 }}
            >
              {renderSuggestions(DEFAULT_SUGGESTIONS)}
            </Empty>
          ) : (
            <>
              {messages.map((msg, idx) => {
                if (msg.role === 'tool_call') {
                  return (
                    <div key={idx} style={{ textAlign: 'center', margin: '8px 0' }}>
                      <Tag
                        icon={<LoadingOutlined />}
                        color="processing"
                      >
                        {msg.toolLabel || msg.content}
                      </Tag>
                    </div>
                  )
                }

                const isUser = msg.role === 'user'

                return (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      justifyContent: isUser ? 'flex-end' : 'flex-start',
                      marginBottom: isMobile ? 12 : 16,
                    }}
                  >
                    <Space align="start" style={{ maxWidth: bubbleMaxWidth, flexDirection: isUser ? 'row-reverse' : 'row' }}>
                      <div style={{
                        width: avatarSize,
                        height: avatarSize,
                        borderRadius: '50%',
                        background: isUser ? '#1677ff' : '#f0f0f0',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                      }}>
                        {isUser
                          ? <UserOutlined style={{ color: '#fff', fontSize: isMobile ? 12 : 14 }} />
                          : <RobotOutlined style={{ color: '#1677ff', fontSize: isMobile ? 12 : 14 }} />
                        }
                      </div>
                      <div style={{
                        padding: isMobile ? '6px 12px' : '8px 14px',
                        borderRadius: 12,
                        background: isUser ? '#1677ff' : '#f5f5f5',
                        color: isUser ? '#fff' : '#333',
                        lineHeight: 1.6,
                        wordBreak: 'break-word',
                      }}>
                        {isUser ? (
                          <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
                        ) : (
                          <div className="markdown-body">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              rehypePlugins={[rehypeRaw, rehypeSanitize]}
                              components={{
                                a: ({ href, children, ...props }) => (
                                  <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                                    {children}
                                  </a>
                                ),
                              }}
                            >
                              {msg.content}
                            </ReactMarkdown>
                          </div>
                        )}
                      </div>
                    </Space>
                  </div>
                )
              })}

              {loading && (
                <div style={{ display: 'flex', marginBottom: isMobile ? 12 : 16 }}>
                  <Space align="start">
                    <div style={{
                      width: avatarSize, height: avatarSize, borderRadius: '50%',
                      background: '#f0f0f0', display: 'flex',
                      alignItems: 'center', justifyContent: 'center',
                    }}>
                      <RobotOutlined style={{ color: '#1677ff', fontSize: isMobile ? 12 : 14 }} />
                    </div>
                    <div style={{ padding: isMobile ? '8px 12px' : '10px 14px', borderRadius: 12, background: '#f5f5f5' }}>
                      <Spin size="small" />
                      <span style={{ marginLeft: 8, color: '#999', fontSize: isMobile ? 12 : 14 }}>思考中...</span>
                    </div>
                  </Space>
                </div>
              )}

              {/* Suggestion chips after messages */}
              {!streaming && suggestions.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  {renderSuggestions(suggestions)}
                </div>
              )}

              {!streaming && profiling && (
                <Card
                  size="small"
                  style={{
                    marginTop: 12,
                    borderRadius: 10,
                    border: '1px solid #e6f4ff',
                    background: '#fafcff',
                  }}
                  title={(
                    <Space size={6}>
                      <ThunderboltOutlined style={{ color: '#1677ff' }} />
                      <span style={{ fontSize: 13, fontWeight: 600 }}>本次聊天性能</span>
                    </Space>
                  )}
                >
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: isMobile ? '1fr' : 'repeat(4, minmax(0, 1fr))',
                    gap: 10,
                  }}>
                    <Card size="small" style={{ borderRadius: 8 }}>
                      <Statistic title="总耗时" value={totalMs} precision={1} suffix="ms" />
                    </Card>
                    <Card size="small" style={{ borderRadius: 8 }}>
                      <Statistic title="历史消息" value={profiling.history_message_count || 0} suffix="条" />
                    </Card>
                    <Card size="small" style={{ borderRadius: 8 }}>
                      <Statistic title="工具耗时合计" value={totalToolMs} precision={1} suffix="ms" />
                    </Card>
                    <Card size="small" style={{ borderRadius: 8 }}>
                      <Statistic title="截断次数" value={truncationCount} suffix="次" />
                    </Card>
                  </div>

                  {llmRounds.length > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: '#666', marginBottom: 6 }}>LLM 轮次耗时</div>
                      <Space direction="vertical" style={{ width: '100%' }} size={6}>
                        {llmRounds.map(([name, value]) => (
                          <div key={name}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 2 }}>
                              <span>第{name.replace('llm_round_', '').replace('_ms', '')}轮</span>
                              <span>{Number(value).toFixed(1)} ms</span>
                            </div>
                            <Progress percent={Math.min(100, totalMs > 0 ? (Number(value) / totalMs) * 100 : 0)} showInfo={false} size="small" />
                          </div>
                        ))}
                      </Space>
                    </div>
                  )}

                  {(profiling.tool_calls || []).length > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: '#666', marginBottom: 6 }}>工具调用耗时</div>
                      <Space wrap size={[8, 8]}>
                        {profiling.tool_calls.map((item, idx) => (
                          <Tag key={`${item.name}-${idx}`} color="blue">
                            {item.name}: {item.elapsed_ms.toFixed(1)}ms
                          </Tag>
                        ))}
                      </Space>
                    </div>
                  )}

                  {(profiling.truncations || []).length > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: '#666', marginBottom: 6 }}>截断详情</div>
                      <Space wrap size={[8, 8]}>
                        {profiling.truncations.map((item, idx) => (
                          <Tag key={`${item.tool_name || 'tool'}-${idx}`} color="gold">
                            {(item.tool_name || 'tool')} {item.original_length}→{item.truncated_length} ({item.elapsed_ms.toFixed(3)}ms)
                          </Tag>
                        ))}
                      </Space>
                    </div>
                  )}

                  <div style={{ marginTop: 10, fontSize: 12, color: '#888' }}>
                    工具数 {profiling.selected_tool_count || 0} · 日历意图 {profiling.calendar_intent ? '是' : '否'} · commit轮次 {commitRounds.length}
                  </div>
                </Card>
              )}
            </>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div style={{
          padding: isMobile ? '10px 12px' : '12px 16px',
          borderTop: '1px solid #f0f0f0',
          background: '#fafafa',
        }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <TextArea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isMobile ? '输入问题...' : '输入问题... (Shift+Enter 换行)'}
              autoSize={{ minRows: 1, maxRows: 4 }}
              disabled={streaming}
              style={{ borderRadius: 8, fontSize: 14 }}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={() => handleSend()}
              loading={streaming}
              disabled={!input.trim() && !streaming}
              style={{ height: 'auto', borderRadius: 8, minWidth: isMobile ? 40 : undefined }}
            >
              {!isMobile && '发送'}
            </Button>
          </div>
        </div>
      </Content>
    </Layout>
  )
}
