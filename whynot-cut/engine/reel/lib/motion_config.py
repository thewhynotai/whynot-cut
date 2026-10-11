"""Motion-mode configuration (config/defaults/motion.json, profile-overridable) and motion-project helpers."""
from __future__ import annotations

from .common import load_config, read_json

RTL_LANGS = {"ar", "fa", "ur", "he"}


def motion_cfg() -> dict:
    return load_config("motion.json")


def format_spec(fmt: str) -> dict:
    f = (motion_cfg().get("formats") or {}).get(fmt)
    if not f:
        raise SystemExit(f"unknown motion format {fmt!r} (known: {', '.join(motion_cfg().get('formats', {}))})")
    return dict(f, name=fmt)


def direction_for(lang: str | None) -> str:
    return "rtl" if (lang or "").strip().lower()[:2] in RTL_LANGS else "ltr"


def source(paths) -> dict:
    if not getattr(paths, "video_id", None):
        return {}
    return read_json(paths.p("00_inputs/source.json"), {}) or {}


def is_motion(paths) -> bool:
    return source(paths).get("kind") == "motion_reel"


def recipe_motion(paths) -> dict:
    return dict((source(paths).get("recipe") or {}).get("motion") or {})
