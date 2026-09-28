---
name: escalate_to_human
input_schema:
  type: object
  properties:
    summary:
      type: string
      description: One or two sentences on what the customer needs and what has been tried.
  required: [summary]
  additionalProperties: false
timeout_seconds: 10
max_retries: 2
backoff_seconds: 1
retry_on: [unavailable]
side_effect: true
---
Hands the conversation to a human colleague. Use it when the customer asks for a person, when verification is locked, when an action's outcome is unknown, or when a request needs a policy exception. Returns `ticket_reference` and `expected_response_hours`, which you can share with the customer.
