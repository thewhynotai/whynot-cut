---
type: regex
target: trace
match: not_contains
---

"name":"Write"[^{]*?"input":\{(?:"file_path":"[^"]*C0308[\\/]+review-input\.json","content":"(?:[^"\\]|\\.)*?\{(?=(?:[^{}"\\]|\\.)*?\\"event_id\\"\s*:\s*\\"(?:G01|G02|G03)\\")(?=(?:[^{}"\\]|\\.)*?\\"flag\\"\s*:\s*\\"(?:business)\\")(?=(?:[^{}"\\]|\\.)*?\\"verdict\\"\s*:\s*\\"(?:(?!ok\\")[a-z-]+)\\")|"content":"(?:[^"\\]|\\.)*?\{(?=(?:[^{}"\\]|\\.)*?\\"event_id\\"\s*:\s*\\"(?:G01|G02|G03)\\")(?=(?:[^{}"\\]|\\.)*?\\"flag\\"\s*:\s*\\"(?:business)\\")(?=(?:[^{}"\\]|\\.)*?\\"verdict\\"\s*:\s*\\"(?:(?!ok\\")[a-z-]+)\\")(?:[^"\\]|\\.)*","file_path":"[^"]*C0308[\\/]+review-input\.json")
