import asyncio

import pytest

from prompt_kit import (
    ErrorKind,
    ToolCall,
    ToolError,
    ToolExecutor,
    call_tool_with_retry,
    make_idempotency_key,
)


class FlakyTool:
    """Raises the queued errors in order, then returns `result`."""

    def __init__(self, errors: list[Exception], result: dict | None = None) -> None:
        self.errors = list(errors)
        self.result = result or {"ok": True}
        self.calls: list[dict] = []

    async def __call__(self, **arguments):
        self.calls.append(arguments)
        if self.errors:
            raise self.errors.pop(0)
        return self.result


async def hang_forever(**arguments):
    await asyncio.sleep(10)


def call_for(name: str, **arguments) -> ToolCall:
    return ToolCall(id="call_1", name=name, arguments=arguments or {"thing_id": "T-1"})


async def test_retries_transient_errors_until_success(session):
    tool_function = FlakyTool(
        [ToolError(ErrorKind.UNAVAILABLE), ToolError(ErrorKind.UNAVAILABLE)]
    )

    outcome = await call_tool_with_retry(
        session.registry.tools["read_thing"], tool_function, {"thing_id": "T-1"}
    )

    assert outcome.success and outcome.attempts == 3


async def test_does_not_retry_kinds_outside_retry_on(session):
    tool_function = FlakyTool([ToolError(ErrorKind.INVALID_INPUT)])

    outcome = await call_tool_with_retry(
        session.registry.tools["read_thing"], tool_function, {"thing_id": "T-1"}
    )

    assert (
        not outcome.success
        and outcome.attempts == 1
        and outcome.error.kind == ErrorKind.INVALID_INPUT
    )


async def test_gives_up_after_retry_budget(session):
    tool_function = FlakyTool([ToolError(ErrorKind.UNAVAILABLE)] * 5)

    outcome = await call_tool_with_retry(
        session.registry.tools["read_thing"], tool_function, {"thing_id": "T-1"}
    )

    assert not outcome.success and outcome.attempts == 3


async def test_side_effect_tool_with_retries_requires_idempotency_key(session):
    with pytest.raises(ValueError, match="idempotency_key is required"):
        await call_tool_with_retry(
            session.registry.tools["change_thing"], FlakyTool([]), {"thing_id": "T-1"}
        )


async def test_timed_out_side_effect_reports_outcome_unknown(session):
    outcome = await call_tool_with_retry(
        session.registry.tools["change_thing"],
        hang_forever,
        {"thing_id": "T-1"},
        idempotency_key="key",
    )

    assert outcome.error.kind == ErrorKind.OUTCOME_UNKNOWN


def test_idempotency_key_is_stable_across_argument_order():
    first = make_idempotency_key("session", "change_thing", {"a": 1, "b": 2})

    assert first == make_idempotency_key("session", "change_thing", {"b": 2, "a": 1})
    assert first != make_idempotency_key("session", "change_thing", {"a": 1, "b": 3})


async def test_fixed_message_resolution_carries_tool_content_and_exact_text(session):
    tool_function = FlakyTool(
        [ToolError(ErrorKind.RATE_LIMITED, retry_after_seconds=30)] * 3
    )
    executor = ToolExecutor(session, {"read_thing": tool_function})

    resolution = await executor.execute(call_for("read_thing"))

    assert resolution.status == "fixed"
    assert resolution.assistant_text == "Busy, retry in 30s."
    assert resolution.content["error"] == "rate_limited"


async def test_generated_error_resolution_has_no_user_text(session):
    executor = ToolExecutor(
        session,
        {
            "read_thing": FlakyTool(
                [ToolError(ErrorKind.NOT_FOUND, hint="Check the ID.")]
            )
        },
    )

    resolution = await executor.execute(call_for("read_thing"))

    assert resolution.status == "error" and resolution.assistant_text is None
    assert resolution.content == {
        "error": "not_found",
        "outcome_known": True,
        "hint": "Check the ID.",
    }


async def test_confirmation_runs_tool_only_after_approval(session):
    tool_function = FlakyTool([])
    executor = ToolExecutor(session, {"change_thing": tool_function})

    pending = await executor.execute(call_for("change_thing"))
    assert (
        pending.status == "confirmation_required"
        and pending.assistant_text == "Change T-1?"
    )
    assert tool_function.calls == []

    resolution = await executor.resolve_confirmation(approved=True)

    assert resolution.status == "ok" and resolution.content["user_confirmed"] is True
    assert "idempotency_key" in tool_function.calls[0]


async def test_declined_confirmation_never_runs_tool(session):
    tool_function = FlakyTool([])
    executor = ToolExecutor(session, {"change_thing": tool_function})
    await executor.execute(call_for("change_thing"))

    resolution = await executor.resolve_confirmation(approved=False)

    assert (
        resolution.content["error"] == "declined_by_user" and tool_function.calls == []
    )


async def test_tool_outside_persona_is_not_allowed(make_registry):
    from prompt_kit import PromptSession

    persona = "---\nname: agent\ndescription: x\nallowed_tools: [read_thing]\n---\nHi."
    registry = make_registry(
        {
            "personas/agent.md": persona,
            "routing.yaml": "agent:\n  default: [fallback]\n",
        }
    )
    executor = ToolExecutor(
        PromptSession(registry, "agent", {}), {"change_thing": FlakyTool([])}
    )

    resolution = await executor.execute(call_for("change_thing"))

    assert resolution.content["error"] == "not_allowed"


async def test_verification_gates_and_locks(make_registry):
    from prompt_kit import PromptSession

    files = {
        "tools/verify.md": """
            ---
            name: verify
            input_schema: {type: object, properties: {}, required: [], additionalProperties: false}
            grants_verification: true
            ---
            Verifies.
            """,
        "tools/read_thing.md": """
            ---
            name: read_thing
            input_schema: {type: object, properties: {}, required: [], additionalProperties: false}
            requires_verification: true
            ---
            Reads.
            """,
        "personas/agent.md": "---\nname: agent\ndescription: x\nallowed_tools: [verify, read_thing]\n---\nHi.",
        "routing.yaml": "agent:\n  default: [fallback]\n",
    }
    session = PromptSession(make_registry(files), "agent", {})
    executor = ToolExecutor(
        session,
        {"verify": FlakyTool([], {"verified": False}), "read_thing": FlakyTool([])},
    )

    blocked = await executor.execute(ToolCall("c1", "read_thing", {}))
    await executor.execute(ToolCall("c2", "verify", {}))
    await executor.execute(ToolCall("c3", "verify", {}))
    locked = await executor.execute(ToolCall("c4", "verify", {}))

    assert (
        blocked.content["error"] == "verification_required"
        and "hint" in blocked.content
    )
    assert locked.content["error"] == "verification_locked"
