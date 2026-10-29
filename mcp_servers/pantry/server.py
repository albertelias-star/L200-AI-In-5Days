# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""Pantry MCP server: a tiny, self-hosted Model Context Protocol server.

Why a separate MCP server? The course recommends consuming external systems
through MCP instead of hand-writing API wrappers, and self-hosting servers
rather than using unaudited public ones. In production this server would
front a real smart-fridge / inventory API; here it persists to a local JSON
file so the demo is fully reproducible.

Run standalone (stdio transport):  python mcp_servers/pantry/server.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

# stdout is the MCP stdio channel, so all logging must go to stderr.
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(message)s")
log = logging.getLogger("pantry-mcp")

DB_PATH = Path(os.getenv("MEALMATE_PANTRY_DB", Path.home() / ".mealmate_pantry.json"))
MAX_ITEMS = 200
MAX_NAME_LEN = 60

server = MCPServer(
    name="mealmate-pantry",
    instructions="Read and update the household pantry (ingredients already at home).",
)


def _load() -> list[str]:
    if not DB_PATH.exists():
        return []
    try:
        data = json.loads(DB_PATH.read_text(encoding="utf-8"))
        return sorted({str(x).lower() for x in data.get("items", [])})
    except (OSError, json.JSONDecodeError):
        log.warning("pantry db unreadable, starting empty")
        return []


def _save(items: list[str]) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write so a crash never leaves a half-written file.
    with tempfile.NamedTemporaryFile(
        "w", dir=DB_PATH.parent, delete=False, encoding="utf-8"
    ) as fh:
        json.dump({"items": sorted(set(items))}, fh)
        tmp = fh.name
    os.replace(tmp, DB_PATH)


def _clean(names: list[str]) -> tuple[list[str], list[str]]:
    """Validates ingredient names; returns (accepted, rejected)."""
    ok, bad = [], []
    for n in names:
        token = str(n).strip().lower()
        if 0 < len(token) <= MAX_NAME_LEN and all(
            c.isalnum() or c in " -'()" for c in token
        ):
            ok.append(token)
        else:
            bad.append(str(n)[:MAX_NAME_LEN])
    return ok, bad


@server.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def list_pantry() -> dict:
    """Lists every ingredient currently in the household pantry."""
    items = _load()
    log.info(json.dumps({"event": "list_pantry", "count": len(items)}))
    return {"status": "success", "items": items}


@server.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True
    )
)
def add_pantry_items(items: list[str]) -> dict:
    """Adds ingredients to the pantry, e.g. ["basmati rice", "olive oil"].

    Names must be plain ingredient names (letters, numbers, spaces, - ' ( )).
    """
    accepted, rejected = _clean(items)
    current = set(_load()) | set(accepted)
    if len(current) > MAX_ITEMS:
        return {
            "status": "error",
            "error_message": f"Pantry is limited to {MAX_ITEMS} items.",
        }
    _save(sorted(current))
    log.info(
        json.dumps(
            {"event": "add_pantry_items", "added": accepted, "rejected": rejected}
        )
    )
    result = {"status": "success", "items": sorted(current)}
    if rejected:
        result["rejected"] = rejected
        result["hint"] = "Some names were rejected; use plain ingredient names."
    return result


@server.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True
    )
)
def remove_pantry_items(items: list[str]) -> dict:
    """Removes ingredients that have run out from the pantry."""
    accepted, _ = _clean(items)
    current = set(_load()) - set(accepted)
    _save(sorted(current))
    log.info(json.dumps({"event": "remove_pantry_items", "removed": accepted}))
    return {"status": "success", "items": sorted(current)}


if __name__ == "__main__":
    server.run("stdio")
