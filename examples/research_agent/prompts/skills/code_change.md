---
name: code_change
description: Propose and apply a small, confirmed file change.
requires_tools: [read_file, write_file]
includes: [tool_errors]
priority: 30
---
## Code change

1. `read_file` the whole target file first so the change is based on its current content.
2. Describe the change in one or two sentences, then call `write_file` with the complete new file content.
3. Keep changes minimal and in the file's existing style; larger refactors deserve a plan the user agrees to first.
