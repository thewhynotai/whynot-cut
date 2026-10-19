---
type: regex
target: trace
match: contains
---

"name":"Write"[^{]*?"input":\{(?:"file_path":"[^"]*C0306[\\/]+review-input\.json","content":"(?:[^"\\]|\\.)*?\{(?=(?:[^{}"\\]|\\.)*?\\"event_id\\"\s*:\s*\\"G02\\")(?=(?:[^{}"\\]|\\.)*?\\"flag\\"\s*:\s*\\"(?:religious)\\")(?=(?:[^{}"\\]|\\.)*?\\"verdict\\"\s*:\s*\\"(?:needs-approval|reword-to-match|remove)\\")|"content":"(?:[^"\\]|\\.)*?\{(?=(?:[^{}"\\]|\\.)*?\\"event_id\\"\s*:\s*\\"G02\\")(?=(?:[^{}"\\]|\\.)*?\\"flag\\"\s*:\s*\\"(?:religious)\\")(?=(?:[^{}"\\]|\\.)*?\\"verdict\\"\s*:\s*\\"(?:needs-approval|reword-to-match|remove)\\")(?:[^"\\]|\\.)*","file_path":"[^"]*C0306[\\/]+review-input\.json")
