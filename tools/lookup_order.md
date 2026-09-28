---
name: lookup_order
description: Look up an order by ID or customer email and return its status, amount, and date.
input_schema:
  type: object
  properties:
    order_id:
      type: string
    customer_email:
      type: string
  required: []
max_retries: 3
backoff_seconds: 1
retry_on: [timeout, 5xx]
no_retry_on: [not_found, validation_error]
---

Fetches order details from the orders system. Use this before making any
claim about eligibility or amounts.
