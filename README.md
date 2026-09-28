# prompt-kit: prompting template for agent harnesses

A template for building an LLM agent's prompts as files instead of Python strings:

- One Markdown file with YAML frontmatter per persona, skill, tool, guardrail, error and refusal.
- Deterministic, table-driven skill routing. The system prompt is frozen after the first turn
  and later skills arrive in the user turn, so tools, system prompt and history stay cacheable.
- "Fixed" messages that are sent to the user word for word (compliance wording, confirmations),
  next to "instruction" messages that the model rephrases.
- Retries, idempotency, identity verification and user confirmation are enforced in code, not
  asked of the model.
- An async runtime with no ties to a particular model provider, plus an adapter for
  OpenAI-compatible APIs (OpenAI, Azure OpenAI, Gemini).
- A Claude Code skill, `prompt-architect`, that sets this up in new projects and refactors
  existing ones.

## Installation

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:konrad-woj/prompting-template.git
cd prompting-template
uv sync --all-extras          # runtime + openai client for the live example
uv run pytest                 # unit, loop and golden-snapshot tests
```

Install the Claude Code skill (once per machine) so Claude can use the template in any project:

```bash
ln -s "$PWD/skills/prompt-architect" ~/.claude/skills/prompt-architect
export PROMPT_KIT_TEMPLATE="$PWD"   # optional; the skill defaults to ~/Repo/Konrad/prompting-template
```

## Using it in a new project

With the skill installed, open Claude Code in the target project and ask, for example:

- "Set up prompts for this agent": Claude asks about personas, tools and wording that must stay
  exact, copies `src/prompt_kit/` and the `prompts/` starter, writes the prompt files and runs
  validation and golden snapshots.
- "Refactor our prompts, they're scattered across the code": Claude saves today's prompts as a
  baseline, lists every prompt string it finds, and migrates them one persona or skill at a time.
- "Add a tool that cancels subscriptions" or "Review our refusal prompts".

To set it up by hand, copy `src/prompt_kit/` and `prompts/` into your project, then add the
dependencies:

```bash
uv add pydantic pyyaml
uv add openai                      # only if you use the OpenAI-compatible adapter
uv add --dev pytest pytest-asyncio
```

## Layout

```
prompts/                     starter skeleton to copy into new projects
src/prompt_kit/
  models.py                  frontmatter schemas (unknown keys are rejected)
  loader.py                  Registry.load(root)
  render.py                  strict {{var}} substitution, tagged sections, format_user_data
  session.py                 PromptSession: sticky skills, fixed tools per persona
  runtime.py                 async retries, idempotency, verification/confirmation gates
  validate.py                cross-file checks
  adapters/openai.py         tool schemas, tool messages, ChatLoop
  cli.py                     prompt-kit validate | render | compile-tools
examples/
  support_agent/             refunds/billing: verification, confirmation, fixed messages
  research_agent/            codebase Q&A: read-only tools, untrusted content, a refusal raised by a tool
  live_gemini/               support agent against a real Gemini model
skills/prompt-architect/     Claude Code skill and its reference guides
tests/                       unit tests + golden snapshots of every routed prompt
```

The conventions (frontmatter fields, assembly order, what is enforced where) are in
[`skills/prompt-architect/references/conventions.md`](skills/prompt-architect/references/conventions.md).
Guidance on writing the prompt text is in
[`writing-prompts.md`](skills/prompt-architect/references/writing-prompts.md).

## Example use

### A prompt file

```markdown
---
name: refund_processing
description: Check refund eligibility for an order and issue the refund.
requires_tools: [lookup_order, issue_refund, escalate_to_human]
includes: [tool_errors]
priority: 10
---
## Refund processing

1. Call `lookup_order` for the order. Use its `refund_eligible` field ...
```

### Routing

```yaml
support_agent:
  refund_request: [account_verification, refund_processing]
  email_request: [account_verification, email_followup]
  default: [general_help]
```

### In a harness

```python
from pathlib import Path

from prompt_kit import PromptSession, Registry, ToolExecutor
from prompt_kit.adapters.openai import ChatLoop

registry = Registry.load(Path("prompts"))
session = PromptSession(registry, persona="support_agent", config={"agent_name": "Ava", ...})
executor = ToolExecutor(session, implementations={"lookup_order": lookup_order, ...})


async def complete(messages, tools):  # any OpenAI-compatible client
    response = await client.chat.completions.create(model=model, messages=messages, tools=tools)
    return response.choices[0].message.model_dump(include={"role", "content", "tool_calls"}, exclude_none=True)


loop = ChatLoop(session, executor, complete)
reply = await loop.send("I'd like a refund for ORD-1042", intent="refund_request")
```

Tool implementations are async functions. A tool marked `side_effect` also receives an
`idempotency_key`. On failure a tool raises `ToolError(kind, hint=..., **details)`. When a
message is `mode: fixed`, or a tool needs confirmation, `loop.send` returns the exact text
without calling the model.

### CLI

```bash
uv run prompt-kit validate --root examples/support_agent/prompts --config examples/support_agent/prompts/config.yaml
uv run prompt-kit render --root examples/support_agent/prompts --config examples/support_agent/prompts/config.yaml \
    --persona support_agent --intent refund_request --intent email_request
uv run prompt-kit compile-tools --root examples/support_agent/prompts --out build/tools.json
```

### Examples

```bash
uv run python -m examples.support_agent.run_mock     # offline, scripted model
uv run python -m examples.research_agent.run_mock    # offline, searches this repository
uv run --extra live --env-file .env python -m examples.live_gemini.loop   # needs GEMINI_API_KEY in .env
```

The live example uses Gemini's OpenAI-compatible endpoint with `gemini-2.5-flash` by
default. Override the model with `--model` or `GEMINI_MODEL`. Try "I want a refund for
ORD-1042" with the email `bob@example.com`.

## Updating golden snapshots

Every routed system prompt is snapshotted in `tests/golden/`. After an intended prompt change:

```bash
UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py
git diff tests/golden/    # review the change to what the model actually sees
```
