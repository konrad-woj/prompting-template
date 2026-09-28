---
name: rate_limited
mode: fixed
trigger_kinds: [rate_limited]
---
You're sending requests a bit faster than we can process them. Please wait about {{retry_after_seconds}} seconds and try again. If this keeps happening, contact support at {{support_email}}.
