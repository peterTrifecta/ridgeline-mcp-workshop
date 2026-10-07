# ridgeline-mcp-workshop

A small MCP server over a fictional company's CRM and ERP, built for a live
five-step walkthrough. `README.md` explains the design and how to run it.

## Rules
- Business rules live only in `pricing_service.py`. `ridgeline_tools.py` (the MCP layer) holds only AI-specific guardrails.
- `checkpoints/` holds `ridgeline_tools.py` at the start of each step and `snippets/` holds the pasted edits; `scripts/rebuild_checkpoints.py` regenerates the checkpoints from the solution and the snippets. Change those, not the checkpoints by hand, and keep `uv run test` green.
- The committed `ridgeline_tools.py` is the finished solution. After `uv run reset`, git shows it as modified; don't commit that state.
- The API key is `ANTHROPIC_API_KEY` in `.env`. Never commit `.env` or print the key.
- Developed on macOS. Python via uv. No Node/npm.
