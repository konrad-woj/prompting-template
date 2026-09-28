"""OpenAI-compatible Chat Completions adapter and a minimal agent loop.

The loop takes a `complete` coroutine instead of a client, so the same code runs against
any OpenAI-compatible API (OpenAI, Azure OpenAI, Gemini's compatibility endpoint) or a
scripted fake in tests and mock examples.

Example:
    async def complete(messages, tools):
        response = await client.chat.completions.create(model=model, messages=messages, tools=tools)
        return response.choices[0].message.model_dump(include={"role", "content", "tool_calls"}, exclude_none=True)

    loop = ChatLoop(session, executor, complete)
    reply = await loop.send("I want a refund for ORD-1042", intent="refund_request")
"""

import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from prompt_kit.loader import PromptUnit
from prompt_kit.models import ToolMeta
from prompt_kit.render import format_user_data
from prompt_kit.runtime import ToolCall, ToolExecutor, ToolResolution
from prompt_kit.session import PromptSession

Message = dict[str, Any]
Completion = Callable[[list[Message], list[dict[str, Any]]], Awaitable[Message]]

WORD_PATTERN = re.compile(r"[a-z']+")
AFFIRMATIVE_WORDS = frozenset(
    {
        "yes",
        "y",
        "yeah",
        "yep",
        "sure",
        "ok",
        "okay",
        "confirm",
        "confirmed",
        "go",
        "proceed",
    }
)
NEGATIVE_WORDS = frozenset(
    {"no", "not", "don't", "dont", "cancel", "stop", "wait", "instead"}
)
CLEARED_TOOL_RESULT = json.dumps(
    {
        "cleared": "Older tool result removed to save context; call the tool again if needed."
    }
)


def to_openai_tools(
    tools: list[PromptUnit[ToolMeta]], strict: bool = True
) -> list[dict[str, Any]]:
    """Builds function tools. `strict=False` is for compatible APIs without strict mode (e.g. Gemini)."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.body,
                "parameters": tool.meta.input_schema
                if strict
                else _without_additional_properties(tool.meta.input_schema),
                **({"strict": True} if strict else {}),
            },
        }
        for tool in tools
    ]


def _without_additional_properties(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {
            key: _without_additional_properties(value)
            for key, value in schema.items()
            if key != "additionalProperties"
        }
    if isinstance(schema, list):
        return [_without_additional_properties(item) for item in schema]
    return schema


def tool_calls_from_message(message: Message) -> list[ToolCall]:
    return [
        ToolCall(
            id=tool_call["id"],
            name=tool_call["function"]["name"],
            arguments=json.loads(tool_call["function"]["arguments"] or "{}"),
        )
        for tool_call in message.get("tool_calls") or []
    ]


def resolution_messages(resolution: ToolResolution) -> list[Message]:
    messages: list[Message] = [
        {
            "role": "tool",
            "tool_call_id": resolution.tool_call_id,
            "content": json.dumps(resolution.content),
        }
    ]
    if resolution.status == "fixed":
        # Recorded in history so the model knows what the user was told on the next turn.
        messages.append({"role": "assistant", "content": resolution.assistant_text})
    return messages


def skipped_message(tool_call: ToolCall) -> Message:
    content = {
        "error": "not_run",
        "hint": "Not executed because an earlier call in this turn paused for the user.",
    }
    return {
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps(content),
    }


def is_affirmative(text: str) -> bool:
    words = WORD_PATTERN.findall(text.lower())
    return (
        bool(words)
        and words[0] in AFFIRMATIVE_WORDS
        and not NEGATIVE_WORDS.intersection(words)
    )


def clear_old_tool_results(messages: list[Message], keep_recent: int) -> None:
    """Replaces all but the last `keep_recent` tool results with a stub, keeping history valid."""
    tool_messages = [message for message in messages if message["role"] == "tool"]
    for message in tool_messages[: max(len(tool_messages) - keep_recent, 0)]:
        message["content"] = CLEARED_TOOL_RESULT


@dataclass
class ChatLoop:
    """Minimal agent loop. `keep_tool_results` bounds history growth in long sessions."""

    session: PromptSession
    executor: ToolExecutor
    complete: Completion
    max_model_calls: int = 8
    strict_tools: bool = True
    keep_tool_results: int | None = None
    messages: list[Message] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._tools = to_openai_tools(self.session.tools(), strict=self.strict_tools)

    async def send(
        self,
        user_text: str,
        intent: str = "default",
        user_data: Mapping[str, Any] | None = None,
    ) -> str:
        """Handles one user message and returns the text to show the user."""
        if self.executor.pending_confirmation is not None:
            resolution = await self.executor.resolve_confirmation(
                approved=is_affirmative(user_text)
            )
            # The reply itself goes into history too: "no, refund 30 instead" is more than a no.
            self.messages += resolution_messages(resolution)[:1]
            self.messages.append({"role": "user", "content": user_text})
            if resolution.status == "fixed":
                self.messages.append(
                    {"role": "assistant", "content": resolution.assistant_text}
                )
                return resolution.assistant_text
            return await self._run_model()

        self.session.activate(intent)
        parts = [self.session.take_late_instructions() if self.messages else None]
        parts += [format_user_data(user_data) if user_data else None, user_text]
        self.messages.append(
            {"role": "user", "content": "\n\n".join(part for part in parts if part)}
        )
        return await self._run_model()

    async def _run_model(self) -> str:
        for _ in range(self.max_model_calls):
            if self.keep_tool_results is not None:
                clear_old_tool_results(self.messages, self.keep_tool_results)
            system = {"role": "system", "content": self.session.system_prompt()}
            assistant_message = await self.complete(
                [system, *self.messages], self._tools
            )
            self.messages.append(assistant_message)
            tool_calls = tool_calls_from_message(assistant_message)
            if not tool_calls:
                return assistant_message.get("content") or ""
            for index, tool_call in enumerate(tool_calls):
                resolution = await self.executor.execute(tool_call)
                if resolution.status != "confirmation_required":
                    self.messages += resolution_messages(resolution)
                if resolution.status in ("confirmation_required", "fixed"):
                    # Every tool call needs an answer before the next model call, so calls after a
                    # pause are reported as not run and the model can re-issue them later.
                    self.messages += [
                        skipped_message(skipped) for skipped in tool_calls[index + 1 :]
                    ]
                    return resolution.assistant_text
        raise RuntimeError(f"no final answer after {self.max_model_calls} model calls")
