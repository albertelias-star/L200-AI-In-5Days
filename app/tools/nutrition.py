# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""Nutrition and allergen verification tools used by the quality critic."""

from __future__ import annotations

from typing import Any

from app.tools.catalog import normalise_tokens, recipes

# Simple, transparent daily targets per person for three main meals (snacks
# excluded). Illustrative only - not medical advice.
DAILY_TARGETS = {"kcal": (1200, 2600), "protein_g": (45, 160), "fiber_g": (20, 60)}


def check_menu_nutrition(daily_recipe_ids: list[list[str]]) -> dict[str, Any]:
    """Computes per-day nutrition for a menu and flags days outside healthy ranges.

    Use this to verify a draft weekly menu. Each inner list is one day's recipe
    ids (normally breakfast, lunch, dinner).

    Args:
        daily_recipe_ids: One list of recipe ids per day, e.g.
            [["b01", "l02", "d03"], ["b03", "l06", "d01"]].

    Returns:
        {"status": "success", "days": [{"day": 1, "kcal": ..., "protein_g": ...,
        "fiber_g": ..., "issues": [...]}], "summary": "..."} where "issues" lists
        any value outside the target ranges, or {"status": "error", ...}.
    """
    if not daily_recipe_ids:
        return {
            "status": "error",
            "error_message": "Provide at least one day of recipe ids.",
        }
    catalog = recipes()
    days = []
    total_issues = 0
    for idx, day in enumerate(daily_recipe_ids, start=1):
        unknown = [rid for rid in day if rid not in catalog]
        if unknown:
            return {
                "status": "error",
                "error_message": f"Day {idx} has unknown recipe ids {unknown}. Use ids from search_recipes.",
            }
        totals = {"kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0}
        for rid in day:
            for key in totals:
                totals[key] += catalog[rid]["nutrition"][key]
        issues = []
        for key, (low, high) in DAILY_TARGETS.items():
            if totals[key] < low:
                issues.append(f"{key} too low ({totals[key]} < {low})")
            elif totals[key] > high:
                issues.append(f"{key} too high ({totals[key]} > {high})")
        total_issues += len(issues)
        days.append({"day": idx, **totals, "issues": issues})
    summary = (
        "All days are within target ranges."
        if total_issues == 0
        else f"{total_issues} nutrition issue(s) found; swap recipes on the flagged days."
    )
    return {"status": "success", "days": days, "summary": summary}


def check_allergens(recipe_ids: list[str], allergens: list[str]) -> dict[str, Any]:
    """Verifies that none of the given recipes contain the household's allergens.

    This is a deterministic safety check: always run it before approving a menu.

    Args:
        recipe_ids: All recipe ids in the menu.
        allergens: The household's allergens, e.g. ["peanuts", "shellfish"].

    Returns:
        {"status": "success", "safe": bool, "violations": [{"recipe_id",
        "name", "allergens"}...]}.
    """
    avoid = set(normalise_tokens(allergens))
    catalog = recipes()
    violations = []
    for rid in dict.fromkeys(recipe_ids):  # keep order, drop duplicates
        recipe = catalog.get(rid)
        if recipe is None:
            violations.append(
                {
                    "recipe_id": rid,
                    "name": "UNKNOWN",
                    "allergens": ["unknown recipe id"],
                }
            )
            continue
        hit = sorted(avoid.intersection(recipe["allergens"]))
        if hit:
            violations.append(
                {"recipe_id": rid, "name": recipe["name"], "allergens": hit}
            )
    return {"status": "success", "safe": not violations, "violations": violations}
