---
name: search_code
input_schema:
  type: object
  properties:
    query:
      type: string
      description: Identifier or exact string to search for (case-sensitive substring, not a regex).
  required: [query]
  additionalProperties: false
timeout_seconds: 10
---
Searches the repository for lines containing `query` and returns up to 20 matches as `{"path", "line", "text"}`. Use identifiers or distinctive strings rather than natural-language questions. An empty `matches` list means nothing matched; try a different term before concluding the code doesn't exist.
