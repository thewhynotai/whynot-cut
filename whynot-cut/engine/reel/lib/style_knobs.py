# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Style knobs that `reel plan` reads (3.0 Phase 4 T4.2).

Four knobs, set for a client in `reel-profile/style.json` (defaults in config/defaults/style.json) and, for three of
them, for one reel in edit-decisions `global`:
    caption_size_px       null (the highlight_caption template's size) | whole px   reel > client > template
    captions_during_hook  "hide" (captions stay hidden under the hook title) | "show"  client only
    hook_title_sfx        true (the hook title's own sound) | false                  graphic's sfx > reel > client
    highlight_colour      "brand" | "accent" | "ink" | "#RRGGBB" (keyword caption box)  reel > client
`resolve` turns them into the timeline-spec's `style` block. Only knobs that change something are written, so a client
at the defaults keeps a byte-identical spec (and its plan approval). A bad reel value is a plan error (the story editor
fixes edit-decisions); a bad client value is a warning and the default applies (G10: a profile slip never blocks).
Types follow the edit-decisions schema, so `reel validate` and the plan say the same thing.

The builders read the compiled spec, never the live style.json: a style change reaches a build only through `reel plan`
(common.caption_hide_default(spec) for the hook mode; the caption stills for size, line length and highlight colour).

A chosen caption size also scales the caption line length (the template's max_chars and subtitle-style short_max_chars
times template size / chosen size, rounded down, at least 8), so bigger captions wrap instead of leaving the frame.

The highlight colour is the box behind the keyword caption's text: it is checked against that text colour with the G68
rule (legibility.legible, thresholds by caption size) and, when it is too faint, drawn in the most readable brand
colour instead, with a warning naming where the colour came from. The default "brand" is never checked. Premiere's
caption stills use it; After Effects captions keep the brand colour control for now.

These keys sit at the top level of style.json, never inside `captions` (the caption-look preference of Task 23):
setting a T4.2 knob never switches a client onto a caption look.
"""
from __future__ import annotations

import difflib
import math
import re

DEFAULTS = {"caption_size_px": None, "captions_during_hook": "hide", "hook_title_sfx": True, "highlight_colour": "brand"}
REEL_KNOBS = ("caption_size_px", "hook_title_sfx", "highlight_colour")
ALIASES = {"highlight_color": "highlight_colour"}
SIZE_RANGE = (32, 140)                 # px on a 1080 px wide frame (scaled by the frame width)
MIN_CHARS = 8                          # the shortest caption line length a size may scale to
ROLES = ("brand", "accent", "ink")
_HEX = re.compile(r"#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})")
_TOKEN_HEX = re.compile(r"#?([0-9A-Fa-f]{6})")       # brand-tokens.json (written by the engine; "#" optional there)
COLOUR_HELP = 'use "brand", "accent", "ink" or a colour code "#RRGGBB"'
CLIENT_FILE = "reel-profile/style.json"


class _Bad(ValueError):
    pass


def size_range(frame_w: int) -> tuple[int, int]:
    k = (frame_w or 1080) / 1080
    return int(round(SIZE_RANGE[0] * k)), int(round(SIZE_RANGE[1] * k))


def _size(v, frame_w: int) -> int:
    """A caption size: a whole number of px (72 or 72.0, like the schema's integer) inside the frame-scaled range."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (isinstance(v, float) and not (
            math.isfinite(v) and v.is_integer())):
        raise _Bad("must be a whole number of pixels")
    lo, hi = size_range(frame_w)
    if not lo <= v <= hi:
        raise _Bad(f"must be between {lo} and {hi} px on this {frame_w} px wide frame")
    return int(v)


def _bool(v) -> bool:
    if isinstance(v, bool):
        return v
    raise _Bad("must be true or false")


def _hook_mode(v) -> str:
    if isinstance(v, str) and v.strip().lower() in ("hide", "show"):
        return v.strip().lower()
    raise _Bad('must be "hide" or "show"')


def _policy(v) -> str:
    """"brand" | "accent" | "ink" | "#RRGGBB" (upper case; #RGB expanded). The "#" is required."""
    if isinstance(v, str):
        s = v.strip()
        if s.lower() in ROLES:
            return s.lower()
        m = _HEX.fullmatch(s)
        if m:
            h = m.group(1).upper()
            return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h)
    raise _Bad(COLOUR_HELP)


def _rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(int(c) for c in rgb[:3])


def brand_colours(tokens: dict) -> dict:
    """Colour roles from brand-tokens.json (as previews.Brand reads them), each else the brand fallback; accent None
    when the brand has none."""
    from .common import brand_fallback
    tokens = tokens if isinstance(tokens, dict) else {}
    roles, der = tokens.get("roles") or {}, tokens.get("derived") or {}

    def pick(src, key, fb):
        entry = src.get(key) if isinstance(src, dict) else None
        h = entry.get("hex") if isinstance(entry, dict) else None
        if isinstance(h, str) and _TOKEN_HEX.fullmatch(h.strip()):
            return _rgb(h.strip())
        return _rgb(brand_fallback(fb)) if fb else None
    return {"primary": pick(roles, "primary", "primary"), "neutral_light": pick(roles, "neutral_light", "neutral_light"),
            "paper": pick(der, "paper_tint", "paper_tint"), "ink": pick(der, "ink", "ink"),
            "accent": pick(roles, "accent", None)}


def layers(ctx) -> list[tuple[str, object]]:
    """The style.json files a Context merges, lowest first, as (label, content): config/defaults, the shipped profile,
    the client's reel-profile. Knobs are read per file (an alias counts only in a file without the real key)."""
    from .common import CONFIG_DIR, PROFILES_DIR, read_json
    out = [("config/defaults/style.json", read_json(CONFIG_DIR / "style.json", {}))]
    for d in ctx.profile_dirs():
        data = read_json(d / "style.json")
        if data is None:
            continue
        label = f"profiles/{d.name}/style.json" if d.parent == PROFILES_DIR else CLIENT_FILE
        out.append((label, data))
    return out


def needs_tokens(style, glob) -> bool:
    """Whether resolve() will need the brand tokens (a highlight colour other than the default is set)."""
    for src in (style, glob):
        if isinstance(src, dict):
            for k in ("highlight_colour", "highlight_color"):
                if src.get(k) not in (None, "brand"):
                    return True
    return False


def _value(src: dict, key: str):
    """(set, value) of src[key]. An explicit null means "not set" (the next layer decides), for the real key and the
    alias alike; the alias spelling (highlight_color) counts only when this file has no real key at all."""
    if key in src:
        return src[key] is not None, src[key]
    for alias, real in ALIASES.items():
        if real == key and src.get(alias) is not None:
            return True, src[alias]
    return False, None


def _alias_clashes(src: dict, where: str) -> list[str]:
    return [f"{where}: {alias!r} is ignored because the same file sets {real!r}" for alias, real in ALIASES.items()
            if real in src and src.get(alias) is not None]


def _near_misses(src: dict, where: str, knobs) -> list[str]:
    out = []
    for k in src:
        if not isinstance(k, str) or k in DEFAULTS or k in ALIASES:
            continue
        m = difflib.get_close_matches(k, knobs, n=1, cutoff=0.82)
        if m:
            out.append(f"{where}: {k!r} is not a style knob: did you mean {m[0]!r}?")
    return out


def resolve(style, glob, templates: dict, tokens: dict | None, frame_w=None, layers_=None,
            subtitle_style=None) -> tuple[dict, list, list]:
    """(block, errors, warnings). block = the timeline-spec `style` entries that differ from the defaults, with
    `sources` {knob: "reel" | "client"}; {} at the defaults.
    style: the merged style.json (its captions_hidden_during decides whether "show" changes anything);
    layers_: [(label, content)] per file (default: `style` as the client's file); templates: graphics-templates.json
    templates; tokens: brand-tokens.json (only read for a highlight colour); frame_w: the frame width in px, or a
    callable (asked only when a caption size is set); subtitle_style: subtitle-style.json, or a callable (idem)."""
    errors, warnings = [], []
    if layers_ is None:
        layers_ = [(CLIENT_FILE, style)]
    files = []
    for label, data in layers_:
        if not isinstance(data, dict):
            warnings.append(f"{label} is not an object (it holds {type(data).__name__}): the default style is used "
                            "— make it a JSON object such as {\"caption_size_px\": 72}")
            continue
        if label != "config/defaults/style.json":
            warnings += _near_misses(data, label, tuple(DEFAULTS)) + _alias_clashes(data, label)
        files.append((label, data))
    style = style if isinstance(style, dict) else {}
    glob = glob if isinstance(glob, dict) else {}
    warnings += _near_misses(glob, "edit-decisions global", REEL_KNOBS + ("captions_during_hook",))
    warnings += _alias_clashes(glob, "edit-decisions global")
    tpl_cap = (templates or {}).get("highlight_caption") or {}
    width = [None]

    def fw():
        if width[0] is None:
            width[0] = int((frame_w() if callable(frame_w) else frame_w) or 1080)
        return width[0]

    def pick(key, parse):
        """(value, source, label): the reel's value (a plan error when bad), else the highest file that sets it (a
        warning naming that file when bad), else the default."""
        if key in REEL_KNOBS:
            here, v = _value(glob, key)
            if here:
                try:
                    return parse(v), "reel", f"edit-decisions global.{key}"
                except _Bad as e:
                    errors.append(f"edit-decisions global.{key} {v!r} {e}")
                    return DEFAULTS[key], None, None
        for label, data in reversed(files):
            here, v = _value(data, key)
            if here:
                try:
                    return parse(v), "client", f"{label} {key}"
                except _Bad as e:
                    warnings.append(f"{label} {key} {v!r} {e}: the default is used")
                    return DEFAULTS[key], None, None
        return DEFAULTS[key], None, None

    block, sources = {}, {}
    size, src, _ = pick("caption_size_px", lambda v: _size(v, fw()))
    tpl_size = tpl_cap.get("size")
    if size is not None and size != tpl_size:
        block["caption_size_px"], sources["caption_size_px"] = size, src
        k = (tpl_size or size) / size
        ss = (subtitle_style() if callable(subtitle_style) else subtitle_style) or {}
        block["caption_max_chars"] = max(MIN_CHARS, math.floor(int(tpl_cap.get("max_chars", 30)) * k))
        block["caption_short_max_chars"] = max(MIN_CHARS, math.floor(int(ss.get("short_max_chars", 18)) * k))

    mode, _, _ = pick("captions_during_hook", _hook_mode)
    if "captions_during_hook" in glob:
        warnings.append("edit-decisions global.captions_during_hook is not read: it is a client setting "
                        "(reel-profile/style.json); for one reel list the graphics that hide captions in "
                        "global.captions_hidden_during")
    if mode == "show":
        from .common import CAPTION_HIDE_SAFE
        client_list = style.get("captions_hidden_during") or CAPTION_HIDE_SAFE
        reel_list = glob.get("captions_hidden_during")
        if isinstance(reel_list, list) and reel_list and "hook_title" in reel_list:
            warnings.append("this reel's global.captions_hidden_during hides captions under the hook title, so the "
                            "client's captions_during_hook \"show\" is not used for this reel")
        elif not (isinstance(reel_list, list) and reel_list) and "hook_title" in client_list:
            block["captions_during_hook"] = "show"           # only when it changes the output (review #9)

    sfx, src, _ = pick("hook_title_sfx", _bool)
    if sfx is False:
        block["hook_title_sfx"], sources["hook_title_sfx"] = False, src

    policy, src, where = pick("highlight_colour", _policy)
    if policy != "brand":
        block["highlight"] = _highlight(policy, tokens, tpl_cap, size or tpl_size or 62, warnings, where)
        sources["highlight_colour"] = src
    if block and sources:
        block["sources"] = sources
    return block, errors, warnings


def _highlight(policy: str, tokens, tpl_cap: dict, size_px: float, warnings: list, where: str) -> dict:
    """The keyword box colour for `policy`, checked against the caption text colour (G68). `where` names the file and
    key the colour came from (the client's style.json, a shipped profile, or this reel's edit-decisions)."""
    from .legibility import legible
    from .motion_layout import contrast
    bc = brand_colours(tokens or {})
    if policy == "accent":
        box = bc["accent"]
        if box is None:
            box = bc["primary"]
            warnings.append(f"{where} \"accent\": the brand has no accent colour (branding/brand-tokens.json "
                            f"roles.accent): the brand primary {_hex(box)} is used")
    elif policy == "ink":
        box = bc["ink"]
    else:
        box = _rgb(policy)
    text_role = tpl_cap.get("text_role", "neutral_light")
    text = {"primary": bc["primary"], "neutral_light": bc["neutral_light"], "paper": bc["paper"],
            "ink": bc["ink"]}.get(text_role, bc["primary"])
    fallbacks = [("the brand ink", bc["ink"]), ("the brand primary", bc["primary"]),
                 ("white", bc["neutral_light"]), ("paper", bc["paper"])]
    r = legible(tuple(box), [tuple(text)], size_px, [(n, tuple(c)) for n, c in fallbacks if c])
    out = {"policy": policy, "hex": _hex(r["rgb"]), "text_hex": _hex(text), "contrast": r["ratio"], "need": r["need"],
           "adjusted": bool(r["fallback"])}
    if r["fallback"]:
        out["from_hex"] = _hex(box)
        warnings.append(f"{where}: highlight colour {_hex(box)} behind the caption text {_hex(text)} has contrast "
                        f"{r['original_ratio']:.1f}:1 (needs {r['need']:.1f}:1 at {size_px:g} px): the keyword box is "
                        f"drawn in {r['name']} {_hex(r['rgb'])} ({r['ratio']:.1f}:1) instead (G68) — set a colour with "
                        "more contrast there to keep your own")
    elif r["ratio"] < r["need"]:
        warnings.append(f"{where}: highlight colour {_hex(box)} behind the caption text {_hex(text)} has contrast "
                        f"{contrast(tuple(box), tuple(text)):.1f}:1, below the {r['need']:.1f}:1 it needs; no brand "
                        "colour reads better, so it is kept — set a colour with more contrast there (G68)")
    return out
