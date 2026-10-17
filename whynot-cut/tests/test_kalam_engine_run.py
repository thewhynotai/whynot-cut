# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, Task 11 (N4 part C): the WhyNot Kalam engine runtime (lib/kalam/{audio,transcribe,device,engine,store,
mogrt,setup_models}.py). Ported from the owner's Kalam engine tests (engine/tests/test_{doctor,portable,setup_models,cli,
pipeline_slow}.py: 2 + 12 + 2 + 2 + 3), every upstream test function is one method here with the SAME name; bodies are
unchanged apart from the mechanical pytest -> unittest rewrite and the substitutions below. tests/test_kalam_test_map.py
guards that none is dropped. test_align.py (1 test) belongs to Task 16 (align.py is not ported yet); two tests of
test_portable.py need it (test_align_device_choice, test_aligner_moves_to_cpu_when_a_cuda_forward_pass_fails) and skip
with that reason until Task 16 lands, then run unchanged.

Substitutions (each one listed here):
  * pytest fixtures: tmp_path -> TemporaryDirectory, capsys -> contextlib.redirect_stdout, monkeypatch -> unittest.mock.
  * kalam_engine.main / kalam_engine.aligner_present -> lib.kalam.engine.main / aligner_present; `from kalam import X`
    -> `from lib.kalam import X`; `setup_models as S` -> lib.kalam.setup_models.
  * test_cli / test_pipeline_slow ran a real clip of a named speaker from the developer Mac's Application Support folder
    with the real models. Here they run only when the Kalam model pack is installed (engine home tools/kalam/models) AND a
    test clip is given (env WHYNOT_KALAM_TEST_WAV, an H13 clip under whynot-test/); otherwise they skip with that reason.
    The assertions are unchanged (the named-word onset checks of the Arabic clip are kept for the clip they were written
    for: WHYNOT_KALAM_TEST_WAV_IS_REFERENCE=1); the English clip likewise (WHYNOT_KALAM_TEST_WAV_EN).
  * Fixture scan: the five upstream files hold no real name other than that clip's folder/file names (replaced above).

New tests (audit §3.1/§5, brief): audio without soundfile, device DLL dirs through plat.enable_cuda_libs, the engine JSON
lines (UTF-8, LF only, the settings file deleted on read, the API key never in argv/output/logs/reports), doctor on a
Windows CUDA -> CPU run (faked), store layout, safe_name parity with the JS port, the MOGRT scan against the upstream
G.scan, setup_models entries.
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import hashlib
import http.server
import importlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent / "engine" / "reel"
sys.path.insert(0, str(ENGINE))

import numpy as np  # noqa: E402

ADOBE_TOOLS = HERE.parents[1] / "adobe" / "tools"
KALAM_SRC = ADOBE_TOOLS / "kalam" / "src"
KALAM_UP = ADOBE_TOOLS / "kalam" / "_upstream"
RUNNER = ADOBE_TOOLS / "_harness" / "js_runner.js"
NODE = shutil.which("node")
HAVE_JS = bool(NODE) and KALAM_SRC.is_dir() and RUNNER.is_file()
NEED_JS = "needs node and adobe/tools (not in the plugin zip)"


def mod(name):
    """lib.kalam.<name>, imported when the test runs (a test file must stay importable while a module is not there yet)"""
    return importlib.import_module("lib.kalam." + name)


def touch(p: Path, text: str = "x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def run_js(root, load, calls):
    """calls = [{"fn": "KalamPlatform.safeName", "args": [...]}] through adobe/tools/_harness/js_runner.js in ONE node process"""
    with tempfile.TemporaryDirectory() as d:
        req = Path(d) / "request.json"
        req.write_text(json.dumps({"load": load, "calls": calls}), encoding="utf-8")
        p = subprocess.run([NODE, str(RUNNER), str(root), str(req)], capture_output=True, text=True, encoding="utf-8",
                           timeout=120)
    if p.returncode != 0:
        raise AssertionError("js_runner failed (%d): %s" % (p.returncode, p.stderr[-800:]))
    out = json.loads(p.stdout)["results"]
    for r in out:
        if isinstance(r, dict) and "error" in r:
            raise AssertionError("js_runner call failed: %s" % r["error"])
    return out


class TestSafeName(unittest.TestCase):
    """store.safe_name = the JS port's safeName rules (Task 5) plus control characters U+0000-U+001F replaced by "-" and
    CONIN$ / CONOUT$ reserved (Task 5 review minors)"""

    BOTH = [
        ("Episode 2: \"final\" <v2>?|*\\x/y", "Episode 2- -final- -v2-----x-y"),
        ("Weekly Show", "Weekly Show"), ("\u062d\u0644\u0642\u0629 \u0661", "\u062d\u0644\u0642\u0629 \u0661"),
        ("nul", "nul_"), ("NUL.srt", "NUL_.srt"), ("Com1", "Com1_"), ("lpt9.tar.gz", "lpt9_.tar.gz"), ("PRN", "PRN_"),
        ("aux ", "aux_"), ("con.", "con_"), ("prn .txt", "prn _.txt"), ("CON:", "CON-"), ("COM0", "COM0"),
        ("COM10", "COM10"), ("console", "console"), ("nullable.srt", "nullable.srt"), ("my.nul", "my.nul"),
        ("", "_"), ("...", "_"), (" . ", "_"), ("a.b. .", "a.b"), ("trailing space ", "trailing space"),
        ("\u0645\u0644\u0641:\u0627\u062e\u062a\u0628\u0627\u0631", "\u0645\u0644\u0641-\u0627\u062e\u062a\u0628\u0627\u0631"),
        ("K\u212aNUL", "K\u212aNUL"), ("\u017fnul", "\u017fnul"),            # Kelvin sign / long s are not ASCII letters
    ]

    def test_names_both_implementations_handle(self):
        safe = mod("store").safe_name
        for src, want in self.BOTH:
            self.assertEqual(safe(src), want, src)

    @unittest.skipUnless(HAVE_JS, NEED_JS)
    def test_parity_with_the_js_port(self):
        safe = mod("store").safe_name
        got = run_js(KALAM_SRC, ["js/platform.js"], [{"fn": "KalamPlatform.safeName", "args": [s]} for s, _ in self.BOTH])
        self.assertEqual(got, [want for _, want in self.BOTH])
        self.assertEqual([safe(s) for s, _ in self.BOTH], got)

    def test_control_characters_become_dashes(self):
        safe = mod("store").safe_name
        self.assertEqual(safe("a\x00b\x1fc\nd\te\rf"), "a-b-c-d-e-f")
        self.assertEqual(safe("\x01\x02"), "--")
        self.assertEqual(safe("ok\x7fname"), "ok\x7fname")          # only U+0000-U+001F (Windows refuses those)
        self.assertEqual(safe("line\n"), "line-")                   # a trailing newline is not "trailing space"

    def test_console_handles_are_reserved(self):
        safe = mod("store").safe_name
        self.assertEqual(safe("CONIN$"), "CONIN$_")
        self.assertEqual(safe("conout$"), "conout$_")
        self.assertEqual(safe("CONOUT$.srt"), "CONOUT$_.srt")
        self.assertEqual(safe("CONIN$x"), "CONIN$x")
        self.assertEqual(safe("my CONIN$"), "my CONIN$")

    def test_a_name_is_never_a_path(self):
        safe = mod("store").safe_name
        for s in ("../../etc/passwd", "..\\..\\x", "C:\\Windows\\System32", "/abs/path"):
            out = safe(s)
            self.assertFalse(any(c in out for c in '\\/:*?"<>|'), out)


class TestStore(unittest.TestCase):
    """<engine home>/tools/kalam/: settings (private), logs/whynot-kalam.log, cache, models, hf; the report text never holds
    settings or keys (PRD FR-24 rule)"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "engine-home"
        self.S = mod("store").Store(self.home)

    def test_layout_is_under_the_engine_home_on_every_os(self):
        S = self.S
        base = self.home / "tools" / "kalam"
        self.assertEqual((S.home, S.logs, S.cache_dir, S.models_dir, S.hf_dir),
                         (base, base / "logs", base / "cache", base / "models", base / "hf"))
        self.assertEqual(S.log_file, base / "logs" / "whynot-kalam.log")
        self.assertEqual(S.settings_file, base / "settings.json")

    def test_default_engine_home_is_plat_engine_home(self):
        from lib import plat
        self.assertEqual(mod("store").Store().engine_home, plat.engine_home())
        self.assertEqual(mod("store").default_models_dir(), plat.engine_home() / "tools" / "kalam" / "models")

    def test_log_appends_iso_time_lines_utf8_lf_and_never_raises(self):
        self.assertTrue(self.S.log("caption run \u0627\u062e\u062a\u0628\u0627\u0631\nsecond\r\nline"))
        self.assertTrue(self.S.log("done"))
        raw = self.S.log_file.read_bytes()
        self.assertNotIn(b"\r", raw)
        lines = raw.decode("utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z  caption run \u0627\u062e\u062a\u0628\u0627\u0631 second line$")
        self.assertTrue(self.S.log("lone surrogate \ud800 ok"))      # never raises on a character UTF-8 cannot hold
        blocked = mod("store").Store(Path(self._tmp.name) / "file-not-folder")
        (Path(self._tmp.name) / "file-not-folder").write_text("x", encoding="utf-8")
        self.assertFalse(blocked.log("x"))                          # a log must not stop a run

    def test_settings_round_trip_utf8_lf_and_private(self):
        self.assertEqual(self.S.load_settings({"max_line": 32}), {"max_line": 32})
        self.assertTrue(self.S.save_settings({"max_line": 30, "glossary": {"X": ["\u0627"]}}))
        raw = self.S.settings_file.read_bytes()
        self.assertTrue(raw.endswith(b"\n") and b"\r" not in raw)
        self.assertEqual(self.S.load_settings({"max_line": 32, "max_lines": 2}),
                         {"max_line": 30, "max_lines": 2, "glossary": {"X": ["\u0627"]}})
        if os.name != "nt":
            self.assertEqual(self.S.settings_file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.S.home.stat().st_mode & 0o777, 0o700)

    def test_take_settings_reads_the_file_and_deletes_it(self):
        f = Path(self._tmp.name) / "run-settings.json"
        f.write_text(json.dumps({"api_key": "sk-test-key-0000", "max_line": 28}), encoding="utf-8")
        got = mod("store").take_settings(f)
        self.assertEqual(got, {"api_key": "sk-test-key-0000", "max_line": 28})
        self.assertFalse(f.exists())

    def test_take_settings_deletes_even_when_the_content_is_unusable(self):
        t = mod("store").take_settings
        for text in ("not json", "[1, 2]", ""):
            f = Path(self._tmp.name) / "bad.json"
            f.write_text(text, encoding="utf-8")
            with self.assertRaises(ValueError):
                t(f)
            self.assertFalse(f.exists(), text)
        with self.assertRaises(OSError):
            t(Path(self._tmp.name) / "missing.json")

    def test_take_settings_accepts_the_run_folder_of_the_store_and_the_temp_folder(self):
        take = mod("store").take_settings
        self.S.run_dir.mkdir(parents=True)
        for folder in (self.S.run_dir, Path(tempfile.gettempdir())):
            f = folder / "kalam-run-settings.json"
            f.write_text(json.dumps({"a": 1}), encoding="utf-8")
            self.assertEqual(take(f, store=self.S), {"a": 1})
            self.assertFalse(f.exists())

    def test_take_settings_refuses_the_persistent_settings_file_and_keeps_it(self):
        self.assertTrue(self.S.save_settings({"max_line": 30}))
        with self.assertRaises(PermissionError):
            mod("store").take_settings(self.S.settings_file, store=self.S)
        self.assertTrue(self.S.settings_file.is_file())
        with self.assertRaises(PermissionError):                      # also spelled through the folder with a ".." step
            mod("store").take_settings(self.S.home / "logs" / ".." / "settings.json", store=self.S)
        self.assertTrue(self.S.settings_file.is_file())

    def test_take_settings_refuses_a_file_outside_the_expected_locations_and_keeps_it(self):
        take = mod("store").take_settings
        outside = Path.home() / "somewhere-else" / "notes.json"
        outside.parent.mkdir(parents=True)
        outside.write_text(json.dumps({"api_key": "x"}), encoding="utf-8")
        with self.assertRaises(PermissionError) as cm:
            take(outside, store=self.S)
        self.assertIn("settings", str(cm.exception))
        self.assertTrue(outside.is_file())
        climb = Path(tempfile.gettempdir()) / ".." / ".." / "escape.json"            # resolves above the temp folder
        with self.assertRaises(PermissionError):
            take(climb, store=self.S)

    def test_take_settings_refuses_a_reparse_point_and_keeps_both_files(self):
        take = mod("store").take_settings
        target = Path(self._tmp.name) / "real.json"
        target.write_text(json.dumps({"a": 1}), encoding="utf-8")
        link = Path(self._tmp.name) / "link.json"
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError):
            self.skipTest("this account cannot create symbolic links")
        with self.assertRaises(PermissionError):
            take(link, store=self.S)
        self.assertTrue(target.is_file() and link.is_symlink())

    def test_a_windows_reparse_point_attribute_is_refused_too(self):
        S = mod("store")
        f = Path(self._tmp.name) / "junction-like.json"
        f.write_text(json.dumps({"a": 1}), encoding="utf-8")
        with mock.patch.object(S, "_is_reparse", lambda path: True):
            with self.assertRaises(PermissionError):
                S.take_settings(f, store=self.S)
        self.assertTrue(f.is_file())
        self.assertFalse(S._is_reparse(f))                                  # an ordinary file is not one

    def test_take_settings_reads_a_bom(self):
        f = Path(self._tmp.name) / "bom.json"
        f.write_bytes(b"\xef\xbb\xbf" + json.dumps({"a": 1}).encode("utf-8"))
        self.assertEqual(mod("store").take_settings(f), {"a": 1})

    def test_report_text_never_contains_settings_or_keys(self):
        self.S.save_settings({"api_key": "sk-test-key-0000", "rules": "private client rules", "max_line": 31})
        self.S.log("run done")
        rep = {"python": "3.12", "backend": "portable", "models": {"arabic": True},
               "settings": {"api_key": "sk-test-key-0000"}, "api_key": "sk-test-key-0000",
               "stats": {"error": None, "apiKey": "sk-test-key-0000"}}
        text = self.S.report_text(rep, secrets=("sk-test-key-0000",))
        for needle in ("sk-test-key-0000", "private client rules", "api_key", "apiKey", "settings"):
            self.assertNotIn(needle, text)
        self.assertIn("backend", text)
        self.assertIn("run done", text)                             # the log tail is part of the report
        self.assertNotIn("\r", text)

    def test_redact_removes_secret_named_keys_at_every_depth_without_changing_the_input(self):
        redact = mod("store").redact
        src = {"a": {"api_key": "k", "token": "t", "ok": 1}, "list": [{"password": "p", "x": 2}], "apikey": "z"}
        out = redact(src)
        self.assertEqual(out, {"a": {"ok": 1}, "list": [{"x": 2}]})
        self.assertIn("api_key", src["a"])


# ======================================================================================================== MOGRT scan
THUMB = b"\x89PNG\r\n\x1a\n" + b"fake-thumbnail-bytes"
ARABIC_TEST = "\u0627\u062e\u062a\u0628\u0627\u0631"


def definition(name_en="Example Lower Third", fields=("Headline", "Speaker"), extra_controls=1, localized=True):
    """a definition.json (the shape Premiere writes): capsuleName(+Localized) and clientControls (type 6 = text)"""
    controls = [{"type": 6, "uiName": {"strDB": [{"localeString": "en_US", "str": f}]}} for f in fields]
    controls += [{"type": 2, "uiName": {"strDB": [{"localeString": "en_US", "str": "Color"}]}}] * extra_controls
    d = {"capsuleName": name_en, "clientControls": controls}
    if localized:
        d["capsuleNameLocalized"] = {"strDB": [{"localeString": "de_DE", "str": "Beispiel"},
                                                {"localeString": "en_US", "str": name_en}]}
    return d


def make_mogrt(path: Path, defn=None, thumb=THUMB, deflate=True, extra=(), raw_definition=None):
    import zipfile
    path.parent.mkdir(parents=True, exist_ok=True)
    comp = zipfile.ZIP_DEFLATED if deflate else zipfile.ZIP_STORED
    with zipfile.ZipFile(path, "w", comp) as z:
        z.writestr("definition.json", raw_definition if raw_definition is not None
                   else json.dumps(defn if defn is not None else definition(), ensure_ascii=False))
        z.writestr("project.aegraphic", b"x" * 300)
        if thumb is not None:
            z.writestr("thumb.png", thumb)
        for name, data in extra:
            z.writestr(name, data)
    return path


def templates_tree(base: Path) -> Path:
    make_mogrt(base / "Basic Title.mogrt", definition("Basic Title", ("Text",)))
    make_mogrt(base / "Captions" / "Bold Web Caption.mogrt", definition("Bold Web Caption", ("Line 1", "Line 2")))
    make_mogrt(base / "Captions" / "Portrait" / ("Comic %s.mogrt" % ARABIC_TEST),
               definition("Comic " + ARABIC_TEST, ("Text",)), deflate=False)
    make_mogrt(base / "Captions" / "alpha.mogrt", definition("Alpha", ()), thumb=None)
    make_mogrt(base / "Upper" / "NO-NAME.MOGRT", {"clientControls": [{"type": 6, "uiName": {}}]})
    make_mogrt(base / ".hidden" / "Skipped.mogrt")
    make_mogrt(base / "Captions" / ".dot.mogrt")
    (base / "Captions" / "notes.txt").write_text("not a template", encoding="utf-8")
    (base / "Broken").mkdir()
    (base / "Broken" / "Corrupt.mogrt").write_bytes(b"this is not a zip file")
    make_mogrt(base / "Bad JSON" / "Bad.mogrt", raw_definition="{not json")
    return base


class TestMogrtScan(unittest.TestCase):
    """scan(base, cache_dir) = upstream G.scan: every .mogrt under Premiere's Local Templates -> [{path, name, folder,
    textFields, thumb}] sorted by folder then name, cached by path + modification time, thumbnails as sha1(path).png"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.base = templates_tree(self.tmp / "Templates")
        self.cache = self.tmp / "cache"
        self.M = mod("mogrt")

    def test_scan_output_shape_order_and_names(self):
        out = self.M.scan(str(self.base), str(self.cache))
        self.assertTrue(all(set(m) == {"path", "name", "folder", "textFields", "thumb"} for m in out))
        self.assertEqual([(m["folder"], m["name"]) for m in out], [
            ("", "Basic Title"), ("Bad JSON", "Bad"), ("Broken", "Corrupt"), ("Captions", "Alpha"),
            ("Captions", "Bold Web Caption"), ("Captions/Portrait", "Comic " + ARABIC_TEST), ("Upper", "NO-NAME.MOGRT")])
        by = {m["name"]: m for m in out}
        self.assertEqual(by["Bold Web Caption"]["textFields"], ["Line 1", "Line 2"])
        self.assertEqual(by["NO-NAME.MOGRT"]["textFields"], ["Text 1"])               # no uiName: "Text <n>"
        self.assertEqual(by["Alpha"]["textFields"], [])
        self.assertEqual(by["Corrupt"]["textFields"], [])
        self.assertEqual(by["Bad"]["textFields"], [])

    def test_hidden_files_and_folders_and_other_extensions_are_skipped(self):
        names = {m["name"] for m in self.M.scan(str(self.base), str(self.cache))}
        self.assertNotIn("Skipped", names)
        self.assertNotIn(".dot", names)
        self.assertNotIn("notes", names)

    def test_thumbnails_are_sha1_of_the_path_png_under_mogrt_thumbs(self):
        out = self.M.scan(str(self.base), str(self.cache))
        by = {m["name"]: m for m in out}
        bold = by["Bold Web Caption"]
        want = self.cache / "mogrt-thumbs" / (hashlib.sha1(bold["path"].encode("utf-8")).hexdigest() + ".png")
        self.assertEqual(Path(bold["thumb"]), want)
        self.assertEqual(want.read_bytes(), THUMB)
        self.assertEqual(by["Alpha"]["thumb"], "")                                # no thumb.png in the template
        self.assertEqual(by["Corrupt"]["thumb"], "")
        self.assertEqual(Path(bold["path"]), self.base / "Captions" / "Bold Web Caption.mogrt")

    def test_stored_and_deflated_entries_both_read(self):
        by = {m["name"]: m for m in self.M.scan(str(self.base), str(self.cache))}
        self.assertEqual(Path(by["Comic " + ARABIC_TEST]["thumb"]).read_bytes(), THUMB)

    def test_second_scan_comes_from_the_cache_keyed_by_path_and_mtime(self):
        first = self.M.scan(str(self.base), str(self.cache))
        index = json.loads((self.cache / "mogrt-index.json").read_text(encoding="utf-8"))
        self.assertTrue(any(k.startswith(str(self.base / "Basic Title.mogrt") + "|") for k in index))
        import zipfile
        with mock.patch.object(zipfile, "ZipFile", side_effect=AssertionError("a cached template was opened again")):
            try:
                second = self.M.scan(str(self.base), str(self.cache))
            except AssertionError:
                second = None
        self.assertIsNotNone(second)          # the templates that read fine came back without opening their zip again
        cached = {"Basic Title", "Bold Web Caption", "Comic " + ARABIC_TEST}
        self.assertEqual([m for m in first if m["name"] in cached], [m for m in second if m["name"] in cached])

    def test_a_changed_template_is_read_again_and_a_lost_thumbnail_is_rewritten(self):
        self.M.scan(str(self.base), str(self.cache))
        target = self.base / "Basic Title.mogrt"
        make_mogrt(target, definition("Basic Title v2", ("Text", "More")))
        os.utime(target, ns=(target.stat().st_atime_ns, target.stat().st_mtime_ns + 5_000_000_000))
        by = {m["name"]: m for m in self.M.scan(str(self.base), str(self.cache))}
        self.assertEqual(by["Basic Title v2"]["textFields"], ["Text", "More"])
        thumb = Path(by["Bold Web Caption"]["thumb"])
        thumb.unlink()
        again = {m["name"]: m for m in self.M.scan(str(self.base), str(self.cache))}
        self.assertTrue(Path(again["Bold Web Caption"]["thumb"]).is_file())

    def test_missing_base_and_empty_base(self):
        self.assertEqual(self.M.scan(str(self.tmp / "nowhere"), str(self.cache)), [])
        (self.tmp / "empty").mkdir()
        self.assertEqual(self.M.scan(str(self.tmp / "empty"), str(self.cache)), [])

    def test_index_is_utf8_lf_json(self):
        self.M.scan(str(self.base), str(self.cache))
        raw = (self.cache / "mogrt-index.json").read_bytes()
        self.assertNotIn(b"\r", raw)
        json.loads(raw.decode("utf-8"))

    def test_cache_files_are_written_through_a_temp_name_and_replaced(self):
        calls, real = [], os.replace
        with mock.patch("os.replace", lambda a, b: (calls.append((str(a), str(b))), real(a, b))[1]):
            self.M.scan(str(self.base), str(self.cache))
        targets = {os.path.basename(b) for _a, b in calls}
        self.assertIn("mogrt-index.json", targets)
        self.assertTrue(any(t.endswith(".png") for t in targets))
        self.assertTrue(all(a.endswith(".tmp") for a, _b in calls))
        self.assertEqual(list(self.cache.rglob("*.tmp")), [])

    def test_a_failed_write_keeps_the_previous_index_and_leaves_nothing_behind(self):
        self.M.scan(str(self.base), str(self.cache))
        index = self.cache / "mogrt-index.json"
        before = index.read_bytes()
        make_mogrt(self.base / "New One.mogrt", definition("New One", ("Text",)))
        with mock.patch("os.replace", side_effect=OSError("disk full")):
            self.M.scan(str(self.base), str(self.cache))                 # must not raise
        self.assertEqual(index.read_bytes(), before)
        self.assertEqual(list(self.cache.rglob("*.tmp")), [])

    def test_the_store_docstring_does_not_claim_the_cache_is_private(self):
        doc = mod("store").__doc__
        self.assertNotIn("Everything is user-only", doc)
        self.assertIn("default permissions", doc)

    def test_the_scan_never_modifies_the_templates(self):
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.base.rglob("*.*") if p.is_file()}
        self.M.scan(str(self.base), str(self.cache))
        after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.base.rglob("*.*") if p.is_file()}
        self.assertEqual(before, after)

    def test_sort_is_by_utf16_code_units_like_javascript(self):
        # U+FF5E (BMP, high) sorts AFTER U+1F600 (astral) in UTF-16 code units, BEFORE it by code point
        make_mogrt(self.base / "Emoji" / "\uff5eTilde.mogrt", definition("\uff5eTilde", ()))
        make_mogrt(self.base / "Emoji" / "\U0001f600Smile.mogrt", definition("\U0001f600Smile", ()))
        names = [m["name"] for m in self.M.scan(str(self.base), str(self.cache)) if m["folder"] == "Emoji"]
        self.assertEqual(names, ["\U0001f600Smile", "\uff5eTilde"])


class TestMogrtPureFunctions(unittest.TestCase):
    """the engine twins of the panel's pure functions (definitionInfo, folderOf) against the JS port"""

    DEFS = [{}, {"capsuleName": "Basic", "clientControls": []}, definition(), definition(localized=False),
            {"capsuleNameLocalized": {"strDB": [{"localeString": "fr_FR", "str": "Seul"}]}, "clientControls": [
                {"type": 6, "uiName": {"strDB": [{"localeString": "de_DE", "str": "Kopf"}]}}, {"type": 6, "uiName": {"strDB": []}},
                {"type": 6}, {"type": 1, "uiName": {"strDB": [{"localeString": "en_US", "str": "Not text"}]}}]},
            {"capsuleName": "9\u20229 Test Subtitles", "clientControls": [{"type": 6, "uiName": {"strDB": [
                {"localeString": "en_US", "str": "Text"}]}}, {"type": 6, "uiName": {"strDB": [{"localeString": "en_US", "str": "Speaker"}]}}]}]
    PATHS = [("/T/Captioneer/Portrait/a.mogrt", "/T"), ("/T/Basic Title.mogrt", "/T"), ("C:\\T\\A\\b.mogrt", "C:\\T"),
             ("C:\\T\\b.mogrt", "C:\\T"), ("/T/a/b/c/d.mogrt", "/T/"), ("/T//x/y.mogrt", "/T"), ("/other/x.mogrt", "/T")]

    def test_definition_info(self):
        M = mod("mogrt")
        self.assertEqual(M.definition_info(self.DEFS[5]), {"name": "9\u20229 Test Subtitles", "textFields": ["Text", "Speaker"]})
        self.assertEqual(M.definition_info({}), {"name": "", "textFields": []})
        self.assertEqual(M.definition_info(None), {"name": "", "textFields": []})
        self.assertEqual(M.definition_info(self.DEFS[4])["textFields"], ["Kopf", "Text 2", "Text 3"])

    @unittest.skipUnless(HAVE_JS, NEED_JS)
    def test_definition_info_and_folder_of_match_the_js_port(self):
        M = mod("mogrt")
        calls = [{"fn": "KalamMogrt.definitionInfo", "args": [d]} for d in self.DEFS]
        calls += [{"fn": "KalamMogrt.folderOf", "args": [p, b]} for p, b in self.PATHS]
        got = run_js(KALAM_SRC, ["js/mogrt.js"], calls)
        self.assertEqual(got[:len(self.DEFS)], [M.definition_info(d) for d in self.DEFS])
        self.assertEqual(got[len(self.DEFS):], [M.folder_of(p, b) for p, b in self.PATHS])


@unittest.skipUnless(HAVE_JS and (KALAM_UP / "js" / "mogrt.js").is_file(), NEED_JS)
class TestMogrtScanMatchesUpstream(unittest.TestCase):
    """the engine scan against the owner's G.scan (adobe/tools/kalam/_upstream/js/mogrt.js) run under node, on the same
    folder: same records, same order, byte-identical thumbnails"""

    SCRIPT = (
        "var fs=require('fs'),vm=require('vm');global.window=global;global.cep_node={require:require};\n"
        "vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));\n"
        "var out=window.KalamMogrt.scan(process.argv[2],process.argv[3]);\n"
        "process.stdout.write(JSON.stringify(out));\n")

    def test_scan_equals_upstream_scan(self):
        M = mod("mogrt")
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            base = templates_tree(d / "Templates")
            tiny = KALAM_UP / "tests" / "panel" / "fixtures" / "tiny.mogrt"
            if tiny.is_file():
                (base / "Captioneer" / "Portrait").mkdir(parents=True)
                shutil.copy(tiny, base / "Captioneer" / "Portrait" / "tiny.mogrt")
            js_cache, py_cache = d / "cache-js", d / "cache-py"
            p = subprocess.run([NODE, "-e", self.SCRIPT, str(KALAM_UP / "js" / "mogrt.js"), str(base), str(js_cache)],
                               capture_output=True, text=True, encoding="utf-8", timeout=120)
            self.assertEqual(p.returncode, 0, "the upstream scan failed under node: %s" % p.stderr[-600:])
            want = json.loads(p.stdout)
            got = M.scan(str(base), str(py_cache))

            def rel(m, cache):
                m = dict(m)
                m["thumb"] = os.path.relpath(m["thumb"], cache) if m["thumb"] else ""
                return m

            self.assertEqual([rel(m, py_cache) for m in got], [rel(m, js_cache) for m in want])
            self.assertTrue(len(got) >= 7)
            for g, w in zip(got, want):
                if g["thumb"]:
                    self.assertEqual(Path(g["thumb"]).read_bytes(), Path(w["thumb"]).read_bytes())


# ============================================================================================================== audio
import struct  # noqa: E402

HAVE_SF = importlib.util.find_spec("soundfile") is not None


def _wav_bytes(frames: np.ndarray, rate: int, kind: str = "pcm16", extensible: bool = False, extra_chunks=(), data_len=None,
               trailing=b""):
    """a WAV file from float frames (n, channels) in [-1, 1): kind pcm8 / pcm16 / pcm24 / pcm32 / float32 / float64"""
    frames = np.atleast_2d(frames.T).T if frames.ndim == 1 else frames
    ch = frames.shape[1]
    bits = {"pcm8": 8, "pcm16": 16, "pcm24": 24, "pcm32": 32, "float32": 32, "float64": 64}[kind]
    if kind == "pcm8":
        raw = np.clip(np.round(frames * 128) + 128, 0, 255).astype(np.uint8).tobytes()
    elif kind == "pcm16":
        raw = np.clip(np.round(frames * 32768), -32768, 32767).astype("<i2").tobytes()
    elif kind == "pcm24":
        v = np.clip(np.round(frames * 8388608), -8388608, 8388607).astype("<i4")
        raw = v.reshape(-1).view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    elif kind == "pcm32":
        raw = np.clip(np.round(frames * 2147483648), -2147483648, 2147483647).astype("<i4").tobytes()
    elif kind == "float32":
        raw = frames.astype("<f4").tobytes()
    else:
        raw = frames.astype("<f8").tobytes()
    fmt_tag = 3 if kind.startswith("float") else 1
    block = ch * bits // 8
    if extensible:
        fmt = struct.pack("<HHIIHHHHIH14s", 0xFFFE, ch, rate, rate * block, block, bits, 22, bits, 0, fmt_tag,
                          b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71")
    else:
        fmt = struct.pack("<HHIIHH", fmt_tag, ch, rate, rate * block, block, bits)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    for tag, payload in extra_chunks:
        chunks += tag + struct.pack("<I", len(payload)) + payload + (b"\x00" if len(payload) & 1 else b"")
    length = len(raw) if data_len is None else data_len
    body = b"WAVE" + chunks + b"data" + struct.pack("<I", length) + raw + trailing
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _tone(seconds, rate, channels=1, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * rate)) / rate
    base = 0.4 * np.sin(2 * np.pi * 220 * t) + 0.05 * rng.standard_normal(len(t))
    return np.stack([base * (1 - 0.3 * c) for c in range(channels)], axis=1).astype(np.float32)


def _upstream_downmix(a2d: np.ndarray, sr: int) -> np.ndarray:
    """the owner's load_16k after sf.read: the same lines on the same float32 array"""
    a = a2d.mean(axis=1)
    if sr == 16000:
        return a
    if sr % 16000 == 0:
        k = sr // 16000
        return a[: len(a) // k * k].reshape(-1, k).mean(axis=1).astype(np.float32)
    t = np.arange(0, len(a) / sr, 1.0 / 16000)
    return np.interp(t, np.arange(len(a)) / sr, a).astype(np.float32)


class TestAudio(unittest.TestCase):
    """audio.load_16k / envelope_db without `soundfile` when it is absent (stdlib reader for PCM and float WAVs), arrays
    identical to what soundfile gives on the same files (that half runs only when soundfile can be imported)"""

    CASES = [("pcm16", 16000, 1), ("pcm16", 48000, 2), ("pcm16", 44100, 1), ("pcm16", 8000, 2), ("pcm24", 48000, 2),
             ("pcm32", 32000, 1), ("float32", 16000, 1), ("float32", 96000, 2), ("float64", 22050, 1), ("pcm8", 16000, 1)]

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.A = mod("audio")

    def _write(self, name, data):
        p = self.tmp / name
        p.write_bytes(data)
        return str(p)

    def test_constants_are_the_owners(self):
        self.assertEqual((self.A.RATE, self.A.HOP), (16000, 0.01))

    def test_load_16k_without_soundfile_matches_the_reference_for_every_format(self):
        with mock.patch.dict(sys.modules, {"soundfile": None}):
            for kind, rate, ch in self.CASES:
                frames = _tone(0.37, rate, ch)
                path = self._write("%s-%d-%d.wav" % (kind, rate, ch), _wav_bytes(frames, rate, kind))
                got = self.A.load_16k(path)
                a2d, sr = self.A.read_wav(path)
                self.assertEqual(sr, rate, (kind, rate, ch))
                self.assertEqual((a2d.dtype, a2d.ndim, a2d.shape[1]), (np.float32, 2, ch), (kind, rate, ch))
                want = _upstream_downmix(a2d, sr)
                self.assertEqual(got.dtype, np.float32)
                self.assertEqual(got.tobytes(), want.tobytes(), (kind, rate, ch))
                tol = {"pcm8": 1 / 128, "pcm16": 1 / 32768, "pcm24": 1e-6, "pcm32": 1e-6}.get(kind, 0)
                self.assertTrue(np.allclose(a2d, frames, atol=tol + 1e-7), (kind, rate, ch))     # the samples are what was written

    def test_integer_pcm_is_scaled_by_a_power_of_two_exactly(self):
        for kind, bits in (("pcm16", 15), ("pcm24", 23), ("pcm32", 31)):
            raw = {"pcm16": [-32768, 0, 1, 32767], "pcm24": [-8388608, 0, 1, 8388607],
                   "pcm32": [-2147483648, 0, 1, 2147483647]}[kind]
            frames = np.array(raw, dtype=np.float64).reshape(-1, 1) / 2.0 ** bits
            path = self._write(kind + ".wav", _wav_bytes(frames, 16000, kind))
            a2d, _sr = self.A.read_wav(path)
            self.assertEqual(a2d[:, 0].tolist(), (np.array(raw, dtype=np.float32) * np.float32(2.0 ** -bits)).tolist(), kind)

    def test_eight_bit_is_unsigned_with_a_128_offset(self):
        path = self._write("u8.wav", _wav_bytes(np.array([[-1.0], [0.0], [0.5]]), 16000, "pcm8"))
        a2d, _ = self.A.read_wav(path)
        self.assertEqual(a2d[:, 0].tolist(), [-1.0, 0.0, 0.5])

    def test_extensible_header_extra_chunks_odd_padding_and_streamed_length(self):
        frames = _tone(0.2, 16000, 2)
        base = self.A.read_wav(self._write("a.wav", _wav_bytes(frames, 16000, "pcm16")))[0]
        for name, data in {
            "ext": _wav_bytes(frames, 16000, "pcm16", extensible=True),
            "list": _wav_bytes(frames, 16000, "pcm16", extra_chunks=[(b"LIST", b"INFOabc"), (b"junk", b"12345")]),
            "streamed0": _wav_bytes(frames, 16000, "pcm16", data_len=0),
            "streamedF": _wav_bytes(frames, 16000, "pcm16", data_len=0xFFFFFFFF),
        }.items():
            got = self.A.read_wav(self._write(name + ".wav", data))[0]
            self.assertEqual(got.tobytes(), base.tobytes(), name)

    def test_a_partial_last_frame_is_dropped_and_an_empty_file_is_an_empty_array(self):
        frames = _tone(0.1, 16000, 2)
        data = _wav_bytes(frames, 16000, "pcm16", data_len=frames.shape[0] * 4 + 3, trailing=b"\x01\x02\x03")
        a2d, _ = self.A.read_wav(self._write("p.wav", data))
        self.assertEqual(a2d.shape, frames.shape)
        empty = self.A.load_16k(self._write("e.wav", _wav_bytes(np.zeros((0, 1), dtype=np.float32), 16000, "pcm16")))
        self.assertEqual((empty.shape, empty.dtype), ((0,), np.float32))

    def test_unusable_files_raise_a_clear_error(self):
        with self.assertRaises(ValueError) as cm:
            self.A.load_16k(self._write("x.wav", b"this is not a wav file at all"))
        self.assertIn("WAV", str(cm.exception))
        alaw = bytearray(_wav_bytes(_tone(0.05, 16000), 16000, "pcm16"))
        alaw[20:22] = struct.pack("<H", 6)                                  # A-law: only soundfile could read it
        with self.assertRaises(ValueError) as cm:
            self.A.load_16k(self._write("alaw.wav", bytes(alaw)))
        self.assertIn("soundfile", str(cm.exception))
        with self.assertRaises(OSError):
            self.A.load_16k(str(self.tmp / "missing.wav"))

    def test_envelope_db_is_the_owners_formula(self):
        a = _tone(1.234, 16000)[:, 0]
        env = self.A.envelope_db(a)
        n = 160
        frames = len(a) // n
        rms = np.sqrt((a[: frames * n].reshape(frames, n) ** 2).mean(axis=1))
        self.assertEqual(env.tobytes(), (20 * np.log10(np.maximum(rms, 1e-5))).astype(np.float32).tobytes())
        self.assertEqual(env.shape[0], int(len(a) / 160))
        self.assertEqual(self.A.envelope_db(np.zeros(1600, dtype=np.float32)).tolist(), [-100.0] * 10)

    def test_soundfile_is_used_when_it_can_be_imported(self):
        calls = []
        fake = types_module("soundfile")

        def read(path, dtype, always_2d):
            calls.append((path, dtype, always_2d))
            return np.array([[0.5, 0.25], [0.5, 0.25]], dtype=np.float32), 16000

        fake.read = read
        with mock.patch.dict(sys.modules, {"soundfile": fake}):
            out = self.A.load_16k("whatever.flac")
        self.assertEqual(calls, [("whatever.flac", "float32", True)])
        self.assertEqual(out.tolist(), [0.375, 0.375])

    @unittest.skipUnless(HAVE_SF, "soundfile is not installed here: the byte-identity half runs where it is")
    def test_arrays_are_byte_identical_to_the_soundfile_path(self):
        import soundfile as sf
        for kind, rate, ch in self.CASES:
            frames = _tone(0.37, rate, ch)
            path = self._write("sf-%s-%d-%d.wav" % (kind, rate, ch), _wav_bytes(frames, rate, kind))
            ref, sr = sf.read(path, dtype="float32", always_2d=True)
            mine, sr2 = self.A.read_wav(path)
            self.assertEqual((sr, ref.shape), (sr2, mine.shape))
            self.assertEqual(mine.tobytes(), ref.tobytes(), (kind, rate, ch))
            with mock.patch.dict(sys.modules, {"soundfile": None}):
                nosf = self.A.load_16k(path)
            self.assertEqual(nosf.tobytes(), _upstream_downmix(ref, sr).tobytes(), (kind, rate, ch))


def types_module(name):
    import types
    return types.ModuleType(name)


class TestAudioStreaming(unittest.TestCase):
    """read_wav holds the samples once (a memory-mapped file read in blocks), never the file bytes and the samples side by
    side; RF64 / W64 are refused with the way out"""

    def test_peak_memory_is_about_the_output_not_twice_the_file(self):
        import tracemalloc
        A = mod("audio")
        frames = _tone(30.0, 48000, 2)                                      # 30 s, 48 kHz, stereo, 24-bit: 8.6 MB on disk
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "long.wav"
            path.write_bytes(_wav_bytes(frames, 48000, "pcm24"))
            out_bytes = frames.shape[0] * frames.shape[1] * 4
            tracemalloc.start()
            try:
                a2d, sr = A.read_wav(str(path))
                _cur, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            self.assertEqual((a2d.shape, sr), (frames.shape, 48000))
            self.assertLess(peak, out_bytes * 1.35, "peak %d vs output %d" % (peak, out_bytes))
            path.unlink()                                                   # the file is closed (Windows would refuse)
            self.assertFalse(path.exists())

    def test_blocks_give_the_same_samples_as_one_pass_for_every_format(self):
        A = mod("audio")
        with tempfile.TemporaryDirectory() as d:
            for kind in ("pcm8", "pcm16", "pcm24", "pcm32", "float32", "float64"):
                frames = _tone(0.9, 16000, 2)
                path = Path(d) / (kind + ".wav")
                path.write_bytes(_wav_bytes(frames, 16000, kind))
                whole, _ = A.read_wav(str(path))
                with mock.patch.object(A, "BLOCK_FRAMES", 977):             # many small odd-sized blocks
                    blocks, _ = A.read_wav(str(path))
                self.assertEqual(whole.tobytes(), blocks.tobytes(), kind)

    def test_rf64_and_w64_say_what_to_use(self):
        A = mod("audio")
        with tempfile.TemporaryDirectory() as d:
            for tag in (b"RF64", b"BW64", b"riff"):
                path = Path(d) / "big.wav"
                path.write_bytes(tag + b"\xff\xff\xff\xffWAVE" + b"\x00" * 64)
                with self.assertRaises(ValueError) as cm:
                    A.read_wav(str(path))
                self.assertIn("soundfile", str(cm.exception), tag)
            empty = Path(d) / "empty.wav"
            empty.write_bytes(b"")
            with self.assertRaises(ValueError):
                A.read_wav(str(empty))


# ==================================================================================== test_portable.py (12) + new
RATE = 16000


def _speech(seconds):
    rng = np.random.default_rng(0)
    return (0.3 * rng.standard_normal(int(seconds * RATE))).astype(np.float32)


class _W:
    def __init__(self, word, start, end):
        self.word, self.start, self.end = word, start, end


class _Seg:
    words = [_W(" hello", 0.1, 0.4)]


def _align_or_skip(tc):
    try:
        return importlib.import_module("lib.kalam.align")
    except ModuleNotFoundError:
        tc.skipTest("Task 16: lib/kalam/align.py is not ported yet (this test runs unchanged once it is)")


class TestPortable(unittest.TestCase):
    def test_pick_uses_cuda_when_probe_finds_a_gpu(self):
        self.assertEqual(mod("device").pick(probe_cuda=lambda: 1), ("cuda", "float16"))

    def test_pick_falls_back_to_cpu_when_probe_raises(self):
        def broken():
            raise RuntimeError("cudnn64_9.dll not found")
        self.assertEqual(mod("device").pick(probe_cuda=broken), ("cpu", "int8"))

    def test_pick_cpu_when_no_gpu(self):
        self.assertEqual(mod("device").pick(probe_cuda=lambda: 0), ("cpu", "int8"))

    def test_chunks_cover_audio_without_overlap_and_max_25s(self):
        a = _speech(70)
        c = mod("transcribe").chunks(a)
        self.assertTrue(c[0][0] == 0 and c[-1][1] == len(a))
        self.assertTrue(all(c[i][1] == c[i + 1][0] for i in range(len(c) - 1)))
        self.assertTrue(all(e - s <= 25 * RATE for s, e in c))

    def test_chunks_cut_in_silence(self):
        a = _speech(40)
        a[int(22.0 * RATE):int(22.3 * RATE)] = 0
        first_end = mod("transcribe").chunks(a)[0][1] / RATE
        self.assertTrue(22.0 <= first_end <= 22.3)

    def test_chunks_continuous_hard_cut(self):
        c = mod("transcribe").chunks(_speech(30))
        self.assertTrue(20 * RATE <= c[0][1] <= 25 * RATE)

    def test_chunks_short_audio_is_one_chunk(self):
        a = _speech(5)
        self.assertEqual(mod("transcribe").chunks(a), [(0, len(a))])

    def test_align_device_choice(self):
        torch_device = _align_or_skip(self).torch_device
        self.assertEqual(torch_device(lambda: True), "cuda")
        self.assertEqual(torch_device(lambda: False), "cpu")
        self.assertEqual(torch_device(lambda: 1 / 0), "cpu")

    def test_whisper_falls_back_to_cpu_when_cuda_fails_while_transcribing(self):
        T = mod("transcribe")
        made = []

        class Fake:
            def __init__(self, d, device, compute_type):
                self.device = device
                made.append(device)

            def transcribe(self, a, **kw):
                if self.device == "cuda":
                    raise RuntimeError("CUBLAS_STATUS_NOT_SUPPORTED")
                return iter([_Seg()]), None

        with mock.patch.object(T._device, "pick", lambda: ("cuda", "float16")), mock.patch.object(T, "_fw", {}):
            words = T._fw_words(np.zeros(16000, dtype=np.float32), "/m/x", "ar", factory=Fake)
        self.assertTrue(words == [{"w": "hello", "s": 0.1, "e": 0.4}] and made == ["cuda", "cpu"] and T.last_device == "cpu")

    def test_aligner_moves_to_cpu_when_a_cuda_forward_pass_fails(self):
        place_model = _align_or_skip(self).place_model
        calls = []

        class M:
            dev = "cpu"

            def to(self, d):
                calls.append(d)
                self.dev = d
                return self

            def __call__(self, x):
                if self.dev == "cuda":
                    raise RuntimeError("no kernel image is available for execution on the device")
                return "ok"

        m, dev = place_model(M(), "cuda", probe=lambda model, d: model(None))
        self.assertTrue(dev == "cpu" and calls == ["cuda", "cpu"] and m.dev == "cpu")

    def test_session_providers_reports_what_onnx_really_uses(self):
        session_providers = mod("transcribe").session_providers

        class Sess:
            def get_providers(self):
                return ["CPUExecutionProvider"]

        class Inner:
            def __init__(self):
                self._encoder = Sess()

        class Adapter:
            def __init__(self):
                self.asr = Inner()

        self.assertEqual(session_providers(Adapter()), ["CPUExecutionProvider"])
        self.assertEqual(session_providers(object()), [])

    def test_chunks_prefer_a_real_pause_over_a_dip_inside_a_word(self):
        a = _speech(30)
        a[int(21.0 * RATE):int(21.25 * RATE)] *= 0.01      # a real pause (room tone, not digital silence)
        a[int(24.50 * RATE):int(24.52 * RATE)] = 0         # 20 ms dip inside a word
        end = mod("transcribe").chunks(a)[0][1] / RATE
        self.assertTrue(21.0 <= end <= 21.25, end)


class TestDevice(unittest.TestCase):
    """device.add_torch_dlls: the CUDA libraries (plat.enable_cuda_libs: the engine's cuda/bin and NVIDIA's pip wheels) and,
    on Windows, torch\\lib of the Kalam pack when it is installed"""

    def setUp(self):
        self.D = mod("device")
        patcher = mock.patch.object(self.D, "_added", False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_enables_the_engines_cuda_libs_once(self):
        with mock.patch.object(self.D._plat, "enable_cuda_libs", return_value=["/x/cuda/bin"]) as enable:
            self.D.add_torch_dlls()
            self.D.add_torch_dlls()
        enable.assert_called_once_with()

    def test_a_failure_in_enable_cuda_libs_never_raises(self):
        with mock.patch.object(self.D._plat, "enable_cuda_libs", side_effect=OSError("denied")):
            self.D.add_torch_dlls()

    def test_windows_puts_the_torch_lib_folder_of_the_pack_on_the_dll_path(self):
        with tempfile.TemporaryDirectory() as d:
            lib = Path(d) / "torch" / "lib"
            lib.mkdir(parents=True)
            spec = types_module("spec")
            spec.origin = str(Path(d) / "torch" / "__init__.py")
            added = []
            with mock.patch.object(self.D._plat, "enable_cuda_libs", return_value=[]), \
                    mock.patch.object(self.D.sys, "platform", "win32"), \
                    mock.patch("importlib.util.find_spec", return_value=spec), \
                    mock.patch.object(os, "add_dll_directory", lambda p: added.append(p), create=True), \
                    mock.patch.dict(os.environ, {"PATH": "/before"}):
                self.D.add_torch_dlls()
                path = os.environ["PATH"]
        self.assertEqual(added, [str(lib)])
        self.assertTrue(path.startswith(str(lib) + os.pathsep) and path.endswith("/before"))

    def test_other_systems_do_not_look_for_torch(self):
        with mock.patch.object(self.D._plat, "enable_cuda_libs", return_value=[]), \
                mock.patch.object(self.D.sys, "platform", "darwin"), \
                mock.patch("importlib.util.find_spec", side_effect=AssertionError("torch must not be searched")):
            self.D.add_torch_dlls()

    def test_no_torch_in_the_runtime_is_fine(self):
        with mock.patch.object(self.D._plat, "enable_cuda_libs", return_value=[]), \
                mock.patch.object(self.D.sys, "platform", "win32"), mock.patch("importlib.util.find_spec", return_value=None):
            self.D.add_torch_dlls()


class TestTranscribeRouting(unittest.TestCase):
    """the owner's transcribe() routing: the portable backends (faster-whisper CTranslate2 / Parakeet ONNX) or, on Apple
    Silicon, MLX; the model folders sit under the Kalam pack dir of the engine home (tools/kalam/models)"""

    def setUp(self):
        self.T = mod("transcribe")
        self.a = np.zeros(16000, dtype=np.float32)

    def test_folder_names_are_the_packs(self):
        T = self.T
        self.assertEqual((T.CT2_ARABIC_DIR, T.CT2_OTHER_DIR, T.ONNX_ENGLISH_DIR),
                         ("ct2-whisper-turbo-ar-dialectal", "ct2-whisper-large-v3-turbo", "parakeet-tdt-0.6b-v2-onnx"))
        self.assertEqual((T.ARABIC_DIR, T.OTHER_REPO, T.ENGLISH_REPO), ("whisper-turbo-ar-dialectal",
                         "mlx-community/whisper-large-v3-turbo", "mlx-community/parakeet-tdt-0.6b-v2"))

    def test_portable_routes_each_mode_to_its_model_folder(self):
        T = self.T
        seen = []
        with mock.patch.object(T._platform, "backend", lambda: "portable"), \
                mock.patch.object(T, "_fw_words", lambda a, d, lang, **kw: seen.append(("fw", d, lang)) or ["fw"]), \
                mock.patch.object(T, "_onnx_parakeet_words", lambda a, d: seen.append(("onnx", d)) or ["onnx"]):
            self.assertEqual(T.transcribe(self.a, "ar", "/pack"), ["fw"])
            self.assertEqual(T.transcribe(self.a, "en", "/pack"), ["onnx"])
            self.assertEqual(T.transcribe(self.a, "other", "/pack"), ["fw"])
        self.assertEqual(seen, [("fw", str(Path("/pack") / T.CT2_ARABIC_DIR), "ar"),
                                ("onnx", str(Path("/pack") / T.ONNX_ENGLISH_DIR)),
                                ("fw", str(Path("/pack") / T.CT2_OTHER_DIR), None)])

    def test_without_a_models_dir_the_pack_of_the_engine_home_is_used(self):
        T = self.T
        seen = []
        with mock.patch.object(T._platform, "backend", lambda: "portable"), \
                mock.patch.object(T, "_fw_words", lambda a, d, lang, **kw: seen.append(d) or []):
            T.transcribe(self.a, "ar")
        self.assertEqual(seen, [str(mod("store").default_models_dir() / T.CT2_ARABIC_DIR)])

    def test_mlx_routes_each_mode_on_apple_silicon_with_fakes(self):
        T = self.T
        seen = []
        with mock.patch.object(T._platform, "backend", lambda: "mlx"), \
                mock.patch.object(T, "_snapshot", lambda repo: "/snap/" + repo), \
                mock.patch.object(T, "_whisper", lambda a, m, lang: seen.append(("whisper", m, lang)) or ["w"]), \
                mock.patch.object(T, "_parakeet_words", lambda a: seen.append(("parakeet",)) or ["p"]):
            self.assertEqual(T.transcribe(self.a, "ar", "/pack"), ["w"])
            self.assertEqual(T.transcribe(self.a, "en", "/pack"), ["p"])
            self.assertEqual(T.transcribe(self.a, "other", "/pack"), ["w"])
        self.assertEqual(seen, [("whisper", str(Path("/pack") / T.ARABIC_DIR), "ar"), ("parakeet",),
                                ("whisper", "/snap/" + T.OTHER_REPO, None)])

    def test_the_mlx_whisper_call_and_word_shape(self):
        T = self.T
        calls = []
        fake = types_module("mlx_whisper")

        def transcribe(a, **kw):
            calls.append(kw)
            return {"segments": [{"words": [{"word": " \u0645\u0631\u062d\u0628\u0627 ", "start": 0.5, "end": 0.9},
                                            {"word": "  ", "start": 1.0, "end": 1.1}]}, {}]}

        fake.transcribe = transcribe
        with mock.patch.dict(sys.modules, {"mlx_whisper": fake}):
            words = T._whisper(self.a, "/pack/whisper-turbo-ar-dialectal", "ar")
        self.assertEqual(words, [{"w": "\u0645\u0631\u062d\u0628\u0627", "s": 0.5, "e": 0.9}])
        self.assertEqual(calls, [{"path_or_hf_repo": "/pack/whisper-turbo-ar-dialectal", "language": "ar",
                                  "word_timestamps": True, "condition_on_previous_text": False, "verbose": None}])

    def test_cuda_failing_at_load_time_falls_back_to_the_cpu_once(self):
        T = self.T
        made = []

        class Fake:
            def __init__(self, d, device, compute_type):
                made.append((device, compute_type))
                if device == "cuda":
                    raise RuntimeError("CUDA driver version is insufficient")
                self.device = device

            def transcribe(self, a, **kw):
                return iter([_Seg()]), None

        with mock.patch.object(T._device, "pick", lambda: ("cuda", "float16")), mock.patch.object(T, "_fw", {}):
            words = T._fw_words(self.a, "/m/y", None, factory=Fake)
            again = T._fw_words(self.a, "/m/y", None, factory=Fake)              # the loaded CPU model is reused
        self.assertEqual(made, [("cuda", "float16"), ("cpu", "int8")])
        self.assertEqual((words, again), ([{"w": "hello", "s": 0.1, "e": 0.4}],) * 2)
        self.assertEqual(T.last_device, "cpu")

    def test_the_cuda_libs_are_enabled_before_the_first_model_loads(self):
        T = self.T
        order = []

        class Fake:
            def __init__(self, d, device, compute_type):
                order.append("load")

            def transcribe(self, a, **kw):
                return iter([_Seg()]), None

        with mock.patch.object(T._device, "add_torch_dlls", lambda: order.append("dlls")), \
                mock.patch.object(T._device, "pick", lambda: ("cpu", "int8")), mock.patch.object(T, "_fw", {}):
            T._fw_words(self.a, "/m/z", "ar", factory=Fake)
        self.assertEqual(order, ["dlls", "load"])


# =========================================================================================== test_setup_models.py (2) + new
class TestSetupModels(unittest.TestCase):
    def setUp(self):
        self.S = mod("setup_models")

    def test_preprocessor_config_has_the_models_mel_count(self):
        with tempfile.TemporaryDirectory() as tmp_path:
            self.S.write_preprocessor(Path(tmp_path), n_mels=128)
            with open(Path(tmp_path) / "preprocessor_config.json", encoding="utf-8") as f:
                cfg = json.load(f)
        self.assertTrue(cfg["feature_size"] == 128 and cfg["sampling_rate"] == 16000 and cfg["hop_length"] == 160)

    def test_portable_complete_needs_every_model(self):
        S = self.S
        with tempfile.TemporaryDirectory() as tmp_path:
            tmp_path = Path(tmp_path)
            self.assertEqual(S.portable_missing(tmp_path), [S.CT2_ARABIC, S.CT2_OTHER, S.ONNX_ENGLISH])
            for d, f in ((S.CT2_ARABIC, "model.bin"), (S.CT2_OTHER, "model.bin"), (S.ONNX_ENGLISH, "encoder-model.onnx")):
                (tmp_path / d).mkdir()
                (tmp_path / d / f).write_bytes(b"x")
            self.assertEqual(S.portable_missing(tmp_path), [])

    def test_folder_names_match_the_runtime_and_the_sources_are_the_owners(self):
        S, T = self.S, mod("transcribe")
        self.assertEqual((S.CT2_ARABIC, S.CT2_OTHER, S.ONNX_ENGLISH), (T.CT2_ARABIC_DIR, T.CT2_OTHER_DIR, T.ONNX_ENGLISH_DIR))
        self.assertEqual((S.ARABIC_SRC, S.OTHER_SRC, S.ONNX_SRC), ("oddadmix/whisper-large-v3-turbo-arabic-dialectal",
                         "openai/whisper-large-v3-turbo", "istupakov/parakeet-tdt-0.6b-v2-onnx"))
        self.assertEqual(S.ONNX_FILES, ["config.json", "vocab.txt", "nemo128.onnx", "decoder_joint-model.onnx",
                                        "encoder-model.onnx", "encoder-model.onnx.data"])

    def test_convert_ct2_converts_to_float16_copies_the_tokenizer_and_writes_the_mel_count(self):
        S = self.S
        calls = []
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src = d / "snap"
            src.mkdir()
            (src / "config.json").write_text(json.dumps({"num_mel_bins": 128}), encoding="utf-8")
            (src / "tokenizer.json").write_text("{}", encoding="utf-8")
            out = d / "out"
            out.mkdir()
            conv_mod = types_module("ctranslate2.converters")

            class TransformersConverter:
                def __init__(self, path):
                    calls.append(("init", path))

                def convert(self, dest, quantization, force):
                    calls.append(("convert", dest, quantization, force))

            conv_mod.TransformersConverter = TransformersConverter
            hub = types_module("huggingface_hub")
            hub.snapshot_download = lambda repo, allow_patterns=None, **kw: calls.append(
                ("download", repo, allow_patterns, kw.get("revision"))) or str(src)
            with mock.patch.dict(sys.modules, {"ctranslate2": types_module("ctranslate2"), "ctranslate2.converters": conv_mod,
                                               "huggingface_hub": hub}):
                S.convert_ct2(S.ARABIC_SRC, out)
            self.assertTrue((out / "tokenizer.json").is_file())
            self.assertEqual(json.loads((out / "preprocessor_config.json").read_text(encoding="utf-8"))["feature_size"], 128)
        self.assertEqual(calls, [("download", S.ARABIC_SRC, ["*.json", "model.safetensors", "*.txt"], S.REVISIONS[S.ARABIC_SRC]),
                                 ("init", str(src)), ("convert", str(out), "float16", True)])

    def test_main_portable_prepares_only_what_is_missing_and_never_vendors(self):
        S = self.S
        calls = []
        with tempfile.TemporaryDirectory() as d:
            md = Path(d) / "models"
            (md / S.CT2_OTHER).mkdir(parents=True)
            (md / S.CT2_OTHER / "model.bin").write_bytes(b"x")                 # already there
            hub = types_module("huggingface_hub")
            hub.snapshot_download = lambda repo, **kw: calls.append(
                ("download", repo, kw.get("local_dir"), kw.get("revision"))) or str(d)
            out = io.StringIO()
            with mock.patch.dict(sys.modules, {"huggingface_hub": hub}), \
                    mock.patch.object(S, "convert_ct2", lambda repo, dest: calls.append(("convert", repo, str(dest)))), \
                    contextlib.redirect_stdout(out):
                S.main_portable(str(md))
        self.assertEqual(calls, [("convert", S.ARABIC_SRC, str(md / S.CT2_ARABIC)),
                                 ("download", S.ONNX_SRC, str(md / S.ONNX_ENGLISH), S.REVISIONS[S.ONNX_SRC]),
                                 ("download", S.ALIGNER_REPO, None, S.ALIGNER_REV)])
        text = out.getvalue()
        self.assertIn("portable models ready", text)
        self.assertNotIn(str(S.CT2_OTHER), text)
        notices = [l for l in text.splitlines() if l.lstrip().startswith("model:")]
        self.assertEqual(len(notices), 3)                                  # one notice per model, before its download
        for repo, licence in ((S.ARABIC_SRC, "Apache-2.0"), (S.ONNX_SRC, "CC-BY-4.0"), (S.ALIGNER_REPO, "CC-BY-NC-4.0")):
            line = next(l for l in notices if repo in l)
            self.assertIn(licence, line)
            self.assertIn(S.REVISIONS[repo][:8], line)
        self.assertLess(text.index(S.ONNX_SRC), text.index("portable models ready"))

    def test_the_mlx_conversion_is_for_a_mac_only(self):
        S = self.S
        with mock.patch.object(S.sys, "platform", "win32"):
            with self.assertRaises(RuntimeError) as cm:
                S.main("/models")
            self.assertIn("Apple Silicon", str(cm.exception))
            with self.assertRaises(RuntimeError):
                S.convert_hf_whisper("some/repo", Path("/out"))

    def test_every_download_source_has_a_pinned_revision_from_the_licence_table(self):
        S = self.S
        wanted = {S.ARABIC_SRC, S.OTHER_SRC, S.ONNX_SRC, S.ALIGNER_REPO, "mlx-community/whisper-large-v3-turbo",
                  "mlx-community/parakeet-tdt-0.6b-v2"}
        self.assertEqual(set(S.REVISIONS), wanted)
        for repo, rev in S.REVISIONS.items():
            self.assertRegex(rev, r"^[0-9a-f]{40}$", repo)
        align_w2v = importlib.import_module("lib.align_w2v")
        self.assertEqual((S.ALIGNER_REPO, S.ALIGNER_REV), (align_w2v.MMS_REPO, align_w2v.MMS_REV))   # one place for the aligner
        doc = HERE.parents[1] / "docs" / "legal" / "third-party-licences.md"
        if not doc.is_file():
            self.skipTest("docs/ is not part of the plugin zip")
        lines = doc.read_text(encoding="utf-8").splitlines()
        for repo, rev in S.REVISIONS.items():
            self.assertTrue(any(repo in l and rev[:8] in l for l in lines), "%s @ %s is not in the licence table" % (repo, rev[:8]))

    def test_an_unpinned_repo_is_refused_before_anything_is_downloaded(self):
        S = self.S
        calls = []
        hub = types_module("huggingface_hub")
        hub.snapshot_download = lambda *a, **k: calls.append(a) or "/x"
        with mock.patch.dict(sys.modules, {"huggingface_hub": hub, "ctranslate2": types_module("ctranslate2"),
                                           "ctranslate2.converters": types_module("ctranslate2.converters")}):
            with self.assertRaises(ValueError) as cm:
                S.convert_ct2("some/unpinned-repo", Path("/out"))
        self.assertIn("no pinned revision", str(cm.exception))
        self.assertEqual(calls, [])

    def test_the_mac_path_pins_every_download_and_prints_the_notices(self):
        S = self.S
        calls, converted = [], []
        hub = types_module("huggingface_hub")
        hub.snapshot_download = lambda repo, **kw: calls.append((repo, kw.get("revision"))) or "/x"
        out = io.StringIO()
        with mock.patch.dict(sys.modules, {"huggingface_hub": hub}), mock.patch.object(S.sys, "platform", "darwin"), \
                mock.patch.object(S, "convert_hf_whisper", lambda repo, dest: converted.append(repo)), \
                contextlib.redirect_stdout(out), tempfile.TemporaryDirectory() as d:
            S.main(d)
        self.assertEqual(converted, [S.ARABIC_SRC])
        self.assertEqual(calls, [(repo, S.REVISIONS[repo]) for repo in S.OTHERS])
        self.assertEqual(len([l for l in out.getvalue().splitlines() if l.lstrip().startswith("model:")]), 4)

    def test_the_mlx_conversion_downloads_the_pinned_revision(self):
        S = self.S
        calls = []
        hub = types_module("huggingface_hub")

        def snapshot(repo, **kw):
            calls.append((repo, kw.get("revision")))
            raise RuntimeError("stop after the download call")

        hub.snapshot_download = snapshot
        mlx, core = types_module("mlx"), types_module("mlx.core")
        with mock.patch.dict(sys.modules, {"huggingface_hub": hub, "mlx": mlx, "mlx.core": core}), \
                mock.patch.object(S.sys, "platform", "darwin"):
            with self.assertRaises(RuntimeError):
                S.convert_hf_whisper(S.ARABIC_SRC, Path("/out"))
        self.assertEqual(calls, [(S.ARABIC_SRC, S.REVISIONS[S.ARABIC_SRC])])

    def test_the_mlx_name_map_is_the_owners(self):
        S = self.S
        self.assertEqual(S._REPL[0], ("model.", ""))
        self.assertEqual(len(S._REPL), 17)
        self.assertEqual(S.OTHERS, ["mlx-community/whisper-large-v3-turbo", "mlx-community/parakeet-tdt-0.6b-v2",
                                    "MahmoudAshraf/mms-300m-1130-forced-aligner"])

    def test_cli_defaults_to_the_pack_of_the_engine_home_and_keeps_the_hf_cache_there(self):
        S = self.S
        seen = []
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"WHYNOT_HOME": home}):
            os.environ.pop("HF_HOME", None)
            with mock.patch.object(S, "main_portable", lambda md: seen.append(("portable", md, os.environ.get("HF_HOME")))):
                S.main_cli(["--portable"])
            self.assertEqual(seen, [("portable", str(Path(home) / "tools" / "kalam" / "models"),
                                     str(Path(home) / "tools" / "kalam" / "hf"))])
        with mock.patch.dict(os.environ, {"HF_HOME": "/somewhere/else"}), \
                mock.patch.object(S, "main_portable", lambda md: seen.append(("portable", md, os.environ.get("HF_HOME")))):
            S.main_cli(["/my/models", "--portable"])
        self.assertEqual(seen[-1], ("portable", "/my/models", "/somewhere/else"))

    def test_cli_picks_the_backend_like_the_runtime_and_rejects_unknown_flags(self):
        S = self.S
        seen = []
        with mock.patch.object(S, "main_portable", lambda md: seen.append("portable")), \
                mock.patch.object(S, "main", lambda md: seen.append("mlx")), \
                mock.patch.object(S._platform, "backend", lambda: "mlx"):
            S.main_cli(["/m"])
            S.main_cli(["/m", "--portable"])
        self.assertEqual(seen, ["mlx", "portable"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(S.main_cli(["/m", "--nope"]), 2)


# ============================================================================== engine: doctor, run, CLI (JSON lines)
import types as _types  # noqa: E402

SECRET_KEY = "sk-test-key-0000-not-a-real-key"
FAKE_EMAIL, FAKE_ORG = "ali.example@example.invalid", "Example Org"
WORDS = [("\u0645\u0631\u062d\u0628\u0627", 0.40, 0.80), ("\u0628\u0643\u0645", 0.85, 1.20),
         ("\u0641\u064a", 1.25, 1.40), ("\u0627\u0644\u062d\u0644\u0642\u0629", 1.45, 2.00),
         ("Soft", 2.60, 2.90), ("Tissue", 2.95, 3.30)]


def fake_transcribe(a, mode, models):
    fake_transcribe.calls.append((mode, models))
    return [{"w": w, "s": s_, "e": e} for w, s_, e in WORDS]


fake_transcribe.calls = []


def fake_align(a, words):
    return [dict(w, score=0.9) for w in words]


def fake_aligner_module():
    return _types.SimpleNamespace(align=fake_align, REPO="example/aligner", _load=lambda: (None, {}, "cpu"))


def write_wav(path: Path, seconds=3.6):
    path.write_bytes(_wav_bytes(_tone(seconds, 16000), 16000, "pcm16"))
    return str(path)


def capture_main(argv, stdin_text=None):
    """(exit code, stdout BYTES, stderr text) of engine.main(argv) with stdout as a UTF-8 byte stream (like a pipe)"""
    E = mod("engine")
    raw = io.BytesIO()
    out = io.TextIOWrapper(raw, encoding="cp1252", errors="strict", newline="\r\n", write_through=True)   # a hostile console
    err = io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
        code = E.main(argv)
        out.flush()
    return code, raw.getvalue(), err.getvalue()


def json_lines(data: bytes) -> list:
    return [json.loads(line) for line in data.decode("utf-8").split("\n") if line.strip()]


class _EchoAnthropic:
    """the API client stand-in: replies with the lines it was sent (a correction that changes nothing)"""
    made = []

    def __init__(self, **kw):
        _EchoAnthropic.made.append(kw)
        self.beta = self.messages = self

    def create(self, **kw):
        lines = json.loads(kw["messages"][0]["content"])["lines"]
        blk = _types.SimpleNamespace(type="text", text=json.dumps({"lines": lines}, ensure_ascii=False))
        return _types.SimpleNamespace(content=[blk], stop_reason="end_turn")


def echo_api_modules():
    anthropic = types_module("anthropic")

    class APIError(Exception):
        pass

    anthropic.APIError, anthropic.Anthropic = APIError, _EchoAnthropic
    return mock.patch.dict(sys.modules, {"anthropic": anthropic})


class EngineCase(unittest.TestCase):
    def setUp(self):
        self.E = mod("engine")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.wav = write_wav(self.tmp / "clip.wav")
        self.out = self.tmp / "out"
        fake_transcribe.calls.clear()
        _EchoAnthropic.made.clear()
        for patcher in (mock.patch.object(self.E, "transcribe", fake_transcribe),
                        mock.patch.object(self.E, "_align_module", fake_aligner_module),
                        mock.patch.object(self.E, "_gpu", lambda: "Example GPU, 000.00")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def settings_file(self, settings):
        f = self.tmp / "run-settings.json"
        f.write_text(json.dumps(settings), encoding="utf-8")
        return f

    def run_main(self, settings, mode="ar", extra=()):
        f = self.settings_file(settings)
        argv = ["run", "--wav", self.wav, "--mode", mode, "--out", str(self.out), "--settings", str(f),
                "--models", str(self.tmp / "models")] + list(extra)
        return f, argv, capture_main(argv)


class TestEngineRun(EngineCase):
    """`kalam_engine.py run` as lib.kalam.engine.main: one JSON object per stdout line (UTF-8, LF, ensure_ascii=False)"""

    def test_an_uncorrected_run_emits_the_stages_and_writes_utf8_lf_files(self):
        f, argv, (code, stdout, stderr) = self.run_main({"correct": False})
        self.assertEqual(code, 0, stderr)
        ev = json_lines(stdout)
        self.assertEqual([e["stage"] for e in ev], ["loading", "transcribing", "aligning", "captions", "done"])
        self.assertEqual(ev[1]["mode"], "ar")
        self.assertEqual(ev[-1]["corrected"], False)
        self.assertNotIn("notice", ev[-1])
        self.assertNotIn(b"\r", stdout)
        for name in ("captions.srt", "captions.json", "corrected.json", "words.json"):
            raw = (self.out / name).read_bytes()
            self.assertNotIn(b"\r", raw, name)
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), name)
            raw.decode("utf-8")
        srt = (self.out / "captions.srt").read_text(encoding="utf-8")
        self.assertTrue(srt.startswith("1\n00:00:00,400 --> "))
        self.assertIn("\u0645\u0631\u062d\u0628\u0627", srt)
        caps = json.loads((self.out / "captions.json").read_text(encoding="utf-8"))
        self.assertTrue(caps and caps[0]["n"] == 1 and set(caps[0]) == {"n", "s", "e", "text"})
        self.assertEqual(ev[-1]["srt"], str(self.out / "captions.srt"))
        self.assertEqual(fake_transcribe.calls[0][1], str(self.tmp / "models"))

    def test_the_run_has_no_gaps_between_captions_like_upstream(self):
        code, stdout, _ = self.run_main({"correct": False})[2]
        self.assertEqual(code, 0)
        caps = json.loads((self.out / "captions.json").read_text(encoding="utf-8"))
        self.assertTrue(all(a["e"] == b["s"] for a, b in zip(caps, caps[1:])))

    def test_the_settings_file_is_deleted_as_soon_as_it_is_read(self):
        f, argv, (code, stdout, _) = self.run_main({"correct": False, "api_key": SECRET_KEY})
        self.assertEqual(code, 0)
        self.assertFalse(f.exists())

    def test_the_settings_file_is_deleted_even_when_the_run_fails(self):
        self.wav = str(self.tmp / "missing.wav")
        f, argv, (code, stdout, _) = self.run_main({"correct": False, "api_key": SECRET_KEY})
        self.assertEqual(code, 1)
        self.assertFalse(f.exists())
        ev = json_lines(stdout)
        self.assertEqual(ev[-1]["stage"], "error")
        self.assertIn("missing.wav", ev[-1]["error"])
        self.assertNotIn(SECRET_KEY.encode(), stdout)

    def test_arabic_in_a_line_is_utf8_bytes_not_escapes(self):
        name = "ملف-اختبار"
        self.wav = str(self.tmp / (name + ".wav"))                          # an Arabic file name that does not exist
        f, argv, (code, stdout, _) = self.run_main({"correct": False})
        self.assertEqual(code, 1)
        self.assertIn(name.encode("utf-8"), stdout)
        self.assertNotIn(b"\\u0645", stdout)
        self.assertNotIn(b"\r", stdout)

    def test_unreadable_settings_are_an_error_line_and_still_deleted(self):
        f = self.tmp / "bad.json"
        f.write_text("{not json", encoding="utf-8")
        code, stdout, _ = capture_main(["run", "--wav", self.wav, "--out", str(self.out), "--settings", str(f)])
        self.assertEqual(code, 1)
        self.assertFalse(f.exists())
        self.assertEqual(json_lines(stdout)[-1]["stage"], "error")

    def test_the_api_key_reaches_the_client_and_never_the_output_files_log_or_argv(self):
        with echo_api_modules():
            f, argv, (code, stdout, stderr) = self.run_main({"correct": True, "backend": "api", "api_key": SECRET_KEY})
        self.assertEqual(code, 0, stderr)
        self.assertEqual(_EchoAnthropic.made, [{"api_key": SECRET_KEY, "max_retries": 3}])
        ev = json_lines(stdout)
        self.assertEqual(ev[-1]["corrected"], True)
        self.assertNotIn(SECRET_KEY, " ".join(argv))                                    # never on the command line
        blobs = [stdout, stderr.encode("utf-8")] + [p.read_bytes() for p in self.out.iterdir()]
        log = mod("store").Store().log_file
        if log.exists():
            blobs.append(log.read_bytes())
        for blob in blobs:
            self.assertNotIn(SECRET_KEY.encode("utf-8"), blob)

    def test_a_key_that_an_error_message_would_repeat_is_scrubbed(self):
        def boom(a, mode, models):
            raise RuntimeError("the server said: bad key %s" % SECRET_KEY)

        with mock.patch.object(self.E, "transcribe", boom):
            f, argv, (code, stdout, stderr) = self.run_main({"correct": False, "api_key": SECRET_KEY})
        self.assertEqual(code, 1)
        last = json_lines(stdout)[-1]
        self.assertEqual(last["stage"], "error")
        self.assertIn("***", last["error"])
        self.assertNotIn(SECRET_KEY, json.dumps(last, ensure_ascii=False))
        self.assertNotIn(SECRET_KEY, mod("store").Store().log_file.read_text(encoding="utf-8") if mod("store").Store().log_file.exists() else "")

    def test_without_claude_the_run_still_makes_captions_with_a_notice(self):
        code, stdout, _ = self.run_main({"correct": True})[2]
        done = json_lines(stdout)[-1]
        self.assertEqual((code, done["stage"], done["corrected"]), (0, "done", False))
        self.assertEqual(done["notice"], "claude_code_missing")
        self.assertTrue((self.out / "captions.srt").exists())

    def test_missing_key_on_the_api_backend_keeps_the_captions_and_says_why(self):
        code, stdout, _ = self.run_main({"correct": True, "backend": "api", "api_key": ""})[2]
        done = json_lines(stdout)[-1]
        self.assertEqual((code, done["corrected"], done["notice"]), (0, False, "no_api_key"))

    def test_a_refused_subscription_is_reported_with_its_how_and_the_captions_keep_their_text(self):
        auth = lambda args, cwd: (0, json.dumps({"loggedIn": True, "authMethod": "api_key", "email": FAKE_EMAIL,
                                                 "orgName": FAKE_ORG}))
        correct_mod = mod("correct")
        with mock.patch.object(self.E, "find_claude_code", lambda *a, **k: "/x/claude"), \
                mock.patch.object(correct_mod, "_run_auth_status", auth):
            code, stdout, _ = self.run_main({"correct": True})[2]
        done = json_lines(stdout)[-1]
        self.assertEqual((code, done["corrected"], done["notice"]), (0, False, "subscription_not_active"))
        self.assertIn("ANTHROPIC_API_KEY", done["how"])
        self.assertNotIn(FAKE_EMAIL.encode(), stdout)
        self.assertNotIn(FAKE_ORG.encode(), stdout)

    def test_the_engine_does_not_need_the_aligner_to_import_and_says_so_when_it_is_missing(self):
        def missing():
            raise ImportError("No module named 'lib.kalam.align'")

        with mock.patch.object(self.E, "_align_module", missing):
            f, argv, (code, stdout, _) = self.run_main({"correct": False})
        self.assertEqual(code, 1)
        last = json_lines(stdout)[-1]
        self.assertEqual(last["stage"], "error")
        self.assertIn("aligner", last["error"])

    def test_kmp_duplicate_lib_ok_is_set_on_windows_only(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("KMP_DUPLICATE_LIB_OK", None)
            with mock.patch.object(self.E._platform, "is_windows", lambda: True):
                self.E.prepare_env()
            self.assertEqual(os.environ.get("KMP_DUPLICATE_LIB_OK"), "TRUE")
            os.environ["KMP_DUPLICATE_LIB_OK"] = "FALSE"
            with mock.patch.object(self.E._platform, "is_windows", lambda: True):
                self.E.prepare_env()
            self.assertEqual(os.environ["KMP_DUPLICATE_LIB_OK"], "FALSE")                # setdefault: the caller wins
            os.environ.pop("KMP_DUPLICATE_LIB_OK")
            with mock.patch.object(self.E._platform, "is_windows", lambda: False):
                self.E.prepare_env()
            self.assertNotIn("KMP_DUPLICATE_LIB_OK", os.environ)

    def test_the_hf_cache_stays_in_the_engine_home_unless_set(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("HF_HOME", None)
            self.E.prepare_env()
            self.assertEqual(os.environ["HF_HOME"], str(mod("store").Store().hf_dir))

    def test_the_default_models_dir_is_the_pack_of_the_engine_home(self):
        f = self.settings_file({"correct": False})
        code, stdout, _ = capture_main(["run", "--wav", self.wav, "--out", str(self.out), "--settings", str(f)])
        self.assertEqual(code, 0)
        self.assertEqual(fake_transcribe.calls[0][1], str(mod("store").default_models_dir()))

    def test_run_log_lines_carry_no_settings(self):
        self.run_main({"correct": False, "api_key": SECRET_KEY, "rules": "private client rules", "glossary": {"X": ["y"]}})
        log = mod("store").Store().log_file
        text = log.read_text(encoding="utf-8")
        self.assertTrue(text)
        for needle in (SECRET_KEY, "private client rules", "glossary"):
            self.assertNotIn(needle, text)


class TestEngineProcess(unittest.TestCase):
    """the real process: python -m lib.kalam.engine, stdout is bytes (UTF-8, LF) whatever the console encoding is"""

    def test_doctor_quick_in_a_real_process_prints_one_utf8_json_line(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, PYTHONPATH=str(ENGINE), PYTHONIOENCODING="cp1252", KALAM_BACKEND="portable")
            env.pop("PYTHONUTF8", None)
            p = subprocess.run([sys.executable, "-s", "-B", "-m", "lib.kalam.engine", "doctor", "--models", d, "--quick"],
                               capture_output=True, env=env, timeout=120, cwd=str(ENGINE))
        self.assertEqual(p.returncode, 1, p.stderr[-500:])
        self.assertNotIn(b"\r", p.stdout)
        lines = p.stdout.decode("utf-8").split("\n")
        self.assertEqual(len([x for x in lines if x.strip()]), 1)
        rep = json.loads(lines[0])
        self.assertEqual((rep["backend"], rep["ok"]), ("portable", False))


class TestDoctor(unittest.TestCase):
    def test_doctor_quick_reports_missing_models(self):
        E = mod("engine")
        with tempfile.TemporaryDirectory() as tmp_path, mock.patch.dict(os.environ, {"KALAM_BACKEND": "portable"}), \
                mock.patch.object(E, "aligner_present", lambda: False), mock.patch.object(E, "_gpu", lambda: ""):
            # never point huggingface_hub at tmp: it keeps HF_HOME from first import
            code, stdout, _ = capture_main(["doctor", "--models", tmp_path, "--quick"])
        rep = json_lines(stdout)[-1]
        self.assertTrue(code == 1 and rep["ok"] is False)
        self.assertEqual(rep["backend"], "portable")
        self.assertEqual(set(rep["models"]), {"arabic", "english", "other", "aligner"})
        self.assertTrue(all(v is not True for v in rep["models"].values()))
        self.assertTrue(rep["device"] in ("cuda", "cpu") and "python" in rep and "claude" in rep)

    def test_doctor_quick_ok_when_files_exist(self):
        E = mod("engine")
        with tempfile.TemporaryDirectory() as tmp_path, mock.patch.dict(os.environ, {"KALAM_BACKEND": "portable"}), \
                mock.patch.object(E, "aligner_present", lambda: True), mock.patch.object(E, "_gpu", lambda: ""):
            tmp_path = Path(tmp_path)
            for d, f in (("ct2-whisper-turbo-ar-dialectal", "model.bin"), ("ct2-whisper-large-v3-turbo", "model.bin"),
                         ("parakeet-tdt-0.6b-v2-onnx", "encoder-model.onnx")):
                (tmp_path / d).mkdir()
                (tmp_path / d / f).write_bytes(b"x")
            _code, stdout, _ = capture_main(["doctor", "--models", str(tmp_path), "--quick"])
        rep = json_lines(stdout)[-1]
        self.assertEqual(rep["models"], {"arabic": True, "english": True, "other": True, "aligner": True})


class TestDoctorNew(unittest.TestCase):
    def setUp(self):
        self.E = mod("engine")
        self.real_aligner_present = self.E.aligner_present
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.md = Path(self._tmp.name)
        for d, f in (("ct2-whisper-turbo-ar-dialectal", "model.bin"), ("ct2-whisper-large-v3-turbo", "model.bin"),
                     ("parakeet-tdt-0.6b-v2-onnx", "encoder-model.onnx")):
            (self.md / d).mkdir()
            (self.md / d / f).write_bytes(b"x")
        for patcher in (mock.patch.dict(os.environ, {"KALAM_BACKEND": "portable"}),
                        mock.patch.object(self.E, "aligner_present", lambda: True),
                        mock.patch.object(self.E, "_gpu", lambda: "Example GPU, 000.00"),
                        mock.patch.object(self.E._device, "add_torch_dlls", lambda: None)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_cuda_machine_whose_cuda_fails_at_run_time_is_reported_as_cpu(self):
        """Windows CUDA -> CPU (faked): pick() says cuda, the transcriber falls back, the doctor shows what really ran"""
        E = self.E

        def transcribe(a, mode, models):
            E._tr.last_device = "cpu"                                   # what _fw_words sets after its CPU fallback
            return []

        with mock.patch.object(E._device, "pick", lambda: ("cuda", "float16")), mock.patch.object(E._tr, "transcribe", transcribe), \
                mock.patch.object(E, "_align_module", fake_aligner_module):
            rep = E.doctor(str(self.md), quick=False)
        self.assertEqual(rep["device"], "cpu")
        self.assertEqual(rep["devices"]["arabic"], "cpu")
        self.assertEqual(rep["models"], {"arabic": True, "english": True, "other": True, "aligner": True})

    def test_quick_does_not_load_anything_and_shows_the_picked_device(self):
        E = self.E

        def never(*a, **k):
            raise AssertionError("a quick doctor must not load a model")

        with mock.patch.object(E._device, "pick", lambda: ("cuda", "float16")), mock.patch.object(E._tr, "transcribe", never):
            rep = E.doctor(str(self.md), quick=True)
        self.assertEqual((rep["device"], rep["devices"]), ("cuda", {}))

    def test_a_model_that_fails_to_load_is_named_with_the_error(self):
        E = self.E

        def transcribe(a, mode, models):
            if mode == "en":
                raise RuntimeError("onnxruntime could not load the encoder")
            E._tr.last_device = "cuda"
            return []

        with mock.patch.object(E._tr, "transcribe", transcribe), mock.patch.object(E, "_align_module", fake_aligner_module):
            rep = E.doctor(str(self.md), quick=False)
        self.assertEqual(rep["models"]["english"], "RuntimeError: onnxruntime could not load the encoder")
        self.assertIs(rep["models"]["arabic"], True)
        self.assertIs(rep["ok"], False)

    def test_without_the_aligner_package_the_doctor_says_missing(self):
        E = self.E

        def missing():
            raise ImportError("no align")

        with mock.patch.object(E, "aligner_present", self.real_aligner_present), mock.patch.object(E, "_align_module", missing):
            self.assertFalse(E.aligner_present())

    def test_the_correction_line_shows_the_subscription_or_the_refusal(self):
        E, correct_mod = self.E, mod("correct")
        ok = lambda args, cwd: (0, json.dumps({"loggedIn": True, "authMethod": "claude.ai", "email": FAKE_EMAIL, "orgName": FAKE_ORG}))
        bad = lambda args, cwd: (0, json.dumps({"loggedIn": True, "authMethod": "api_key_helper", "email": FAKE_EMAIL, "orgName": FAKE_ORG}))
        with mock.patch.object(E, "find_claude_code", lambda *a, **k: "/x/claude"):
            with mock.patch.object(correct_mod, "_run_auth_status", ok):
                rep = E.doctor(str(self.md), quick=True)
            self.assertEqual(rep["correction"]["ok"], True)
            self.assertIn("subscription (claude.ai)", rep["correction"]["line"])
            with mock.patch.object(correct_mod, "_run_auth_status", bad):
                rep2 = E.doctor(str(self.md), quick=True)
        self.assertEqual((rep2["correction"]["ok"], rep2["correction"]["code"]), (False, "subscription_not_active"))
        self.assertIn("apiKeyHelper", rep2["correction"]["line"])
        for r in (rep, rep2):
            blob = json.dumps(r, ensure_ascii=False)
            self.assertNotIn(FAKE_EMAIL, blob)
            self.assertNotIn(FAKE_ORG, blob)

    def test_no_identity_value_in_the_doctor_output_the_log_or_the_report_text(self):
        E, correct_mod = self.E, mod("correct")
        ok = lambda args, cwd: (0, json.dumps({"loggedIn": True, "authMethod": "claude.ai", "email": FAKE_EMAIL,
                                               "orgId": "org-0000-example", "orgName": FAKE_ORG, "token": "sk-ant-fake-0000"}))
        with mock.patch.object(E, "find_claude_code", lambda *a, **k: "/x/claude"), \
                mock.patch.object(correct_mod, "_run_auth_status", ok):
            code, stdout, _ = capture_main(["doctor", "--models", str(self.md), "--quick"])
        store = mod("store").Store()
        report = store.report_text(json_lines(stdout)[-1])
        blobs = [stdout.decode("utf-8"), report, store.log_file.read_text(encoding="utf-8") if store.log_file.exists() else ""]
        for blob in blobs:
            for secret in (FAKE_EMAIL, FAKE_ORG, "org-0000-example", "sk-ant-fake-0000"):
                self.assertNotIn(secret, blob)
        self.assertIn("claude.ai", stdout.decode("utf-8"))


class TestEngineFixRound1(EngineCase):
    """Task 11 review: M5 (nvidia-smi through absolute-only discovery), M7 (the key injected into a logged value),
    M9 (the text layer is flushed before bytes are written), and the any-clip checks on a fake run"""


    def test_the_run_log_scrubs_a_key_that_a_logged_value_carries(self):
        E = self.E
        store = mod("store").Store()

        def fake_run(wav, mode, out, settings, models, log=None):
            log("note: the server echoed %s back" % settings["api_key"])
            return {"stage": "done"}

        with mock.patch.object(E, "run", fake_run):
            f, argv, (code, stdout, _) = self.run_main({"correct": False, "api_key": SECRET_KEY})
        self.assertEqual(code, 0)
        text = store.log_file.read_text(encoding="utf-8")
        self.assertIn("note: the server echoed ***", text)
        self.assertNotIn(SECRET_KEY, text)

    def test_say_flushes_text_written_before_it(self):
        E = self.E
        raw = io.BytesIO()
        out = io.TextIOWrapper(raw, encoding="utf-8", newline="\n")             # buffered: not write_through
        with mock.patch.object(sys, "stdout", out):
            out.write("a library print\n")
            E.say(stage="x")
        data = raw.getvalue()
        self.assertTrue(data.startswith(b"a library print\n{"), data)
        out.detach()

    def test_the_any_clip_invariants_hold_on_a_fake_run_and_a_rerun_is_identical(self):
        outs = []
        for n in (1, 2):
            self.out = self.tmp / ("out%d" % n)
            code, stdout, _ = self.run_main({"correct": False})[2]
            self.assertEqual(code, 0)
            outs.append(self.out)
            duration = 3.6
            for name in ("captions.srt", "captions.json", "words.json", "corrected.json"):
                check_utf8_lf(self, (self.out / name).read_bytes(), name)
            check_words(self, json.loads((self.out / "words.json").read_text(encoding="utf-8")), duration)
            check_srt(self, (self.out / "captions.srt").read_text(encoding="utf-8"), duration)
        for name in ("captions.srt", "captions.json", "words.json"):
            self.assertEqual((outs[0] / name).read_bytes(), (outs[1] / name).read_bytes(), name)


class TestGpuLookup(unittest.TestCase):
    """engine._gpu: nvidia-smi is found like Claude: absolute PATH folders only (platform.find_on_path), then System32 on
    Windows; a file in the current folder or a bare name is never started"""

    def setUp(self):
        self.E = mod("engine")

    def test_an_absolute_path_hit_is_started_by_its_full_path(self):
        E = self.E
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            touch(d / "cwd" / "nvidia-smi.exe")
            real = touch(d / "bin" / ("nvidia-smi.exe" if os.name == "nt" else "nvidia-smi"))
            os.chmod(real, 0o755)
            seen = []

            def fake_run(args, **kw):
                seen.append(args)
                return _types.SimpleNamespace(stdout="Example GPU, 000.00\n")

            old = os.getcwd()
            os.chdir(d / "cwd")
            try:
                with mock.patch.dict(os.environ, {"PATH": os.pathsep.join(["", ".", str(real.parent)]),
                                                  "SystemRoot": str(d / "nowhere")}), \
                        mock.patch.object(E.subprocess, "run", fake_run):
                    out = E._gpu()
            finally:
                os.chdir(old)
        self.assertEqual(out, "Example GPU, 000.00")
        self.assertEqual(len(seen), 1)
        self.assertTrue(os.path.isabs(seen[0][0]))
        self.assertEqual(os.path.normcase(seen[0][0]), os.path.normcase(str(real)))

    def test_nothing_is_started_when_only_the_cwd_or_a_bare_name_could_find_it(self):
        E = self.E
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            touch(d / "cwd" / "nvidia-smi.exe")
            old = os.getcwd()
            os.chdir(d / "cwd")
            try:
                with mock.patch.dict(os.environ, {"PATH": os.pathsep.join(["", ".", "cwd"]), "SystemRoot": str(d / "nowhere")}), \
                        mock.patch.object(E.subprocess, "run", side_effect=AssertionError("must not start a program")):
                    out = E._gpu()
            finally:
                os.chdir(old)
        self.assertEqual(out, "")

    def test_system32_is_the_windows_fallback(self):
        E = self.E
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            smi = touch(d / "System32" / "nvidia-smi.exe")
            seen = []
            with mock.patch.dict(os.environ, {"PATH": "", "SystemRoot": str(d)}), mock.patch.object(E._platform, "is_windows", lambda: True), \
                    mock.patch.object(E.subprocess, "run", lambda args, **kw: seen.append(args) or _types.SimpleNamespace(stdout="x\n")):
                E._gpu()
        self.assertEqual([os.path.normcase(a[0]) for a in seen], [os.path.normcase(str(smi))])


# ================================================== test_cli.py (2) and test_pipeline_slow.py (3): real models, real clips
# Two kinds of checks (owner direction: any input, never tuned to single cases):
#   * INVARIANTS that hold for ANY clip (TestRealModelsAnyClip, and test_missing_key_still_makes_captions_with_notice):
#     run when WHYNOT_KALAM_SLOW=1, the Kalam pack and a clip (WHYNOT_KALAM_TEST_WAV, an H13 clip under whynot-test/) exist.
#   * REFERENCE checks of the owner's two clips (the upstream-named tests with their exact words, 17.68 / 15.12 s, >= 190
#     words, >= 20 blocks): only when WHYNOT_KALAM_REFERENCE=1 AND the clip's sha256 equals WHYNOT_KALAM_REF_SHA256_AR /
#     WHYNOT_KALAM_REF_SHA256_EN, so another clip can never run them (and fail for reasons unrelated to the engine).
REAL_PACK = _isolation.REAL_ENGINE_HOME / "tools" / "kalam" / "models"          # read only: the sandbox engine home is empty
WAV_AR = os.environ.get("WHYNOT_KALAM_TEST_WAV", "")                            # an H13 clip under whynot-test/ (Arabic speech)
WAV_EN = os.environ.get("WHYNOT_KALAM_TEST_WAV_EN", "")                         # an H13 clip under whynot-test/ (English speech)


def real_hf_dir() -> Path:
    return _isolation.REAL_ENGINE_HOME / "tools" / "kalam" / "hf"


def slow_env(engine_home: Path) -> dict:
    """the environment of a real-model run: a TEMP engine home (log, caches, settings stay out of the real one), the real
    model cache and pack used read-only (HF_HOME + --models), offline"""
    return dict(os.environ, PYTHONPATH=str(ENGINE), HF_HUB_OFFLINE="1", WHYNOT_HOME=str(engine_home), HF_HOME=str(real_hf_dir()))


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def slow_skip_reason(wav: str, mode: str = "ar") -> str:
    """why the any-clip real-model tests do not run here ('' = they run). They load the Kalam pack and align on the GPU or
    the CPU: run them through the machine queue (heavy.sh gpu|job) with WHYNOT_KALAM_SLOW=1. ANY clip will do."""
    if os.environ.get("WHYNOT_KALAM_SLOW") != "1":
        return "heavy: set WHYNOT_KALAM_SLOW=1 and run through heavy.sh (real models)"
    needed = {"ar": ("ct2-whisper-turbo-ar-dialectal", "model.bin"), "en": ("parakeet-tdt-0.6b-v2-onnx", "encoder-model.onnx")}[mode]
    if not (REAL_PACK / needed[0] / needed[1]).is_file():
        return "the Kalam model pack is not installed (%s needs %s/%s)" % (REAL_PACK, needed[0], needed[1])
    if not wav or not Path(wav).is_file():
        return "no test clip: set WHYNOT_KALAM_TEST_WAV (any H13 clip under whynot-test/; never client media)"
    try:
        importlib.import_module("lib.kalam.align")
    except ModuleNotFoundError:
        return "Task 16: lib/kalam/align.py is not ported yet"
    return ""


def reference_skip_reason(wav: str, which: str) -> str:
    """why a reference check of the OWNER'S clip does not run ('' = it runs): it needs the slow gate, the reference flag
    and a clip whose sha256 equals the digest named in WHYNOT_KALAM_REF_SHA256_<AR|EN>"""
    reason = slow_skip_reason(wav, "en" if which == "EN" else "ar")
    if reason:
        return reason
    if os.environ.get("WHYNOT_KALAM_REFERENCE") != "1":
        return ("reference check of the owner's %s clip: set WHYNOT_KALAM_REFERENCE=1 and WHYNOT_KALAM_REF_SHA256_%s "
                "(the sha256 of that clip); any other clip runs the any-clip invariants instead" % (which, which))
    want = os.environ.get("WHYNOT_KALAM_REF_SHA256_" + which, "").strip().lower()
    if not want:
        return "WHYNOT_KALAM_REF_SHA256_%s does not name the reference clip" % which
    if not wav or not Path(wav).is_file():
        return "no clip: set WHYNOT_KALAM_TEST_WAV%s to the reference clip" % ("" if which == "AR" else "_EN")
    if sha256_of(wav) != want:
        return "this clip is not the reference clip named by WHYNOT_KALAM_REF_SHA256_%s (sha256 differs)" % which
    return ""


def srt_blocks(text):
    out = []
    for blk in text.strip().split("\n\n"):
        ls = blk.split("\n")
        m = re.match(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)$", ls[1])
        h1, m1, s1, f1, h2, m2, s2, f2 = map(int, m.groups())
        out.append((int(ls[0]), ((h1 * 60 + m1) * 60 + s1) * 1000 + f1, ((h2 * 60 + m2) * 60 + s2) * 1000 + f2, ls[2:]))
    return out


WORD_OVERLAP_TOLERANCE_S = 0.1      # untuned until the first real run (aligners overlap by a few ms; measure it, then tighten)


def check_words(tc, words, duration, tol=WORD_OVERLAP_TOLERANCE_S):
    """any clip: words exist, each lies inside the clip, starts never go backwards and a word ends before the next starts
    (within `tol` seconds: aligners overlap by a few ms)"""
    tc.assertTrue(words, "no words")
    for w in words:
        tc.assertTrue(0 <= w["s"] <= w["e"] <= duration + tol, w)
    for a, b in zip(words, words[1:]):
        tc.assertTrue(a["s"] <= b["s"] + 1e-6 and a["e"] <= b["s"] + tol, (a, b))


def check_srt(tc, text, duration):
    """any clip: numbered from 1, gapless, 1-2 lines per block, a line of at most 32 characters unless it is one word,
    nothing after the clip's end (plus the tail the packer adds), no sentence punctuation"""
    blocks = srt_blocks(text)
    tc.assertTrue(blocks, "no blocks")
    tc.assertEqual([b[0] for b in blocks], list(range(1, len(blocks) + 1)))
    tc.assertTrue(all(a[2] == b[1] for a, b in zip(blocks, blocks[1:])), "a gap between blocks")
    for n, start, end, lines in blocks:
        tc.assertTrue(1 <= len(lines) <= 2, (n, lines))
        tc.assertTrue(all(len(l) <= 32 or " " not in l for l in lines), (n, lines))
        tc.assertTrue(0 <= start < end, (n, start, end))
    tc.assertLessEqual(blocks[-1][2] / 1000.0, duration + 1.0)
    tc.assertFalse(re.search(r"[.,!?\u060c\u061f]", " ".join(" ".join(b[3]) for b in blocks)))
    return blocks


def check_utf8_lf(tc, raw: bytes, name=""):
    tc.assertNotIn(b"\r", raw, name)
    tc.assertFalse(raw.startswith(b"\xef\xbb\xbf"), name)
    raw.decode("utf-8")


class TestSlowGates(unittest.TestCase):
    """the gates and the any-clip checks themselves, exercised here with fakes (they can fail)"""

    def test_a_real_model_run_uses_a_temp_engine_home_and_the_real_pack_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            env = slow_env(Path(d))
        self.assertEqual(env["WHYNOT_HOME"], d)
        self.assertNotEqual(Path(env["WHYNOT_HOME"]), _isolation.REAL_ENGINE_HOME)
        self.assertEqual(Path(env["HF_HOME"]), _isolation.REAL_ENGINE_HOME / "tools" / "kalam" / "hf")
        self.assertEqual(env["HF_HUB_OFFLINE"], "1")
        self.assertEqual(Path(env["PYTHONPATH"]), ENGINE)

    def test_the_any_clip_gate_names_any_clip_and_the_reference_gate_names_the_clips_by_sha256(self):
        with tempfile.TemporaryDirectory() as d:
            clip = Path(d) / "any-clip.wav"
            clip.write_bytes(_wav_bytes(_tone(0.2, 16000), 16000, "pcm16"))
            digest = sha256_of(clip)
            with mock.patch.dict(os.environ):
                for k in ("WHYNOT_KALAM_SLOW", "WHYNOT_KALAM_REFERENCE", "WHYNOT_KALAM_REF_SHA256_AR"):
                    os.environ.pop(k, None)
                self.assertIn("WHYNOT_KALAM_SLOW=1", slow_skip_reason(str(clip)))
                os.environ["WHYNOT_KALAM_SLOW"] = "1"
                with mock.patch.object(sys.modules[__name__], "REAL_PACK", Path(d) / "no-pack"):
                    self.assertIn("pack is not installed", slow_skip_reason(str(clip)))
                    self.assertIn("pack is not installed", reference_skip_reason(str(clip), "AR"))
                # the reference gate with everything else open
                pack = Path(d) / "pack"
                (pack / "ct2-whisper-turbo-ar-dialectal").mkdir(parents=True)
                (pack / "ct2-whisper-turbo-ar-dialectal" / "model.bin").write_bytes(b"x")
                (pack / "parakeet-tdt-0.6b-v2-onnx").mkdir()
                (pack / "parakeet-tdt-0.6b-v2-onnx" / "encoder-model.onnx").write_bytes(b"x")
                fake_align = _types.ModuleType("lib.kalam.align")
                with mock.patch.object(sys.modules[__name__], "REAL_PACK", pack), \
                        mock.patch.dict(sys.modules, {"lib.kalam.align": fake_align}):
                    self.assertEqual(slow_skip_reason(str(clip)), "")                          # ANY clip passes the slow gate
                    self.assertIn("WHYNOT_KALAM_REFERENCE=1", reference_skip_reason(str(clip), "AR"))
                    os.environ["WHYNOT_KALAM_REFERENCE"] = "1"
                    self.assertIn("does not name the reference clip", reference_skip_reason(str(clip), "AR"))
                    os.environ["WHYNOT_KALAM_REF_SHA256_AR"] = "0" * 64
                    self.assertIn("is not the reference clip", reference_skip_reason(str(clip), "AR"))
                    os.environ["WHYNOT_KALAM_REF_SHA256_AR"] = digest.upper()
                    self.assertEqual(reference_skip_reason(str(clip), "AR"), "")
                    self.assertIn("does not name the reference clip", reference_skip_reason(str(clip), "EN"))

    def test_the_any_clip_checks_accept_a_good_run_and_reject_a_bad_one(self):
        words = [{"w": "a", "s": 0.1, "e": 0.4}, {"w": "b", "s": 0.45, "e": 0.9}]
        check_words(self, words, 1.0)
        bad = {
            "outside the clip": [{"w": "a", "s": 0.1, "e": 5.0}],
            "backwards": [{"w": "a", "s": 0.5, "e": 0.6}, {"w": "b", "s": 0.1, "e": 0.2}],
            "overlap": [{"w": "a", "s": 0.1, "e": 0.9}, {"w": "b", "s": 0.3, "e": 0.9}],
            "inverted": [{"w": "a", "s": 0.4, "e": 0.1}],
            "empty": [],
        }
        for name, ws in bad.items():
            with self.assertRaises(AssertionError, msg=name):
                check_words(self, ws, 1.0)
        good = "1\n00:00:00,000 --> 00:00:01,000\nline one\nline two\n\n2\n00:00:01,000 --> 00:00:02,000\nnext\n"
        self.assertEqual(len(check_srt(self, good, 2.0)), 2)
        for name, text in {
            "gap": "1\n00:00:00,000 --> 00:00:01,000\na\n\n2\n00:00:01,500 --> 00:00:02,000\nb\n",
            "three lines": "1\n00:00:00,000 --> 00:00:01,000\na\nb\nc\n",
            "long line": "1\n00:00:00,000 --> 00:00:01,000\n" + "word " * 12 + "end\n",
            "numbering": "2\n00:00:00,000 --> 00:00:01,000\na\n",
            "after the end": "1\n00:00:00,000 --> 00:00:09,000\na\n",
            "punctuation": "1\n00:00:00,000 --> 00:00:01,000\nhello.\n",
        }.items():
            with self.assertRaises(AssertionError, msg=name):
                check_srt(self, text, 2.0)
        check_utf8_lf(self, "\u0645\u0631\u062d\u0628\u0627\n".encode("utf-8"))
        for raw in (b"a\r\nb", b"\xef\xbb\xbfa", b"\xff\xfe"):
            with self.assertRaises((AssertionError, UnicodeDecodeError)):
                check_utf8_lf(self, raw)


class TestCli(unittest.TestCase):
    def setUp(self):
        reason = slow_skip_reason(WAV_AR)
        if reason:
            self.skipTest(reason)

    def run_engine(self, tmp_path, settings, wav=None, mode="ar"):
        sp = Path(tmp_path) / "settings.json"
        sp.write_text(json.dumps(settings), encoding="utf-8")
        home = Path(tmp_path) / "engine-home"                                    # a temp engine home, never the real one
        p = subprocess.run(engine_argv(wav or WAV_AR, mode, Path(tmp_path) / "out", sp),
                           capture_output=True, env=slow_env(home), cwd=str(ENGINE), timeout=3600)
        events = [json.loads(l) for l in p.stdout.decode("utf-8").splitlines() if l.startswith("{")]
        return p, events

    def test_uncorrected_run_writes_valid_gapless_srt(self):
        """upstream assertions of the owner's Arabic clip (>= 20 blocks): reference clip only (see the header above)"""
        reason = reference_skip_reason(WAV_AR, "AR")
        if reason:
            self.skipTest(reason)
        with tempfile.TemporaryDirectory() as tmp_path:
            p, ev = self.run_engine(tmp_path, {"correct": False})
            self.assertEqual(p.returncode, 0, p.stderr[-2000:])
            stages = [e["stage"] for e in ev]
            self.assertTrue(stages[0] == "loading" and stages[-1] == "done" and "aligning" in stages)
            blocks = srt_blocks((Path(tmp_path) / "out" / "captions.srt").read_text(encoding="utf-8"))
            self.assertTrue([b[0] for b in blocks] == list(range(1, len(blocks) + 1)) and len(blocks) >= 20)
            self.assertTrue(all(a[2] == b[1] for a, b in zip(blocks, blocks[1:])))
            self.assertTrue(all(1 <= len(b[3]) <= 2 for b in blocks))
            text = " ".join(" ".join(b[3]) for b in blocks)
            self.assertFalse(re.search(r"[.,!?\u060c\u061f]", text))
            caps = json.loads((Path(tmp_path) / "out" / "captions.json").read_text(encoding="utf-8"))
            self.assertTrue(len(caps) == len(blocks) and ev[-1]["corrected"] is False and "notice" not in ev[-1])

    def test_missing_key_still_makes_captions_with_notice(self):
        with tempfile.TemporaryDirectory() as tmp_path:
            p, ev = self.run_engine(tmp_path, {"correct": True, "backend": "api", "api_key": ""})
            self.assertTrue(p.returncode == 0 and ev[-1]["stage"] == "done")
            self.assertTrue(ev[-1]["corrected"] is False and ev[-1]["notice"] == "no_api_key")
            self.assertTrue((Path(tmp_path) / "out" / "captions.srt").exists())


class TestPipelineSlow(unittest.TestCase):
    """the upstream slow tests with their exact numbers and words: they hold only for the owner's two reference clips, so
    they run only behind the reference gate (WHYNOT_KALAM_REFERENCE=1 + the clip's sha256), never for another clip"""

    def setUp(self):
        self.A = mod("audio")

    def _need(self, wav, which):
        reason = reference_skip_reason(wav, which)
        if reason:
            self.skipTest(reason)
        self.align = importlib.import_module("lib.kalam.align").align
        self.transcribe = mod("transcribe").transcribe

    def test_load_16k_resamples_48k(self):
        self._need(WAV_EN, "EN")
        a = self.A.load_16k(WAV_EN)
        self.assertTrue(abs(len(a) / 16000 - 17.68) < 0.05 or abs(len(a) / 16000 - 15.12) < 0.05)
        self.assertEqual(self.A.envelope_db(a).shape[0], int(len(a) / 160))

    def test_arabic_transcribe_and_align(self):
        self._need(WAV_AR, "AR")
        a = self.A.load_16k(WAV_AR)
        ws = self.align(a, self.transcribe(a, "ar", str(REAL_PACK)))
        self.assertTrue(len(ws) >= 190)
        self.assertTrue(all(w["s"] <= w["e"] for w in ws))
        self.assertTrue(all(ws[i]["s"] <= ws[i + 1]["s"] + 1e-6 for i in range(len(ws) - 1)))
        shabab = [w for w in ws if w["w"] == "\u0634\u0628\u0627\u0628"]
        self.assertTrue(shabab and abs(shabab[0]["s"] - 5.87) < 0.2)
        self.assertTrue(all("score" in w for w in ws))

    def test_english_parakeet(self):
        self._need(WAV_EN, "EN")
        a = self.A.load_16k(WAV_EN)
        ws = self.align(a, self.transcribe(a, "en", str(REAL_PACK)))     # Parakeet starts ~0.25 s early; alignment fixes it
        text = " ".join(w["w"] for w in ws).lower()
        self.assertTrue("silence" in text and "final sentence" in text)
        hello = [w for w in ws if w["w"].lower().strip(",.") == "hello"]
        self.assertTrue(hello and abs(hello[0]["s"] - 1.21) < 0.1)



# ============================================================ N1: a REAL huggingface_hub cache, installed with the pinned revision
class _HubHandler(http.server.BaseHTTPRequestHandler):
    """a minimal local Hugging Face endpoint (HF_ENDPOINT): the revision, tree and resolve calls the real client makes"""
    repos = {}                                                    # repo -> (commit sha, {file name: bytes})

    def log_message(self, *a):
        pass

    def _send(self, body, code=200, headers=None, head=False):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _handle(self, head):
        path = self.path.split("?")[0]
        for repo, (sha, files) in self.repos.items():
            if path == "/api/models/%s/revision/%s" % (repo, sha):
                body = json.dumps({"id": repo, "sha": sha, "siblings": [{"rfilename": f} for f in files]}).encode()
                return self._send(body, headers={"Content-Type": "application/json"}, head=head)
            if path == "/api/models/%s/tree/%s" % (repo, sha):
                body = json.dumps([{"type": "file", "path": f, "size": len(d), "oid": hashlib.sha1(d).hexdigest()}
                                   for f, d in files.items()]).encode()
                return self._send(body, headers={"Content-Type": "application/json"}, head=head)
            prefix = "/%s/resolve/%s/" % (repo, sha)
            if path.startswith(prefix) and path[len(prefix):] in files:
                data = files[path[len(prefix):]]
                return self._send(data, headers={"ETag": '"%s"' % hashlib.sha1(data).hexdigest(), "X-Repo-Commit": sha,
                                                 "Content-Type": "application/octet-stream", "Accept-Ranges": "bytes"}, head=head)
        self._send(b"{}", 404, head=head)

    def do_GET(self):
        self._handle(False)

    def do_HEAD(self):
        self._handle(True)


@contextlib.contextmanager
def fake_hub(repos):
    import threading
    handler = type("Handler", (_HubHandler,), {"repos": repos})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d" % server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


# what the installer does on a Mac (pins and downloads the three MLX / aligner repos through the REAL client) ...
INSTALL_SCRIPT = """
import sys, types
from lib.kalam import setup_models as S
S.sys = types.SimpleNamespace(platform="darwin")
S.convert_hf_whisper = lambda repo, dest: None
S.main(sys.argv[1])
"""
# ... and what the runtime does afterwards, offline, with the same repo names
LOOKUP_SCRIPT = """
import json, sys, types
import numpy as np
from lib.kalam import engine as E, setup_models as S, transcribe as T
out = {}
E._align_module = lambda: types.SimpleNamespace(REPO=S.ALIGNER_REPO)
out["aligner_present"] = E.aligner_present()
out["whisper_path"] = T._snapshot(T.OTHER_REPO)
out["parakeet_path"] = T._snapshot(T.ENGLISH_REPO)
seen = {}
fake = types.ModuleType("mlx_whisper")
fake.transcribe = lambda a, **kw: seen.update(kw) or {"segments": []}
sys.modules["mlx_whisper"] = fake
T._platform.backend = lambda: "mlx"
T.transcribe(np.zeros(16000, dtype=np.float32), "other", "/pack")
out["mlx_whisper_arg"] = seen.get("path_or_hf_repo")
pk = types.ModuleType("parakeet_mlx")
pk.from_pretrained = lambda arg, **kw: out.update(parakeet_arg=arg) or "model"
sys.modules["parakeet_mlx"] = pk
out["parakeet_model"] = T._load_parakeet()
from huggingface_hub import snapshot_download
try:
    snapshot_download(S.ALIGNER_REPO, local_files_only=True)
    out["unpinned"] = "found"
except Exception as e:
    out["unpinned"] = type(e).__name__
print(json.dumps(out))
"""


ABSENT_SCRIPT = """
import json, types
from lib.kalam import engine as E, setup_models as S
E._align_module = lambda: types.SimpleNamespace(REPO=S.ALIGNER_REPO)
print(json.dumps({"aligner_present": E.aligner_present()}))
"""


class TestPinnedCacheLayout(unittest.TestCase):
    """Task 11 re-review N1: a download pinned to a commit leaves no refs/main in the Hugging Face cache, so a lookup by repo
    name alone finds nothing. Every runtime lookup passes the same pinned revision (lib/kalam/revisions.py, shared with
    setup_models). Tested against the REAL huggingface_hub client and a real cache layout in a temp HF_HOME."""

    def _env(self, hf, endpoint, offline=False):
        env = dict(os.environ, PYTHONPATH=str(ENGINE), HF_HOME=hf, HF_ENDPOINT=endpoint, HF_HUB_DISABLE_XET="1",
                   HF_HUB_DISABLE_PROGRESS_BARS="1", HF_HUB_DISABLE_TELEMETRY="1", NO_PROXY="*", HTTP_PROXY="", HTTPS_PROXY="")
        env.pop("HF_HUB_OFFLINE", None)
        if offline:
            env["HF_HUB_OFFLINE"] = "1"
            env["HF_ENDPOINT"] = "http://127.0.0.1:9"                      # nothing listens: a network try would fail loudly
        return env

    def _run(self, script, env, *args):
        p = subprocess.run([sys.executable, "-s", "-B", "-c", script, *args], env=env, cwd=str(ENGINE),
                           capture_output=True, text=True, encoding="utf-8", timeout=300)
        self.assertEqual(p.returncode, 0, p.stderr[-1500:])
        return p.stdout

    def test_a_pinned_install_is_found_offline_by_every_runtime_lookup(self):
        S = mod("setup_models")
        repos = {r: (S.REVISIONS[r], {"config.json": b'{"n": 1}', "weights.bin": b"w" * 64}) for r in S.OTHERS}
        with fake_hub(repos) as endpoint, tempfile.TemporaryDirectory() as hf, tempfile.TemporaryDirectory() as models:
            installed = self._run(INSTALL_SCRIPT, self._env(hf, endpoint), models)
            self.assertIn("model:", installed)                    # the notices were printed
            hub = Path(hf) / "hub"
            for repo, (sha, _files) in repos.items():
                cache = hub / ("models--" + repo.replace("/", "--"))
                self.assertTrue((cache / "snapshots" / sha / "config.json").is_file(), repo)   # a real hub cache layout
                self.assertFalse((cache / "refs" / "main").exists(), repo)                    # and no refs/main, ever
            found = json.loads(self._run(LOOKUP_SCRIPT, self._env(hf, endpoint, offline=True)).strip().splitlines()[-1])
            snap = lambda repo: str(hub / ("models--" + repo.replace("/", "--")) / "snapshots" / repos[repo][0])  # noqa: E731
            self.assertNotEqual(found["unpinned"], "found")                  # by name alone it is NOT found
            self.assertTrue(found["aligner_present"], "aligner_present() cannot see the pinned install")
            self.assertEqual(os.path.normcase(found["whisper_path"]), os.path.normcase(snap("mlx-community/whisper-large-v3-turbo")))
            self.assertEqual(os.path.normcase(found["parakeet_path"]), os.path.normcase(snap("mlx-community/parakeet-tdt-0.6b-v2")))
            self.assertEqual(os.path.normcase(found["mlx_whisper_arg"]), os.path.normcase(found["whisper_path"]))
            self.assertEqual(os.path.normcase(found["parakeet_arg"]), os.path.normcase(found["parakeet_path"]))

    def test_an_aligner_that_was_never_installed_is_not_present(self):
        S = mod("setup_models")
        with fake_hub({}) as endpoint, tempfile.TemporaryDirectory() as hf:
            found = json.loads(self._run(ABSENT_SCRIPT, self._env(hf, endpoint, offline=True)).strip().splitlines()[-1])
        self.assertFalse(found["aligner_present"])

    def test_the_revision_table_is_one_module_shared_by_setup_and_the_runtime(self):
        R, S, T, E = mod("revisions"), mod("setup_models"), mod("transcribe"), mod("engine")
        self.assertIs(S.REVISIONS, R.REVISIONS)
        self.assertEqual((S.ALIGNER_REPO, S.ALIGNER_REV), (R.ALIGNER_REPO, R.ALIGNER_REV))
        self.assertEqual(R.pinned(R.ALIGNER_REPO), R.ALIGNER_REV)
        with self.assertRaises(ValueError):
            R.pinned("some/unpinned-repo")
        self.assertIn(T.OTHER_REPO, R.REVISIONS)
        self.assertIn(T.ENGLISH_REPO, R.REVISIONS)

    def test_refs_main_is_never_written_by_our_code(self):
        for name in ("revisions", "setup_models", "transcribe", "engine"):
            src = Path(mod(name).__file__).read_text(encoding="utf-8")
            self.assertNotIn("refs/main", src, name)
            self.assertNotIn('"refs"', src, name)

    def test_the_snapshot_helper_passes_the_pinned_revision_and_the_offline_flag(self):
        R = mod("revisions")
        calls = []
        hub = types_module("huggingface_hub")
        hub.snapshot_download = lambda repo, **kw: calls.append((repo, kw)) or "/x"
        with mock.patch.dict(sys.modules, {"huggingface_hub": hub}):
            R.snapshot(R.ALIGNER_REPO, local_only=True)
            R.snapshot("mlx-community/whisper-large-v3-turbo")
        self.assertEqual(calls, [(R.ALIGNER_REPO, {"revision": R.ALIGNER_REV, "local_files_only": True}),
                                 ("mlx-community/whisper-large-v3-turbo",
                                  {"revision": R.REVISIONS["mlx-community/whisper-large-v3-turbo"], "local_files_only": False})])


class TestGpuLookupRoot(unittest.TestCase):
    """Task 11 re-review N2: the System32 fallback takes SystemRoot only when it is an absolute path"""

    def setUp(self):
        self.E = mod("engine")

    def test_a_relative_systemroot_is_never_used(self):
        E = self.E
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            touch(d / "System32" / "nvidia-smi.exe")
            old = os.getcwd()
            os.chdir(d)
            try:
                for root in (".", "", "System32", "..\\x", "./"):
                    with mock.patch.dict(os.environ, {"PATH": "", "SystemRoot": root}), \
                            mock.patch.object(E._platform, "is_windows", lambda: True), \
                            mock.patch.object(E.subprocess, "run", side_effect=AssertionError("must not start a program")):
                        self.assertIsNone(E._nvidia_smi(), repr(root))
                        self.assertEqual(E._gpu(), "", repr(root))
            finally:
                os.chdir(old)

    def test_a_rooted_path_without_a_drive_is_not_absolute_either(self):
        E = self.E
        with mock.patch.dict(os.environ, {"PATH": "", "SystemRoot": "\\Windows"}), mock.patch.object(E._platform, "is_windows", lambda: True):
            self.assertIsNone(E._nvidia_smi())


class TestRunSettingsContract(unittest.TestCase):
    """Task 11 re-review N3: the per-run settings file goes in the store's run folder (created user-only by the store) or the
    temp folder; the contract is in the engine's usage text and header; a refusal leaves the file for its caller to delete"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.S = mod("store").Store(Path(self._tmp.name) / "engine-home")

    def test_the_store_creates_its_run_folder_user_only(self):
        d = self.S.ensure_run_dir()
        self.assertEqual(d, self.S.home / "run")
        self.assertTrue(d.is_dir())
        if os.name == "nt":
            from serve import security
            self.assertTrue(security.user_only(d, directory=True))
            self.assertTrue(security.user_only(self.S.home, directory=True))
        else:
            self.assertEqual(d.stat().st_mode & 0o777, 0o700)

    def test_new_run_settings_writes_a_private_utf8_lf_file_that_take_settings_accepts_and_deletes(self):
        settings = {"api_key": "sk-test-key-0000", "rules": "اختبار", "max_line": 28}
        f = self.S.new_run_settings(settings)
        g = self.S.new_run_settings(settings)
        self.assertEqual(f.parent, self.S.run_dir)
        self.assertRegex(f.name, r"^kalam-run-[0-9a-f]{16,}\.json$")
        self.assertNotEqual(f, g)
        raw = f.read_bytes()
        self.assertTrue(raw.endswith(b"\n") and b"\r" not in raw)
        self.assertEqual(json.loads(raw.decode("utf-8")), settings)
        if os.name != "nt":
            self.assertEqual(f.stat().st_mode & 0o777, 0o600)
        self.assertEqual(mod("store").take_settings(f, store=self.S), settings)
        self.assertFalse(f.exists())
        self.assertTrue(g.exists())                                    # only the file it was given

    def test_new_run_settings_never_touches_the_persistent_settings(self):
        self.S.save_settings({"max_line": 30})
        before = self.S.settings_file.read_bytes()
        self.S.new_run_settings({"api_key": "k"})
        self.assertEqual(self.S.settings_file.read_bytes(), before)

    def test_the_contract_is_in_the_engine_header_and_usage(self):
        E = self.E = mod("engine")
        contract = E.RUN_SETTINGS_CONTRACT
        for needle in ("tools/kalam/run", "temp", "delete", "new_run_settings", "settings.json"):
            self.assertIn(needle, contract)
            self.assertIn(needle, E.__doc__, needle)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            E.main(["run", "--help"])
        self.assertEqual(cm.exception.code, 0)
        text = " ".join(out.getvalue().split())
        self.assertIn("tools/kalam/run", text)
        self.assertIn("delete", text)

    def test_a_refused_settings_file_is_reported_and_left_for_the_caller_to_delete(self):
        E = mod("engine")
        elsewhere = Path.home() / "caller-dir" / "settings.json"
        elsewhere.parent.mkdir(parents=True)
        elsewhere.write_text(json.dumps({"api_key": "sk-test-key-0000"}), encoding="utf-8")
        code, stdout, _ = capture_main(["run", "--wav", "x.wav", "--out", str(Path(self._tmp.name) / "o"), "--settings", str(elsewhere)])
        self.assertEqual(code, 1)
        self.assertTrue(elsewhere.is_file())                           # the engine did not delete it ...
        last = json_lines(stdout)[-1]
        self.assertEqual(last["stage"], "error")                       # ... and says why, so the caller can
        self.assertIn("settings", last["error"])
        self.assertNotIn(b"sk-test-key-0000", stdout)


# ============================================================ N5: the comparison of two runs; N4: the mode of a real run
def compare_runs(tc, out1, out2, cuda: bool):
    """a re-run of the same clip: the words are the same and the output files are byte-identical on the CPU; on CUDA
    (kernels may differ in the last bit) the word text and the block texts are identical and every time is within 1 ms"""
    names = ("captions.srt", "captions.json", "words.json")
    if not cuda:
        for name in names:
            tc.assertEqual((out1 / name).read_bytes(), (out2 / name).read_bytes(), name)
        return
    w1, w2 = (json.loads((o / "words.json").read_text(encoding="utf-8")) for o in (out1, out2))
    tc.assertEqual([w["w"] for w in w1], [w["w"] for w in w2])
    for a, b in zip(w1, w2):
        tc.assertLessEqual(abs(a["s"] - b["s"]), 1e-3, (a, b))
        tc.assertLessEqual(abs(a["e"] - b["e"]), 1e-3, (a, b))
    b1, b2 = (srt_blocks((o / "captions.srt").read_text(encoding="utf-8")) for o in (out1, out2))
    tc.assertEqual(len(b1), len(b2))
    for x, y in zip(b1, b2):
        tc.assertEqual((x[0], x[3]), (y[0], y[3]))
        tc.assertLessEqual(abs(x[1] - y[1]), 1)
        tc.assertLessEqual(abs(x[2] - y[2]), 1)


def engine_argv(wav, mode, out, settings_file, models=None):
    return [sys.executable, "-s", "-B", "-m", "lib.kalam.engine", "run", "--wav", str(wav), "--mode", mode,
            "--out", str(out), "--settings", str(settings_file), "--models", str(models or REAL_PACK)]


class TestRunComparison(unittest.TestCase):
    """Task 11 re-review N4 / N5: the any-clip helpers (mode of a real run, tolerance, determinism check) tested with fakes"""

    def _run(self, d, name, words, srt):
        out = Path(d) / name
        out.mkdir()
        (out / "words.json").write_text(json.dumps(words), encoding="utf-8")
        (out / "captions.json").write_text("[]", encoding="utf-8")
        (out / "captions.srt").write_text(srt, encoding="utf-8")
        return out

    def test_the_overlap_tolerance_is_a_named_untuned_constant(self):
        self.assertEqual(WORD_OVERLAP_TOLERANCE_S, 0.1)
        src = Path(__file__).read_text(encoding="utf-8")
        self.assertRegex(src, r"(?m)^WORD_OVERLAP_TOLERANCE_S = 0\.1 +# untuned until the first real run")
        self.assertIs(check_words.__defaults__[0], WORD_OVERLAP_TOLERANCE_S)           # the checks use the constant

    def test_cpu_runs_must_be_byte_identical_and_cuda_runs_within_a_millisecond(self):
        srt = "1\n00:00:00,400 --> 00:00:01,000\nhello\n"
        srt2 = "1\n00:00:00,401 --> 00:00:01,000\nhello\n"
        words = [{"w": "hello", "s": 0.4, "e": 1.0}]
        close = [{"w": "hello", "s": 0.4004, "e": 1.0}]
        with tempfile.TemporaryDirectory() as d:
            a, same = self._run(d, "a", words, srt), self._run(d, "same", words, srt)
            near = self._run(d, "near", close, srt2)
            compare_runs(self, a, same, cuda=False)
            compare_runs(self, a, same, cuda=True)
            compare_runs(self, a, near, cuda=True)
            with self.assertRaises(AssertionError):
                compare_runs(self, a, near, cuda=False)                # not byte-identical on the CPU

    def test_a_different_word_or_a_time_beyond_a_millisecond_fails_on_cuda_too(self):
        srt = "1\n00:00:00,400 --> 00:00:01,000\nhello\n"
        with tempfile.TemporaryDirectory() as d:
            a = self._run(d, "a", [{"w": "hello", "s": 0.4, "e": 1.0}], srt)
            other_word = self._run(d, "w", [{"w": "hullo", "s": 0.4, "e": 1.0}], srt)
            late = self._run(d, "t", [{"w": "hello", "s": 0.4, "e": 1.003}], srt)
            late_block = self._run(d, "b", [{"w": "hello", "s": 0.4, "e": 1.0}], "1\n00:00:00,400 --> 00:00:01,003\nhello\n")
            other_text = self._run(d, "x", [{"w": "hello", "s": 0.4, "e": 1.0}], "1\n00:00:00,400 --> 00:00:01,000\nhullo\n")
            for other in (other_word, late, late_block, other_text):
                with self.assertRaises(AssertionError, msg=other.name):
                    compare_runs(self, a, other, cuda=True)

    def test_engine_argv_carries_the_mode_and_never_a_key(self):
        argv = engine_argv("clip.wav", "en", "/o", "/s.json", "/models")
        self.assertEqual(argv[argv.index("--mode") + 1], "en")
        self.assertEqual(engine_argv("c.wav", "ar", "/o", "/s.json")[argv.index("--mode") + 1], "ar")
        self.assertNotIn("api_key", " ".join(argv))

    def test_the_slow_gate_checks_the_pack_of_the_mode(self):
        with tempfile.TemporaryDirectory() as d:
            clip = Path(d) / "clip.wav"
            clip.write_bytes(_wav_bytes(_tone(0.2, 16000), 16000, "pcm16"))
            pack = Path(d) / "pack"
            (pack / "ct2-whisper-turbo-ar-dialectal").mkdir(parents=True)
            (pack / "ct2-whisper-turbo-ar-dialectal" / "model.bin").write_bytes(b"x")
            fake_align = _types.ModuleType("lib.kalam.align")
            with mock.patch.dict(os.environ, {"WHYNOT_KALAM_SLOW": "1"}), \
                    mock.patch.object(sys.modules[__name__], "REAL_PACK", pack), \
                    mock.patch.dict(sys.modules, {"lib.kalam.align": fake_align}):
                self.assertEqual(slow_skip_reason(str(clip), "ar"), "")
                self.assertIn("pack is not installed", slow_skip_reason(str(clip), "en"))      # no Parakeet in this pack
                (pack / "parakeet-tdt-0.6b-v2-onnx").mkdir()
                (pack / "parakeet-tdt-0.6b-v2-onnx" / "encoder-model.onnx").write_bytes(b"x")
                self.assertEqual(slow_skip_reason(str(clip), "en"), "")


class TestRealModelsAnyClip(unittest.TestCase):
    """invariants of the real pipeline that hold for ANY clip (the clip is only 'a clip from whynot-test/'): Arabic mode on
    WHYNOT_KALAM_TEST_WAV, English (Parakeet) mode on WHYNOT_KALAM_TEST_WAV_EN, both without any reference gate"""

    def setUp(self):
        self.A = mod("audio")

    def _need(self, wav, mode):
        reason = slow_skip_reason(wav, mode)
        if reason:
            self.skipTest(reason)
        a2d, rate = self.A.read_wav(wav)
        return a2d.shape[0] / rate                                               # the file's OWN length

    def run_once(self, tmp_path, name, wav, mode):
        runner = TestCli("test_missing_key_still_makes_captions_with_notice")
        sub = Path(tmp_path) / name
        sub.mkdir()
        p, ev = runner.run_engine(sub, {"correct": False}, wav, mode)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        return sub / "out", ev

    def check_run(self, out, ev, duration, mode):
        stages = [e["stage"] for e in ev]
        self.assertEqual(stages[0], "loading")
        self.assertEqual(stages[-1], "done")
        self.assertTrue(all(s_ in ("loading", "transcribing", "aligning", "correcting", "captions", "done") for s_ in stages))
        self.assertEqual(ev[1]["mode"], mode)
        self.assertLessEqual(abs(ev[1]["seconds"] - round(duration, 2)), 0.02)
        for name in ("captions.srt", "captions.json", "words.json", "corrected.json"):
            check_utf8_lf(self, (out / name).read_bytes(), name)
        check_words(self, json.loads((out / "words.json").read_text(encoding="utf-8")), duration)
        blocks = check_srt(self, (out / "captions.srt").read_text(encoding="utf-8"), duration)
        caps = json.loads((out / "captions.json").read_text(encoding="utf-8"))
        self.assertEqual([c["n"] for c in caps], [b[0] for b in blocks])

    def _two_runs(self, wav, mode):
        duration = self._need(wav, mode)
        with tempfile.TemporaryDirectory() as tmp_path:
            out1, ev1 = self.run_once(tmp_path, "one", wav, mode)
            self.check_run(out1, ev1, duration, mode)
            out2, ev2 = self.run_once(tmp_path, "two", wav, mode)
            cuda = "cuda" in (ev1[2].get("device"), ev2[2].get("device"))
            compare_runs(self, out1, out2, cuda)

    def test_durations_equal_the_files_own_length(self):
        duration = self._need(WAV_AR, "ar")
        a = self.A.load_16k(WAV_AR)
        self.assertLessEqual(abs(len(a) / 16000 - duration), 2 / 16000)
        self.assertEqual(self.A.envelope_db(a).shape[0], int(len(a) / 160))
        if WAV_EN and Path(WAV_EN).is_file():
            a2d, rate = self.A.read_wav(WAV_EN)
            self.assertLessEqual(abs(len(self.A.load_16k(WAV_EN)) / 16000 - a2d.shape[0] / rate), 2 / 16000)

    def test_an_arabic_run_obeys_the_pipeline_invariants_and_a_rerun_agrees(self):
        self._two_runs(WAV_AR, "ar")

    def test_an_english_parakeet_run_obeys_the_same_invariants_and_a_rerun_agrees(self):
        self._two_runs(WAV_EN, "en")

    def test_transcribe_and_align_give_ordered_scored_words(self):
        self._need(WAV_AR, "ar")
        a = self.A.load_16k(WAV_AR)
        align = importlib.import_module("lib.kalam.align").align
        ws = align(a, mod("transcribe").transcribe(a, "ar", str(REAL_PACK)))
        check_words(self, ws, len(a) / 16000)
        self.assertTrue(all("score" in w for w in ws))


if __name__ == "__main__":
    unittest.main()
