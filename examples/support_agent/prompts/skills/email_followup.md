---
name: email_followup
description: Send the verified customer a follow-up or confirmation email.
requires_tools: [send_email]
includes: [tool_errors]
priority: 20
---
## Email follow-up

When the customer asks for something in writing, call `send_email` with a short subject and a plain-text body that summarises what was agreed in this conversation. The system sends it only to the verified email address on file, so don't ask for an address.
