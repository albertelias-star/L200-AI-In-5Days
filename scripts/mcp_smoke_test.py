# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""Smoke test: start the Pantry MCP server over stdio and exercise its tools.

Proves the MCP handshake, tool discovery and tool calls work end to end,
independently of any LLM. Used in CI (``.github/workflows/ci.yml``).
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parents[1] / "mcp_servers" / "pantry" / "server.py"


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(SERVER)],
            env={**os.environ, "MEALMATE_PANTRY_DB": str(Path(tmp) / "pantry.json")},
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = sorted(t.name for t in (await session.list_tools()).tools)
            print("tools:", tools)
            assert tools == [
                "add_pantry_items",
                "list_pantry",
                "remove_pantry_items",
            ], tools
            result = await session.call_tool(
                "add_pantry_items", {"items": ["olive oil", "cumin"]}
            )
            print(
                "add_pantry_items ->",
                result.content[0].text if result.content else result,
            )
            listed = await session.call_tool("list_pantry", {})
            text = listed.content[0].text if listed.content else ""
            assert "olive oil" in text and "cumin" in text, text
            print("MCP smoke test passed")


if __name__ == "__main__":
    asyncio.run(main())
