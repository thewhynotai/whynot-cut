"""ET1-07 browser checks of the installer window shell (installer/app/ui), in headless Chrome or Edge.

Each page load is read through the page's own self-check (<meta name="mock-check">, the fields of the mockup's
installer.js check plus csp= and jserr=), the browser console on stderr (CSP and uncaught errors), and the dumped DOM.

Matrix: the demo shell at 760 and 640, AR and EN, macOS chrome (default, G11) and the Windows variant; the hostile-path
fixture; the empty (no demo) entry. Detector proofs: a fixture that breaks the CSP, a fixture that asks for a missing
key and icon, and a staging without the fonts must each be caught, so a green run means something.
Run heavy: heavy.sh job et1-07 -- python -m unittest -v (from installer/app/tests).
"""
from __future__ import annotations

import concurrent.futures as cf
import pathlib
import re
import shutil
import tempfile
import unittest

import _harness as H

LANGS = ("en", "ar")
WIDTHS = (760, 640)
OSES = ("mac", "win")
BIDI_CONTROLS = set("؜‎‏‪‫‬‭‮⁦⁧⁨⁩")
HOSTILE_HTML = "<img src=x onerror=alert(1)>"


class ShellRenders(unittest.TestCase):
    R: dict = {}

    @classmethod
    def setUpClass(cls):
        cls.exe = H.browser()
        cls.work = pathlib.Path(tempfile.mkdtemp(prefix="ui-", dir=H.tmp_root()))
        cls.delta = H.viewport_delta(cls.exe, cls.work)
        cls.stage = H.stage(cls.work / "stage")
        cls.stage_nofonts = H.stage(cls.work / "stage-nofonts", skip_fonts=True)
        jobs = {}
        for lang in LANGS:
            for w in WIDTHS:
                for os_kind in OSES:
                    jobs[("shell", lang, w, os_kind)] = (cls.stage, {"demo": "shell", "lang": lang, "os": os_kind}, w, os_kind)
                    jobs[("hostile", lang, w, os_kind)] = (cls.stage, {"demo": "shell", "fixture": "hostile", "lang": lang,
                                                                       "os": os_kind}, w, os_kind)
        jobs[("idle", "en", 760, "mac")] = (cls.stage, {"lang": "en"}, 760, "mac")
        for lang in LANGS:
            jobs[("nosupport", lang, 640, "mac")] = (cls.stage, {"demo": "shell", "lang": lang, "support": "off"}, 640, "mac")
        jobs[("csp-probe", "en", 760, "mac")] = (cls.stage, {"demo": "shell", "fixture": "csp-probe", "lang": "en"}, 760, "mac")
        jobs[("missing", "en", 760, "mac")] = (cls.stage, {"demo": "shell", "fixture": "missing", "lang": "en"}, 760, "mac")
        jobs[("nofonts", "ar", 760, "mac")] = (cls.stage_nofonts, {"demo": "shell", "lang": "ar"}, 760, "mac")
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            futs = {k: ex.submit(H.render, cls.exe, st, cls.work, q, w, os_kind, "-".join(map(str, k)), delta=cls.delta)
                    for k, (st, q, w, os_kind) in jobs.items()}
            cls.R = {k: f.result() for k, f in futs.items()}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def cases(self, kinds=("shell", "hostile", "idle", "nosupport")):
        return [(k, r) for k, r in self.R.items() if k[0] in kinds]

    # ---- every normal page ----
    def test_self_check_present(self):
        for k, r in self.cases():
            with self.subTest(k=k):
                self.assertIsNotNone(r.raw_check, f"no self-check in the DOM: {r.label()}\n{r.log[-2000:]}")

    def test_csp_violations_zero(self):
        for k, r in self.cases():
            with self.subTest(k=k):
                self.assertEqual(r.check.get("csp"), "0", r.raw_check)
                self.assertEqual(r.console_csp, [])
                self.assertEqual(r.console_csp_notes, [])

    def test_no_script_errors(self):
        for k, r in self.cases():
            with self.subTest(k=k):
                self.assertEqual(r.check.get("jserr"), "0", r.raw_check)
                self.assertEqual(r.console_errors, [])

    def test_no_horizontal_overflow(self):
        for k, r in self.cases():
            with self.subTest(k=k):
                self.assertEqual(r.check.get("overflow"), "0", f"{r.label()}: worst={r.check.get('worst')}")

    def test_fonts_loaded(self):
        for k, r in self.cases():
            with self.subTest(k=k):
                self.assertEqual(r.check.get("fonts"), "ok", r.raw_check)

    def test_no_missing_key_or_icon(self):
        for k, r in self.cases():
            with self.subTest(k=k):
                self.assertEqual(r.check.get("missing"), "", r.raw_check)

    def test_window_width_direction_and_mirroring(self):
        for k, r in self.cases(("shell", "hostile")):
            _, lang, w, _ = k
            with self.subTest(k=k):
                self.assertEqual(r.check.get("w"), str(w))
                self.assertEqual(r.check.get("h"), str(H.CONTENT_H[w] + H.CHROME_H[k[3]]))
                self.assertEqual(r.check.get("dir"), "rtl" if lang == "ar" else "ltr")
                self.assertEqual(r.check.get("mono"), "right" if lang == "ar" else "left")
                self.assertEqual(r.check.get("lang"), lang)

    def test_keycap_rules(self):
        for k, r in self.cases():
            with self.subTest(k=k):
                self.assertEqual(r.check.get("dangerkbd"), "0")
                self.assertEqual(r.check.get("confirmkbd"), "0")
                self.assertIn(r.check.get("violet"), ("0", "1"))

    def test_os_chrome_variant(self):
        for k, r in self.cases(("shell",)):
            d = H.scan_dom(r.dom)
            classes = " ".join(a.get("class", "") for _, a in d.tags)
            with self.subTest(k=k):
                self.assertIn("i-os-" + k[3], classes)
                self.assertNotIn("i-os-" + ("win" if k[3] == "mac" else "mac"), classes)

    def test_unsigned_build_shows_beta_chip_never_signed_line(self):
        for k, r in self.cases(("shell",)):
            d = H.scan_dom(r.dom, ("i-hdr", "i-rail-trust"))
            with self.subTest(k=k):
                self.assertTrue("".join(d.text_in["i-hdr"]).strip())
                self.assertIn("m-chip-warn", r.dom)
                self.assertTrue("".join(d.text_in["i-rail-trust"]).strip())

    def test_support_live_by_default_and_one_soon_line_when_off(self):
        # D-05: WhatsApp support is live: the promise line, no "coming soon"; support.url absent: copy only + ONE line
        for k, r in self.cases(("shell", "nosupport")):
            with self.subTest(k=k):
                if k[0] == "shell":
                    self.assertEqual(r.dom.count("m-support-promise"), 1)
                    self.assertEqual(r.dom.count("m-soonline"), 0)
                else:
                    self.assertEqual(r.dom.count("m-support-promise"), 0)
                    self.assertEqual(r.dom.count("m-soonline"), 1)

    def test_plural_picks_the_arabic_dual(self):
        # the demo shows i04.amber.fonts with n = 2 through I.plural: Arabic has a .two form, English uses {n}
        for k, r in self.cases(("shell",)):
            text = "".join(H.scan_dom(r.dom).body_text)
            with self.subTest(k=k):
                if k[1] == "ar":
                    self.assertIn("خطين ", text)  # «خطين »
                else:
                    self.assertIn("2 fonts are in use", text)

    # ---- hostile data renders as inert text ----
    def test_hostile_path_is_inert_text(self):
        for k, r in self.cases(("hostile",)):
            d = H.scan_dom(r.dom, ("i-path", "i-monobox", "i-step-name"))
            with self.subTest(k=k):
                imgs = [a for t, a in d.tags if t == "img"]
                self.assertTrue(imgs)
                for a in imgs:
                    self.assertTrue(a.get("src", "").startswith("vendor/brand/"), a)
                for t, a in d.tags:
                    bad = [n for n in a if n.lower().startswith("on")]
                    self.assertEqual(bad, [], (t, a))
                for cls in ("i-path", "i-monobox", "i-step-name"):
                    text = "".join(d.text_in[cls])
                    self.assertIn(HOSTILE_HTML, text, cls)
                    self.assertEqual(sorted(set(text) & BIDI_CONTROLS), [], f"bidi control left in {cls}")
                    self.assertIn("[U+202E]", text, cls)

    def test_path_field_stays_one_line(self):
        # the field is 32 px high and cuts at its end: no break opportunity inside it (Chrome breaks at <wbr> even
        # under white-space: nowrap, which drew a long hostile path as three clipped lines)
        for k, r in self.cases(("shell", "hostile")):
            fields = re.findall(r'<div class="i-path i-clip"[^>]*>(.*?)</div>', r.dom, re.S)
            with self.subTest(k=k):
                self.assertTrue(fields)
                for f in fields:
                    self.assertNotIn("<wbr>", f)

    def test_hostile_name_is_its_own_isolate(self):
        # a name from data sits in its own bidi isolate (dir=auto), so an Arabic line never reorders its brackets
        for k, r in self.cases(("hostile",)):
            d = H.scan_dom(r.dom, ("m-data",))
            with self.subTest(k=k):
                self.assertIn(HOSTILE_HTML, "".join(d.text_in["m-data"]))
                self.assertTrue(any(t == "bdi" and "m-data" in a.get("class", "") and a.get("dir") == "auto"
                                    for t, a in d.tags))

    def test_hostile_text_never_reorders_anywhere(self):
        for k, r in self.cases(("hostile",)):
            d = H.scan_dom(r.dom)
            body = "".join(d.body_text)
            with self.subTest(k=k):
                self.assertEqual(sorted(set(body) & {"‪", "‫", "‭", "‮"}), [])

    # ---- the detectors are not vacuous ----
    def test_detector_catches_a_csp_violation(self):
        r = self.R[("csp-probe", "en", 760, "mac")]
        self.assertIsNotNone(r.raw_check, r.log[-2000:])
        self.assertNotEqual(r.check.get("csp"), "0")
        self.assertTrue(r.console_csp)

    def test_detector_catches_missing_key_and_icon(self):
        r = self.R[("missing", "en", 760, "mac")]
        self.assertIn("no.such.key", r.check.get("missing", ""))
        self.assertIn("icon:no-such-icon@16", r.check.get("missing", ""))

    def test_detector_catches_missing_fonts(self):
        r = self.R[("nofonts", "ar", 760, "mac")]
        self.assertIsNotNone(r.raw_check, r.log[-2000:])
        self.assertEqual(r.check.get("fonts"), "fallback")


if __name__ == "__main__":
    unittest.main()
