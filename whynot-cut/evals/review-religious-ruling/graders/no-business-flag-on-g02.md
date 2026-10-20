---
type: regex
target:
  source: file
  path: example-talks/output/projects/C0306/review-input.json
match: not_contains
---

\{(?=[^{}]*"event_id"\s*:\s*"G02")(?=[^{}]*"flag"\s*:\s*"(?:business)")(?=[^{}]*"verdict"\s*:\s*"(?:(?!ok")[a-z-]+)")
