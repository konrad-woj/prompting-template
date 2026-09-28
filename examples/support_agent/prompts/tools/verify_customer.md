---
name: verify_customer
input_schema:
  type: object
  properties:
    order_id:
      type: string
      description: Order ID in the form ORD-12345.
    email:
      type: string
      description: Email address the customer used for the order.
  required: [order_id, email]
  additionalProperties: false
timeout_seconds: 5
max_retries: 2
backoff_seconds: 0.5
retry_on: [timeout, unavailable]
grants_verification: true
---
Checks that an order ID and email address belong to the same customer account. Call it before any account-specific help, once you have both values from the customer. Returns `{"verified": true}` on a match and `{"verified": false}` otherwise; it never says which value was wrong. After repeated failures it returns a `verification_locked` error instead of checking again.
