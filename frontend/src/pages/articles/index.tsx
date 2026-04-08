import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Table, Button, Space, Tag, Modal, DatePicker, Select, Card, message, Popconfirm, Typography,
} from 'antd'
import {
  PlusOutlined, EyeOutlined, SendOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import {
  getArticles, generateArticle, publishArticle, deleteArticle,
  type ArticleItem,
} from '../../api/articles'

const { Title } = Typography

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

export default function ArticlesPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [typeFilter, setTypeFilter] = useState<string>()
  const [statusFilter, setStatusFilter] = useState<string>()
  const [genModalOpen, setGenModalOpen] = useState(false)
  const [genType, setGenType] = useState<string>('daily')
  const [genDate, setGenDate] = useState<dayjs.Dayjs | null>(dayjs())

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['articles', page, typeFilter, statusFilter],
    queryFn: () =>
      getArticles({
        page,
        page_size: 15,
        article_type: typeFilter,
        status: statusFilter,
      }),
  })

  const genMutation = useMutation({
    mutationFn: generateArticle,
    onSuccess: (res) => {
      message.success(res.message || '文章生成成功')
      setGenModalOpen(false)
      queryClient.invalidateQueries({ queryKey: ['articles'] })
    },
    onError: (e: any) => {
      message.error(e?.response?.data?.detail || '生成失败')
    },
  })

  const pubMutation = useMutation({
    mutationFn: publishArticle,
    onSuccess: (res) => {
      message.success(res.message || '发布成功')
      queryClient.invalidateQueries({ queryKey: ['articles'] })
    },
    onError: (e: any) => {
      message.error(e?.response?.data?.detail || '发布失败')
    },
  })

  const delMutation = useMutation({
    mutationFn: deleteArticle,
    onSuccess: () => {
      message.success('已删除')
      queryClient.invalidateQueries({ queryKey: ['articles'] })
    },
  })

  const handleGenerate = () => {
    const params: { article_type: string; target_date?: string } = {
      article_type: genType,
    }
    if (genDate) {
      params.target_date = genDate.format('YYYY-MM-DD')
    }
    genMutation.mutate(params)
  }

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (text: string, record: ArticleItem) => (
        <a onClick={() => navigate(`/articles/${record.id}`)}>{text}</a>
      ),
    },
    {
      title: '类型',
      dataIndex: 'article_type',
      key: 'article_type',
      width: 80,
      render: (t: string) => {
        const m = TYPE_MAP[t]
        return m ? <Tag color={m.color}>{m.label}</Tag> : t
      },
    },
    {
      title: '数据日期',
      dataIndex: 'data_date',
      key: 'data_date',
      width: 160,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (s: string) => {
        const m = STATUS_MAP[s]
        return m ? <Tag color={m.color}>{m.label}</Tag> : s
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (t: string) => (t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, record: ArticleItem) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/articles/${record.id}`)}
          >
            预览
          </Button>
          {record.status === 'draft' && (
            <Button
              type="link"
              size="small"
              icon={<SendOutlined />}
              onClick={() => pubMutation.mutate(record.id)}
              loading={pubMutation.isPending}
            >
              发布
            </Button>
          )}
          <Popconfirm title="确定删除？" onConfirm={() => delMutation.mutate(record.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>文章管理</Title>
        <Space>
          <Select
            allowClear
            placeholder="文章类型"
            style={{ width: 120 }}
            value={typeFilter}
            onChange={setTypeFilter}
            options={[
              { label: '全部', value: undefined },
              { label: '日报', value: 'daily' },
              { label: '周报', value: 'weekly' },
              { label: '月报', value: 'monthly' },
            ]}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 100 }}
            value={statusFilter}
            onChange={setStatusFilter}
            options={[
              { label: '全部', value: undefined },
              { label: '草稿', value: 'draft' },
              { label: '已发布', value: 'published' },
              { label: '失败', value: 'failed' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setGenModalOpen(true)}>
            生成文章
          </Button>
        </Space>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={data?.items || []}
        loading={isLoading}
        pagination={{
          current: page,
          pageSize: 15,
          total: data?.total || 0,
          showTotal: (t) => `共 ${t} 篇`,
          onChange: setPage,
        }}
      />

      <Modal
        title="生成文章"
        open={genModalOpen}
        onCancel={() => setGenModalOpen(false)}
        onOk={handleGenerate}
        confirmLoading={genMutation.isPending}
        okText="开始生成"
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <div style={{ marginBottom: 6 }}>文章类型</div>
            <Select
              style={{ width: '100%' }}
              value={genType}
              onChange={setGenType}
              options={[
                { label: '📅 每日分析（日报）', value: 'daily' },
                { label: '📊 每周分析（周报）', value: 'weekly' },
                { label: '📈 每月分析（月报）', value: 'monthly' },
              ]}
            />
          </div>
          <div>
            <div style={{ marginBottom: 6 }}>
              {genType === 'daily' ? '目标日期' : genType === 'weekly' ? '所在周的任意日期' : '目标月份'}
            </div>
            <DatePicker
              style={{ width: '100%' }}
              value={genDate}
              onChange={setGenDate}
              picker={genType === 'monthly' ? 'month' : 'date'}
            />
          </div>
        </Space>
      </Modal>
    </div>
  )
}
