---
type: regex
target:
  source: file
  path: example-clinic/output/projects/C0314/review-input.json
match: contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G03")(?=[^{}]*"flag"\s*:\s*"(?:medical)")(?=[^{}]*"verdict"\s*:\s*"(?:ok)")
