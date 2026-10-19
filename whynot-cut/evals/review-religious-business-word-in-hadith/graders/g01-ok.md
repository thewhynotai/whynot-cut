---
type: regex
target: trace
match: contains
---

"name":"Write"[^{]*?"input":\{(?:"file_path":"[^"]*C0308[\\/]+review-input\.json","content":"(?:[^"\\]|\\.)*?\{(?=(?:[^{}"\\]|\\.)*?\\"event_id\\"\s*:\s*\\"G01\\")(?=(?:[^{}"\\]|\\.)*?\\"flag\\"\s*:\s*\\"(?:religious|medical)\\")(?=(?:[^{}"\\]|\\.)*?\\"verdict\\"\s*:\s*\\"(?:ok)\\")|"content":"(?:[^"\\]|\\.)*?\{(?=(?:[^{}"\\]|\\.)*?\\"event_id\\"\s*:\s*\\"G01\\")(?=(?:[^{}"\\]|\\.)*?\\"flag\\"\s*:\s*\\"(?:religious|medical)\\")(?=(?:[^{}"\\]|\\.)*?\\"verdict\\"\s*:\s*\\"(?:ok)\\")(?:[^"\\]|\\.)*","file_path":"[^"]*C0308[\\/]+review-input\.json")
