"""Section 5 of the data model doc — the expected answers, against the service.

Row numbers below are that table's row numbers. Rows 10 and 11 depend on what
the model does, so they live in `uv run smoke` instead.
"""

import pytest


# --- standing and contract pricing -----------------------------------------

@pytest.mark.parametrize("account_id,standing", [
    ("ACC-SUMMIT", "Good"),
    ("ACC-BLUERIDGE", "Good"),
    ("ACC-CASCADE", "Credit hold"),
    ("ACC-PINECREST", "Good"),
    ("ACC-NORTHFORK", "Watch"),
])
def test_account_standing(service, account_id, standing):
    assert service.get_account_standing(account_id)["standing"] == standing


@pytest.mark.parametrize("account_id,sku,unit", [
    ("ACC-SUMMIT", "TENT-TL2", 224.10),      # Gold: 10% off $249
    ("ACC-BLUERIDGE", "PACK-RDG45", 170.05),  # Silver: 5% off $179
    ("ACC-PINECREST", "STOVE-EMB", 69.00),    # Bronze: list
    ("ACC-NORTHFORK", "TENT-TL2", 236.55),    # Silver: 5% off $249
])
def test_contract_unit_price(service, account_id, sku, unit):
    assert service.get_contract_pricing(account_id, sku, 1)["contract_unit_price"] == unit


def test_rounding_is_half_up(service):
    """$224.10 less 15% is $190.485. It has to round up, not down."""
    priced = service.get_contract_pricing("ACC-SUMMIT", "TENT-TL2", 200, 15)
    assert priced["discounted_unit_price"] == 190.49
    assert priced["discounted_line_total"] == 38098.00


# --- row 1: Summit Trail, 15% off 200 TrailLite, net 60 ---------------------

def test_row1_pricing_and_credit(service):
    priced = service.get_contract_pricing("ACC-SUMMIT", "TENT-TL2", 200, 15)
    assert priced["contract_unit_price"] == 224.10
    assert priced["discounted_line_total"] == 38098.00

    credit = service.check_credit("ACC-SUMMIT", 38098.00)
    assert credit["available_credit"] == 112000.00
    assert credit["fits_available_credit"] is True
    assert credit["net_60_allowed"] is True


def test_row1_discount_needs_the_manager(service):
    result = service.request_discount("ACC-SUMMIT", "TENT-TL2", 200, 15,
                                      requested_via="ai", max_auto_approve_pct=5)
    assert result["discounted_unit_price"] == 190.49
    assert result["total"] == 38098.00
    assert result["status"] == "Pending manager approval"
    assert result["approver"] == "Laura Bennett"


# --- row 2: the same order at 10%, before and after step 5 ------------------

def test_row2_before_step5_is_auto_approved(service):
    result = service.request_discount("ACC-SUMMIT", "TENT-TL2", 200, 10,
                                      requested_via="ai")
    assert result["discounted_unit_price"] == 201.69
    assert result["total"] == 40338.00
    assert result["status"] == "Approved"


def test_row2_after_step5_goes_to_the_rep(service):
    result = service.request_discount("ACC-SUMMIT", "TENT-TL2", 200, 10,
                                      requested_via="ai", max_auto_approve_pct=5)
    assert result["total"] == 40338.00
    assert result["status"] == "Pending sales rep OK"
    assert result["approver"] == "Dana Ruiz"


def test_a_rep_asking_for_10_percent_is_unaffected_by_the_ai_limit(service):
    result = service.request_discount("ACC-SUMMIT", "TENT-TL2", 200, 10,
                                      requested_via="rep", max_auto_approve_pct=5)
    assert result["status"] == "Approved"


# --- row 3: Blue Ridge, 100 packs, exceeds credit ---------------------------

def test_row3_exceeds_credit_and_no_net_60(service):
    priced = service.get_contract_pricing("ACC-BLUERIDGE", "PACK-RDG45", 100)
    assert priced["line_total"] == 17005.00

    credit = service.check_credit("ACC-BLUERIDGE", 17005.00)
    assert credit["available_credit"] == 9000.00
    assert credit["fits_available_credit"] is False
    assert credit["net_60_allowed"] is False
    assert "Silver" in credit["net_60_reason"]
    assert credit["partial_shipment_amount"] == 8502.50


# --- row 4: Cascade is on credit hold ---------------------------------------

def test_row4_credit_hold_refuses_any_discount(service):
    result = service.request_discount("ACC-CASCADE", "TENT-BC4", 50, 5,
                                      requested_via="ai", max_auto_approve_pct=5)
    assert result["status"] == "Refused"
    assert "credit hold" in result["reason"].lower()
    assert "INV-5201" in result["reason"]


def test_row4_credit_hold_is_prepay_only(service):
    credit = service.check_credit("ACC-CASCADE", 1000.00)
    assert credit["net_60_allowed"] is False
    assert credit["available_terms"] == ["Prepay"]


# --- rows 5 and 5b: Pinecrest -----------------------------------------------

def test_row5_eight_percent_before_and_after_step5(service):
    before = service.request_discount("ACC-PINECREST", "STOVE-EMB", 20, 8,
                                      requested_via="ai")
    after = service.request_discount("ACC-PINECREST", "STOVE-EMB", 20, 8,
                                     requested_via="ai", max_auto_approve_pct=5)
    for result in (before, after):
        assert result["discounted_unit_price"] == 63.48
        assert result["total"] == 1269.60
    assert before["status"] == "Approved"
    assert after["status"] == "Pending sales rep OK"
    assert after["approver"] == "Tom Kowalski"


def test_row5b_five_percent_is_auto_approved_either_way(service):
    before = service.request_discount("ACC-PINECREST", "STOVE-EMB", 20, 5,
                                      requested_via="ai")
    after = service.request_discount("ACC-PINECREST", "STOVE-EMB", 20, 5,
                                     requested_via="ai", max_auto_approve_pct=5)
    for result in (before, after):
        assert result["discounted_unit_price"] == 65.55
        assert result["total"] == 1311.00
        assert result["status"] == "Approved"


def test_pinecrest_is_net_30(service):
    credit = service.check_credit("ACC-PINECREST", 1311.00)
    assert credit["available_terms"] == ["Net 30"]
    assert credit["net_60_allowed"] is False


# --- rows 6 and 6b: Northfork is on Watch -----------------------------------

def test_row6_no_net_60_on_watch(service):
    credit = service.check_credit("ACC-NORTHFORK", 10000.00)
    assert credit["standing"] == "Watch"
    assert credit["net_60_allowed"] is False
    assert credit["available_terms"] == ["Net 30"]


def test_row6b_watch_does_not_block_a_discount(service):
    result = service.request_discount("ACC-NORTHFORK", "TENT-TL2", 40, 5,
                                      requested_via="ai", max_auto_approve_pct=5)
    assert result["contract_unit_price"] == 236.55
    assert result["discounted_unit_price"] == 224.72
    assert result["total"] == 8988.80
    assert result["status"] == "Approved"


# --- rows 7 and 7b: the guardrails do not move ------------------------------

def test_row7_fifteen_percent_always_needs_the_manager(service):
    """No argument the AI can pass changes this. The service decides."""
    for max_pct in (None, 5, 10, 20, 100):
        result = service.request_discount("ACC-SUMMIT", "TENT-TL2", 200, 15,
                                          requested_via="ai",
                                          max_auto_approve_pct=max_pct)
        assert result["status"] == "Pending manager approval"


def test_row7b_the_ai_limit_cannot_be_talked_around(service):
    result = service.request_discount("ACC-PINECREST", "STOVE-EMB", 20, 8,
                                      requested_via="ai", max_auto_approve_pct=5)
    assert result["status"] == "Pending sales rep OK"


# --- row 8: over 20% is refused ---------------------------------------------

def test_row8_over_twenty_percent_is_refused(service):
    result = service.request_discount("ACC-SUMMIT", "TENT-TL2", 200, 25,
                                      requested_via="ai", max_auto_approve_pct=5)
    assert result["status"] == "Refused"
    assert "20%" in result["reason"]


def test_twenty_percent_exactly_still_goes_to_the_manager(service):
    result = service.request_discount("ACC-SUMMIT", "TENT-TL2", 200, 20,
                                      requested_via="ai", max_auto_approve_pct=5)
    assert result["status"] == "Pending manager approval"


# --- row 9: open invoices ----------------------------------------------------

def test_row9_open_invoices_for_summit(service):
    result = service.get_open_invoices("ACC-SUMMIT")
    assert result["count"] == 2
    assert result["total_open"] == 38000.00
    assert result["past_due_count"] == 0
    numbers = {i["invoice_number"]: i["open_balance"] for i in result["invoices"]}
    assert numbers == {"INV-5001": 14200.00, "INV-5002": 23800.00}


def test_open_invoices_ignores_paid_ones(service):
    """Every account has paid history. The credit check counts open invoices only."""
    result = service.get_open_invoices("ACC-PINECREST")
    assert result["count"] == 1
    assert result["total_open"] == 2000.00


# --- row 12: open orders -----------------------------------------------------

def test_row12_open_orders_for_summit(service):
    result = service.get_open_orders("ACC-SUMMIT")
    assert result["count"] == 1
    assert result["orders"][0]["order_id"] == "ORD-9001"
    assert result["total"] == 40000.00


def test_credit_check_ignores_pending_orders(service):
    """The workshop's rule, as written: open invoices only."""
    credit = service.check_credit("ACC-SUMMIT", 1000.00)
    assert credit["open_balance"] == 38000.00     # not 78,000
    assert credit["available_credit"] == 112000.00


# --- find_account ------------------------------------------------------------

@pytest.mark.parametrize("query", ["Summit Trail Co.", "Summit Trail", "summit",
                                   "ACC-SUMMIT"])
def test_find_account_is_forgiving_about_names(service, query):
    account = service.find_account(query)
    assert account["found"] is True
    assert account["account_id"] == "ACC-SUMMIT"
    assert account["tier"] == "Gold"
    assert account["sales_rep"] == "Dana Ruiz"


def test_find_account_reports_a_miss(service):
    assert service.find_account("Nonexistent Outfitters")["found"] is False


def test_find_account_reports_an_ambiguous_name(service):
    """'ridge' matches two accounts. Better to ask than to guess."""
    result = service.find_account("ridge")
    assert result["found"] is False
    assert set(result["candidates"]) == {"Blue Ridge Guides", "Laurel Ridge Supply"}
