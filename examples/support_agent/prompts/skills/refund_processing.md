---
name: refund_processing
description: Check refund eligibility for an order and issue the refund.
requires_tools: [lookup_order, issue_refund, escalate_to_human]
includes: [tool_errors]
priority: 10
---
## Refund processing

1. Call `lookup_order` for the order. Use its `refund_eligible` and `refund_reason` fields as the answer on eligibility rather than working it out from dates yourself; the order system applies rules you can't see.
2. If eligible, call `issue_refund` with the order ID and the exact amount from the order record.
3. If not eligible, explain the reason in one sentence (the standard window is {{refund_window_days}} days from delivery) and offer `escalate_to_human` if they want an exception reviewed.
4. After a successful refund, confirm the amount and that it usually shows up within {{refund_processing_days}} business days.

<examples>
<example>
Eligible, refund succeeded: "Done - your refund of 42.00 EUR for order ORD-1042 is on its way and should reach you within {{refund_processing_days}} business days."
</example>
<example>
Not eligible: "Order ORD-0907 was delivered more than {{refund_window_days}} days ago, so it's outside our refund window. I can pass it to a colleague to review as an exception if you'd like."
</example>
<example>
Refund outcome unknown: "I've sent the refund request, but I can't confirm yet whether it went through. I've asked a colleague to check, and you'll hear back within 4 hours."
</example>
</examples>
