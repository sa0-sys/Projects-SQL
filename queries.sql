-- Payments Operations SQL Analysis: queries (SQLite 3.25+)
-- Run one at a time, e.g.  sqlite3 -header -column payments.db < queries.sql
-- Each query answers a question a support or account team would actually ask.

-- Q1. Daily payment success rate (the "is something wrong today?" view)
SELECT date(created_at) AS day,
       COUNT(*) AS charges,
       ROUND(100.0 * SUM(status = 'succeeded') / COUNT(*), 1) AS success_pct
FROM charges
GROUP BY day
ORDER BY day
LIMIT 10;

-- Q2. Why are payments failing? Failure reasons by payment method
SELECT payment_method, failure_code, COUNT(*) AS failures,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY payment_method), 1) AS pct_of_method_failures
FROM charges
WHERE status = 'failed'
GROUP BY payment_method, failure_code
ORDER BY payment_method, failures DESC;

-- Q3. Enterprise vs SME success rate by country
SELECT m.segment, m.country, COUNT(*) AS charges,
       ROUND(100.0 * SUM(c.status = 'succeeded') / COUNT(*), 2) AS success_pct
FROM charges c JOIN merchants m USING (merchant_id)
GROUP BY m.segment, m.country
ORDER BY m.segment, success_pct;

-- Q4. Which merchants had a sharp week-over-week drop in success rate? (CTE + LAG)
WITH weekly AS (
  SELECT merchant_id,
         strftime('%Y-%W', created_at) AS wk,
         100.0 * SUM(status = 'succeeded') / COUNT(*) AS success_pct,
         COUNT(*) AS charges
  FROM charges
  GROUP BY merchant_id, wk
  HAVING COUNT(*) >= 40
), lagged AS (
  SELECT *, LAG(success_pct) OVER (PARTITION BY merchant_id ORDER BY wk) AS prev_pct FROM weekly
)
SELECT merchant_id, wk, ROUND(prev_pct, 1) AS prev_pct, ROUND(success_pct, 1) AS success_pct,
       ROUND(success_pct - prev_pct, 1) AS change_pts
FROM lagged
WHERE prev_pct IS NOT NULL AND success_pct - prev_pct <= -15
ORDER BY change_pts;

-- Q5. Webhook endpoints with the worst delivery failure rate (first attempt)
SELECT e.endpoint_id, e.merchant_id, COUNT(*) AS events,
       ROUND(100.0 * SUM(d.success = 0) / COUNT(*), 1) AS first_attempt_fail_pct
FROM webhook_endpoints e
JOIN webhook_events ev ON ev.endpoint_id = e.endpoint_id
JOIN webhook_deliveries d ON d.event_id = ev.event_id AND d.attempt = 1
GROUP BY e.endpoint_id
HAVING first_attempt_fail_pct > 5
ORDER BY first_attempt_fail_pct DESC;

-- Q6. What are the failing endpoints returning? (status code breakdown tells you the fix)
SELECT ev.endpoint_id, COALESCE(CAST(d.http_status AS TEXT), 'timeout') AS response, COUNT(*) AS failed_attempts
FROM webhook_deliveries d
JOIN webhook_events ev ON ev.event_id = d.event_id
WHERE d.success = 0
  AND ev.endpoint_id IN (SELECT ev2.endpoint_id
                         FROM webhook_events ev2
                         JOIN webhook_deliveries d2 ON d2.event_id = ev2.event_id AND d2.attempt = 1
                         GROUP BY ev2.endpoint_id
                         HAVING 100.0 * SUM(d2.success = 0) / COUNT(*) > 20)
GROUP BY ev.endpoint_id, response
ORDER BY ev.endpoint_id, failed_attempts DESC;

-- Q7. Events that were never delivered after every retry
SELECT ev.endpoint_id, COUNT(*) AS undelivered_events
FROM webhook_events ev
WHERE NOT EXISTS (SELECT 1 FROM webhook_deliveries d WHERE d.event_id = ev.event_id AND d.success = 1)
GROUP BY ev.endpoint_id
ORDER BY undelivered_events DESC
LIMIT 10;

-- Q8. Support load: cases and average hours to close, by category and tier
SELECT category, tier, COUNT(*) AS cases,
       ROUND(AVG((julianday(closed_at) - julianday(opened_at)) * 24), 1) AS avg_hours_to_close,
       SUM(closed_at IS NULL) AS still_open
FROM support_cases
GROUP BY category, tier
ORDER BY category, tier;

-- Q9. Do webhook problems show up as support cases? (join the two signals per merchant)
WITH wh AS (
  SELECT e.merchant_id,
         ROUND(100.0 * SUM(d.success = 0) / COUNT(*), 1) AS first_attempt_fail_pct
  FROM webhook_endpoints e
  JOIN webhook_events ev ON ev.endpoint_id = e.endpoint_id
  JOIN webhook_deliveries d ON d.event_id = ev.event_id AND d.attempt = 1
  GROUP BY e.merchant_id
), sc AS (
  SELECT merchant_id, COUNT(*) AS webhook_cases
  FROM support_cases WHERE category = 'webhooks' GROUP BY merchant_id
)
SELECT m.merchant_id, m.segment, wh.first_attempt_fail_pct, COALESCE(sc.webhook_cases, 0) AS webhook_cases
FROM merchants m
JOIN wh USING (merchant_id)
LEFT JOIN sc USING (merchant_id)
ORDER BY wh.first_attempt_fail_pct DESC
LIMIT 8;
