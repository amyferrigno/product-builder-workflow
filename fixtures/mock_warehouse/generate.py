#!/usr/bin/env python3
"""
Regenerate the synthetic mock warehouse CSVs (deterministic, seed 42).
All data is invented. Usage: python fixtures/mock_warehouse/generate.py
"""

import csv
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent
SEGMENTS = ["smb", "mid_market", "enterprise"]
PLANS = ["starter", "pro", "team"]
CATEGORIES = ["scheduling_conflict", "timezone_confusion", "reminders", "calendar_sync", "billing", "other"]
MONTHS = ["2025-%02d" % m for m in range(1, 13)]


def write(name, header, rows):
    with open(OUT / name, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main():
    rng = random.Random(42)

    accounts = []
    for i in range(1, 61):
        accounts.append((f"A{i:03d}", rng.choice(SEGMENTS), rng.choice(PLANS), rng.choice(MONTHS[:6])))
    write("accounts.csv", ["account_id", "segment", "plan", "signup_month"], accounts)

    tickets = []
    for i in range(1, 301):
        account = rng.choice(accounts)[0]
        category = rng.choices(CATEGORIES, weights=[30, 20, 15, 15, 10, 10])[0]
        tickets.append((f"T{i:04d}", account, category, rng.choice(MONTHS[6:])))
    write("support_tickets.csv", ["ticket_id", "account_id", "category", "created_month"], tickets)

    events = []
    for i in range(1, 401):
        account = rng.choice(accounts)
        messages = rng.randint(2, 14) if account[1] != "enterprise" else rng.randint(4, 20)
        minutes = rng.randint(5, 90) + messages * 2
        completed = 1 if rng.random() < 0.85 else 0
        events.append((f"E{i:04d}", account[0], messages, minutes, completed))
    write("scheduling_events.csv",
          ["event_id", "account_id", "messages_exchanged", "minutes_to_confirm", "completed"], events)

    customers = []
    for i in range(1, 81):
        customers.append((f"C{i:03d}", rng.choice(accounts)[0], f"Test Person {i}",
                          f"person{i}@example.invalid", f"+00 000 {i:04d}"))
    write("customers.csv", ["customer_id", "account_id", "full_name", "email", "phone"], customers)


if __name__ == "__main__":
    main()
