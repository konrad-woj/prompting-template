---
name: prompt-architect
description: Design, scaffold, or refactor the prompting of an LLM agent or harness using the prompt-kit template (one Markdown+frontmatter file per persona/skill/tool/error/refusal, deterministic routing, fixed vs generated messages, code-enforced retries, verification and confirmation). Use when the user wants to set up prompts for a new agent project, move prompt strings scattered through Python into files, add or change a persona/skill/tool/guardrail/error/refusal, or review prompt quality. Triggers on "set up prompts", "prompt structure", "refactor our prompts", "prompts are scattered", "add a skill/tool/persona", "system prompt design", "agent harness prompts", "refusal/error messages".
---

# Prompt Architect

Builds and maintains an agent's prompting with the prompt-kit template: prompt text lives in
`prompts/` as one file per unit, Python only loads, routes and assembles it, and anything that
must hold every time (retries, verification, confirmation, exact compliance wording) is
enforced in code rather than asked of the model.

Template source: `$PROMPT_KIT_TEMPLATE`, else `~/Repo/Konrad/prompting-template`, else clone
`git@github.com:konrad-woj/prompting-template.git` into a temp dir. Read its `README.md` first.

## Pick the workflow

| Situation | Workflow |
|---|---|
| New project, no prompts yet | A. Scaffold |
| Prompt strings in code (f-strings, constants, concatenation) | B. Refactor (read `references/refactor.md`) |
| Existing prompt-kit project, change requested | C. Change a unit |
| "Are our prompts any good?" | D. Review |

Always read `references/conventions.md` before writing units and
`references/writing-prompts.md` before writing any prompt prose.

## A. Scaffold

1. Interview before writing anything; ask only what the code can't tell you:
   - Personas and who their users are.
   - Tools, and for each: read-only or side effect? needs a verified user? needs user confirmation?
   - Wording that must be exact every time (legal, compliance, privacy) -> `mode: fixed`.
   - Model provider (the adapter targets OpenAI-compatible Chat Completions: OpenAI, Azure
     OpenAI, Gemini's compatibility endpoint). Async harness? (runtime is async).
2. Copy from the template into the project:
   - `src/prompt_kit/` -> the project's source root (keep the package name).
   - `prompts/` starter skeleton -> project root.
   - `tests/test_golden.py` and the `EXAMPLE_PROMPT_DIRS`/`load_example_config` helpers from
     `tests/conftest.py`, pointed at the project's `prompts/`.
   - `uv add pydantic pyyaml` (and `openai` for a live loop); `uv add --dev pytest pytest-asyncio`.
3. Author units from the interview, using the examples in the template as models:
   `examples/support_agent/prompts` (verification, confirmation, fixed messages) and
   `examples/research_agent/prompts` (read-only tools, untrusted content, tool-raised refusal).
4. Wire the harness: `PromptSession` per conversation, `ToolExecutor` with the tool
   implementations, `ChatLoop` (or your own loop following its message rules).
5. Verify: `uv run prompt-kit validate --root prompts --config prompts/config.yaml`,
   `UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py`, then `uv run pytest`.

## B. Refactor scattered prompts

Follow `references/refactor.md`: freeze a baseline of today's rendered prompts, inventory and
classify every prompt string, migrate one persona/skill at a time with a diff against the
baseline, then delete the old strings. Never big-bang.

## C. Change a unit

1. Find the unit and everything that references it (`routing.yaml`, `includes:`, persona
   `allowed_tools`, `confirm_<tool>` partials).
2. Edit following `references/writing-prompts.md`; one rule lives in one place.
3. Run validate, then `uv run pytest tests/test_golden.py`. Show the user the snapshot diff,
   and regenerate with `UPDATE_GOLDEN=1` only after they accept it.

## D. Review

Check against `references/writing-prompts.md` and report, most severe first:
- Rules the prompt asks of the model that code should enforce (authorization, retries, counts).
- Prompts that promise actions no tool provides, or tools a persona can't use.
- Conflicting or duplicated rules across core/guardrails/persona/skills.
- Bare NEVER/ALWAYS rules without a reason; missing "what to do instead".
- Error handling that treats `not_found` as failure or has no `outcome_unknown` path.
- Tool descriptions under 3 sentences or missing return shape and error kinds.

## Rules for Claude

- Prompt prose never goes in `.py` files. Code references units by name only.
- Don't add a unit "just in case"; every skill must be routed and every tool allowed by a persona.
- Keep `prompts/config.yaml` to trusted operator values; user or request data goes through
  `format_user_data` into the user turn, never into `config`.
