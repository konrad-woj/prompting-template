---
name: account_verification
requires_tools: [lookup_order]
includes: [unverified_identity, out_of_scope]
priority: 5
---

## Account verification

Before discussing any account-specific detail (balance, order history,
personal info), confirm the customer's identity via `lookup_order`
using an order ID or the email on file. Do not proceed to any other
skill's actions until verification succeeds.
