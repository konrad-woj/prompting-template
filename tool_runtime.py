"""
Code-level retry/backoff for tool execution.

This is the other half of "retries" — guardrail/error fragments tell the
MODEL how to talk about a failure; this module is what actually decides
whether to retry the underlying call, and enforces the same policy the
tool's .md file declares in frontmatter (max_retries, backoff_seconds,
retry_on, no_retry_on). Keeping the policy declared in the tool's own
file (rather than hardcoded per-callsite in Python) means the prompt
fragment and the code can't silently drift apart — both read from the
same source.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from render import Registry, PromptUnit, get_fixed_for_kind


class ToolError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind  # "timeout" | "5xx" | "validation_error" | "not_found" | ...


@dataclass
class RetryOutcome:
    success: bool
    result: Any = None
    error: ToolError | None = None
    attempts: int = 0


@dataclass
class TurnResponse:
    """
    What the caller (your agent loop) does next after a tool call fails.

    mode="fixed": `text` is the exact string to send to the user —
        do NOT pass this through the model. A trigger_kind matched a
        mode:fixed error/refusal file.
    mode="generate": no fixed message is declared for this failure kind.
        Proceed with a normal LLM turn — the active skill already
        includes the matching instruction-mode fragment (tool_failure,
        timeout, etc.) to guide how the model phrases it. `error_kind`
        is provided so you can also drop it into the dynamic context.
    """
    mode: str  # "fixed" | "generate"
    text: str | None = None
    error_kind: str | None = None


def handle_failure(registry: Registry, outcome: RetryOutcome, context: dict[str, Any] | None = None) -> TurnResponse:
    """
    Central place to decide fixed-vs-generated after a tool call fails.
    Every callsite should route through this rather than each deciding
    on its own — that's what keeps the fixed/instruction split from
    drifting into inconsistent per-feature judgment calls.
    """
    assert outcome.error is not None, "handle_failure called on a success"
    fixed_text = get_fixed_for_kind(registry, outcome.error.kind, context)
    if fixed_text is not None:
        return TurnResponse(mode="fixed", text=fixed_text)
    return TurnResponse(mode="generate", error_kind=outcome.error.kind)


def call_tool_with_retry(
    tool_unit: PromptUnit,
    fn: Callable[..., Any],
    *args: Any,
    idempotency_key: str | None = None,
    **kwargs: Any,
) -> RetryOutcome:
    """
    Executes fn(*args, **kwargs) honoring the calling tool's declared
    retry policy. fn should raise ToolError(kind=...) on failure so this
    runner can decide whether that kind is retryable.

    For an irreversible action (issue_refund, etc.), the caller must
    pass idempotency_key — retried calls must be safe to repeat, never
    "retry by calling it again and hoping."
    """
    max_retries: int = tool_unit.meta.get("max_retries", 0)
    backoff_seconds: float = tool_unit.meta.get("backoff_seconds", 0)
    retry_on: set[str] = set(tool_unit.meta.get("retry_on", []))
    no_retry_on: set[str] = set(tool_unit.meta.get("no_retry_on", []))

    if idempotency_key is not None:
        kwargs.setdefault("idempotency_key", idempotency_key)

    attempt = 0
    last_error: ToolError | None = None

    while attempt <= max_retries:
        attempt += 1
        try:
            result = fn(*args, **kwargs)
            return RetryOutcome(success=True, result=result, attempts=attempt)
        except ToolError as e:
            last_error = e
            if e.kind in no_retry_on:
                break  # never retry this kind, regardless of budget left
            if retry_on and e.kind not in retry_on:
                break  # only declared kinds are retryable
            if attempt > max_retries:
                break
            time.sleep(backoff_seconds * attempt)  # linear backoff; swap for exponential if needed

    return RetryOutcome(success=False, error=last_error, attempts=attempt)


# ---------------------------------------------------------------------------
# Demo: simulate lookup_order (transient timeout, then succeeds) and
# issue_refund (validation error, must NOT retry).
# ---------------------------------------------------------------------------

def _demo() -> None:
    registry = Registry.load()

    print("=== lookup_order: transient timeout then success ===")
    calls = {"n": 0}

    def flaky_lookup(order_id: str, idempotency_key: str | None = None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ToolError("timeout", "orders service timed out")
        return {"order_id": order_id, "amount": 42.00, "status": "delivered"}

    outcome = call_tool_with_retry(registry.tools["lookup_order"], flaky_lookup, order_id="ORD-1")
    print(f"success={outcome.success} attempts={outcome.attempts} result={outcome.result}")

    print("\n=== issue_refund: validation error, must not retry ===")

    def bad_refund(order_id: str, amount: float, idempotency_key: str | None = None):
        raise ToolError("validation_error", "amount exceeds order total")

    outcome = call_tool_with_retry(
        registry.tools["issue_refund"], bad_refund,
        order_id="ORD-1", amount=999.0, idempotency_key="refund-ORD-1-abc123",
    )
    print(f"success={outcome.success} attempts={outcome.attempts} "
          f"error_kind={outcome.error.kind if outcome.error else None}")
    assert outcome.attempts == 1, "validation_error must not trigger a retry"

    response = handle_failure(registry, outcome)
    print(f"-> TurnResponse.mode={response.mode!r} (validation_error has no fixed "
          f"message, so this falls through to a normal LLM turn guided by the "
          f"skill's included 'tool_failure' instruction fragment)")
    assert response.mode == "generate"

    print("\n=== issue_refund: rate limited -> fixed response, no LLM call ===")

    def rate_limited_refund(order_id: str, amount: float, idempotency_key: str | None = None):
        raise ToolError("rate_limited", "too many refund requests")

    outcome = call_tool_with_retry(
        registry.tools["issue_refund"], rate_limited_refund,
        order_id="ORD-1", amount=42.0, idempotency_key="refund-ORD-1-abc124",
    )
    response = handle_failure(
        registry, outcome,
        context={"retry_after_seconds": 30, "support_email": "help@acme.com"},
    )
    print(f"-> TurnResponse.mode={response.mode!r}")
    print(f"   text sent verbatim to user (no generation): {response.text!r}")
    assert response.mode == "fixed"
    assert "30 seconds" in response.text

    print("\nAll three cases behaved per the tool's declared policy and the"
          " fixed/instruction split — no drift between what the prompt system"
          " declares and what the code actually does.")


if __name__ == "__main__":
    _demo()
