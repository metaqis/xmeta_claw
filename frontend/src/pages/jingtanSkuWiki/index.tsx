import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Drawer, Grid, Image, Input, List, Space, Table, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import { jingtanSkuWikiApi, JingtanSkuWikiItem } from '../../api/jingtanSkuWiki'
import { tasksApi } from '../../api/tasks'
import { useAuthStore } from '../../store/auth'

const { Text } = Typography
const { useBreakpoint } = Grid

export default function JingtanSkuWikiPage() {
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const role = useAuthStore((s) => s.role)
  const isAdmin = role === 'admin'

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [search, setSearch] = useState<string | undefined>(undefined)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [runLoading, setRunLoading] = useState(false)

  const params = useMemo(
    () => ({ page, page_size: pageSize, search }),
    [page, pageSize, search],
  )

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['jingtanSkuWikis', params],
    queryFn: () => jingtanSkuWikiApi.list(params),
  })

  const items = data?.items ?? []

  const { data: detail, isFetching: detailFetching } = useQuery({
    queryKey: ['jingtanSkuWikiDetail', detailId],
    queryFn: () => jingtanSkuWikiApi.detail(detailId!),
    enabled: !!detailId && detailOpen,
  })

  const openDetail = (r: JingtanSkuWikiItem) => {
    setDetailId(r.sku_id)
    setDetailOpen(true)
  }

  const columns = [
    {
      title: '图片',
      dataIndex: 'mini_file_url',
      key: 'img',
      width: 60,
      render: (v: string | null) => v ? <Image src={v} width={40} height={40} style={{ borderRadius: 4, objectFit: 'cover' }} /> : '-',
    },
    {
      title: '藏品名称',
      dataIndex: 'sku_name',
      key: 'sku_name',
      ellipsis: true,
      render: (v: string, r: JingtanSkuWikiItem) => <a onClick={() => openDetail(r)}>{v}</a>,
    },
    { title: '作者', dataIndex: 'author', key: 'author', width: 140, ellipsis: true },
    { title: '分类', key: 'cat', width: 220, render: (_: any, r: JingtanSkuWikiItem) => (
      <div>
        <div>{r.first_category_name ?? r.first_category ?? '-'}</div>
        <Text type="secondary">{r.second_category_name ?? r.second_category ?? '-'}</Text>
      </div>
    ) },
    { title: '数量', dataIndex: 'sku_quantity', key: 'qty', width: 90 },
    { title: '发行时间', key: 'issue', width: 180, render: (_: any, r: JingtanSkuWikiItem) => (
      r.sku_issue_time_ms ? dayjs(r.sku_issue_time_ms).format('YYYY-MM-DD HH:mm:ss') : '-'
    ) },
    { title: '更新', dataIndex: 'updated_at', key: 'updated_at', width: 180, render: (v: string | null) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-' },
  ]

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
          <Input.Search
            placeholder="搜索 skuId/名称/作者/机构"
            allowClear
            style={{ width: isMobile ? '100%' : 360 }}
            onSearch={(v) => {
              setSearch(v || undefined)
              setPage(1)
            }}
          />
          <Space>
            <Button loading={isFetching} onClick={() => refetch()}>刷新</Button>
            <Button
              type="primary"
              disabled={!isAdmin}
              loading={runLoading}
              onClick={async () => {
                setRunLoading(true)
                try {
                  const res = await tasksApi.run('crawl_jingtan_sku_wiki')
                  message.success(`已触发爬取，run_id=${res.run_id}，可到任务管理查看日志`)
                } catch (e: any) {
                  message.error(e?.response?.data?.detail || '触发失败')
                } finally {
                  setRunLoading(false)
                }
              }}
            >
              爬取更新
            </Button>
          </Space>
        </Space>
        {!isAdmin ? (
          <div style={{ marginTop: 10 }}>
            <Tag>仅管理员可触发爬虫任务</Tag>
          </div>
        ) : null}
      </Card>

      {isMobile ? (
        <List
          loading={isFetching}
          dataSource={items}
          pagination={{
            total: data?.total ?? 0,
            current: page,
            pageSize,
            onChange: (p, ps) => {
              setPage(p)
              setPageSize(ps)
            },
            size: 'small',
          }}
          renderItem={(r: JingtanSkuWikiItem) => (
            <Card size="small" style={{ marginBottom: 8, cursor: 'pointer' }} onClick={() => openDetail(r)}>
              <div style={{ display: 'flex', gap: 12 }}>
                {r.mini_file_url ? (
                  <Image
                    src={r.mini_file_url}
                    width={72}
                    height={72}
                    style={{ borderRadius: 8, objectFit: 'cover' }}
                    preview={false}
                  />
                ) : null}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {r.sku_name}
                  </div>
                  <div style={{ color: '#999', fontSize: 12, marginTop: 4 }}>
                    {r.author ?? '-'} · {r.owner ?? '-'}
                  </div>
                  <div style={{ color: '#999', fontSize: 12, marginTop: 8 }}>
                    {(r.first_category_name ?? r.first_category ?? '-') + ' / ' + (r.second_category_name ?? r.second_category ?? '-')}
                  </div>
                </div>
              </div>
            </Card>
          )}
        />
      ) : (
        <Table
          loading={isFetching}
          dataSource={items}
          columns={columns as any}
          rowKey="sku_id"
          size="small"
          scroll={{ x: 1000 }}
          pagination={{
            total: data?.total ?? 0,
            current: page,
            pageSize,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => {
              setPage(p)
              setPageSize(ps)
            },
          }}
        />
      )}

      <Drawer
        title={detail ? `${detail.sku_name} (${detail.sku_id})` : '详情'}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width={isMobile ? '100%' : 860}
      >
        {detailFetching ? <Text>加载中...</Text> : null}
        {detail ? (
          <div>
            {detail.mini_file_url ? (
              <div style={{ marginBottom: 12 }}>
                <Image src={detail.mini_file_url} width={120} height={120} style={{ borderRadius: 8, objectFit: 'cover' }} />
              </div>
            ) : null}
            <div style={{ marginBottom: 8 }}><Text type="secondary">作者：</Text>{detail.author ?? '-'}</div>
            <div style={{ marginBottom: 8 }}><Text type="secondary">机构：</Text>{detail.owner ?? '-'}</div>
            <div style={{ marginBottom: 8 }}><Text type="secondary">分类：</Text>{(detail.first_category_name ?? detail.first_category ?? '-') + ' / ' + (detail.second_category_name ?? detail.second_category ?? '-')}</div>
            <div style={{ marginBottom: 8 }}><Text type="secondary">数量：</Text>{detail.sku_quantity ?? '-'}</div>
            <div style={{ marginBottom: 12 }}><Text type="secondary">发行时间：</Text>{detail.sku_issue_time_ms ? dayjs(detail.sku_issue_time_ms).format('YYYY-MM-DD HH:mm:ss') : '-'}</div>
            <div style={{ marginTop: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>原始 JSON</div>
              <pre style={{ background: '#fafafa', padding: 12, borderRadius: 8, overflow: 'auto' }}>
                {detail.raw_json ? JSON.stringify(JSON.parse(detail.raw_json), null, 2) : ''}
              </pre>
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  )
}

