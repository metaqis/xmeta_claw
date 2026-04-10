import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Row, Col, Card, Statistic, Table, Select, Tabs, Tag, Spin, DatePicker, Avatar, Typography, Empty,
} from 'antd'
import {
  RiseOutlined, FallOutlined, BarChartOutlined, FireOutlined,
} from '@ant-design/icons'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent, DataZoomComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import dayjs, { Dayjs } from 'dayjs'
import {
  marketStatsApi,
  DailySummaryItem,
  PlaneSnapshotItem,
  IPSnapshotItem,
  ArchiveSnapshotItem,
  TopCategory,
  PlaneCensusItem,
  TopCensusItem,
} from '../../api/marketStats'

echarts.use([
  BarChart, LineChart,
  GridComponent, TooltipComponent, LegendComponent, DataZoomComponent,
  CanvasRenderer,
])

const { Text } = Typography

// ── 工具函数 ──────────────────────────────────────────────────────

function fmtNum(n: number | null | undefined, digits = 0) {
  if (n == null) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  if (abs >= 1e4) return (n / 1e4).toFixed(2) + '万'
  return n.toFixed(digits)
}

function RateTag({ rate }: { rate: number | null | undefined }) {
  if (rate == null) return <Text type="secondary">—</Text>
  const positive = rate >= 0
  return (
    <Tag color={positive ? 'red' : 'green'} icon={positive ? <RiseOutlined /> : <FallOutlined />}>
      {positive ? '+' : ''}{rate.toFixed(2)}%
    </Tag>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────

export default function MarketStatsPage() {
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [activeCategory, setActiveCategory] = useState<string>('')

  // 可用日期列表
  const { data: datesData } = useQuery({
    queryKey: ['market-available-dates'],
    queryFn: marketStatsApi.availableDates,
  })
  const availableDates = datesData?.dates ?? []
  const latestDate = availableDates[0] ?? null
  const queryDate = selectedDate ?? latestDate

  // 近30天汇总趋势
  const { data: summaryList = [], isLoading: summaryLoading } = useQuery({
    queryKey: ['market-summary'],
    queryFn: () => marketStatsApi.summary(),
  })

  // 板块快照
  const { data: planes = [], isLoading: planesLoading } = useQuery({
    queryKey: ['market-planes', queryDate],
    queryFn: () => marketStatsApi.planes({ date: queryDate ?? undefined }),
    enabled: !!queryDate,
  })

  // IP 排行
  const { data: ips = [], isLoading: ipsLoading } = useQuery({
    queryKey: ['market-ips', queryDate],
    queryFn: () => marketStatsApi.ips({ date: queryDate ?? undefined, limit: 30 }),
    enabled: !!queryDate,
  })

  // 行情分类列表
  const { data: topCats = [] as TopCategory[] } = useQuery({
    queryKey: ['market-top-cats', queryDate],
    queryFn: () => marketStatsApi.topCategories({ date: queryDate ?? undefined }),
    enabled: !!queryDate,
  })

  useEffect(() => {
    if (topCats.length > 0 && !activeCategory) {
      setActiveCategory(topCats[0].code)
    }
  }, [topCats, activeCategory])

  // 热门藏品（当前分类）
  const { data: archives = [], isLoading: archivesLoading } = useQuery({
    queryKey: ['market-archives', queryDate, activeCategory],
    queryFn: () => marketStatsApi.archives({ date: queryDate ?? undefined, top_code: activeCategory || undefined }),
    enabled: !!queryDate,
  })

  // 板块涨跌分布普查
  const { data: planeCensus = [] as PlaneCensusItem[] } = useQuery({
    queryKey: ['market-plane-census', queryDate],
    queryFn: () => marketStatsApi.planeCensus({ date: queryDate ?? undefined }),
    enabled: !!queryDate,
  })

  // 行情分类涨跌分布普查
  const { data: topCensus = [] as TopCensusItem[] } = useQuery({
    queryKey: ['market-top-census', queryDate],
    queryFn: () => marketStatsApi.topCensus({ date: queryDate ?? undefined }),
    enabled: !!queryDate,
  })

  // 当前分类的普查数据
  const activeCensus = topCensus.find((c) => c.top_code === activeCategory)

  // 最新一天的汇总
  const todayMeta: DailySummaryItem | undefined = useMemo(() => {
    if (!queryDate || summaryList.length === 0) return undefined
    return summaryList.find((s) => s.stat_date === queryDate) ?? summaryList[summaryList.length - 1]
  }, [summaryList, queryDate])

  // ── 折线图：全市场成交量趋势 ──────────────────────────────────
  const trendOption = useMemo(() => {
    const dates = summaryList.map((s) => s.stat_date.slice(5))
    return {
      tooltip: { trigger: 'axis' as const },
      legend: { data: ['成交量', '总市值(亿)'], textStyle: { fontSize: 11 }, top: 4 },
      grid: { left: 52, right: 52, top: 36, bottom: 40 },
      dataZoom: [
        { type: 'inside' as const, start: summaryList.length > 20 ? 40 : 0, end: 100 },
      ],
      xAxis: {
        type: 'category' as const,
        data: dates,
        axisLabel: { fontSize: 10, rotate: 30 },
      },
      yAxis: [
        { type: 'value' as const, name: '成交量', nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 10 } },
        { type: 'value' as const, name: '市值(亿)', nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 10 } },
      ],
      series: [
        {
          name: '成交量',
          type: 'bar',
          data: summaryList.map((s) => s.total_deal_count ?? 0),
          itemStyle: { color: '#1890ff', borderRadius: [3, 3, 0, 0] },
          barMaxWidth: 24,
        },
        {
          name: '总市值(亿)',
          type: 'line',
          yAxisIndex: 1,
          data: summaryList.map((s) =>
            s.total_market_value ? +(s.total_market_value / 1e8).toFixed(2) : null
          ),
          itemStyle: { color: '#f5a623' },
          smooth: true,
        },
      ],
    }
  }, [summaryList])

  // ── 条形图：板块市值对比 ──────────────────────────────────────
  const planesOption = useMemo(() => {
    const sorted = [...planes].sort((a, b) => (b.total_market_value ?? 0) - (a.total_market_value ?? 0))
    return {
      tooltip: { trigger: 'axis' as const },
      grid: { left: 90, right: 60, top: 12, bottom: 12 },
      xAxis: { type: 'value' as const, axisLabel: { fontSize: 10 } },
      yAxis: {
        type: 'category' as const,
        data: sorted.map((p) => p.plane_name),
        axisLabel: { fontSize: 11, width: 70, overflow: 'truncate' as const },
      },
      series: [
        {
          name: '总市值',
          type: 'bar',
          data: sorted.map((p) => p.total_market_value ?? 0),
          itemStyle: { color: '#722ed1', borderRadius: [0, 3, 3, 0] },
          barMaxWidth: 20,
          label: {
            show: true,
            position: 'right' as const,
            formatter: (params: { value: number }) => fmtNum(params.value),
            fontSize: 10,
          },
        },
      ],
    }
  }, [planes])

  // ── 板块成交量条形图 ─────────────────────────────────────────
  const planesDealOption = useMemo(() => {
    const sorted = [...planes].sort((a, b) => (b.deal_count ?? 0) - (a.deal_count ?? 0))
    return {
      tooltip: { trigger: 'axis' as const },
      grid: { left: 90, right: 60, top: 12, bottom: 12 },
      xAxis: { type: 'value' as const, minInterval: 1, axisLabel: { fontSize: 10 } },
      yAxis: {
        type: 'category' as const,
        data: sorted.map((p) => p.plane_name),
        axisLabel: { fontSize: 11, width: 70, overflow: 'truncate' as const },
      },
      series: [
        {
          name: '成交量',
          type: 'bar',
          data: sorted.map((p) => p.deal_count ?? 0),
          itemStyle: { color: '#52c41a', borderRadius: [0, 3, 3, 0] },
          barMaxWidth: 20,
        },
      ],
    }
  }, [planes])

  // ── IP 成交量柱状图 ───────────────────────────────────────────
  const ipBarOption = useMemo(() => {
    const top15 = ips.slice(0, 15).reverse()
    return {
      tooltip: { trigger: 'axis' as const },
      grid: { left: 130, right: 60, top: 8, bottom: 8 },
      xAxis: { type: 'value' as const, minInterval: 1, axisLabel: { fontSize: 10 } },
      yAxis: {
        type: 'category' as const,
        data: top15.map((ip) => ip.name),
        axisLabel: { fontSize: 11, width: 110, overflow: 'truncate' as const },
      },
      series: [
        {
          name: '成交量',
          type: 'bar',
          data: top15.map((ip) => ip.deal_count ?? 0),
          itemStyle: { color: '#fa8c16', borderRadius: [0, 3, 3, 0] },
          barMaxWidth: 18,
        },
      ],
    }
  }, [ips])

  // ── 板块涨跌分布堆叠图 ──────────────────────────────────────
  const planeUpDownOption = useMemo(() => {
    if (planeCensus.length === 0) return null
    const sorted = [...planeCensus].sort((a, b) => (b.total_deal_count ?? 0) - (a.total_deal_count ?? 0))
    const labels = ['0-3%', '3-5%', '5-7%', '7-10%', '>10%']
    const upSeries = labels.map((lbl, i) => ({
      name: `涨${lbl}`,
      type: 'bar' as const,
      stack: 'up',
      data: sorted.map((p) => {
        const bucket = p.up_down_list.find((b) => b.type === 1 && b.label === lbl.replace('%', ''))
        return bucket?.count ?? 0
      }),
      itemStyle: { color: ['#ff7875', '#ff4d4f', '#f5222d', '#cf1322', '#820014'][i] },
      barMaxWidth: 24,
    }))
    const downSeries = labels.map((lbl, i) => ({
      name: `跌${lbl}`,
      type: 'bar' as const,
      stack: 'down',
      data: sorted.map((p) => {
        const bucket = p.up_down_list.find((b) => b.type === 2 && b.label === lbl.replace('%', ''))
        return -(bucket?.count ?? 0)
      }),
      itemStyle: { color: ['#95de64', '#73d13d', '#52c41a', '#389e0d', '#135200'][i] },
      barMaxWidth: 24,
    }))
    return {
      tooltip: { trigger: 'axis' as const },
      legend: { show: false },
      grid: { left: 85, right: 20, top: 12, bottom: 24 },
      xAxis: {
        type: 'value' as const,
        axisLabel: { fontSize: 10, formatter: (v: number) => Math.abs(v).toString() },
      },
      yAxis: {
        type: 'category' as const,
        data: sorted.map((p) => p.plane_name ?? p.plane_code),
        axisLabel: { fontSize: 11, width: 70, overflow: 'truncate' as const },
      },
      series: [...upSeries, ...downSeries],
    }
  }, [planeCensus])

  // ── 分类涨跌分布图（用于顶部普查 tab）──────────────────────
  const topCensusBarOption = useMemo(() => {
    if (topCensus.length === 0) return null
    return {
      tooltip: { trigger: 'axis' as const },
      legend: { data: ['上涨藏品', '下跌藏品'], textStyle: { fontSize: 11 } },
      grid: { left: 90, right: 40, top: 28, bottom: 12 },
      xAxis: { type: 'value' as const, minInterval: 1, axisLabel: { fontSize: 10 } },
      yAxis: {
        type: 'category' as const,
        data: topCensus.map((c) => c.top_name ?? c.top_code),
        axisLabel: { fontSize: 11, width: 70, overflow: 'truncate' as const },
      },
      series: [
        {
          name: '上涨藏品',
          type: 'bar',
          data: topCensus.map((c) => c.up_archive_count ?? 0),
          itemStyle: { color: '#ff4d4f', borderRadius: [0, 3, 3, 0] },
          barMaxWidth: 18,
        },
        {
          name: '下跌藏品',
          type: 'bar',
          data: topCensus.map((c) => c.down_archive_count ?? 0),
          itemStyle: { color: '#52c41a', borderRadius: [0, 3, 3, 0] },
          barMaxWidth: 18,
        },
      ],
    }
  }, [topCensus])

  // ── 热门藏品表列 ─────────────────────────────────────────────
  const archiveColumns = [
    { title: '排名', dataIndex: 'rank', width: 55, align: 'center' as const },
    {
      title: '藏品',
      render: (_: unknown, r: ArchiveSnapshotItem) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {r.archive_img && (
            <Avatar shape="square" size={36} src={r.archive_img} />
          )}
          <Text style={{ maxWidth: 160 }} ellipsis={{ tooltip: r.archive_name ?? '' }}>
            {r.archive_name ?? r.archive_id}
          </Text>
        </div>
      ),
    },
    {
      title: '成交量',
      dataIndex: 'deal_count',
      align: 'right' as const,
      sorter: (a: ArchiveSnapshotItem, b: ArchiveSnapshotItem) =>
        (a.deal_count ?? 0) - (b.deal_count ?? 0),
      render: (v: number | null) => fmtNum(v),
    },
    {
      title: '总市值',
      dataIndex: 'market_amount',
      align: 'right' as const,
      sorter: (a: ArchiveSnapshotItem, b: ArchiveSnapshotItem) =>
        (a.market_amount ?? 0) - (b.market_amount ?? 0),
      render: (v: number | null) => fmtNum(v),
    },
    {
      title: '市值涨跌',
      dataIndex: 'market_amount_rate',
      align: 'center' as const,
      render: (v: number | null) => <RateTag rate={v} />,
    },
    {
      title: '均价',
      dataIndex: 'avg_amount',
      align: 'right' as const,
      render: (v: number | null) => (v == null ? '—' : `¥${v.toFixed(2)}`),
    },
    {
      title: '均价涨跌',
      dataIndex: 'avg_amount_rate',
      align: 'center' as const,
      render: (v: number | null) => <RateTag rate={v} />,
    },
    {
      title: '最低价',
      dataIndex: 'min_amount',
      align: 'right' as const,
      render: (v: number | null) => (v == null ? '—' : `¥${v.toFixed(2)}`),
    },
    {
      title: '发行量',
      dataIndex: 'publish_count',
      align: 'right' as const,
      render: (v: number | null) => fmtNum(v),
    },
  ]

  // ── IP 表列 ─────────────────────────────────────────────────
  const ipTableColumns = [
    { title: '排名', dataIndex: 'rank', width: 55, align: 'center' as const },
    {
      title: 'IP方',
      render: (_: unknown, r: IPSnapshotItem) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {r.avatar && <Avatar size={28} src={r.avatar} />}
          <Text style={{ maxWidth: 140 }} ellipsis={{ tooltip: r.name }}>{r.name}</Text>
        </div>
      ),
    },
    {
      title: '成交量',
      dataIndex: 'deal_count',
      align: 'right' as const,
      sorter: (a: IPSnapshotItem, b: IPSnapshotItem) => (a.deal_count ?? 0) - (b.deal_count ?? 0),
      render: (v: number | null) => fmtNum(v),
    },
    {
      title: '成交变化',
      dataIndex: 'deal_count_rate',
      align: 'center' as const,
      render: (v: number | null) => <RateTag rate={v} />,
    },
    {
      title: '总市值',
      dataIndex: 'market_amount',
      align: 'right' as const,
      sorter: (a: IPSnapshotItem, b: IPSnapshotItem) => (a.market_amount ?? 0) - (b.market_amount ?? 0),
      render: (v: number | null) => fmtNum(v),
    },
    {
      title: '市值涨跌',
      dataIndex: 'market_amount_rate',
      align: 'center' as const,
      render: (v: number | null) => <RateTag rate={v} />,
    },
    {
      title: '热度',
      dataIndex: 'hot',
      align: 'right' as const,
      render: (v: number | null) => (v == null ? '—' : v.toFixed(2)),
    },
    {
      title: '藏品数',
      dataIndex: 'archive_count',
      align: 'right' as const,
      render: (v: number | null) => fmtNum(v),
    },
  ]

  const isDisabledDate = (d: Dayjs) => {
    return !availableDates.includes(d.format('YYYY-MM-DD'))
  }

  return (
    <div style={{ padding: '12px 12px' }}>
      {/* 标题栏 + 日期选择 */}
      <Row align="middle" gutter={[12, 8]} style={{ marginBottom: 12, flexWrap: 'wrap' }}>
        <Col flex="auto">
          <h2 style={{ margin: 0, fontSize: 'clamp(16px, 4vw, 22px)', whiteSpace: 'nowrap' }}>
            <BarChartOutlined style={{ marginRight: 8 }} />
            市场行情统计
          </h2>
        </Col>
        <Col>
          <DatePicker
            value={queryDate ? dayjs(queryDate) : null}
            disabledDate={isDisabledDate}
            allowClear={false}
            onChange={(d) => setSelectedDate(d ? d.format('YYYY-MM-DD') : null)}
            placeholder="选择快照日期"
            size="small"
          />
        </Col>
      </Row>

      {!queryDate && (
        <Empty description="暂无快照数据，请等待每日 23:50 定时任务执行或手动触发" />
      )}

      {queryDate && (
        <>
          {/* 当日关键指标 */}
          <Row gutter={[10, 10]} style={{ marginBottom: 12 }}>
            <Col xs={12} sm={12} md={6}>
              <Card size="small" style={{ minWidth: 0 }}>
                <Statistic
                  title="全市场成交量"
                  value={todayMeta?.total_deal_count ?? '—'}
                  valueStyle={{ color: '#1890ff', fontSize: 'clamp(16px, 3.5vw, 24px)' }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={12} md={6}>
              <Card size="small" style={{ minWidth: 0 }}>
                <Statistic
                  title="全市场总市值"
                  value={todayMeta?.total_market_value ? fmtNum(todayMeta.total_market_value) : '—'}
                  valueStyle={{ color: '#722ed1', fontSize: 'clamp(16px, 3.5vw, 24px)' }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={12} md={6}>
              <Card size="small" style={{ minWidth: 0 }}>
                <Statistic
                  title="成交最高板块"
                  value={todayMeta?.top_plane_name ?? '—'}
                  valueStyle={{ fontSize: 'clamp(14px, 3vw, 20px)' }}
                />
                {todayMeta?.top_plane_deal_count != null && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    成交 {todayMeta.top_plane_deal_count} 笔
                  </Text>
                )}
              </Card>
            </Col>
            <Col xs={12} sm={12} md={6}>
              <Card size="small" style={{ minWidth: 0 }}>
                <Statistic
                  title="成交最高 IP"
                  value={todayMeta?.top_ip_name ?? '—'}
                  valueStyle={{ fontSize: 'clamp(14px, 3vw, 20px)' }}
                />
                {todayMeta?.top_ip_deal_count != null && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    成交 {todayMeta.top_ip_deal_count} 笔
                  </Text>
                )}{todayMeta?.active_plane_count != null && (
                  <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                    · {todayMeta.active_plane_count} 板块活跃
                  </Text>
                )}
              </Card>
            </Col>
          </Row>

          {/* Tabs */}
          <Tabs
            size="small"
            tabBarStyle={{ marginBottom: 10 }}
            items={[
              {
                key: 'trend',
                label: '市场趋势',
                children: (
                  <Spin spinning={summaryLoading}>
                    <Card title="全市场成交量 & 总市值趋势（近30天）" size="small">
                      {summaryList.length > 0 ? (
                        <ReactEChartsCore
                          echarts={echarts}
                          option={trendOption}
                          style={{ height: 280 }}
                        />
                      ) : (
                        <Empty description="暂无趋势数据" />
                      )}
                    </Card>
                  </Spin>
                ),
              },
              {
                key: 'planes',
                label: '板块行情',
                children: (
                  <Spin spinning={planesLoading}>
                    <Row gutter={[16, 16]}>
                      <Col xs={24} lg={12}>
                        <Card title="板块总市值对比" size="small">
                          {planes.length > 0 ? (
                            <ReactEChartsCore
                              echarts={echarts}
                              option={planesOption}
                              style={{ height: 300 }}
                            />
                          ) : (
                            <Empty description="暂无数据" />
                          )}
                        </Card>
                      </Col>
                      <Col xs={24} lg={12}>
                        <Card title="板块成交量对比" size="small">
                          {planes.length > 0 ? (
                            <ReactEChartsCore
                              echarts={echarts}
                              option={planesDealOption}
                              style={{ height: 300 }}
                            />
                          ) : (
                            <Empty description="暂无数据" />
                          )}
                        </Card>
                      </Col>
                      {planeUpDownOption && (
                        <Col xs={24}>
                          <Card title="板块涨跌分布（红=涨幅区间 绿=跌幅区间）" size="small">
                            <ReactEChartsCore
                              echarts={echarts}
                              option={planeUpDownOption}
                              style={{ height: Math.max(260, planeCensus.length * 34 + 36) }}
                            />
                          </Card>
                        </Col>
                      )}
                      <Col xs={24}>
                        <Card title="板块详情" size="small">
                          <Table<PlaneSnapshotItem>
                            dataSource={planes}
                            rowKey={(r) => r.plane_code}
                            size="small"
                            pagination={false}
                            scroll={{ x: 720 }}
                            columns={[
                              { title: '板块', dataIndex: 'plane_name', width: 120 },
                              {
                                title: '总市值',
                                dataIndex: 'total_market_value',
                                align: 'right' as const,
                                sorter: (a, b) => (a.total_market_value ?? 0) - (b.total_market_value ?? 0),
                                defaultSortOrder: 'descend' as const,
                                render: (v: number | null) => fmtNum(v),
                              },
                              {
                                title: '成交量',
                                dataIndex: 'deal_count',
                                align: 'right' as const,
                                sorter: (a, b) => (a.deal_count ?? 0) - (b.deal_count ?? 0),
                                render: (v: number | null) => fmtNum(v),
                              },
                              {
                                title: '均价涨跌',
                                dataIndex: 'avg_price',
                                align: 'center' as const,
                                render: (v: number | null) => <RateTag rate={v} />,
                              },
                              {
                                title: '最新成交价',
                                dataIndex: 'deal_price',
                                align: 'right' as const,
                                render: (v: number | null) => (v == null ? '—' : `¥${v.toFixed(2)}`),
                              },
                              {
                                title: '挂售率',
                                dataIndex: 'shelves_rate',
                                align: 'right' as const,
                                render: (v: number | null) => (v == null ? '—' : `${v.toFixed(2)}%`),
                              },
                              {
                                title: '上涨/下跌',
                                align: 'center' as const,
                                render: (_: unknown, row: PlaneSnapshotItem) => {
                                  const c = planeCensus.find((p) => p.plane_code === row.plane_code)
                                  if (!c) return <Text type="secondary">—</Text>
                                  return (
                                    <span>
                                      <Text type="danger">{c.up_archive_count ?? 0}↑</Text>
                                      {' / '}
                                      <Text type="success">{c.down_archive_count ?? 0}↓</Text>
                                    </span>
                                  )
                                },
                              },
                            ]}
                          />
                        </Card>
                      </Col>
                    </Row>
                  </Spin>
                ),
              },
              {
                key: 'ips',
                label: 'IP 排行',
                children: (
                  <Spin spinning={ipsLoading}>
                    <Row gutter={[16, 16]}>
                      <Col xs={24} lg={12}>
                        <Card title="IP 成交量 Top 15" size="small">
                          {ips.length > 0 ? (
                            <ReactEChartsCore
                              echarts={echarts}
                              option={ipBarOption}
                              style={{ height: 380 }}
                            />
                          ) : (
                            <Empty description="暂无数据" />
                          )}
                        </Card>
                      </Col>
                      <Col xs={24} lg={12}>
                        <Card title="IP 排行榜详情" size="small">
                          <Table<IPSnapshotItem>
                            dataSource={ips}
                            rowKey="community_ip_id"
                            size="small"
                            pagination={{ pageSize: 15, size: 'small', simple: true }}
                            columns={ipTableColumns}
                            scroll={{ x: 600 }}
                          />
                        </Card>
                      </Col>
                    </Row>
                  </Spin>
                ),
              },
              {
                key: 'archives',
                label: (
                  <span>
                    <FireOutlined />
                    热门藏品
                  </span>
                ),
                children: (
                  <Spin spinning={archivesLoading}>
                    <Row gutter={[16, 16]}>
                      {/* 当前分类成交普查概况 */}
                      {activeCensus && (
                        <Col xs={24}>
                          <Card size="small" style={{ background: '#fafafa' }}>
                            <Row gutter={16}>
                              <Col xs={12} sm={4}>
                                <Statistic
                                  title="分类总市值"
                                  value={fmtNum(activeCensus.total_market_amount)}
                                  valueStyle={{ fontSize: 16, color: '#722ed1' }}
                                />
                                <RateTag rate={activeCensus.total_market_amount_rate} />
                              </Col>
                              <Col xs={12} sm={4}>
                                <Statistic
                                  title="今日成交量"
                                  value={activeCensus.total_deal_count ?? '—'}
                                  valueStyle={{ fontSize: 16, color: '#1890ff' }}
                                />
                                <RateTag rate={activeCensus.total_deal_count_rate} />
                              </Col>
                              <Col xs={12} sm={4}>
                                <Statistic
                                  title="藏品总数"
                                  value={activeCensus.total_archive_count ?? '—'}
                                  valueStyle={{ fontSize: 16 }}
                                />
                              </Col>
                              <Col xs={12} sm={4}>
                                <Statistic
                                  title="上涨藏品"
                                  value={activeCensus.up_archive_count ?? '—'}
                                  valueStyle={{ fontSize: 16, color: '#cf1322' }}
                                />
                              </Col>
                              <Col xs={12} sm={4}>
                                <Statistic
                                  title="下跌藏品"
                                  value={activeCensus.down_archive_count ?? '—'}
                                  valueStyle={{ fontSize: 16, color: '#389e0d' }}
                                />
                              </Col>
                            </Row>
                          </Card>
                        </Col>
                      )}
                      <Col xs={24}>
                        <Card
                          title="热门成交藏品排行"
                          size="small"
                          extra={
                            topCats.length > 0 && (
                              <Select
                                value={activeCategory || topCats[0]?.code}
                                onChange={setActiveCategory}
                                style={{ width: 120 }}
                                size="small"
                                options={topCats.map((c) => ({ label: c.name, value: c.code }))}
                              />
                            )
                          }
                        >
                          {archives.length > 0 ? (
                            <Table<ArchiveSnapshotItem>
                              dataSource={archives.filter(
                                (a) => !activeCategory || a.top_code === activeCategory
                              )}
                              rowKey={(r) => `${r.top_code}-${r.archive_id}`}
                              size="small"
                              pagination={false}
                              columns={archiveColumns}
                              scroll={{ x: 800 }}
                            />
                          ) : (
                            <Empty description="暂无数据" />
                          )}
                        </Card>
                      </Col>
                    </Row>
                  </Spin>
                ),
              },
              {
                key: 'census',
                label: '涨跌全览',
                children: (
                  <Row gutter={[16, 16]}>
                    {topCensusBarOption && (
                      <Col xs={24} lg={14}>
                        <Card title="行情分类涨跌藏品数对比" size="small">
                          <ReactEChartsCore
                            echarts={echarts}
                            option={topCensusBarOption}
                            style={{ height: 280 }}
                          />
                        </Card>
                      </Col>
                    )}
                    <Col xs={24} lg={10}>
                      <Card title="行情分类成交普查" size="small">
                        <Table<TopCensusItem>
                          dataSource={topCensus}
                          rowKey="top_code"
                          size="small"
                          pagination={false}                          scroll={{ x: 500 }}                          columns={[
                            { title: '分类', dataIndex: 'top_name', render: (v: string | null, r: TopCensusItem) => v ?? r.top_code },
                            {
                              title: '成交量',
                              dataIndex: 'total_deal_count',
                              align: 'right' as const,
                              render: (v: number | null) => fmtNum(v),
                            },
                            {
                              title: '成交变化',
                              dataIndex: 'total_deal_count_rate',
                              align: 'center' as const,
                              render: (v: number | null) => <RateTag rate={v} />,
                            },
                            {
                              title: '上涨',
                              dataIndex: 'up_archive_count',
                              align: 'right' as const,
                              render: (v: number | null) => <Text type="danger">{v ?? '—'}</Text>,
                            },
                            {
                              title: '下跌',
                              dataIndex: 'down_archive_count',
                              align: 'right' as const,
                              render: (v: number | null) => <Text type="success">{v ?? '—'}</Text>,
                            },
                            {
                              title: '总市值',
                              dataIndex: 'total_market_amount',
                              align: 'right' as const,
                              render: (v: number | null) => fmtNum(v),
                            },
                          ]}
                        />
                      </Card>
                    </Col>
                    <Col xs={24}>
                      <Card title="板块成交普查" size="small">
                        <Table<PlaneCensusItem>
                          dataSource={planeCensus}
                          rowKey="plane_code"
                          size="small"
                          pagination={false}
                          scroll={{ x: 680 }}
                          columns={[
                            { title: '板块', dataIndex: 'plane_name', render: (v: string | null, r: PlaneCensusItem) => v ?? r.plane_code },
                            {
                              title: '总市值',
                              dataIndex: 'total_market_amount',
                              align: 'right' as const,
                              sorter: (a: PlaneCensusItem, b: PlaneCensusItem) => (a.total_market_amount ?? 0) - (b.total_market_amount ?? 0),
                              defaultSortOrder: 'descend' as const,
                              render: (v: number | null) => fmtNum(v),
                            },
                            {
                              title: '市值涨跌',
                              dataIndex: 'total_market_amount_rate',
                              align: 'center' as const,
                              render: (v: number | null) => <RateTag rate={v} />,
                            },
                            {
                              title: '成交量',
                              dataIndex: 'total_deal_count',
                              align: 'right' as const,
                              render: (v: number | null) => fmtNum(v),
                            },
                            {
                              title: '成交变化',
                              dataIndex: 'total_deal_count_rate',
                              align: 'center' as const,
                              render: (v: number | null) => <RateTag rate={v} />,
                            },
                            {
                              title: '上涨',
                              dataIndex: 'up_archive_count',
                              align: 'right' as const,
                              render: (v: number | null) => <Text type="danger">{v ?? '—'}</Text>,
                            },
                            {
                              title: '下跌',
                              dataIndex: 'down_archive_count',
                              align: 'right' as const,
                              render: (v: number | null) => <Text type="success">{v ?? '—'}</Text>,
                            },
                            {
                              title: '藏品总数',
                              dataIndex: 'total_archive_count',
                              align: 'right' as const,
                              render: (v: number | null) => fmtNum(v),
                            },
                          ]}
                        />
                      </Card>
                    </Col>
                  </Row>
                ),
              },
            ]}
          />
        </>
      )}
    </div>
  )
}
