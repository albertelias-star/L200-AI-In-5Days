# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""Shopping list and cost tools ("action" and "calculation" tools)."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from google.adk.tools.tool_context import ToolContext

from app.tools.catalog import BASE_SERVINGS, prices, recipes


def _pantry_lookup(pantry_items: list[str] | None) -> set[str]:
    return {p.strip().lower() for p in (pantry_items or []) if p.strip()}


def build_shopping_list(
    recipe_ids: list[str],
    servings: int,
    pantry_items: list[str] | None = None,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Aggregates the ingredients for a menu into a costed, aisle-grouped list.

    Ingredients already in the pantry are excluded. The result is also saved to
    session state as "shopping_list" so the coordinator can place the order.

    Args:
        recipe_ids: Every recipe id in the menu. Repeat an id if it is cooked
            more than once in the week.
        servings: Number of people eating each meal (1-12).
        pantry_items: Ingredient names the household already has, e.g.
            ["olive oil", "basmati rice"]. Get these from the pantry tools.

    Returns:
        {"status": "success", "items": [{"item", "qty", "unit", "category",
        "est_cost_qar"}...], "total_qar": float, "skipped_pantry_items": [...]}
        or {"status": "error", ...}.
    """
    if not recipe_ids:
        return {
            "status": "error",
            "error_message": "recipe_ids is empty; plan a menu first.",
        }
    if not 1 <= int(servings) <= 12:
        return {
            "status": "error",
            "error_message": "servings must be between 1 and 12.",
        }
    catalog, price_book = recipes(), prices()
    unknown = sorted({rid for rid in recipe_ids if rid not in catalog})
    if unknown:
        return {"status": "error", "error_message": f"Unknown recipe ids {unknown}."}

    scale = int(servings) / BASE_SERVINGS
    have = _pantry_lookup(pantry_items)
    totals: dict[tuple[str, str], float] = defaultdict(float)
    for rid in recipe_ids:
        for ing in catalog[rid]["ingredients"]:
            totals[(ing["item"], ing["unit"])] += ing["qty"] * scale

    items, skipped, total = [], set(), 0.0
    for (name, unit), qty in sorted(totals.items()):
        if name.lower() in have:
            skipped.add(name)
            continue
        qty = math.ceil(qty) if unit == "pcs" else round(qty)
        entry = price_book.get(name, {"category": "Other", "qar_per_unit": 0.0})
        cost = round(qty * entry["qar_per_unit"], 2)
        total += cost
        items.append(
            {
                "item": name,
                "qty": qty,
                "unit": unit,
                "category": entry["category"],
                "est_cost_qar": cost,
            }
        )
    items.sort(key=lambda x: (x["category"], x["item"]))
    result = {
        "status": "success",
        "items": items,
        "total_qar": round(total, 2),
        "skipped_pantry_items": sorted(skipped),
    }
    if tool_context is not None:
        tool_context.state["shopping_list"] = {
            "items": items,
            "total_qar": result["total_qar"],
            "servings": int(servings),
        }
    return result
