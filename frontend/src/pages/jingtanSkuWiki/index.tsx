import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Divider, Drawer, Grid, Image, Input, List, Select, Space, Table, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import { jingtanSkuWikiApi, JingtanSkuWikiItem } from '../../api/jingtanSkuWiki'
import { tasksApi } from '../../api/tasks'
import { useAuthStore } from '../../store/auth'

const { Text } = Typography
const { useBreakpoint } = Grid
const FIRST_CATEGORY_OPTIONS = [
  { label: '文化(WH)', value: 'WH' },
  { label: '娱乐(YL)', value: 'YL' },
  { label: '艺术(YS)', value: 'YS' },
  { label: '潮玩(CW)', value: 'CW' },
  { label: '体育(TY)', value: 'TY' },
  { label: '品牌(PP)', value: 'PP' },
  { label: '科技(KJ)', value: 'KJ' },
  { label: 'ACG(ACG)', value: 'ACG' },
  { label: '景区(JQ)', value: 'JQ' },
  { label: '非遗(AFY)', value: 'AFY' },
  { label: '游戏(AYX)', value: 'AYX' },
  { label: '原创设计(AYCSJ)', value: 'AYCSJ' },
  { label: '其他(QT)', value: 'QT' },
]

function prettyJson(raw?: string | null) {
  if (!raw) return ''
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}

function parseImageList(raw?: string | null) {
  if (!raw) return []
  try {
    const list = JSON.parse(raw)
    if (!Array.isArray(list)) return []
    return list.filter((x) => typeof x === 'string')
  } catch {
    return []
  }
}

export default function JingtanSkuWikiPage() {
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const role = useAuthStore((s) => s.role)
  const isAdmin = role === 'admin'

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [search, setSearch] = useState<string | undefined>(undefined)
  const [firstCategory, setFirstCategory] = useState<string | undefined>(undefined)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [runWikiLoading, setRunWikiLoading] = useState(false)
  const [runDetailLoading, setRunDetailLoading] = useState(false)

  const params = useMemo(
    () => ({ page, page_size: pageSize, search, first_category: firstCategory }),
    [page, pageSize, search, firstCategory],
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
          <Space wrap style={{ width: isMobile ? '100%' : 'auto' }}>
            <Select
              allowClear
              placeholder="一级分类"
              style={{ width: isMobile ? '100%' : 180 }}
              options={FIRST_CATEGORY_OPTIONS}
              value={firstCategory}
              onChange={(v) => {
                setFirstCategory(v || undefined)
                setPage(1)
              }}
            />
            <Input.Search
              placeholder="搜索 skuId/名称/作者/机构"
              allowClear
              style={{ width: isMobile ? '100%' : 360 }}
              onSearch={(v) => {
                setSearch(v || undefined)
                setPage(1)
              }}
            />
          </Space>
          <Space>
            <Button loading={isFetching} onClick={() => refetch()}>刷新</Button>
            <Button
              type="primary"
              disabled={!isAdmin}
              loading={runWikiLoading}
              onClick={async () => {
                setRunWikiLoading(true)
                try {
                  const res = await tasksApi.run('crawl_jingtan_sku_wiki')
                  message.success(`已触发爬取，run_id=${res.run_id}，可到任务管理查看日志`)
                } catch (e: any) {
                  message.error(e?.response?.data?.detail || '触发失败')
                } finally {
                  setRunWikiLoading(false)
                }
              }}
            >
              爬取库
            </Button>
            <Button
              disabled={!isAdmin}
              loading={runDetailLoading}
              onClick={async () => {
                setRunDetailLoading(true)
                try {
                  const res = await tasksApi.run('crawl_jingtan_sku_details')
                  message.success(`已触发详情抓取，run_id=${res.run_id}，可到任务管理查看日志`)
                } catch (e: any) {
                  message.error(e?.response?.data?.detail || '触发失败')
                } finally {
                  setRunDetailLoading(false)
                }
              }}
            >
              爬取详情
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
            {(detail.homepage_detail?.mini_file_url || detail.mini_file_url) ? (
              <div style={{ marginBottom: 12 }}>
                <Image
                  src={detail.homepage_detail?.mini_file_url || detail.mini_file_url || ''}
                  width={120}
                  height={120}
                  style={{ borderRadius: 8, objectFit: 'cover' }}
                />
              </div>
            ) : null}
            <div style={{ marginBottom: 8 }}><Text type="secondary">作者：</Text>{detail.author ?? '-'}</div>
            <div style={{ marginBottom: 8 }}><Text type="secondary">机构：</Text>{detail.owner ?? '-'}</div>
            <div style={{ marginBottom: 8 }}><Text type="secondary">分类：</Text>{(detail.first_category_name ?? detail.first_category ?? '-') + ' / ' + (detail.second_category_name ?? detail.second_category ?? '-')}</div>
            <div style={{ marginBottom: 8 }}><Text type="secondary">数量：</Text>{detail.sku_quantity ?? '-'}</div>
            <div style={{ marginBottom: 12 }}><Text type="secondary">发行时间：</Text>{detail.sku_issue_time_ms ? dayjs(detail.sku_issue_time_ms).format('YYYY-MM-DD HH:mm:ss') : '-'}</div>
            <Divider style={{ margin: '12px 0' }} />
            {detail.homepage_detail ? (
              <div>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>详情页数据</div>
                <div style={{ marginBottom: 8 }}>
                  <Text type="secondary">收藏数：</Text>{detail.homepage_detail.collect_num ?? '-'}
                  <Text type="secondary" style={{ marginLeft: 16 }}>评论数：</Text>{detail.homepage_detail.comment_num ?? '-'}
                  <Text type="secondary" style={{ marginLeft: 16 }}>动态数：</Text>{detail.homepage_detail.mini_feed_num ?? '-'}
                </div>
                <div style={{ marginBottom: 8 }}>
                  <Text type="secondary">发行方：</Text>{detail.homepage_detail.producer_name ?? '-'}
                  <Text type="secondary" style={{ marginLeft: 16 }}>认证：</Text>{detail.homepage_detail.certification_name ?? '-'}
                </div>
                <div style={{ marginBottom: 8 }}>
                  <Text type="secondary">背景图：</Text>
                  {detail.homepage_detail.bg_info ? <a href={detail.homepage_detail.bg_info} target="_blank" rel="noreferrer">查看</a> : '-'}
                  <Text type="secondary" style={{ marginLeft: 16 }}>原始资源：</Text>
                  {detail.homepage_detail.origin_file_url ? <a href={detail.homepage_detail.origin_file_url} target="_blank" rel="noreferrer">查看</a> : '-'}
                </div>
                {detail.homepage_detail.sku_desc ? (
                  <div style={{ marginBottom: 10 }}>
                    <Text type="secondary">藏品介绍：</Text>
                    <div style={{ marginTop: 6, whiteSpace: 'pre-wrap', lineHeight: 1.75 }}>{detail.homepage_detail.sku_desc}</div>
                  </div>
                ) : null}
                {parseImageList(detail.homepage_detail.sku_desc_image_file_ids).length > 0 ? (
                  <div style={{ marginBottom: 10 }}>
                    <Text type="secondary">介绍图片：</Text>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                      {parseImageList(detail.homepage_detail.sku_desc_image_file_ids).map((url) => (
                        <Image key={url} src={url} width={88} height={88} style={{ borderRadius: 8, objectFit: 'cover' }} />
                      ))}
                    </div>
                  </div>
                ) : null}
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontWeight: 600, marginBottom: 6 }}>详情原始 JSON</div>
                  <pre style={{ background: '#fafafa', padding: 12, borderRadius: 8, overflow: 'auto' }}>
                    {prettyJson(detail.homepage_detail.raw_json)}
                  </pre>
                </div>
              </div>
            ) : (
              <Tag color="warning">该藏品暂无详情抓取数据，请先运行“爬取详情”任务</Tag>
            )}
            <div style={{ marginTop: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>藏品库原始 JSON</div>
              <pre style={{ background: '#fafafa', padding: 12, borderRadius: 8, overflow: 'auto' }}>
                {prettyJson(detail.raw_json)}
              </pre>
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  )
}

