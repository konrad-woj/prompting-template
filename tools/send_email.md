---
name: send_email
description: Send a confirmation or follow-up email to the customer.
input_schema:
  type: object
  properties:
    to:
      type: string
    subject:
      type: string
    body:
      type: string
  required: [to, subject, body]
---

Sends an email on behalf of the support agent. Never include internal
ticket IDs or jargon in the body.
