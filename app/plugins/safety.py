# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""SafetyPlugin: app-wide input screening and output PII redaction.

Layered defence (course "Vibe Coding Agent Security & Evaluation"):
1. Deterministic input screen for prompt-injection / jailbreak patterns
   (``before_model_callback``) - cheap, predictable, runs before any LLM call.
2. Output PII scrubbing (``after_model_callback``) - masks e-mails, phone and
   card numbers so they never reach logs or the UI.
3. In the cloud, Model Armor floor settings add a managed classifier on top.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins import BasePlugin
from google.genai import types

log = logging.getLogger("mealmate.safety")

INJECTION_PATTERNS = [
    r"ignore (all|any|the)? ?(previous|prior|above) (instructions|prompts|rules)",
    r"disregard (your|the) (system|previous) (prompt|instructions)",
    r"(reveal|print|show|leak) (your|the) (system prompt|instructions|credentials|api key|secrets?)",
    r"you are now (dan|developer mode|unrestricted)",
    r"act as (an? )?(unfiltered|jailbroken)",
]
_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

PII_PATTERNS = {
    "EMAIL": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "CARD": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "PHONE": re.compile(r"(?<!\w)\+?\d[\d\s-]{7,}\d(?!\w)"),
}

REFUSAL = (
    "I can only help with meal planning, recipes, pantry and grocery lists. "
    "I can't change my instructions or share internal details."
)


def detect_injection(text: str) -> bool:
    """Returns True when text matches a known prompt-injection pattern."""
    return bool(_INJECTION_RE.search(text or ""))


def redact_pii(text: str) -> tuple[str, int]:
    """Masks e-mails, card and phone numbers. Returns (text, redaction_count)."""
    count = 0
    for label, pattern in PII_PATTERNS.items():
        text, n = pattern.subn(f"[{label} REDACTED]", text)
        count += n
    return text, count


def _last_user_text(llm_request: LlmRequest) -> str:
    for content in reversed(llm_request.contents or []):
        if content.role == "user" and content.parts:
            texts = [p.text for p in content.parts if getattr(p, "text", None)]
            if texts:
                return " ".join(texts)
    return ""


class SafetyPlugin(BasePlugin):
    """Blocks prompt-injection attempts and scrubs PII from model output."""

    def __init__(self, name: str = "mealmate_safety") -> None:
        super().__init__(name=name)

    async def before_model_callback(
        self, *, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> LlmResponse | None:
        text = _last_user_text(llm_request)
        if detect_injection(text):
            log.warning(
                '{"event": "guardrail_block", "reason": "prompt_injection", "agent": "%s"}',
                callback_context.agent_name,
            )
            callback_context.state["temp:guardrail_blocked"] = True
            return LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=REFUSAL)])
            )
        return None

    async def after_model_callback(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> LlmResponse | None:
        content = llm_response.content
        if not content or not content.parts:
            return None
        changed = 0
        for part in content.parts:
            if getattr(part, "text", None):
                part.text, n = redact_pii(part.text)
                changed += n
        if changed:
            log.info('{"event": "pii_redacted", "count": %d}', changed)
            return llm_response
        return None

    async def before_tool_callback(
        self, *, tool: Any, tool_args: dict[str, Any], tool_context: Any
    ) -> dict[str, Any] | None:
        # Defence in depth: tool arguments are model-generated, so screen them too.
        for value in tool_args.values():
            if isinstance(value, str) and detect_injection(value):
                return {"status": "error", "error_message": "Blocked by safety policy."}
        return None
