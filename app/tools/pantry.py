# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""Pantry access for MealMate.

Primary path: the self-hosted **Pantry MCP server** (``mcp_servers/pantry``),
consumed through ADK's ``McpToolset`` with an explicit tool allow-list.
Fallback path: in-process tools over user-scoped session state, used when
MCP is disabled (``MEALMATE_ENABLE_MCP=false``) or unavailable at runtime.
"""

from __future__ import annotations

import functools
import os
import sys
from pathlib import Path
from typing import Any

from google.adk.tools.tool_context import ToolContext

from app import config

PANTRY_STATE_KEY = "user:pantry"
PANTRY_MCP_TOOLS = ["list_pantry", "add_pantry_items", "remove_pantry_items"]
_SERVER = Path(__file__).resolve().parents[2] / "mcp_servers" / "pantry" / "server.py"


@functools.cache
def pantry_toolset() -> Any | None:
    """Builds the (shared) McpToolset for the pantry server, or None if disabled.

    Cached so every agent reuses one MCP server process instead of spawning
    one per agent.
    """
    if not config.ENABLE_MCP or not _SERVER.exists():
        return None
    from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
    from mcp import StdioServerParameters

    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[str(_SERVER)],
                env={**os.environ, "MEALMATE_PANTRY_DB": config.PANTRY_DB_PATH},
            ),
            timeout=20,
        ),
        tool_filter=PANTRY_MCP_TOOLS,  # least privilege: only expose what we need
    )


def get_pantry(tool_context: ToolContext) -> dict[str, Any]:
    """Lists ingredients the household already has at home (fallback tool).

    Returns:
        {"status": "success", "items": ["olive oil", ...]}.
    """
    return {
        "status": "success",
        "items": sorted(tool_context.state.get(PANTRY_STATE_KEY, [])),
    }


def update_pantry(
    tool_context: ToolContext,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> dict[str, Any]:
    """Adds or removes pantry ingredients (fallback tool).

    Args:
        add: Ingredient names to add, e.g. ["basmati rice", "olive oil"].
        remove: Ingredient names that ran out.

    Returns:
        {"status": "success", "items": [...]}.
    """
    items = {i.strip().lower() for i in tool_context.state.get(PANTRY_STATE_KEY, [])}
    items |= {a.strip().lower() for a in (add or []) if a.strip()}
    items -= {r.strip().lower() for r in (remove or [])}
    tool_context.state[PANTRY_STATE_KEY] = sorted(items)
    return {"status": "success", "items": sorted(items)}


def pantry_tools() -> list[Any]:
    """Returns the MCP toolset when enabled, else the in-process fallback tools."""
    toolset = pantry_toolset()
    return [toolset] if toolset is not None else [get_pantry, update_pantry]
