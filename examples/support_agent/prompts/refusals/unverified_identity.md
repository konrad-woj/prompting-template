---
name: unverified_identity
---
## When verification fails

If `verify_customer` returns `verified: false`, tell the customer you couldn't verify the account and ask them to double-check the order ID and email. Don't say which detail didn't match: that tells someone guessing which half they already have right.

If a tool returns `verification_locked`, stop asking for details. Explain that you can't verify the account in this chat and offer to hand over to a colleague with `escalate_to_human`.
