"""Ridgeline's Pricing & Credit service — every business rule lives here.

In production this would be a process API (MuleSoft, an Apex service, a pricing
microservice) sitting on top of system APIs for Salesforce and the ERP. Here it
reads crm.db (mock Salesforce) and erp.db (mock ERP) directly.

The MCP server is a thin layer on top of this file. This file is never edited
during the walkthrough: it is the stand-in for the systems that own the rules.

Money is Decimal throughout, rounded half up to the cent. Floats would turn
$190.485 into $190.48 and quietly break the expected answers.
"""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from data import generate, model as m

ROOT = Path(__file__).resolve().parent
# RIDGELINE_DATA_DIR lets the tests work on their own copy of the databases
# instead of the ones the demo is using.
DATA_DIR = Path(os.environ.get("RIDGELINE_DATA_DIR") or ROOT)
CRM_DB = DATA_DIR / "crm.db"
ERP_DB = DATA_DIR / "erp.db"

CENT = Decimal("0.01")
_databases_checked = False


# --- plumbing --------------------------------------------------------------

def ensure_databases() -> None:
    """Build crm.db / erp.db if they are missing or were built on an earlier day.

    Called by every public function, so running the MCP server straight from
    Claude Desktop needs no setup step.
    """
    global _databases_checked
    if _databases_checked and CRM_DB.exists() and ERP_DB.exists():
        return
    generate.ensure_fresh(CRM_DB, ERP_DB)
    _databases_checked = True


def _connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def money(value) -> Decimal:
    """Any stored number -> an exact Decimal amount."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def apply_pct(amount: Decimal, pct) -> Decimal:
    """Take `pct` percent off `amount`, rounded half up to the cent."""
    factor = (Decimal(100) - Decimal(str(pct))) / Decimal(100)
    return (amount * factor).quantize(CENT, rounding=ROUND_HALF_UP)


def usd(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def pct_str(value) -> str:
    """5 -> "5", 7.5 -> "7.5". Decimal.normalize() would render 10 as 1E+1."""
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if d == d.to_integral_value():
        return str(d.to_integral_value())
    return str(d.normalize())


def _as_of() -> dt.date:
    """The date the data was built for (today, unless AS_OF overrode it)."""
    con = _connect(CRM_DB)
    row = con.execute("SELECT value FROM meta WHERE key='as_of'").fetchone()
    con.close()
    return dt.date.fromisoformat(row["value"])


# --- accounts --------------------------------------------------------------

def _account_row(account_id: str):
    con = _connect(CRM_DB)
    row = con.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
    con.close()
    return row


def find_account(name: str) -> dict:
    """Look an account up by name (or by account id)."""
    ensure_databases()
    needle = (name or "").strip().lower()
    con = _connect(CRM_DB)
    rows = con.execute("SELECT * FROM accounts").fetchall()
    con.close()

    match = None
    for row in rows:
        if row["account_id"].lower() == needle or row["name"].lower() == needle:
            match = row
            break

    if match is None and needle:
        # "Summit Trail" should find "Summit Trail Co.". Anything that matches
        # more than one account is reported back rather than guessed at.
        partial = [row for row in rows if needle in row["name"].lower()]
        if len(partial) == 1:
            match = partial[0]
        elif len(partial) > 1:
            return {
                "found": False,
                "searched_for": name,
                "candidates": [row["name"] for row in partial],
                "message": (f"More than one account matches {name!r}: "
                            f"{', '.join(row['name'] for row in partial)}. "
                            f"Ask which one is meant."),
            }

    if match is None:
        return {
            "found": False,
            "searched_for": name,
            "candidates": sorted(row["name"] for row in rows),
            "message": (f"No Ridgeline account matches {name!r}. "
                        f"The accounts are listed in candidates."),
        }

    standing = get_account_standing(match["account_id"])
    credit = _credit_snapshot(match["account_id"])
    on_hold = standing["standing"] == m.STANDING_CREDIT_HOLD
    return {
        "found": True,
        "account_id": match["account_id"],
        "name": match["name"],
        "tier": match["tier"],
        "region": match["region"],
        "sales_rep": match["owner"],
        "erp_customer_id": match["erp_customer_id"],
        "credit_limit": float(credit["credit_limit"]),
        "open_balance": float(credit["open_balance"]),
        "available_credit": float(credit["available_credit"]),
        "standing": standing["standing"],
        "standing_reason": standing["reason"],
        "payment_terms": "Prepay only" if on_hold else m.DEFAULT_TERMS,
        "net_60_possible": match["tier"] == "Gold" and standing["standing"] == m.STANDING_GOOD,
        "summary": (
            f"{match['name']} ({match['account_id']}) — {match['tier']} tier, "
            f"rep {match['owner']}, standing {standing['standing']}, "
            f"terms {'Prepay only' if on_hold else m.DEFAULT_TERMS}, "
            f"{usd(credit['available_credit'])} credit available."
        ),
    }


def get_account_standing(account_id: str) -> dict:
    """Standing comes from the most past-due OPEN invoice in the ERP.

    Good: nothing more than 30 days past due.
    Watch: the most past-due invoice is 31-60 days past due.
    Credit hold: anything more than 60 days past due.
    """
    ensure_databases()
    account = _account_row(account_id)
    if account is None:
        return {"found": False, "message": f"No account {account_id}."}

    as_of = _as_of()
    con = _connect(ERP_DB)
    rows = con.execute(
        "SELECT * FROM invoices WHERE erp_customer_id = ? AND status = 'Open'",
        (account["erp_customer_id"],),
    ).fetchall()
    con.close()

    worst_days = 0
    worst_invoice = None
    for row in rows:
        days = (as_of - dt.date.fromisoformat(row["due_date"])).days
        if days > worst_days:
            worst_days, worst_invoice = days, row["invoice_number"]

    if worst_days > m.CREDIT_HOLD_DAYS:
        standing = m.STANDING_CREDIT_HOLD
        reason = (f"{worst_invoice} is {worst_days} days past due "
                  f"(more than {m.CREDIT_HOLD_DAYS} days).")
    elif worst_days > m.WATCH_DAYS:
        standing = m.STANDING_WATCH
        reason = f"{worst_invoice} is {worst_days} days past due."
    else:
        standing = m.STANDING_GOOD
        reason = "No invoice is more than 30 days past due."

    return {
        "found": True,
        "account_id": account_id,
        "standing": standing,
        "reason": reason,
        "most_past_due_days": worst_days,
        "most_past_due_invoice": worst_invoice,
    }


# --- contract pricing ------------------------------------------------------

def get_contract_pricing(account_id: str, sku: str, quantity: int,
                         extra_discount_pct=0) -> dict:
    """The account's contract price for a SKU: Gold -10%, Silver -5%, Bronze list.

    `extra_discount_pct` prices up a proposed extra discount on top of the
    contract price. It only does the arithmetic — nothing is submitted and no
    approval is decided here. That is request_discount's job.
    """
    ensure_databases()
    account = _account_row(account_id)
    if account is None:
        return {"found": False, "message": f"No account {account_id}."}

    con = _connect(CRM_DB)
    product = con.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    con.close()
    if product is None:
        return {"found": False, "message": f"No product with SKU {sku!r}."}

    quantity = int(quantity)
    list_price = money(product["list_price"])
    tier_pct = m.TIER_DISCOUNT_PCT[account["tier"]]
    unit = apply_pct(list_price, tier_pct)
    total = (unit * quantity).quantize(CENT, rounding=ROUND_HALF_UP)

    result = {
        "found": True,
        "account_id": account_id,
        "account_name": account["name"],
        "tier": account["tier"],
        "sku": sku,
        "product_name": product["name"],
        "quantity": quantity,
        "list_price": float(list_price),
        "tier_discount_pct": tier_pct,
        "contract_unit_price": float(unit),
        "line_total": float(total),
        "extra_discount_auto_approved_up_to_pct": m.SERVICE_AUTO_APPROVE_PCT,
        "extra_discount_needs_manager_above_pct": m.SERVICE_AUTO_APPROVE_PCT,
        "extra_discount_refused_above_pct": m.MANAGER_APPROVE_CEILING_PCT,
    }
    summary = (
        f"{account['name']} is {account['tier']} tier: {product['name']} lists at "
        f"{usd(list_price)} and their contract price is {usd(unit)} each. "
        f"{quantity} × {usd(unit)} = {usd(total)}."
    )

    extra_pct = Decimal(str(extra_discount_pct or 0))
    if extra_pct > 0:
        # Price up the proposed discount here, so nobody has to do the
        # arithmetic by hand. Whether it is allowed is decided at submit time.
        discounted_unit = apply_pct(unit, extra_pct)
        discounted_total = (discounted_unit * quantity).quantize(
            CENT, rounding=ROUND_HALF_UP)
        result.update({
            "extra_discount_pct": float(extra_pct),
            "discounted_unit_price": float(discounted_unit),
            "discounted_line_total": float(discounted_total),
        })
        summary += (
            f" With {pct_str(extra_pct)}% off that: {usd(discounted_unit)} each, "
            f"{usd(discounted_total)} total."
        )

    summary += (
        f" Extra discounts up to {m.SERVICE_AUTO_APPROVE_PCT}% are auto-approved, "
        f"above that needs the sales manager, and above "
        f"{m.MANAGER_APPROVE_CEILING_PCT}% is refused."
    )
    result["summary"] = summary
    return result


# --- credit ----------------------------------------------------------------

def _credit_snapshot(account_id: str) -> dict:
    """Credit limit minus the open invoice balance. Open invoices only."""
    account = _account_row(account_id)
    as_of = _as_of()
    con = _connect(ERP_DB)
    customer = con.execute(
        "SELECT * FROM erp_customers WHERE erp_customer_id = ?",
        (account["erp_customer_id"],),
    ).fetchone()
    rows = con.execute(
        "SELECT * FROM invoices WHERE erp_customer_id = ? AND status = 'Open' "
        "ORDER BY due_date",
        (account["erp_customer_id"],),
    ).fetchall()
    con.close()

    invoices = []
    open_balance = Decimal("0.00")
    for row in rows:
        balance = money(row["amount"]) - money(row["amount_paid"])
        open_balance += balance
        days = (as_of - dt.date.fromisoformat(row["due_date"])).days
        invoices.append({
            "invoice_number": row["invoice_number"],
            "issue_date": row["issue_date"],
            "due_date": row["due_date"],
            "amount": float(money(row["amount"])),
            "amount_paid": float(money(row["amount_paid"])),
            "open_balance": float(balance),
            "days_past_due": days if days > 0 else 0,
        })

    limit = money(customer["credit_limit"])
    return {
        "credit_limit": limit,
        "open_balance": open_balance,
        "available_credit": limit - open_balance,
        "invoices": invoices,
        "erp_customer_id": account["erp_customer_id"],
        "legal_name": customer["legal_name"],
    }


def check_credit(account_id: str, order_amount) -> dict:
    """Does this order fit, and what payment terms are available?

    Net 60 only for a Gold account in Good standing whose order fits available
    credit. Credit hold means prepay only. Everything else is Net 30.
    """
    ensure_databases()
    account = _account_row(account_id)
    if account is None:
        return {"found": False, "message": f"No account {account_id}."}

    amount = money(order_amount)
    credit = _credit_snapshot(account_id)
    standing = get_account_standing(account_id)
    available = credit["available_credit"]
    fits = amount <= available
    on_hold = standing["standing"] == m.STANDING_CREDIT_HOLD

    if on_hold:
        net_60 = False
        net_60_reason = f"Account is on credit hold — {standing['reason']} Prepay only."
        terms = ["Prepay"]
    elif account["tier"] != "Gold":
        net_60 = False
        net_60_reason = (f"Net 60 is Gold tier only; {account['name']} is "
                         f"{account['tier']} tier.")
        terms = [m.DEFAULT_TERMS]
    elif standing["standing"] != m.STANDING_GOOD:
        net_60 = False
        net_60_reason = (f"Net 60 needs Good standing; this account is on "
                         f"{standing['standing']} — {standing['reason']}")
        terms = [m.DEFAULT_TERMS]
    elif not fits:
        net_60 = False
        net_60_reason = (f"Net 60 needs the order to fit available credit; "
                         f"{usd(amount)} exceeds {usd(available)}.")
        terms = [m.DEFAULT_TERMS]
    else:
        net_60 = True
        net_60_reason = "Gold tier, Good standing, and the order fits available credit."
        terms = [m.DEFAULT_TERMS, "Net 60"]

    options = []
    partial = None
    if on_hold:
        options.append("Prepay the order.")
    elif not fits:
        options.append("Prepay the order.")
        half = (amount / 2).quantize(CENT, rounding=ROUND_HALF_UP)
        if half <= available:
            partial = float(half)
            options.append(
                f"Ship about half now on {m.DEFAULT_TERMS} ({usd(half)} fits within "
                f"{usd(available)} available) and the rest when the balance comes down."
            )

    if on_hold:
        summary = (f"{account['name']} is on credit hold — {standing['reason']} "
                   f"Prepay only; no terms available.")
    elif fits:
        summary = (f"{usd(amount)} fits: {usd(credit['credit_limit'])} limit minus "
                   f"{usd(credit['open_balance'])} open invoices leaves "
                   f"{usd(available)} available. Terms: {', '.join(terms)}.")
    else:
        summary = (f"{usd(amount)} exceeds available credit — "
                   f"{usd(credit['credit_limit'])} limit minus "
                   f"{usd(credit['open_balance'])} open invoices leaves "
                   f"{usd(available)}. {net_60_reason}")

    return {
        "found": True,
        "account_id": account_id,
        "account_name": account["name"],
        "tier": account["tier"],
        "standing": standing["standing"],
        "standing_reason": standing["reason"],
        "credit_limit": float(credit["credit_limit"]),
        "open_balance": float(credit["open_balance"]),
        "available_credit": float(available),
        "order_amount": float(amount),
        "fits_available_credit": fits,
        "net_60_allowed": net_60,
        "net_60_reason": net_60_reason,
        "available_terms": terms,
        "partial_shipment_amount": partial,
        "options": options,
        "summary": summary,
    }


# --- invoices and orders ---------------------------------------------------

def get_open_invoices(account_id: str) -> dict:
    """Unpaid invoices for an account, from the ERP."""
    ensure_databases()
    account = _account_row(account_id)
    if account is None:
        return {"found": False, "message": f"No account {account_id}."}

    credit = _credit_snapshot(account_id)
    invoices = credit["invoices"]
    total = sum((money(i["open_balance"]) for i in invoices), Decimal("0.00"))
    past_due = [i for i in invoices if i["days_past_due"] > 0]
    worst = max((i["days_past_due"] for i in invoices), default=0)

    if not invoices:
        summary = f"{account['name']} has no open invoices."
    elif past_due:
        summary = (f"{account['name']} has {len(invoices)} open invoice(s) totalling "
                   f"{usd(total)}; {len(past_due)} past due, the worst by {worst} days.")
    else:
        summary = (f"{account['name']} has {len(invoices)} open invoice(s) totalling "
                   f"{usd(total)}, none past due.")

    return {
        "found": True,
        "account_id": account_id,
        "account_name": account["name"],
        "erp_customer_id": credit["erp_customer_id"],
        "invoices": invoices,
        "count": len(invoices),
        "total_open": float(total),
        "past_due_count": len(past_due),
        "most_past_due_days": worst,
        "summary": summary,
    }


def get_open_orders(account_id: str) -> dict:
    """Orders that are booked but not yet invoiced."""
    ensure_databases()
    account = _account_row(account_id)
    if account is None:
        return {"found": False, "message": f"No account {account_id}."}

    con = _connect(ERP_DB)
    invoiced = {row["order_id"] for row in con.execute("SELECT order_id FROM invoices")}
    con.close()

    con = _connect(CRM_DB)
    rows = con.execute(
        "SELECT * FROM orders WHERE account_id = ? ORDER BY order_date DESC",
        (account_id,),
    ).fetchall()
    con.close()

    orders = [
        {"order_id": row["order_id"], "order_date": row["order_date"],
         "status": row["status"], "total": float(money(row["total"]))}
        for row in rows if row["order_id"] not in invoiced
    ]
    total = sum((money(o["total"]) for o in orders), Decimal("0.00"))

    if orders:
        listed = ", ".join(f"{o['order_id']} ({usd(money(o['total']))})" for o in orders)
        summary = (f"{account['name']} has {len(orders)} booked order(s) not yet "
                   f"invoiced, {usd(total)} in total: {listed}.")
    else:
        summary = f"{account['name']} has no booked orders awaiting invoicing."

    return {
        "found": True,
        "account_id": account_id,
        "account_name": account["name"],
        "orders": orders,
        "count": len(orders),
        "total": float(total),
        "summary": summary,
    }


def get_products() -> dict:
    """The Ridgeline catalogue, with descriptions."""
    ensure_databases()
    con = _connect(CRM_DB)
    rows = con.execute(
        "SELECT * FROM products WHERE sku != ? ORDER BY sku", (m.FREIGHT_SKU,)
    ).fetchall()
    con.close()
    return {
        "products": [
            {"sku": r["sku"], "name": r["name"], "category": r["category"],
             "list_price": float(money(r["list_price"])), "description": r["description"]}
            for r in rows
        ]
    }


# --- discounts -------------------------------------------------------------

def request_discount(account_id: str, sku: str, quantity: int, discount_pct,
                     requested_via: str = "rep",
                     max_auto_approve_pct=None) -> dict:
    """Submit an extra discount on top of the contract price, and route it.

    The business rules (these belong to Salesforce's approval process in real life):
      - up to 10%: auto-approved
      - over 10% and up to 20%: sales manager approval
      - over 20%: refused
      - credit hold: no extra discounts at all

    `max_auto_approve_pct` is the *caller's* own, lower ceiling. The MCP layer
    passes it so the AI can auto-approve less than a human rep can. Anything the
    rules would have auto-approved that exceeds the caller's ceiling goes to the
    account's sales rep for a one-click OK instead.
    """
    ensure_databases()
    account = _account_row(account_id)
    if account is None:
        return {"found": False, "message": f"No account {account_id}."}

    pricing = get_contract_pricing(account_id, sku, quantity)
    if not pricing.get("found"):
        return pricing

    pct = Decimal(str(discount_pct))
    quantity = int(quantity)
    contract_unit = money(pricing["contract_unit_price"])
    discounted_unit = apply_pct(contract_unit, pct)
    total = (discounted_unit * quantity).quantize(CENT, rounding=ROUND_HALF_UP)
    standing = get_account_standing(account_id)

    # --- the approval rules, in order ---
    if standing["standing"] == m.STANDING_CREDIT_HOLD:
        status = "Refused"
        approver = None
        reason = (f"Account is on credit hold — {standing['reason']} "
                  f"No extra discounts; prepay only.")
    elif pct > m.MANAGER_APPROVE_CEILING_PCT:
        status = "Refused"
        approver = None
        reason = (f"{pct_str(pct)}% is over the {m.MANAGER_APPROVE_CEILING_PCT}% "
                  f"ceiling — refused.")
    elif pct > m.SERVICE_AUTO_APPROVE_PCT:
        status = "Pending manager approval"
        approver = m.SALES_MANAGER
        reason = (f"Over {m.SERVICE_AUTO_APPROVE_PCT}% — needs sales manager "
                  f"approval ({m.SALES_MANAGER}).")
    elif (requested_via == "ai" and max_auto_approve_pct is not None
          and pct > Decimal(str(max_auto_approve_pct))):
        # The caller's own ceiling is lower than the rule's. A rep could approve
        # this; the AI cannot, so it goes to the rep for a one-click OK.
        status = "Pending sales rep OK"
        approver = account["owner"]
        reason = (f"Within the {m.SERVICE_AUTO_APPROVE_PCT}% a sales rep can approve, "
                  f"but over the AI's {pct_str(max_auto_approve_pct)}% "
                  f"auto-approval limit — sent to {account['owner']} for a one-click OK.")
    else:
        status = "Approved"
        approver = None
        reason = (f"{pct_str(pct)}% is within the "
                  f"{m.SERVICE_AUTO_APPROVE_PCT}% auto-approval limit.")

    con = _connect(CRM_DB)
    count = con.execute("SELECT COUNT(*) AS n FROM discount_requests").fetchone()["n"]
    request_id = f"DR-{count + 1:04d}"
    con.execute(
        "INSERT INTO discount_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (request_id, account_id, sku, quantity, float(pct), float(contract_unit),
         float(discounted_unit), float(total), requested_via, status, approver,
         reason, dt.datetime.now().isoformat(timespec="seconds")),
    )
    con.commit()
    con.close()

    summary = (
        f"{request_id}: {quantity} × {pricing['product_name']} for "
        f"{account['name']} at {pct_str(pct)}% off the {usd(contract_unit)} contract "
        f"price = {usd(discounted_unit)} each, {usd(total)} total. Status: {status}."
        + (f" With {approver}." if approver else "")
        + f" {reason}"
    )

    return {
        "found": True,
        "request_id": request_id,
        "account_id": account_id,
        "account_name": account["name"],
        "sku": sku,
        "product_name": pricing["product_name"],
        "quantity": quantity,
        "discount_pct": float(pct),
        "contract_unit_price": float(contract_unit),
        "discounted_unit_price": float(discounted_unit),
        "total": float(total),
        "requested_via": requested_via,
        "status": status,
        "approver": approver,
        "reason": reason,
        "summary": summary,
    }


def get_discount_requests(account_id: str | None = None) -> dict:
    """Discount requests raised so far (the workshop's stand-in for Quotes)."""
    ensure_databases()
    con = _connect(CRM_DB)
    if account_id:
        rows = con.execute(
            "SELECT * FROM discount_requests WHERE account_id = ? ORDER BY request_id",
            (account_id,)).fetchall()
    else:
        rows = con.execute("SELECT * FROM discount_requests ORDER BY request_id").fetchall()
    con.close()
    return {"requests": [dict(r) for r in rows], "count": len(rows)}
