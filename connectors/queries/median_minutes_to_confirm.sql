-- Median minutes from first message to a confirmed meeting, completed meetings, one segment.
-- No window functions (the guard rejects them): the median is the mean of the lower and upper
-- middle values, found by counting how many values are <= each candidate.
WITH ev AS (
  SELECT e.minutes_to_confirm AS minutes
  FROM scheduling_events e
  JOIN accounts a ON a.account_id = e.account_id
  WHERE e.completed = 1
    AND a.segment = :segment
),
c AS (
  SELECT COUNT(*) AS cnt FROM ev
)
SELECT
  ((SELECT MIN(x.minutes) FROM ev x
    WHERE (SELECT COUNT(*) FROM ev y WHERE y.minutes <= x.minutes) >= (c.cnt + 1) / 2)
   + (SELECT MIN(x.minutes) FROM ev x
      WHERE (SELECT COUNT(*) FROM ev y WHERE y.minutes <= x.minutes) >= (c.cnt + 2) / 2)
  ) / 2.0 AS median_minutes,
  c.cnt AS n_meetings
FROM c
