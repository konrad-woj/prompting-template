from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from prompt_kit import PromptSession, Registry

REPOSITORY_ROOT = Path(__file__).parents[1]
EXAMPLE_PROMPT_DIRS = {
    "starter": REPOSITORY_ROOT / "prompts",
    "support_agent": REPOSITORY_ROOT / "examples" / "support_agent" / "prompts",
    "research_agent": REPOSITORY_ROOT / "examples" / "research_agent" / "prompts",
}

MINIMAL_PROMPTS = {
    "core/base_rules.md": "---\nname: base_rules\n---\nBe concise.",
    "guardrails/global.md": "---\nname: global\n---\nNo secrets.",
    "personas/agent.md": """
        ---
        name: agent
        description: Test persona.
        allowed_tools: [read_thing, change_thing]
        ---
        You are {{agent_name}}.
        """,
    "skills/reading.md": """
        ---
        name: reading
        description: Read things.
        requires_tools: [read_thing]
        includes: [tool_errors]
        priority: 10
        ---
        Read carefully.
        """,
    "skills/changing.md": """
        ---
        name: changing
        description: Change things.
        requires_tools: [change_thing]
        includes: [tool_errors]
        priority: 5
        ---
        Change carefully.
        """,
    "skills/fallback.md": "---\nname: fallback\ndescription: Fallback.\n---\nHelp generally.",
    "errors/tool_errors.md": "---\nname: tool_errors\n---\nHandle tool errors.",
    "errors/busy.md": "---\nname: busy\nmode: fixed\ntrigger_kinds: [rate_limited]\n---\nBusy, retry in {{retry_after_seconds}}s.",
    "confirmations/confirm_change_thing.md": (
        "---\nname: confirm_change_thing\nmode: fixed\ntrigger_kinds: [confirm_change_thing]\n---\nChange {{thing_id}}?"
    ),
    "tools/read_thing.md": """
        ---
        name: read_thing
        input_schema:
          type: object
          properties:
            thing_id: {type: string}
          required: [thing_id]
          additionalProperties: false
        timeout_seconds: 1
        max_retries: 2
        retry_on: [timeout, unavailable]
        ---
        Reads a thing.
        """,
    "tools/change_thing.md": """
        ---
        name: change_thing
        input_schema:
          type: object
          properties:
            thing_id: {type: string}
          required: [thing_id]
          additionalProperties: false
        timeout_seconds: 1
        max_retries: 1
        retry_on: [unavailable]
        side_effect: true
        requires_confirmation: true
        ---
        Changes a thing.
        """,
    "routing.yaml": """
        agent:
          read: [reading]
          change: [changing]
          default: [fallback]
        """,
}


def write_prompts(root: Path, files: dict[str, str | None]) -> Path:
    """Writes MINIMAL_PROMPTS overridden by `files` (None deletes a file) under `root`."""
    for relative_path, content in {**MINIMAL_PROMPTS, **files}.items():
        if content is None:
            continue
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(content).strip() + "\n")
    return root


@pytest.fixture
def make_registry(tmp_path: Path):
    def factory(files: dict[str, str | None] | None = None) -> Registry:
        return Registry.load(write_prompts(tmp_path / "prompts", files or {}))

    return factory


@pytest.fixture
def session(make_registry) -> PromptSession:
    return PromptSession(make_registry(), persona="agent", config={"agent_name": "Ava"})


def load_example_config(prompts_dir: Path) -> dict:
    return yaml.safe_load((prompts_dir / "config.yaml").read_text())
