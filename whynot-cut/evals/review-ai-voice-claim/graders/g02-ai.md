---
type: regex
target:
  source: file
  path: example-clinic/output/projects/C0315/review-input.json
match: contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G02")(?=[^{}]*"flag"\s*:\s*"(?:ai)")(?=[^{}]*"verdict"\s*:\s*"(?:reword-to-match|remove|needs-approval)")
