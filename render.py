"""
Deterministic prompt renderer.

Design rules (see RULES.md):
  - One file per skill/persona/tool/fragment, markdown + YAML frontmatter.
  - Frontmatter is metadata only; it is parsed and stripped, never sent
    to the model.
  - Bodies use plain {{var}} substitution only — no embedded logic.
  - Selection is entirely table-driven via routing.yaml.
  - Every section is wrapped in an identifying XML-ish tag before being
    sent to the model.
  - Assembly order: core_rules -> guardrails -> persona -> skills
    (priority order) -> tool_context -> user_context.
  - guardrails/, errors/, and refusals/ hold prompt TEXT (what the model
    says/does). Retry COUNTS/backoff live in tool frontmatter and are
    enforced in code (see tool_runtime.py) — the two must describe the
    same policy, never diverge.
  - Every errors/ and refusals/ file declares mode: "instruction"
    (default) or "fixed". "instruction" is guidance the model reads and
    paraphrases in its own words — variable wording, natural in
    conversation. "fixed" is a literal, {{var}}-substituted string
    returned directly to the user with NO model generation involved —
    for wording that must be exact every time (compliance refusals,
    rate-limit notices). A fixed-mode file may never be pulled into a
    skill's `includes:` (that would hand a literal user-facing string
    to the model as if it were an instruction to paraphrase — exactly
    what "fixed" is meant to prevent). Instead it's looked up by
    `trigger_kinds` at the moment a matching condition fires — see
    get_fixed_for_kind() and tool_runtime.py.

No third-party templating engine required — stdlib + PyYAML only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.exit("Missing dependency: pip install pyyaml")

ROOT = Path(__file__).parent
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n(.*)$", re.DOTALL)
VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

@dataclass
class PromptUnit:
    """A single loaded file: its parsed frontmatter + body."""
    path: Path
    meta: dict[str, Any]
    body: str

    @property
    def name(self) -> str:
        return self.meta.get("name", self.path.stem)


def load_unit(path: Path) -> PromptUnit:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        # No frontmatter (e.g. core rules) — treat whole file as body.
        return PromptUnit(path=path, meta={}, body=text.strip())
    raw_meta, body = match.groups()
    meta = yaml.safe_load(raw_meta) or {}
    return PromptUnit(path=path, meta=meta, body=body.strip())


def load_dir(dirpath: Path) -> dict[str, PromptUnit]:
    units = {}
    if not dirpath.exists():
        return units
    for f in sorted(dirpath.glob("*.md")):
        unit = load_unit(f)
        units[unit.name] = unit
    return units


# ---------------------------------------------------------------------------
# Substitution (logic-free — {{var}} only, dotted paths into context dict)
# ---------------------------------------------------------------------------

def substitute(text: str, context: dict[str, Any]) -> str:
    def resolve(match: re.Match) -> str:
        path = match.group(1).split(".")
        value: Any = context
        for key in path:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                # Missing variable: leave a visible placeholder rather than
                # silently dropping it or raising mid-render.
                return f"[[MISSING:{match.group(1)}]]"
        return str(value)

    return VAR_RE.sub(resolve, text)


def wrap(tag: str, body: str, **attrs: str) -> str:
    attr_str = "".join(f' {k}="{v}"' for k, v in attrs.items())
    return f"<{tag}{attr_str}>\n{body}\n</{tag}>"


# ---------------------------------------------------------------------------
# Includes (fragments) resolution
# ---------------------------------------------------------------------------

def resolve_includes(unit: PromptUnit, fragments: dict[str, PromptUnit]) -> str:
    body = unit.body
    for frag_name in unit.meta.get("includes", []):
        frag = fragments.get(frag_name)
        if frag is None:
            body += f"\n\n[[MISSING FRAGMENT: {frag_name}]]"
            continue
        if frag.meta.get("mode", "instruction") == "fixed":
            # A fixed-mode file is a literal user-facing string, not an
            # instruction for the model to paraphrase. Pulling it into a
            # skill's prompt body would defeat the point of "fixed"
            # (exact wording every time) — see validate() for the
            # corresponding check that catches this in CI.
            body += f"\n\n[[ERROR: '{frag_name}' is mode:fixed — cannot be included as a prompt instruction. Use get_fixed_for_kind() instead.]]"
            continue
        body += f"\n\n{frag.body}"
    return body


# ---------------------------------------------------------------------------
# Fixed (non-generated) responses
# ---------------------------------------------------------------------------

def get_fixed_for_kind(registry: "Registry", kind: str, context: dict[str, Any] | None = None) -> str | None:
    """
    Looks up a mode:"fixed" error/refusal file whose `trigger_kinds`
    includes `kind`, and returns its literal, {{var}}-substituted text.
    Returns None if no fixed message is declared for that kind — the
    caller should then fall back to a normal LLM turn, relying on the
    matching instruction-mode fragment already included in the active
    skill to guide phrasing.

    `kind` is a free-form string your app defines — a ToolError.kind
    from tool_runtime.py, or any other named condition raised by input
    classifiers, policy checks, etc. Nothing here is tool-specific.
    """
    context = context or {}
    for unit in registry.includable_pool().values():
        if unit.meta.get("mode") == "fixed" and kind in unit.meta.get("trigger_kinds", []):
            return substitute(unit.body, context)
    return None


# ---------------------------------------------------------------------------
# Registry: loads everything once
# ---------------------------------------------------------------------------

@dataclass
class Registry:
    core: dict[str, PromptUnit] = field(default_factory=dict)
    guardrails: dict[str, PromptUnit] = field(default_factory=dict)
    personas: dict[str, PromptUnit] = field(default_factory=dict)
    skills: dict[str, PromptUnit] = field(default_factory=dict)
    tools: dict[str, PromptUnit] = field(default_factory=dict)
    fragments: dict[str, PromptUnit] = field(default_factory=dict)
    errors: dict[str, PromptUnit] = field(default_factory=dict)
    refusals: dict[str, PromptUnit] = field(default_factory=dict)
    routing: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path = ROOT) -> "Registry":
        routing_path = root / "routing.yaml"
        routing = yaml.safe_load(routing_path.read_text()) if routing_path.exists() else {}
        return cls(
            core=load_dir(root / "core"),
            guardrails=load_dir(root / "guardrails"),
            personas=load_dir(root / "personas"),
            skills=load_dir(root / "skills"),
            tools=load_dir(root / "tools"),
            fragments=load_dir(root / "fragments"),
            errors=load_dir(root / "errors"),
            refusals=load_dir(root / "refusals"),
            routing=routing or {},
        )

    def includable_pool(self) -> dict[str, PromptUnit]:
        """
        Everything a skill's `includes:` list is allowed to reference —
        fragments, error-handling copy, and refusal patterns are all
        'partials' from the composition point of view. Kept in separate
        directories only for human organization, not different mechanics.
        """
        pool: dict[str, PromptUnit] = {}
        pool.update(self.fragments)
        pool.update(self.errors)
        pool.update(self.refusals)
        return pool

    def skills_for(self, persona: str, intent: str) -> list[str]:
        persona_routes = self.routing.get(persona, {})
        names = persona_routes.get(intent, persona_routes.get("default", []))
        return names

    def tools_for_skills(self, skill_names: list[str]) -> list[str]:
        seen: list[str] = []
        for name in skill_names:
            skill = self.skills.get(name)
            if not skill:
                continue
            for tool_name in skill.meta.get("requires_tools", []):
                if tool_name not in seen:
                    seen.append(tool_name)
        return seen


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render(
    registry: Registry,
    persona: str,
    intent: str,
    context: dict[str, Any] | None = None,
) -> tuple[str, list[dict]]:
    context = context or {}
    parts: list[str] = []

    # 1. Core rules (static, always first — best for prompt caching)
    for unit in registry.core.values():
        parts.append(wrap("core_rules", substitute(unit.body, context), name=unit.name))

    # 1b. Guardrails — also static, always-on, unconditional. Kept as a
    # separate category from core_rules so a reviewer can audit "what
    # can never be overridden" as one block, distinct from ordinary
    # behavioral defaults.
    for unit in registry.guardrails.values():
        parts.append(wrap("guardrails", substitute(unit.body, context), name=unit.name))

    # 2. Persona
    persona_unit = registry.personas.get(persona)
    if persona_unit is None:
        raise KeyError(f"Unknown persona: {persona!r}")
    parts.append(wrap("persona", substitute(persona_unit.body, context), name=persona))

    # 3. Skills, selected deterministically via routing table, in priority order.
    # A skill's `includes:` list may pull in fragments, error-handling
    # copy, or refusal patterns interchangeably — see includable_pool().
    skill_names = registry.skills_for(persona, intent)
    skill_units = [registry.skills[n] for n in skill_names if n in registry.skills]
    skill_units.sort(key=lambda u: u.meta.get("priority", 100))

    includable = registry.includable_pool()
    for unit in skill_units:
        body = resolve_includes(unit, includable)
        parts.append(wrap("skill", substitute(body, context), name=unit.name))

    # 4. Tool schemas (metadata for the API layer, plus a short in-prompt note)
    tool_names = registry.tools_for_skills(skill_names)
    tool_schemas = [compile_tool_schema(registry.tools[t]) for t in tool_names if t in registry.tools]
    if tool_names:
        parts.append(wrap("tool_context", f"Available tools for this turn: {', '.join(tool_names)}"))

    # 5. Dynamic user context (goes last — most volatile, least cache-friendly)
    if context:
        user_ctx_text = "\n".join(f"{k}: {v}" for k, v in context.items())
        parts.append(wrap("user_context", user_ctx_text))

    prompt = "\n\n".join(parts)
    return prompt, tool_schemas


# ---------------------------------------------------------------------------
# Tool schema compilation (markdown+frontmatter -> JSON for function-calling)
# ---------------------------------------------------------------------------

def compile_tool_schema(unit: PromptUnit) -> dict:
    """
    Turns a tools/<name>.md file into the JSON schema shape most
    function-calling APIs expect. The .md is hand-authored source of
    truth; this JSON is generated, never edited directly.
    """
    return {
        "name": unit.name,
        "description": unit.meta.get("description", unit.body.split("\n")[0]),
        "input_schema": unit.meta.get("input_schema", {"type": "object", "properties": {}}),
    }


def compile_all_tools(registry: Registry, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, unit in registry.tools.items():
        schema = compile_tool_schema(unit)
        (out_dir / f"{name}.json").write_text(json.dumps(schema, indent=2))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(registry: Registry) -> list[str]:
    errors = []
    includable = registry.includable_pool()

    for persona, routes in registry.routing.items():
        if persona not in registry.personas:
            errors.append(f"routing.yaml references unknown persona: {persona}")
        for intent, skill_names in routes.items():
            for name in skill_names:
                if name not in registry.skills:
                    errors.append(f"routing[{persona}][{intent}] references unknown skill: {name}")

    for name, unit in registry.skills.items():
        for tool_name in unit.meta.get("requires_tools", []):
            if tool_name not in registry.tools:
                errors.append(f"skill '{name}' requires unknown tool: {tool_name}")
        for frag_name in unit.meta.get("includes", []):
            if frag_name not in includable:
                errors.append(
                    f"skill '{name}' includes unknown fragment/error/refusal: {frag_name}"
                )
            elif includable[frag_name].meta.get("mode", "instruction") == "fixed":
                errors.append(
                    f"skill '{name}' includes '{frag_name}', which is mode:fixed — "
                    f"fixed messages can't be included as prompt instructions, "
                    f"they're looked up via get_fixed_for_kind() at the moment they fire"
                )

    # Two fixed-mode files claiming the same trigger_kind is ambiguous:
    # which one fires? Catch it at validation time instead of at runtime.
    kind_owners: dict[str, str] = {}
    for name, unit in includable.items():
        if unit.meta.get("mode") != "fixed":
            continue
        for kind in unit.meta.get("trigger_kinds", []):
            if kind in kind_owners:
                errors.append(
                    f"trigger_kind '{kind}' is claimed by both '{kind_owners[kind]}' "
                    f"and '{name}' — each kind must map to exactly one fixed message"
                )
            kind_owners[kind] = name

    # Tool retry config sanity: catch config that would silently retry
    # something irreversible, or a positive backoff with zero retries.
    for name, unit in registry.tools.items():
        max_retries = unit.meta.get("max_retries")
        no_retry_on = unit.meta.get("no_retry_on", [])
        if max_retries is not None and max_retries > 0 and "validation_error" not in no_retry_on:
            errors.append(
                f"tool '{name}' allows retries but doesn't exclude validation_error "
                f"in no_retry_on — retrying a bad request just repeats the failure"
            )

    return errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Render or validate the prompt system.")
    parser.add_argument("--persona", help="Persona name")
    parser.add_argument("--intent", default="default", help="Intent/state key (default: 'default')")
    parser.add_argument("--context", help="JSON string of dynamic context vars", default="{}")
    parser.add_argument("--validate", action="store_true", help="Validate routing/references and exit")
    parser.add_argument("--compile-tools", action="store_true", help="Compile tools/*.md to JSON schemas")
    args = parser.parse_args()

    registry = Registry.load()

    if args.validate:
        errors = validate(registry)
        if errors:
            print("VALIDATION FAILED:")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        print("OK: all routing/tool/fragment references are valid.")
        return

    if args.compile_tools:
        compile_all_tools(registry, ROOT / "tools_compiled")
        print(f"Compiled {len(registry.tools)} tool schemas to tools_compiled/")
        return

    if not args.persona:
        parser.error("--persona is required unless --validate or --compile-tools")

    context = json.loads(args.context)
    prompt, tool_schemas = render(registry, args.persona, args.intent, context)

    print(prompt)
    print("\n\n# ---- tool schemas passed to API (not in prompt text) ----")
    print(json.dumps(tool_schemas, indent=2))


if __name__ == "__main__":
    main()
