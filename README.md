# JingTan Data Platform 鲸探数据采集与分析平台

数据采集、存储、管理和展示鲸探数字藏品数据的完整平台。

## 技术栈

**后端** Python 3.11 / FastAPI / SQLAlchemy / PostgreSQL / Redis / JWT
**前端** React 18 / TypeScript / Vite / Ant Design / ECharts / React Query
**爬虫** httpx（连接池 + 并发控制）/ APScheduler / tenacity（指数退避重试）

## 项目结构

```
xmeta_claw/
├── backend/
│   ├── app/
│   │   ├── main.py                        # FastAPI 入口 + 生命周期管理
│   │   ├── core/
│   │   │   ├── config.py                  # Pydantic 配置管理
│   │   │   └── security.py                # JWT 认证 / 密码哈希
│   │   ├── database/
│   │   │   ├── db.py                      # 异步数据库引擎 + 连接池
│   │   │   └── models.py                  # ORM 模型(12 张表)
│   │   ├── api/
│   │   │   ├── auth.py                    # 登录认证
│   │   │   ├── calendar.py                # 发行日历
│   │   │   ├── archives.py                # 藏品库
│   │   │   ├── ips.py                     # IP库
│   │   │   ├── stats.py                   # 统计/Dashboard
│   │   │   ├── crawler.py                 # 爬虫管理接口
│   │   │   └── tasks.py                   # 定时任务管理
│   │   ├── crawler/
│   │   │   ├── client.py                  # HTTP 客户端(连接池/UA轮转/反封)
│   │   │   ├── calendar_crawler.py        # 发行日历爬虫
│   │   │   ├── launch_detail_crawler.py   # 发行详情爬虫
│   │   │   ├── archive_crawler.py         # 藏品数据爬虫
│   │   │   ├── ip_crawler.py              # IP信息爬虫
│   │   │   ├── calendar_archive_backfill.py # 日历关联藏品补齐
│   │   │   └── archive_id_backfill.py     # 藏品ID批量补齐
│   │   └── scheduler/
│   │       └── tasks.py                   # APScheduler 定时任务
│   ├── .env / .env.example
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── main.tsx                       # React 入口
│   │   ├── App.tsx
│   │   ├── api/                           # API 请求层(Axios)
│   │   ├── store/                         # Zustand 状态管理
│   │   ├── router/                        # React Router 路由
│   │   ├── layouts/                       # 响应式布局
│   │   └── pages/
│   │       ├── login/                     # 登录页
│   │       ├── dashboard/                 # 数据概览 + ECharts 图表
│   │       ├── calendar/                  # 发行日历 + 详情抽屉
│   │       ├── archives/                  # 藏品库 + 详情
│   │       ├── ips/                       # IP库
│   │       └── tasks/                     # 任务管理 + 执行日志
│   ├── package.json
│   └── vite.config.ts
├── spider_process.md                      # 爬虫流程文档
└── README.md
```

## 快速开始

### 1. 环境准备

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Redis (可选，用于缓存)

### 2. 数据库

```bash
createdb jingtan
```

### 3. 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # 按需修改配置
uvicorn app.main:app --reload --port 8000
```

首次启动自动建表并创建 admin 账户。

### 4. 前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:3000`

### 5. 登录

默认管理员账号（可在 `.env` 中修改）：

```
用户名: admin
密码:   admin123
```

## 爬虫反封策略

| 策略 | 说明 |
|------|------|
| UA 轮转 | 9 个 User-Agent (Android/iOS/桌面端) 随机切换 |
| 随机延迟 | 基础延迟 ±40% 抖动，避免固定请求频率 |
| 请求头变换 | Accept-Language/Accept/Cache-Control 等随机组合 |
| 连接池复用 | httpx 持久化连接池，减少握手开销 |
| 并发控制 | 信号量限制最大并发数（默认 3），避免瞬间高频 |
| 代理支持 | 可配置 HTTP/SOCKS 代理，支持代理池轮换 |
| 指数退避 | 失败后指数退避重试（2s → 4s → 8s，最多 3 次） |
| 优雅降级 | 单条失败不中断整体任务，继续处理下一条 |

配置项（`.env`）：

```bash
CRAWLER_REQUEST_DELAY=0.5    # 基础请求间隔(秒)
CRAWLER_CONCURRENCY=3        # 最大并发请求数
CRAWLER_PROXY=               # 代理地址, 留空则直连
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/login` | 登录 |
| POST | `/auth/logout` | 登出 |
| GET | `/auth/me` | 当前用户信息 |
| GET | `/calendar/` | 发行日历列表（支持日期/平台/IP/搜索筛选） |
| GET | `/calendar/{id}` | 发行详情（含关联藏品） |
| GET | `/archives/` | 藏品列表（支持排序/筛选/分页） |
| GET | `/archives/{id}` | 藏品详情 |
| GET | `/ips/` | IP列表（含藏品数统计） |
| GET | `/stats/dashboard` | Dashboard 统计 + 近30天发行趋势 |
| GET | `/tasks/` | 任务列表 |
| PUT | `/tasks/{id}` | 更新任务配置（管理员） |
| POST | `/tasks/{id}/run` | 触发任务执行（管理员） |
| GET | `/tasks/{id}/runs` | 任务执行历史 |
| GET | `/tasks/{id}/runs/{rid}/logs` | 任务执行日志 |
| POST | `/crawler/full` | 触发全量爬取（管理员） |
| POST | `/crawler/calendar/{date}` | 爬取指定日期日历（管理员） |

所有接口（除 login）需在请求头携带 `Authorization: Bearer <token>`。

## 定时任务

| 任务 | 默认频率 | 说明 |
|------|----------|------|
| 今日日历 | 每小时 | 爬取今日和明日发行日历，补全详情和关联藏品 |
| 补全详情 | 每小时 | 爬取缺少详情的发行记录 |
| 藏品列表 | 每 6 小时 | 更新藏品库数据 |
| 全量爬取 | 每天（默认禁用） | 往前连续爬取直到 15 天无数据停止 |
| 近7天爬取 | 每天（默认禁用） | 重跑近7天日历、详情并补齐关联藏品 |
| 藏品ID补齐 | 每天（默认禁用） | 从 archiveId=15000 批量补齐到 10000 |

所有任务频率可在前端任务管理页面动态调整。

## 数据采集流程

详见 [spider_process.md](./spider_process.md)

```
第一阶段：日历数据
  遍历日期 → 获取发行日历列表 → 获取发行详情 → 提取关联藏品ID
  → 获取藏品详细数据 → 获取IP信息 → 保存/更新数据库

第二阶段：藏品ID补齐
  从 archiveId=15000 开始批量查库 → 过滤缺失ID → 并发拉取详情 → 写入数据库
```

## 前端页面

| 页面 | 功能 |
|------|------|
| Dashboard | 统计卡片 + 近30天发行趋势柱状图 + 热门IP排行榜 + 最新藏品 |
| 发行日历 | 日期/搜索筛选 + 详情抽屉（包含/关联藏品表格） |
| 藏品库 | 搜索/排序 + 藏品列表 + 全量爬取触发按钮 |
| 藏品详情 | 基本信息卡片（图片、平台、IP、类型、数量、发行时间等） |
| IP库 | IP列表 + 藏品数统计 |
| 任务管理 | 任务开关/配置 + 执行历史 + 实时日志查看 |

## 数据库表

| 表名 | 说明 |
|------|------|
| `users` | 用户(admin/viewer) |
| `platforms` | 平台 |
| `ips` | IP（含 source_uid、粉丝数、描述） |
| `launch_calendar` | 发行日历 |
| `launch_detail` | 发行详情(含 raw_json) |
| `archives` | 藏品 |
| `task_configs` | 定时任务配置 |
| `task_runs` | 任务执行记录 |
| `task_run_logs` | 任务执行日志 |

## 响应式设计

- `<768px` 手机：Table 切换为 Card 列表，Sidebar 切换为 Drawer
- `768-1200px` 平板：自适应列数
- `>1200px` PC：完整表格 + 固定侧边栏 + 完整图表
