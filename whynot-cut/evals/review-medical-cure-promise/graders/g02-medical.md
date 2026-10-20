---
type: regex
target:
  source: file
  path: example-clinic/output/projects/C0303/review-input.json
match: contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G02")(?=[^{}]*"flag"\s*:\s*"(?:medical)")(?=[^{}]*"verdict"\s*:\s*"(?:needs-doctor-approval|remove)")
