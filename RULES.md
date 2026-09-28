# Prompt System — Rules & Migration Guide

Target: a large existing harness (30 skills, 60 tools, multiple personas)
currently built from Python strings/variables scattered and concatenated
ad hoc. Goal: deterministic, file-based, versioned prompt composition.

## 1. Core rules (non-negotiable)

1. **One file per unit.** Every skill, persona, tool description, and
   reusable fragment lives in its own `.md` file. No prompt text lives in
   `.py` files, ever — Python only loads, selects, and assembles.
2. **YAML frontmatter is metadata for the loader, never sent to the model.**
   `name`, `triggers`, `requires_tools`, `priority`, `includes` — parsed,
   then stripped before the body goes into a prompt.
3. **Templates are logic-free.** Bodies use plain `{{var}}` placeholders
   only (via `string.Template` or a minimal regex substitutor). No
   `{% if %}` / `{% for %}` inside prompt text. All branching — which
   skills apply, which fragments to include — happens in Python against
   the routing table, before rendering.
4. **Selection is deterministic and table-driven.** A single
   `routing.yaml` maps `(persona, intent/state) -> [skill names]`. No
   embeddings, no runtime LLM call to decide what to include. The table
   is reviewable in a PR like code.
5. **Every rendered section is wrapped in an XML-style tag** identifying
   what it is (`<persona>`, `<core_rules>`, `<skill name="...">`,
   `<tool_context>`, `<user_context>`). This is sent to the model — it
   is not decoration, it's how the model tracks provenance and where one
   instruction block ends and another begins.
6. **Assembly order is static-to-dynamic**: `core_rules → persona →
   selected skills (priority order) → tool schemas → dynamic user
   context`. This maximizes prompt-cache prefix hits, since everything
   before "dynamic user context" is byte-identical across requests with
   the same persona+skill-set.
7. **Tool descriptions are authored as markdown+frontmatter too**, and a
   build step compiles them to the JSON schema your API/tool-calling
   layer needs. The `.md` is the source of truth; the `.json` is
   generated, never hand-edited.
8. **Fragments are partials.** Small reusable snippets (guardrails, error
   recovery, disclaimers) live in `fragments/` and are pulled in via an
   `includes:` list in frontmatter — never copy-pasted across skill files.
9. **Nothing is included "just in case."** If a skill isn't selected by
   the routing table for this turn, its tokens are not in the prompt.
   Context budget at 60 tools is a real constraint — persona-scope your
   tool exposure the same way you persona-scope skills.
10. **Validate and snapshot-test the whole system**, not just individual
    files: every `routing.yaml` entry resolves to a real file, every
    `requires_tools`/`includes` reference exists, and golden-file tests
    catch accidental prompt drift when someone edits a skill.

## 2. Migration path for an existing, messy system

Do this incrementally — do not attempt a big-bang rewrite of 30 skills
and 60 tools at once.

**Step 0 — Freeze current behavior as a baseline.**
For your top 10–20 most common (persona, intent) combinations, capture
the *actual current* rendered prompt (print what your existing Python
concatenation produces today) and save each as a golden file. This is
your regression baseline — if the new renderer doesn't reproduce
equivalent behavior, you'll see it immediately instead of finding out
in production.

**Step 1 — Stand up the renderer and directory skeleton empty.**
Build `core/`, `personas/`, `skills/`, `tools/`, `fragments/`,
`routing.yaml`, and the renderer script (below) before moving a single
real skill over. Prove it works on one dummy skill end-to-end.

**Step 2 — Extract the core/base rules first.**
Find whatever text is currently duplicated across every persona
(safety, tone, output format) — it's usually copy-pasted or f-string
concatenated in several places. Consolidate it into one
`core/base_rules.md`. This alone usually kills a chunk of duplication.

**Step 3 — Migrate personas one at a time.**
For each persona, write `personas/<name>.md` with frontmatter declaring
its default skill set and allowed tools. Keep the old code path working
in parallel (feature-flagged) until the new one matches the baseline
for that persona.

**Step 4 — Migrate skills in priority order, not alphabetically.**
Start with the 5–10 skills that are used most often / are most
duplicated across personas. Each migration: extract the prose into
`skills/<name>.md`, fill frontmatter (`triggers`, `requires_tools`),
add its routing entries, run the golden-file test for any
(persona, intent) pair that touches it, diff against baseline, fix
discrepancies before moving to the next skill.

**Step 5 — Migrate tool descriptions and add the compile step.**
Move each tool's description out of wherever it's currently defined
(likely a Python dict or decorator) into `tools/<name>.md`, then write
the small compiler that emits the JSON schema your function-calling
layer expects. Keep the compiled JSON identical to what you have today
until you're ready to also revise wording.

**Step 6 — Turn on validation and CI.**
Add `validate_routes.py` (checks referential integrity) and the
snapshot tests to CI so future edits can't silently break composition.

**Step 7 — Decommission the old path.**
Once every persona routes through the new system and baselines match,
delete the scattered Python string variables. Don't leave both paths
alive longer than migration requires — that's exactly the drift risk
you're trying to eliminate.

## 3. Guardrails, refusals, errors, and retries

These are four distinct categories with different placement rules — do
not lump them into a single generic "guardrails" folder.

| Category | Directory | What it is | Always sent? |
|---|---|---|---|
| Guardrails | `guardrails/` | Unconditional safety/scope boundaries — never overridden by skill, persona, or user | Yes, every request, like `core/` |
| Refusals | `refusals/` | Reusable patterns for *how* to decline (out-of-scope, unverified identity) | No — pulled in via a skill's `includes:` |
| Errors | `errors/` | What to tell the user when a tool fails, times out, or rejects input | No — pulled in via a skill's `includes:` |
| Retries | tool frontmatter + `tool_runtime.py` | Actual retry count/backoff — enforced in **code**, not prompt text | N/A — this is not prompt text |

### 3a. Instruction vs. fixed — are errors/refusals "really prompts"?

Every file in `errors/` and `refusals/` declares `mode: instruction`
(default) or `mode: fixed`, and the two behave completely differently:

- **`mode: instruction`** — a real prompt. The model reads it as
  guidance and generates its own wording, adapted to conversation flow
  and persona tone. Output varies call to call by design. This is what
  most error/refusal copy should be — a tool timing out reads more
  naturally as "Hmm, that's taking longer than expected" woven into
  context than as a dropped-in canned line.
- **`mode: fixed`** — not a prompt at all. It's a literal string with
  `{{var}}` substitution only, returned directly to the user via
  `get_fixed_for_kind()` with **no LLM call**. Use this for wording that
  must be exact and legally/compliance-reviewed every time — a
  PII-disclosure refusal, a rate-limit notice, anything where phrasing
  variance is a liability rather than a feature.

A `mode: fixed` file can never appear in a skill's `includes:` list —
`render.py --validate` rejects that at CI time, because stuffing a
literal user-facing string into a prompt as if it were an instruction
defeats the entire point of declaring it fixed. Instead, fixed files
declare `trigger_kinds` (e.g. `rate_limited`, `pii_disclosure_request`)
and get looked up by kind at the exact moment that condition fires —
from `tool_runtime.py`'s `handle_failure()` after a tool error, or from
any other classifier/guard in your app that raises a named condition.
Validation also rejects two fixed files claiming the same
`trigger_kind`, since that's an ambiguous "which one fires" situation
you want caught before runtime, not after.

Key distinction: guardrails/refusals/errors are all prompt **text** —
they live in the includable pool (`fragments/`, `errors/`, `refusals/`
are functionally identical to the loader; the separate directories are
for human organization only). Retries are different in kind: "retry 3
times with backoff" is a runtime decision, not something you want the
model deciding turn-to-turn. Declare the policy once, in the tool's own
`.md` frontmatter (`max_retries`, `backoff_seconds`, `retry_on`,
`no_retry_on`), and:
- the **prompt** gets a short fragment (`fragments/retry_policy.md`)
  telling the model retries are handled for it and not to re-call a
  tool itself after a hard failure;
- the **code** (`tool_runtime.py`) reads the same frontmatter fields to
  actually execute the retry/backoff.

This is the one place a validator check earns its keep: `render.py
--validate` flags any tool that allows retries without excluding
`validation_error` from `no_retry_on` — retrying a malformed request
just repeats the same failure and burns latency for nothing. For any
tool with a real-world side effect (refund, deletion, email send),
require an idempotency key on every call so a network-level retry can
never double-execute it.

Where to attach guardrails/refusals/errors:
- **Global, no exceptions** → `guardrails/`, always rendered right after
  `core_rules`, before persona — so it reads first and is easy to audit
  as one block.
- **Scoped to a specific skill's failure modes** → put the include in
  that skill's frontmatter (e.g. `account_verification` includes
  `unverified_identity`; `refund_processing` includes `tool_failure`,
  `timeout`, `retry_policy`). Don't make every skill include everything
  — only what its own tools/actions can actually trigger.

## 4. What "done" looks like

- Grep for prompt text in `.py` files returns nothing.
- Every skill/persona/tool/fragment is a reviewable, diffable file.
- `python render.py --persona X --intent Y` prints the exact prompt
  that would be sent, for any combination, with no live LLM call.
- Adding a new skill means: write one `.md` file, add one routing entry,
  run tests. No hunting through Python for where to splice it in.
