"""Builds crm.db (mock Salesforce) and erp.db (mock ERP) from the data model.

Everything is derived from day-offsets against AS_OF, so the expected answers in
the data model doc hold whatever day this runs. All money is integer cents here;
only the final write to SQLite converts to dollars.

Run directly:  uv run python -m data.generate
"""

from __future__ import annotations

import datetime as dt
import os
import random
import sqlite3
from pathlib import Path

from data import model as m

ROOT = Path(__file__).resolve().parent.parent


# --- helpers ---------------------------------------------------------------

def as_of_date() -> dt.date:
    """Today, unless AS_OF overrides it (e.g. AS_OF=2026-10-07 to replay a given day)."""
    raw = os.environ.get("AS_OF", "").strip()
    if raw:
        return dt.date.fromisoformat(raw)
    return dt.date.today()


def days_before(as_of: dt.date, days: int) -> str:
    return (as_of - dt.timedelta(days=days)).isoformat()


def dollars(cents: int) -> float:
    """Cents -> dollars for storage. Values are always whole cents."""
    return round(cents / 100, 2)


def contract_price_cents(list_cents: int, tier: str) -> int:
    """Tier price, rounded half up to the cent. Gold -10%, Silver -5%, Bronze list."""
    pct = m.TIER_DISCOUNT_PCT[tier]
    if pct == 0:
        return list_cents
    # half-up on integers: (a * (100 - pct) + 50) // 100
    return (list_cents * (100 - pct) + 50) // 100


def tier_prices(tier: str) -> dict[str, int]:
    return {
        p["sku"]: contract_price_cents(p["list_price"], tier)
        for p in m.PRODUCTS
        if p["sku"] != m.FREIGHT_SKU
    }


def compose_near(prices: dict[str, int], target: int, rng: random.Random):
    """Random line items whose subtotal is just under `target`.

    Returns (lines, subtotal). The shortfall is always less than the cheapest
    unit price, because the cheapest SKU closes the gap last.
    """
    lines: dict[str, int] = {}
    remaining = target
    skus = list(prices)
    rng.shuffle(skus)
    for sku in skus:
        price = prices[sku]
        if price > remaining:
            continue
        max_q = remaining // price
        q = rng.randint(1, max(1, max_q // 2))
        lines[sku] = lines.get(sku, 0) + q
        remaining -= q * price
    cheapest = min(prices, key=lambda s: prices[s])
    if prices[cheapest] <= remaining:
        q = remaining // prices[cheapest]
        lines[cheapest] = lines.get(cheapest, 0) + q
        remaining -= q * prices[cheapest]
    return lines, target - remaining


def compose_to_total(prices: dict[str, int], total: int, rng: random.Random,
                     attempts: int = 800):
    """Line items plus a freight line that together hit `total` exactly.

    This is how an order matches its invoice to the cent. Freight is whatever is
    left over, and it has to stay within MAX_FREIGHT_PCT of the order, so we
    resample until it does.
    """
    floor_subtotal = total - (total * m.MAX_FREIGHT_PCT) // 100
    for _ in range(attempts):
        lines, subtotal = compose_near(prices, total, rng)
        if lines and subtotal >= floor_subtotal:
            return lines, subtotal, total - subtotal
    raise RuntimeError(f"could not compose an order totalling {total} cents")


def freight_for(subtotal: int, rng: random.Random) -> int:
    """A plausible freight charge: 1-3% of the order."""
    pct = rng.uniform(1.0, float(m.MAX_FREIGHT_PCT))
    return int(round(subtotal * pct / 100))


# --- order construction ----------------------------------------------------

class OrderBuilder:
    def __init__(self):
        self.orders = []          # dicts with order_id/account_id/date/lines/...
        self._seq = 1000

    def next_id(self) -> str:
        self._seq += 1
        return f"ORD-{self._seq}"

    def add(self, account_id, order_date, lines, subtotal, freight, order_id=None):
        order_id = order_id or self.next_id()
        self.orders.append({
            "order_id": order_id,
            "account_id": account_id,
            "order_date": order_date,
            "lines": lines,
            "subtotal": subtotal,          # ex-freight: this is "order dollars"
            "freight": freight,
            "total": subtotal + freight,
        })
        return self.orders[-1]


def fill_window(builder, account, prices, as_of, needed, day_lo, day_hi,
                n_orders, rng):
    """Lay down filler orders inside a 90-day window to hit an order-dollar target."""
    if needed <= 0 or n_orders <= 0:
        return
    remaining = needed
    for i in range(n_orders):
        left = n_orders - i
        target = remaining if left == 1 else int(remaining / left * rng.uniform(0.75, 1.25))
        target = min(target, remaining)
        if target < min(prices.values()):
            break
        lines, subtotal = compose_near(prices, target, rng)
        if not lines:
            continue
        day = rng.randint(day_lo, day_hi)
        builder.add(account["account_id"], days_before(as_of, day), lines, subtotal,
                    freight_for(subtotal, rng))
        remaining -= subtotal
    # Anything left over is a rounding crumb smaller than the cheapest unit.


SEASON_SHAPE = {
    # days_ago -> multiplier, for history older than the two trend windows
    "spring_preseason": lambda d: 2.2 if 181 <= d <= 215 else (1.6 if 330 <= d <= 400 else 0.7),
    "summer_heavy": lambda d: 1.8 if 200 <= d <= 300 else 0.5,
    "steady": lambda d: 1.0,
    "small_frequent": lambda d: 1.0,
    "slowdown": lambda d: 1.4,  # healthy for a year, then the recent drop
}


def fill_history(builder, account, prices, as_of, rng):
    """Older history (beyond the two trend windows), shaped by seasonality."""
    shape = SEASON_SHAPE[account["seasonality"]]
    base = account["window_prior_90"] // 6  # a typical order for this account
    day = 2 * m.WINDOW_DAYS + 1
    while day <= m.HISTORY_DAYS:
        gap = rng.randint(8, 24) if account["seasonality"] == "small_frequent" else rng.randint(14, 40)
        target = int(base * shape(day) * rng.uniform(0.6, 1.4))
        if target >= min(prices.values()):
            lines, subtotal = compose_near(prices, target, rng)
            if lines:
                builder.add(account["account_id"], days_before(as_of, day), lines,
                            subtotal, freight_for(subtotal, rng))
        day += gap


def build_orders(as_of: dt.date):
    """All orders for every account, plus the invoice each one maps to."""
    builder = OrderBuilder()
    invoices = []           # dicts ready for erp.db
    anchor_for_invoice = {}

    # 1. Anchor orders for the nine open invoices: the order total IS the invoice.
    for inv in m.OPEN_INVOICES:
        account = next(a for a in m.ACCOUNTS if a["erp_customer_id"] == inv["erp_customer_id"])
        rng = random.Random(f"anchor-{inv['invoice_number']}")
        prices = tier_prices(account["tier"])
        lines, subtotal, freight = compose_to_total(prices, inv["amount"], rng)
        order = builder.add(account["account_id"],
                            days_before(as_of, inv["issued_days_ago"]),
                            lines, subtotal, freight)
        anchor_for_invoice[inv["invoice_number"]] = order
        issue = days_before(as_of, inv["issued_days_ago"])
        due = days_before(as_of, inv["issued_days_ago"] - m.INVOICE_TERM_DAYS)
        invoices.append({
            "invoice_number": inv["invoice_number"],
            "erp_customer_id": inv["erp_customer_id"],
            "order_id": order["order_id"],
            "issue_date": issue,
            "due_date": due,
            "amount": inv["amount"],
            "amount_paid": 0,
            "status": "Open",
        })

    # 2. Pending orders: booked, no invoice pointing at them yet.
    for pend in m.PENDING_ORDERS:
        account = m.account_by_id(pend["account_id"])
        rng = random.Random(f"pending-{pend['order_id']}")
        prices = tier_prices(account["tier"])
        lines, subtotal, freight = compose_to_total(prices, pend["total"], rng)
        builder.add(account["account_id"], days_before(as_of, pend["ordered_days_ago"]),
                    lines, subtotal, freight, order_id=pend["order_id"])

    # 3. Named accounts: hit the trend targets, then lay down older history.
    for account in m.ACCOUNTS:
        rng = random.Random(f"trend-{account['account_id']}")
        prices = tier_prices(account["tier"])
        mine = [o for o in builder.orders if o["account_id"] == account["account_id"]]

        def window_total(lo, hi):
            total = 0
            for o in mine:
                days = (as_of - dt.date.fromisoformat(o["order_date"])).days
                if lo <= days <= hi:
                    total += o["subtotal"]
            return total

        last_have = window_total(0, m.WINDOW_DAYS - 1)
        prior_have = window_total(m.WINDOW_DAYS, 2 * m.WINDOW_DAYS - 1)
        n = 10 if account["seasonality"] == "small_frequent" else 5
        fill_window(builder, account, prices, as_of,
                    account["window_last_90"] - last_have, 1, m.WINDOW_DAYS - 1, n, rng)
        fill_window(builder, account, prices, as_of,
                    account["window_prior_90"] - prior_have,
                    m.WINDOW_DAYS, 2 * m.WINDOW_DAYS - 1, n, rng)
        fill_history(builder, account, prices, as_of, rng)

    # 4. Filler accounts: plausible noise, no open invoices.
    for (acct_id, _name, tier, _region, _owner, _erp, _limit) in m.FILLER_ACCOUNTS:
        rng = random.Random(f"filler-{acct_id}")
        prices = tier_prices(tier)
        prior = rng.randint(400000, 3000000)
        last = int(prior * (1 + rng.uniform(-0.12, 0.12)))
        fake = {"account_id": acct_id, "window_prior_90": prior,
                "seasonality": "steady"}
        fill_window(builder, fake, prices, as_of, last, 1, m.WINDOW_DAYS - 1, 4, rng)
        fill_window(builder, fake, prices, as_of, prior, m.WINDOW_DAYS,
                    2 * m.WINDOW_DAYS - 1, 4, rng)
        fill_history(builder, fake, prices, as_of, rng)

    # 5. Every other order is already paid for: a matching Paid invoice.
    pending_ids = {p["order_id"] for p in m.PENDING_ORDERS}
    anchored_ids = {o["order_id"] for o in anchor_for_invoice.values()}
    erp_by_account = {a["account_id"]: a["erp_customer_id"] for a in m.ACCOUNTS}
    for (acct_id, _n, _t, _r, _o, erp_id, _l) in m.FILLER_ACCOUNTS:
        erp_by_account[acct_id] = erp_id

    seq = 1000
    for order in sorted(builder.orders, key=lambda o: o["order_date"]):
        if order["order_id"] in pending_ids or order["order_id"] in anchored_ids:
            continue
        seq += 1
        invoices.append({
            "invoice_number": f"INV-{seq}",
            "erp_customer_id": erp_by_account[order["account_id"]],
            "order_id": order["order_id"],
            "issue_date": order["order_date"],
            "due_date": (dt.date.fromisoformat(order["order_date"])
                         + dt.timedelta(days=m.INVOICE_TERM_DAYS)).isoformat(),
            "amount": order["total"],
            "amount_paid": order["total"],
            "status": "Paid",
        })

    return builder.orders, invoices


# --- schema + write --------------------------------------------------------

CRM_SCHEMA = """
CREATE TABLE users (
    name TEXT PRIMARY KEY, role TEXT, region TEXT
);
CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY, name TEXT, tier TEXT, region TEXT,
    owner TEXT, erp_customer_id TEXT, credit_limit REAL
);
CREATE TABLE products (
    sku TEXT PRIMARY KEY, name TEXT, category TEXT, list_price REAL, description TEXT
);
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY, account_id TEXT, order_date TEXT,
    status TEXT, freight REAL, total REAL
);
CREATE TABLE order_lines (
    order_id TEXT, line_no INTEGER, sku TEXT, quantity INTEGER,
    unit_price REAL, line_total REAL
);
CREATE TABLE discount_requests (
    request_id TEXT PRIMARY KEY, account_id TEXT, sku TEXT, quantity INTEGER,
    discount_pct REAL, contract_unit_price REAL, discounted_unit_price REAL,
    total REAL, requested_via TEXT, status TEXT, approver TEXT, reason TEXT,
    created_at TEXT
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX idx_orders_account ON orders(account_id, order_date);
CREATE INDEX idx_lines_order ON order_lines(order_id);
"""

ERP_SCHEMA = """
CREATE TABLE erp_customers (
    erp_customer_id TEXT PRIMARY KEY, legal_name TEXT,
    credit_limit REAL, default_terms TEXT
);
CREATE TABLE invoices (
    invoice_number TEXT PRIMARY KEY, erp_customer_id TEXT, order_id TEXT,
    issue_date TEXT, due_date TEXT, amount REAL, amount_paid REAL, status TEXT
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX idx_invoices_customer ON invoices(erp_customer_id, status);
"""


def build(crm_path: Path, erp_path: Path, as_of: dt.date | None = None) -> dt.date:
    as_of = as_of or as_of_date()
    orders, invoices = build_orders(as_of)

    for path in (crm_path, erp_path):
        if path.exists():
            path.unlink()

    crm = sqlite3.connect(crm_path)
    crm.executescript(CRM_SCHEMA)
    crm.executemany("INSERT INTO users VALUES (?,?,?)",
                    [(u["name"], u["role"], u["region"]) for u in m.USERS])
    crm.executemany(
        "INSERT INTO accounts VALUES (?,?,?,?,?,?,?)",
        [(a["account_id"], a["name"], a["tier"], a["region"], a["owner"],
          a["erp_customer_id"], dollars(a["credit_limit"])) for a in m.ACCOUNTS]
        + [(f[0], f[1], f[2], f[3], f[4], f[5], dollars(f[6])) for f in m.FILLER_ACCOUNTS],
    )
    crm.executemany(
        "INSERT INTO products VALUES (?,?,?,?,?)",
        [(p["sku"], p["name"], p["category"], dollars(p["list_price"]), p["description"])
         for p in m.PRODUCTS],
    )
    crm.executemany(
        "INSERT INTO orders VALUES (?,?,?,?,?,?)",
        [(o["order_id"], o["account_id"], o["order_date"], "Activated",
          dollars(o["freight"]), dollars(o["total"])) for o in orders],
    )

    line_rows = []
    for order in orders:
        account = next((a for a in m.ACCOUNTS if a["account_id"] == order["account_id"]), None)
        tier = account["tier"] if account else next(
            f[2] for f in m.FILLER_ACCOUNTS if f[0] == order["account_id"])
        prices = tier_prices(tier)
        line_no = 0
        for sku, qty in sorted(order["lines"].items()):
            line_no += 1
            unit = prices[sku]
            line_rows.append((order["order_id"], line_no, sku, qty,
                              dollars(unit), dollars(unit * qty)))
        if order["freight"]:
            line_no += 1
            line_rows.append((order["order_id"], line_no, m.FREIGHT_SKU, 1,
                              dollars(order["freight"]), dollars(order["freight"])))
    crm.executemany("INSERT INTO order_lines VALUES (?,?,?,?,?,?)", line_rows)
    crm.executemany("INSERT INTO meta VALUES (?,?)",
                    [("built_on", dt.date.today().isoformat()),
                     ("as_of", as_of.isoformat())])
    crm.commit()
    crm.close()

    erp = sqlite3.connect(erp_path)
    erp.executescript(ERP_SCHEMA)
    erp.executemany(
        "INSERT INTO erp_customers VALUES (?,?,?,?)",
        [(a["erp_customer_id"], a["legal_name"], dollars(a["credit_limit"]), m.DEFAULT_TERMS)
         for a in m.ACCOUNTS]
        + [(f[5], f[1], dollars(f[6]), m.DEFAULT_TERMS) for f in m.FILLER_ACCOUNTS],
    )
    erp.executemany(
        "INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?)",
        [(i["invoice_number"], i["erp_customer_id"], i["order_id"], i["issue_date"],
          i["due_date"], dollars(i["amount"]), dollars(i["amount_paid"]), i["status"])
         for i in invoices],
    )
    erp.executemany("INSERT INTO meta VALUES (?,?)",
                    [("built_on", dt.date.today().isoformat()),
                     ("as_of", as_of.isoformat())])
    erp.commit()
    erp.close()
    return as_of


def is_stale(crm_path: Path, erp_path: Path, as_of: dt.date | None = None) -> bool:
    """True if the databases are missing, built on an earlier day, or for a different AS_OF."""
    as_of = as_of or as_of_date()
    for path in (crm_path, erp_path):
        if not path.exists():
            return True
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            rows = dict(con.execute("SELECT key, value FROM meta").fetchall())
            con.close()
        except sqlite3.Error:
            return True
        if rows.get("built_on") != dt.date.today().isoformat():
            return True
        if rows.get("as_of") != as_of.isoformat():
            return True
    return False


def ensure_fresh(crm_path: Path, erp_path: Path, as_of: dt.date | None = None) -> bool:
    """Rebuild if stale. Returns True when a rebuild happened."""
    if is_stale(crm_path, erp_path, as_of):
        build(crm_path, erp_path, as_of)
        return True
    return False


if __name__ == "__main__":
    when = build(ROOT / "crm.db", ROOT / "erp.db")
    print(f"Built crm.db and erp.db for AS_OF {when.isoformat()}")
