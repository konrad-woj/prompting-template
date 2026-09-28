"""Frontmatter schemas for every prompt unit kind.

Unknown keys are rejected (`extra="forbid"`) so a typo in frontmatter fails at load time
instead of being silently ignored.
"""

from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ErrorKind(StrEnum):
    """Error kinds the runtime and executor understand. Tools may raise other kinds too."""

    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome_unknown"
    NOT_ALLOWED = "not_allowed"
    VERIFICATION_REQUIRED = "verification_required"
    VERIFICATION_LOCKED = "verification_locked"
    DECLINED_BY_USER = "declined_by_user"


TRANSIENT_ERROR_KINDS = frozenset(
    {ErrorKind.TIMEOUT, ErrorKind.UNAVAILABLE, ErrorKind.RATE_LIMITED}
)


class UnitMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str


class PersonaMeta(UnitMeta):
    description: str
    allowed_tools: list[str] = Field(default_factory=list)


class SkillMeta(UnitMeta):
    description: str
    requires_tools: list[str] = Field(default_factory=list)
    includes: list[str] = Field(default_factory=list)
    priority: int = 100


class ToolMeta(UnitMeta):
    input_schema: dict[str, Any]
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=0, ge=0)
    backoff_seconds: float = Field(default=0.0, ge=0)
    retry_on: list[ErrorKind] = Field(default_factory=list)
    side_effect: bool = False
    requires_verification: bool = False
    requires_confirmation: bool = False
    grants_verification: bool = False


class PartialMeta(UnitMeta):
    mode: Literal["instruction", "fixed"] = "instruction"
    trigger_kinds: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_trigger_kinds_match_mode(self) -> Self:
        if self.mode == "fixed" and not self.trigger_kinds:
            raise ValueError("mode: fixed requires at least one trigger_kind")
        if self.mode == "instruction" and self.trigger_kinds:
            raise ValueError("trigger_kinds only apply to mode: fixed")
        return self
