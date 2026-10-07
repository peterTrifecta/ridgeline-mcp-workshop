"""The local chat page used on the projector.

The API key stays here, in the Python backend. The browser never sees it.

"New conversation" clears the history *and* restarts the MCP server, so an edit
to ridgeline_tools.py takes effect without restarting this app.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from workshop import agent, config
from workshop.mcp_supervisor import McpSupervisor

STATIC = Path(__file__).resolve().parent / "static"


class Session:
    """Everything the page needs. One presenter, one conversation."""

    def __init__(self):
        self.messages: list[dict] = []
        self.mcp = McpSupervisor()
        self.client = None
        self.lock = asyncio.Lock()

    async def reset(self) -> None:
        self.messages = []
        await self.mcp.restart()


session = Session()


@asynccontextmanager
async def lifespan(app: FastAPI):
    session.client = agent.new_client()
    await session.mcp.start()
    yield
    await session.mcp.stop()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def no_browser_cache(request, call_next):
    """Never cache the page or its CSS/JS, so a plain refresh shows edits."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def state_payload() -> dict[str, Any]:
    state = config.read_state()
    spec = config.STEPS.get(str(state.get("step", "solution")), config.STEPS["solution"])
    return {
        "step": state.get("step"),
        "label": config.step_label(state),
        "about": spec["about"],
        "tools_default": state.get("tools_default", True),
        "tools": session.mcp.tool_names,
        "tool_count": len(session.mcp.tool_names),
        "model": config.model(),
        "mcp_error": session.mcp.error,
        "has_history": bool(session.messages),
    }


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
async def get_state():
    return state_payload()


@app.get("/api/tools")
async def get_tools():
    """The raw tools/list payload — what the model actually receives."""
    return {"tools": session.mcp.tools_list_json}


@app.post("/api/new")
async def new_conversation():
    async with session.lock:
        await session.reset()
    return state_payload()


class ChatRequest(BaseModel):
    message: str
    use_tools: bool = True


@app.post("/api/chat")
async def chat(request: ChatRequest):
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(event: dict) -> None:
        await queue.put(event)

    async def run() -> None:
        try:
            async with session.lock:
                session.messages.append({"role": "user", "content": request.message})
                await agent.run_turn(
                    session.client, session.messages, session.mcp, emit,
                    use_tools=request.use_tools,
                )
        except Exception as exc:  # noqa: BLE001 - shown in the page
            await queue.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            await queue.put({"type": "done"})

    async def stream():
        task = asyncio.create_task(run())
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event["type"] == "done":
                break
        await task

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
