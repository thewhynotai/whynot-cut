---
type: regex
target: last_message
match: not_contains
flags: i
---

\b(?:mv|ren|Rename-Item|Move-Item)\s[^\n]*(?:data[/\\]Raw|C02\d\d\.MP4)|(?:-o|>|-OutFile|-Destination)\s*[\"']?assets[/\\]
