-- Average messages exchanged to schedule one completed meeting, one segment.
SELECT
  ROUND(AVG(e.messages_exchanged), 2) AS avg_messages,
  COUNT(*) AS n_meetings
FROM scheduling_events e
JOIN accounts a ON a.account_id = e.account_id
WHERE e.completed = 1
  AND a.segment = :segment
