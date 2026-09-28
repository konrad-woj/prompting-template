---
name: code_navigation
description: Find and explain code in the repository.
requires_tools: [search_code, read_file]
includes: [tool_errors]
priority: 10
---
## Code navigation

Start with `search_code` using identifiers or distinctive strings from the question, then `read_file` the most relevant hits before explaining anything. Two or three targeted searches beat one broad one. Read only the line range you need; `read_file` tells you when there is more. When you explain behaviour, cite the lines that implement it.

<examples>
<example>
Question: "Where is retry backoff computed?"
Good searches: `def backoff_delay`, then `backoff_seconds` to find where the setting is read.
</example>
<example>
Question: "Why does the loop stop after a confirmation?"
Good searches: `confirmation_required`, then read the loop that handles that status rather than the tool that produces it.
</example>
</examples>
