import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Row, Col, Card, Statistic, Table, Grid, List, Tag, Spin } from 'antd'
import {
  AppstoreOutlined,
  TeamOutlined,
  CalendarOutlined,
  BankOutlined,
} from '@ant-design/icons'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { statsApi, RecentArchiveItem, TopIPItem } from '../../api/stats'

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const { useBreakpoint } = Grid

export default function DashboardPage() {
  const screens = useBreakpoint()
  const isMobile = !screens.md

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: statsApi.dashboard,
  })

  const trendOption = useMemo(() => {
    const trend = data?.launch_trend ?? []
    return {
      tooltip: { trigger: 'axis' as const },
      grid: { left: 40, right: 16, top: 16, bottom: 24 },
      xAxis: {
        type: 'category' as const,
        data: trend.map((t) => t.date.slice(5)),
        axisLabel: { fontSize: 11 },
      },
      yAxis: {
        type: 'value' as const,
        minInterval: 1,
        axisLabel: { fontSize: 11 },
      },
      series: [
        {
          type: 'bar',
          data: trend.map((t) => t.count),
          itemStyle: { color: '#1890ff', borderRadius: [3, 3, 0, 0] },
          barMaxWidth: 24,
        },
      ],
    }
  }, [data?.launch_trend])

  const ipBarOption = useMemo(() => {
    const ips = (data?.top_ips ?? []).slice(0, 10).reverse()
    return {
      tooltip: { trigger: 'axis' as const },
      grid: { left: 100, right: 24, top: 8, bottom: 24 },
      xAxis: {
        type: 'value' as const,
        minInterval: 1,
        axisLabel: { fontSize: 11 },
      },
      yAxis: {
        type: 'category' as const,
        data: ips.map((ip) => ip.ip_name),
        axisLabel: { fontSize: 11, width: 80, overflow: 'truncate' as const },
      },
      series: [
        {
          type: 'bar',
          data: ips.map((ip) => ip.archive_count),
          itemStyle: { color: '#52c41a', borderRadius: [0, 3, 3, 0] },
          barMaxWidth: 20,
        },
      ],
    }
  }, [data?.top_ips])

  if (isLoading) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />

  const stats = data?.stats
  const recent = data?.recent_archives ?? []
  const topIPs = data?.top_ips ?? []

  const statCards = [
    { title: '藏品总数', value: stats?.total_archives ?? 0, icon: <AppstoreOutlined />, color: '#1890ff' },
    { title: 'IP总数', value: stats?.total_ips ?? 0, icon: <TeamOutlined />, color: '#52c41a' },
    { title: '平台数', value: stats?.total_platforms ?? 0, icon: <BankOutlined />, color: '#722ed1' },
    { title: '今日发行', value: stats?.today_launches ?? 0, icon: <CalendarOutlined />, color: '#fa8c16' },
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

      {/* 发行趋势图 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card title="近 30 天发行趋势" size="small">
            <ReactEChartsCore
              echarts={echarts}
              option={trendOption}
              style={{ height: isMobile ? 200 : 260 }}
              notMerge
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card title="最新藏品" size="small">
            {isMobile ? (
              <List
                dataSource={recent}
                renderItem={(item: RecentArchiveItem) => (
                  <List.Item>
                    <List.Item.Meta
                      avatar={<Tag color="blue">NEW</Tag>}
                      title={item.archive_name}
                      description={item.archive_id}
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Table
                dataSource={recent}
                rowKey="archive_id"
                size="small"
                pagination={false}
                columns={[
                  { title: '藏品', dataIndex: 'archive_name', key: 'name', ellipsis: true },
                  { title: 'ID', dataIndex: 'archive_id', key: 'id', width: 140 },
                ]}
              />
            )}
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title="热门 IP TOP 10" size="small">
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
              <ReactEChartsCore
                echarts={echarts}
                option={ipBarOption}
                style={{ height: 300 }}
                notMerge
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
