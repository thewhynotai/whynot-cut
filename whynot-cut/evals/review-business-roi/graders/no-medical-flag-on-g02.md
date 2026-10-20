---
type: regex
target:
  source: file
  path: example-clinic/output/projects/C0309/review-input.json
match: not_contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G02")(?=[^{}]*"flag"\s*:\s*"(?:medical)")(?=[^{}]*"verdict"\s*:\s*"(?:(?!ok")[a-z-]+)")
