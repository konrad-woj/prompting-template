"""Logic-free rendering: `{{var}}` substitution and tagged sections.

Trusted operator config is substituted into prompt bodies. Untrusted user data never is;
it goes into the user turn through `format_user_data`, escaped.
"""

import re
from collections.abc import Mapping
from typing import Any

from prompt_kit.loader import PromptUnit, Registry
from prompt_kit.models import SkillMeta

VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class MissingVariableError(KeyError):
    pass


def find_variables(text: str) -> set[str]:
    return set(VARIABLE_PATTERN.findall(text))


def substitute(text: str, variables: Mapping[str, Any]) -> str:
    missing = find_variables(text) - variables.keys()
    if missing:
        raise MissingVariableError(f"missing prompt variables: {sorted(missing)}")
    return VARIABLE_PATTERN.sub(lambda match: str(variables[match.group(1)]), text)


def escape_untrusted(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def wrap(tag: str, body: str, name: str | None = None) -> str:
    name_attribute = f' name="{name}"' if name else ""
    return f"<{tag}{name_attribute}>\n{body}\n</{tag}>"


def format_user_data(user_data: Mapping[str, Any]) -> str:
    """Renders untrusted per-request data for the user turn, never the system prompt."""
    lines = (
        f"{escape_untrusted(str(key))}: {escape_untrusted(str(value))}"
        for key, value in user_data.items()
    )
    return wrap("user_data", "\n".join(lines))


def render_static_sections(
    registry: Registry, persona: str, config: Mapping[str, Any]
) -> list[str]:
    sections = [
        wrap("core_rules", substitute(unit.body, config), unit.name)
        for unit in registry.core.values()
    ]
    sections += [
        wrap("guardrails", substitute(unit.body, config), unit.name)
        for unit in registry.guardrails.values()
    ]
    sections.append(
        wrap("persona", substitute(registry.personas[persona].body, config), persona)
    )
    return sections


def render_skill(
    registry: Registry,
    skill: PromptUnit[SkillMeta],
    config: Mapping[str, Any],
    partial_names: list[str],
) -> str:
    # Partials get their own section so shared guidance doesn't read as scoped to this skill.
    sections = [wrap("skill", substitute(skill.body, config), skill.name)]
    sections += [
        wrap("guidance", substitute(registry.partials[name].body, config), name)
        for name in partial_names
    ]
    return "\n\n".join(sections)


def render_fixed_message(
    registry: Registry, kind: str, variables: Mapping[str, Any]
) -> str | None:
    """Returns the exact user-facing text for `kind`, or None if no fixed message exists."""
    unit = registry.fixed_partial_for_kind(kind)
    return substitute(unit.body, variables) if unit else None
