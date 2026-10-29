# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""MealMate function tools, grouped by the course's tool taxonomy.

* Retrieval: search_recipes, get_recipe
* Verification: check_menu_nutrition, check_allergens
* Calculation / action: build_shopping_list
* State / memory: save_household_profile, get_household_profile, rate_recipe
* Human-in-the-loop action: place_grocery_order
* External system via MCP: pantry tools (see app/tools/pantry.py)
"""

from app.tools.nutrition import check_allergens, check_menu_nutrition
from app.tools.order import place_grocery_order
from app.tools.pantry import get_pantry, pantry_tools, update_pantry
from app.tools.profile import get_household_profile, rate_recipe, save_household_profile
from app.tools.recipes import get_recipe, search_recipes
from app.tools.shopping import build_shopping_list

__all__ = [
    "build_shopping_list",
    "check_allergens",
    "check_menu_nutrition",
    "get_household_profile",
    "get_pantry",
    "get_recipe",
    "pantry_tools",
    "place_grocery_order",
    "rate_recipe",
    "save_household_profile",
    "search_recipes",
    "update_pantry",
]
