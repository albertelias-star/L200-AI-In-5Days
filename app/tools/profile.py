# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""Household profile and feedback tools backed by user-scoped session state.

State keys prefixed with ``user:`` persist across every session of the same
user (course Day 3a), so MealMate remembers allergies and budgets between
conversations. Long-term, semantic recall of past conversations is handled
separately by the memory service (see app/agent.py).
"""

from __future__ import annotations

from typing import Any

from google.adk.tools.tool_context import ToolContext

from app.config import DEFAULT_WEEKLY_BUDGET_QAR
from app.tools.catalog import KNOWN_ALLERGENS, KNOWN_DIETS, normalise_tokens, recipes

PROFILE_KEY = "user:household_profile"
RATINGS_KEY = "user:recipe_ratings"


def save_household_profile(
    tool_context: ToolContext,
    household_size: int,
    allergies: list[str] | None = None,
    diets: list[str] | None = None,
    disliked_ingredients: list[str] | None = None,
    weekly_budget_qar: float = DEFAULT_WEEKLY_BUDGET_QAR,
    max_cooking_minutes: int = 45,
) -> dict[str, Any]:
    """Saves (or updates) the household's food profile for future sessions.

    Call this once the user has told you who is eating and any restrictions.
    Only pass fields the user actually stated; ask instead of guessing allergies.

    Args:
        household_size: Number of people eating each meal (1-12).
        allergies: Allergens to always avoid, e.g. ["peanuts", "shellfish"].
        diets: Diet labels that apply to every meal, e.g. ["halal"].
        disliked_ingredients: Ingredients to avoid where possible.
        weekly_budget_qar: Weekly grocery budget in Qatari Riyal.
        max_cooking_minutes: Longest acceptable cooking time per meal.

    Returns:
        {"status": "success", "profile": {...}, "warnings": [...]} or
        {"status": "error", ...}.
    """
    if not 1 <= int(household_size) <= 12:
        return {
            "status": "error",
            "error_message": "household_size must be between 1 and 12.",
        }
    if weekly_budget_qar <= 0:
        return {
            "status": "error",
            "error_message": "weekly_budget_qar must be positive.",
        }
    allergy_tokens = normalise_tokens(allergies)
    diet_tokens = normalise_tokens(diets)
    warnings = []
    untracked = [a for a in allergy_tokens if a not in KNOWN_ALLERGENS]
    if untracked:
        warnings.append(
            f"Allergens {untracked} are not tracked by the recipe catalog. "
            "Tell the user to check ingredient labels themselves."
        )
    bad_diets = [d for d in diet_tokens if d not in KNOWN_DIETS]
    if bad_diets:
        return {
            "status": "error",
            "error_message": f"Unknown diet(s) {bad_diets}. Use only {sorted(KNOWN_DIETS)}.",
        }
    profile = {
        "household_size": int(household_size),
        "allergies": allergy_tokens,
        "diets": diet_tokens,
        "disliked_ingredients": [
            d.strip().lower() for d in (disliked_ingredients or [])
        ],
        "weekly_budget_qar": float(weekly_budget_qar),
        "max_cooking_minutes": int(max_cooking_minutes),
    }
    tool_context.state[PROFILE_KEY] = profile
    return {"status": "success", "profile": profile, "warnings": warnings}


def get_household_profile(tool_context: ToolContext) -> dict[str, Any]:
    """Returns the saved household profile and recipe ratings, if any.

    Returns:
        {"status": "success", "profile": {...}, "ratings": {...}} or
        {"status": "not_found", "hint": "..."} when no profile exists yet.
    """
    profile = tool_context.state.get(PROFILE_KEY)
    if not profile:
        return {
            "status": "not_found",
            "hint": "No profile yet. Ask for household size, allergies, diets and budget.",
        }
    return {
        "status": "success",
        "profile": profile,
        "ratings": tool_context.state.get(RATINGS_KEY, {}),
    }


def rate_recipe(
    tool_context: ToolContext, recipe_id: str, stars: int
) -> dict[str, Any]:
    """Records the household's 1-5 star rating for a recipe they cooked.

    Low-rated recipes (1-2 stars) are excluded from future menus.

    Args:
        recipe_id: Recipe id, e.g. "d02".
        stars: Rating from 1 (disliked) to 5 (loved).

    Returns:
        {"status": "success", "ratings": {...}} or {"status": "error", ...}.
    """
    if recipe_id not in recipes():
        return {"status": "error", "error_message": f"Unknown recipe id '{recipe_id}'."}
    if not 1 <= int(stars) <= 5:
        return {"status": "error", "error_message": "stars must be between 1 and 5."}
    ratings = dict(tool_context.state.get(RATINGS_KEY, {}))
    ratings[recipe_id] = int(stars)
    tool_context.state[RATINGS_KEY] = ratings
    return {"status": "success", "ratings": ratings}
