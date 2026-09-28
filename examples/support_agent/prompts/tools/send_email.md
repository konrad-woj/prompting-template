---
name: send_email
input_schema:
  type: object
  properties:
    subject:
      type: string
      description: Short subject line.
    body:
      type: string
      description: Plain-text body summarising what was agreed.
  required: [subject, body]
  additionalProperties: false
timeout_seconds: 10
side_effect: true
requires_verification: true
requires_confirmation: true
---
Emails the verified customer at the address on their account; you can't choose the recipient. Use it when the customer asks for a written summary or confirmation. Keep the body plain text without internal IDs or jargon. The customer is asked to confirm before it is sent.
