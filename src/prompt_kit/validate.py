"""Whole-registry checks that a single file's frontmatter schema can't catch.

Example:
    problems = validate(Registry.load(Path("prompts")), config={"agent_name": "Ava"})
"""

from collections.abc import Mapping
from typing import Any

from prompt_kit.loader import Registry
from prompt_kit.models import TRANSIENT_ERROR_KINDS
from prompt_kit.render import find_variables


def validate(registry: Registry, config: Mapping[str, Any] | None = None) -> list[str]:
    """Returns human-readable problems; empty means valid. Pass `config` to also check variables."""
    return [
        *_check_routing(registry),
        *_check_personas(registry),
        *_check_skills(registry),
        *_check_partials(registry),
        *_check_tools(registry),
        *(_check_variables(registry, config) if config is not None else []),
    ]


def _check_routing(registry: Registry) -> list[str]:
    problems = []
    for persona, routes in registry.routing.items():
        if persona not in registry.personas:
            problems.append(f"routing.yaml: unknown persona '{persona}'")
            continue
        if "default" not in routes:
            problems.append(f"routing.yaml: persona '{persona}' has no 'default' route")
        allowed_tools = set(registry.personas[persona].meta.allowed_tools)
        for intent, skill_names in routes.items():
            for skill_name in skill_names:
                skill = registry.skills.get(skill_name)
                if skill is None:
                    problems.append(
                        f"routing.yaml: {persona}.{intent} references unknown skill '{skill_name}'"
                    )
                    continue
                for tool_name in sorted(set(skill.meta.requires_tools) - allowed_tools):
                    problems.append(
                        f"routing.yaml: {persona}.{intent} routes skill '{skill_name}', which needs tool "
                        f"'{tool_name}' that is not in persona '{persona}' allowed_tools"
                    )
    for persona in registry.personas.keys() - registry.routing.keys():
        problems.append(f"routing.yaml: persona '{persona}' has no routes")
    return problems


def _check_personas(registry: Registry) -> list[str]:
    return [
        f"persona '{persona.name}' allows unknown tool '{tool_name}'"
        for persona in registry.personas.values()
        for tool_name in persona.meta.allowed_tools
        if tool_name not in registry.tools
    ]


def _check_skills(registry: Registry) -> list[str]:
    problems = []
    partials = registry.partials
    for skill in registry.skills.values():
        for tool_name in skill.meta.requires_tools:
            if tool_name not in registry.tools:
                problems.append(
                    f"skill '{skill.name}' requires unknown tool '{tool_name}'"
                )
        for partial_name in skill.meta.includes:
            partial = partials.get(partial_name)
            if partial is None:
                problems.append(
                    f"skill '{skill.name}' includes unknown partial '{partial_name}'"
                )
            elif partial.meta.mode == "fixed":
                problems.append(
                    f"skill '{skill.name}' includes '{partial_name}', which is mode: fixed; fixed messages "
                    f"are sent to the user verbatim and must not be used as model instructions"
                )
    return problems


def _check_partials(registry: Registry) -> list[str]:
    problems = []
    owner_by_name: dict[str, str] = {}
    for directory, units in registry.partials_by_directory.items():
        for name in units:
            if name in owner_by_name:
                problems.append(
                    f"partial name '{name}' exists in both {owner_by_name[name]}/ and {directory}/"
                )
            owner_by_name[name] = directory

    owner_by_kind: dict[str, str] = {}
    for unit in registry.partials.values():
        for kind in unit.meta.trigger_kinds:
            if kind in owner_by_kind:
                problems.append(
                    f"trigger kind '{kind}' is claimed by both '{owner_by_kind[kind]}' and '{unit.name}'"
                )
            owner_by_kind[kind] = unit.name
    return problems


def _check_tools(registry: Registry) -> list[str]:
    problems = []
    for tool in registry.tools.values():
        meta = tool.meta
        if not tool.body:
            problems.append(f"tool '{tool.name}' has no description body")
        for kind in sorted(set(meta.retry_on) - TRANSIENT_ERROR_KINDS):
            problems.append(
                f"tool '{tool.name}' retries on '{kind}', which is not transient; retrying repeats it"
            )
        if meta.retry_on and meta.max_retries == 0:
            problems.append(
                f"tool '{tool.name}' declares retry_on but max_retries is 0"
            )
        if meta.requires_confirmation:
            confirmation = registry.fixed_partial_for_kind(f"confirm_{tool.name}")
            if confirmation is None:
                problems.append(
                    f"tool '{tool.name}' requires confirmation but no fixed partial has trigger kind "
                    f"'confirm_{tool.name}'"
                )
        problems += [
            f"tool '{tool.name}' input_schema: {problem}"
            for problem in _strict_schema_problems(meta.input_schema)
        ]
    return problems


def _strict_schema_problems(schema: Mapping[str, Any], path: str = "$") -> list[str]:
    # Strict function calling needs every object closed and every property required.
    problems = []
    if schema.get("type") == "object":
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is not False:
            problems.append(f"{path} must set additionalProperties: false")
        missing_required = set(properties) - set(schema.get("required", []))
        if missing_required:
            problems.append(
                f"{path} must list every property in required (missing {sorted(missing_required)})"
            )
        for property_name, property_schema in properties.items():
            problems += _strict_schema_problems(
                property_schema, f"{path}.{property_name}"
            )
    if schema.get("type") == "array" and "items" in schema:
        problems += _strict_schema_problems(schema["items"], f"{path}[]")
    return problems


def _check_variables(registry: Registry, config: Mapping[str, Any]) -> list[str]:
    problems = []
    instruction_units = [
        *registry.core.values(),
        *registry.guardrails.values(),
        *registry.personas.values(),
        *registry.skills.values(),
        *(
            unit
            for unit in registry.partials.values()
            if unit.meta.mode == "instruction"
        ),
    ]
    for unit in instruction_units:
        for variable in sorted(find_variables(unit.body) - config.keys()):
            problems.append(
                f"{unit.path.relative_to(registry.root)} uses '{{{{{variable}}}}}', missing from config"
            )
    for tool in registry.tools.values():
        confirmation = registry.fixed_partial_for_kind(f"confirm_{tool.name}")
        if confirmation is None:
            continue
        available = config.keys() | tool.meta.input_schema.get("properties", {}).keys()
        for variable in sorted(find_variables(confirmation.body) - available):
            problems.append(
                f"{confirmation.path.relative_to(registry.root)} uses '{{{{{variable}}}}}', which is neither in "
                f"config nor an argument of '{tool.name}'"
            )
    return problems
