"""The same expected answers, but through the real MCP server over stdio.

Run twice: once at the step-5 checkpoint (before the AI's own limit exists) and
once at the solution (after). The difference between those two runs is exactly
what step 5 adds.
"""

import asyncio
import json

import pytest

from workshop import config
from workshop.mcp_supervisor import McpSupervisor

CALLS = [
    ("summit", "find_account", {"name": "Summit Trail Co."}),
    ("summit_15_priced", "check_contract_pricing",
     {"account_id": "ACC-SUMMIT", "sku": "TENT-TL2", "quantity": 200,
      "extra_discount_pct": 15}),
    ("summit_credit", "check_credit_availability",
     {"account_id": "ACC-SUMMIT", "order_amount": 38098.00}),
    ("summit_15", "request_discount",
     {"account_id": "ACC-SUMMIT", "sku": "TENT-TL2", "quantity": 200,
      "discount_pct": 15, "customer_confirmed": True}),
    ("summit_10", "request_discount",
     {"account_id": "ACC-SUMMIT", "sku": "TENT-TL2", "quantity": 200,
      "discount_pct": 10, "customer_confirmed": True}),
    ("summit_25", "request_discount",
     {"account_id": "ACC-SUMMIT", "sku": "TENT-TL2", "quantity": 200,
      "discount_pct": 25, "customer_confirmed": True}),
    ("unconfirmed", "request_discount",
     {"account_id": "ACC-SUMMIT", "sku": "TENT-TL2", "quantity": 200,
      "discount_pct": 10, "customer_confirmed": False}),
    ("blueridge_priced", "check_contract_pricing",
     {"account_id": "ACC-BLUERIDGE", "sku": "PACK-RDG45", "quantity": 100}),
    ("blueridge_credit", "check_credit_availability",
     {"account_id": "ACC-BLUERIDGE", "order_amount": 17005.00}),
    ("cascade_5", "request_discount",
     {"account_id": "ACC-CASCADE", "sku": "TENT-BC4", "quantity": 50,
      "discount_pct": 5, "customer_confirmed": True}),
    ("pinecrest_8", "request_discount",
     {"account_id": "ACC-PINECREST", "sku": "STOVE-EMB", "quantity": 20,
      "discount_pct": 8, "customer_confirmed": True}),
    ("pinecrest_5", "request_discount",
     {"account_id": "ACC-PINECREST", "sku": "STOVE-EMB", "quantity": 20,
      "discount_pct": 5, "customer_confirmed": True}),
    ("northfork_credit", "check_credit_availability",
     {"account_id": "ACC-NORTHFORK", "order_amount": 10000.00}),
    ("northfork_5", "request_discount",
     {"account_id": "ACC-NORTHFORK", "sku": "TENT-TL2", "quantity": 40,
      "discount_pct": 5, "customer_confirmed": True}),
    ("summit_orders", "get_open_orders", {"account_id": "ACC-SUMMIT"}),
    ("summit_invoices", "get_open_invoices", {"account_id": "ACC-SUMMIT"}),
    ("products", "list_products", {}),
]


class Server:
    def __init__(self, checkpoint, names, results):
        self.checkpoint = checkpoint
        self.names = names
        self.results = results

    def __getitem__(self, key):
        return self.results[key]


async def _collect(tools_file):
    supervisor = McpSupervisor(tools_file=tools_file)
    await supervisor.start()
    assert supervisor.error is None, supervisor.error
    names = set(supervisor.tool_names)
    results = {}
    for key, tool, args in CALLS:
        text, is_error = await supervisor.call(tool, args)
        assert not is_error, f"{tool} failed: {text}"
        results[key] = json.loads(text)
    await supervisor.stop()
    return names, results


@pytest.fixture(scope="module", params=["step5", "solution"])
def server(request, data_dir):
    tools_file = config.CHECKPOINTS / request.param / "ridgeline_tools.py"
    names, results = asyncio.run(_collect(tools_file))
    return Server(request.param, names, results)


# --- the tool list ----------------------------------------------------------

def test_the_server_lists_the_expected_tools(server):
    assert server.names == config.EXPECTED_TOOLS[server.checkpoint]


def test_step_four_added_get_open_invoices(server):
    assert "get_open_invoices" in server.names


# --- things that are the same before and after step 5 -----------------------

def test_find_account(server):
    summit = server["summit"]
    assert summit["account_id"] == "ACC-SUMMIT"
    assert summit["tier"] == "Gold"
    assert summit["standing"] == "Good"
    assert summit["available_credit"] == 112000.00


def test_row1_the_hero_question(server):
    priced = server["summit_15_priced"]
    assert priced["contract_unit_price"] == 224.10
    assert priced["discounted_unit_price"] == 190.49
    assert priced["discounted_line_total"] == 38098.00

    credit = server["summit_credit"]
    assert credit["fits_available_credit"] is True
    assert credit["net_60_allowed"] is True

    discount = server["summit_15"]
    assert discount["total"] == 38098.00
    assert discount["status"] == "Pending manager approval"
    assert discount["approver"] == "Laura Bennett"


def test_row3_blue_ridge_exceeds_credit(server):
    assert server["blueridge_priced"]["line_total"] == 17005.00
    credit = server["blueridge_credit"]
    assert credit["fits_available_credit"] is False
    assert credit["net_60_allowed"] is False
    assert credit["partial_shipment_amount"] == 8502.50


def test_row4_cascade_is_refused(server):
    assert server["cascade_5"]["status"] == "Refused"


def test_row5b_five_percent_is_auto_approved(server):
    assert server["pinecrest_5"]["total"] == 1311.00
    assert server["pinecrest_5"]["status"] == "Approved"


def test_row6_northfork_cannot_have_net_60(server):
    credit = server["northfork_credit"]
    assert credit["standing"] == "Watch"
    assert credit["net_60_allowed"] is False


def test_row6b_northfork_five_percent(server):
    assert server["northfork_5"]["total"] == 8988.80
    assert server["northfork_5"]["status"] == "Approved"


def test_row8_twenty_five_percent_is_refused(server):
    assert server["summit_25"]["status"] == "Refused"


def test_row9_open_invoices(server):
    invoices = server["summit_invoices"]
    assert invoices["total_open"] == 38000.00
    assert {i["invoice_number"] for i in invoices["invoices"]} == {"INV-5001", "INV-5002"}
    assert invoices["past_due_count"] == 0


def test_row12_open_orders(server):
    orders = server["summit_orders"]
    assert orders["count"] == 1
    assert orders["orders"][0]["order_id"] == "ORD-9001"
    assert orders["total"] == 40000.00


def test_row11_nothing_is_submitted_without_confirmation(server):
    """The MCP layer's own guardrail, prebuilt — no service call happens at all."""
    assert server["unconfirmed"]["submitted"] is False
    assert "confirm" in server["unconfirmed"]["reason"].lower()


def test_products_carry_the_descriptions_that_answer_product_questions(server):
    products = {p["sku"]: p for p in server["products"]["products"]}
    assert "four-person" in products["TENT-BC4"]["description"].lower()
    assert products["TENT-TL2"]["list_price"] == 249.00


# --- the difference step 5 makes --------------------------------------------

def test_row2_ten_percent_changes_at_step_5(server):
    result = server["summit_10"]
    assert result["total"] == 40338.00
    if server.checkpoint == "step5":
        assert result["status"] == "Approved"
        assert result["approver"] is None
    else:
        assert result["status"] == "Pending sales rep OK"
        assert result["approver"] == "Dana Ruiz"


def test_row5_eight_percent_changes_at_step_5(server):
    result = server["pinecrest_8"]
    assert result["total"] == 1269.60
    if server.checkpoint == "step5":
        assert result["status"] == "Approved"
    else:
        assert result["status"] == "Pending sales rep OK"
        assert result["approver"] == "Tom Kowalski"


def test_fifteen_percent_is_unaffected_by_the_ai_limit(server):
    """The manager rule belongs to the service; step 5 does not touch it."""
    assert server["summit_15"]["status"] == "Pending manager approval"
