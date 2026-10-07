"""Derive checkpoints/step{2..5} from checkpoints/solution.

To change the finished server, edit checkpoints/solution/ridgeline_tools.py,
re-run this, then `uv run reset solution` to load it live:

    uv run python scripts/rebuild_checkpoints.py

The source is the checkpoint, not the ridgeline_tools.py at the repo root:
`uv run reset` overwrites that file with whichever step is loaded, so deriving
from it would break `uv run check` everywhere except at the solution.

tests/test_checkpoints.py checks that pasting each snippet into one checkpoint
reproduces the next one exactly, which is what makes `uv run reset N+1` a safe
recovery when a live edit goes wrong.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
solution = (ROOT / "checkpoints" / "solution" / "ridgeline_tools.py").read_text()

SEPARATOR = "# " + "-" * 75 + "\n"


def swap(text, old, new, label):
    assert old in text, f"anchor not found: {label}"
    return text.replace(old, new, 1)


def snippet_body(name):
    """A snippet file minus its explanatory header — what gets pasted on stage.

    Reading the snippets here is what keeps them honest: if one drifts from the
    solution, the anchor stops matching and this script fails loudly.
    """
    text = (ROOT / "snippets" / f"{name}.py").read_text()
    return text.split(SEPARATOR, 1)[1].lstrip("\n")


# ---------------------------------------------------------------- step 5
LIMIT_BLOCK = snippet_body("step5a_ai_auto_approve_limit")
LIMIT_BLOCK_STEP5 = """# --------------------------------------------------------------------------
# ---- STEP 5a: the AI's own auto-approval limit goes here ----
# --------------------------------------------------------------------------
"""
PASS_LIMIT = snippet_body("step5b_pass_the_limit")
PASS_LIMIT_STEP5 = (
    "        # ---- STEP 5b: hand the AI's limit to the service here ----\n"
)
step5 = swap(solution, LIMIT_BLOCK, LIMIT_BLOCK_STEP5, "limit block")
step5 = swap(step5, PASS_LIMIT, PASS_LIMIT_STEP5, "pass limit")

# ---------------------------------------------------------------- step 4
INVOICES_TOOL = '''@mcp.tool()
def get_open_invoices(account_id: str) -> dict:
    """List the customer's unpaid invoices, and flag any that are past due.

    This comes from the ERP, which is the system of record for what customers
    owe. Use it when someone asks about an account's balance, or why an account
    is on Watch or Credit hold.

    Args:
        account_id: The account id from find_account, e.g. "ACC-SUMMIT".
    """
    return pricing_service.get_open_invoices(account_id)


'''
INVOICES_PLACEHOLDER = """# --------------------------------------------------------------------------
# ---- STEP 4: a new tool goes here ----
# Open snippets/step4_get_open_invoices.py, copy the whole tool, paste it below.
# --------------------------------------------------------------------------


"""
step4 = swap(step5, INVOICES_TOOL, INVOICES_PLACEHOLDER, "invoices tool")

# ---------------------------------------------------------------- step 3
GOOD_PRICING = snippet_body("step3_check_contract_pricing")
VAGUE_PRICING = (
    "# ---- STEP 3: check_contract_pricing ----\n"
    "@mcp.tool()\n"
    "def check_contract_pricing(a: str, b: str, c: int, d: float = 0) -> dict:\n"
    '    """Legacy batch job. Used by the nightly reconciliation run only."""\n'
    "    return pricing_service.get_contract_pricing(a, b, c, d)\n"
)
step3 = swap(step4, GOOD_PRICING, VAGUE_PRICING, "good pricing")
step2 = step3

# "solution" is the source, so writing it back is a no-op. It is listed so
# derive() covers every checkpoint the tests parametrize over.
CHECKPOINTS = {"step2": step2, "step3": step3, "step4": step4,
               "step5": step5, "solution": solution}


def derive() -> dict[str, str]:
    """What each checkpoint file should contain, derived from the solution."""
    return dict(CHECKPOINTS)


def main() -> None:
    for name, text in CHECKPOINTS.items():
        out = ROOT / "checkpoints" / name / "ridgeline_tools.py"
        out.write_text(text)
        print(f"wrote checkpoints/{name}/ridgeline_tools.py  ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
