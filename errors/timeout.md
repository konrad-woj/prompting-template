---
name: timeout
mode: instruction
---

If a tool call times out:
1. Tell the customer the lookup is taking longer than expected — don't
   pretend it succeeded or failed.
2. The system will have already retried per the tool's `max_retries`
   before surfacing this to you; do not ask the customer to "try again"
   more than once yourself.
3. If it's still unresolved, offer to follow up by email instead of
   holding the conversation open indefinitely.
