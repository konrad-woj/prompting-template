"""A fake chat model that replays scripted assistant messages, for offline examples and tests.

Example:
    model = ScriptedModel([say("Hi!"), call("lookup_order", order_id="ORD-1")])
    loop = ChatLoop(session, executor, model.complete)
"""

import itertools
import json
from typing import Any

from prompt_kit.adapters.openai import Message

_call_ids = itertools.count(1)


def say(text: str) -> Message:
    return {"role": "assistant", "content": text}


def call(tool_name: str, **arguments: Any) -> Message:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call_{next(_call_ids)}",
                "type": "function",
                "function": {"name": tool_name, "arguments": json.dumps(arguments)},
            }
        ],
    }


class ScriptedModel:
    def __init__(self, responses: list[Message]) -> None:
        self._responses = list(responses)
        self.system_prompts: list[str] = []

    async def complete(
        self, messages: list[Message], tools: list[dict[str, Any]]
    ) -> Message:
        self.system_prompts.append(messages[0]["content"])
        if not self._responses:
            raise RuntimeError("scripted model ran out of responses")
        return self._responses.pop(0)
