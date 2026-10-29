# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""ObservabilityPlugin: structured JSON logs and per-invocation metrics.

Complements ADK's built-in OpenTelemetry spans (exported to Cloud Trace on
Agent Runtime) with the "logs" and "metrics" pillars from the course's
Agent Quality whitepaper:

* one JSON log line per model call, tool call and invocation
  (intent before an action, outcome after it);
* per-invocation counters: LLM calls, tool calls, tool errors, prompt /
  completion tokens, wall-clock latency;
* a running summary in session state (``temp:metrics``) for debugging.

On Cloud Run / Agent Runtime, stdout JSON lines are parsed by Cloud Logging
automatically, so these become queryable log-based metrics.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins import BasePlugin

log = logging.getLogger("mealmate.observability")


def _emit(event: str, **fields: Any) -> None:
    log.info(json.dumps({"event": event, **fields}, default=str))


class ObservabilityPlugin(BasePlugin):
    """Emits structured logs and aggregates token / latency metrics."""

    def __init__(self, name: str = "mealmate_observability") -> None:
        super().__init__(name=name)
        self._runs: dict[str, dict[str, Any]] = {}
        self._tool_started: dict[str, float] = {}
        self._model_started: dict[str, float] = {}

    def _run(self, invocation_id: str) -> dict[str, Any]:
        return self._runs.setdefault(
            invocation_id,
            {
                "started": time.perf_counter(),
                "llm_calls": 0,
                "tool_calls": 0,
                "tool_errors": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "tools": [],
            },
        )

    async def before_run_callback(self, *, invocation_context: Any) -> None:
        self._run(invocation_context.invocation_id)
        _emit(
            "invocation_start",
            invocation_id=invocation_context.invocation_id,
            session_id=invocation_context.session.id,
            agent=invocation_context.agent.name,
        )
        return None

    async def after_run_callback(self, *, invocation_context: Any) -> None:
        run = self._runs.pop(invocation_context.invocation_id, None)
        if run is None:
            return None
        latency_ms = round((time.perf_counter() - run.pop("started")) * 1000)
        _emit(
            "invocation_end",
            invocation_id=invocation_context.invocation_id,
            latency_ms=latency_ms,
            **run,
        )
        return None

    async def before_model_callback(
        self, *, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> LlmResponse | None:
        key = f"{callback_context.invocation_id}:{callback_context.agent_name}"
        self._model_started[key] = time.perf_counter()
        self._run(callback_context.invocation_id)["llm_calls"] += 1
        _emit("llm_request", agent=callback_context.agent_name, model=llm_request.model)
        return None

    async def after_model_callback(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> LlmResponse | None:
        key = f"{callback_context.invocation_id}:{callback_context.agent_name}"
        started = self._model_started.pop(key, None)
        usage = llm_response.usage_metadata
        prompt = getattr(usage, "prompt_token_count", 0) or 0
        completion = getattr(usage, "candidates_token_count", 0) or 0
        run = self._run(callback_context.invocation_id)
        run["prompt_tokens"] += prompt
        run["completion_tokens"] += completion
        _emit(
            "llm_response",
            agent=callback_context.agent_name,
            prompt_tokens=prompt,
            completion_tokens=completion,
            latency_ms=round((time.perf_counter() - started) * 1000)
            if started
            else None,
            error_code=llm_response.error_code,
        )
        callback_context.state["temp:metrics"] = {
            k: v for k, v in run.items() if k not in ("started",)
        }
        return None

    async def before_tool_callback(
        self, *, tool: Any, tool_args: dict[str, Any], tool_context: Any
    ) -> None:
        self._tool_started[tool_context.function_call_id or tool.name] = (
            time.perf_counter()
        )
        run = self._run(tool_context.invocation_id)
        run["tool_calls"] += 1
        run["tools"].append(tool.name)
        _emit(
            "tool_call",
            tool=tool.name,
            agent=tool_context.agent_name,
            args=list(tool_args),
        )
        return None

    async def after_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
        result: dict[str, Any],
    ) -> None:
        started = self._tool_started.pop(
            tool_context.function_call_id or tool.name, None
        )
        status = result.get("status") if isinstance(result, dict) else None
        if status == "error":
            self._run(tool_context.invocation_id)["tool_errors"] += 1
        _emit(
            "tool_result",
            tool=tool.name,
            status=status,
            latency_ms=round((time.perf_counter() - started) * 1000)
            if started
            else None,
        )
        return None

    async def on_tool_error_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
        error: Exception,
    ) -> dict[str, Any] | None:
        self._run(tool_context.invocation_id)["tool_errors"] += 1
        _emit(
            "tool_exception",
            tool=tool.name,
            error=type(error).__name__,
            detail=str(error)[:300],
        )
        # Turn crashes into an actionable message so the agent can recover.
        return {
            "status": "error",
            "error_message": f"{tool.name} failed ({type(error).__name__}). Try again or continue without it.",
        }
