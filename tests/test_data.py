"""The generated data has to match the data model doc, or nothing downstream does."""

import datetime as dt
import sqlite3
from decimal import Decimal

import pytest

from data import model as m

OPEN_BALANCES = {
    "C-10231": Decimal("38000.00"),   # Summit Trail
    "C-10388": Decimal("31000.00"),   # Blue Ridge
    "C-10412": Decimal("22000.00"),   # Cascade
    "C-10507": Decimal("2000.00"),    # Pinecrest
    "C-10619": Decimal("12000.00"),   # Northfork
}

MOST_PAST_DUE = {"C-10231": 0, "C-10388": 0, "C-10412": 75, "C-10507": 0, "C-10619": 45}


def D(value):
    return Decimal(str(value))


@pytest.mark.parametrize("erp_id,expected", OPEN_BALANCES.items())
def test_open_balance(erp, erp_id, expected):
    rows = erp.execute(
        "SELECT amount, amount_paid FROM invoices "
        "WHERE erp_customer_id = ? AND status = 'Open'", (erp_id,)).fetchall()
    assert sum((D(r["amount"]) - D(r["amount_paid"]) for r in rows), Decimal(0)) == expected


@pytest.mark.parametrize("erp_id,expected", MOST_PAST_DUE.items())
def test_most_past_due_days(erp, as_of, erp_id, expected):
    rows = erp.execute(
        "SELECT due_date FROM invoices WHERE erp_customer_id = ? AND status = 'Open'",
        (erp_id,)).fetchall()
    worst = max(((as_of - dt.date.fromisoformat(r["due_date"])).days for r in rows),
                default=0)
    assert max(worst, 0) == expected


def test_every_invoice_matches_its_order_total(crm, erp):
    for row in erp.execute("SELECT invoice_number, order_id, amount FROM invoices"):
        order = crm.execute("SELECT total FROM orders WHERE order_id = ?",
                            (row["order_id"],)).fetchone()
        assert order is not None, f"{row['invoice_number']} points at a missing order"
        assert D(order["total"]) == D(row["amount"]), row["invoice_number"]


def test_order_lines_sum_to_the_order_total(crm):
    for row in crm.execute("SELECT order_id, total FROM orders"):
        lines = crm.execute("SELECT line_total FROM order_lines WHERE order_id = ?",
                            (row["order_id"],)).fetchall()
        assert sum((D(r["line_total"]) for r in lines), Decimal(0)) == D(row["total"])


def test_freight_stays_within_three_percent(crm):
    for row in crm.execute("SELECT order_id, freight, total FROM orders"):
        if D(row["total"]) > 0:
            share = D(row["freight"]) / D(row["total"]) * 100
            assert share <= Decimal("3.01"), row["order_id"]


@pytest.mark.parametrize("account", m.ACCOUNTS, ids=lambda a: a["account_id"])
def test_order_trend_hits_its_target(crm, as_of, account):
    """Order dollars, last 90 days vs the 90 before, freight excluded."""
    last = prior = Decimal(0)
    for row in crm.execute(
            "SELECT order_date, freight, total FROM orders WHERE account_id = ?",
            (account["account_id"],)):
        days = (as_of - dt.date.fromisoformat(row["order_date"])).days
        value = D(row["total"]) - D(row["freight"])
        if 0 <= days < m.WINDOW_DAYS:
            last += value
        elif m.WINDOW_DAYS <= days < 2 * m.WINDOW_DAYS:
            prior += value
    change = (last / prior - 1) * 100
    assert abs(change - D(account["trend_target_pct"])) <= 3, (
        f"{account['name']}: {change:+.1f}% vs target {account['trend_target_pct']:+.1f}%")


def test_northfork_is_the_only_flagged_account():
    flagged = [a["name"] for a in m.ACCOUNTS if a["trend_target_pct"] <= -25]
    assert flagged == ["Northfork Paddle & Pack"]


def test_pending_orders_are_not_invoiced(crm, erp):
    invoiced = {r["order_id"] for r in erp.execute("SELECT order_id FROM invoices")}
    for pending in m.PENDING_ORDERS:
        row = crm.execute("SELECT total FROM orders WHERE order_id = ?",
                          (pending["order_id"],)).fetchone()
        assert row is not None
        assert D(row["total"]) == D(pending["total"]) / 100
        assert pending["order_id"] not in invoiced


def test_rebuilding_is_deterministic(tmp_path, data_dir, as_of):
    from data import generate
    generate.build(tmp_path / "crm.db", tmp_path / "erp.db", as_of)
    again = sqlite3.connect(tmp_path / "crm.db")
    original = sqlite3.connect(data_dir / "crm.db")
    rows_a = again.execute("SELECT order_id, total FROM orders ORDER BY order_id").fetchall()
    rows_b = original.execute("SELECT order_id, total FROM orders ORDER BY order_id").fetchall()
    again.close()
    original.close()
    assert rows_a == rows_b
