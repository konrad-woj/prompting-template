import pytest

from prompt_kit import PromptSession


def test_sections_render_in_static_to_dynamic_order(session):
    session.activate("read")

    prompt = session.system_prompt()

    positions = [
        prompt.index(tag)
        for tag in ("<core_rules", "<guardrails", "<persona", '<skill name="reading"')
    ]
    assert positions == sorted(positions)


def test_system_prompt_is_frozen_and_late_skills_are_handed_out_once(session):
    session.activate("read")
    first_prompt = session.system_prompt()

    added = session.activate("change")

    assert added == ["changing"]
    assert session.system_prompt() == first_prompt
    assert '<skill name="changing">' in session.take_late_instructions()
    assert session.take_late_instructions() is None
    assert session.active_skills == ["reading", "changing"]


def test_skills_activated_before_first_render_are_in_the_system_prompt(session):
    session.activate("read")
    session.activate("change")

    assert '<skill name="changing">' in session.system_prompt()
    assert session.take_late_instructions() is None


def test_reactivating_an_intent_adds_nothing(session):
    session.activate("read")

    assert session.activate("read") == []


def test_shared_partial_is_rendered_once(session):
    session.activate("read")
    session.activate("change")

    assert session.system_prompt().count('<guidance name="tool_errors">') == 1


def test_tools_are_fixed_per_persona_regardless_of_skills(session):
    tools_before = [tool.name for tool in session.tools()]
    session.activate("read")

    assert (
        [tool.name for tool in session.tools()]
        == tools_before
        == ["read_thing", "change_thing"]
    )


def test_unknown_intent_falls_back_to_default(session):
    assert session.activate("something_else") == ["fallback"]


def test_unknown_persona_is_rejected(make_registry):
    with pytest.raises(KeyError, match="nobody"):
        PromptSession(make_registry(), persona="nobody", config={})


def test_verification_locks_after_max_failures(session):
    session.record_verification(False)
    session.record_verification(False)

    assert session.verification_locked
