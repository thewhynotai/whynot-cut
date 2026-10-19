"""Fail on CSS or markup the UXP kit cannot paint, and on copy that breaks the rules, in the mockup sources.

    python adobe/panel-ui/design/_build/check_css.py

Scans design/*.css, design/*.js (except the generated icons.js), design/css/*.css, design/js/*.js, design/strings/*.js
and design/screens/*.html (R2 designer P2-15: the group files were never scanned). Forbidden: shadows, effects, the flex
spacing property, the two-dimensional layout module, the native button element, an SVG fill attribute, the
inherited-colour keyword, logical inline margins, and @font-face anywhere except mockup.css (mockup-only). In the
strings files it also checks the VALUES: no "engine" / "المحرك" (it is "WhyNot Cut service"), never "Claude Code" in
panel copy, and every link on the allowlist (https thewhynot.ai, dl.thewhynot.ai, claude.ai, support.claude.com,
code.claude.com; wa.me ONLY for the support chat, MOCK_DATA.support.url in strings.js: D-05 update 2026-10-16,
eng-data-contract §7.10). Every copy file: no command (`reel setup`, `reel brand-fetch`, ... : Addendum C1.4, J-T9c's
banned `reel `). The copy files in DEV_WORD_FILES (the J12 group, J-T9a) also carry Addendum J5.2's developer-word
denylist: JSON, CSS, robots, sha256, token, daemon, CLI (the other groups' copy predates it and their sample DATA
legitimately holds e.g. a plan fingerprint). Prints one line per hit and a summary line; exit 1 on any hit.
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

DESIGN = pathlib.Path(__file__).resolve().parent.parent
# code files: substring match, as before. strings files hold copy, so only the copy rules apply to them.
FORBIDDEN = ["box-shadow", "filter", "gap:", "grid", "<button", 'fill="', "currentColor", "margin-inline"]
JS_PATTERNS = {  # the JS group files use words like Array.filter(); match the CSS-ish forms only
    "box-shadow": r"box-shadow", "filter:": r"filter\s*:", "gap:": r"(?<![\w-])(row-|column-)?gap\s*:",
    "grid": r"display\s*:\s*grid|grid-template|grid-area", "<button": r"<button", 'fill="': r'fill="',
    "currentColor": r"currentColor", "margin-inline": r"margin-inline",
}
ALLOWED_HOSTS = {"thewhynot.ai", "www.thewhynot.ai", "dl.thewhynot.ai", "claude.ai", "support.claude.com", "code.claude.com"}
SUPPORT_ONLY = {"wa.me"}  # the WhatsApp support chat: allowed only as support.url (the `support:` line of MOCK_DATA)
VALUE = re.compile(r'"((?:[^"\\]|\\.)*)"')
# a WhyNot Cut command in copy (C1.4): lower-case "reel" + one of its sub-commands, as typed; "a 52 s reel on ..." and
# "Reel edit:" are nouns, not hits
COMMAND = re.compile(r"\breel\s+(?:setup|doctor|serve|scaffold|client-init|inbox|next|lock|watch|needs-you|brand-[a-z]+)\b")
DEV_WORD_FILES = {"strings/client-setup.js", "strings/panel-v1.js"}
DEV_WORDS = re.compile(r"\b(?:JSON|CSS|robots|sha256|token|daemon|CLI)\b", re.I)


def main() -> int:
    code = (sorted(DESIGN.glob("*.css")) + sorted(DESIGN.glob("css/*.css")) +
            sorted(p for p in DESIGN.glob("*.js") if p.name not in ("icons.js", "strings.js")) + sorted(DESIGN.glob("js/*.js")) +
            sorted((DESIGN / "screens").glob("*.html")))
    copy = [DESIGN / "strings.js"] + sorted(DESIGN.glob("strings/*.js"))
    hits = 0
    for f in code:
        rel = f.relative_to(DESIGN).as_posix()
        is_js = f.suffix == ".js"
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            low = line.lower()
            if is_js:
                for tok, rx in JS_PATTERNS.items():
                    if re.search(rx, line, re.I):
                        hits += 1
                        print(f"{rel}:{n}: forbidden '{tok}': {line.strip()[:100]}")
            else:
                for tok in FORBIDDEN:
                    if tok.lower() in low:
                        hits += 1
                        print(f"{rel}:{n}: forbidden '{tok}': {line.strip()[:100]}")
            if "@font-face" in line and rel != "mockup.css":
                hits += 1
                print(f"{rel}:{n}: forbidden '@font-face' outside mockup.css: {line.strip()[:100]}")
    for f in copy:
        rel = f.relative_to(DESIGN).as_posix()
        in_block = False
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            code_part = ""
            rest = line
            while rest:  # keep only the code outside /* ... */ comments (comments may span lines)
                if in_block:
                    end = rest.find("*/")
                    if end < 0:
                        rest = ""
                    else:
                        in_block, rest = False, rest[end + 2:]
                else:
                    start = rest.find("/*")
                    if start < 0:
                        code_part += rest
                        rest = ""
                    else:
                        code_part += rest[:start]
                        in_block, rest = True, rest[start + 2:]
            code_part = re.sub(r'"[\w.\-]+"\s*:', " ", code_part)  # drop the keys, check the values only
            for m in VALUE.finditer(code_part):
                v = m.group(1)
                if re.search(r"\bengine\b", v, re.I) or "المحرك" in v or "المحرّك" in v:
                    hits += 1
                    print(f"{rel}:{n}: copy says engine (use 'WhyNot Cut service'): {v[:90]}")
                if COMMAND.search(v):
                    hits += 1
                    print(f"{rel}:{n}: copy names a command (use a fix button): {v[:90]}")
                if rel in DEV_WORD_FILES and DEV_WORDS.search(v):
                    hits += 1
                    print(f"{rel}:{n}: copy has a developer word ({DEV_WORDS.search(v).group(0)}): {v[:90]}")
                if "claude code" in v.lower():
                    hits += 1
                    print(f"{rel}:{n}: copy says Claude Code: {v[:90]}")
                for u in re.findall(r"https?://([^/\s\"'«»)]+)", v):
                    if u.lower() in SUPPORT_ONLY and rel == "strings.js" and line.lstrip().startswith("support:"):
                        continue
                    if u.lower() not in ALLOWED_HOSTS:
                        hits += 1
                        print(f"{rel}:{n}: link host not on the allowlist: {u}")
    print(f"check_css: {len(code)} code files, {len(copy)} copy files, {hits} forbidden hits")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
