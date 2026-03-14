WITH garbage AS (
  SELECT a.archive_id
  FROM archives a
  WHERE a.issue_time IS NULL
    AND a.total_goods_count IS NULL
    AND a.archive_name = a.archive_id
)
DELETE FROM archive_market m
USING garbage g
WHERE m.archive_id = g.archive_id;

WITH garbage AS (
  SELECT a.archive_id
  FROM archives a
  WHERE a.issue_time IS NULL
    AND a.total_goods_count IS NULL
    AND a.archive_name = a.archive_id
)
DELETE FROM archive_price_history h
USING garbage g
WHERE h.archive_id = g.archive_id;

WITH garbage AS (
  SELECT a.archive_id
  FROM archives a
  WHERE a.issue_time IS NULL
    AND a.total_goods_count IS NULL
    AND a.archive_name = a.archive_id
)
DELETE FROM archives a
USING garbage g
WHERE a.archive_id = g.archive_id;

