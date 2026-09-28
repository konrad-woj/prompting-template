"""Offline multi-turn support conversation with a scripted model.

Shows sticky skill activation, the verification and confirmation gates, a retried
refund, and a fixed rate-limit message sent without a model call.

Run:
    uv run python -m examples.support_agent.run_mock
"""

import asyncio
import logging
from pathlib import Path

import yaml

from examples.scripted_model import ScriptedModel, call, say
from examples.support_agent.backend import SupportBackend
from prompt_kit import ErrorKind, PromptSession, Registry, ToolError, ToolExecutor
from prompt_kit.adapters.openai import ChatLoop

PROMPTS_DIR = Path(__file__).parent / "prompts"
logger = logging.getLogger("support_mock")

SCRIPT = [
    say("I can help with that. What's the email address you used for the order?"),
    call("verify_customer", order_id="ORD-1042", email="bob@example.com"),
    call("lookup_order", order_id="ORD-1042"),
    call("issue_refund", order_id="ORD-1042", amount=42.0),
    say(
        "Done - your refund of 42.00 EUR for order ORD-1042 is on its way and should reach you within 5 business days."
    ),
    call(
        "send_email",
        subject="Your refund for ORD-1042",
        body="We've refunded 42.00 EUR for order ORD-1042.",
    ),
]

CONVERSATION = [
    ("Hi, I'd like a refund for order ORD-1042.", "refund_request"),
    ("bob@example.com", "refund_request"),
    ("yes", "refund_request"),
    ("Could you email me a summary?", "email_request"),
    ("yes", "email_request"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    registry = Registry.load(PROMPTS_DIR)
    config = yaml.safe_load((PROMPTS_DIR / "config.yaml").read_text())
    session = PromptSession(registry, persona="support_agent", config=config)
    backend = SupportBackend(
        fail_next={
            "issue_refund": [ToolError(ErrorKind.UNAVAILABLE)],
            "send_email": [ToolError(ErrorKind.RATE_LIMITED, retry_after_seconds=30)],
        }
    )
    model = ScriptedModel(SCRIPT)
    loop = ChatLoop(
        session, ToolExecutor(session, backend.implementations()), model.complete
    )

    for user_text, intent in CONVERSATION:
        logger.info("user      > %s", user_text)
        reply = await loop.send(user_text, intent=intent)
        logger.info(
            "assistant > %s   [skills: %s]\n", reply, ", ".join(session.active_skills)
        )

    logger.info(
        "system prompt identical across all %d model calls: %s",
        len(model.system_prompts),
        len(set(model.system_prompts)) == 1,
    )
    late_skill_messages = [
        message
        for message in loop.messages
        if message["role"] == "user" and "<skill" in message["content"]
    ]
    logger.info(
        "skills added after the first turn arrived in %d user message(s)",
        len(late_skill_messages),
    )


if __name__ == "__main__":
    asyncio.run(main())
