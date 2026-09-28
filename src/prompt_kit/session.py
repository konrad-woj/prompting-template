"""Per-conversation prompt state with sticky skill routing.

The tool set is fixed per persona, and the system prompt is frozen the first time it is
rendered. Skills activated later are handed out once through `take_late_instructions` for
the harness to put at the start of the next user turn, so tools, system prompt and earlier
history stay byte-identical and the provider's prompt cache keeps hitting.

Example:
    session = PromptSession(registry, persona="support_agent", config=config)
    session.activate("refund_request")
    system_prompt = session.system_prompt()     # frozen from here on
    session.activate("email_request")
    late_instructions = session.take_late_instructions()   # prepend to the next user message
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from prompt_kit.loader import PromptUnit, Registry
from prompt_kit.models import ToolMeta
from prompt_kit.render import render_skill, render_static_sections


@dataclass
class PromptSession:
    registry: Registry
    persona: str
    config: Mapping[str, Any]
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    max_verification_attempts: int = 2
    verified: bool = False
    verification_failures: int = 0
    active_skills: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.persona not in self.registry.personas:
            raise KeyError(f"unknown persona: {self.persona!r}")
        self._static_prefix = "\n\n".join(
            render_static_sections(self.registry, self.persona, self.config)
        )
        self._skill_sections: list[str] = []
        self._late_sections: list[str] = []
        self._included_partials: set[str] = set()
        self._frozen_system_prompt: str | None = None

    @property
    def verification_locked(self) -> bool:
        return (
            not self.verified
            and self.verification_failures >= self.max_verification_attempts
        )

    def activate(self, intent: str) -> list[str]:
        """Adds the skills routed for `intent` and returns the ones that were new."""
        routed = self.registry.skills_for(self.persona, intent)
        new_skills = sorted(
            (name for name in routed if name not in self.active_skills),
            key=lambda name: self.registry.skills[name].meta.priority,
        )
        for name in new_skills:
            skill = self.registry.skills[name]
            # A partial shared by several skills is rendered once, with the first skill that needs it.
            partial_names = [
                partial
                for partial in skill.meta.includes
                if partial not in self._included_partials
            ]
            self._included_partials.update(partial_names)
            self.active_skills.append(name)
            rendered = render_skill(self.registry, skill, self.config, partial_names)
            (
                self._late_sections
                if self._frozen_system_prompt
                else self._skill_sections
            ).append(rendered)
        return new_skills

    def record_verification(self, verified: bool) -> None:
        if verified:
            self.verified = True
        else:
            self.verification_failures += 1

    def system_prompt(self) -> str:
        if self._frozen_system_prompt is None:
            self._frozen_system_prompt = "\n\n".join(
                [self._static_prefix, *self._skill_sections]
            )
        return self._frozen_system_prompt

    def take_late_instructions(self) -> str | None:
        """Returns skills activated after the system prompt froze, once, or None."""
        if not self._late_sections:
            return None
        late_instructions = "\n\n".join(self._late_sections)
        self._late_sections.clear()
        return late_instructions

    @property
    def allowed_tool_names(self) -> list[str]:
        return self.registry.personas[self.persona].meta.allowed_tools

    def tools(self) -> list[PromptUnit[ToolMeta]]:
        return [self.registry.tools[name] for name in self.allowed_tool_names]
