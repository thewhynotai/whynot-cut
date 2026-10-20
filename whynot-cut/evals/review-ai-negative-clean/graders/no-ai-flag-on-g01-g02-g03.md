---
type: regex
target:
  source: file
  path: example-clinic/output/projects/C0316/review-input.json
match: not_contains
---

\{(?=[^{}]*"event_id"\s*:\s*"(?:G01|G02|G03)")(?=[^{}]*"flag"\s*:\s*"(?:ai)")(?=[^{}]*"verdict"\s*:\s*"(?:(?!ok")[a-z-]+)")
