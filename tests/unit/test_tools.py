# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for MealMate's function tools (deterministic, offline)."""

from __future__ import annotations

from app.tools import (
    build_shopping_list,
    check_allergens,
    check_menu_nutrition,
    get_household_profile,
    get_recipe,
    place_grocery_order,
    rate_recipe,
    save_household_profile,
    search_recipes,
    update_pantry,
)
from app.tools.catalog import prices, recipes


def test_catalog_is_consistent() -> None:
    # Every ingredient must have a price; every recipe has the core fields.
    price_book = prices()
    for recipe in recipes().values():
        assert recipe["meal_type"] in {"breakfast", "lunch", "dinner"}
        assert {"kcal", "protein_g", "fiber_g"} <= recipe["nutrition"].keys()
        for ing in recipe["ingredients"]:
            assert ing["item"] in price_book, ing["item"]


def test_search_respects_allergens_and_diets() -> None:
    result = search_recipes(
        "dinner", diets=["halal"], exclude_allergens=["fish", "Tree nuts"], limit=10
    )
    assert result["status"] == "success"
    assert result["results"], "expected at least one dinner"
    for r in result["results"]:
        assert "fish" not in r["allergens"] and "nuts" not in r["allergens"]
        assert "halal" in r["diet"]


def test_search_validates_inputs() -> None:
    assert search_recipes("supper")["status"] == "error"
    assert search_recipes("lunch", diets=["keto"])["status"] == "error"
    warn = search_recipes("lunch", exclude_allergens=["kiwi"])
    assert warn["status"] == "success" and "warning" in warn


def test_search_hint_when_nothing_matches() -> None:
    result = search_recipes("dinner", diets=["vegan"], max_minutes=5)
    assert result["results"] == [] and "hint" in result


def test_get_recipe() -> None:
    assert get_recipe("D03")["recipe"]["name"].startswith("Chickpea")
    assert get_recipe("zzz")["status"] == "error"


def test_nutrition_flags_and_errors() -> None:
    ok = check_menu_nutrition([["b02", "l01", "d04"]])
    assert ok["status"] == "success" and ok["days"][0]["kcal"] == 420 + 610 + 680
    assert check_menu_nutrition([["nope"]])["status"] == "error"
    assert check_menu_nutrition([])["status"] == "error"


def test_allergen_check_finds_violations() -> None:
    result = check_allergens(["b05", "d08", "l02"], ["peanuts", "shellfish"])
    assert result["safe"] is False
    assert {v["recipe_id"] for v in result["violations"]} == {"b05", "d08"}
    assert check_allergens(["l02"], ["peanuts"])["safe"] is True


def test_shopping_list_scales_and_skips_pantry(ctx) -> None:
    result = build_shopping_list(
        ["l02", "l02"], servings=2, pantry_items=["Olive Oil"], tool_context=ctx
    )
    assert result["status"] == "success"
    items = {i["item"]: i for i in result["items"]}
    assert "olive oil" not in items and result["skipped_pantry_items"] == ["olive oil"]
    assert (
        items["red lentils"]["qty"] == 400
    )  # 400 g per 4 servings, x2 days, /2 servings
    assert result["total_qar"] > 0
    assert ctx.state["shopping_list"]["total_qar"] == result["total_qar"]


def test_shopping_list_validation(ctx) -> None:
    assert build_shopping_list([], 4, tool_context=ctx)["status"] == "error"
    assert build_shopping_list(["l02"], 40, tool_context=ctx)["status"] == "error"
    assert build_shopping_list(["x99"], 4, tool_context=ctx)["status"] == "error"


def test_profile_roundtrip(ctx) -> None:
    assert get_household_profile(ctx)["status"] == "not_found"
    saved = save_household_profile(
        ctx, household_size=3, allergies=["Peanuts", "kiwi"], diets=["halal"]
    )
    assert saved["status"] == "success" and saved["warnings"]
    assert get_household_profile(ctx)["profile"]["allergies"] == ["peanuts", "kiwi"]
    assert save_household_profile(ctx, household_size=0)["status"] == "error"
    assert (
        save_household_profile(ctx, household_size=2, diets=["paleo"])["status"]
        == "error"
    )


def test_rate_recipe(ctx) -> None:
    assert rate_recipe(ctx, "d01", 5)["ratings"] == {"d01": 5}
    assert rate_recipe(ctx, "d01", 9)["status"] == "error"
    assert rate_recipe(ctx, "zz", 3)["status"] == "error"


def test_pantry_fallback(ctx) -> None:
    assert update_pantry(ctx, add=["Rice", "cumin"])["items"] == ["cumin", "rice"]
    assert update_pantry(ctx, remove=["rice"])["items"] == ["cumin"]


def test_order_requires_list(ctx) -> None:
    assert place_grocery_order(ctx)["status"] == "error"


def test_order_human_in_the_loop(profile_ctx) -> None:
    build_shopping_list(["l02", "d03"], 4, tool_context=profile_ctx)
    first = place_grocery_order(profile_ctx, "evening")
    assert first["status"] == "pending_approval"
    assert (
        profile_ctx.confirmation_requests
        and "QAR" in profile_ctx.confirmation_requests[0]["hint"]
    )

    profile_ctx.tool_confirmation = type("C", (), {"confirmed": True})()
    placed = place_grocery_order(profile_ctx, "evening")
    assert placed["status"] == "placed" and placed["order_id"].startswith("MM-")
    assert profile_ctx.state["user:order_history"][-1]["order_id"] == placed["order_id"]


def test_order_rejected_and_capped(profile_ctx) -> None:
    build_shopping_list(["l02"], 4, tool_context=profile_ctx)
    profile_ctx.tool_confirmation = type("C", (), {"confirmed": False})()
    assert place_grocery_order(profile_ctx)["status"] == "rejected"

    profile_ctx.state["shopping_list"]["total_qar"] = 99999
    assert "safety cap" in place_grocery_order(profile_ctx)["error_message"]
    assert place_grocery_order(profile_ctx, "midnight")["status"] == "error"
