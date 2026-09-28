---
name: lookup_order
input_schema:
  type: object
  properties:
    order_id:
      type: string
      description: Order ID in the form ORD-12345.
  required: [order_id]
  additionalProperties: false
timeout_seconds: 5
max_retries: 3
backoff_seconds: 0.5
retry_on: [timeout, unavailable]
requires_verification: true
---
Fetches an order from the order system. Use it before saying anything about an order's status, amount, dates or refund eligibility. Returns `order_id`, `status`, `amount`, `currency`, `delivered_on`, `refund_eligible` and `refund_reason`. Returns a `not_found` error when no order has that ID, which is an answer to relay, not a malfunction.
