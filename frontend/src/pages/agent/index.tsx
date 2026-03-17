import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import {
  Layout, Button, Input, List, Tag, Space, Popconfirm, Empty,
  Drawer, Grid, Spin, App,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, SendOutlined, RobotOutlined,
  UserOutlined, MenuFoldOutlined, LoadingOutlined, MessageOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import {
  createSession, listSessions, deleteSession, getMessages,
  streamChat, ChatSession, ChatMessage, SSEEvent,
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

type RenderItem =
  | DisplayMessage
  | { role: 'tool_group'; tools: string[] }

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

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const avatarSize = isMobile ? 28 : 32
  const bubbleMaxWidth = isMobile ? '88%' : '80%'

  // Group consecutive tool_call messages into compact summaries when not actively streaming
  const renderItems: RenderItem[] = useMemo(() => {
    const result: RenderItem[] = []
    let toolGroup: string[] = []

    const flushToolGroup = () => {
      if (toolGroup.length === 0) return
      result.push({ role: 'tool_group', tools: [...toolGroup] })
      toolGroup = []
    }

    for (const msg of messages) {
      if (msg.role === 'tool_call') {
        toolGroup.push(msg.toolLabel || msg.content)
      } else {
        flushToolGroup()
        result.push(msg)
      }
    }

    // Trailing tool calls: show individually during streaming, group when done
    if (toolGroup.length > 0) {
      if (streaming) {
        for (const tool of toolGroup) {
          result.push({ role: 'tool_call', content: tool, toolLabel: tool })
        }
      } else {
        flushToolGroup()
      }
    }

    return result
  }, [messages, streaming])

  const scrollToBottom = useCallback((instant = false) => {
    messagesEndRef.current?.scrollIntoView({ behavior: instant ? 'auto' : 'smooth' })
  }, [])

  useEffect(() => { scrollToBottom(streaming) }, [messages, suggestions, scrollToBottom, streaming])

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
            className="agent-suggestion-chip"
            onClick={() => handleSuggestionClick(s)}
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
    <>
      <style>{`
        .agent-suggestion-chip {
          cursor: pointer;
          border-radius: 16px;
          padding: 6px 14px;
          font-size: 13px;
          border: 1px solid #1677ff;
          color: #1677ff;
          background: #f0f5ff;
          white-space: nowrap;
          user-select: none;
          transition: all 0.2s ease;
        }
        .agent-suggestion-chip:hover {
          background: #1677ff;
          color: #fff;
          transform: translateY(-1px);
          box-shadow: 0 2px 8px rgba(22, 119, 255, 0.3);
        }
        .agent-suggestion-chip:active {
          transform: translateY(0);
          box-shadow: 0 1px 4px rgba(22, 119, 255, 0.2);
        }
        .agent-tool-summary {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          margin: 6px 0;
          animation: agentFadeIn 0.3s ease;
        }
        @keyframes agentFadeIn {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes agentTypingDot {
          0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
          30% { opacity: 1; transform: translateY(-4px); }
        }
        .agent-typing-dot {
          display: inline-block;
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #1677ff;
          margin: 0 2px;
        }
        .agent-typing-dot:nth-child(1) { animation: agentTypingDot 1.2s infinite 0s; }
        .agent-typing-dot:nth-child(2) { animation: agentTypingDot 1.2s infinite 0.2s; }
        .agent-typing-dot:nth-child(3) { animation: agentTypingDot 1.2s infinite 0.4s; }
        .markdown-body {
          overflow-wrap: anywhere;
          word-break: break-word;
        }
        .markdown-body table {
          border-collapse: collapse;
          margin: 8px 0;
          width: 100%;
          table-layout: fixed;
          overflow-x: auto;
          display: block;
        }
        .markdown-body th, .markdown-body td {
          border: 1px solid #e8e8e8;
          padding: 6px 10px;
          font-size: 13px;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .markdown-body th {
          background: #fafafa;
          font-weight: 600;
        }
        .markdown-body p { margin: 0 0 8px; }
        .markdown-body p:last-child { margin-bottom: 0; }
        .markdown-body ul, .markdown-body ol { padding-left: 20px; margin: 4px 0; }
        .markdown-body a {
          color: #1677ff;
          text-decoration: none;
          word-break: break-all;
        }
        .markdown-body a:hover { text-decoration: underline; }
        .markdown-body code {
          background: rgba(0, 0, 0, 0.04);
          border-radius: 4px;
          padding: 1px 6px;
          font-size: 0.9em;
        }
        .markdown-body img {
          max-width: 100%;
          height: auto;
        }
      `}</style>
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
                {renderItems.map((item, idx) => {
                  // Completed tool group: compact summary
                  if (item.role === 'tool_group') {
                    return (
                      <div key={idx} className="agent-tool-summary">
                        <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 12 }} />
                        <span style={{ fontSize: 12, color: '#8c8c8c' }}>
                          已调用 {item.tools.join('、')}
                        </span>
                      </div>
                    )
                  }

                  // Active tool call (streaming in progress)
                  if (item.role === 'tool_call') {
                    return (
                      <div key={idx} style={{ textAlign: 'center', margin: '6px 0' }}>
                        <Tag icon={<LoadingOutlined />} color="processing">
                          {item.toolLabel || item.content}
                        </Tag>
                      </div>
                    )
                  }

                  const isUser = item.role === 'user'

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
                            <div style={{ whiteSpace: 'pre-wrap' }}>{item.content}</div>
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
                                {item.content}
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
                      <div style={{
                        padding: isMobile ? '10px 16px' : '12px 18px',
                        borderRadius: 12,
                        background: '#f5f5f5',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 2,
                      }}>
                        <span className="agent-typing-dot" />
                        <span className="agent-typing-dot" />
                        <span className="agent-typing-dot" />
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
    </>
  )
}
