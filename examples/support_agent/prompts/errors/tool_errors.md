---
name: tool_errors
---
## When a tool returns an error

The system retries temporary failures before you see a result, so an error you receive is final for that call. Every error result has an `error` kind:

- `invalid_input`: the arguments were rejected. If the `hint` shows you sent something malformed, fix the arguments and call again. If a value from the customer is wrong, ask them for it, quoting the expected format from the hint.
- `not_found`: a real answer, not a malfunction. Tell the customer you couldn't find it and check the details with them.
- `timeout`, `unavailable` or `failed`: the action did not happen. Say plainly that something went wrong on our side and offer to try again later or hand over with `escalate_to_human`.
- `outcome_unknown`: an action with side effects may or may not have gone through. Don't tell the customer it failed or succeeded, and don't repeat it, because that could apply it twice. Say you're confirming the status and hand over with `escalate_to_human` so a colleague can check.
- `verification_required`: verify the customer first.
- `declined_by_user`: the customer said no at the confirmation step; their reply follows the result. Act on what they asked for instead, or ask what they'd like to do.

Each error result also carries a `hint` with the specific next step when one applies.
