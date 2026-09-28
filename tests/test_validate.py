import pytest

from prompt_kit import PromptLoadError, validate


def test_minimal_prompts_are_valid(make_registry):
    assert validate(make_registry(), config={"agent_name": "Ava"}) == []


@pytest.mark.parametrize(
    ("files", "expected_problem"),
    [
        (
            {
                "skills/reading.md": "---\nname: reading\ndescription: x\nincludes: [busy]\n---\nRead."
            },
            "includes 'busy', which is mode: fixed",
        ),
        (
            {
                "refusals/busy_too.md": "---\nname: busy_too\nmode: fixed\ntrigger_kinds: [rate_limited]\n---\nBusy."
            },
            "trigger kind 'rate_limited' is claimed by both",
        ),
        (
            {"refusals/tool_errors.md": "---\nname: tool_errors\n---\nDuplicate."},
            "partial name 'tool_errors' exists in both",
        ),
        (
            {
                "personas/agent.md": "---\nname: agent\ndescription: x\nallowed_tools: [read_thing]\n---\nHi."
            },
            "needs tool 'change_thing' that is not in persona 'agent' allowed_tools",
        ),
        (
            {"confirmations/confirm_change_thing.md": None},
            "requires confirmation but no fixed partial has trigger kind 'confirm_change_thing'",
        ),
        (
            {"routing.yaml": "agent:\n  read: [reading]\n"},
            "persona 'agent' has no 'default' route",
        ),
    ],
)
def test_reports_cross_file_problems(make_registry, files, expected_problem):
    problems = validate(make_registry(files), config={"agent_name": "Ava"})

    assert any(expected_problem in problem for problem in problems), problems


def test_rejects_retrying_non_transient_errors(make_registry):
    tool = MINIMAL_TOOL.replace(
        "retry_on: [timeout]", "retry_on: [timeout, invalid_input]"
    )

    problems = validate(make_registry({"tools/read_thing.md": tool}))

    assert any("retries on 'invalid_input'" in problem for problem in problems)


def test_rejects_non_strict_input_schema(make_registry):
    tool = MINIMAL_TOOL.replace("  additionalProperties: false\n", "")

    problems = validate(make_registry({"tools/read_thing.md": tool}))

    assert any("additionalProperties: false" in problem for problem in problems)


def test_reports_variables_missing_from_config(make_registry):
    problems = validate(make_registry(), config={})

    assert any(
        "'{{agent_name}}', missing from config" in problem for problem in problems
    )


def test_confirmation_variables_must_be_config_or_tool_arguments(make_registry):
    confirmation = "---\nname: confirm_change_thing\nmode: fixed\ntrigger_kinds: [confirm_change_thing]\n---\n{{amount}}?"

    problems = validate(
        make_registry({"confirmations/confirm_change_thing.md": confirmation}),
        config={"agent_name": "A"},
    )

    assert any(
        "'{{amount}}', which is neither in config nor an argument" in problem
        for problem in problems
    )


@pytest.mark.parametrize(
    ("content", "expected_message"),
    [
        (
            "---\nname: other_name\ndescription: x\n---\nBody",
            "must match the file name",
        ),
        (
            "---\nname: reading\ndescription: x\ntriggers: [a]\n---\nBody",
            "Extra inputs are not permitted",
        ),
        ("No frontmatter here", "missing YAML frontmatter"),
    ],
)
def test_load_rejects_malformed_units(make_registry, content, expected_message):
    with pytest.raises(PromptLoadError, match=expected_message):
        make_registry({"skills/reading.md": content})


MINIMAL_TOOL = """---
name: read_thing
input_schema:
  type: object
  properties:
    thing_id: {type: string}
  required: [thing_id]
  additionalProperties: false
max_retries: 1
retry_on: [timeout]
---
Reads a thing.
"""
