import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Table, Card, Input, Row, Col, Grid, List, Image, Select } from 'antd'
import { archiveApi, ArchiveItem, ArchiveParams } from '../../api/archives'

const { useBreakpoint } = Grid

export default function ArchivesPage() {
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const navigate = useNavigate()

  const [params, setParams] = useState<ArchiveParams>({ page: 1, page_size: 20 })

  const { data, isLoading } = useQuery({
    queryKey: ['archives', params],
    queryFn: () => archiveApi.list(params),
  })

  const goDetail = (id: string) => navigate(`/archives/${id}`)

  const columns = [
    {
      title: '图片',
      dataIndex: 'img',
      key: 'img',
      width: 60,
      render: (v: string | null) => v ? <Image src={v} width={40} height={40} style={{ borderRadius: 4, objectFit: 'cover' }} /> : '-',
    },
    {
      title: '藏品名称',
      dataIndex: 'archive_name',
      key: 'name',
      ellipsis: true,
      render: (v: string, r: ArchiveItem) => (
        <a onClick={() => goDetail(r.archive_id)}>{v}</a>
      ),
    },
    { title: '平台', dataIndex: 'platform_name', key: 'platform', width: 100 },
    { title: 'IP', dataIndex: 'ip_name', key: 'ip', width: 120, ellipsis: true },
    { title: '类型', dataIndex: 'archive_type', key: 'type', width: 120, ellipsis: true },
    { title: '数量', dataIndex: 'total_goods_count', key: 'count', width: 90 },
  ]

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={[12, 12]}>
          <Col xs={24} sm={12} md={8}>
            <Input.Search
              placeholder="搜索藏品"
              allowClear
              onSearch={(v) => setParams((p) => ({ ...p, search: v || undefined, page: 1 }))}
            />
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Select
              style={{ width: '100%' }}
              placeholder="排序"
              allowClear
              options={[
                { label: '最新发行', value: 'time_desc' },
                { label: '最早发行', value: 'time_asc' },
              ]}
              onChange={(v) => setParams((p) => ({ ...p, sort_by: v, page: 1 }))}
            />
          </Col>
        </Row>
      </Card>

      {isMobile ? (
        <List
          loading={isLoading}
          dataSource={data?.items ?? []}
          pagination={{
            total: data?.total ?? 0,
            current: params.page,
            pageSize: params.page_size,
            onChange: (page, pageSize) => setParams((p) => ({ ...p, page, page_size: pageSize })),
            size: 'small',
          }}
          renderItem={(item: ArchiveItem) => (
            <Card
              size="small"
              style={{ marginBottom: 8, cursor: 'pointer' }}
              onClick={() => goDetail(item.archive_id)}
            >
              <div style={{ display: 'flex', gap: 12 }}>
                {item.img && (
                  <Image
                    src={item.img}
                    width={72}
                    height={72}
                    style={{ borderRadius: 8, objectFit: 'cover' }}
                    preview={false}
                  />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.archive_name}
                  </div>
                  <div style={{ color: '#999', fontSize: 12, marginTop: 4 }}>{item.ip_name} · {item.platform_name}</div>
                  <div style={{ color: '#999', fontSize: 12, marginTop: 8 }}>
                    {item.archive_type ?? '-'} · 数量 {item.total_goods_count ?? '-'}
                  </div>
                </div>
              </div>
            </Card>
          )}
        />
      ) : (
        <Table
          loading={isLoading}
          dataSource={data?.items ?? []}
          columns={columns}
          rowKey="archive_id"
          size="small"
          pagination={{
            total: data?.total ?? 0,
            current: params.page,
            pageSize: params.page_size,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (page, pageSize) => setParams((p) => ({ ...p, page, page_size: pageSize })),
          }}
        />
      )}
    </div>
  )
}
