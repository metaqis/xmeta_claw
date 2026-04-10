import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card, Button, Space, Tag, Spin, Typography, Descriptions, Modal, Input, message, Divider,
} from 'antd'
import {
  ArrowLeftOutlined, SendOutlined, EditOutlined, ReloadOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getArticle, publishArticle, updateArticle, generateArticle } from '../../api/articles'

const { Title, Text } = Typography
const { TextArea } = Input

const TYPE_MAP: Record<string, { label: string; color: string }> = {
  daily: { label: '日报', color: 'blue' },
  weekly: { label: '周报', color: 'green' },
  monthly: { label: '月报', color: 'purple' },
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  generating: { label: '生成中', color: 'processing' },
  draft: { label: '草稿', color: 'default' },
  publishing: { label: '发布中', color: 'processing' },
  published: { label: '已发布', color: 'success' },
  failed: { label: '失败', color: 'error' },
}

export default function ArticlePreviewPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [editOpen, setEditOpen] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [editSummary, setEditSummary] = useState('')
  const [editMarkdown, setEditMarkdown] = useState('')
  const [previewMode, setPreviewMode] = useState<'html' | 'markdown'>('html')

  const { data: article, isLoading } = useQuery({
    queryKey: ['article', id],
    queryFn: () => getArticle(Number(id)),
    enabled: !!id,
  })

  const pubMutation = useMutation({
    mutationFn: () => publishArticle(Number(id)),
    onSuccess: (res) => {
      message.success(res.message || '发布成功')
      queryClient.invalidateQueries({ queryKey: ['article', id] })
    },
    onError: (e: any) => {
      message.error(e?.response?.data?.detail || '发布失败')
    },
  })

  const updateMutation = useMutation({
    mutationFn: (data: { title?: string; content_markdown?: string; summary?: string }) =>
      updateArticle(Number(id), data),
    onSuccess: () => {
      message.success('已保存')
      setEditOpen(false)
      queryClient.invalidateQueries({ queryKey: ['article', id] })
    },
    onError: (e: any) => {
      message.error(e?.response?.data?.detail || '保存失败')
    },
  })

  const regenMutation = useMutation({
    mutationFn: () =>
      generateArticle({
        article_type: article?.article_type || 'daily',
        target_date: article?.data_date?.split('~')[0] || undefined,
      }),
    onSuccess: (res) => {
      message.success(`已重新生成: ${res.title}`)
      navigate(`/articles/${res.id}`)
    },
    onError: (e: any) => {
      message.error(e?.response?.data?.detail || '重新生成失败')
    },
  })

  const openEdit = () => {
    if (!article) return
    setEditTitle(article.title)
    setEditSummary(article.summary || '')
    setEditMarkdown(article.content_markdown || '')
    setEditOpen(true)
  }

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!article) {
    return <div style={{ textAlign: 'center', padding: 80 }}>文章不存在</div>
  }

  const typeInfo = TYPE_MAP[article.article_type] || { label: article.article_type, color: 'default' }
  const statusInfo = STATUS_MAP[article.status] || { label: article.status, color: 'default' }

  return (
    <div>
      {/* 顶部操作栏 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/articles')}>
          返回列表
        </Button>
        <Space>
          {article.status === 'draft' && (
            <>
              <Button icon={<EditOutlined />} onClick={openEdit}>
                编辑
              </Button>
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={() => pubMutation.mutate()}
                loading={pubMutation.isPending}
              >
                发布到微信
              </Button>
            </>
          )}
          <Button
            icon={<ReloadOutlined />}
            onClick={() => regenMutation.mutate()}
            loading={regenMutation.isPending}
          >
            重新生成
          </Button>
        </Space>
      </div>

      {/* 文章信息 */}
      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={{ xs: 1, sm: 2, md: 3 }} size="small">
          <Descriptions.Item label="标题">
            <Text strong>{article.title}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="类型">
            <Tag color={typeInfo.color}>{typeInfo.label}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={statusInfo.color}>{statusInfo.label}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="数据日期">{article.data_date || '-'}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{article.created_at || '-'}</Descriptions.Item>
          <Descriptions.Item label="发布时间">{article.published_at || '-'}</Descriptions.Item>
        </Descriptions>
        {article.summary && (
          <div style={{ marginTop: 12, padding: '8px 12px', background: '#f6f8fa', borderRadius: 6 }}>
            <Text type="secondary">摘要：{article.summary}</Text>
          </div>
        )}
        {article.error_message && (
          <div style={{ marginTop: 12, padding: '8px 12px', background: '#fff2f0', borderRadius: 6 }}>
            <Text type="danger">错误：{article.error_message}</Text>
          </div>
        )}
      </Card>

      {/* 预览切换 */}
      <div style={{ marginBottom: 12 }}>
        <Space>
          <Button
            type={previewMode === 'html' ? 'primary' : 'default'}
            size="small"
            onClick={() => setPreviewMode('html')}
          >
            渲染预览
          </Button>
          <Button
            type={previewMode === 'markdown' ? 'primary' : 'default'}
            size="small"
            onClick={() => setPreviewMode('markdown')}
          >
            Markdown 源码
          </Button>
        </Space>
      </div>

      {/* 文章内容预览 */}
      <Card
        style={{
          maxWidth: 700,
          margin: '0 auto',
          boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
        }}
      >
        {previewMode === 'html' ? (
          <div
            dangerouslySetInnerHTML={{ __html: article.content_html || '<p>暂无内容</p>' }}
            style={{ lineHeight: 1.8 }}
            className="article-html-preview"
          />
        ) : (
          <pre
            style={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontSize: 13,
              lineHeight: 1.6,
              background: '#f6f8fa',
              padding: 16,
              borderRadius: 6,
              maxHeight: 600,
              overflow: 'auto',
            }}
          >
            {article.content_markdown || '暂无内容'}
          </pre>
        )}
      </Card>

      {/* 编辑弹窗 */}
      <Modal
        title="编辑文章"
        open={editOpen}
        width={800}
        onCancel={() => setEditOpen(false)}
        onOk={() =>
          updateMutation.mutate({
            title: editTitle,
            summary: editSummary,
            content_markdown: editMarkdown,
          })
        }
        confirmLoading={updateMutation.isPending}
        okText="保存"
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <div style={{ marginBottom: 4 }}>标题</div>
            <Input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
          </div>
          <div>
            <div style={{ marginBottom: 4 }}>摘要</div>
            <TextArea
              rows={2}
              value={editSummary}
              onChange={(e) => setEditSummary(e.target.value)}
            />
          </div>
          <div>
            <div style={{ marginBottom: 4 }}>正文（Markdown）</div>
            <TextArea
              rows={16}
              value={editMarkdown}
              onChange={(e) => setEditMarkdown(e.target.value)}
              style={{ fontFamily: 'monospace', fontSize: 13 }}
            />
          </div>
        </Space>
      </Modal>
    </div>
  )
}
