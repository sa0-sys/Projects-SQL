# Payments Operations SQL Analysis

A small, self-directed SQL project that answers the questions a support or account team asks about a payments platform: where are payments failing, which integrations are broken, and are the two connected?

**The data is synthetic.** `seed.py` generates a reproducible dataset (seed 42) in SQLite. It contains no real customer or platform data. I planted four problems in it so I could check the queries find them:

- Merchant 7 has a 10-day spike in `authentication_required` declines.
- Webhook endpoint 5 times out and returns 503/504.
- Webhook endpoint 9 returns 410 (the URL no longer exists).
- Webhook endpoint 14 returns 401 (the receiving server is rejecting the request, which is what a broken signature check looks like).

## Run it

```
python seed.py          # builds payments.db (needs only Python 3)
python run_queries.py   # runs all 9 queries and prints results
```

## Tables

`merchants`, `charges`, `webhook_endpoints`, `webhook_events`, `webhook_deliveries`, `support_cases`. See `schema.sql`.

## Queries (`queries.sql`)

| # | Question | Techniques |
|---|----------|-----------|
| 1 | Daily success rate | aggregation, date functions |
| 2 | Why do payments fail, by payment method? | window function (`SUM() OVER`) |
| 3 | Enterprise vs SME success by country | join, conditional aggregation |
| 4 | Which merchants dropped sharply week over week? | CTEs, `LAG` |
| 5 | Which webhook endpoints fail on first attempt? | multi-table join, `HAVING` |
| 6 | What are the failing endpoints returning? | subquery, `COALESCE` for timeouts |
| 7 | Which events were never delivered after all retries? | `NOT EXISTS` |
| 8 | Support load and time to close by category and tier | `julianday` arithmetic |
| 9 | Do webhook failures show up as support cases? | two CTEs joined per merchant |

## What the results show

- Q5 and Q6 pick out endpoints 5, 9 and 14 and the response each returns, which points to the fix: a 503/timeout is a capacity or availability problem on the merchant side, a 410 means the URL is dead and needs updating, a 401 means authentication on the receiving end is rejecting events.
- Q7 shows how many events were lost for good on each endpoint, which is the number a merchant actually cares about.
- Q9 shows the same three merchants also have the most webhook support cases, so delivery failures are visible in the ticket queue.
- Q4 flags merchant 7's drop in week 8.

## Limits

SQLite has no median function, so Q8 uses averages. The dataset is small and clean compared with production data, so these queries would need tuning (indexes, partitioning, date filters) at real scale.
