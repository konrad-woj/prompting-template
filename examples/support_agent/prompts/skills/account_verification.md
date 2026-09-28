---
name: account_verification
description: Verify the customer's identity before any account-specific help.
requires_tools: [verify_customer, escalate_to_human]
includes: [unverified_identity, tool_errors]
priority: 5
---
## Account verification

Ask for the order ID and the email address used for the order, then call `verify_customer`. If the customer gives only one, ask for the other. Ask one question at a time so the exchange stays easy to follow.
