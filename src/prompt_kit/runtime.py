"""Async tool execution: retries, idempotency, verification and confirmation gates.

Everything here is provider-neutral. A `ToolResolution` describes what happened; an
adapter (see `prompt_kit.adapters.openai`) turns it into provider messages.

Example:
    executor = ToolExecutor(session, implementations={"lookup_order": lookup_order})
    resolution = await executor.execute(ToolCall(id="call_1", name="lookup_order", arguments={...}))
    if resolution.status == "confirmation_required":
        show(resolution.assistant_text)
        resolution = await executor.resolve_confirmation(approved=True)
"""

import asyncio
import hashlib
import json
import logging
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from prompt_kit.loader import PromptUnit
from prompt_kit.models import ErrorKind, ToolMeta
from prompt_kit.render import render_fixed_message
from prompt_kit.session import PromptSession

logger = logging.getLogger(__name__)

ToolFunction = Callable[..., Awaitable[Any]]

DEFAULT_HINTS = {
    ErrorKind.NOT_ALLOWED: "This tool isn't available in this conversation; continue without it.",
    ErrorKind.VERIFICATION_REQUIRED: "Verify the user with the verification tool first, then call this again.",
    ErrorKind.VERIFICATION_LOCKED: "Verification is locked after repeated failures; stop asking for details and offer a handoff.",
    ErrorKind.DECLINED_BY_USER: "The user declined at the confirmation step; their reply follows. Don't retry without a new request.",
    ErrorKind.OUTCOME_UNKNOWN: "The action may have been applied. Don't repeat it or report it as failed; have it checked.",
    ErrorKind.TIMEOUT: "The system already retried. Report the failure instead of calling again with the same arguments.",
}


class ToolError(Exception):
    """Raised by tool implementations. `details` are facts passed to the model and to fixed messages."""

    def __init__(
        self, kind: str, message: str = "", hint: str | None = None, **details: Any
    ) -> None:
        super().__init__(message or kind)
        self.kind = kind
        self.hint = hint
        self.details = details


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolOutcome:
    success: bool
    attempts: int
    result: Any = None
    error: ToolError | None = None


@dataclass(frozen=True)
class ToolResolution:
    """What the agent loop does next for one tool call.

    status:
        "ok" / "error": send `content` back as the tool result and call the model again.
        "fixed": send `content` as the tool result, then show `assistant_text` to the user
            verbatim and end the turn without calling the model.
        "confirmation_required": show `assistant_text`, wait for the user's answer, then call
            `ToolExecutor.resolve_confirmation`. No tool result is sent yet.
    """

    tool_call_id: str
    status: Literal["ok", "error", "fixed", "confirmation_required"]
    content: dict[str, Any] | None = None
    assistant_text: str | None = None

    @property
    def is_error(self) -> bool:
        return self.status in ("error", "fixed")


def make_idempotency_key(
    session_id: str, tool_name: str, arguments: Mapping[str, Any]
) -> str:
    # Derived from the call's content, not the provider's tool_call id, so a model that
    # re-issues the same call gets the same key and the backend deduplicates it.
    canonical = json.dumps(
        {"session": session_id, "tool": tool_name, "arguments": arguments},
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def backoff_delay(meta: ToolMeta, attempt: int, error: ToolError) -> float:
    if "retry_after_seconds" in error.details:
        return float(error.details["retry_after_seconds"])
    return meta.backoff_seconds * 2 ** (attempt - 1) * random.uniform(0.5, 1.0)


async def call_tool_with_retry(
    tool: PromptUnit[ToolMeta],
    tool_function: ToolFunction,
    arguments: Mapping[str, Any],
    idempotency_key: str | None = None,
) -> ToolOutcome:
    meta = tool.meta
    if meta.side_effect and meta.max_retries > 0 and idempotency_key is None:
        raise ValueError(
            f"tool '{tool.name}' has side effects and retries; an idempotency_key is required"
        )
    call_arguments = dict(arguments)
    if idempotency_key is not None:
        call_arguments["idempotency_key"] = idempotency_key

    last_error = ToolError(ErrorKind.FAILED)
    for attempt in range(1, meta.max_retries + 2):
        try:
            async with asyncio.timeout(meta.timeout_seconds):
                result = await tool_function(**call_arguments)
            return ToolOutcome(success=True, attempts=attempt, result=result)
        except TimeoutError:
            last_error = ToolError(
                ErrorKind.TIMEOUT, f"no response within {meta.timeout_seconds}s"
            )
        except ToolError as error:
            last_error = error
        logger.warning(
            "tool %s attempt %d failed: %s",
            tool.name,
            attempt,
            last_error.kind,
            extra={
                "tool": tool.name,
                "attempt": attempt,
                "error_kind": last_error.kind,
            },
        )
        if last_error.kind not in meta.retry_on or attempt > meta.max_retries:
            break
        await asyncio.sleep(backoff_delay(meta, attempt, last_error))

    if meta.side_effect and last_error.kind == ErrorKind.TIMEOUT:
        # A timed-out side effect may have been applied; reporting it as failed invites a repeat.
        last_error = ToolError(
            ErrorKind.OUTCOME_UNKNOWN, str(last_error), **last_error.details
        )
    return ToolOutcome(success=False, attempts=attempt, error=last_error)


@dataclass
class ToolExecutor:
    session: PromptSession
    implementations: Mapping[str, ToolFunction]
    pending_confirmation: ToolCall | None = field(default=None, init=False)

    async def execute(self, call: ToolCall) -> ToolResolution:
        tool = self.session.registry.tools.get(call.name)
        if tool is None or call.name not in self.session.allowed_tool_names:
            return self._error(call, ToolError(ErrorKind.NOT_ALLOWED))
        if tool.meta.grants_verification and self.session.verification_locked:
            return self._error(call, ToolError(ErrorKind.VERIFICATION_LOCKED))
        if tool.meta.requires_verification and not self.session.verified:
            return self._error(call, ToolError(ErrorKind.VERIFICATION_REQUIRED))
        if tool.meta.requires_confirmation:
            self.pending_confirmation = call
            confirmation_text = render_fixed_message(
                self.session.registry,
                f"confirm_{call.name}",
                {**self.session.config, **call.arguments},
            )
            return ToolResolution(
                call.id, "confirmation_required", assistant_text=confirmation_text
            )
        return await self._run(tool, call)

    async def resolve_confirmation(self, approved: bool) -> ToolResolution:
        call = self.pending_confirmation
        if call is None:
            raise RuntimeError("no tool call is waiting for confirmation")
        self.pending_confirmation = None
        if not approved:
            return self._error(call, ToolError(ErrorKind.DECLINED_BY_USER))
        return await self._run(
            self.session.registry.tools[call.name], call, confirmed=True
        )

    async def _run(
        self, tool: PromptUnit[ToolMeta], call: ToolCall, confirmed: bool = False
    ) -> ToolResolution:
        idempotency_key = (
            make_idempotency_key(self.session.session_id, call.name, call.arguments)
            if tool.meta.side_effect
            else None
        )
        outcome = await call_tool_with_retry(
            tool, self.implementations[call.name], call.arguments, idempotency_key
        )
        if tool.meta.grants_verification and outcome.success:
            self.session.record_verification(bool(outcome.result.get("verified")))
        if outcome.success:
            content = {"result": outcome.result}
            if confirmed:
                content["user_confirmed"] = True
            return ToolResolution(call.id, "ok", content=content)
        return self._error(call, outcome.error)

    def _error(self, call: ToolCall, error: ToolError) -> ToolResolution:
        content: dict[str, Any] = {
            "error": error.kind,
            "outcome_known": error.kind != ErrorKind.OUTCOME_UNKNOWN,
            **error.details,
        }
        hint = error.hint or DEFAULT_HINTS.get(error.kind)
        if hint:
            content["hint"] = hint
        fixed_text = render_fixed_message(
            self.session.registry, error.kind, {**self.session.config, **error.details}
        )
        if fixed_text is not None:
            return ToolResolution(
                call.id, "fixed", content=content, assistant_text=fixed_text
            )
        return ToolResolution(call.id, "error", content=content)
