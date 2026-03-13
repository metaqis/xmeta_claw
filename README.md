# JingTan Data Platform 鲸探数据采集与分析平台

数据采集、存储、管理和展示鲸探数字藏品数据的完整平台。

## 技术栈

**后端** Python 3.11 / FastAPI / SQLAlchemy / PostgreSQL / Redis / JWT
**前端** React 18 / TypeScript / Vite / Ant Design / ECharts / React Query
**爬虫** httpx / APScheduler / tenacity(重试)

## 项目结构

```
xmeta_claw/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── core/
│   │   │   ├── config.py        # 配置管理
│   │   │   └── security.py      # JWT 认证
│   │   ├── database/
│   │   │   ├── db.py            # 数据库连接
│   │   │   └── models.py        # ORM 模型
│   │   ├── api/
│   │   │   ├── auth.py          # 登录认证
│   │   │   ├── calendar.py      # 发行日历
│   │   │   ├── archives.py      # 藏品库
│   │   │   ├── ips.py           # IP库
│   │   │   ├── stats.py         # 统计/Dashboard
│   │   │   └── crawler.py       # 爬虫管理接口
│   │   ├── crawler/
│   │   │   ├── client.py        # HTTP 客户端(重试/日志)
│   │   │   ├── calendar_crawler.py
│   │   │   ├── launch_detail_crawler.py
│   │   │   ├── archive_crawler.py
│   │   │   └── market_crawler.py
│   │   └── scheduler/
│   │       └── tasks.py         # 定时任务(APScheduler)
│   ├── .env                     # 环境变量
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── main.tsx             # React 入口
│   │   ├── App.tsx
│   │   ├── api/                 # API 请求层
│   │   ├── store/               # Zustand 状态管理
│   │   ├── router/              # 路由配置
│   │   ├── layouts/             # 布局(侧边栏/响应式)
│   │   └── pages/
│   │       ├── login/           # 登录页
│   │       ├── dashboard/       # 数据概览
│   │       ├── calendar/        # 发行日历
│   │       ├── archives/        # 藏品库 + 详情
│   │       └── ips/             # IP库
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
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
# 创建 PostgreSQL 数据库
createdb jingtan
```

### 3. 后端

```bash
cd backend

# 创建虚拟环境
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（按需修改 .env）
cp .env.example .env

# 启动服务（首次启动自动建表和创建 admin 账户）
uvicorn app.main:app --reload --port 8000
```

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

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/login` | 登录 |
| POST | `/auth/logout` | 登出 |
| GET | `/auth/me` | 当前用户信息 |
| GET | `/calendar/` | 发行日历列表（支持日期/平台/IP/搜索筛选） |
| GET | `/calendar/{id}` | 发行详情 |
| GET | `/archives/` | 藏品列表（支持排序/筛选） |
| GET | `/archives/{id}` | 藏品详情（含价格历史） |
| GET | `/ips/` | IP列表 |
| GET | `/stats/dashboard` | Dashboard 统计数据 |
| POST | `/crawler/full` | 触发完整爬取（管理员） |
| POST | `/crawler/market` | 触发市场数据更新（管理员） |
| POST | `/crawler/calendar/{date}` | 爬取指定日期日历（管理员） |

所有接口（除 login）需在请求头携带 `Authorization: Bearer <token>`。

## 定时任务

启动后端后自动运行：

| 任务 | 频率 | 说明 |
|------|------|------|
| 市场数据更新 | 每 10 分钟 | 更新所有藏品价格、挂单、成交数据，并记录历史 |
| 今日日历 | 每小时 | 爬取今日和明日发行日历 |
| 补全详情 | 每小时 | 爬取缺少详情的发行记录 |
| 藏品列表 | 每 6 小时 | 更新藏品库 |

## 数据采集流程

```
遍历日期(today-2年 ~ today+30天)
  → 获取发行日历 (/h5/news/launchCalendar/list)
  → 获取发行详情 (/h5/news/launchCalendar/detailed)
  → 提取 archiveId
  → 获取藏品市场数据 (/h5/goods/archive)
  → 保存/更新数据库
```

首次完整爬取：登录后调用 `POST /crawler/full`。

## 数据库表

| 表名 | 说明 |
|------|------|
| `users` | 用户(admin/viewer) |
| `platforms` | 平台 |
| `ips` | IP |
| `launch_calendar` | 发行日历 |
| `launch_detail` | 发行详情(含 raw_json) |
| `archives` | 藏品 |
| `archive_market` | 藏品当前市场数据 |
| `archive_price_history` | 藏品价格历史(每次更新追加) |

## 响应式设计

- `<768px` 手机：Table 切换为 Card 列表，Sidebar 切换为 Drawer
- `768-1200px` 平板：自适应列数
- `>1200px` PC：完整表格 + 固定侧边栏
