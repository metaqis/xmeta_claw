import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import { EditOutlined, HistoryOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { tasksApi, TaskItem, TaskRunItem, TaskRunLogItem } from '../../api/tasks'
import { useAuthStore } from '../../store/auth'

const { Text } = Typography

function formatSchedule(t: TaskItem) {
  if (t.schedule_type === 'cron') return t.cron || '-'
  const sec = t.interval_seconds || 0
  if (sec % 3600 === 0) return `${sec / 3600} 小时`
  if (sec % 60 === 0) return `${sec / 60} 分钟`
  return `${sec} 秒`
}

function statusTag(status: string) {
  if (status === 'success') return <Tag color="green">成功</Tag>
  if (status === 'failed') return <Tag color="red">失败</Tag>
  if (status === 'running') return <Tag color="blue">运行中</Tag>
  if (status === 'cancelling') return <Tag color="orange">停止中</Tag>
  if (status === 'cancelled') return <Tag color="default">已停止</Tag>
  if (status === 'queued') return <Tag color="default">排队中</Tag>
  return <Tag>{status}</Tag>
}

export default function TasksPage() {
  const qc = useQueryClient()
  const role = useAuthStore((s) => s.role)
  const isAdmin = role === 'admin'

  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<TaskItem | null>(null)
  const [runsOpen, setRunsOpen] = useState(false)
  const [runsTask, setRunsTask] = useState<TaskItem | null>(null)
  const [runsPage, setRunsPage] = useState(1)
  const [runsPageSize, setRunsPageSize] = useState(20)
  const [logsOpen, setLogsOpen] = useState(false)
  const [logsRun, setLogsRun] = useState<TaskRunItem | null>(null)
  const [logsPage, setLogsPage] = useState(1)
  const [logsPageSize, setLogsPageSize] = useState(200)

  const [form] = Form.useForm()
  const scheduleType = Form.useWatch('schedule_type', form)

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['tasks'],
    queryFn: tasksApi.list,
    refetchInterval: 5000,
  })

  const items = data?.items ?? []

  const updateMutation = useMutation({
    mutationFn: ({ taskId, data }: { taskId: string; data: any }) => tasksApi.update(taskId, data),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['tasks'] })
      message.success('已更新')
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '更新失败'),
  })

  const runMutation = useMutation({
    mutationFn: (taskId: string) => tasksApi.run(taskId),
    onSuccess: async (res) => {
      await qc.invalidateQueries({ queryKey: ['tasks'] })
      message.success(`已触发，run_id=${res.run_id}`)
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || '触发失败'),
  })

  const runsQueryEnabled = runsOpen && !!runsTask
  const runsQueryKey = useMemo(
    () => ['taskRuns', runsTask?.task_id, runsPage, runsPageSize],
    [runsTask?.task_id, runsPage, runsPageSize],
  )
  const { data: runsData, isFetching: runsFetching, refetch: refetchRuns } = useQuery({
    queryKey: runsQueryKey,
    queryFn: () => tasksApi.runs(runsTask!.task_id, runsPage, runsPageSize),
    enabled: runsQueryEnabled,
    refetchInterval: runsQueryEnabled ? 3000 : false,
  })

  const logsQueryEnabled = logsOpen && !!runsTask && !!logsRun
  const logsQueryKey = useMemo(
    () => ['taskRunLogs', runsTask?.task_id, logsRun?.id, logsPage, logsPageSize],
    [runsTask?.task_id, logsRun?.id, logsPage, logsPageSize],
  )
  const { data: logsData, isFetching: logsFetching } = useQuery({
    queryKey: logsQueryKey,
    queryFn: () => tasksApi.logs(runsTask!.task_id, logsRun!.id, logsPage, logsPageSize),
    enabled: logsQueryEnabled,
    refetchInterval: logsQueryEnabled ? 2000 : false,
  })

  const columns = [
    {
      title: '任务',
      dataIndex: 'name',
      key: 'name',
      render: (_: any, t: TaskItem) => (
        <div>
          <div style={{ fontWeight: 600 }}>{t.name}</div>
          <Text type="secondary">{t.task_id}</Text>
          {t.description ? <div><Text type="secondary">{t.description}</Text></div> : null}
        </div>
      ),
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 90,
      render: (_: any, t: TaskItem) => (
        <Switch
          checked={t.enabled}
          disabled={!isAdmin || updateMutation.isPending}
          onChange={(checked) => updateMutation.mutate({ taskId: t.task_id, data: { enabled: checked } })}
        />
      ),
    },
    {
      title: '调度',
      key: 'schedule',
      width: 140,
      render: (_: any, t: TaskItem) => (
        <div>
          <div>{t.schedule_type === 'cron' ? 'Cron' : '间隔'}</div>
          <Text type="secondary">{formatSchedule(t)}</Text>
        </div>
      ),
    },
    {
      title: '下次执行',
      dataIndex: 'next_run_time',
      key: 'next',
      width: 180,
      render: (v: string | null) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '最近一次',
      key: 'last',
      width: 200,
      render: (_: any, t: TaskItem) => {
        const r = t.last_run
        if (!r) return '-'
        return (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {statusTag(r.status)}
              <Text type="secondary">{dayjs(r.started_at).format('MM-DD HH:mm:ss')}</Text>
            </div>
            {r.duration_ms != null ? <Text type="secondary">{`${r.duration_ms}ms`}</Text> : null}
          </div>
        )
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_: any, t: TaskItem) => (
        <Space>
          <Button
            icon={<PlayCircleOutlined />}
            disabled={!isAdmin || runMutation.isPending}
            onClick={() => runMutation.mutate(t.task_id)}
          >
            运行
          </Button>
          <Button
            icon={<EditOutlined />}
            disabled={!isAdmin}
            onClick={() => {
              setEditing(t)
              setEditOpen(true)
              form.setFieldsValue({
                schedule_type: t.schedule_type,
                interval_minutes: t.interval_seconds ? Math.max(1, Math.round(t.interval_seconds / 60)) : 10,
                cron: t.cron || '',
              })
            }}
          >
            配置
          </Button>
          <Button
            icon={<HistoryOutlined />}
            onClick={() => {
              setRunsTask(t)
              setRunsOpen(true)
              setRunsPage(1)
            }}
          >
            记录
          </Button>
        </Space>
      ),
    },
  ]

  const runColumns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 80 },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => statusTag(v),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 180,
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '结束时间',
      dataIndex: 'finished_at',
      key: 'finished_at',
      width: 180,
      render: (v: string | null) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 100,
      render: (v: number | null) => v != null ? `${v}ms` : '-',
    },
    {
      title: '消息',
      dataIndex: 'message',
      key: 'message',
      render: (v: string | null) => v ? <Text ellipsis title={v}>{v}</Text> : '-',
    },
    {
      title: '错误',
      dataIndex: 'error',
      key: 'error',
      render: (v: string | null) => v ? <Text type="danger" ellipsis title={v}>{v}</Text> : '-',
    },
    {
      title: '日志',
      key: 'logs',
      width: 180,
      render: (_: any, r: TaskRunItem) => (
        <Space>
          <Button
            size="small"
            onClick={() => {
              setLogsRun(r)
              setLogsOpen(true)
              setLogsPage(1)
            }}
          >
            日志
          </Button>
          <Button
            size="small"
            danger
            disabled={!isAdmin || !['running', 'queued', 'cancelling'].includes(r.status)}
            onClick={() => {
              if (!runsTask) return
              Modal.confirm({
                title: '停止任务？',
                content: `run_id=${r.id}，将请求停止当前任务运行。`,
                okText: '停止',
                cancelText: '取消',
                onOk: async () => {
                  try {
                    await tasksApi.cancel(runsTask.task_id, r.id)
                    message.success('已请求停止')
                    await refetchRuns()
                  } catch (e: any) {
                    message.error(e?.response?.data?.detail || '停止失败')
                  }
                },
              })
            }}
          >
            停止
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ fontWeight: 700, fontSize: 16 }}>任务管理</div>
        <Space>
          <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => refetch()}>
            刷新
          </Button>
        </Space>
      </div>

      {!isAdmin ? (
        <div style={{ marginBottom: 12 }}>
          <Tag>仅管理员可配置/触发任务</Tag>
        </div>
      ) : null}

      <Table
        rowKey="task_id"
        dataSource={items}
        columns={columns as any}
        loading={isFetching}
        pagination={false}
      />

      <Modal
        title={`配置任务：${editing?.name || ''}`}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        okText="保存"
        onOk={async () => {
          const values = await form.validateFields()
          const scheduleType = values.schedule_type as 'interval' | 'cron'
          const payload: any = { schedule_type: scheduleType }
          if (scheduleType === 'interval') {
            payload.interval_seconds = Number(values.interval_minutes) * 60
            payload.cron = null
          } else {
            payload.cron = values.cron
          }
          if (editing) updateMutation.mutate({ taskId: editing.task_id, data: payload })
          setEditOpen(false)
        }}
        destroyOnClose
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            label="调度类型"
            name="schedule_type"
            rules={[{ required: true, message: '请选择调度类型' }]}
          >
            <Switch
              checkedChildren="Cron"
              unCheckedChildren="间隔"
              checked={scheduleType === 'cron'}
              onChange={(checked) => form.setFieldsValue({ schedule_type: checked ? 'cron' : 'interval' })}
            />
          </Form.Item>

          {scheduleType !== 'cron' ? (
            <Form.Item
              label="间隔（分钟）"
              name="interval_minutes"
              rules={[{ required: true, message: '请输入间隔' }]}
            >
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
          ) : (
            <Form.Item
              label="Cron 表达式（5 段）"
              name="cron"
              rules={[{ required: true, message: '请输入 Cron 表达式' }]}
            >
              <Input placeholder="例如：0 */1 * * *" />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Drawer
        title={runsTask ? `执行记录：${runsTask.name}` : '执行记录'}
        open={runsOpen}
        onClose={() => setRunsOpen(false)}
        width={900}
        extra={
          <Button icon={<ReloadOutlined />} loading={runsFetching} onClick={() => refetchRuns()}>
            刷新
          </Button>
        }
      >
        <Table
          rowKey="id"
          dataSource={(runsData?.items ?? []) as TaskRunItem[]}
          columns={runColumns as any}
          loading={runsFetching}
          pagination={{
            current: runsPage,
            pageSize: runsPageSize,
            total: runsData?.total ?? 0,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setRunsPage(p)
              setRunsPageSize(ps)
            },
          }}
        />
      </Drawer>

      <Drawer
        title={`运行日志 ${logsRun?.id ?? ''}`}
        open={logsOpen}
        onClose={() => setLogsOpen(false)}
        width={900}
      >
        <Table
          rowKey="id"
          dataSource={(logsData?.items ?? []) as TaskRunLogItem[]}
          loading={logsFetching}
          size="small"
          pagination={{
            current: logsPage,
            pageSize: logsPageSize,
            total: logsData?.total ?? 0,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setLogsPage(p)
              setLogsPageSize(ps)
            },
          }}
          columns={[
            {
              title: '时间',
              dataIndex: 'created_at',
              key: 'created_at',
              width: 180,
              render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm:ss'),
            },
            { title: '级别', dataIndex: 'level', key: 'level', width: 90 },
            {
              title: '内容',
              dataIndex: 'message',
              key: 'message',
              render: (v: string) => <Text ellipsis title={v}>{v}</Text>,
            },
          ]}
        />
      </Drawer>
    </div>
  )
}
