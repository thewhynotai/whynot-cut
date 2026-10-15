#!/usr/bin/env python3
"""Export the WhyNot Cut guide chapters as Markdown pages for the docs site.

    python guide-ar/site.py [--lang ar] [--out guide-ar/site/ar] [--chapters guide-ar/chapters]

export_site(chapters_dir, out_dir, lang) writes one page per chapter file (chapters/NN-*.html,
chapter 0 included) and returns the paths in chapter order.

Each page starts with front matter (title, slug, order, lang, dir) and then the chapter as Markdown:
  - headings carry an explicit anchor, «## Title {#heading-id}», so every internal link resolves;
  - internal «#chNN-…» links become «<slug-of-chapter-NN>.md#<anchor>» (same-page links stay «#anchor»);
    a link whose target does not exist is an error, never a dead link;
  - ol.steps -> ordered list, tables -> pipe tables, command boxes (.cmd) -> fenced code,
    Latin <bdi> text -> plain text, <code> -> inline code;
  - .tip / .warn / .todo -> blockquotes led by their label in bold (the labels are the ones the PDF
    prints: they are read from the ::before rules of styles.css, so no label is written twice);
    .fix keeps its three labels in bold; .owner is a blockquote (the PDF gives it no label);
  - figure.shot -> «![caption](shots/<id>.png)» and the caption in italics on the line below;
  - team comments and everything print-only are gone (print-only markup is added by build.py when it
    assembles the PDF; it is never in the chapter sources).

Standard library only. Chapter titles and the «N · » prefix come from build.py's heading helpers.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_build():
    """guide-ar/build.py (stdlib at import time; pypdf is loaded lazily, so it is not needed here)."""
    if "guide_build" in sys.modules:
        return sys.modules["guide_build"]
    spec = importlib.util.spec_from_file_location("guide_build", ROOT / "build.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["guide_build"] = module
    spec.loader.exec_module(module)
    return module


build = _load_build()

DIRECTIONS = {"ar": "rtl"}
_VOID = {"br", "img", "hr", "meta", "link", "input", "wbr"}
_INLINE = {"a", "abbr", "b", "bdi", "bdo", "br", "code", "em", "i", "kbd", "mark", "small", "span", "strong", "sub", "sup"}
_BR = "\x00"  # hard-break sentinel inside inline text


# ------------------------------------------------------------------ labels (read from the PDF's CSS)
_LABEL_RULES = {
    "tip": r"\.tip::before",
    "warn": r"\.warn::before",
    "todo": r"\.todo::before",
    "cmd-claude": r'\.cmd\[data-who="claude"\]::before',
}


def css_labels(styles: Path | None = None) -> dict[str, str]:
    """The box labels the PDF prints (tip, warn, todo, cmd-claude) and the three .fix labels' CSS-free names
    come from the chapter sources themselves."""
    css = (styles or ROOT / "styles.css").read_text(encoding="utf-8")
    labels = {}
    for key, selector in _LABEL_RULES.items():
        for block in re.finditer(selector + r"\s*\{([^}]*)\}", css):
            m = re.search(r'content:\s*"([^"]*)"', block.group(1))
            if m:
                labels[key] = m.group(1)
                break
        else:
            raise ValueError(f"styles.css has no content: label for {selector}")
    return labels


# ------------------------------------------------------------------ a small DOM
class Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict[str, str] | None = None) -> None:
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list = []

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())


class _DomParser(HTMLParser):
    """HTML -> Node tree. Comments are dropped here, so no team comment can reach the output."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k.lower(): (v or "") for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = Node(tag, {k.lower(): (v or "") for k, v in attrs})
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        kids = self.stack[-1].children
        if kids and isinstance(kids[-1], str):
            kids[-1] += data
        else:
            kids.append(data)

    def handle_comment(self, data):
        pass


def parse(html: str) -> Node:
    p = _DomParser()
    p.feed(html)
    p.close()
    return p.root


def walk(node: Node):
    yield node
    for child in node.children:
        if isinstance(child, Node):
            yield from walk(child)


def raw_text(node, br: str = "\n") -> str:
    """All text under a node, untouched whitespace (command boxes)."""
    if isinstance(node, str):
        return node
    if node.tag == "br":
        return br
    return "".join(raw_text(c, br) for c in node.children)


def text_of(node) -> str:
    """Visible text with collapsed whitespace and no bidi controls (alt text, titles)."""
    text = re.sub(r"[ \t\r\n]+", " ", raw_text(node, " "))
    return build._BIDI_CONTROLS.sub("", text).strip()


# ------------------------------------------------------------------ inline rendering
def esc(text: str) -> str:
    """Escape what Markdown would read as markup inside running text."""
    text = text.replace("\\", "\\\\")
    for ch in "*_[]<`":
        text = text.replace(ch, "\\" + ch)
    return text


def _code_span(text: str) -> str:
    text = re.sub(r"[ \t\r\n]+", " ", text).strip()
    if not text:
        return ""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


class _Ctx:
    """Per-chapter state: its slug, the id -> page map of every chapter, a shot counter."""

    def __init__(self, slug: str, pages: dict[str, tuple[str, str]]) -> None:
        self.slug = slug
        self.pages = pages  # id -> (page slug, "heading" | "section" | "other")
        self.shots = 0
        self.labels: dict[str, str] = {}

    def link(self, href: str) -> str:
        if not href.startswith("#"):
            return f"<{href}>" if re.search(r"[\s()]", href) else href
        target = href[1:]
        if target not in self.pages:
            raise ValueError(f"{self.slug}: link to #{target}, which is not a heading id in any chapter")
        page, kind = self.pages[target]
        if kind == "other":
            raise ValueError(f"{self.slug}: link to #{target}, which is not a heading or chapter id")
        if kind == "section":  # the chapter itself: its page, no anchor
            return "#" if page == self.slug else f"{page}.md"
        return f"#{target}" if page == self.slug else f"{page}.md#{target}"


def inline(nodes, ctx: _Ctx) -> str:
    out = []
    for node in nodes:
        if isinstance(node, str):
            out.append(esc(re.sub(r"[ \t\r\n]+", " ", node)))
            continue
        tag = node.tag
        if tag == "br":
            out.append(_BR)
        elif tag == "code":
            out.append(_code_span(raw_text(node)))
        elif tag in ("strong", "b"):
            out.append(_wrap(inline(node.children, ctx), "**"))
        elif tag in ("em", "i"):
            out.append(_wrap(inline(node.children, ctx), "*"))
        elif tag == "a":
            label = inline(node.children, ctx).replace(_BR, " ").strip()
            href = node.attrs.get("href", "")
            if not href:
                out.append(label)
            else:
                out.append(f"[{label or esc(href)}]({ctx.link(href)})")
        elif tag == "span" and "fix-label" in node.classes:
            out.append(_wrap(inline(node.children, ctx).strip() + ":", "**"))
        elif tag in _INLINE:  # bdi, span, abbr, kbd, ...: the text itself
            out.append(inline(node.children, ctx))
        else:
            raise ValueError(f"{ctx.slug}: unexpected <{tag}> inside running text")
    return "".join(out)


def _wrap(inner: str, mark: str) -> str:
    stripped = inner.strip()
    if not stripped:
        return inner
    lead = inner[: len(inner) - len(inner.lstrip())]
    trail = inner[len(inner.rstrip()):]
    return f"{lead}{mark}{stripped}{mark}{trail}"


def _line_starts(text: str) -> str:
    """Escape a line start that would turn into a list, quote or heading."""
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"^(\d+)([.)])(?=\s)", r"\1\\\2", line)
        line = re.sub(r"^([-+]|#{1,6})(?=\s)", r"\\\1", line)
        line = re.sub(r"^>", r"\\>", line)
        lines.append(line)
    return "\n".join(lines)


def paragraph(nodes, ctx: _Ctx) -> str:
    text = inline(nodes, ctx)
    text = re.sub(r" {2,}", " ", text).strip(" " + _BR)
    text = re.sub(r" *" + _BR + r" *", "\\\\\n", text)
    return _line_starts(text)


def flat(nodes, ctx: _Ctx) -> str:
    """One line of inline Markdown (headings, table cells)."""
    return re.sub(r" {2,}", " ", inline(nodes, ctx).replace(_BR, " ")).strip()


# ------------------------------------------------------------------ block rendering
Block = tuple[str, str]  # (kind, markdown)


def blocks_of(children, ctx: _Ctx) -> list[Block]:
    out: list[Block] = []
    buf: list = []

    def flush():
        if buf:
            text = paragraph(buf, ctx)
            if text.strip():
                out.append(("p", text))
            buf.clear()

    for child in children:
        if isinstance(child, str) or child.tag in _INLINE:
            buf.append(child)
        else:
            flush()
            out.extend(block(child, ctx))
    flush()
    return out


def block(node: Node, ctx: _Ctx) -> list[Block]:
    tag, cls = node.tag, node.classes
    if tag == "p":
        text = paragraph(node.children, ctx)
        return [("p", text)] if text else []
    if tag in ("h1", "h2", "h3"):
        text = flat(node.children, ctx)
        if tag == "h1":
            text = re.sub(r"^\d+\s*·\s*", "", text)
        anchor = f" {{#{node.attrs['id']}}}" if node.attrs.get("id") else ""
        return [("heading", f"{'#' * int(tag[1])} {text}{anchor}")]
    if tag in ("ul", "ol"):
        return [("list", list_md(node, ctx))]
    if tag == "table":
        return [("table", table_md(node, ctx))]
    if tag == "figure" and "shot" in cls:
        return [("img", shot_md(node, ctx))]
    if tag == "section":
        return blocks_of(node.children, ctx)
    if tag == "div" and "cmd" in cls:
        return command_md(node, ctx)
    if tag == "aside" and cls & {"tip", "warn", "todo"}:
        key = ({"tip", "warn", "todo"} & cls).pop()
        return [("quote", callout(blocks_of(node.children, ctx), ctx.labels[key]))]
    if tag == "div" and "owner" in cls:
        return [("quote", callout(blocks_of(node.children, ctx), None))]
    if tag == "div" and "fix" in cls:
        return [("p", fix_md(node, ctx))]
    raise ValueError(f"{ctx.slug}: no Markdown rule for <{tag} class=\"{node.attrs.get('class', '')}\">")


def _indent(text: str, pad: str, first: str | None = None) -> str:
    lines = text.split("\n")
    out = [(first if first is not None else pad) + lines[0]]
    out.extend(pad + line if line else "" for line in lines[1:])
    return "\n".join(out)


def list_md(node: Node, ctx: _Ctx) -> str:
    ordered = node.tag == "ol"
    items = []
    n = 0
    for li in node.children:
        if not isinstance(li, Node) or li.tag != "li":
            if isinstance(li, str) and not li.strip():
                continue
            raise ValueError(f"{ctx.slug}: <{node.tag}> holds something other than <li>")
        blocks = blocks_of(li.children, ctx)
        if not blocks:
            continue
        n += 1
        marker = f"{n}. " if ordered else "- "
        pad = " " * len(marker)
        parts = [_indent(blocks[0][1], pad, marker)]
        for (prev, _), (kind, text) in zip(blocks, blocks[1:]):
            sep = "\n" if kind == "list" and prev == "p" else "\n\n"
            parts.append(sep + _indent(text, pad, pad))
        items.append("".join(parts))
    return "\n".join(items)


def table_md(node: Node, ctx: _Ctx) -> str:
    rows = []
    for tr in (n for n in walk(node) if n.tag == "tr"):
        cells = [c for c in tr.children if isinstance(c, Node) and c.tag in ("th", "td")]
        rows.append([flat(c.children, ctx).replace("|", "\\|") for c in cells])
    if not rows:
        raise ValueError(f"{ctx.slug}: empty <table>")
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    line = lambda cells: "| " + " | ".join(cells) + " |"  # noqa: E731
    return "\n".join([line(rows[0]), line(["---"] * width)] + [line(r) for r in rows[1:]])


def shot_md(node: Node, ctx: _Ctx) -> str:
    ctx.shots += 1
    shot_id = node.attrs.get("id") or node.attrs.get("data-shot") or f"{ctx.slug}-{ctx.shots}"
    caption = next((text_of(c) for c in node.children if isinstance(c, Node) and c.tag == "figcaption"), "")
    caption = caption or text_of(node)
    alt = esc(caption)
    return f"![{alt}](shots/{shot_id}.png)\n\n*{alt}*"


def command_md(node: Node, ctx: _Ctx) -> list[Block]:
    text = "\n".join(line.rstrip() for line in raw_text(node).strip("\n").split("\n")).strip("\n")
    longest = max((len(m) for m in re.findall(r"`{3,}", text)), default=2)
    fence = "`" * (longest + 1)
    out: list[Block] = []
    if node.attrs.get("data-who") == "claude":
        out.append(("p", f"*{ctx.labels['cmd-claude']}*"))
    out.append(("code", f"{fence}\n{text}\n{fence}"))
    return out


def callout(blocks: list[Block], label: str | None) -> str:
    blocks = list(blocks)
    if label:
        if blocks and blocks[0][0] == "p":
            blocks[0] = ("p", f"**{label}:** {blocks[0][1]}")
        else:
            blocks.insert(0, ("p", f"**{label}:**"))
    text = "\n\n".join(t for _, t in blocks)
    return "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))


def fix_md(node: Node, ctx: _Ctx) -> str:
    parts = []
    for child in node.children:
        if isinstance(child, str):
            if child.strip():
                raise ValueError(f"{ctx.slug}: loose text inside a .fix box")
            continue
        if child.tag != "p" or not any(c.startswith("fix-") for c in child.classes):
            raise ValueError(f"{ctx.slug}: unexpected <{child.tag}> inside a .fix box")
        parts.append(paragraph(child.children, ctx))
    return "\\\n".join(parts)


# ------------------------------------------------------------------ export
def _yaml(value: str) -> str:
    if re.search(r"[:#\[\]{}&*!|>'\"%@`]|^[\s\-?]|\s$", value):
        return json.dumps(value, ensure_ascii=False)
    return value


def chapter_files(chapters_dir: Path) -> list[Path]:
    """Chapter sources in reading order (the same order build.assemble() uses)."""
    return sorted(Path(chapters_dir).glob("*.html"))


def _title_and_order(html: str, path: Path) -> tuple[str, int]:
    for level, _hid, inner in build.toc_headings(html):
        if level != "h1":
            continue
        m = build._NUM_LABEL.fullmatch(build.plain_text(inner))
        if not m:
            raise ValueError(f"{path.name}: the chapter h1 has no «N · » prefix")
        order = int(m.group(1))
        if not path.name.startswith(f"{order:02d}-"):
            raise ValueError(f"{path.name}: the file number does not match the h1 number {order}")
        return m.group(2).strip(), order
    raise ValueError(f"{path.name}: no h1.ch-title")


def export_site(chapters_dir: Path, out_dir: Path, lang: str, labels: dict[str, str] | None = None) -> list[Path]:
    """One Markdown page per chapter file, written to out_dir; the paths come back in chapter order.

    labels (tip, warn, todo, cmd-claude) default to the PDF's own labels from styles.css, which exist for
    Arabic only: pass them for another language.
    """
    if labels is None:
        if lang != "ar":
            raise ValueError(f"lang {lang!r}: pass labels= (the PDF labels in styles.css are Arabic)")
        labels = css_labels()
    files = chapter_files(chapters_dir)
    if not files:
        raise ValueError(f"no chapters in {chapters_dir}")
    docs = {}
    pages: dict[str, tuple[str, str]] = {}
    for path in files:
        html = path.read_text(encoding="utf-8-sig")
        docs[path] = (html, parse(html))
        for node in walk(docs[path][1]):
            hid = node.attrs.get("id") if isinstance(node, Node) else None
            if not hid:
                continue
            if hid in pages:
                raise ValueError(f"duplicate id {hid!r} ({pages[hid][0]} and {path.stem})")
            pages[hid] = (path.stem, "heading" if node.tag in ("h1", "h2", "h3") else
                          "section" if node.tag == "section" else "other")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for path in files:
        html, dom = docs[path]
        title, order = _title_and_order(html, path)
        ctx = _Ctx(path.stem, pages)
        ctx.labels = labels
        body = "\n\n".join(text for _, text in blocks_of(dom.children, ctx))
        front = "\n".join(["---", f"title: {_yaml(title)}", f"slug: {path.stem}", f"order: {order}",
                           f"lang: {lang}", f"dir: {DIRECTIONS.get(lang, 'ltr')}", "---"])
        target = out_dir / f"{path.stem}.md"
        target.write_bytes((front + "\n\n" + body + "\n").encode("utf-8"))
        written.append(target)
    for stale in out_dir.glob("*.md"):  # a renamed or removed chapter leaves no page behind
        if stale not in written:
            stale.unlink()
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export the guide chapters as Markdown pages for the docs site.")
    ap.add_argument("--lang", default="ar", help="page language (default ar)")
    ap.add_argument("--out", type=Path, default=None, help="output folder (default guide-ar/site/<lang>)")
    ap.add_argument("--chapters", type=Path, default=ROOT / "chapters", help="chapter sources folder")
    args = ap.parse_args(argv)
    out = args.out or ROOT / "site" / args.lang
    paths = export_site(args.chapters, out, args.lang)
    print(f"wrote {len(paths)} pages to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
