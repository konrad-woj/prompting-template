import json

import pytest

from examples.scripted_model import ScriptedModel, call, say
from prompt_kit import ToolExecutor
from prompt_kit.adapters.openai import (
    ChatLoop,
    clear_old_tool_results,
    is_affirmative,
    to_openai_tools,
)


async def fake_tool(**arguments):
    return {"ok": True}


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("yes", True),
        ("Yes, go ahead!", True),
        ("ok", True),
        ("no", False),
        ("yes but not now", False),
        ("no, refund 30 instead", False),
        ("what does that mean?", False),
    ],
)
def test_is_affirmative(reply, expected):
    assert is_affirmative(reply) is expected


async def test_confirmation_reply_text_reaches_the_model(session):
    model = ScriptedModel(
        [
            call("change_thing", thing_id="T-1"),
            say("Okay, what should I change instead?"),
        ]
    )
    loop = ChatLoop(
        session, ToolExecutor(session, {"change_thing": fake_tool}), model.complete
    )
    await loop.send("change it", intent="change")

    await loop.send("no, change T-2 instead")

    tool_message, user_message = loop.messages[-3], loop.messages[-2]
    assert json.loads(tool_message["content"])["error"] == "declined_by_user"
    assert user_message == {"role": "user", "content": "no, change T-2 instead"}


async def test_late_skills_go_into_the_user_turn_and_system_prompt_stays_fixed(session):
    model = ScriptedModel([say("Read."), say("Changed.")])
    loop = ChatLoop(session, ToolExecutor(session, {}), model.complete)

    await loop.send("read it", intent="read")
    await loop.send("now change it", intent="change")

    assert model.system_prompts[0] == model.system_prompts[1]
    assert loop.messages[-2]["content"].startswith('<skill name="changing">')
    assert loop.messages[-2]["content"].endswith("now change it")


def test_clear_old_tool_results_keeps_recent_and_structure():
    messages = [
        {"role": "tool", "tool_call_id": f"call_{index}", "content": "{}"}
        for index in range(3)
    ]

    clear_old_tool_results(messages, keep_recent=1)

    assert [json.loads(message["content"]) != {} for message in messages] == [
        True,
        True,
        False,
    ]
    assert [message["tool_call_id"] for message in messages] == [
        "call_0",
        "call_1",
        "call_2",
    ]


def two_calls(first: dict, second: dict) -> dict:
    return {**first, "tool_calls": first["tool_calls"] + second["tool_calls"]}


async def test_every_tool_call_is_answered_when_a_confirmation_pauses_the_turn(session):
    model = ScriptedModel(
        [
            two_calls(
                call("change_thing", thing_id="T-1"), call("read_thing", thing_id="T-2")
            ),
            say("Done."),
        ]
    )
    loop = ChatLoop(
        session,
        ToolExecutor(session, {"change_thing": fake_tool, "read_thing": fake_tool}),
        model.complete,
    )

    assert await loop.send("change it", intent="change") == "Change T-1?"
    assert await loop.send("yes") == "Done."

    requested_ids = {
        tool_call["id"]
        for message in loop.messages
        for tool_call in message.get("tool_calls", [])
    }
    answered_ids = {
        message["tool_call_id"]
        for message in loop.messages
        if message["role"] == "tool"
    }
    assert requested_ids == answered_ids


async def test_fixed_message_is_recorded_in_history_without_calling_the_model(session):
    from prompt_kit import ErrorKind, ToolError

    async def rate_limited(**arguments):
        raise ToolError(ErrorKind.RATE_LIMITED, retry_after_seconds=5)

    model = ScriptedModel([call("read_thing", thing_id="T-1")])
    loop = ChatLoop(
        session, ToolExecutor(session, {"read_thing": rate_limited}), model.complete
    )

    reply = await loop.send("read it", intent="read")

    assert reply == "Busy, retry in 5s."
    assert loop.messages[-1] == {"role": "assistant", "content": "Busy, retry in 5s."}
    assert json.loads(loop.messages[-2]["content"])["error"] == "rate_limited"


def test_non_strict_tools_drop_strict_flag_and_additional_properties(session):
    (strict_tool,) = to_openai_tools(session.tools()[:1])
    (relaxed_tool,) = to_openai_tools(session.tools()[:1], strict=False)

    assert strict_tool["function"]["strict"] is True
    assert "strict" not in relaxed_tool["function"]
    assert "additionalProperties" not in json.dumps(relaxed_tool)
