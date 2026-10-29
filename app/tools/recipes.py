# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""Recipe discovery tools ("retrieval" tools in the course taxonomy)."""

from __future__ import annotations

from typing import Any

from app.tools.catalog import (
    KNOWN_ALLERGENS,
    KNOWN_DIETS,
    MEAL_TYPES,
    normalise_tokens,
    recipes,
)


def search_recipes(
    meal_type: str,
    diets: list[str] | None = None,
    exclude_allergens: list[str] | None = None,
    max_minutes: int = 60,
    exclude_recipe_ids: list[str] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Finds recipes for one meal slot that respect the household's constraints.

    Use this to shortlist candidate recipes before planning a menu. It never
    returns a recipe that contains an excluded allergen or breaks a diet.

    Args:
        meal_type: One of "breakfast", "lunch" or "dinner".
        diets: Diet labels every recipe must carry, e.g. ["vegetarian"] or
            ["halal", "gluten_free"]. Allowed: vegetarian, vegan, halal,
            gluten_free. Leave empty for no diet filter.
        exclude_allergens: Allergens to avoid, e.g. ["peanuts", "shellfish"].
            Allowed: gluten, dairy, eggs, nuts, peanuts, fish, shellfish, soy,
            sesame.
        max_minutes: Longest acceptable total cooking time, in minutes.
        exclude_recipe_ids: Recipe ids to skip (e.g. already chosen or disliked).
        limit: Maximum number of results (1-10).

    Returns:
        {"status": "success", "results": [{"id", "name", "minutes", "cuisine",
        "diet", "allergens", "kcal_per_serving"}...]} or
        {"status": "error", "error_message": "..."} with guidance on how to fix
        the request.
    """
    meal_type = (meal_type or "").strip().lower()
    if meal_type not in MEAL_TYPES:
        return {
            "status": "error",
            "error_message": f"meal_type must be one of {list(MEAL_TYPES)}, got '{meal_type}'.",
        }
    wanted_diets = normalise_tokens(diets)
    unknown = [d for d in wanted_diets if d not in KNOWN_DIETS]
    if unknown:
        return {
            "status": "error",
            "error_message": f"Unknown diet(s) {unknown}. Use only {sorted(KNOWN_DIETS)}.",
        }
    avoid = normalise_tokens(exclude_allergens)
    unknown_allergens = [a for a in avoid if a not in KNOWN_ALLERGENS]
    skip = set(exclude_recipe_ids or [])
    limit = max(1, min(int(limit), 10))

    results = []
    for r in recipes().values():
        if r["meal_type"] != meal_type or r["id"] in skip:
            continue
        if r["minutes"] > max_minutes:
            continue
        if any(d not in r["diet"] for d in wanted_diets):
            continue
        if any(a in r["allergens"] for a in avoid):
            continue
        results.append(
            {
                "id": r["id"],
                "name": r["name"],
                "minutes": r["minutes"],
                "cuisine": r["cuisine"],
                "diet": r["diet"],
                "allergens": r["allergens"],
                "kcal_per_serving": r["nutrition"]["kcal"],
            }
        )
    results.sort(key=lambda x: x["minutes"])
    response: dict[str, Any] = {"status": "success", "results": results[:limit]}
    if unknown_allergens:
        response["warning"] = (
            f"Allergen(s) {unknown_allergens} are not tracked in the catalog; "
            "ask the user to double-check ingredient lists manually."
        )
    if not results:
        response["hint"] = (
            "No recipe matched. Relax max_minutes or diets, or tell the user the "
            "constraints are too strict for this meal slot."
        )
    return response


def get_recipe(recipe_id: str) -> dict[str, Any]:
    """Returns the full recipe (ingredients for 4 servings and nutrition).

    Args:
        recipe_id: The recipe id returned by search_recipes, e.g. "d03".

    Returns:
        {"status": "success", "recipe": {...}} or {"status": "error", ...}.
    """
    recipe = recipes().get((recipe_id or "").strip().lower())
    if recipe is None:
        return {
            "status": "error",
            "error_message": f"No recipe with id '{recipe_id}'. Call search_recipes first.",
        }
    return {"status": "success", "recipe": recipe}
