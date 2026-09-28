# prompt-kit conventions

## Layout

```
prompts/
  core/          always sent first: how the agent works, instruction priority
  guardrails/    always sent: boundaries no skill, persona or user can override
  personas/      who the agent is for a deployment; declares allowed_tools
  skills/        task instructions, selected by routing.yaml
  tools/         tool descriptions (body) + JSON schema and runtime policy (frontmatter)
  errors/        partials: how to respond to tool error kinds
  refusals/      partials: how to decline
  fragments/     partials: anything else reusable
  confirmations/ fixed partials `confirm_<tool>` shown before a confirmed tool runs
  routing.yaml   persona -> intent -> [skills]; every persona needs `default`
  config.yaml    trusted operator variables for {{var}} substitution
```

`errors/`, `refusals/`, `fragments/` and `confirmations/` are one namespace ("partials");
names must be unique across them. Every file's `name` equals its file stem.

## Frontmatter

| Kind | Fields |
|---|---|
| core, guardrails | `name` |
| persona | `name`, `description`, `allowed_tools` |
| skill | `name`, `description`, `requires_tools`, `includes`, `priority` (lower first within one activation) |
| tool | `name`, `input_schema` (strict: closed objects, all properties required), `timeout_seconds`, `max_retries`, `backoff_seconds`, `retry_on` (only `timeout`, `unavailable`, `rate_limited`), `side_effect`, `requires_verification`, `requires_confirmation`, `grants_verification` |
| partial | `name`, `mode` (`instruction` default, or `fixed`), `trigger_kinds` (fixed only) |

Unknown keys fail loading, so typos surface immediately.

## Assembly

System prompt = core -> guardrails -> persona -> skills active at the first model call, each
skill followed by its `<guidance>` partials. Each section is wrapped in a named tag.

- Sticky routing: a `PromptSession` only adds skills as intents arrive. The system prompt is
  frozen at the first model call; skills activated later are prepended to the next user
  message (`take_late_instructions`). Tools are fixed per persona. Together this keeps tools,
  system prompt and history byte-identical, so the provider's prompt cache keeps hitting.
- Verification state is not in the prompt: the model learns it from the verification tool's
  result, and code blocks gated tools until then.
- A partial shared by several skills is rendered once, in its own `<guidance>` section.
- Rules that must hold regardless of routing (e.g. out-of-scope handling) go in guardrails,
  not in a partial that only some skills include.
- `{{var}}` comes from `config.yaml` only; a missing variable raises.
- Untrusted data (user profile, retrieved text) goes in the user turn via `format_user_data`,
  escaped, never into the system prompt.

## Instruction vs fixed

- `instruction`: guidance the model paraphrases. Default for errors and refusals.
- `fixed`: exact text sent to the user without a model call, found by `trigger_kinds`.
  Use for compliance wording and confirmations. Never `includes:`-ed into a skill.
  Variables come from config plus the error's details (or the tool arguments for
  `confirm_<tool>`).

## Runtime (enforced in code)

- Retries: `call_tool_with_retry` honours `max_retries`/`retry_on`, exponential backoff with
  jitter or the error's `retry_after_seconds`, and a per-attempt timeout.
- Side effects: the executor derives an idempotency key from (session, tool, arguments) and
  passes it as `idempotency_key`; a timed-out side effect is reported as `outcome_unknown`.
- Verification: `requires_verification` tools are blocked until a `grants_verification` tool
  returns `{"verified": true}`; after `max_verification_attempts` failures it locks.
- Confirmation: `requires_confirmation` tools pause, show `confirm_<tool>`, and run only on an
  explicit yes; a no returns `declined_by_user` to the model.
- Tool results are JSON facts (`error`, `outcome_known`, `hint`, details); behaviour guidance
  stays in the prompt partials.

## Validation (`prompt-kit validate`)

Routing references, persona tool coverage for every routed skill, fixed partials not
included, unique trigger kinds and partial names, non-transient retries, strict schemas,
`confirm_<tool>` presence and variables, and (with `--config`) every `{{var}}` resolvable.
