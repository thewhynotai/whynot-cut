---
type: regex
target:
  source: file
  path: example-clinic/output/projects/C0312/review-input.json
match: not_contains
---

\{(?=[^{}]*"event_id"\s*:\s*"(?:G01|G02|G03)")(?=[^{}]*"flag"\s*:\s*"(?:business)")(?=[^{}]*"verdict"\s*:\s*"(?:(?!ok")[a-z-]+)")
