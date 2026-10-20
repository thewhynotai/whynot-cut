---
type: regex
target:
  source: file
  path: example-talks/output/projects/C0306/review-input.json
match: contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G02")(?=[^{}]*"flag"\s*:\s*"(?:religious)")(?=[^{}]*"verdict"\s*:\s*"(?:needs-approval|reword-to-match|remove)")
