# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""Read-only access to MealMate's bundled, synthetic recipe and price catalog.

The catalog ships with the repo (``app/data``) so the agent is reproducible
and needs no third-party API keys. All prices are illustrative QAR values.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

KNOWN_ALLERGENS = frozenset(
    {"gluten", "dairy", "eggs", "nuts", "peanuts", "fish", "shellfish", "soy", "sesame"}
)
KNOWN_DIETS = frozenset({"vegetarian", "vegan", "halal", "gluten_free"})
MEAL_TYPES = ("breakfast", "lunch", "dinner")
BASE_SERVINGS = 4  # every recipe's ingredient list is written for 4 servings


@functools.cache
def recipes() -> dict[str, dict[str, Any]]:
    """Returns all recipes keyed by recipe id."""
    data = json.loads((DATA_DIR / "recipes.json").read_text(encoding="utf-8"))
    return {r["id"]: r for r in data}


@functools.cache
def prices() -> dict[str, dict[str, Any]]:
    """Returns the per-unit price and aisle category for every ingredient."""
    return json.loads((DATA_DIR / "prices.json").read_text(encoding="utf-8"))


def normalise_tokens(values: list[str] | None) -> list[str]:
    """Lower-cases and de-duplicates free-text tokens such as allergens."""
    if not values:
        return []
    out: list[str] = []
    for v in values:
        token = v.strip().lower().replace("-", "_").replace(" ", "_")
        if token == "tree_nuts":
            token = "nuts"
        if token and token not in out:
            out.append(token)
    return out
