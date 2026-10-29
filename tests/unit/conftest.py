# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for MealMate unit tests (no LLM calls, no network)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("MEALMATE_ENABLE_MCP", "false")


class FakeToolContext:
    """Minimal stand-in for google.adk.tools.ToolContext used by the tools."""

    def __init__(
        self, state: dict[str, Any] | None = None, confirmed: bool | None = None
    ):
        self.state: dict[str, Any] = dict(state or {})
        self.tool_confirmation = (
            None if confirmed is None else SimpleNamespace(confirmed=confirmed)
        )
        self.confirmation_requests: list[dict[str, Any]] = []
        self.invocation_id = "inv-test"
        self.agent_name = "test_agent"
        self.function_call_id = "call-1"

    def request_confirmation(
        self, *, hint: str | None = None, payload: Any = None
    ) -> None:
        self.confirmation_requests.append({"hint": hint, "payload": payload})


@pytest.fixture
def ctx() -> FakeToolContext:
    return FakeToolContext()


@pytest.fixture
def profile_ctx() -> FakeToolContext:
    return FakeToolContext(
        state={
            "user:household_profile": {
                "household_size": 4,
                "allergies": ["peanuts", "shellfish"],
                "diets": ["halal"],
                "disliked_ingredients": [],
                "weekly_budget_qar": 700.0,
                "max_cooking_minutes": 45,
            }
        }
    )
