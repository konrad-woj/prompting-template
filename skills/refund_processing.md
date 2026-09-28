---
name: refund_processing
requires_tools: [lookup_order, issue_refund]
includes: [tool_failure, timeout, retry_policy]
priority: 10
---

## Refund processing

1. Look up the order using `lookup_order` before saying anything about
   eligibility.
2. Refunds are allowed within {{refund_window_days}} days of purchase.
3. If eligible, call `issue_refund` with the exact order amount — never
   round or estimate.
4. Confirm the refund to the customer in one sentence, including the
   amount and expected processing time.
