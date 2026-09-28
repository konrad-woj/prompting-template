---
name: write_file
input_schema:
  type: object
  properties:
    path:
      type: string
      description: Repository-relative file path.
    content:
      type: string
      description: Complete new file content.
  required: [path, content]
  additionalProperties: false
timeout_seconds: 10
side_effect: true
requires_confirmation: true
---
Overwrites a file with new content. Read the file first and send the complete new content, not a diff. The user is asked to confirm before it is written. Returns `{"path", "bytes_written"}`.
