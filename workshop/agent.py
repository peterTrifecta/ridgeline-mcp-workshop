"""The chat loop: Claude, streaming, with the Ridgeline tools attached.

Emits UI events as it goes so the projector can show every tool call as it
happens. The same loop backs the chat page and `uv run smoke`.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from anthropic import AsyncAnthropic

from workshop import config
from workshop.mcp_supervisor import McpSupervisor

SYSTEM_PROMPT = (
    "You are a sales assistant for Ridgeline Outfitters, a company that makes "
    "outdoor gear and sells it wholesale to retailers and guide outfitters.\n\n"
    "When tools are available, use them and base your answer on what they return "
    "rather than on what you assume. Keep answers short and concrete: a few "
    "sentences, with the numbers that matter and who has to approve what."
)

MAX_TOKENS = 8000
MAX_TOOL_ROUNDS = 12

Emit = Callable[[dict[str, Any]], Awaitable[None]]


def new_client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=config.api_key())


async def run_turn(
    client: AsyncAnthropic,
    messages: list[dict],
    mcp: McpSupervisor | None,
    emit: Emit,
    use_tools: bool = True,
    model: str | None = None,
) -> list[dict]:
    """Run one user turn to completion, tool calls and all.

    `messages` is mutated and returned, so the conversation carries forward.
    """
    model = model or config.model()
    tools = mcp.tools if (use_tools and mcp and mcp.tools) else None

    for _ in range(MAX_TOOL_ROUNDS):
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM_PROMPT,
            "messages": messages,
            "output_config": {"effort": config.effort()},
        }
        if tools:
            kwargs["tools"] = tools

        async with client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "text":
                    await emit({"type": "text_delta", "text": event.text})
            final = await stream.get_final_message()

        # Append the assistant turn exactly as it came back. Thinking blocks
        # have to go back unchanged, so never rebuild this from the text.
        messages.append({"role": "assistant", "content": final.content})

        if final.stop_reason == "refusal":
            await emit({"type": "error",
                        "message": "The model declined to answer that request."})
            return messages

        if final.stop_reason != "tool_use":
            return messages

        results = []
        for block in final.content:
            if block.type != "tool_use":
                continue
            await emit({"type": "tool_call", "id": block.id,
                        "name": block.name, "input": block.input})
            text, is_error = await mcp.call(block.name, block.input)
            await emit({"type": "tool_result", "id": block.id, "name": block.name,
                        "result": text, "is_error": is_error})
            result_block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": text,
            }
            if is_error:
                result_block["is_error"] = True
            results.append(result_block)

        messages.append({"role": "user", "content": results})

    await emit({"type": "error",
                "message": f"Stopped after {MAX_TOOL_ROUNDS} rounds of tool calls."})
    return messages


def assistant_text(messages: list[dict]) -> str:
    """The text of the last assistant turn — what the user actually sees."""
    for message in reversed(messages):
        if message["role"] != "assistant":
            continue
        parts = []
        for block in message["content"]:
            block_type = getattr(block, "type", None) or (
                block.get("type") if isinstance(block, dict) else None)
            if block_type == "text":
                parts.append(getattr(block, "text", None) or block.get("text", ""))
        if parts:
            return "\n".join(parts)
    return ""
