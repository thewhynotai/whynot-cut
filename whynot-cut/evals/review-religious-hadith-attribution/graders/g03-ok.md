---
type: regex
target:
  source: file
  path: example-talks/output/projects/C0305/review-input.json
match: contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G03")(?=[^{}]*"flag"\s*:\s*"(?:religious|medical)")(?=[^{}]*"verdict"\s*:\s*"(?:ok)")
