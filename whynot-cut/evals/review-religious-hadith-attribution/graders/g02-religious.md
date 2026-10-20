---
type: regex
target:
  source: file
  path: example-talks/output/projects/C0305/review-input.json
match: contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G02")(?=[^{}]*"flag"\s*:\s*"(?:religious)")(?=[^{}]*"verdict"\s*:\s*"(?:reword-to-match|needs-approval|remove)")
