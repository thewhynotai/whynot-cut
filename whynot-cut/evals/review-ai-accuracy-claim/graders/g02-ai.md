---
type: regex
target:
  source: file
  path: example-clinic/output/projects/C0313/review-input.json
match: contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G02")(?=[^{}]*"flag"\s*:\s*"(?:ai)")(?=[^{}]*"verdict"\s*:\s*"(?:needs-approval)")
