import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Table, Card, Input, DatePicker, Row, Col, Grid, List, Tag, Image, Space } from 'antd'
import dayjs from 'dayjs'
import { calendarApi, CalendarItem, CalendarParams } from '../../api/calendar'

const { useBreakpoint } = Grid

export default function CalendarPage() {
  const screens = useBreakpoint()
  const isMobile = !screens.md

  const [params, setParams] = useState<CalendarParams>({ page: 1, page_size: 20 })

  const { data, isLoading } = useQuery({
    queryKey: ['calendar', params],
    queryFn: () => calendarApi.list(params),
  })

  const columns = [
    {
      title: '图片',
      dataIndex: 'img',
      key: 'img',
      width: 60,
      render: (v: string | null) => v ? <Image src={v} width={40} height={40} style={{ borderRadius: 4, objectFit: 'cover' }} /> : '-',
    },
    { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
    {
      title: '发售时间',
      dataIndex: 'sell_time',
      key: 'sell_time',
      width: 160,
      render: (v: string | null) => v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      width: 90,
      render: (v: number | null) => v != null ? `¥${v}` : '-',
    },
    { title: '数量', dataIndex: 'count', key: 'count', width: 80 },
    { title: '平台', dataIndex: 'platform_name', key: 'platform', width: 100 },
    { title: 'IP', dataIndex: 'ip_name', key: 'ip', width: 100, ellipsis: true },
    {
      title: '优先购',
      dataIndex: 'is_priority_purchase',
      key: 'priority',
      width: 80,
      render: (v: boolean) => v ? <Tag color="green">是</Tag> : <Tag>否</Tag>,
    },
  ]

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={[12, 12]}>
          <Col xs={24} sm={8} md={6}>
            <DatePicker
              style={{ width: '100%' }}
              placeholder="选择日期"
              onChange={(d) =>
                setParams((p) => ({ ...p, date: d ? d.format('YYYY-MM-DD') : undefined, page: 1 }))
              }
            />
          </Col>
          <Col xs={24} sm={16} md={8}>
            <Input.Search
              placeholder="搜索藏品名称"
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
          renderItem={(item: CalendarItem) => (
            <Card size="small" style={{ marginBottom: 8 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <div style={{ display: 'flex', gap: 12 }}>
                  {item.img && (
                    <Image src={item.img} width={60} height={60} style={{ borderRadius: 8, objectFit: 'cover' }} />
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.name}
                    </div>
                    <div style={{ color: '#999', fontSize: 12, marginTop: 4 }}>
                      {item.sell_time ? dayjs(item.sell_time).format('YYYY-MM-DD HH:mm') : '-'}
                    </div>
                  </div>
                </div>
                <Row gutter={8}>
                  <Col span={8}><span style={{ color: '#999' }}>价格:</span> {item.price != null ? `¥${item.price}` : '-'}</Col>
                  <Col span={8}><span style={{ color: '#999' }}>数量:</span> {item.count ?? '-'}</Col>
                  <Col span={8}>{item.is_priority_purchase && <Tag color="green">优先购</Tag>}</Col>
                </Row>
              </Space>
            </Card>
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
