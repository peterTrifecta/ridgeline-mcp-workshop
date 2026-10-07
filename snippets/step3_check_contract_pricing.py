# STEP 3 — replace the whole check_contract_pricing tool in ridgeline_tools.py
# with everything below the line.
#
# Same code underneath. What changes is what the AI can see: a description that
# says when to use the tool, and argument names that mean something.
# ---------------------------------------------------------------------------


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
