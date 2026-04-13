import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Row, Col, Card, Statistic, Table, Grid, List, Tag, Spin, Segmented, Empty, Typography, Avatar } from 'antd'
import {
  AppstoreOutlined,
  TeamOutlined,
  CalendarOutlined,
  BankOutlined,
} from '@ant-design/icons'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import dayjs from 'dayjs'
import {
  statsApi,
  CalendarCardItem,
  RecentArchiveItem,
  TrendPoint,
  PlaneTrendItem,
  IPTrendItem,
} from '../../api/stats'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, CanvasRenderer])

const { useBreakpoint } = Grid
const { Text } = Typography

const RANGE_OPTIONS = [
  { label: '近7天', value: 7 },
  { label: '近30天', value: 30 },
  { label: '近90天', value: 90 },
]

/** 智能数值格式化：>=1亿→X.XX亿，>=1万→X.XX万，否则原样 */
function fmtNum(v: number | null | undefined, suffix = ''): string {
  if (v == null) return '-'
  if (Math.abs(v) >= 1_0000_0000) return `${(v / 1_0000_0000).toFixed(2)}亿${suffix}`
  if (Math.abs(v) >= 1_0000) return `${(v / 1_0000).toFixed(2)}万${suffix}`
  return `${v.toLocaleString()}${suffix}`
}

/** 根据数据集自动决定 Y 轴单位 */
function autoUnit(values: (number | null | undefined)[]): { divisor: number; label: string } {
  const max = Math.max(...values.filter((v): v is number => v != null).map(Math.abs), 0)
  if (max >= 1_0000_0000) return { divisor: 1_0000_0000, label: '(亿)' }
  if (max >= 1_0000) return { divisor: 1_0000, label: '(万)' }
  return { divisor: 1, label: '' }
}

/** 通用单线图配置 */
function singleLineOption(points: TrendPoint[], color: string, isMobile: boolean) {
  const dates = points.map((p) => p.date.slice(5))
  const values = points.map((p) => p.value)
  const { divisor, label } = autoUnit(values)
  return {
    tooltip: {
      trigger: 'axis' as const,
      valueFormatter: (v: number) => fmtNum(v),
    },
    grid: { left: isMobile ? 52 : 60, right: 16, top: label ? 28 : 16, bottom: 24 },
    xAxis: { type: 'category' as const, data: dates, axisLabel: { fontSize: 11 } },
    yAxis: {
      type: 'value' as const,
      name: label,
      nameTextStyle: { fontSize: 11, padding: [0, 0, 0, 4] },
      axisLabel: {
        fontSize: 11,
        formatter: (v: number) => divisor > 1 ? (v / divisor).toFixed(1) : v.toLocaleString(),
      },
    },
    series: [
      {
        type: 'line',
        data: values,
        smooth: true,
        symbol: 'circle',
        symbolSize: isMobile ? 4 : 6,
        lineStyle: { color },
        itemStyle: { color },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: color + '40' },
          { offset: 1, color: color + '05' },
        ]) },
      },
    ],
  }
}

/** 通用多线图配置 */
function multiLineOption(
  series: { name: string; points: TrendPoint[] }[],
  isMobile: boolean,
) {
  const dateSet = new Set<string>()
  series.forEach((s) => s.points.forEach((p) => dateSet.add(p.date)))
  const dates = [...dateSet].sort()
  const colors = ['#1890ff', '#52c41a', '#faad14', '#f5222d', '#722ed1', '#13c2c2']

  const allValues = series.flatMap((s) => s.points.map((p) => p.value))
  const { divisor, label } = autoUnit(allValues)

  return {
    tooltip: {
      trigger: 'axis' as const,
      valueFormatter: (v: number) => fmtNum(v),
    },
    legend: {
      data: series.map((s) => s.name),
      bottom: 0,
      type: 'scroll' as const,
      textStyle: { fontSize: 11 },
    },
    grid: { left: isMobile ? 52 : 60, right: 16, top: label ? 28 : 16, bottom: isMobile ? 40 : 36 },
    xAxis: {
      type: 'category' as const,
      data: dates.map((d) => d.slice(5)),
      axisLabel: { fontSize: 11 },
    },
    yAxis: {
      type: 'value' as const,
      name: label,
      nameTextStyle: { fontSize: 11, padding: [0, 0, 0, 4] },
      axisLabel: {
        fontSize: 11,
        formatter: (v: number) => divisor > 1 ? (v / divisor).toFixed(1) : v.toLocaleString(),
      },
    },
    series: series.map((s, i) => {
      const valueMap = new Map(s.points.map((p) => [p.date, p.value]))
      return {
        name: s.name,
        type: 'line',
        data: dates.map((d) => valueMap.get(d) ?? null),
        smooth: true,
        symbol: 'circle',
        symbolSize: isMobile ? 3 : 5,
        lineStyle: { color: colors[i % colors.length] },
        itemStyle: { color: colors[i % colors.length] },
      }
    }),
  }
}

export default function DashboardPage() {
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const [days, setDays] = useState(7)

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard', days],
    queryFn: () => statsApi.dashboard(days),
    refetchInterval: 60_000,
  })

  const stats = data?.stats
  const calendar = data?.today_calendar ?? []
  const recent = data?.recent_archives ?? []
  const marketValue = data?.market_value_trend ?? []
  const dealCount = data?.deal_count_trend ?? []
  const planeTrends = data?.plane_trends ?? []
  const ipTrends = data?.ip_trends ?? []

  const mvOption = useMemo(() => singleLineOption(marketValue, '#1890ff', isMobile), [marketValue, isMobile])
  const dcOption = useMemo(() => singleLineOption(dealCount, '#faad14', isMobile), [dealCount, isMobile])
  const planeOption = useMemo(
    () => multiLineOption(planeTrends.map((p) => ({ name: p.plane_name, points: p.points })), isMobile),
    [planeTrends, isMobile],
  )
  const ipOption = useMemo(
    () => multiLineOption(ipTrends.map((p) => ({ name: p.name, points: p.points })), isMobile),
    [ipTrends, isMobile],
  )

  if (isLoading) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />

  const statCards = [
    { title: '藏品总数', value: stats?.total_archives ?? 0, icon: <AppstoreOutlined />, color: '#1890ff' },
    { title: 'IP总数', value: stats?.total_ips ?? 0, icon: <TeamOutlined />, color: '#52c41a' },
    { title: '平台数', value: stats?.total_platforms ?? 0, icon: <BankOutlined />, color: '#722ed1' },
    { title: '今日发行', value: stats?.today_launches ?? 0, icon: <CalendarOutlined />, color: '#fa8c16' },
  ]

  const chartHeight = isMobile ? 220 : 280

  return (
    <div>
      {/* ── 顶部统计卡片 ── */}
      <Row gutter={[12, 12]}>
        {statCards.map((s) => (
          <Col xs={12} sm={8} md={6} lg={6} xl={6} key={s.title}>
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

      {/* ── 今日发售日历 + 最近藏品 ── */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} lg={14}>
          <Card title="今日发售日历" size="small">
            {calendar.length === 0 ? (
              <Empty description="今天暂无发售" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : isMobile ? (
              <List
                dataSource={calendar}
                renderItem={(item: CalendarCardItem) => (
                  <List.Item>
                    <List.Item.Meta
                      avatar={item.img ? <Avatar shape="square" size={48} src={item.img} /> : undefined}
                      title={item.name}
                      description={
                        <>
                          {item.sell_time ? <Tag color="orange">{dayjs(item.sell_time).format('HH:mm')}</Tag> : null}
                          {item.price != null ? <Tag>¥{item.price}</Tag> : null}
                          {item.count != null ? <Tag>限量 {item.count}</Tag> : null}
                          {item.ip_name ? <Text type="secondary"> · {item.ip_name}</Text> : null}
                        </>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Table
                dataSource={calendar}
                rowKey="id"
                size="small"
                pagination={false}
                scroll={{ x: 600 }}
                columns={[
                  {
                    title: '藏品',
                    dataIndex: 'name',
                    key: 'name',
                    ellipsis: true,
                    render: (name: string, r: CalendarCardItem) => (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        {r.img ? <Avatar shape="square" size={32} src={r.img} /> : null}
                        <span>{name}</span>
                      </div>
                    ),
                  },
                  {
                    title: '时间',
                    dataIndex: 'sell_time',
                    key: 'time',
                    width: 80,
                    render: (v: string | null) => v ? dayjs(v).format('HH:mm') : '-',
                  },
                  { title: '价格', dataIndex: 'price', key: 'price', width: 80, render: (v: number | null) => v != null ? `¥${v}` : '-' },
                  { title: '数量', dataIndex: 'count', key: 'count', width: 80 },
                  { title: 'IP', dataIndex: 'ip_name', key: 'ip', width: 120, ellipsis: true },
                ]}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="最近更新藏品" size="small">
            <List
              dataSource={recent}
              renderItem={(item: RecentArchiveItem) => (
                <List.Item>
                  <List.Item.Meta
                    avatar={item.img ? <Avatar shape="square" size={40} src={item.img} /> : <Tag color="blue">NEW</Tag>}
                    title={item.archive_name}
                    description={
                      <>
                        <Text type="secondary">{item.archive_id}</Text>
                        {item.ip_name ? <Text type="secondary"> · {item.ip_name}</Text> : null}
                      </>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      {/* ── 时间范围切换 ── */}
      <Row style={{ marginTop: 16, marginBottom: 4 }}>
        <Col>
          <Segmented
            options={RANGE_OPTIONS}
            value={days}
            onChange={(v) => setDays(v as number)}
          />
        </Col>
      </Row>

      {/* ── 全市场市值趋势 ── */}
      <Row gutter={[12, 12]} style={{ marginTop: 8 }}>
        <Col xs={24} lg={12}>
          <Card title="全市场总市值" size="small">
            {marketValue.length ? (
              <ReactEChartsCore echarts={echarts} option={mvOption} style={{ height: chartHeight }} notMerge />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="全市场成交量" size="small">
            {dealCount.length ? (
              <ReactEChartsCore echarts={echarts} option={dcOption} style={{ height: chartHeight }} notMerge />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
            )}
          </Card>
        </Col>
      </Row>

      {/* ── 板块市值趋势 ── */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col span={24}>
          <Card title="板块市值趋势 TOP 6" size="small">
            {planeTrends.length ? (
              <ReactEChartsCore echarts={echarts} option={planeOption} style={{ height: chartHeight }} notMerge />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
            )}
          </Card>
        </Col>
      </Row>

      {/* ── 热门 IP 市值趋势 ── */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col span={24}>
          <Card title="热门 IP 市值趋势 TOP 6" size="small">
            {ipTrends.length ? (
              <ReactEChartsCore echarts={echarts} option={ipOption} style={{ height: chartHeight }} notMerge />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
