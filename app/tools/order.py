# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""Human-in-the-loop grocery ordering (course Day 2b long-running operation).

Placing an order is the only action with a real-world side effect, so it
ALWAYS pauses for explicit human approval via ``request_confirmation``. The
checkout itself is simulated: no money moves and no external API is called.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from google.adk.tools.tool_context import ToolContext

from app.config import MAX_ORDER_QAR

ORDER_HISTORY_KEY = "user:order_history"
VALID_SLOTS = ("morning", "afternoon", "evening")


def place_grocery_order(
    tool_context: ToolContext, delivery_slot: str = "evening"
) -> dict[str, Any]:
    """Places the grocery order for the current shopping list after human approval.

    Only call this when the user explicitly asks to order the groceries. The
    tool pauses and asks the user to approve the exact basket and total before
    anything is placed. Orders above the platform cap are refused.

    Args:
        delivery_slot: Preferred delivery window: "morning", "afternoon" or
            "evening".

    Returns:
        {"status": "pending_approval", ...} while waiting for the human,
        {"status": "placed", "order_id": ...} once approved,
        {"status": "rejected"} if the human declines, or
        {"status": "error", "error_message": ...}.
    """
    shopping_list = tool_context.state.get("shopping_list")
    if not shopping_list or not shopping_list.get("items"):
        return {
            "status": "error",
            "error_message": "There is no shopping list yet. Plan the week and build the list first.",
        }
    slot = (delivery_slot or "evening").strip().lower()
    if slot not in VALID_SLOTS:
        return {
            "status": "error",
            "error_message": f"delivery_slot must be one of {list(VALID_SLOTS)}.",
        }

    total = float(shopping_list["total_qar"])
    if total > MAX_ORDER_QAR:
        return {
            "status": "error",
            "error_message": (
                f"Order total {total:.2f} QAR exceeds the {MAX_ORDER_QAR:.0f} QAR safety cap. "
                "Suggest cheaper swaps or splitting the order."
            ),
        }

    budget = (tool_context.state.get("user:household_profile") or {}).get(
        "weekly_budget_qar"
    )
    over_budget = budget is not None and total > float(budget)

    confirmation = tool_context.tool_confirmation
    if not confirmation:
        hint = (
            f"Approve grocery order of {len(shopping_list['items'])} items for "
            f"{total:.2f} QAR, delivery: {slot}?"
        )
        if over_budget:
            hint += (
                f" WARNING: this is over the weekly budget of {float(budget):.0f} QAR."
            )
        tool_context.request_confirmation(
            hint=hint,
            payload={
                "total_qar": total,
                "item_count": len(shopping_list["items"]),
                "slot": slot,
            },
        )
        return {
            "status": "pending_approval",
            "message": "Waiting for the user to approve the order.",
        }

    if not confirmation.confirmed:
        return {
            "status": "rejected",
            "message": "The user declined the order. Nothing was placed.",
        }

    order = {
        "order_id": f"MM-{uuid.uuid4().hex[:8].upper()}",
        "total_qar": total,
        "delivery_slot": slot,
        "placed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "simulated": True,
    }
    history = list(tool_context.state.get(ORDER_HISTORY_KEY, []))
    history.append(order)
    tool_context.state[ORDER_HISTORY_KEY] = history[-10:]
    return {"status": "placed", **order}
