---
name: read_file
input_schema:
  type: object
  properties:
    path:
      type: string
      description: Repository-relative file path.
    start_line:
      type: integer
      description: First line to return, starting at 1.
    max_lines:
      type: integer
      description: Maximum number of lines to return; 200 is a good default.
  required: [path, start_line, max_lines]
  additionalProperties: false
timeout_seconds: 10
max_retries: 1
retry_on: [timeout]
---
Returns a range of a file's lines, numbered, plus `total_lines`. Use it before explaining or changing a file, and read only the range you need. When `truncated` is true, `next_start_line` says where to continue. Returns `not_found` for missing paths; secret and credential files are refused with `secret_file_request`.
