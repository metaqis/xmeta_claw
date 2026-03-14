import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Table, Card, Input, DatePicker, Row, Col, Grid, List, Tag, Image, Space, Drawer, Descriptions, Typography, Button } from 'antd'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import { calendarApi, CalendarItem, CalendarParams, CalendarDetail, CalendarRelatedArchiveItem } from '../../api/calendar'

const { useBreakpoint } = Grid
const { Text, Paragraph } = Typography

export default function CalendarPage() {
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const navigate = useNavigate()

  const [params, setParams] = useState<CalendarParams>({ page: 1, page_size: 20 })
  const [open, setOpen] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['calendar', params],
    queryFn: () => calendarApi.list(params),
  })

  const { data: detail, isFetching: detailLoading, refetch: refetchDetail } = useQuery({
    queryKey: ['calendarDetail', selectedId],
    queryFn: () => calendarApi.detail(selectedId as number),
    enabled: selectedId != null && open,
  })

  const openDetail = (id: number) => {
    setSelectedId(id)
    setOpen(true)
  }

  const relatedColumns = useMemo(
    () => [
      {
        title: '藏品',
        key: 'archive',
        render: (_: any, r: CalendarRelatedArchiveItem) => (
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            {r.archive_img ? <Image src={r.archive_img} width={40} height={40} style={{ borderRadius: 6, objectFit: 'cover' }} /> : null}
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 320 }}>
                {r.archive_name || '-'}
              </div>
              <Text type="secondary">{r.associated_archive_id || '-'}</Text>
            </div>
          </div>
        ),
      },
      {
        title: '数量',
        dataIndex: 'total_goods_count',
        key: 'count',
        width: 100,
        render: (v: number | null) => v != null ? v : '-',
      },
      {
        title: '可转赠',
        dataIndex: 'is_transfer',
        key: 'transfer',
        width: 90,
        render: (v: boolean | null) => v ? <Tag color="green">是</Tag> : <Tag>否</Tag>,
      },
      {
        title: '操作',
        key: 'action',
        width: 110,
        render: (_: any, r: CalendarRelatedArchiveItem) => (
          <Button
            size="small"
            disabled={!r.associated_archive_id}
            onClick={() => r.associated_archive_id && navigate(`/archives/${r.associated_archive_id}`)}
          >
            查看
          </Button>
        ),
      },
    ],
    [navigate],
  )

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
            <Card size="small" style={{ marginBottom: 8 }} onClick={() => openDetail(item.id)} hoverable>
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
          onRow={(record) => ({
            onClick: () => openDetail(record.id),
          })}
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

      <Drawer
        title="发行详情"
        open={open}
        onClose={() => setOpen(false)}
        width={isMobile ? '100%' : 980}
        extra={
          <Button loading={detailLoading} onClick={() => refetchDetail()}>
            刷新
          </Button>
        }
      >
        {detail ? (
          <div>
            <Descriptions bordered size="small" column={isMobile ? 1 : 2}>
              <Descriptions.Item label="名称">{detail.name}</Descriptions.Item>
              <Descriptions.Item label="ID">{detail.id}</Descriptions.Item>
              <Descriptions.Item label="发售时间">
                {detail.sell_time ? dayjs(detail.sell_time).format('YYYY-MM-DD HH:mm:ss') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="平台/IP">
                {(detail.platform_name || '-')}/{(detail.ip_name || '-')}
              </Descriptions.Item>
              <Descriptions.Item label="价格/数量">
                {(detail.price != null ? `¥${detail.price}` : '-')}/{(detail.count ?? '-')}
              </Descriptions.Item>
              <Descriptions.Item label="状态">{detail.status ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="优先购时间">
                {detail.priority_purchase_time ? dayjs(detail.priority_purchase_time).format('YYYY-MM-DD HH:mm:ss') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="图片">
                {detail.img ? <Image src={detail.img} width={80} height={80} style={{ borderRadius: 8, objectFit: 'cover' }} /> : '-'}
              </Descriptions.Item>
            </Descriptions>

            <div style={{ marginTop: 16, fontWeight: 600, marginBottom: 8 }}>购买阶段说明</div>
            <Paragraph style={{ whiteSpace: 'pre-wrap' }}>
              {detail.context_condition_text || '-'}
            </Paragraph>

            <div style={{ marginTop: 16, fontWeight: 600, marginBottom: 8 }}>包含藏品</div>
            <Table
              rowKey={(r: CalendarRelatedArchiveItem) => `${r.id ?? ''}-${r.associated_archive_id ?? ''}`}
              dataSource={detail.contain_archives}
              columns={relatedColumns as any}
              size="small"
              pagination={false}
            />

            <div style={{ marginTop: 16, fontWeight: 600, marginBottom: 8 }}>关联藏品</div>
            <Table
              rowKey={(r: CalendarRelatedArchiveItem) => `${r.id ?? ''}-${r.associated_archive_id ?? ''}-a`}
              dataSource={detail.association_archives}
              columns={relatedColumns as any}
              size="small"
              pagination={false}
            />
          </div>
        ) : (
          <Text type="secondary">选择一条发行记录查看详情</Text>
        )}
      </Drawer>
    </div>
  )
}
