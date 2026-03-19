# API 样本目录

本目录将 [spider_process.md](../spider_process.md) 中提到的外部接口样本按“一个接口一个文件”的方式拆分，便于后续维护。

## 规范

- 文件格式：请求样本与完整原始响应样本统一保存在 `.http` 文件中。
- 命名规则：`{序号}_{模块}_{动作}.http`
- 单文件职责：一个文件对应一个接口；同一路径的不同筛选场景，放在同一个文件内用多个 request section 区分。
- 样本内容：包含接口说明、请求样本、原始完整响应（以注释块形式内嵌在同一 `.http` 文件中）。
- 维护建议：文档新增接口时，按同样命名规则补充新文件，并在本索引登记。

## 文件索引

1. [01_launch_calendar_list.http](01_launch_calendar_list.http) - 日历基础数据
2. [02_launch_calendar_detail.http](02_launch_calendar_detail.http) - 日历详细数据
3. [03_goods_archive.http](03_goods_archive.http) - 藏品详细数据
4. [04_community_user_home.http](04_community_user_home.http) - IP 信息
5. [05_archive_market.http](05_archive_market.http) - 藏品价格查询
6. [06_archive_census_line.http](06_archive_census_line.http) - 藏品销售折线图
7. [07_plane_list_new.http](07_plane_list_new.http) - 最新版块统计
8. [08_market_archive_page.http](08_market_archive_page.http) - 市场成交列表/板块交易明细
9. [09_market_top_list.http](09_market_top_list.http) - 行情分类
10. [10_market_top_archive_page.http](10_market_top_archive_page.http) - 分类下热门成交数据
11. [11_market_ip_page.http](11_market_ip_page.http) - IP 方热榜成交量
12. [12_market_plane_list.http](12_market_plane_list.http) - 板块列表
13. [13_home_search_app_new.http](13_home_search_app_new.http) - 在线藏品/IP 搜索

## 使用说明

1. 将 `@baseUrl` 保持为线上地址，或按需要替换为代理地址。
2. 如目标接口有风控要求，可在请求头中补充 `User-Agent`、`Referer`、`Origin`、`Cookie`。
3. 若某个接口需要多个查询场景，优先在同一个 `.http` 文件里继续追加 `###` 分段。
