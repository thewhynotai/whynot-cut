---
type: regex
target: trace
match: contains
---

"name":"Write"[^{]*?"input":\{(?:"file_path":"[^"]*C0315[\\/]+review-input\.json","content":"(?:[^"\\]|\\.)*?\{(?=(?:[^{}"\\]|\\.)*?\\"event_id\\"\s*:\s*\\"G02\\")(?=(?:[^{}"\\]|\\.)*?\\"flag\\"\s*:\s*\\"(?:ai)\\")(?=(?:[^{}"\\]|\\.)*?\\"verdict\\"\s*:\s*\\"(?:reword-to-match|remove|needs-approval)\\")|"content":"(?:[^"\\]|\\.)*?\{(?=(?:[^{}"\\]|\\.)*?\\"event_id\\"\s*:\s*\\"G02\\")(?=(?:[^{}"\\]|\\.)*?\\"flag\\"\s*:\s*\\"(?:ai)\\")(?=(?:[^{}"\\]|\\.)*?\\"verdict\\"\s*:\s*\\"(?:reword-to-match|remove|needs-approval)\\")(?:[^"\\]|\\.)*","file_path":"[^"]*C0315[\\/]+review-input\.json")
