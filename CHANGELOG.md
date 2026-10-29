# Changelog

All notable changes to MealMate are documented here (Keep a Changelog format).

## [0.1.0] - 2026-10-29

### Added
- Multi-agent MealMate concierge: coordinator, profile agent, and a weekly
  planning pipeline (parallel recipe scouts, menu planner, critic/refiner loop,
  shopping-list agent).
- Function tools for recipe search, nutrition and allergen checks, costed
  shopping lists, household profile, ratings, and human-approved grocery orders.
- Self-hosted Pantry MCP server consumed through `McpToolset` with a tool allow-list.
- Long-term memory (`add_session_to_memory`, `preload_memory`, `load_memory`),
  user-scoped state, SQLite sessions in the demo, and event compaction.
- SafetyPlugin (prompt-injection screen, PII redaction), allergy policy callback,
  and ObservabilityPlugin (structured JSON logs and token/latency metrics).
- Unit tests, integration tests, ADK evalset with trajectory and rubric judges,
  agents-cli eval dataset, and load test.
- CI (lint, tests, Bandit, pip-audit, gitleaks, MCP smoke test), PR eval gate,
  staging and production deployment to Agent Runtime, and Terraform with WIF.
