---
name: search_code
input_schema:
  type: object
  properties:
    query:
      type: string
      description: Identifier, string literal or regular expression to search for.
  required: [query]
  additionalProperties: false
timeout_seconds: 10
max_retries: 1
retry_on: [timeout]
---
Searches the repository and returns up to 20 matches as `{"path", "line", "text"}`. Use identifiers or distinctive strings rather than natural-language questions. An empty `matches` list means nothing matched; try a different term before concluding the code doesn't exist.
