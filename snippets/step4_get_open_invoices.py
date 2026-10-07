# STEP 4 — copy everything below the line into ridgeline_tools.py, where the
# "STEP 4: a new tool goes here" comment is. Nothing else changes.
#
# It is the same shape as every other tool in that file: a name, a description
# written for a person, the arguments, and one call into the service.
# ---------------------------------------------------------------------------


@mcp.tool()
def get_open_invoices(account_id: str) -> dict:
    """List the customer's unpaid invoices, and flag any that are past due.

    This comes from the ERP, which is the system of record for what customers
    owe. Use it when someone asks about an account's balance, or why an account
    is on Watch or Credit hold.

    Args:
        account_id: The account id from find_account, e.g. "ACC-SUMMIT".
    """
    return pricing_service.get_open_invoices(account_id)
