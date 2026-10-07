"""The five commands: start, check, reset, test, smoke."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from workshop import config

ROOT = config.ROOT

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
BOLD = "\033[1m"
OFF = "\033[0m"


def _tty(text: str, code: str) -> str:
    return f"{code}{text}{OFF}" if sys.stdout.isatty() else text


def app_is_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        return probe.connect_ex(("127.0.0.1", config.port())) == 0


# --------------------------------------------------------------------------
# start
# --------------------------------------------------------------------------

def start() -> None:
    if not config.api_key():
        print(config.MISSING_KEY_MESSAGE)
        sys.exit(1)

    from data import generate
    if generate.ensure_fresh(config.CRM_DB, config.ERP_DB):
        print("Rebuilt crm.db and erp.db for today.")

    state = config.read_state()
    port = config.port()
    url = f"http://127.0.0.1:{port}"

    print()
    print(_tty(config.step_label(state), BOLD))
    print(f"  {config.STEPS[str(state.get('step', 'solution'))]['about']}")
    print()
    print(f"Chat page: {_tty(url, BOLD)}   (model: {config.model()})")
    print(_tty("Ctrl-C to stop.", DIM))
    print()

    threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    import uvicorn
    uvicorn.run("workshop.app:app", host="127.0.0.1", port=port, log_level="warning")


# --------------------------------------------------------------------------
# reset
# --------------------------------------------------------------------------

def reset() -> None:
    args = sys.argv[1:]
    step = (args[0] if args else "1").strip().lower()

    if step not in config.STEPS:
        valid = ", ".join(k for k in config.STEPS)
        print(f"Unknown step {step!r}. Use one of: {valid}")
        sys.exit(1)

    spec = config.STEPS[step]
    source = config.CHECKPOINTS / spec["checkpoint"] / "ridgeline_tools.py"
    if not source.exists():
        print(f"Missing checkpoint file: {source}")
        sys.exit(1)

    shutil.copyfile(source, config.TOOLS_FILE)

    from data import generate
    as_of = generate.build(config.CRM_DB, config.ERP_DB)
    config.write_state(step)

    label = config.step_label({"step": step})
    print()
    print(_tty(label, BOLD))
    print(f"  {spec['about']}")
    print()
    print(f"  copied   checkpoints/{spec['checkpoint']}/ridgeline_tools.py "
          f"-> ridgeline_tools.py")
    print(f"  rebuilt  crm.db and erp.db  (AS_OF {as_of.isoformat()}, "
          f"discount requests cleared)")
    print(f"  tools    start {'OFF' if not spec['tools_default'] else 'ON'} "
          f"in the chat page")
    print()

    if app_is_running():
        print(_tty("  The chat app is running — click New conversation to pick this up.",
                   BOLD))
        print()


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------

class Checks:
    def __init__(self):
        self.failed = 0

    def report(self, ok: bool, label: str, detail: str = "") -> bool:
        tag = _tty("PASS", GREEN) if ok else _tty("FAIL", RED)
        print(f"  {tag}  {label}" + (f"  {_tty(detail, DIM)}" if detail else ""))
        if not ok:
            self.failed += 1
        return ok


def check() -> None:
    checks = Checks()
    state = config.read_state()
    print()
    print(_tty(f"Checking the workshop — {config.step_label(state)}", BOLD))
    print()

    # 1. uv and Python
    uv = shutil.which("uv")
    checks.report(bool(uv) and sys.version_info >= (3, 11),
                  "uv and Python",
                  f"uv at {uv}, Python {sys.version.split()[0]}")

    # 2. dependencies
    try:
        import anthropic  # noqa: F401
        import fastapi  # noqa: F401
        import mcp  # noqa: F401
        import uvicorn  # noqa: F401
        checks.report(True, "dependencies installed", "mcp, anthropic, fastapi, uvicorn")
    except ImportError as exc:
        checks.report(False, "dependencies installed", str(exc))

    # 3. the API key
    key = config.api_key()
    checks.report(bool(key), ".env with ANTHROPIC_API_KEY",
                  "set" if key else "missing — see .env.example")

    # 4. the API itself
    if key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            client.messages.create(
                model=config.model(), max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            checks.report(True, "Anthropic API reachable", config.model())
        except Exception as exc:  # noqa: BLE001
            checks.report(False, "Anthropic API reachable",
                          f"{type(exc).__name__}: {exc}")
    else:
        checks.report(False, "Anthropic API reachable", "skipped, no key")

    # 5. the databases
    try:
        from data import generate
        generate.build(config.CRM_DB, config.ERP_DB)
        import pricing_service
        summit = pricing_service.find_account("Summit Trail Co.")
        ok = summit.get("available_credit") == 112000.0
        checks.report(ok, "crm.db and erp.db build",
                      f"Summit Trail available credit "
                      f"${summit.get('available_credit'):,.2f}")
    except Exception as exc:  # noqa: BLE001
        checks.report(False, "crm.db and erp.db build", f"{type(exc).__name__}: {exc}")

    # 6. the MCP server, against the step that is loaded
    checkpoint = state.get("checkpoint", "solution")
    expected = config.EXPECTED_TOOLS.get(checkpoint, set())
    try:
        import asyncio

        from workshop.mcp_supervisor import McpSupervisor

        async def list_tools():
            supervisor = McpSupervisor()
            await supervisor.start()
            names = set(supervisor.tool_names)
            error = supervisor.error
            await supervisor.stop()
            return names, error

        names, error = asyncio.run(list_tools())
        if error:
            checks.report(False, "MCP server starts", error)
        else:
            ok = names == expected
            missing = expected - names
            extra = names - expected
            detail = f"{len(names)} tools"
            if missing:
                detail += f", missing {sorted(missing)}"
            if extra:
                detail += f", unexpected {sorted(extra)}"
            checks.report(ok, f"MCP server lists the tools for {checkpoint}", detail)
    except Exception as exc:  # noqa: BLE001
        checks.report(False, "MCP server starts", f"{type(exc).__name__}: {exc}")

    # 7. the deterministic tests
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header"],
        cwd=ROOT, capture_output=True, text=True,
    )
    summary = (result.stdout.strip().splitlines() or ["no output"])[-1]
    if not checks.report(result.returncode == 0, "expected answers (pytest)", summary):
        print()
        print(result.stdout[-4000:])

    print()
    if checks.failed:
        print(_tty(f"{checks.failed} check(s) failed.", RED))
        sys.exit(1)
    print(_tty("All checks passed.", GREEN))
    print(_tty("  `uv run smoke` runs the model-dependent cases "
               "(costs a few cents, not included here).", DIM))
    print()


# --------------------------------------------------------------------------
# test / smoke
# --------------------------------------------------------------------------

def test() -> None:
    sys.exit(subprocess.run([sys.executable, "-m", "pytest", "-q"] + sys.argv[1:],
                            cwd=ROOT).returncode)


def smoke() -> None:
    from workshop import smoke as smoke_module
    sys.exit(smoke_module.main(sys.argv[1:]))
