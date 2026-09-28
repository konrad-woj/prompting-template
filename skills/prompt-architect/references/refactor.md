# Refactoring scattered prompts into prompt-kit

Incremental, baseline-first. Never rewrite everything at once.

## 0. Baseline

For the 10-20 most common (persona, intent) combinations, capture today's exact system prompt
and tool list (log what the current code sends). Save under `tests/baseline/`. This is the
regression reference until migration ends.

## 1. Inventory

Search for prompt text in code, e.g.:

```bash
rg -n --type py '("""|f""|system_prompt|SYSTEM|PROMPT|instructions|role.*system)' src/
rg -n --type py 'description\s*=' src/ | rg -i tool
```

List every string with `file:line`, what it is, and where it's concatenated. Show the list to
the user before moving anything.

## 2. Classify

| Found in code | Becomes |
|---|---|
| Text in every prompt (tone, format, safety) | `core/` or `guardrails/` |
| Per-deployment identity | `personas/<name>.md` with `allowed_tools` |
| `if task == ...: prompt += ...` | a skill + a `routing.yaml` entry |
| Tool docstrings/descriptions, JSON schemas | `tools/<name>.md` |
| Error/refusal strings sent to users verbatim | `mode: fixed` partial with `trigger_kinds` |
| Error/refusal guidance for the model | instruction partial in `errors/` or `refusals/` |
| Retry loops, "ask at most twice", auth checks in prompts | tool frontmatter + runtime, not prose |
| Values interpolated from config | `{{var}}` + `config.yaml` |
| Values interpolated from users/requests | `format_user_data` in the user turn |

## 3. Scaffold

Workflow A steps 2 and 4 from SKILL.md, with an empty routing table.

## 4. Migrate one unit group at a time

Order: core/guardrails (kills the most duplication), then one persona, then its most-used
skills, then tools. For each step: move the text, add routing, run validate, render the
baseline cases, diff against the baseline, and explain every difference to the user. Behind a
feature flag, keep the old path live until the persona matches.

## 5. Improve wording (separate step)

Only after behaviour matches the baseline, apply `writing-prompts.md`, one reviewed diff at a
time, and regenerate golden snapshots.

## 6. Decommission

Delete the old strings and the flag. Done when `rg` finds no prompt prose in `.py` files and
every prompt the harness sends can be printed with `prompt-kit render`.
