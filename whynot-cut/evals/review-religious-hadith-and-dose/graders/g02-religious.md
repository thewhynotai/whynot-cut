---
type: regex
target:
  source: file
  path: example-clinic/output/projects/C0307/review-input.json
match: contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G02")(?=[^{}]*"flag"\s*:\s*"(?:religious)")(?=[^{}]*"verdict"\s*:\s*"(?:needs-approval)")
