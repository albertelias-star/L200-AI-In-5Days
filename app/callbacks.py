# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""Agent-level callbacks: deterministic policy and long-term memory.

* ``enforce_allergy_policy`` (before_tool_callback): the LLM can never put a
  recipe containing a household allergen on a shopping list, no matter what
  the prompt says. "Write software, not rules" - the check is code.
* ``save_session_to_memory`` (after_agent_callback): pushes the finished
  conversation to the memory service (Memory Bank on Agent Runtime,
  in-memory locally) so future sessions can recall preferences and feedback.
"""

from __future__ import annotations

import logging
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from app.tools.catalog import normalise_tokens, recipes
from app.tools.profile import PROFILE_KEY

log = logging.getLogger("mealmate.policy")

_RECIPE_ARG_TOOLS = {"build_shopping_list": "recipe_ids"}


def enforce_allergy_policy(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> dict[str, Any] | None:
    """Blocks tool calls that would include a recipe with a household allergen."""
    arg_name = _RECIPE_ARG_TOOLS.get(tool.name)
    if not arg_name:
        return None
    profile = tool_context.state.get(PROFILE_KEY) or {}
    allergies = set(normalise_tokens(profile.get("allergies")))
    if not allergies:
        return None
    catalog = recipes()
    offending = sorted(
        {
            rid
            for rid in args.get(arg_name, []) or []
            if rid in catalog and allergies.intersection(catalog[rid]["allergens"])
        }
    )
    if offending:
        log.warning(
            '{"event": "policy_block", "tool": "%s", "recipes": %s}',
            tool.name,
            offending,
        )
        return {
            "status": "error",
            "error_message": (
                f"Policy violation: recipes {offending} contain household allergens "
                f"{sorted(allergies)}. Replace them before building the list."
            ),
        }
    return None


async def save_session_to_memory(callback_context: CallbackContext) -> None:
    """Persists the session to long-term memory after each coordinator turn."""
    try:
        await callback_context.add_session_to_memory()
    except ValueError:
        # No memory service configured (e.g. plain unit tests) - nothing to do.
        pass
    except Exception as exc:  # never let memory problems break the conversation
        log.warning(
            '{"event": "memory_save_failed", "error": "%s"}', type(exc).__name__
        )
    return None
