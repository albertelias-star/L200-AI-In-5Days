# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""MealMate: a multi-agent family meal-planning and grocery concierge.

Architecture (see README.md for the diagram):

    mealmate (coordinator, LlmAgent, smart model)
      |- AgentTool(profile_agent)            household profile + pantry (MCP)
      |- AgentTool(weekly_plan_pipeline)     SequentialAgent
      |     |- recipe_scouts                 ParallelAgent: breakfast/lunch/dinner
      |     |- menu_planner                  LlmAgent -> state["draft_menu"]
      |     |- menu_quality_loop             LoopAgent: critic <-> refiner
      |     |- shopping_list_agent           LlmAgent -> costed list
      |- place_grocery_order                 human-in-the-loop (request_confirmation)
      |- rate_recipe, load/preload memory, pantry tools

Why multi-agent here (the course warns against it by default):
  * the three scouts are genuinely parallel and independent;
  * the critic/refiner loop is an adversarial check-and-balance;
  * workers run on a cheaper model than the planner (model routing).
"""

from __future__ import annotations

import os

import google.auth
from google.adk.agents import Agent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.apps import App
from google.adk.apps.app import EventsCompactionConfig, ResumabilityConfig
from google.adk.models import Gemini
from google.adk.tools import AgentTool, exit_loop, load_memory, preload_memory
from google.auth.exceptions import DefaultCredentialsError

from app import config, prompts
from app.callbacks import enforce_allergy_policy, save_session_to_memory
from app.plugins import ObservabilityPlugin, SafetyPlugin
from app.tools import (
    build_shopping_list,
    check_allergens,
    check_menu_nutrition,
    get_household_profile,
    pantry_tools,
    place_grocery_order,
    rate_recipe,
    save_household_profile,
    search_recipes,
)

# --- Platform configuration ---------------------------------------------------
# Gemini on Agent Platform (Vertex AI) with Application Default Credentials.
# Set GEMINI_API_KEY instead to use Google AI Studio for local experiments.
if not os.environ.get("GEMINI_API_KEY"):
    try:
        _, _project_id = google.auth.default()
        if _project_id:
            os.environ.setdefault("GOOGLE_CLOUD_PROJECT", _project_id)
    except DefaultCredentialsError:
        pass
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
    os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", "True")


def _model(name: str) -> Gemini:
    return Gemini(model=name, retry_options=config.RETRY_OPTIONS)


# --- Specialist agents ---------------------------------------------------------
profile_agent = Agent(
    name="profile_agent",
    model=_model(config.FAST_MODEL),
    description="Collects and saves the household's food profile and pantry contents.",
    instruction=prompts.PROFILE,
    tools=[save_household_profile, get_household_profile, *pantry_tools()],
)


def _scout(meal: str) -> Agent:
    return Agent(
        name=f"{meal}_scout",
        model=_model(config.FAST_MODEL),
        description=f"Shortlists {meal} recipes that fit the household profile.",
        instruction=prompts.SCOUT.format(meal=meal),
        tools=[search_recipes],
        output_key=f"{meal}_options",
    )


recipe_scouts = ParallelAgent(
    name="recipe_scouts",
    description="Scouts breakfast, lunch and dinner options concurrently.",
    sub_agents=[_scout("breakfast"), _scout("lunch"), _scout("dinner")],
)

menu_planner = Agent(
    name="menu_planner",
    model=_model(config.SMART_MODEL),
    description="Composes a varied 7-day menu from the scouted options.",
    instruction=prompts.PLANNER,
    output_key="draft_menu",
)

menu_critic = Agent(
    name="menu_critic",
    model=_model(config.FAST_MODEL),
    description="Checks the draft menu for allergens and nutrition balance.",
    instruction=prompts.CRITIC,
    tools=[check_allergens, check_menu_nutrition],
    output_key="critique",
)

menu_refiner = Agent(
    name="menu_refiner",
    model=_model(config.SMART_MODEL),
    description="Applies the critic's swaps, or ends the loop when approved.",
    instruction=prompts.REFINER,
    tools=[exit_loop],
    output_key="draft_menu",
)

menu_quality_loop = LoopAgent(
    name="menu_quality_loop",
    description="Critic/refiner loop that iterates until the menu is safe and balanced.",
    sub_agents=[menu_critic, menu_refiner],
    max_iterations=config.MAX_LOOP_ITERATIONS,
)

shopping_list_agent = Agent(
    name="shopping_list_agent",
    model=_model(config.FAST_MODEL),
    description="Turns the approved menu into a costed shopping list.",
    instruction=prompts.SHOPPER,
    tools=[build_shopping_list, *pantry_tools()],
    before_tool_callback=enforce_allergy_policy,
    output_key="final_plan",
)

weekly_plan_pipeline = SequentialAgent(
    name="weekly_plan_pipeline",
    description=(
        "Plans a full week: parallel recipe scouting, menu drafting, a "
        "nutrition/allergen review loop and a costed shopping list."
    ),
    sub_agents=[recipe_scouts, menu_planner, menu_quality_loop, shopping_list_agent],
)

# --- Coordinator ----------------------------------------------------------------
root_agent = Agent(
    # Keep in sync with create_params.root_agent_name in agents-cli-manifest.yaml:
    # telemetry reports this name as gen_ai.agent.name.
    name="mealmate",
    model=_model(config.SMART_MODEL),
    description="Family meal-planning and grocery concierge.",
    instruction=prompts.COORDINATOR,
    tools=[
        AgentTool(agent=profile_agent),
        AgentTool(agent=weekly_plan_pipeline),
        place_grocery_order,
        rate_recipe,
        get_household_profile,
        preload_memory,
        load_memory,
        *pantry_tools(),
    ],
    before_tool_callback=enforce_allergy_policy,
    after_agent_callback=save_session_to_memory,
)

app = App(
    name="app",
    root_agent=root_agent,
    plugins=[SafetyPlugin(), ObservabilityPlugin()],
    # Day 3a: summarise older turns so long conversations stay cheap and fast.
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=config.COMPACTION_INTERVAL,
        overlap_size=config.COMPACTION_OVERLAP,
    ),
    # Day 2b: lets place_grocery_order pause for approval and resume.
    resumability_config=ResumabilityConfig(is_resumable=True),
)
