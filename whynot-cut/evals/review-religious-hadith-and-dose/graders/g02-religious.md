---
type: regex
target: trace
match: contains
---

"name":"Write"[^{]*?"input":\{(?:"file_path":"[^"]*C0307[\\/]+review-input\.json","content":"(?:[^"\\]|\\.)*?\{(?=(?:[^{}"\\]|\\.)*?\\"event_id\\"\s*:\s*\\"G02\\")(?=(?:[^{}"\\]|\\.)*?\\"flag\\"\s*:\s*\\"(?:religious)\\")(?=(?:[^{}"\\]|\\.)*?\\"verdict\\"\s*:\s*\\"(?:ok|reword-to-match|needs-approval|remove)\\")|"content":"(?:[^"\\]|\\.)*?\{(?=(?:[^{}"\\]|\\.)*?\\"event_id\\"\s*:\s*\\"G02\\")(?=(?:[^{}"\\]|\\.)*?\\"flag\\"\s*:\s*\\"(?:religious)\\")(?=(?:[^{}"\\]|\\.)*?\\"verdict\\"\s*:\s*\\"(?:ok|reword-to-match|needs-approval|remove)\\")(?:[^"\\]|\\.)*","file_path":"[^"]*C0307[\\/]+review-input\.json")
