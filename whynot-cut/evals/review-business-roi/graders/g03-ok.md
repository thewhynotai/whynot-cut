---
type: regex
target:
  source: file
  path: example-clinic/output/projects/C0309/review-input.json
match: contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G03")(?=[^{}]*"flag"\s*:\s*"(?:business)")(?=[^{}]*"verdict"\s*:\s*"(?:ok)")
