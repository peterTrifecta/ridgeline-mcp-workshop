"""Ridgeline Outfitters — the MCP layer.

This is the thin, AI-facing front door. Every tool below is a few lines: take
the arguments, call the Pricing & Credit service, hand back what it said. The
business rules are not here. They are in pricing_service.py, which stands in for
the service that owns them.

Two kinds of things DO belong here, because they are rules about the AI rather
than rules about the business:

  1. Confirmation before submitting a discount request.
  2. The AI's own auto-approval limit, which is lower than a sales rep's.

This is the only file edited during the walkthrough.
"""

from mcp.server.mcpserver import MCPServer

import pricing_service

mcp = MCPServer("ridgeline")


# --------------------------------------------------------------------------
# ---- STEP 5a: the AI's own auto-approval limit goes here ----
# --------------------------------------------------------------------------


@mcp.tool()
def find_account(name: str) -> dict:
    """Look up a Ridgeline customer account by name.

    Use this first whenever someone names a customer. It returns the account id
    you need for the other tools, plus their pricing tier, their sales rep,
    their account standing (Good, Watch or Credit hold), their payment terms,
    and how much credit they have available right now.

    Args:
        name: The customer's name, e.g. "Summit Trail Co." or just "Summit Trail".
    """
    return pricing_service.find_account(name)


@mcp.tool()
def list_products() -> dict:
    """List everything Ridgeline sells, with descriptions and list prices.

    Use this to find the SKU for a product someone describes in words, or to
    answer questions about which product suits a customer's needs.
    """
    return pricing_service.get_products()


@mcp.tool()
def check_contract_pricing(account_id: str, sku: str, quantity: int,
                           extra_discount_pct: float = 0) -> dict:
    """Get a customer's contract price for a product, and what the line costs.

    Contract price depends on the account's tier, so it is not the list price.
    This also tells you how big an extra discount can be before it needs someone
    to approve it.

    Always use this to price an order. Do not work the numbers out yourself.

    Args:
        account_id: The account id from find_account, e.g. "ACC-SUMMIT".
        sku: The product code, e.g. "TENT-TL2". Use list_products to find it.
        quantity: How many units the customer wants.
        extra_discount_pct: An extra discount the customer is asking for, on top
            of their contract price, e.g. 15 for 15%. This only prices it up;
            nothing is submitted and nothing is approved.
    """
    return pricing_service.get_contract_pricing(account_id, sku, quantity,
                                                extra_discount_pct)


@mcp.tool()
def check_credit_availability(account_id: str, order_amount: float) -> dict:
    """Check whether an order fits the customer's credit, and which terms apply.

    Credit available is their credit limit minus what they already owe on open
    invoices. Use this before promising any payment terms — net 60 in particular
    is only available to some accounts.

    Args:
        account_id: The account id from find_account, e.g. "ACC-SUMMIT".
        order_amount: The total value of the proposed order, in dollars.
    """
    return pricing_service.check_credit(account_id, order_amount)


@mcp.tool()
def get_open_orders(account_id: str) -> dict:
    """List orders the customer has placed that have not been invoiced yet.

    Args:
        account_id: The account id from find_account, e.g. "ACC-SUMMIT".
    """
    return pricing_service.get_open_orders(account_id)


# --------------------------------------------------------------------------
# ---- STEP 4: a new tool goes here ----
# Open snippets/step4_get_open_invoices.py, copy the whole tool, paste it below.
# --------------------------------------------------------------------------


@mcp.tool()
def request_discount(account_id: str, sku: str, quantity: int,
                     discount_pct: float, customer_confirmed: bool) -> dict:
    """Submit a request for an extra discount on top of the contract price.

    This writes a real request that a person may have to act on, so never call
    it until the user has seen the numbers and told you to go ahead.

    The service decides what happens to the request — approved, sent to the
    sales rep, sent to the sales manager, or refused. You do not decide that,
    and you cannot change it.

    Args:
        account_id: The account id from find_account, e.g. "ACC-SUMMIT".
        sku: The product code, e.g. "TENT-TL2".
        quantity: How many units the customer wants.
        discount_pct: The extra discount off the contract price, e.g. 15 for 15%.
        customer_confirmed: True only once the user has explicitly confirmed
            that you should submit this request.
    """
    # AI guardrail: confirm first. Nothing is submitted without it.
    if not customer_confirmed:
        return {
            "submitted": False,
            "reason": "Not submitted. Show the customer the price and the "
                      "discount, and ask them to confirm before submitting.",
        }

    return pricing_service.request_discount(
        account_id,
        sku,
        quantity,
        discount_pct,
        requested_via="ai",
        # ---- STEP 5b: hand the AI's limit to the service here ----
    )


if __name__ == "__main__":
    mcp.run()
