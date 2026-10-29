# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""Central configuration for MealMate.

Every tunable lives here and can be overridden with an environment variable,
so the same code runs locally (``.env``), in CI and on Agent Runtime.
"""

from __future__ import annotations

import os

from google.genai import types

# --- Model routing -----------------------------------------------------------
# A small, cheap model does the high-volume worker steps (recipe scouting,
# shopping lists); a stronger model plans the menu and coordinates the user
# conversation. See "Model routing" in README.md.
FAST_MODEL: str = os.getenv("MEALMATE_FAST_MODEL", "gemini-3.5-flash-lite")
SMART_MODEL: str = os.getenv("MEALMATE_SMART_MODEL", "gemini-3.8-flash")

# Retry policy taken from the course labs (Day 1b / 2b / 3a).
RETRY_OPTIONS = types.HttpRetryOptions(
    attempts=5,
    exp_base=7,
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],
)

# --- Guardrails / business rules ----------------------------------------------
# Hard ceiling for a single grocery order, in Qatari Riyal (QAR). Orders above
# the household budget always require human approval; orders above this cap
# are refused outright by the deterministic policy layer.
MAX_ORDER_QAR: float = float(os.getenv("MEALMATE_MAX_ORDER_QAR", "1500"))
DEFAULT_WEEKLY_BUDGET_QAR: float = float(
    os.getenv("MEALMATE_DEFAULT_WEEKLY_BUDGET_QAR", "600")
)
MAX_LOOP_ITERATIONS: int = int(os.getenv("MEALMATE_MAX_LOOP_ITERATIONS", "3"))

# --- Context management -------------------------------------------------------
COMPACTION_INTERVAL: int = int(os.getenv("MEALMATE_COMPACTION_INTERVAL", "6"))
COMPACTION_OVERLAP: int = int(os.getenv("MEALMATE_COMPACTION_OVERLAP", "1"))

# --- MCP ---------------------------------------------------------------------
# Set MEALMATE_ENABLE_MCP=false to run without the pantry MCP server
# (e.g. in restricted environments). The agent then falls back to the
# in-process pantry tools that use session state.
ENABLE_MCP: bool = os.getenv("MEALMATE_ENABLE_MCP", "true").lower() in ("1", "true")
PANTRY_DB_PATH: str = os.getenv(
    "MEALMATE_PANTRY_DB", os.path.join(os.path.expanduser("~"), ".mealmate_pantry.json")
)
