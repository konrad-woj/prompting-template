---
name: retry_policy
---

Retries for tool calls are handled by the system, not by you deciding to
call the same tool again. Each tool declares its own retry budget
(`max_retries`, `backoff_seconds` in its definition). If you receive a
final failure after retries are exhausted, treat it as a hard failure —
follow the matching error fragment (tool_failure / timeout /
invalid_input) rather than calling the tool again yourself.
