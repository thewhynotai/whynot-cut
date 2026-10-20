---
type: regex
target:
  source: file
  path: example-coach/output/projects/C0302/review-input.json
match: not_contains
---

\{(?=[^{}]*"event_id"\s*:\s*"(G\d\d)")(?=[^{}]*"flag"\s*:\s*"([a-z]+)")[^{}]*\}[\s\S]*?\{(?=[^{}]*"event_id"\s*:\s*"\1")(?=[^{}]*"flag"\s*:\s*"\2")
