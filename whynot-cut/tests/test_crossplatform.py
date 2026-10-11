"""WhyNot Cut 2.0: macOS + Windows behaviour (paths, text shaping, PowerShell guard, preferences, onboarding, docs).
Run:  <engine venv python> -m unittest discover -s <plugin>/tests -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import plat  # noqa: E402

GUARD = SK / "hooks" / "guard.py"


def guard(tool, cmd, cwd):
    from test_plugin import isolated_env
    r = subprocess.run([sys.executable, str(GUARD)], capture_output=True, text=True, env=isolated_env(),
                       input=json.dumps({"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(cwd)}))
    return r.returncode


def arabic_font() -> Path | None:
    cands = ["arial.ttf", "tahoma.ttf", "segoeui.ttf", "GeezaPro.ttc", "SFArabic.ttf", "Baghdad.ttc",
             "NotoSansArabic-Regular.ttf", "DejaVuSans.ttf"]
    for d in plat.font_dirs():
        for c in cands:
            hits = list(d.rglob(c)) if d.is_dir() else []
            if hits:
                return hits[0]
    return None


class TestPaths(unittest.TestCase):
    def test_pathurl_roundtrip(self):
        from lib.premiere_xml import pathurl, path_from_url
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "client folder" / "C0238 é.MP4"
            u = pathurl(f)
            self.assertTrue(u.startswith("file://localhost/"), u)
            self.assertNotIn("\\", u)
            self.assertNotIn("%5C", u.upper())
            self.assertNotIn("%3A", u.upper())                 # drive colon stays literal (Premiere on Windows)
            self.assertIn("%20", u)
            self.assertEqual(path_from_url(u).resolve(), f.resolve())
        self.assertEqual(path_from_url("file://localhost/Volumes/DOMA%202.5%20SS/x.mov").as_posix(), "/Volumes/DOMA 2.5 SS/x.mov")

    def test_native_path(self):
        if plat.IS_WIN:
            self.assertEqual(plat.native_path("/d/0 Work/x"), "D:/0 Work/x")
            self.assertEqual(plat.native_path("/c"), "C:/")
        self.assertEqual(plat.native_path("relative/x"), "relative/x")

    def test_venv_layout_and_home(self):
        py = plat.venv_python(Path("H"))
        self.assertEqual(py.parts[-2:], ("Scripts", "python.exe") if plat.IS_WIN else ("bin", "python"))
        with tempfile.TemporaryDirectory() as h:
            old = dict(os.environ)
            try:
                for k in plat.HOME_ENV:
                    os.environ.pop(k, None)
                os.environ["WHYNOT_HOME"] = h
                self.assertEqual(plat.engine_home(), Path(h))
            finally:
                os.environ.clear()
                os.environ.update(old)

    def test_cep_and_debug_commands(self):
        d = plat.cep_extensions_dir()
        self.assertEqual(d.parts[-3:], ("Adobe", "CEP", "extensions"))
        cmds = plat.debug_mode_commands()
        self.assertEqual(len(cmds), len(plat.CSXS_VERSIONS))
        self.assertIn("reg add" if plat.IS_WIN else "defaults write", cmds[0])


class TestHarfBuzz(unittest.TestCase):
    def setUp(self):
        from lib import hb_text
        if not hb_text.AVAILABLE:
            self.skipTest("uharfbuzz/freetype not installed")
        self.font = arabic_font()
        if not self.font:
            self.skipTest("no Arabic-capable system font found")
        self.hb = hb_text

    def test_runs_rtl_base_and_latin_first(self):
        rtl, rs = self.hb.runs("evidence إنها ممكن تساعد")
        self.assertTrue(rtl)
        self.assertEqual(rs[0], ("L", "evidence"))
        self.assertEqual(rs[1][0], "R")
        rtl, rs = self.hb.runs("Hello world")
        self.assertFalse(rtl)
        self.assertEqual(len(rs), 1)
        _, rs = self.hb.runs("الجرعة 50 ملغ")
        self.assertIn(("L", "50"), rs)                     # digits keep LTR order inside Arabic

    def test_arabic_is_joined(self):
        f = self.hb.HBFontSpec(str(self.font), 60)
        word = "مرحبا بالعالم"
        isolated = sum(self.hb.measure(ch, f) for ch in word)
        self.assertLess(self.hb.measure(word, f), isolated * 0.97)   # contextual forms are narrower than isolated ones

    def test_latin_first_word_ends_up_rightmost(self):
        f = self.hb.HBFontSpec(str(self.font), 40)
        glyphs = self.hb.shape_line("evidence إنها", f)
        e_gid = self.hb.shape_line("e", f)[0][0]
        # visual order left -> right: the Arabic run first, then "evidence" ending in "e" at the far right
        self.assertEqual(glyphs[-1][0], e_gid, "Latin word not on the right in an RTL line")
        self.assertNotEqual(glyphs[0][0], e_gid)

    def test_render_geometry(self):
        f = self.hb.HBFontSpec(str(self.font), 50)
        im, base, w = self.hb.render_line("نص تجريبي", f, (255, 255, 255, 255))
        self.assertEqual(im.mode, "RGBA")
        self.assertGreater(w, 50)
        self.assertGreater(im.getchannel("A").getextrema()[1], 200)
        self.assertEqual(base, 4 + f.getmetrics()[0])


class TestPowerShellGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "client x"
        for d in ("assets/Logo", "data/Raw", "output"):
            (self.root / d).mkdir(parents=True)
        (self.root / "data/Raw/C1.MP4").write_bytes(b"x")
        (self.root / ".whynot-client").write_text("{}", encoding="utf-8")     # 3.0: positive client marker

    def tearDown(self):
        self.tmp.cleanup()

    def test_blocked(self):
        r = self.root.as_posix()
        for c in ['Remove-Item "data/Raw/C1.MP4"', "Copy-Item /x.png -Destination assets/Logo/",
                  f"Set-Content -Path '{r}/assets/x.txt' -Value 1", "echo hi > data/Raw/n.txt",
                  "ffmpeg -i data/Raw/C1.MP4 -y assets/o.mp4", "cd output; Remove-Item ../data -Recurse",
                  "reel ae-build --root x --video-id C1", "Move-Item data/Raw/C1.MP4,data/Raw/C2.MP4 output/",
                  "ren data/Raw/C1.MP4 a.mp4", "Invoke-WebRequest https://x -OutFile data/Raw/x.mp4",
                  "ni assets/new.txt"]:
            self.assertEqual(guard("PowerShell", c, self.root), 2, c)

    def test_allowed(self):
        for c in ["Copy-Item data/Raw/C1.MP4 output/c.mp4", "Get-ChildItem data -Recurse", "echo hi 2> output/log.txt",
                  "ffmpeg -i data/Raw/C1.MP4 -y output/o.mp4", "reel ae-build --extras", "Get-Content data/Raw/C1.MP4 | Out-Null",
                  "reel inbox --root ."]:
            self.assertEqual(guard("PowerShell", c, self.root), 0, c)

    def test_git_bash_paths(self):
        if not plat.IS_WIN:
            self.skipTest("Git Bash drive paths exist only on Windows")
        p = self.root.as_posix()
        msys = "/" + p[0].lower() + p[2:]
        self.assertEqual(guard("Bash", f"rm '{msys}/data/Raw/C1.MP4'", Path.home()), 2)
        self.assertEqual(guard("Bash", f"ls '{msys}/data'", Path.home()), 0)


class TestSettings(unittest.TestCase):
    def test_parse_defaults_and_invalid(self):
        from lib import settings as S
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "ws" / "client"
            d.mkdir(parents=True)
            (Path(t) / "ws/.claude").mkdir()
            (Path(t) / "ws/.claude" / S.FILE).write_text(
                '---\neditor_name: "Sara"\nlanguage: ar\napproval: auto\nwhisper_model: turbo\npreview_video: false\n---\nnotes\n',
                encoding="utf-8")
            st = S.load(d)                                 # found from a sub-folder
            self.assertEqual((st["editor_name"], st["language"], st["approval"]), ("Sara", "ar", "auto"))
            self.assertIs(st["preview_video"], False)
            self.assertEqual(st["whisper_model"], "large-v3")   # invalid value falls back
            self.assertTrue(st["_problems"])
            self.assertEqual(st["_notes"], "notes")
            out = S.save(Path(t) / "other/.claude" / S.FILE, {"approval": "ask"})
            self.assertEqual(S.parse(out.read_text(encoding="utf-8"))[0]["approval"], "ask")


class TestOnboarding(unittest.TestCase):
    def test_scaffold_and_inbox(self):
        from lib.onboard import scaffold, inbox, FOLDERS
        from lib.common import Paths
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "Dr Test"
            r = scaffold(root, "Dr Test")
            self.assertEqual(r["status"], "CREATED")
            for rel in FOLDERS:
                self.assertTrue((root / rel).is_dir(), rel)
            self.assertIn("data/Raw", (root / "START_HERE.md").read_text(encoding="utf-8"))
            (root / "data/Raw/C0001.mp4").write_bytes(b"\0" * 2000)
            self.assertEqual(scaffold(root)["status"], "EXISTS")     # never touches a folder with material
            ib = inbox(root)
            self.assertEqual(ib["new"], ["C0001"])
            self.assertTrue(any("logo" in m for m in ib["missing_material"]))
            Paths(root, "C0001").ensure_project()                   # preflight-like: folder exists, no transcript
            self.assertEqual(inbox(root, refresh=False)["new"], ["C0001"])


class TestDocuments(unittest.TestCase):
    def test_rtf_docx_readers(self):
        from lib.discover import read_document, _rtf_text
        txt = _rtf_text(r"{\rtf1\ansi{\fonttbl\f0 Helvetica;}{\colortbl;\red255;}{\*\expandedcolortbl;;}\f0 Teal #20ACAF\par"
                        r" \u1593?\u1585? caf\'e9}")
        self.assertIn("#20ACAF", txt)
        self.assertIn("عر", txt)
        self.assertIn("café", txt)
        self.assertNotIn("Helvetica", txt)
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "brief.docx"
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("word/document.xml",
                           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                           '<w:p><w:r><w:t>Brand colour #20ACAF</w:t></w:r></w:p><w:p><w:r><w:t>د. نهلة</w:t></w:r></w:p>'
                           '</w:body></w:document>')
            self.assertEqual(read_document(p).splitlines(), ["Brand colour #20ACAF", "د. نهلة"])


class TestPreviewAnimation(unittest.TestCase):
    def test_presets_match_premiere_keyframes(self):
        from lib.preview_video import anim_state
        F = 1 / 24
        g = {"anim": "bar_sweep", "start_s": 0, "end_s": 2, "fade_out_s": 0.2}
        self.assertEqual(anim_state(g, 0)["crop_left"], 1.0)            # hidden until the 1-frame delay
        self.assertAlmostEqual(anim_state(g, 4 * F)["crop_left"], 0.5, places=3)
        self.assertEqual(anim_state(g, 1.0)["crop_left"], 0.0)
        self.assertAlmostEqual(anim_state(g, 1.9)["opacity"], 0.5, places=3)  # fade-out
        pop = {"anim": "text_pop", "start_s": 0, "end_s": 1}
        self.assertAlmostEqual(anim_state(pop, 0)["scale"], 0.9)
        self.assertEqual(anim_state(pop, 0.5)["opacity"], 1.0)
        fl = {"anim": "flash", "start_s": 0, "end_s": 1, "peak": 90}
        self.assertAlmostEqual(anim_state(fl, 0.5)["opacity"], 0.9)
        sl = {"anim": "slide", "start_s": 0, "end_s": 1}
        self.assertEqual(anim_state(sl, 0)["dx"], 60)


class TestReviewHardening(unittest.TestCase):
    def test_adobe_prefs_never_written_by_claude(self):
        here = Path(tempfile.gettempdir())
        for tool, c in [("Bash", 'reg add "HKCU\\Software\\Adobe\\CSXS.12" /v PlayerDebugMode /t REG_SZ /d 1 /f'),
                        ("Bash", "defaults write com.adobe.CSXS.12 PlayerDebugMode 1"),
                        ("PowerShell", 'Set-ItemProperty -Path "HKCU:\\Software\\Adobe\\CSXS.12" -Name PlayerDebugMode -Value 1')]:
            self.assertEqual(guard(tool, c, here), 2, c)
        for tool, c in [("Bash", "defaults read com.adobe.CSXS.12 PlayerDebugMode"),
                        ("PowerShell", "reg query HKCU\\Software\\Adobe\\CSXS.12 /v PlayerDebugMode")]:
            self.assertEqual(guard(tool, c, here), 0, c)

    def test_subagent_cannot_change_preferences(self):
        payload = {"tool_name": "Bash", "agent_type": "whynot-cut:story-editor", "cwd": tempfile.gettempdir(),
                   "tool_input": {"command": "reel settings --init ~ --set approval=auto --force"}}
        r = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload), capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_settings_write_validation_and_clients_root_fallback(self):
        cli = [sys.executable, str(SK / "engine/reel/cli.py"), "settings"]
        with tempfile.TemporaryDirectory() as t:
            env = {k: v for k, v in os.environ.items() if k not in ("WHYNOT_CLIENTS_ROOT", "CLAUDE_PLUGIN_OPTION_CLIENTS_ROOT")}
            bad = subprocess.run(cli + ["--init", t, "--set", "approval=always"], capture_output=True, text=True, env=env)
            self.assertNotEqual(bad.returncode, 0)
            bad = subprocess.run(cli + ["--init", t, "--set", "aproval=auto"], capture_output=True, text=True, env=env)
            self.assertIn("unknown preference", bad.stderr)
            clients = Path(t) / "clients"
            (clients / "Dr X/assets").mkdir(parents=True)
            (clients / "Dr X/data").mkdir()
            ok = subprocess.run(cli + ["--init", t, "--set", f"clients_root={clients.as_posix()}"],
                                capture_output=True, text=True, env=env)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            code = ("import sys; sys.path.insert(0, %r); from lib.common import resolve_root; print(resolve_root('Dr X'))"
                    % str(SK / "engine/reel"))
            r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=t, env=env)
            self.assertEqual(Path(r.stdout.strip()).resolve(), (clients / "Dr X").resolve(), r.stderr)


class TestPremiereWindowsFixes(unittest.TestCase):
    """Found in the first live build on Windows (Premiere 26.5.2): exportFramePNG rejects any '/' in the path, and a
    job where every frame failed was reported with error None."""

    def test_frame_export_paths_are_native(self):
        jsx = (SK / "templates/premiere/nh_ppro_lib.jsx").read_text(encoding="utf-8")
        self.assertIn("NHPP.outPath = function", jsx)
        self.assertNotIn('d.out_dir + "/', jsx)

    def test_failed_frames_are_reported(self):
        from unittest import mock
        from lib import ppro_build
        from lib.common import Paths, write_json
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "C"
            (root / "assets").mkdir(parents=True)
            (root / "data").mkdir()
            p = Paths(root, "V1")
            p.ensure_project()
            write_json(p.p("01_analysis/timeline-spec.json"), {"events": [], "duration_frames": 240})
            fail = {"ok": True, "response": {"ok": True, "result": {"frames": [{"t": 1.0, "error": "Error: Unknown error exception"}]}}}
            with mock.patch("lib.ppro_bridge.submit", return_value=fail):
                r = ppro_build.export_frames(p, times=[1.0])
            self.assertFalse(r["ok"])
            self.assertIn("Unknown error exception", r["error"])


class TestPremiereFileLocks(unittest.TestCase):
    """Windows: Premiere keeps imported stills locked until it quits (seen live on 26.5.2)."""

    def test_unchanged_still_is_not_rewritten(self):
        from PIL import Image
        from lib.previews import save_still
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "x.png"
            im = Image.new("RGBA", (40, 40), (32, 172, 175, 255))
            save_still(im, out)
            m0 = out.stat().st_mtime_ns
            os.utime(out, ns=(m0 - 10**9, m0 - 10**9))
            save_still(im, out)                              # identical pixels -> no write (a locked file is fine)
            self.assertEqual(out.stat().st_mtime_ns, m0 - 10**9)
            save_still(Image.new("RGBA", (40, 40), (0, 0, 0, 255)), out)
            self.assertNotEqual(out.stat().st_mtime_ns, m0 - 10**9)

    def test_premiere_gets_per_build_copies(self):
        from lib.common import Paths
        from lib.ppro_build import stage_stills
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "C"
            (root / "assets").mkdir(parents=True)
            (root / "data").mkdir()
            p = Paths(root, "V1")
            p.ensure_project()
            src = p.p("03_broll/typography/GFX_001_fg.png")
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_bytes(b"png")
            g = [{"png": str(src)}]
            d = stage_stills(p, g)
            self.assertTrue(Path(g[0]["png"]).is_relative_to(d))
            self.assertEqual(Path(g[0]["png"]).read_bytes(), b"png")
            self.assertNotEqual(Path(g[0]["png"]), src)


class TestRealClientGaps(unittest.TestCase):
    """Gaps found editing a real client clip (16:9 finished episode, Arabic, Windows), 2026-10-11."""

    def test_image_files_never_get_document_roles(self):
        from lib.discover import classify
        with tempfile.TemporaryDirectory() as t:
            for rel in ("assets/Photos/Profile.jpg", "assets/Brand/Season promo S.jpg", "assets/Brand/brief.md",
                        "assets/Logo/logo.png"):
                (Path(t) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(t) / rel).write_bytes(b"x")
            role = {rel: classify(Path(t) / rel, rel)["role"] for rel in
                    ("assets/Photos/Profile.jpg", "assets/Brand/Season promo S.jpg", "assets/Brand/brief.md",
                     "assets/Logo/logo.png")}
        self.assertEqual(role["assets/Photos/Profile.jpg"], "client_photo")
        self.assertEqual(role["assets/Brand/Season promo S.jpg"], "brand_image")
        self.assertEqual(role["assets/Brand/brief.md"], "client_brief")
        self.assertEqual(role["assets/Logo/logo.png"], "logo")

    def test_palette_measured_from_brand_image(self):
        from PIL import Image
        from lib.client_db import image_palette
        with tempfile.TemporaryDirectory() as t:
            im = Image.new("RGB", (100, 100), (32, 172, 175))
            im.paste((221, 171, 123), (0, 0, 100, 30))
            im.save(Path(t) / "poster.png")
            pal = image_palette(Path(t) / "poster.png")
        self.assertEqual(pal[0]["hex"], "#20ACAF")
        self.assertIn("#DDAB7B", [c["hex"] for c in pal])

    def test_cutaway_ranges(self):
        from lib.media import cutaway_ranges
        self.assertEqual(cutaway_ranges([True] * 10 + [False] * 6 + [True] * 4, 2, 10), [[4750, 7750]])
        self.assertEqual(cutaway_ranges([True] * 4 + [False] + [True] * 4, 2, 5), [])          # blips ignored
        self.assertEqual(cutaway_ranges([False] * 4 + [True] + [False] * 4, 2, 4.5), [[0, 4250]])  # bridged

    def test_wide_source_reframe_and_cutaway_letterbox(self):
        sys.path.insert(0, str(SK / "tests"))
        import test_pipeline as T
        from lib.common import ffmpeg_exe, write_json, read_json
        from lib.discover import run_discovery
        from lib.media import preflight
        from lib.plan import compile_plan
        from lib.previews import render_all
        from lib.preview_video import render as preview
        from lib.qc import run_qc
        with tempfile.TemporaryDirectory() as t:
            root, p, _ = T.make_project(Path(t))
            clip = root / "data/Raw/CLIP1.mov"            # replace with a 16:9 source (a finished episode is like this)
            subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=384x216:r=25:d=12",
                            "-f", "lavfi", "-i", "sine=f=440:r=48000:d=12", "-ac", "2", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-shortest", str(clip)], check=True)
            run_discovery(p)
            preflight(p, [clip])
            pre = read_json(p.p("00_inputs/preflight.json"))
            rf = next(iter(pre["reframe"].values()))
            self.assertAlmostEqual(rf["base_scale_percent"], 1920 / 216 * 100, places=1)   # fill the height
            rf["cutaways_ms"] = [[6000, 8000]]                                             # a card in the source
            write_json(p.p("00_inputs/preflight.json"), pre)
            tc = T.TestPlanToXML()
            tc.p = p
            tc._semantic_stub()
            ed = tc.decisions()
            ed["global"]["base_scale_percent"] = "auto"
            write_json(p.p("01_analysis/edit-decisions.json"), ed)
            self.assertTrue(compile_plan(p)["ok"])
            spec = read_json(p.p("01_analysis/timeline-spec.json"))
            self.assertTrue(spec["framing"].startswith("auto-reframe"))
            cut = [s for s in spec["main_segments"] if s.get("decision_id") == "AUTO_CUTAWAY"]
            self.assertTrue(cut, spec["main_segments"])
            fit = min(1080 / 384, 1920 / 216) * 100
            self.assertAlmostEqual(cut[0]["scale_factor"] * spec["base_scale_percent"], fit, places=1)
            render_all(p, composite_preview=False)
            pv = preview(p, width=270)
            self.assertTrue(pv["ok"], pv)
            png = Path(t) / "f.png"
            subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", "7.0", "-i", pv["video"], "-frames:v", "1",
                            str(png)], check=True)
            from PIL import Image
            from PIL import ImageStat, ImageFilter
            with Image.open(png) as im:
                g = im.convert("L")
                top, mid = g.crop((0, 30, 270, 120)), g.crop((0, 200, 270, 280))
                detail = lambda x: ImageStat.Stat(x.filter(ImageFilter.FIND_EDGES)).mean[0]
                self.assertGreater(ImageStat.Stat(top).mean[0], 20, "cutaway fill should not be black bars")
                self.assertLess(detail(top), detail(mid), "fill above the card should be blurred, the card sharp")
            fonts = next(c for c in run_qc(p)["checks"] if c["check"].startswith("Brand fonts installed"))
            self.assertFalse(fonts["mandatory"])                       # stills don't need installed fonts


class TestBrollVideo(unittest.TestCase):
    """Licensed stock B-roll videos (data/Broll), as the agency's editor uses them in real reels."""

    def test_broll_video_end_to_end(self):
        sys.path.insert(0, str(SK / "tests"))
        import test_pipeline as T
        import xml.etree.ElementTree as ET
        from lib.common import ffmpeg_exe, write_json, read_json
        from lib.discover import run_discovery
        from lib.media import preflight
        from lib.plan import compile_plan
        from lib.previews import render_all
        from lib.premiere_xml import build_xml
        from lib.preview_video import render as preview
        with tempfile.TemporaryDirectory() as t:
            root, p, _ = T.make_project(Path(t))
            (root / "data/Broll").mkdir()
            subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=640x360:r=25:d=4",
                            "-f", "lavfi", "-i", "sine=f=900:r=48000:d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-shortest", str(root / "data/Broll/stock_red.mp4")], check=True)
            inv = run_discovery(p)["inventory"]
            self.assertIn("data/Broll/stock_red.mp4", inv["by_role"].get("broll_video", []))
            self.assertNotIn("data/Broll/stock_red.mp4", inv["by_role"].get("source_footage", []))
            self.assertTrue(any("licence" in w for w in inv["warnings"]))          # no SOURCES/licence file yet
            preflight(p, [root / "data/Raw/CLIP1.mov"])
            tc = T.TestPlanToXML()
            tc.p = p
            tc._semantic_stub()
            ed = tc.decisions()
            ed["decisions"][0]["graphics"].append({"id": "BR_001", "template": "broll_video", "start": "00:00:02.000",
                                                   "end": "00:00:03.900", "video": "data/Broll/stock_red.mp4", "in": 1.0})
            write_json(p.p("01_analysis/edit-decisions.json"), ed)
            r = compile_plan(p)
            self.assertTrue(r["ok"], r["errors"])
            render_all(p, composite_preview=False)
            xml = ET.parse(build_xml(p, native_graphics=True, lanes=["broll", "gfx_text"])["xml"]).getroot()
            vids = [c for c in xml.iter("clipitem") if "B-roll" in (c.findtext("name") or "")]
            self.assertEqual(len(vids), 1)
            audio_names = [c.findtext("name") or "" for c in xml.find("./sequence/media/audio").iter("clipitem")]
            self.assertFalse([n for n in audio_names if "stock_red" in n], "B-roll audio must never reach the timeline")
            pv = preview(p, width=270)
            self.assertTrue(pv["ok"], pv)
            png = Path(t) / "b.png"
            subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", "3.0", "-i", pv["video"], "-frames:v", "1",
                            str(png)], check=True)
            from PIL import Image
            with Image.open(png) as im:
                r_, g_, b_ = im.convert("RGB").getpixel((20, 60))
            self.assertTrue(r_ > 150 and g_ < 90 and b_ < 90, (r_, g_, b_))       # the B-roll picture is on screen


class TestSessionHookOptions(unittest.TestCase):
    def test_plugin_options_exported_to_tool_shell(self):
        with tempfile.TemporaryDirectory() as t:
            envf = Path(t) / "env.sh"
            env = {k: v for k, v in os.environ.items() if k not in ("WHYNOT_HOME", "WHYNOT_CLIENTS_ROOT")}
            env.update(CLAUDE_ENV_FILE=str(envf), CLAUDE_PLUGIN_OPTION_ENGINE_HOME=str(Path(t) / "eng"),
                       CLAUDE_PLUGIN_ROOT=str(SK))
            before = {str(f) for f in (SK / "engine").rglob("*.pyc")}
            r = subprocess.run([sys.executable, str(SK / "hooks/session_context.py")], input=json.dumps({"cwd": t}),
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("export WHYNOT_HOME=", envf.read_text(encoding="utf-8"))
            new = {str(f) for f in (SK / "engine").rglob("*.pyc")} - before
            self.assertFalse(new, "hook wrote bytecode into the plugin")


class TestManifest(unittest.TestCase):
    def test_branding_and_new_components(self):
        pj = json.loads((SK / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(pj["name"], "whynot-cut")
        self.assertEqual(pj["author"]["email"], "info@thewhynot.ai")
        for s in ("start", "autopilot", "preview", "preferences", "help"):
            self.assertTrue((SK / "skills" / s / "SKILL.md").exists(), s)
        for a in ("setup-doctor", "intake-inspector"):
            self.assertTrue((SK / "agents" / f"{a}.md").exists(), a)
        hooks = json.loads((SK / "hooks/hooks.json").read_text(encoding="utf-8"))
        self.assertIn("PowerShell", hooks["hooks"]["PreToolUse"][0]["matcher"])
        self.assertTrue((SK / "bin/reel.cmd").exists())


def _wav(path: Path, x, sr: int = 16000, ch: int = 1):
    import wave
    import numpy as np
    a = (np.clip(np.asarray(x, dtype=np.float32), -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(a.tobytes())
    return path


class TestFieldTestRound2(unittest.TestCase):
    """Gaps found taking a real reel (R02, a 29.97 fps 16:9 episode, Arabic, religious) through the chain, 2026-10-11."""

    # G17 Whisper audio decoded by the engine (faster-whisper's own decoder breaks with newer PyAV)
    def test_whisper_audio_any_wav(self):
        import numpy as np
        from lib.transcribe import whisper_audio
        with tempfile.TemporaryDirectory() as t:
            a = whisper_audio(_wav(Path(t) / "a.wav", np.zeros(16000)))
            self.assertEqual(a.dtype, np.float32)
            self.assertEqual(len(a), 16000)
            st = np.zeros(48000 * 2, dtype=np.float32)          # 1 s stereo 48 kHz, interleaved
            b = whisper_audio(_wav(Path(t) / "b.wav", st, sr=48000, ch=2))
            self.assertAlmostEqual(len(b) / 16000, 1.0, places=1)
            self.assertFalse((Path(t) / "b.16k.wav").exists())  # temp file cleaned up

    # G18 GPU detection says why Whisper runs on the CPU
    def test_gpu_info_shape(self):
        g = plat.gpu_info()
        self.assertIn(g["whisper_device"], ("cpu", "cuda"))
        if plat.IS_MAC:
            self.assertEqual(g["whisper_device"], "cpu")
        self.assertIn("nvidia-cublas-cu12", plat.CUDA_PIP["windows"])

    # G19 glossary hits after Arabic normalisation; short terms keep hamza / ta marbuta
    def test_glossary_hits_normalised(self):
        sys.path.insert(0, str(SK / "tests"))
        from test_pipeline import words_from
        from lib.transcribe import glossary_hits
        w = words_from("بس أهم حاجة ايه امنوا الأول وعملوا الصالحات قال تعالى".split())
        hits = glossary_hits(w, ["آمنوا", "آية", "قال تعالى"])
        terms = {h["term"]: h for h in hits}
        self.assertIn("آمنوا", terms)                       # آمنوا = امنوا
        self.assertNotIn("آية", terms)                      # verse != Egyptian «ايه» (what)
        self.assertEqual(terms["قال تعالى"]["word_ids"], [9, 10])

    # G20 names from the profile hint that Whisper wrote differently
    def test_vocabulary_misses(self):
        sys.path.insert(0, str(SK / "tests"))
        from test_pipeline import words_from
        from lib.transcribe import vocabulary_misses
        w = words_from("وأنا نضال ولا جيكوفيتش آمنوا وعملوا الصالحات".split())
        miss = {m["expected"]: m["heard"] for m in vocabulary_misses(w, "نادال، ديوكوفيتش، العمل الصالح.")}
        self.assertEqual(miss.get("نادال"), "نضال")
        self.assertEqual(miss.get("ديوكوفيتش"), "جيكوفيتش")
        self.assertNotIn("الصالح", miss)                    # a word form that was heard is not a miss

    # G21 flagged words never go on a graphic; G37 corrections re-anchor after a re-transcription
    def test_flags_block_graphics_and_reanchor(self):
        sys.path.insert(0, str(SK / "tests"))
        import test_pipeline as T
        from lib.common import write_json, read_json
        from lib.plan import compile_plan
        from lib.transcribe import apply_corrections, transcript_flags
        with tempfile.TemporaryDirectory() as t:
            root, p, words = T.make_project(Path(t))
            tc = T.TestPlanToXML()
            tc.p = p
            tc._semantic_stub()
            write_json(p.p("01_analysis/edit-decisions.json"), tc.decisions())
            write_json(p.p("02_transcription/transcript-corrections.json"),
                       {"corrections": [{"word_id": 1, "from": "الليزر", "to": "الليزر", "reason": "re-anchor test"}],
                        "flags": [{"word_id": 3, "note": "unclear"}]})
            r = apply_corrections(p)
            self.assertEqual(r["flagged"], 1)
            self.assertTrue(r["reanchored"] and r["reanchored"][0].startswith("1->"), r)
            self.assertEqual([f["word"] for f in transcript_flags(p)], ["حاجات"])
            res = compile_plan(p)
            self.assertFalse(res["ok"])
            self.assertTrue(any("GFX_001" in e and "uncertain" in e for e in res["errors"]), res["errors"])

    # G24-G27 audio: identical channels, hum only where it stands out, no denoise on a clean master
    def test_assess_source(self):
        import numpy as np
        from lib.audio_clean import SR, assess_source, detect_hum
        rng = np.random.default_rng(1)
        n = SR * 6
        t = np.arange(n) / SR
        speech = (np.sin(2 * np.pi * 220 * t) * 0.3) * (np.sin(2 * np.pi * 0.5 * t) > 0)   # on/off "speech"
        hum = sum(0.004 * np.sin(2 * np.pi * h * t) for h in (100, 150, 200))
        noisy = speech + hum + rng.normal(0, 0.0005, n)
        h = detect_hum(noisy.astype(np.float32))
        self.assertEqual(h["mains_hz"], 50)
        self.assertIn(100, h["notch_hz"])
        clean = (speech + rng.normal(0, 1e-5, n)).astype(np.float32)
        self.assertEqual(detect_hum(clean)["notch_hz"], [])
        a = assess_source(np.stack([clean, clean], axis=1))
        self.assertTrue(a["identical_channels"])
        self.assertTrue(a["already_clean"])
        two = np.stack([clean, (rng.normal(0, 0.05, n)).astype(np.float32)], axis=1)
        self.assertFalse(assess_source(two)["identical_channels"])

    # G28 quotes of the speaker in the client's own documents
    def test_document_quotes(self):
        sys.path.insert(0, str(SK / "tests"))
        import test_pipeline as T
        from lib.discover import run_discovery
        from lib.transcribe import document_quotes
        with tempfile.TemporaryDirectory() as t:
            root, p, words = T.make_project(Path(t))
            (root / "data/Ref/plan.md").write_text("ابدأ من «هل في حاجات معينة لازم» ثم «أول حاجه التشخيص السليم»\n",
                                                   encoding="utf-8")
            run_discovery(p)
            q = {x["quote"]: x for x in document_quotes(p, words)}
        self.assertTrue(q["هل في حاجات معينة لازم"]["exact"])
        diff = q["أول حاجه التشخيص السليم"]
        self.assertFalse(diff["exact"])
        self.assertIn("الصحيح", diff["transcript"])

    # G29 word cuts
    def test_word_cuts(self):
        sys.path.insert(0, str(SK / "tests"))
        from test_pipeline import words_from
        from lib.plan import subtract_ranges, word_cut_ranges
        self.assertEqual(subtract_ranges([(0, 1000), (1500, 3000)], [(800, 1600), (2000, 2010)]),
                         [(0, 800), (1600, 2000), (2010, 3000)])
        w = words_from("يعني أنا جبت مضرب".split(), 0, 400)
        rng, cut, err = word_cut_ranges(w, [{"word_ids": [1], "reason": "filler"}, 99], 2000)
        self.assertEqual(rng, [(0, 390)])                    # word end + 30 ms, never into the next word (at 400)
        self.assertEqual(cut[0]["word"], "يعني")
        self.assertTrue(err and "99" in err[0])

    def test_word_cut_compiles_out_of_captions(self):
        sys.path.insert(0, str(SK / "tests"))
        import test_pipeline as T
        from lib.common import write_json, read_json
        from lib.plan import compile_plan
        from lib import srt as srtlib
        with tempfile.TemporaryDirectory() as t:
            root, p, words = T.make_project(Path(t))
            tc = T.TestPlanToXML()
            tc.p = p
            tc._semantic_stub()
            ed = tc.decisions()
            ed["global"]["cut_words"] = [{"word_ids": [6], "reason": "test"}]       # «أبقى»
            write_json(p.p("01_analysis/edit-decisions.json"), ed)
            res = compile_plan(p)
            self.assertTrue(res["ok"], res["errors"])
            spec = read_json(p.p("01_analysis/timeline-spec.json"))
            self.assertEqual(spec["time_map"]["words_cut"][0]["word"], "أبقى")
            caps = " ".join(c["text"] for c in srtlib.read_srt(p.p("02_transcription/captions-short-seq.srt")))
            self.assertNotIn("أبقى", caps)
            self.assertIn("عارفاها", caps)
            self.assertIn("Words cut (1)", p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8"))

    # G30 / G31 a reel = a range of a longer raw file; --video-id picks its own clip
    def test_source_range_schemas_and_ffmpeg_args(self):
        from lib.common import Paths, range_input_args, source_range, write_json
        with tempfile.TemporaryDirectory() as t:
            p = Paths(Path(t), "R02")
            p.ensure_project()
            self.assertEqual(source_range(p), {})
            write_json(p.p("00_inputs/source.json"), {"footage": "data/Raw/EP.mp4", "in_ms": 1500, "out_ms": 4000})
            self.assertEqual(range_input_args(source_range(p)), ["-ss", "1.500", "-t", "2.500"])
            write_json(p.p("00_inputs/source.json"), {"kind": "episode_reel", "rel": "data/Episodes/EP.mp4",
                                                      "offset_ms": 2000, "duration_ms": 1000, "reel_id": "R1"})
            r = source_range(p)
            self.assertEqual((r["footage"], r["in_ms"], r["out_ms"], r["reel_id"]), ("data/Episodes/EP.mp4", 2000, 3000, "R1"))

    def test_xml_points_into_the_original_file(self):
        sys.path.insert(0, str(SK / "tests"))
        import re as _re
        import test_pipeline as T
        from lib.common import write_json, read_json, ticks_per_frame
        from lib.media import preflight
        from lib.plan import compile_plan
        from lib.premiere_xml import build_xml
        with tempfile.TemporaryDirectory() as t:
            root, p, words = T.make_project(Path(t))
            write_json(p.p("00_inputs/source.json"), {"footage": "data/Raw/CLIP1.mov", "in_ms": 500, "out_ms": 12000})
            preflight(p, [root / "data/Raw/CLIP1.mov"])
            tc = T.TestPlanToXML()
            tc.p = p
            tc._semantic_stub()
            write_json(p.p("01_analysis/edit-decisions.json"), tc.decisions())
            self.assertTrue(compile_plan(p)["ok"])
            spec = read_json(p.p("01_analysis/timeline-spec.json"))
            self.assertEqual(spec["source_in_ms"], 500)
            xml = Path(build_xml(p)["xml"]).read_text(encoding="utf-8")
            first_in = int(_re.search(r"<pproTicksIn>(\d+)</pproTicksIn>", xml).group(1))
            self.assertEqual(first_in, round((spec["main_segments"][0]["src_in_ms"] + 500) * 254016000000 / 1000))

    # G32 / G33 the sequence rate follows the client; NTSC rates in FCP7 XML
    def test_ntsc_rate_helpers(self):
        from lib.common import fps_arg, ms_to_frame, ticks_per_frame
        from lib.premiere_xml import rate
        self.assertEqual(rate(29.97002997), "<rate><timebase>30</timebase><ntsc>TRUE</ntsc></rate>")
        self.assertEqual(rate(25), "<rate><timebase>25</timebase><ntsc>FALSE</ntsc></rate>")
        self.assertEqual(ticks_per_frame(30000 / 1001), 8475667200)
        self.assertEqual(ticks_per_frame(25), 10160640000)
        self.assertEqual(fps_arg(30000 / 1001), "30000/1001")
        self.assertEqual(ms_to_frame(1001, 30000 / 1001), 30)

    def test_profile_sequence_rate_2997(self):
        sys.path.insert(0, str(SK / "tests"))
        import test_pipeline as T
        from lib import common
        from lib.common import write_json, read_json
        from lib.plan import compile_plan
        from lib.premiere_xml import build_xml
        from lib.qc import run_qc
        with tempfile.TemporaryDirectory() as t:
            root, p, words = T.make_project(Path(t))
            prof = root / common.CLIENT_PROFILE_REL
            prof.mkdir(parents=True, exist_ok=True)
            write_json(prof / "sequence-settings.json", {"general": {"timebase": 30, "ntsc": True}})
            common.set_context(root)
            try:
                from lib.media import preflight
                preflight(p, [root / "data/Raw/CLIP1.mov"])
                self.assertAlmostEqual(common.seq_fps(), 29.97, places=2)
                tc = T.TestPlanToXML()
                tc.p = p
                tc._semantic_stub()
                write_json(p.p("01_analysis/edit-decisions.json"), tc.decisions())
                self.assertTrue(compile_plan(p)["ok"])
                spec = read_json(p.p("01_analysis/timeline-spec.json"))
                self.assertEqual(spec["duration_frames"], round(12000 * 30000 / 1001 / 1000))
                xml = Path(build_xml(p)["xml"]).read_text(encoding="utf-8")
                self.assertIn("<timebase>30</timebase><ntsc>TRUE</ntsc>", xml)
                rate_chk = next(c for c in run_qc(p)["checks"] if c["check"].startswith("Sequence rate"))
                self.assertEqual(rate_chk["result"], "PASS", rate_chk)
            finally:
                common.set_context(None)
                self.assertEqual(common.seq_fps(), 24.0)

    # G36 a range never starts or ends mid-word
    def test_snap_range_points(self):
        import numpy as np
        from lib.common import ffmpeg_exe
        from lib.media import snap_range_points
        sr = 16000
        x = np.concatenate([np.sin(np.arange(int(0.6 * sr)) * 0.2) * 0.3, np.zeros(int(1.1 * sr)),
                            np.sin(np.arange(int(3.0 * sr)) * 0.2) * 0.3, np.zeros(int(1.0 * sr)),
                            np.sin(np.arange(int(1.0 * sr)) * 0.2) * 0.3])
        with tempfile.TemporaryDirectory() as t:
            wav = _wav(Path(t) / "ep.wav", x, sr)
            r = snap_range_points(wav, 300, 4200)
        self.assertTrue(1500 <= r["in"]["suggested_ms"] <= 1700, r)     # just before speech resumes at 1.7 s
        self.assertTrue(4700 <= r["out"]["suggested_ms"] <= 4900, r)    # just after it stops at 4.7 s

    # G39 the plan reads on the reel's clock; G42 captions dodge a card only when it overlaps them
    def test_seq_frame_and_cover(self):
        from lib.plan import _seq_frame, speaker_covered_frames
        spec = {"fps": 25, "duration_frames": 100, "events": [{"template": "broll_card", "start_frame": 0, "end_frame": 10}],
                "main_segments": [{"start_frame": 0, "end_frame": 50, "src_in_ms": 0},
                                  {"start_frame": 50, "end_frame": 100, "src_in_ms": 3000, "decision_id": "AUTO_CUTAWAY"}]}
        self.assertEqual(_seq_frame(spec, 1000), 25)
        self.assertEqual(_seq_frame(spec, 2500), 50)       # inside a removed stretch -> next kept piece
        self.assertEqual(_seq_frame(spec, 4000), 75)
        self.assertEqual(speaker_covered_frames(spec), 60)

    def test_caption_avoids_only_overlapping_cards(self):
        sys.path.insert(0, str(SK / "tests"))
        import test_pipeline as T
        from PIL import Image
        from lib.common import write_json, load_config
        from lib.plan import compile_plan
        from lib.previews import render_captions
        with tempfile.TemporaryDirectory() as t:
            root, p, words = T.make_project(Path(t))
            tc = T.TestPlanToXML()
            tc.p = p
            tc._semantic_stub()
            write_json(p.p("01_analysis/edit-decisions.json"), tc.decisions())
            self.assertTrue(compile_plan(p)["ok"])
            y = load_config("graphics-templates.json")["templates"]["highlight_caption"]["y"]

            def first_cap_box(avoid):
                c = render_captions(p, [], avoid=avoid)[0]
                return Image.open(c["fg"]).getchannel("A").getbbox()
            base = first_cap_box([])
            top_card = first_cap_box([(0, 60000, 150, 420)])                # card at the top: caption stays
            low_card = first_cap_box([(0, 60000, y - 40, y + 160)])         # card on the caption band: moves above
        self.assertEqual(top_card, base)
        self.assertLess(low_card[3], y - 40)
        self.assertGreater(low_card[1], 200)


class TestClientPlanRules(unittest.TestCase):
    """Rules from a client's written reels plan (Reels_Plan_EP02.md) that the plugin must be able to follow."""

    def test_caption_punctuation(self):
        from lib.previews import caption_text
        self.assertEqual(caption_text("وعملوا الصالحات،\nبس لازم"), "وعملوا الصالحات، بس لازم")      # default: as heard
        self.assertEqual(caption_text("وعملوا الصالحات، بس... لازم؟", "،,.;؛:"), "وعملوا الصالحات بس… لازم؟")
        self.assertEqual(caption_text(" ، ", "،"), "")

    def test_caption_lead_in_never_overlaps(self):
        sys.path.insert(0, str(SK / "tests"))
        import test_pipeline as T
        from lib import common
        from lib.common import write_json, read_json
        from lib.plan import compile_plan
        from lib.previews import render_captions
        from lib import srt as srtlib
        with tempfile.TemporaryDirectory() as t:
            root, p, words = T.make_project(Path(t))
            prof = root / common.CLIENT_PROFILE_REL
            prof.mkdir(parents=True, exist_ok=True)
            write_json(prof / "graphics-templates.json", {"templates": {"highlight_caption": {"lead_in_ms": 200}}})
            common.set_context(root)
            try:
                tc = T.TestPlanToXML()
                tc.p = p
                tc._semantic_stub()
                write_json(p.p("01_analysis/edit-decisions.json"), tc.decisions())
                self.assertTrue(compile_plan(p)["ok"])
                spec = read_json(p.p("01_analysis/timeline-spec.json"))
                src = srtlib.read_srt(p.p(spec["caption_source"]))
                caps = render_captions(p, [])
            finally:
                common.set_context(None)
        self.assertEqual(caps[0]["start_ms"], max(0, src[0]["start_ms"] - 200))
        for a, b in zip(caps, caps[1:]):
            self.assertLessEqual(a["end_ms"], b["start_ms"])

    def test_sharpen_only_on_strong_upscale(self):
        from lib import common
        from lib.common import write_json
        from lib.ppro_build import sharpen_settings
        self.assertEqual(sharpen_settings({"base_scale_percent": 177.778})["amount"], 15)   # default style
        self.assertIsNone(sharpen_settings({"base_scale_percent": 100}))                  # native 9:16 untouched
        with tempfile.TemporaryDirectory() as t:
            prof = Path(t) / common.CLIENT_PROFILE_REL
            prof.mkdir(parents=True)
            write_json(prof / "style.json", {"reframe_sharpen": {"amount": 18, "grain_percent": 2}})
            common.set_context(Path(t))
            try:
                self.assertEqual(sharpen_settings({"base_scale_percent": 177.8}), {"amount": 18.0, "grain": 2.0})
                write_json(prof / "style.json", {"reframe_sharpen": {"amount": 0}})
                self.assertIsNone(sharpen_settings({"base_scale_percent": 177.8}))
            finally:
                common.set_context(None)

    def test_export_name_from_client_pattern(self):
        from lib import common
        from lib.common import Paths, write_json
        from lib.handoff import export_spec
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            prof = root / common.CLIENT_PROFILE_REL
            prof.mkdir(parents=True)
            write_json(prof / "style.json", {"export": {"name": "{episode}_{video_id}_{name}_9x16_AR_v{version:02d}.mp4",
                                                        "folder": "EP2/Reels Plan/Exports"}})
            p = Paths(root, "R02")
            p.ensure_project()
            write_json(p.p("00_inputs/source.json"), {"footage": "data/Raw/EP02.mp4", "in_ms": 0, "out_ms": 1000,
                                                      "label": "R02 Tennis_Racket_Tasleem"})
            common.set_context(root)
            try:
                ex = export_spec(p)
            finally:
                common.set_context(None)
        self.assertEqual(ex["file_name"], "EP02_R02_Tennis_Racket_Tasleem_9x16_AR_v01.mp4")
        self.assertEqual(ex["folder"], "EP2/Reels Plan/Exports")

    def test_window_rect(self):
        from lib.plan import window_rect
        self.assertIsNone(window_rect("9:16"))
        self.assertEqual(window_rect("4:5"), {"w": 1080, "h": 1350, "y": 285, "mode": "4:5"})
        self.assertEqual(window_rect("4x5", 400)["y"], 400)

    def test_four_by_five_framing_chain(self):
        sys.path.insert(0, str(SK / "tests"))
        import re as _re
        import test_pipeline as T
        from PIL import Image, ImageStat
        from lib.common import ffmpeg_exe, write_json, read_json
        from lib.discover import run_discovery
        from lib.media import preflight
        from lib.plan import compile_plan
        from lib.premiere_xml import build_xml
        from lib.previews import render_all
        from lib.preview_video import render as preview
        with tempfile.TemporaryDirectory() as t:
            root, p, _ = T.make_project(Path(t))
            clip = root / "data/Raw/CLIP1.mov"            # a 16:9 source, like a finished episode
            subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=384x216:r=25:d=12",
                            "-f", "lavfi", "-i", "sine=f=440:r=48000:d=12", "-ac", "2", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-shortest", str(clip)], check=True)
            run_discovery(p)
            preflight(p, [clip])
            tc = T.TestPlanToXML()
            tc.p = p
            tc._semantic_stub()
            ed = tc.decisions()
            ed["global"].update({"base_scale_percent": "auto", "framing": "4:5"})
            ed["decisions"][0]["camera"] = {"type": "punch_in", "at": "00:00:01.000", "until": "00:00:03.000",
                                            "scale_factor": 1.08}
            write_json(p.p("01_analysis/edit-decisions.json"), ed)
            res = compile_plan(p)
            self.assertTrue(res["ok"], res["errors"])
            spec = read_json(p.p("01_analysis/timeline-spec.json"))
            self.assertIn("4:5 window", spec["framing"])
            segs = spec["main_segments"]
            self.assertTrue(all(s.get("window") for s in segs if s["decision_id"] != "AUTO_CUTAWAY"), segs)   # cards stay whole
            k45 = 1350 / 216 * 100 / spec["base_scale_percent"]
            hold = next(s for s in segs if s["decision_id"] == "AUTO_WINDOW")
            punch = next(s for s in segs if s["decision_id"] == "EDIT_001")
            self.assertAlmostEqual(hold["scale_factor"], k45, places=3)
            self.assertAlmostEqual(punch["scale_factor"], k45 * 1.08, places=3)
            xml = Path(build_xml(p)["xml"]).read_text(encoding="utf-8")
            self.assertIn("<effectid>crop</effectid>", xml)
            self.assertIn("window]", xml)
            # the punch-in piece is cropped back to the 1350 px window: top crop grows with the zoom
            tops = [float(x) for x in _re.findall(r"<parameterid>top</parameterid><name>top</name><valuemin>0</valuemin>"
                                                  r"<valuemax>100</valuemax><value>([0-9.]+)</value>", xml)]
            self.assertTrue(tops and max(tops) > min(tops) >= 0, tops)
            render_all(p, composite_preview=False)
            pv = preview(p, width=270)
            self.assertTrue(pv["ok"], pv)
            png = Path(t) / "f.png"
            subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", "5.0", "-i", pv["video"], "-frames:v", "1",
                            str(png)], check=True)
            with Image.open(png) as im:   # 270x480 preview: window rows 71..409, blurred bands above and below
                g = im.convert("L")
                step = lambda y: max(abs(g.getpixel((x + 1, y)) - g.getpixel((x, y))) for x in range(269))
                self.assertLess(step(45), step(150) / 2, "band blurred (soft steps), window sharp (hard steps)")
                self.assertLess(step(440), step(150) / 2)

    def test_hallucination_dropped_only_when_not_speech(self):
        from lib.transcribe import drop_hallucinations
        segs = [{"id": 1, "start_ms": 0, "end_ms": 4000, "text": "قال له ما تقلقش", "no_speech_prob": 0.01, "words": [1, 2, 3, 4]},
                {"id": 2, "start_ms": 58800, "end_ms": 59120, "text": "اشتركوا في القناة", "no_speech_prob": 0.93, "words": [5, 6, 7]},
                {"id": 3, "start_ms": 60000, "end_ms": 63000, "text": "اشتركوا في القناة", "no_speech_prob": 0.05, "words": [8, 9, 10]}]
        words = [{"id": i} for i in range(1, 11)]
        s2, w2, dropped = drop_hallucinations(segs, words)
        self.assertEqual([s["id"] for s in s2], [1, 3])          # a speaker who really asks to subscribe stays
        self.assertEqual([w["id"] for w in w2], [1, 2, 3, 4, 8, 9, 10])
        self.assertEqual(dropped[0]["start_ms"], 58800)

    def test_video_vocabulary_file(self):
        from lib.common import Paths
        from lib.transcribe import video_vocabulary
        with tempfile.TemporaryDirectory() as t:
            p = Paths(Path(t), "R02")
            p.ensure_project()
            p.p("00_inputs/vocabulary.txt").write_text("# names\nنادال\nديوكوفيتش، المانيوال\n", encoding="utf-8")
            self.assertEqual(video_vocabulary(p), ["نادال", "ديوكوفيتش", "المانيوال"])

    def test_other_person_on_camera_is_not_the_speaker(self):
        from lib import media, previews
        from lib.common import ffmpeg_exe
        with tempfile.TemporaryDirectory() as t:
            v = Path(t) / "ep.mp4"   # speaker look 0-4 s, another set-up 4-6.5 s, speaker again
            subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0xC89A50:s=320x180:r=10:d=4",
                            "-f", "lavfi", "-i", "color=c=0xE8E2D8:s=320x180:r=10:d=2.5",
                            "-f", "lavfi", "-i", "color=c=0xC89A50:s=320x180:r=10:d=4",
                            "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0", "-pix_fmt", "yuv420p", str(v)], check=True)
            real = previews._face_center
            previews._face_center = lambda im: (0.5, 0.4)     # a face everywhere: the host has one too
            try:
                r = media.analyze_shots(v, 10.5)
            finally:
                previews._face_center = real
        self.assertEqual(len(r["other_people_ms"]), 1, r)
        a, b = r["other_people_ms"][0]
        self.assertTrue(3500 <= a <= 4500 and 6000 <= b <= 7000, r)
        self.assertEqual(r["cutaways_ms"], r["other_people_ms"])

    def test_no_sharpen_when_v1_is_all_blurred_fill(self):
        from lib.ppro_build import sharpen_settings
        segs = [{"decision_id": "AUTO_WINDOW", "window": {"h": 1350}}, {"decision_id": "AUTO_CUTAWAY"}]
        self.assertIsNone(sharpen_settings({"base_scale_percent": 177.8, "main_segments": segs}))
        self.assertIsNotNone(sharpen_settings({"base_scale_percent": 177.8, "main_segments": segs + [{"decision_id": None}]}))

    def test_engine_cuda_folder_is_searched(self):
        with tempfile.TemporaryDirectory() as h:
            old = os.environ.get("WHYNOT_HOME")
            os.environ["WHYNOT_HOME"] = h
            try:
                (Path(h) / "cuda" / "bin").mkdir(parents=True)
                self.assertEqual(plat.cuda_lib_dirs()[0], Path(h) / "cuda" / "bin")
            finally:
                if old is None:
                    os.environ.pop("WHYNOT_HOME", None)
                else:
                    os.environ["WHYNOT_HOME"] = old

    def test_reference_analysis_cached_per_client(self):
        from lib.common import Paths, ffmpeg_exe
        from lib.ref_analysis import analyze_all
        with tempfile.TemporaryDirectory() as t:
            ref = Path(t) / "ref.mp4"
            subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=216x384:r=25:d=3",
                            "-pix_fmt", "yuv420p", str(ref)], check=True)
            p1, p2 = Paths(Path(t), "R01"), Paths(Path(t), "R02")
            p1.ensure_project()
            p2.ensure_project()
            a = analyze_all(p1, [ref], {str(ref): 3.0})
            b = analyze_all(p2, [ref], {str(ref): 3.0})
            log2 = p2.p("logs/pipeline.log").read_text(encoding="utf-8")
            self.assertIn("cached client analysis", log2)
            self.assertEqual(a["references"], b["references"])
            self.assertTrue(p2.p("01_analysis/reference_analysis/reference-measurements.json").exists())

    def test_caption_over_blurred_fill_gets_a_box(self):
        sys.path.insert(0, str(SK / "tests"))
        import test_pipeline as T
        from lib.common import ffmpeg_exe, write_json, read_json
        from lib.discover import run_discovery
        from lib.media import preflight
        from lib.plan import compile_plan
        from lib.previews import render_captions
        with tempfile.TemporaryDirectory() as t:
            root, p, _ = T.make_project(Path(t))
            clip = root / "data/Raw/CLIP1.mov"
            subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=384x216:r=25:d=12",
                            "-f", "lavfi", "-i", "sine=f=440:r=48000:d=12", "-ac", "2", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-shortest", str(clip)], check=True)
            run_discovery(p)
            preflight(p, [clip])
            pre = read_json(p.p("00_inputs/preflight.json"))
            next(iter(pre["reframe"].values()))["cutaways_ms"] = [[2000, 5000]]     # a card in the source
            write_json(p.p("00_inputs/preflight.json"), pre)
            tc = T.TestPlanToXML()
            tc.p = p
            tc._semantic_stub()
            ed = tc.decisions()
            ed["global"]["base_scale_percent"] = "auto"
            ed["caption_highlights"] = []
            write_json(p.p("01_analysis/edit-decisions.json"), ed)
            self.assertTrue(compile_plan(p)["ok"])
            caps = render_captions(p, [])
        over = [c for c in caps if c["start_ms"] < 5000 and c["end_ms"] > 2000]
        away = [c for c in caps if c["start_ms"] >= 5200]
        self.assertTrue(over and all(c.get("bar") for c in over), over)      # boxed over the bright blur
        self.assertTrue(away and not any(c.get("bar") for c in away), away)  # the client's plain style elsewhere

    def test_untouched_save_is_not_an_editor_change(self):
        import gzip
        import time as _time
        from lib.common import Paths, write_json
        from lib.verify import editor_modified, prproj_signature
        xml = ('<Project><MZ.BuildVersion.Modified>26.5 - {t}</MZ.BuildVersion.Modified><NextID>{n}</NextID>'
               '<MasterClipChangeVersion>{v}</MasterClipChangeVersion>{nodes}<MZ.EditLine>{e}</MZ.EditLine>'
               '<ClipItem start="{s}"/></Project>')
        with tempfile.TemporaryDirectory() as t:
            p = Paths(Path(t), "R05")
            p.ensure_project()
            prj = p.p("07_premiere/project/R05_RE_EDIT.prproj")
            prj.parent.mkdir(parents=True, exist_ok=True)
            write = lambda **k: prj.write_bytes(gzip.compress(xml.format(**k).encode("utf-8")))
            write(t="4:06", n=1000001, v=2144, nodes="", e=0, s=0)
            built = prj.stat().st_mtime
            write_json(p.p("07_premiere/ppro-build-result.json"), {"project": str(prj), "prproj_mtime": built,
                                                                   "content_signature": prproj_signature(prj)})
            # Premiere re-saves it (another reel was built, or auto-save): stamp, ids, empty nodes, playhead change
            write(t="4:09", n=1000004, v=2145, nodes='<Node Version="1">\n<ID>1000003</ID>\n</Node>', e=12018513024000, s=0)
            os.utime(prj, (built + 300, built + 300))
            self.assertIsNone(editor_modified(p))
            write(t="4:12", n=1000006, v=2146, nodes="", e=5, s=48)          # the editor moved a clip
            os.utime(prj, (built + 600, built + 600))
            em = editor_modified(p)
            self.assertIsNotNone(em)
            self.assertEqual(em["content"], "changed")

    def test_bridge_sets_grain_by_intensity_or_amount(self):
        jsx = (SK / "templates/premiere/nh_ppro_lib.jsx").read_text(encoding="utf-8")
        self.assertIn('NHPP.prop(nc, "Intensity") || NHPP.prop(nc, "Amount of Noise")', jsx)   # Premiere 26 default is 50
        self.assertIn("NHPP.actions.clip_components", jsx)


class TestMainFootageFraming(unittest.TestCase):
    """Framing is sized from THIS reel's footage (global.main_footage, or the range footage in source.json), never
    from whichever file preflight.json lists first."""

    def _wide_project(self, t):
        sys.path.insert(0, str(SK / "tests"))
        import test_pipeline as T
        from lib.common import ffmpeg_exe
        from lib.discover import run_discovery
        root, p, _ = T.make_project(Path(t))
        clip = root / "data/Raw/CLIP1.mov"            # a 16:9 source (a finished episode)
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=384x216:r=25:d=12",
                        "-f", "lavfi", "-i", "sine=f=440:r=48000:d=12", "-ac", "2", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-shortest", str(clip)], check=True)
        run_discovery(p)
        tc = T.TestPlanToXML()
        tc.p = p
        tc._semantic_stub()
        return root, p, clip, tc

    def test_range_reel_without_main_footage_gets_the_reframe_and_card_bands(self):
        from lib.common import write_json, read_json
        from lib.media import preflight
        from lib.plan import compile_plan
        from lib.ppro_build import cutaway_bands
        with tempfile.TemporaryDirectory() as t:
            root, p, clip, tc = self._wide_project(t)
            write_json(p.p("00_inputs/source.json"), {"footage": "data/Raw/CLIP1.mov", "in_ms": 0, "out_ms": 12000})
            preflight(p, [clip])
            pre = read_json(p.p("00_inputs/preflight.json"))
            next(iter(pre["reframe"].values()))["cutaways_ms"] = [[6000, 8000]]
            # a stale entry from an earlier --footage run, listed FIRST (a vertical phone clip)
            pre["files"].insert(0, {"path": str(root / "data/Raw/OLD.mov"),
                                    "video": {"display_width": 1080, "display_height": 1920}})
            write_json(p.p("00_inputs/preflight.json"), pre)
            ed = tc.decisions()
            ed["global"].pop("main_footage", None)     # a range reel names its footage in source.json only
            ed["global"]["base_scale_percent"] = "auto"
            write_json(p.p("01_analysis/edit-decisions.json"), ed)
            res = compile_plan(p)
            self.assertTrue(res["ok"], res["errors"])
            spec = read_json(p.p("01_analysis/timeline-spec.json"))
            self.assertTrue(spec["framing"].startswith("auto-reframe"), spec["framing"])
            self.assertTrue(any(s["decision_id"] == "AUTO_CUTAWAY" for s in spec["main_segments"]))
            bands = cutaway_bands(p, spec)
            fit = min(1080 / 384, 1920 / 216)                 # the card is shown whole: 216 px tall at the fit scale
            self.assertEqual(len(bands), 1, bands)
            self.assertAlmostEqual(bands[0][3] - bands[0][2], 216 * fit, delta=2)

    def test_four_by_five_on_a_vertical_clip_is_windowed(self):
        sys.path.insert(0, str(SK / "tests"))
        import test_pipeline as T
        from lib.common import write_json, read_json
        from lib.media import preflight
        from lib.plan import compile_plan
        from lib.premiere_xml import build_xml
        with tempfile.TemporaryDirectory() as t:
            root, p, _ = T.make_project(Path(t))      # CLIP1 is 216x384: already 9:16, so preflight has no reframe
            preflight(p, [root / "data/Raw/CLIP1.mov"])
            tc = T.TestPlanToXML()
            tc.p = p
            tc._semantic_stub()
            ed = tc.decisions()
            ed["global"].update({"base_scale_percent": "auto", "framing": "4:5"})
            write_json(p.p("01_analysis/edit-decisions.json"), ed)
            res = compile_plan(p)
            self.assertTrue(res["ok"], res["errors"])
            spec = read_json(p.p("01_analysis/timeline-spec.json"))
            self.assertIn("4:5 window", spec["framing"])           # not silently built as 9:16
            self.assertAlmostEqual(spec["base_scale_percent"], 500.0, places=2)
            segs = spec["main_segments"]
            self.assertTrue(segs and all(s.get("window") for s in segs), segs)
            self.assertIn("<effectid>crop</effectid>", Path(build_xml(p)["xml"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
