"""Paths, environment and the step definitions shared by the app and the CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RIDGELINE_DATA_DIR") or ROOT)
CRM_DB = DATA_DIR / "crm.db"
ERP_DB = DATA_DIR / "erp.db"
TOOLS_FILE = ROOT / "ridgeline_tools.py"
CHECKPOINTS = ROOT / "checkpoints"
STATE_FILE = ROOT / ".workshop_state.json"

load_dotenv(ROOT / ".env")

DEFAULT_MODEL = "claude-sonnet-5-5"


def model() -> str:
    return os.environ.get("RIDGELINE_MODEL", "").strip() or DEFAULT_MODEL


def effort() -> str:
    return os.environ.get("RIDGELINE_EFFORT", "").strip() or "low"


def port() -> int:
    return int(os.environ.get("RIDGELINE_PORT", "8765"))


def api_key() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return key or None


MISSING_KEY_MESSAGE = f"""
No Anthropic API key found.

The chat page talks to Claude through the Anthropic API, so it needs a key.

  1. Copy the example file:   cp .env.example .env
  2. Open .env and put your key after ANTHROPIC_API_KEY=
     (get one at console.anthropic.com — this is not a Claude Code login)

The key stays in {ROOT / ".env"}, which is gitignored and never committed.
"""

# --- the five steps --------------------------------------------------------
# Each step says which checkpoint file to load, whether the chat starts with
# tools switched on, and what the step is about.

STEPS: dict[str, dict] = {
    "1": {
        "checkpoint": "step2",
        "tools_default": False,
        "title": "No tools — Claude can't answer",
        "about": "Ask the hero question with the tools switched off. Claude has no "
                 "access to Ridgeline's data, so it cannot answer at all — it asks "
                 "for the price sheet and the approval rules instead, and hands the "
                 "work back to you. That is the problem the rest of the walkthrough "
                 "solves.",
    },
    "2": {
        "checkpoint": "step2",
        "tools_default": True,
        "title": "Connect the Ridgeline MCP server",
        "about": "Switch the tools on and ask again. Claude now looks the account up "
                 "in Ridgeline's own systems instead of asking you for the data.",
    },
    "3": {
        "checkpoint": "step3",
        "tools_default": True,
        "title": "Fix a vague tool description",
        "about": "check_contract_pricing is described as a legacy batch job and takes "
                 "arguments called a, b, c and d. Claude skips it and prices the "
                 "order off list instead — confidently, and wrong. Paste "
                 "snippets/step3_check_contract_pricing.py over it and ask again.",
    },
    "4": {
        "checkpoint": "step4",
        "tools_default": True,
        "title": "Add a new tool from a template",
        "about": "Paste snippets/step4_get_open_invoices.py into ridgeline_tools.py. "
                 "A tool is a name, a description for a person, and one call into the "
                 "service that owns the data.",
    },
    "5": {
        "checkpoint": "step5",
        "tools_default": True,
        "title": "Give the AI its own approval limit",
        "about": "Add MAX_AI_AUTO_APPROVE_PCT = 5 and hand it to the service. A rep "
                 "can still approve 10%; the AI can only approve 5%. Then try to talk "
                 "the AI past it — the limit is enforced in the service, not the prompt.",
    },
    "solution": {
        "checkpoint": "solution",
        "tools_default": True,
        "title": "The finished server",
        "about": "Everything built: seven tools, confirmation before submitting, and "
                 "the AI's own 5% auto-approval limit.",
    },
}

# What `uv run check` expects the MCP server to expose at each checkpoint.
EXPECTED_TOOLS: dict[str, set[str]] = {
    "step2": {"find_account", "list_products", "check_contract_pricing",
              "check_credit_availability", "get_open_orders", "request_discount"},
    "step4": {"find_account", "list_products", "check_contract_pricing",
              "check_credit_availability", "get_open_orders", "request_discount"},
    "step5": {"find_account", "list_products", "check_contract_pricing",
              "check_credit_availability", "get_open_orders", "request_discount",
              "get_open_invoices"},
}
EXPECTED_TOOLS["step3"] = EXPECTED_TOOLS["step2"]
EXPECTED_TOOLS["solution"] = EXPECTED_TOOLS["step5"]


def read_state() -> dict:
    """Which step is loaded, per the last `uv run reset`."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"step": "solution", "checkpoint": "solution", "tools_default": True}


def write_state(step: str) -> dict:
    spec = STEPS[step]
    state = {
        "step": step,
        "checkpoint": spec["checkpoint"],
        "tools_default": spec["tools_default"],
        "title": spec["title"],
    }
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")
    return state


def step_label(state: dict) -> str:
    step = str(state.get("step", "solution"))
    spec = STEPS.get(step, STEPS["solution"])
    if step == "solution":
        return f"Solution — {spec['title']}"
    return f"Step {step} — {spec['title']}"
