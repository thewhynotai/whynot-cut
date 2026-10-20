---
type: regex
target:
  source: file
  path: example-talks/output/projects/C0308/review-input.json
match: contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G01")(?=[^{}]*"flag"\s*:\s*"(?:religious|medical)")(?=[^{}]*"verdict"\s*:\s*"(?:ok)")
