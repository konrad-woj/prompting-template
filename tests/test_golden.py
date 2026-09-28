"""Snapshot of every routed system prompt, so any prompt edit shows up as a reviewable diff.

Regenerate after an intended change:
    UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py
"""

import os
from pathlib import Path

import pytest

from prompt_kit import PromptSession, Registry, validate
from tests.conftest import EXAMPLE_PROMPT_DIRS, load_example_config

GOLDEN_DIR = Path(__file__).parent / "golden"


def routed_cases() -> list[tuple[str, str, str]]:
    return [
        (example, persona, intent)
        for example, prompts_dir in EXAMPLE_PROMPT_DIRS.items()
        for persona, routes in Registry.load(prompts_dir).routing.items()
        for intent in routes
    ]


@pytest.mark.parametrize("example", EXAMPLE_PROMPT_DIRS)
def test_example_prompts_are_valid(example):
    prompts_dir = EXAMPLE_PROMPT_DIRS[example]

    assert validate(Registry.load(prompts_dir), load_example_config(prompts_dir)) == []


@pytest.mark.parametrize(("example", "persona", "intent"), routed_cases())
def test_rendered_prompt_matches_snapshot(example, persona, intent):
    prompts_dir = EXAMPLE_PROMPT_DIRS[example]
    session = PromptSession(
        Registry.load(prompts_dir), persona, load_example_config(prompts_dir)
    )
    session.activate(intent)
    snapshot = GOLDEN_DIR / example / f"{persona}__{intent}.txt"

    if os.environ.get("UPDATE_GOLDEN"):
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(session.system_prompt())

    assert session.system_prompt() == snapshot.read_text()
