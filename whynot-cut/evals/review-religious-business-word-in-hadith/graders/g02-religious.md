---
type: regex
target: trace
match: contains
---

"name":"Write"[^{]*?"input":\{(?:"file_path":"[^"]*C0308[\\/]+review-input\.json","content":"(?:[^"\\]|\\.)*?\{(?=(?:[^{}"\\]|\\.)*?\\"event_id\\"\s*:\s*\\"G02\\")(?=(?:[^{}"\\]|\\.)*?\\"flag\\"\s*:\s*\\"(?:religious)\\")(?=(?:[^{}"\\]|\\.)*?\\"verdict\\"\s*:\s*\\"(?:ok|needs-approval)\\")|"content":"(?:[^"\\]|\\.)*?\{(?=(?:[^{}"\\]|\\.)*?\\"event_id\\"\s*:\s*\\"G02\\")(?=(?:[^{}"\\]|\\.)*?\\"flag\\"\s*:\s*\\"(?:religious)\\")(?=(?:[^{}"\\]|\\.)*?\\"verdict\\"\s*:\s*\\"(?:ok|needs-approval)\\")(?:[^"\\]|\\.)*","file_path":"[^"]*C0308[\\/]+review-input\.json")
