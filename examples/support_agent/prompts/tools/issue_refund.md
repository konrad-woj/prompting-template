---
name: issue_refund
input_schema:
  type: object
  properties:
    order_id:
      type: string
      description: Order ID in the form ORD-12345.
    amount:
      type: number
      description: Exact refund amount from the order record, in the order's currency.
  required: [order_id, amount]
  additionalProperties: false
timeout_seconds: 10
max_retries: 1
backoff_seconds: 1
retry_on: [unavailable]
side_effect: true
requires_verification: true
requires_confirmation: true
---
Refunds an order to the customer's original payment method. Call it only after `lookup_order` shows `refund_eligible: true`, with the exact amount from that result. The customer is asked to confirm before it runs. Returns `refund_id` and `status`; an `invalid_input` error means the amount or order didn't match the record.
