---
name: invalid_input
mode: instruction
---

If a tool rejects the input as invalid (bad order ID format, missing
required field):
1. Don't retry with a guessed correction — ask the customer for the
   correct value.
2. State exactly what's needed (e.g. "order IDs look like ORD-12345")
   without exposing raw schema/validation error text.
