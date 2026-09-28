"""`prompt-kit` command line: validate, render, compile-tools.

Example:
    prompt-kit validate --root prompts --config prompts/config.yaml
    prompt-kit render --root prompts --config prompts/config.yaml --persona assistant --intent default
    prompt-kit compile-tools --root prompts --out build/tools.json
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

from prompt_kit.adapters.openai import to_openai_tools
from prompt_kit.loader import PromptLoadError, Registry
from prompt_kit.session import PromptSession
from prompt_kit.validate import validate

logger = logging.getLogger("prompt_kit")


def load_config(path: Path | None) -> dict[str, Any] | None:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {} if path else None


def run_validate(registry: Registry, config: dict[str, Any] | None) -> int:
    problems = validate(registry, config)
    for problem in problems:
        logger.error(problem)
    if problems:
        logger.error("%d problem(s) in %s", len(problems), registry.root)
        return 1
    logger.info("OK: %s is valid", registry.root)
    return 0


def run_render(
    registry: Registry, config: dict[str, Any], persona: str, intents: list[str]
) -> int:
    session = PromptSession(registry, persona=persona, config=config)
    for intent in intents:
        session.activate(intent)
    sys.stdout.write(session.system_prompt() + "\n")
    return 0


def run_compile_tools(registry: Registry, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(to_openai_tools(list(registry.tools.values())), indent=2) + "\n"
    )
    logger.info("wrote %d tool schemas to %s", len(registry.tools), output_path)
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="prompt-kit")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "render", "compile-tools"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--root", type=Path, default=Path("prompts"))
        if command != "compile-tools":
            subparser.add_argument(
                "--config", type=Path, help="YAML file with trusted prompt variables"
            )
    subparsers.choices["render"].add_argument("--persona", required=True)
    subparsers.choices["render"].add_argument(
        "--intent",
        action="append",
        default=[],
        help="Repeat to simulate a session activating several intents",
    )
    subparsers.choices["compile-tools"].add_argument(
        "--out", type=Path, default=Path("build/tools.json")
    )
    args = parser.parse_args()

    try:
        registry = Registry.load(args.root)
    except PromptLoadError as error:
        logger.error("%s", error)
        sys.exit(1)

    if args.command == "validate":
        sys.exit(run_validate(registry, load_config(args.config)))
    if args.command == "render":
        sys.exit(
            run_render(
                registry,
                load_config(args.config) or {},
                args.persona,
                args.intent or ["default"],
            )
        )
    sys.exit(run_compile_tools(registry, args.out))
