---
type: regex
target:
  source: file
  path: example-clinic/output/projects/C0307/review-input.json
match: contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G02")(?=[^{}]*"flag"\s*:\s*"(?:medical)")(?=[^{}]*"verdict"\s*:\s*"(?:reword-to-match|needs-doctor-approval|remove)")
