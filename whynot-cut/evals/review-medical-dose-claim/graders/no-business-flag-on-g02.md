---
type: regex
target:
  source: file
  path: example-clinic/output/projects/C0301/review-input.json
match: not_contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G02")(?=[^{}]*"flag"\s*:\s*"(?:business)")(?=[^{}]*"verdict"\s*:\s*"(?:(?!ok")[a-z-]+)")
