"""Interactive support agent against Google Gemini through its OpenAI-compatible endpoint.

Uses the support example's prompts and in-memory backend. Intent is picked by a keyword
table so skill routing stays deterministic; swap in your own classifier.

Run (the key is read from the environment; --env-file loads it from .env):
    uv run --extra live --env-file .env python -m examples.live_gemini.loop
    uv run --extra live --env-file .env python -m examples.live_gemini.loop --model gemini-2.5-pro
"""

import argparse
import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import yaml
from openai import AsyncOpenAI

from examples.support_agent.backend import SupportBackend
from prompt_kit import PromptSession, Registry, ToolExecutor
from prompt_kit.adapters.openai import ChatLoop, Message

PROMPTS_DIR = Path(__file__).parents[1] / "support_agent" / "prompts"
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_MODEL = "gemini-2.5-flash"
INTENT_KEYWORDS = {
    "refund_request": ("refund", "money back", "return"),
    "email_request": ("email", "e-mail", "in writing"),
    "order_status": ("status", "where is", "tracking", "order"),
}
logger = logging.getLogger("live_gemini")


def classify_intent(text: str, current_intent: str) -> str:
    lowered = text.lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return intent
    return current_intent


async def main(model: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    registry = Registry.load(PROMPTS_DIR)
    config = yaml.safe_load((PROMPTS_DIR / "config.yaml").read_text())
    session = PromptSession(registry, persona="support_agent", config=config)

    async with AsyncOpenAI(
        api_key=os.environ["GEMINI_API_KEY"], base_url=GEMINI_OPENAI_BASE_URL
    ) as client:

        async def complete(
            messages: list[Message], tools: list[dict[str, Any]]
        ) -> Message:
            response = await client.chat.completions.create(
                model=model, messages=messages, tools=tools
            )
            usage = response.usage
            cached_tokens = (
                usage.prompt_tokens_details.cached_tokens
                if usage and usage.prompt_tokens_details
                else 0
            )
            if usage:
                logger.info(
                    "  [prompt tokens %d, cached %s]",
                    usage.prompt_tokens,
                    cached_tokens,
                )
            # Keep only the fields the API accepts back in history.
            return response.choices[0].message.model_dump(
                include={"role", "content", "tool_calls"}, exclude_none=True
            )

        executor = ToolExecutor(session, SupportBackend().implementations())
        # Gemini's compatibility layer has no strict function-calling mode.
        loop = ChatLoop(session, executor, complete, strict_tools=False)
        intent = "default"
        logger.info(
            "Model %s. Try: 'I want a refund for ORD-1042' (email bob@example.com). Empty line quits.",
            model,
        )
        while user_text := (await asyncio.to_thread(input, "you > ")).strip():
            intent = classify_intent(user_text, intent)
            logger.info("agent > %s", await loop.send(user_text, intent=intent))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", default=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    )
    asyncio.run(main(parser.parse_args().model))
