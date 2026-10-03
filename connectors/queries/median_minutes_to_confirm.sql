-- Median minutes from first message to a confirmed meeting, completed meetings, one segment.
WITH ev AS (
  SELECT
    e.minutes_to_confirm AS minutes,
    ROW_NUMBER() OVER (ORDER BY e.minutes_to_confirm) AS rn,
    COUNT(*) OVER () AS cnt
  FROM scheduling_events e
  JOIN accounts a ON a.account_id = e.account_id
  WHERE e.completed = 1
    AND a.segment = :segment
)
SELECT AVG(minutes) AS median_minutes, MAX(cnt) AS n_meetings
FROM ev
WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)
