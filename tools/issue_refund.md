---
name: issue_refund
description: Issue a refund for a given order ID and amount.
input_schema:
  type: object
  properties:
    order_id:
      type: string
    amount:
      type: number
  required: [order_id, amount]
max_retries: 1
backoff_seconds: 2
retry_on: [timeout, 5xx]
no_retry_on: [validation_error]
---

Issues a refund. Irreversible — only call after confirming eligibility
via `lookup_order`. Retries must be idempotent: the caller passes the
same idempotency key on retry so a network-level retry can never
double-refund. Retry budget is intentionally low (1) and never retries
on validation errors, since retrying a bad request just repeats the
same failure.
