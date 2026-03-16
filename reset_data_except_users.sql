TRUNCATE TABLE
  platforms,
  ips,
  launch_calendar,
  launch_detail,
  archives,
  archive_misses,
  task_runs,
  task_run_logs
RESTART IDENTITY CASCADE;

INSERT INTO task_configs (task_id, name, description, schedule_type, interval_seconds, cron, enabled)
VALUES
  ('crawl_calendar', '今日日历', '爬取今日和明日发行日历', 'interval', 3600, NULL, TRUE),
  ('crawl_details', '补全详情', '爬取缺少详情的发行记录', 'interval', 3600, NULL, TRUE),
  ('crawl_archives', '藏品列表', '更新藏品库', 'interval', 21600, NULL, TRUE),
  ('full_crawl', '全量爬取', '从最近日期往前爬，连续15天无数据停止', 'interval', 86400, NULL, FALSE),
  ('recent_7d_crawl', '近7天爬取', '重跑近7天日历、详情并补齐关联藏品', 'interval', 86400, NULL, FALSE),
  ('archive_id_backfill', '藏品ID补齐', '从数据库最大 archiveId 往前补齐到 15000（跳过已存在）', 'interval', 86400, NULL, FALSE),
  ('ip_uid_backfill', 'IP UID补齐', '通过关联藏品详情补齐 IP 的 source_uid', 'interval', 86400, NULL, FALSE)
ON CONFLICT (task_id) DO NOTHING;
