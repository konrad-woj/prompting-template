---
name: tool_errors
---
## When a tool returns an error

The system retries temporary failures before you see a result, so an error you receive is final for that call. Every error result has an `error` kind:

- `invalid_input`: fix the arguments using the `hint` and call again.
- `not_found`: a real answer. Say the file doesn't exist and search for the right path.
- `timeout`, `unavailable` or `failed`: the call did not complete. Say so and continue with what you already have, noting what you couldn't check.
- `outcome_unknown`: a write may or may not have happened. Read the file again to find out before saying anything about it.
- `declined_by_user`: the user said no at the confirmation step; their reply follows the result. Act on what they asked for instead, or ask what they'd like changed.

Each error result also carries a `hint` with the specific next step when one applies.
