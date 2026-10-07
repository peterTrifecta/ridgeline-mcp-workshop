"""The checkpoints have to stay consistent, or `uv run reset N+1` stops being a
safe recovery when a live edit goes wrong.

Two things are checked: that each checkpoint matches what the solution implies,
and that pasting a snippet into one checkpoint reproduces the next one exactly —
which is the edit made on stage.
"""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

from workshop import config

SEPARATOR = "# " + "-" * 75 + "\n"


def load_rebuild_module():
    path = config.ROOT / "scripts" / "rebuild_checkpoints.py"
    spec = importlib.util.spec_from_file_location("rebuild_checkpoints", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["rebuild_checkpoints"] = module
    spec.loader.exec_module(module)
    return module


def checkpoint_text(name):
    return (config.CHECKPOINTS / name / "ridgeline_tools.py").read_text()


def snippet_body(name):
    """A snippet file minus its explanatory header — what actually gets pasted."""
    text = (config.ROOT / "snippets" / f"{name}.py").read_text()
    return text.split(SEPARATOR, 1)[1].lstrip("\n")


def tool_names(source):
    """The @mcp.tool() functions a file defines."""
    names = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and any(
                isinstance(d, ast.Call) and getattr(d.func, "attr", None) == "tool"
                for d in node.decorator_list):
            names.add(node.name)
    return names


@pytest.mark.parametrize("name", ["step2", "step3", "step4", "step5", "solution"])
def test_checkpoint_defines_the_expected_tools(name):
    assert tool_names(checkpoint_text(name)) == config.EXPECTED_TOOLS[name]


# "solution" is the source rebuild_checkpoints.py derives from, so checking it
# against itself would prove nothing. The assertions further down cover it.
@pytest.mark.parametrize("name", ["step2", "step3", "step4", "step5"])
def test_checkpoint_matches_the_solution_it_was_derived_from(name):
    """If checkpoints/solution was edited, run scripts/rebuild_checkpoints.py."""
    expected = load_rebuild_module().derive()[name]
    assert checkpoint_text(name) == expected, (
        f"checkpoints/{name} has drifted from the solution — "
        f"run: uv run python scripts/rebuild_checkpoints.py")


def test_step_1_and_step_2_use_the_same_file():
    """Step 1 is step 2 with the tools switched off. Nothing else differs."""
    assert config.STEPS["1"]["checkpoint"] == config.STEPS["2"]["checkpoint"]
    assert config.STEPS["1"]["tools_default"] is False
    assert config.STEPS["2"]["tools_default"] is True


def test_step_2_and_step_3_start_from_the_same_file():
    """Step 2 has no edit: connecting the server is the whole step."""
    assert checkpoint_text("step2") == checkpoint_text("step3")


def test_step_3_paste_reproduces_step_4():
    """The stage edit: swap the vague tool for the one in the snippet."""
    vague = (
        "# ---- STEP 3: check_contract_pricing ----\n"
        "@mcp.tool()\n"
        "def check_contract_pricing(a: str, b: str, c: int, d: float = 0) -> dict:\n"
        '    """Legacy batch job. Used by the nightly reconciliation run only."""\n'
        "    return pricing_service.get_contract_pricing(a, b, c, d)\n"
    )
    step3 = checkpoint_text("step3")
    assert vague in step3
    assert step3.replace(vague, snippet_body("step3_check_contract_pricing"), 1) \
        == checkpoint_text("step4")


def test_step_4_paste_reproduces_step_5():
    """The stage edit: paste the new tool over the placeholder comment."""
    step4 = checkpoint_text("step4")
    placeholder = (
        "# " + "-" * 74 + "\n"
        "# ---- STEP 4: a new tool goes here ----\n"
        "# Open snippets/step4_get_open_invoices.py, copy the whole tool, "
        "paste it below.\n"
        "# " + "-" * 74 + "\n\n\n"
    )
    assert placeholder in step4
    pasted = step4.replace(placeholder, snippet_body("step4_get_open_invoices") + "\n\n", 1)
    assert pasted == checkpoint_text("step5")


def test_step_5_pastes_reproduce_the_solution():
    """The two stage edits: the AI's own limit, then handing it to the service.

    5b goes inside the call to pricing_service, so its snippet carries the
    leading indentation. If an editor helpfully re-indents it on paste, this is
    the test that would have caught it.
    """
    step5 = checkpoint_text("step5")
    placeholder_5a = (
        "# " + "-" * 74 + "\n"
        "# ---- STEP 5a: the AI's own auto-approval limit goes here ----\n"
        "# " + "-" * 74 + "\n"
    )
    placeholder_5b = (
        "        # ---- STEP 5b: hand the AI's limit to the service here ----\n"
    )
    assert placeholder_5a in step5
    assert placeholder_5b in step5

    pasted = step5.replace(
        placeholder_5a, snippet_body("step5a_ai_auto_approve_limit"), 1)
    pasted = pasted.replace(
        placeholder_5b, snippet_body("step5b_pass_the_limit"), 1)
    assert pasted == checkpoint_text("solution")


def test_every_live_edit_has_a_snippet_to_paste():
    """Nothing is retyped on stage. Every edit is copy, paste, save."""
    for name in ("step3_check_contract_pricing", "step4_get_open_invoices",
                 "step5a_ai_auto_approve_limit", "step5b_pass_the_limit"):
        path = config.ROOT / "snippets" / f"{name}.py"
        assert path.exists(), f"snippets/{name}.py is missing"
        assert SEPARATOR in path.read_text(), (
            f"snippets/{name}.py has no dashed line to copy below")


def test_the_step_3_tool_really_is_hard_to_use():
    """The point of step 3 only lands if the description is genuinely useless."""
    step3 = checkpoint_text("step3")
    assert "Legacy batch job" in step3
    assert "nightly reconciliation" in step3
    assert "def check_contract_pricing(a: str, b: str, c: int" in step3


def test_only_the_solution_carries_the_ai_limit():
    for name in ("step2", "step3", "step4", "step5"):
        assert "MAX_AI_AUTO_APPROVE_PCT = 5" not in checkpoint_text(name)
    assert "MAX_AI_AUTO_APPROVE_PCT = 5" in checkpoint_text("solution")
    assert "max_auto_approve_pct=MAX_AI_AUTO_APPROVE_PCT" in checkpoint_text("solution")


def test_every_checkpoint_has_the_confirmation_guardrail():
    """Confirmation is prebuilt — it is never one of the live edits."""
    for name in ("step2", "step3", "step4", "step5", "solution"):
        assert "customer_confirmed" in checkpoint_text(name)


def test_business_rules_stay_out_of_the_mcp_layer():
    """The whole argument of the session: these tools call rules, they don't hold them.

    Every tool is a docstring and a call into the service. The one exception is
    request_discount, which adds the AI-specific confirmation check.
    """
    for name in ("step2", "step3", "step4", "step5", "solution"):
        source = checkpoint_text(name)
        assert "Laura Bennett" not in source, f"an approver is named in checkpoints/{name}"

        for node in ast.parse(source).body:
            if not (isinstance(node, ast.FunctionDef) and any(
                    isinstance(d, ast.Call) and getattr(d.func, "attr", None) == "tool"
                    for d in node.decorator_list)):
                continue
            body = [n for n in node.body if not (isinstance(n, ast.Expr)
                                                 and isinstance(n.value, ast.Constant))]
            if node.name == "request_discount":
                # the confirmation guard, then the call
                assert len(body) == 2, f"{name}.{node.name} does more than it should"
                assert isinstance(body[0], ast.If)
            else:
                assert len(body) == 1 and isinstance(body[0], ast.Return), (
                    f"checkpoints/{name}: {node.name} should be a single call into "
                    f"pricing_service, not {len(body)} statements")
            call = body[-1].value
            assert isinstance(call, ast.Call), f"{name}.{node.name} must call the service"
            assert getattr(call.func.value, "id", None) == "pricing_service", (
                f"checkpoints/{name}: {node.name} must call pricing_service")
