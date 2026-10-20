---
type: regex
target:
  source: file
  path: example-coach/output/projects/C0302/review-input.json
match: not_contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G02")(?=[^{}]*"flag"\s*:\s*"(?:medical)")(?=[^{}]*"verdict"\s*:\s*"(?:ok)")
