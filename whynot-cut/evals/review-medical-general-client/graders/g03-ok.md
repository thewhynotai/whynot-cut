---
type: regex
target:
  source: file
  path: example-coach/output/projects/C0302/review-input.json
match: contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G03")(?=[^{}]*"flag"\s*:\s*"(?:medical)")(?=[^{}]*"verdict"\s*:\s*"(?:ok)")
