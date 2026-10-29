# Copyright 2026 Albert Elias
# SPDX-License-Identifier: Apache-2.0
"""End-to-end CLI demo of MealMate, including the human-approval pause.

Usage:
    uv run python scripts/demo.py            # interactive approval prompt
    uv run python scripts/demo.py --approve  # auto-approve (CI / recording)

It runs the same ``App`` as ``adk web`` / Agent Runtime, with a persistent
SQLite session store and an in-memory memory service, and walks through:
profile -> weekly plan -> grocery order (pause, approve, resume) -> recall.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "WARNING"))

from app.agent import app  # noqa: E402

USER_ID = "demo-family"
CONVERSATION = [
    (
        "Hi! We're a family of 4. We eat halal, my son is allergic to peanuts and "
        "we avoid shellfish. Budget is 700 QAR a week and I can cook at most 45 "
        "minutes. We already have olive oil, basmati rice and cumin at home."
    ),
    "Great, please plan our week.",
    "Looks good - please order the groceries for evening delivery.",
]


def _print_event(event) -> tuple[str | None, str | None]:
    """Prints agent text and returns (confirmation_call_id, hint) if paused."""
    if not event.content or not event.content.parts:
        return None, None
    for part in event.content.parts:
        if part.text and not event.partial:
            print(f"\n[{event.author}] {part.text.strip()}")
        call = part.function_call
        if call and call.name == "adk_request_confirmation":
            hint = (call.args or {}).get("toolConfirmation", {}).get("hint")
            return call.id, hint
    return None, None


async def _send(
    runner: Runner, session_id: str, message: types.Content, invocation_id=None
):
    pending = None
    last_invocation = invocation_id
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=message,
        invocation_id=invocation_id,
    ):
        last_invocation = event.invocation_id or last_invocation
        call_id, hint = _print_event(event)
        if call_id:
            pending = (call_id, hint, last_invocation)
    return pending


async def main(auto_approve: bool) -> None:
    db_path = Path(".adk") / "demo_sessions.db"
    db_path.parent.mkdir(exist_ok=True)
    runner = Runner(
        app=app,
        session_service=DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{db_path}"),
        memory_service=InMemoryMemoryService(),
    )
    session = await runner.session_service.create_session(
        app_name=app.name, user_id=USER_ID
    )
    print(f"Session {session.id} (SQLite: {db_path})")

    for text in CONVERSATION:
        print(f"\n[user] {text}")
        pending = await _send(
            runner,
            session.id,
            types.Content(role="user", parts=[types.Part(text=text)]),
        )
        while pending:
            call_id, hint, invocation_id = pending
            print(f"\n*** APPROVAL NEEDED: {hint}")
            approved = auto_approve or input("Approve? [y/N] ").strip().lower() == "y"
            print(f"[user] {'approved' if approved else 'declined'}")
            reply = types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call_id,
                            name="adk_request_confirmation",
                            response={"confirmed": approved},
                        )
                    )
                ],
            )
            pending = await _send(
                runner, session.id, reply, invocation_id=invocation_id
            )

    # A brand-new session for the same user still knows the household profile
    # (user:-scoped state) and can recall the last conversation (memory).
    session2 = await runner.session_service.create_session(
        app_name=app.name, user_id=USER_ID
    )
    question = "New week! Remind me of our allergies and budget, and what did we order last time?"
    print(f"\n--- new session {session2.id} ---\n[user] {question}")
    await _send(
        runner,
        session2.id,
        types.Content(role="user", parts=[types.Part(text=question)]),
    )
    await runner.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve", action="store_true", help="auto-approve the order")
    asyncio.run(main(parser.parse_args().approve))
