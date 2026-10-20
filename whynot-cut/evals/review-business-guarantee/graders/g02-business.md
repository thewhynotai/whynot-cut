---
type: regex
target:
  source: file
  path: example-clinic/output/projects/C0310/review-input.json
match: contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G02")(?=[^{}]*"flag"\s*:\s*"(?:business)")(?=[^{}]*"verdict"\s*:\s*"(?:needs-approval)")
