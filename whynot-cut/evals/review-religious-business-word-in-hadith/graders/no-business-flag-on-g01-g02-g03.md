---
type: regex
target:
  source: file
  path: example-talks/output/projects/C0308/review-input.json
match: not_contains
---

\{(?=[^{}]*"event_id"\s*:\s*"(?:G01|G02|G03)")(?=[^{}]*"flag"\s*:\s*"(?:business)")(?=[^{}]*"verdict"\s*:\s*"(?:(?!ok")[a-z-]+)")
