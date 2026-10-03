-- Share of support tickets in one category for a period (months as YYYY-MM).
SELECT
  SUM(CASE WHEN category = :category THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS share,
  COUNT(*) AS total_tickets
FROM support_tickets
WHERE created_month >= :period_start
  AND created_month <= :period_end
