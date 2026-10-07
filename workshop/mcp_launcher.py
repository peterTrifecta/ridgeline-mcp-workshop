"""Stdio entry point for the Ridgeline MCP server (`uv run ridgeline-mcp`).

It loads a tools file by path so the tests can run the server from a checkpoint
(RIDGELINE_TOOLS_FILE) without touching the one being edited live.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_tools_module(path: Path | None = None):
    path = Path(path or os.environ.get("RIDGELINE_TOOLS_FILE") or ROOT / "ridgeline_tools.py")
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"No MCP tools file at {path}")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("ridgeline_tools", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ridgeline_tools"] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    load_tools_module().mcp.run()


if __name__ == "__main__":
    main()
