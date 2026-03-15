import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Card, Descriptions, Spin, Row, Col, Grid, Image, Tag } from 'antd'
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
            </h2>
            <Descriptions
              column={isMobile ? 2 : 4}
              size="small"
              style={{ marginBottom: 16 }}
            >
              <Descriptions.Item label="平台">{data.platform_name ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="IP">{data.ip_name ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="类型">{data.archive_type ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="数量">{data.total_goods_count ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="发行时间">
                {data.issue_time ? dayjs(data.issue_time).format('YYYY-MM-DD') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="可拍卖">
                {data.is_open_auction ? <Tag color="green">是</Tag> : <Tag>否</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="可求购">
                {data.is_open_want_buy ? <Tag color="green">是</Tag> : <Tag>否</Tag>}
              </Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>
      </Card>

      {data.archive_description && (
        <Card title="藏品描述" size="small" style={{ marginTop: 16 }}>
          <p style={{ whiteSpace: 'pre-wrap' }}>{data.archive_description}</p>
        </Card>
      )}
    </div>
  )
}
