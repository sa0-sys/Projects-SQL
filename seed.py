"""Builds payments.db with synthetic data. Run: python seed.py  (deterministic, seed=42)."""
import random, sqlite3
from datetime import datetime, timedelta

random.seed(42)
con = sqlite3.connect("payments.db")
con.executescript(open("schema.sql").read())
cur = con.cursor()
start = datetime(2026, 1, 1)
DAYS = 90

countries = ["IE", "GB", "DE", "NG", "AU", "US"]
methods = ["card", "card", "card", "bank_debit", "wallet"]
codes = ["insufficient_funds", "card_declined", "expired_card", "authentication_required", "processing_error"]

# merchants: 12 enterprise, 28 SME
merchants = []
for i in range(1, 41):
    seg = "enterprise" if i <= 12 else "sme"
    merchants.append((i, f"Merchant {i:02d}", seg, random.choice(countries), (start - timedelta(days=random.randint(30, 900))).isoformat()))
cur.executemany("INSERT INTO merchants VALUES (?,?,?,?,?)", merchants)

# planted pattern: merchant 7 has a bad week of declines (authentication_required) from day 50
BAD_MERCHANT, BAD_FROM = 7, 50

charges = []
cid = 1
for m in merchants:
    mid, seg = m[0], m[2]
    per_day = 14 if seg == "enterprise" else 4
    for d in range(DAYS):
        for _ in range(random.randint(per_day // 2, per_day)):
            fail_p = 0.07
            if mid == BAD_MERCHANT and BAD_FROM <= d < BAD_FROM + 10:
                fail_p = 0.45
            failed = random.random() < fail_p
            code = None
            if failed:
                code = "authentication_required" if (mid == BAD_MERCHANT and BAD_FROM <= d < BAD_FROM + 10 and random.random() < .8) else random.choice(codes)
            ts = start + timedelta(days=d, seconds=random.randint(0, 86399))
            charges.append((cid, mid, random.randint(500, 90000), "EUR", random.choice(methods),
                            "failed" if failed else "succeeded", code, ts.isoformat()))
            cid += 1
cur.executemany("INSERT INTO charges VALUES (?,?,?,?,?,?,?,?)", charges)

# webhook endpoints: merchants 1..30 have one
endpoints = [(i, i, f"https://merchant{i:02d}.example.com/hooks") for i in range(1, 31)]
cur.executemany("INSERT INTO webhook_endpoints VALUES (?,?,?)", endpoints)

# planted patterns: endpoint 5 times out / 503s often; endpoint 9 returns 410 (URL gone); endpoint 14 returns 401 (bad signature check)
events, deliveries = [], []
eid, did = 1, 1
for ep in endpoints:
    n_events = random.randint(150, 260)
    for _ in range(n_events):
        ts = start + timedelta(days=random.randint(0, DAYS - 1), seconds=random.randint(0, 86399))
        events.append((eid, ep[0], random.choice(["charge.succeeded", "charge.failed", "invoice.paid", "payout.paid"]), ts.isoformat()))
        if ep[0] == 5:
            p_ok = 0.35
        elif ep[0] == 9:
            p_ok = 0.0
        elif ep[0] == 14:
            p_ok = 0.05
        else:
            p_ok = 0.985
        for attempt in range(1, 5):
            ok = random.random() < p_ok
            if ok:
                status = 200
            elif ep[0] == 5:
                status = random.choice([503, 503, None, 504])
            elif ep[0] == 9:
                status = 410
            elif ep[0] == 14:
                status = 401
            else:
                status = random.choice([500, 502, None])
            deliveries.append((did, eid, attempt, status, 1 if ok else 0, (ts + timedelta(minutes=attempt * attempt * 5)).isoformat()))
            did += 1
            if ok:
                break
        eid += 1
cur.executemany("INSERT INTO webhook_events VALUES (?,?,?,?)", events)
cur.executemany("INSERT INTO webhook_deliveries VALUES (?,?,?,?,?,?)", deliveries)

# support cases: more cases where webhooks or declines misbehave
cats = ["api_integration", "webhooks", "declines", "payouts", "account_access", "reporting"]
cases, cs = [], 1
for m in merchants:
    mid = m[0]
    n = random.randint(1, 5)
    if mid in (5, 9, 14):
        n += 8
    if mid == BAD_MERCHANT:
        n += 6
    for _ in range(n):
        if mid in (5, 9, 14) and random.random() < .7:
            cat = "webhooks"
        elif mid == BAD_MERCHANT and random.random() < .7:
            cat = "declines"
        else:
            cat = random.choice(cats)
        opened = start + timedelta(days=random.randint(0, DAYS - 1), hours=random.randint(0, 23))
        tier = random.choices([1, 2, 3], [.6, .28, .12])[0]
        hrs = {1: random.randint(1, 30), 2: random.randint(10, 120), 3: random.randint(40, 400)}[tier]
        closed = None if random.random() < .06 else (opened + timedelta(hours=hrs)).isoformat()
        cases.append((cs, mid, cat, opened.isoformat(), closed, tier))
        cs += 1
cur.executemany("INSERT INTO support_cases VALUES (?,?,?,?,?,?)", cases)

con.commit()
for t in ["merchants", "charges", "webhook_endpoints", "webhook_events", "webhook_deliveries", "support_cases"]:
    print(t, cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
con.close()
