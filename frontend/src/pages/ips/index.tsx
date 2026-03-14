import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Table, Card, Input, Row, Col, Grid, List, Avatar } from 'antd'
import { ipApi, IPItem, IPParams } from '../../api/ips'

const { useBreakpoint } = Grid

export default function IPsPage() {
  const screens = useBreakpoint()
  const isMobile = !screens.md

  const [params, setParams] = useState<IPParams>({ page: 1, page_size: 20 })

  const { data, isLoading } = useQuery({
    queryKey: ['ips', params],
    queryFn: () => ipApi.list(params),
  })

  const columns = [
    {
      title: '头像',
      dataIndex: 'ip_avatar',
      key: 'avatar',
      width: 60,
      render: (v: string | null) => <Avatar src={v} size="small">{!v ? 'IP' : ''}</Avatar>,
    },
    { title: 'IP名称', dataIndex: 'ip_name', key: 'name', ellipsis: true },
    { title: '平台', dataIndex: 'platform_name', key: 'platform', width: 120 },
    { title: '粉丝', dataIndex: 'fans_count', key: 'fans', width: 90 },
    { title: '藏品数', dataIndex: 'archive_count', key: 'count', width: 90, sorter: (a: IPItem, b: IPItem) => a.archive_count - b.archive_count },
  ]

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={[12, 12]}>
          <Col xs={24} sm={12} md={8}>
            <Input.Search
              placeholder="搜索IP名称"
              allowClear
              onSearch={(v) => setParams((p) => ({ ...p, search: v || undefined, page: 1 }))}
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
          renderItem={(item: IPItem) => (
            <List.Item>
              <List.Item.Meta
                avatar={<Avatar src={item.ip_avatar} size={40}>{!item.ip_avatar ? item.ip_name[0] : ''}</Avatar>}
                title={item.ip_name}
                description={`${item.platform_name ?? '未知平台'} · 粉丝 ${item.fans_count ?? '-'} · 藏品 ${item.archive_count} 个`}
              />
            </List.Item>
          )}
        />
      ) : (
        <Table
          loading={isLoading}
          dataSource={data?.items ?? []}
          columns={columns}
          rowKey="id"
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
