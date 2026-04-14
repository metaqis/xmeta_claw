"""Agent 工具定义 (OpenAI function calling 格式)"""

TOOLS = [
    # ── DB 查询工具 ──────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "resolve_entities",
            "description": "按用户提供的名称或ID片段，综合解析最可能的藏品或IP。适用于用户只给名称，却要查详情、行情、走势、对比等场景。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "用户输入的藏品名、IP名、别名或ID片段",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回多少个候选，默认5",
                    },
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_archives",
            "description": "搜索藏品库。可按藏品名称、藏品ID、IP名称、平台ID筛选，支持分页；结果会尽量把更精确匹配排在前面。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，匹配藏品名称或IP名称",
                    },
                    "platform_id": {
                        "type": "integer",
                        "description": "平台ID筛选（741=鲸探）",
                    },
                    "page": {"type": "integer", "description": "页码，默认1"},
                    "page_size": {"type": "integer", "description": "每页数量，默认20"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_archive_detail",
            "description": "获取单个藏品的详细信息，包含名称、发行量、类型、IP等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "archive_id": {
                        "type": "string",
                        "description": "藏品ID",
                    },
                },
                "required": ["archive_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_ips",
            "description": "搜索 IP（创作者/发行方），可按名称搜索；结果会尽量把更精确匹配排在前面。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "IP名称关键词",
                    },
                    "page": {"type": "integer", "description": "页码，默认1"},
                    "page_size": {"type": "integer", "description": "每页数量，默认20"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "online_search_archives",
            "description": "在线模糊查询藏品。适合数据库查不到、用户只给了不完整名字、或需要给用户推荐候选项时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "用户输入的藏品名称片段、别名或关键字",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回多少个候选，默认10",
                    },
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "online_search_ips",
            "description": "在线模糊查询IP。适合数据库查不到、用户只给了不完整名字、或需要给用户推荐候选项时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "用户输入的IP名称片段、别名或关键字",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回多少个候选，默认10",
                    },
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ip_detail",
            "description": "获取 IP 详情及其旗下藏品列表。优先使用数据库中的 ip_id；若只有在线查询得到的 source_uid，也可用于获取在线IP资料。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ip_id": {
                        "type": "integer",
                        "description": "IP 的数据库 ID",
                    },
                    "source_uid": {
                        "type": "integer",
                        "description": "在线IP查询结果中的 source_uid / communityIpId；当数据库中不存在该IP时可使用",
                    },
                    "from_type": {
                        "type": "integer",
                        "description": "在线IP来源类型，默认1",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_launches",
            "description": "获取近期（未来7天+过去3天）的发行日历。",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "向前查看天数，默认7",
                    },
                    "days_back": {
                        "type": "integer",
                        "description": "向后查看天数，默认3",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_db_stats",
            "description": "获取平台数据库统计概览：藏品总数、IP总数、平台总数、日历总数等。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    # ── 实时 API 工具 ────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_archive_market",
            "description": "获取藏品的实时市场行情：市值、成交量、最低价、均价等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "archive_id": {
                        "type": "integer",
                        "description": "藏品ID（数字）",
                    },
                    "time_type": {
                        "type": "integer",
                        "description": "时间类型：0=今日, 1=近7天, 2=近30天，默认0",
                    },
                },
                "required": ["archive_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_archive_price_trend",
            "description": "获取藏品的价格走势数据（均价、成交额、最低价、成交量随时间变化）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "archive_id": {
                        "type": "integer",
                        "description": "藏品ID（数字）",
                    },
                    "type": {
                        "type": "integer",
                        "description": "时间粒度：1=按小时, 2=按天, 3=按周，默认1",
                    },
                },
                "required": ["archive_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sector_stats",
            "description": "获取所有板块的统计数据：板块名、均价涨跌、成交量、上架率、总市值等。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hot_archives",
            "description": "获取今日成交热榜（按成交量排序的藏品列表）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_type": {
                        "type": "integer",
                        "description": "时间类型：0=今日, 1=近7天, 2=近30天，默认0",
                    },
                    "page": {"type": "integer", "description": "页码，默认1"},
                    "page_size": {"type": "integer", "description": "每页数量，默认20"},
                    "search_name": {
                        "type": "string",
                        "description": "按名称搜索",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_categories",
            "description": "获取行情分类列表（如：鲸探50、禁出195、新品、鲸探秒转等）。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_category_archives",
            "description": "获取某个行情分类下的藏品列表（需先通过 get_market_categories 获取 topCode）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "top_code": {
                        "type": "string",
                        "description": "分类代码，如 '759475'（鲸探50）",
                    },
                    "time_type": {
                        "type": "integer",
                        "description": "时间类型：0=今日，默认0",
                    },
                    "page": {"type": "integer", "description": "页码，默认1"},
                    "page_size": {"type": "integer", "description": "每页数量，默认20"},
                },
                "required": ["top_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ip_ranking",
            "description": "获取 IP（创作者）热度排行榜：市值、热度、成交量等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_type": {
                        "type": "integer",
                        "description": "时间类型：0=今日, 1=近7天, 2=近30天，默认0",
                    },
                    "page": {"type": "integer", "description": "页码，默认1"},
                    "page_size": {"type": "integer", "description": "每页数量，默认20"},
                    "search_name": {
                        "type": "string",
                        "description": "按IP名称搜索",
                    },
                },
                "required": [],
            },
        },
    },
]

# ── 板块相关工具 ─────────────────────────────────────

TOOLS.extend([
    {
        "type": "function",
        "function": {
            "name": "get_plane_list",
            "description": "获取所有板块列表（如字画板块、文物板块、非遗板块等），返回板块名称和代码(code)",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sector_archives",
            "description": "按板块(planeCode)查看该板块中的藏品交易详细数据，需先通过 get_plane_list 获取板块代码",
            "parameters": {
                "type": "object",
                "properties": {
                    "plane_code": {
                        "type": "string",
                        "description": "板块代码，如 '00000001'(字画)、'00000002'(文物)等，从 get_plane_list 获取",
                    },
                    "time_type": {
                        "type": "integer",
                        "description": "时间类型：0=今日, 1=近7天, 2=近30天，默认0",
                    },
                    "page": {"type": "integer", "description": "页码，默认1"},
                    "page_size": {"type": "integer", "description": "每页数量，默认20"},
                    "search_name": {
                        "type": "string",
                        "description": "按藏品名称搜索",
                    },
                },
                "required": ["plane_code"],
            },
        },
    },
])

# ── 市场概况 / 历史快照 / 深度统计 / 鲸探SKU / 挂单 ──

TOOLS.extend([
    {
        "type": "function",
        "function": {
            "name": "get_market_overview",
            "description": "获取今日或指定日期的市场全局概况：全市场总市值、总成交额、成交笔数、最热板块、最热IP等。适合'今天市场怎么样'、'市场概况'、'大盘'类问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "日期，格式 YYYY-MM-DD，默认今日",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_plane_census",
            "description": "获取某板块的详细成交统计：总市值、市值涨跌、成交量、涨跌分布（多少藏品涨、多少跌、各涨跌幅区间分布）。需先通过 get_plane_list 获取板块代码。",
            "parameters": {
                "type": "object",
                "properties": {
                    "plane_code": {
                        "type": "string",
                        "description": "板块代码，如 '00000001'(字画)，从 get_plane_list 获取",
                    },
                    "time_type": {
                        "type": "integer",
                        "description": "时间类型：0=今日，默认0",
                    },
                },
                "required": ["plane_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_census",
            "description": "获取某行情分类的详细成交统计：总市值、市值涨跌、成交量、涨跌分布。需先通过 get_market_categories 获取 topCode。",
            "parameters": {
                "type": "object",
                "properties": {
                    "top_code": {
                        "type": "string",
                        "description": "分类代码，如 '759475'（鲸探50）",
                    },
                    "time_type": {
                        "type": "integer",
                        "description": "时间类型：0=今日，默认0",
                    },
                },
                "required": ["top_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_archive_goods_listing",
            "description": "查看某藏品在二级市场的实时挂单列表（在售商品），可查看最低价挂单、在售数量、各编号价格。适合'现在卖多少钱'、'挂单情况'、'二级市场'等问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "archive_id": {
                        "type": "integer",
                        "description": "藏品ID（数字）",
                    },
                    "page": {"type": "integer", "description": "页码，默认1"},
                    "page_size": {"type": "integer", "description": "每页数量，默认20"},
                },
                "required": ["archive_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_jingtan_sku",
            "description": "搜索鲸探SKU百科数据：按名称、作者、分类搜索。适合查询藏品官方发行信息、作者、发行量、分类等百科数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，匹配SKU名称或作者",
                    },
                    "category": {
                        "type": "string",
                        "description": "按一级分类名称筛选",
                    },
                    "page": {"type": "integer", "description": "页码，默认1"},
                    "page_size": {"type": "integer", "description": "每页数量，默认20"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_jingtan_sku_detail",
            "description": "获取鲸探SKU详情：包括名称、作者、发行方、描述、收藏数、评论数、发行量等丰富信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku_id": {
                        "type": "string",
                        "description": "SKU ID",
                    },
                },
                "required": ["sku_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_history",
            "description": "查询历史市场快照数据（板块/IP/藏品排名的历史记录）。可查看某日期的板块排名、IP排名或分类排名快照，也可对比两个日期的数据变化。",
            "parameters": {
                "type": "object",
                "properties": {
                    "snapshot_type": {
                        "type": "string",
                        "enum": ["plane", "ip", "archive"],
                        "description": "快照类型：plane=板块, ip=IP方, archive=藏品排名",
                    },
                    "date": {
                        "type": "string",
                        "description": "查询日期，格式 YYYY-MM-DD",
                    },
                    "compare_date": {
                        "type": "string",
                        "description": "对比日期，格式 YYYY-MM-DD，可选",
                    },
                    "top_code": {
                        "type": "string",
                        "description": "分类代码（仅当 snapshot_type=archive 时需要）",
                    },
                    "plane_code": {
                        "type": "string",
                        "description": "板块代码（仅当 snapshot_type=plane 时可选筛选）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回记录数，默认20",
                    },
                },
                "required": ["snapshot_type", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_launch_detail",
            "description": "获取某个发行记录的详情：优先购资格条件、优先购时间、发行状态等。需要先知道具体发行记录的ID。",
            "parameters": {
                "type": "object",
                "properties": {
                    "launch_id": {
                        "type": "integer",
                        "description": "发行日历记录的数据库ID",
                    },
                    "source_id": {
                        "type": "string",
                        "description": "来源ID（原始接口中的id），可替代 launch_id",
                    },
                },
                "required": [],
            },
        },
    },
])

TOOL_NAME_MAP = {
    "resolve_entities": "实体解析",
    "search_archives": "搜索藏品",
    "get_archive_detail": "藏品详情",
    "search_ips": "搜索IP",
    "online_search_archives": "在线藏品查询",
    "online_search_ips": "在线IP查询",
    "get_ip_detail": "IP详情",
    "get_upcoming_launches": "发行日历",
    "get_db_stats": "数据概览",
    "get_archive_market": "藏品行情",
    "get_archive_price_trend": "价格走势",
    "get_sector_stats": "板块统计",
    "get_hot_archives": "成交热榜",
    "get_market_categories": "行情分类",
    "get_category_archives": "分类排行",
    "get_ip_ranking": "IP排行",
    "get_plane_list": "板块列表",
    "get_sector_archives": "板块交易",
    "get_market_overview": "市场概况",
    "get_plane_census": "板块涨跌统计",
    "get_top_census": "分类涨跌统计",
    "get_archive_goods_listing": "挂单列表",
    "search_jingtan_sku": "鲸探SKU搜索",
    "get_jingtan_sku_detail": "鲸探SKU详情",
    "get_market_history": "历史快照",
    "get_launch_detail": "发行详情",
}
