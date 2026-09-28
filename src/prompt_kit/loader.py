"""Loads a `prompts/` directory into a Registry.

Example:
    registry = Registry.load(Path("prompts"))
    registry.skills["refund_processing"].body
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from prompt_kit.models import PartialMeta, PersonaMeta, SkillMeta, ToolMeta, UnitMeta

FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?\n)---\s*\n(.*)\Z", re.DOTALL)

# Partials are everything a skill may pull in via `includes:` or the runtime may look up
# by trigger kind; the separate directories exist for human organization only.
PARTIAL_DIRECTORIES = ("fragments", "errors", "refusals", "confirmations")

Routing = dict[str, dict[str, list[str]]]


class PromptLoadError(Exception):
    pass


@dataclass(frozen=True)
class PromptUnit[MetaT: UnitMeta]:
    path: Path
    meta: MetaT
    body: str

    @property
    def name(self) -> str:
        return self.meta.name


def load_unit[MetaT: UnitMeta](
    path: Path, meta_model: type[MetaT]
) -> PromptUnit[MetaT]:
    match = FRONTMATTER_PATTERN.match(path.read_text(encoding="utf-8"))
    if not match:
        raise PromptLoadError(f"{path}: missing YAML frontmatter")
    raw_meta, body = match.groups()
    try:
        meta = meta_model.model_validate(yaml.safe_load(raw_meta) or {})
    except ValidationError as error:
        raise PromptLoadError(f"{path}: invalid frontmatter\n{error}") from error
    if meta.name != path.stem:
        raise PromptLoadError(
            f"{path}: name '{meta.name}' must match the file name '{path.stem}'"
        )
    return PromptUnit(path=path, meta=meta, body=body.strip())


def load_directory[MetaT: UnitMeta](
    directory: Path, meta_model: type[MetaT]
) -> dict[str, PromptUnit[MetaT]]:
    if not directory.is_dir():
        return {}
    units = (load_unit(path, meta_model) for path in sorted(directory.glob("*.md")))
    return {unit.name: unit for unit in units}


@dataclass(frozen=True)
class Registry:
    root: Path
    core: dict[str, PromptUnit[UnitMeta]]
    guardrails: dict[str, PromptUnit[UnitMeta]]
    personas: dict[str, PromptUnit[PersonaMeta]]
    skills: dict[str, PromptUnit[SkillMeta]]
    tools: dict[str, PromptUnit[ToolMeta]]
    partials_by_directory: dict[str, dict[str, PromptUnit[PartialMeta]]]
    routing: Routing = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path) -> "Registry":
        routing_path = root / "routing.yaml"
        routing = (
            yaml.safe_load(routing_path.read_text(encoding="utf-8"))
            if routing_path.exists()
            else {}
        )
        return cls(
            root=root,
            core=load_directory(root / "core", UnitMeta),
            guardrails=load_directory(root / "guardrails", UnitMeta),
            personas=load_directory(root / "personas", PersonaMeta),
            skills=load_directory(root / "skills", SkillMeta),
            tools=load_directory(root / "tools", ToolMeta),
            partials_by_directory={
                directory: load_directory(root / directory, PartialMeta)
                for directory in PARTIAL_DIRECTORIES
            },
            routing=routing or {},
        )

    @property
    def partials(self) -> dict[str, PromptUnit[PartialMeta]]:
        merged: dict[str, PromptUnit[PartialMeta]] = {}
        for units in self.partials_by_directory.values():
            merged.update(units)
        return merged

    def fixed_partial_for_kind(self, kind: str) -> PromptUnit[PartialMeta] | None:
        for unit in self.partials.values():
            if unit.meta.mode == "fixed" and kind in unit.meta.trigger_kinds:
                return unit
        return None

    def skills_for(self, persona: str, intent: str) -> list[str]:
        routes = self.routing.get(persona, {})
        return routes.get(intent, routes.get("default", []))
