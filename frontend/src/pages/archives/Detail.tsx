import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Card, Descriptions, Tag, Spin, Row, Col, Grid, Image, Statistic } from 'antd'
import { FireOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'
import { archiveApi } from '../../api/archives'

const { useBreakpoint } = Grid

export default function ArchiveDetailPage() {
  const { id } = useParams<{ id: string }>()
  const screens = useBreakpoint()
  const isMobile = !screens.md

  const { data, isLoading } = useQuery({
    queryKey: ['archive-detail', id],
    queryFn: () => archiveApi.detail(id!),
    enabled: !!id,
  })

  if (isLoading) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />
  if (!data) return <div>未找到藏品</div>

  const priceHistory = data.price_history ?? []

  const priceChartOption = {
    tooltip: {
      trigger: 'axis' as const,
      formatter: (params: any) => {
        const p = params[0]
        return `${p.axisValue}<br/>最低价: ¥${p.value}`
      },
    },
    xAxis: {
      type: 'category' as const,
      data: priceHistory.map((h) => dayjs(h.record_time).format('MM-DD HH:mm')),
      axisLabel: { rotate: 30, fontSize: 10 },
    },
    yAxis: { type: 'value' as const, name: '价格(元)' },
    series: [{
      type: 'line',
      data: priceHistory.map((h) => h.min_price),
      smooth: true,
      areaStyle: { color: 'rgba(24,144,255,0.15)' },
      lineStyle: { color: '#1890ff' },
      itemStyle: { color: '#1890ff' },
    }],
    grid: { left: 50, right: 16, bottom: 60, top: 30 },
    dataZoom: priceHistory.length > 50 ? [{ type: 'inside' }, { type: 'slider' }] : [],
  }

  const dealChartOption = {
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['挂单', '求购', '成交'] },
    xAxis: {
      type: 'category' as const,
      data: priceHistory.map((h) => dayjs(h.record_time).format('MM-DD HH:mm')),
      axisLabel: { rotate: 30, fontSize: 10 },
    },
    yAxis: { type: 'value' as const },
    series: [
      { name: '挂单', type: 'line', data: priceHistory.map((h) => h.sell_count), smooth: true },
      { name: '求购', type: 'line', data: priceHistory.map((h) => h.buy_count), smooth: true },
      { name: '成交', type: 'line', data: priceHistory.map((h) => h.deal_count), smooth: true },
    ],
    grid: { left: 50, right: 16, bottom: 60, top: 40 },
  }

  return (
    <div>
      <Card size="small">
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={8} md={6}>
            {data.img && (
              <Image
                src={data.img}
                style={{ width: '100%', maxWidth: 240, borderRadius: 12 }}
              />
            )}
          </Col>
          <Col xs={24} sm={16} md={18}>
            <h2 style={{ marginBottom: 8 }}>
              {data.archive_name}
              {data.is_hot && <Tag color="red" style={{ marginLeft: 8 }}><FireOutlined /> 热门</Tag>}
            </h2>
            <Descriptions
              column={isMobile ? 2 : 4}
              size="small"
              style={{ marginBottom: 16 }}
            >
              <Descriptions.Item label="平台">{data.platform_name ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="IP">{data.ip_name ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="类型">{data.archive_type ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="发行时间">
                {data.issue_time ? dayjs(data.issue_time).format('YYYY-MM-DD') : '-'}
              </Descriptions.Item>
            </Descriptions>

            <Row gutter={[16, 12]}>
              <Col xs={8} md={4}>
                <Statistic
                  title="最低价"
                  value={data.goods_min_price ?? '-'}
                  prefix="¥"
                  valueStyle={{ color: '#f5222d', fontSize: isMobile ? 16 : 20 }}
                />
              </Col>
              <Col xs={8} md={4}>
                <Statistic title="挂单" value={data.selling_count} valueStyle={{ fontSize: isMobile ? 16 : 20 }} />
              </Col>
              <Col xs={8} md={4}>
                <Statistic title="成交" value={data.deal_count} valueStyle={{ fontSize: isMobile ? 16 : 20 }} />
              </Col>
              <Col xs={8} md={4}>
                <Statistic title="求购" value={data.want_buy_count} valueStyle={{ fontSize: isMobile ? 16 : 20 }} />
              </Col>
              <Col xs={8} md={4}>
                <Statistic
                  title="求购最高"
                  value={data.want_buy_max_price ?? '-'}
                  prefix="¥"
                  valueStyle={{ fontSize: isMobile ? 16 : 20 }}
                />
              </Col>
              <Col xs={8} md={4}>
                <Statistic
                  title="成交价"
                  value={data.deal_price ?? '-'}
                  prefix="¥"
                  valueStyle={{ fontSize: isMobile ? 16 : 20 }}
                />
              </Col>
            </Row>
          </Col>
        </Row>
      </Card>

      {data.archive_description && (
        <Card title="藏品描述" size="small" style={{ marginTop: 16 }}>
          <p style={{ whiteSpace: 'pre-wrap' }}>{data.archive_description}</p>
        </Card>
      )}

      {priceHistory.length > 0 && (
        <>
          <Card title="价格趋势" size="small" style={{ marginTop: 16 }}>
            <ReactECharts option={priceChartOption} style={{ height: isMobile ? 260 : 360 }} />
          </Card>
          <Card title="交易趋势" size="small" style={{ marginTop: 16 }}>
            <ReactECharts option={dealChartOption} style={{ height: isMobile ? 260 : 360 }} />
          </Card>
        </>
      )}
    </div>
  )
}
