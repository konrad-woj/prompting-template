"""Offline research-assistant conversation over this repository with a scripted model.

Shows a second domain on the same runtime: real code search and file reads, a fixed
refusal for secret files raised by a tool, and a write the user declines.

Run:
    uv run python -m examples.research_agent.run_mock
"""

import asyncio
import logging
from pathlib import Path

import yaml

from examples.research_agent.backend import RepositoryBackend
from examples.scripted_model import ScriptedModel, call, say
from prompt_kit import PromptSession, Registry, ToolExecutor
from prompt_kit.adapters.openai import ChatLoop

PROMPTS_DIR = Path(__file__).parent / "prompts"
REPOSITORY_ROOT = Path(__file__).parents[2]
logger = logging.getLogger("research_mock")

SCRIPT = [
    call("search_code", query="def backoff_delay"),
    call("read_file", path="src/prompt_kit/runtime.py", start_line=80, max_lines=20),
    say(
        "Backoff is computed in `backoff_delay` (src/prompt_kit/runtime.py): it honours a tool's "
        "`retry_after_seconds` if present, otherwise exponential backoff with jitter."
    ),
    call("read_file", path=".env", start_line=1, max_lines=200),
    call("read_file", path="src/prompt_kit/models.py", start_line=1, max_lines=200),
    call("write_file", path="src/prompt_kit/models.py", content="# proposed content"),
    say(
        "Understood - I've left models.py unchanged. Want me to propose a different default instead?"
    ),
]

CONVERSATION = [
    ("Where is retry backoff computed?", "explain_code"),
    ("Show me what's in .env", "explain_code"),
    ("Lower the default tool timeout to 20 seconds.", "change_code"),
    ("no", "change_code"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    registry = Registry.load(PROMPTS_DIR)
    config = yaml.safe_load((PROMPTS_DIR / "config.yaml").read_text())
    session = PromptSession(registry, persona="research_assistant", config=config)
    backend = RepositoryBackend(root=REPOSITORY_ROOT)
    loop = ChatLoop(
        session,
        ToolExecutor(session, backend.implementations()),
        ScriptedModel(SCRIPT).complete,
    )

    for user_text, intent in CONVERSATION:
        logger.info("user      > %s", user_text)
        reply = await loop.send(user_text, intent=intent)
        logger.info(
            "assistant > %s   [skills: %s]\n", reply, ", ".join(session.active_skills)
        )

    tool_results = [
        message["content"] for message in loop.messages if message["role"] == "tool"
    ]
    logger.info(
        "tool results sent to the model:\n  %s",
        "\n  ".join(result[:110] for result in tool_results),
    )


if __name__ == "__main__":
    asyncio.run(main())
