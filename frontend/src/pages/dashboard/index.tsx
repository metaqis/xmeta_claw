import { useQuery } from '@tanstack/react-query'
import { Row, Col, Card, Statistic, Table, Grid, List, Tag, Spin } from 'antd'
import {
  AppstoreOutlined,
  TeamOutlined,
  CalendarOutlined,
  FireOutlined,
  BankOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { statsApi, TopArchiveItem, TopIPItem } from '../../api/stats'

const { useBreakpoint } = Grid

export default function DashboardPage() {
  const screens = useBreakpoint()
  const isMobile = !screens.md

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: statsApi.dashboard,
  })

  if (isLoading) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />

  const stats = data?.stats
  const topPrice = data?.top_price_archives ?? []
  const topIPs = data?.top_ips ?? []

  const statCards = [
    { title: '藏品总数', value: stats?.total_archives ?? 0, icon: <AppstoreOutlined />, color: '#1890ff' },
    { title: 'IP总数', value: stats?.total_ips ?? 0, icon: <TeamOutlined />, color: '#52c41a' },
    { title: '平台数', value: stats?.total_platforms ?? 0, icon: <BankOutlined />, color: '#722ed1' },
    { title: '今日发行', value: stats?.today_launches ?? 0, icon: <CalendarOutlined />, color: '#fa8c16' },
    { title: '热门藏品', value: stats?.hot_archives ?? 0, icon: <FireOutlined />, color: '#f5222d' },
  ]

  const priceChartOption = {
    tooltip: { trigger: 'axis' as const },
    xAxis: {
      type: 'category' as const,
      data: topPrice.map((a: TopArchiveItem) => a.archive_name.slice(0, 8)),
      axisLabel: { rotate: 30, fontSize: isMobile ? 10 : 12 },
    },
    yAxis: { type: 'value' as const, name: '价格(元)' },
    series: [{
      type: 'bar',
      data: topPrice.map((a: TopArchiveItem) => a.goods_min_price ?? 0),
      itemStyle: { color: '#1890ff', borderRadius: [4, 4, 0, 0] },
    }],
    grid: { left: 50, right: 16, bottom: 60, top: 30 },
  }

  const priceColumns = [
    { title: '藏品', dataIndex: 'archive_name', key: 'name', ellipsis: true },
    {
      title: '最低价',
      dataIndex: 'goods_min_price',
      key: 'price',
      render: (v: number | null) => v != null ? `¥${v}` : '-',
    },
  ]

  return (
    <div>
      <Row gutter={[16, 16]}>
        {statCards.map((s) => (
          <Col xs={12} sm={8} md={8} lg={4} xl={4} key={s.title}>
            <Card size="small">
              <Statistic
                title={s.title}
                value={s.value}
                prefix={<span style={{ color: s.color }}>{s.icon}</span>}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card title="价格排行 TOP 10" size="small">
            <ReactECharts option={priceChartOption} style={{ height: 320 }} />
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title="热门 IP" size="small">
            {isMobile ? (
              <List
                dataSource={topIPs}
                renderItem={(item: TopIPItem, idx: number) => (
                  <List.Item>
                    <List.Item.Meta
                      avatar={<Tag color="blue">{idx + 1}</Tag>}
                      title={item.ip_name}
                      description={`藏品数: ${item.archive_count}`}
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Table
                dataSource={topIPs}
                rowKey="id"
                size="small"
                pagination={false}
                columns={[
                  { title: '排名', render: (_: any, __: any, i: number) => i + 1, width: 60 },
                  { title: 'IP', dataIndex: 'ip_name', key: 'name' },
                  { title: '藏品数', dataIndex: 'archive_count', key: 'count', width: 80 },
                ]}
              />
            )}
          </Card>
        </Col>
      </Row>

      {!isMobile && (
        <Card title="价格排行详情" size="small" style={{ marginTop: 16 }}>
          <Table
            dataSource={topPrice}
            rowKey="archive_id"
            size="small"
            pagination={false}
            columns={priceColumns}
          />
        </Card>
      )}
    </div>
  )
}
