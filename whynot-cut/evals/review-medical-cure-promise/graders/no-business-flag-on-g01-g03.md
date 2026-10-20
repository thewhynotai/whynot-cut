---
type: regex
target:
  source: file
  path: example-clinic/output/projects/C0303/review-input.json
match: not_contains
---

\{(?=[^{}]*"event_id"\s*:\s*"(?:G01|G03)")(?=[^{}]*"flag"\s*:\s*"(?:business)")(?=[^{}]*"verdict"\s*:\s*"(?:(?!ok")[a-z-]+)")
