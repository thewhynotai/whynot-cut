# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Hush: the chat entry points, `reel hush scan` and `reel hush plan` (the panel's scan -> tune -> plan flow).

    scan  <audio.wav> [--lang auto|en|ar] [--fillers] [--sounds] [--intensity N] [--tight|--no-tight]
                      [--sequence ID --start S --end E --tracks V1,A1] [--out scan.json]
    plan  [scan.json] [--fps F] [--intensity N] [--tight|--no-tight] [--tick auto|all|none]

`scan` reads the WAV Premiere exported (the host exports it), builds the 10 ms level envelope and the clip stats, and
with --fillers transcribes it (lib.hush.words) and finds the fillers (strong ticked, soft unticked; --sounds adds the
unclear loud runs, unticked). `plan` turns a scan and the settings in force (lib.hush.settings: Simple intensity with
Tight, or the Advanced numbers) into frame-aligned cuts and the before / after / saved times. The same arithmetic as the
panel's JavaScript (lib.hush.detect). Applying the cuts, markers and undo need the host operations and are not here.
Every command prints ONE JSON object on stdout ({"ok": true, ...} or {"ok": false, "error": ...}); progress lines
({"stage": ...}) go to stderr. main() is not registered in cli.py yet (see the executor's note).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from . import detect, fillers, settings, wav, words
from .store import Store

__all__ = ["DEFAULTS", "default_cfg", "scan", "plan", "summary", "save_scan", "load_scan", "main"]

# the panel's DEFAULTS (main.js:7-13)
DEFAULTS = {
    "lang": "en", "tab": "simple", "intensity": 50, "mode": "cut", "ripple": True, "backup": True, "link": True,
    "tight": True, "padLink": True,
    "adv": {"threshold": -45, "minSilence": 0.5, "padBefore": 0.12, "padAfter": 0.12},
    "fillersOn": False, "fillerLang": "auto", "soundsOn": False,
    "listStrong": fillers.DEFAULT_STRONG, "listSoft": fillers.DEFAULT_SOFT,
}


def default_cfg(overrides=None) -> dict:
    """DEFAULTS with `overrides` on top (the advanced numbers merged key by key, like the panel does)."""
    cfg = copy.deepcopy(DEFAULTS)
    for k, v in (overrides or {}).items():
        if k == "adv" and isinstance(v, dict):
            cfg["adv"].update(v)
        else:
            cfg[k] = copy.deepcopy(v)
    return cfg


def _say(**kw):
    print(json.dumps(kw, ensure_ascii=False), file=sys.stderr, flush=True)


def scan(wav_path, *, language=None, fillers_on=None, cfg=None, store=None, key_parts=None, runner=None,
         make_runner=None, slot=None, say=None, model=None, backend=None) -> dict:
    """{env (float32), duration, sampleRate, stats, words (None without fillers), language, fillers, cached}.

    `key_parts` {sequence, range: [start, end|None], tracks} with a `store` turns the scan cache on: the transcription is
    reused when sequence, range, tracks and the audio sha256 are the same (and the requested language)."""
    cfg = default_cfg(cfg)
    lang = cfg["fillerLang"] if language is None else language
    on = cfg["fillersOn"] if fillers_on is None else fillers_on
    path = Path(wav_path)
    data = path.read_bytes()
    e = wav.envelope(data, detect.HOP)
    env, duration, rate = e["env"], e["duration"], e["sampleRate"]
    st = detect.stats(env)
    if store:
        store.log("scan %s %.2fs @%d" % (path.name, duration, rate))
    found, words_list, lang_out, cached = [], None, None, False
    if on:
        key = None
        if store and key_parts:
            rng = list(key_parts["range"])
            rng[1] = duration if rng[1] is None else rng[1]
            key = store.cache_key(key_parts["sequence"], rng, key_parts.get("tracks"), hashlib.sha256(data).hexdigest())
            entry = store.cache_get(key)
            if entry and entry.get("requested_language") == lang and entry.get("words") is not None:
                words_list, lang_out, cached = entry["words"], entry.get("language"), True
        if words_list is None:
            res = words.transcribe(path, lang, runner=runner, make_runner=make_runner, slot=slot, say=say,
                                   model=model, backend=backend)
            words_list, lang_out = res["words"], res["language"]
            if store:
                store.log("whisper %d words, %s, %ss" % (len(words_list), lang_out, res["elapsed"]))
            if key:
                store.cache_put(key, {"requested_language": lang, "language": lang_out, "words": words_list,
                                      "duration": duration})
        found = fillers.find(words_list, cfg["listStrong"], cfg["listSoft"])
        if cfg["soundsOn"]:
            found += fillers.untranscribed(env, detect.HOP, settings.current(cfg, st)["threshold"], words_list, 0.15, 1.2)
        found.sort(key=lambda f: f["s"])
    return {"env": env, "duration": duration, "sampleRate": rate, "stats": st, "words": words_list,
            "language": lang_out, "fillers": found, "cached": cached}


def plan(scan_result, cfg, fps, chosen=None) -> dict:
    """The cuts for a scan under the settings in force; `chosen` = the fillers to cut (default: the ticked ones)."""
    cfg = default_cfg(cfg)
    if chosen is None:
        chosen = [f for f in scan_result.get("fillers") or [] if f.get("on")]
    st = settings.current(cfg, scan_result["stats"])
    return detect.plan(scan_result["env"], st, chosen, scan_result["duration"], fps)


def summary(p) -> dict:
    """The panel's summary line: before / after / saved as m:ss.s and the number of silence and filler cuts."""
    f = sum(1 for c in p["cuts"] if c.get("kind") == "filler")
    return {"before": detect.fmt(p["before"]), "after": detect.fmt(p["after"]), "saved": detect.fmt(p["removed"]),
            "silences": len(p["cuts"]) - f, "fillers": f}


def save_scan(scan_result, path, store=None) -> bool:
    """Write a scan as JSON (env as plain numbers). With a `store` and a path inside its folder: user-only."""
    out = dict(scan_result)
    out["env"] = np.asarray(out["env"], dtype=np.float32).astype(np.float64).tolist()
    data = (json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if store:
        return store.write_private(path, data)
    Path(path).write_bytes(data)
    return True


def load_scan(path) -> dict:
    s = json.loads(Path(path).read_text(encoding="utf-8"))
    s["env"] = np.asarray(s["env"], dtype=np.float32)
    return s


# ----------------------------------------------------------------------------- command line
class _Usage(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _Usage(message)


def _parser():
    ap = _Parser(prog="reel hush", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    tight = {"dest": "tight", "default": None}
    sc = sub.add_parser("scan", help="analyse an exported WAV")
    sc.add_argument("wav")
    sc.add_argument("--lang", default="auto", help="auto | en | ar (the language Whisper is told)")
    sc.add_argument("--fillers", action="store_true", help="transcribe and find filler words")
    sc.add_argument("--sounds", action="store_true", help="also list unclear loud sounds (with --fillers)")
    sc.add_argument("--intensity", type=float, default=None)
    sc.add_argument("--tight", action="store_true", **tight)
    sc.add_argument("--no-tight", action="store_false", **tight)
    sc.add_argument("--sequence", default=None, help="sequence id: turns the scan cache on")
    sc.add_argument("--start", type=float, default=0.0)
    sc.add_argument("--end", type=float, default=None)
    sc.add_argument("--tracks", default="", help="comma separated track names, e.g. A1,A2")
    sc.add_argument("--model", default=None)
    sc.add_argument("--out", default=None, help="where to write the scan (default: the Hush folder's last-scan.json)")
    pl = sub.add_parser("plan", help="cuts for a scan")
    pl.add_argument("scan", nargs="?", default=None)
    pl.add_argument("--fps", type=float, default=25.0)
    pl.add_argument("--intensity", type=float, default=None)
    pl.add_argument("--tight", action="store_true", **tight)
    pl.add_argument("--no-tight", action="store_false", **tight)
    pl.add_argument("--tick", choices=["auto", "all", "none"], default="auto",
                    help="which fillers are cut: the ticked ones (default), all, or none")
    return ap


def _num(x):
    return int(x) if float(x) == int(x) else x


def main(argv=None, *, runner=None, store=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    try:
        a = _parser().parse_args(argv)
    except _Usage as e:
        print("usage error: %s" % e, file=sys.stderr)
        return 2
    except SystemExit as e:  # --help
        return int(e.code or 0)
    store = store or Store()
    cfg = default_cfg(store.load_settings())
    if a.intensity is not None:
        cfg["intensity"] = _num(a.intensity)
    if a.tight is not None:
        cfg["tight"] = a.tight
    try:
        if a.cmd == "scan":
            cfg["fillersOn"], cfg["soundsOn"] = bool(a.fillers), bool(a.sounds)
            parts = None
            if a.sequence:
                parts = {"sequence": a.sequence, "range": [a.start, a.end],
                         "tracks": [t for t in a.tracks.split(",") if t.strip()]}
            res = scan(a.wav, language=a.lang, cfg=cfg, store=store, key_parts=parts, runner=runner, say=_say,
                       model=a.model)
            out = Path(a.out) if a.out else store.last_scan_file
            if not save_scan(res, out, store=store if not a.out else None):
                raise OSError("cannot write %s" % out)
            print(json.dumps({"ok": True, "duration": res["duration"], "sampleRate": res["sampleRate"],
                              "stats": res["stats"], "words": None if res["words"] is None else len(res["words"]),
                              "language": res["language"], "fillers": len(res["fillers"]), "cached": res["cached"],
                              "out": str(out)}, ensure_ascii=False))
            return 0
        res = load_scan(a.scan or store.last_scan_file)
        chosen = {"auto": None, "all": res["fillers"], "none": []}[a.tick]
        st = settings.current(default_cfg(cfg), res["stats"])
        p = plan(res, cfg, a.fps, chosen)
        print(json.dumps({"ok": True, "plan": p, "summary": summary(p), "settings": st}, ensure_ascii=False))
        return 0
    except Exception as e:  # noqa: BLE001  (a chat command reports, it does not dump a traceback)
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
