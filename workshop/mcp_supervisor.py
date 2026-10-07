"""Owns the Ridgeline MCP server subprocess and talks to it over stdio.

One asyncio task enters and exits the stdio client and the client session, which
is what keeps anyio's cancel scopes happy. Everything else just awaits calls on
the session.

Restarting is how a live edit to ridgeline_tools.py takes effect: the chat page's
"New conversation" button restarts the server and it re-reads the file.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, get_default_environment, stdio_client

from workshop import config

ROOT = config.ROOT


class McpSupervisor:
    """A running Ridgeline MCP server, with its tool list."""

    def __init__(self, tools_file: Path | None = None, env_extra: dict[str, str] | None = None):
        self.tools_file = Path(tools_file) if tools_file else config.TOOLS_FILE
        self.env_extra = dict(env_extra or {})
        self.tools: list[dict[str, Any]] = []
        self.tools_list_json: list[dict[str, Any]] = []
        self.error: str | None = None
        self._session: ClientSession | None = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # --- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        self._stop = asyncio.Event()
        ready: asyncio.Future = asyncio.get_running_loop().create_future()
        self._task = asyncio.create_task(self._run(ready))
        try:
            await asyncio.wait_for(ready, timeout=60)
            self.error = None
        except Exception as exc:  # noqa: BLE001 - surfaced in the UI header
            self.error = f"{type(exc).__name__}: {exc}"
            self.tools = []
            self.tools_list_json = []
            await self.stop()

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=15)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            except Exception:  # noqa: BLE001 - shutting down anyway
                pass
        self._task = None
        self._session = None

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    async def _run(self, ready: asyncio.Future) -> None:
        env = get_default_environment()
        env["RIDGELINE_TOOLS_FILE"] = str(self.tools_file)
        for name in ("AS_OF", "RIDGELINE_DATA_DIR"):
            if os.environ.get(name):
                env[name] = os.environ[name]
        env.update(self.env_extra)

        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "workshop.mcp_launcher"],
            cwd=str(ROOT),
            env=env,
        )
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    self._session = session
                    self.tools_list_json = [
                        {"name": t.name,
                         "description": t.description,
                         "inputSchema": t.input_schema}
                        for t in listed.tools
                    ]
                    self.tools = [
                        {"name": t.name,
                         "description": t.description or "",
                         "input_schema": t.input_schema}
                        for t in listed.tools
                    ]
                    if not ready.done():
                        ready.set_result(True)
                    await self._stop.wait()
        except Exception as exc:  # noqa: BLE001
            if not ready.done():
                ready.set_exception(exc)
            else:
                self.error = f"{type(exc).__name__}: {exc}"

    # --- calls -------------------------------------------------------------

    async def call(self, name: str, arguments: dict) -> tuple[str, bool]:
        """Run one tool. Returns (text result, is_error)."""
        if self._session is None:
            return json.dumps({"error": "The Ridgeline MCP server is not running."}), True
        try:
            result = await self._session.call_tool(name, arguments or {})
        except Exception as exc:  # noqa: BLE001 - handed back to the model
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"}), True

        chunks = []
        for block in result.content:
            text = getattr(block, "text", None)
            chunks.append(text if text is not None else str(block))
        return ("\n".join(chunks) or "(no output)"), bool(result.is_error)

    @property
    def tool_names(self) -> list[str]:
        return [t["name"] for t in self.tools]
