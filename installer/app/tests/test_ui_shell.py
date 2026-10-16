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
import sys
import tempfile
import unittest

import _harness as H

LANGS = ("en", "ar")
WIDTHS = (760, 640)
OSES = ("mac", "win")
NEUTRALISED = ({chr(c) for c in range(0x00, 0x20)} - {"\t"}) | {chr(c) for c in range(0x7F, 0xA0)} | set(
    "\u061c\u200b\u200e\u200f\u2028\u2029\u202a\u202b\u202c\u202d\u202e\u2060\u2066\u2067\u2068\u2069\ufeff\ue000\ue001")
BIDI_CONTROLS = NEUTRALISED
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
        cls.stage_prod = H.stage(cls.work / "stage-prod", production=True)
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
        for lang in LANGS:
            for fx in ("order", "plural"):
                jobs[(fx, lang, 760, "mac")] = (cls.stage, {"demo": "shell", "fixture": fx, "lang": lang}, 760, "mac")
        jobs[("tt-probe", "en", 760, "mac")] = (cls.stage, {"demo": "shell", "fixture": "tt-probe", "lang": "en"}, 760, "mac")
        jobs[("remount", "en", 760, "mac")] = (cls.stage, {"demo": "shell", "fixture": "remount", "lang": "en"}, 760, "mac")
        for lang in LANGS:
            jobs[("prod-idle", lang, 760, "mac")] = (cls.stage_prod, {"lang": lang}, 760, "mac")
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            futs = {k: ex.submit(H.render, cls.exe, st, cls.work, q, w, os_kind, "-".join(map(str, k)), delta=cls.delta)
                    for k, (st, q, w, os_kind) in jobs.items()}
            cls.R = {k: f.result() for k, f in futs.items()}
        retried = sorted(str(k) for k, r in cls.R.items() if len(r.attempts) > 1)
        print(f"[ui-shell] {len(cls.R)} pages, dumped again with a longer budget: {len(retried)} {retried}", file=sys.stderr)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def cases(self, kinds=("shell", "hostile", "idle", "nosupport", "order", "plural", "remount", "prod-idle")):
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
        for k, r in self.cases(("shell",)):
            with self.subTest(k=k):
                self.assertIn("m-btn-danger", r.dom, "the demo must carry a danger button for this check")
                self.assertIn("m-btn-destructive", r.dom, "the demo must carry a destructive button for this check")
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
        # D-04: an unsigned build never claims to be signed: the i00.signed line is absent in both languages, the
        # honest test-build line and the beta chip are present
        S = H.strings()
        flat = lambda t: " ".join(t.replace(" ", " ").split())  # the no-orphan rule binds the last words with NBSP
        for k, r in self.cases(("shell", "idle", "prod-idle")):
            d = H.scan_dom(r.dom, ("i-hdr", "i-rail-trust"))
            text = flat("".join(d.body_text))
            with self.subTest(k=k):
                for lang in ("en", "ar"):
                    self.assertNotIn(flat(S[lang]["i00.signed"]), text)
                self.assertIn(flat(S[k[1]]["i00.unsigned"]), flat("".join(d.text_in["i-rail-trust"])))
                self.assertIn(flat(S[k[1]]["i00.internal"]), flat("".join(d.text_in["i-hdr"])))
                self.assertIn("m-chip-warn", r.dom)

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

    def test_hostile_path_title_is_inert(self):
        for k, r in self.cases(("hostile",)):
            titles = [a.get("title", "") for t, a in H.scan_dom(r.dom).tags if "i-path" in (a.get("class") or "").split()]
            with self.subTest(k=k):
                self.assertTrue(titles)
                for t in titles:
                    self.assertEqual(sorted(set(t) & NEUTRALISED), [])
                    self.assertIn("[U+202E]", t)
                    self.assertIn(HOSTILE_HTML, t)

    def test_string_var_cannot_forge_a_placeholder(self):
        # a data STRING var next to a Node var: "\uE0000\uE001" in the string must not pull the Node in again
        for k, r in self.cases(("hostile",)):
            d = H.scan_dom(r.dom, ("probe-var",))
            text = "".join(d.text_in["probe-var"])
            with self.subTest(k=k):
                self.assertIn("[U+E000]0[U+E001]", text)
                self.assertEqual(text.count("NODEVAR"), 1, text)
                self.assertEqual(sorted(set(text) & NEUTRALISED), [])

    def test_every_data_helper_neutralises(self):
        for k, r in self.cases(("hostile",)):
            d = H.scan_dom(r.dom, ("probe-helper",))
            text = "".join(d.text_in["probe-helper"])
            with self.subTest(k=k):
                self.assertTrue(text)
                self.assertEqual(sorted(set(text) & NEUTRALISED), [])
                for code in ("[U+2029]", "[U+0085]", "[U+001C]", "[U+000B]", "[U+200F]", "[U+FEFF]", "[U+200B]"):
                    self.assertIn(code, text)
                self.assertIn("\u200d", text, "ZWJ is left alone (Arabic and emoji need it)")

    def test_data_keeps_its_drawn_order_in_arabic_and_english(self):
        # F1: measured on screen (a Range per character), not only in the DOM text
        for k, r in self.cases(("order",)):
            m = re.search(r'<meta name="order" content="([^"]*)"', r.dom)
            with self.subTest(k=k):
                self.assertIsNotNone(m, r.log[-1500:])
                pairs = dict(x.split("=", 1) for x in m.group(1).split())
                self.assertGreaterEqual(len(pairs), 100)
                self.assertEqual(sorted(p for p, v in pairs.items() if v != "intact"), [])

    def test_plural_follows_the_cldr_category(self):
        # F5: Intl.PluralRules picks key.zero|one|two|few|many|other, falling back to the base key when a form is missing
        want = {"ar": {"0": "", "1": ".one", "2": ".two", "3": "", "10": "", "11": "", "100": "", "s2": ".two"},
                "en": {"0": "", "1": ".one", "2": "", "3": "", "10": "", "11": "", "100": "", "s2": ""}}
        S = H.strings()
        for k, r in self.cases(("plural",)):
            m = re.search(r'<meta name="plural" content="([^"]*)"', r.dom)
            with self.subTest(k=k):
                self.assertIsNotNone(m, r.log[-1500:])
                got = dict(x.split("=", 1) for x in m.group(1).split())
                for n, form in want[k[1]].items():
                    key = "i04.amber.fonts" + form
                    self.assertIn(key, S[k[1]])
                    self.assertEqual(got[n], key, n)

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

    def test_trusted_types_blocks_a_computed_html_sink(self):
        r = self.R[("tt-probe", "en", 760, "mac")]
        self.assertIsNotNone(r.raw_check, r.log[-2000:])
        m = re.search(r'<meta name="tt" content="([^"]*)"', r.dom)
        self.assertIsNotNone(m, r.log[-2000:])
        self.assertEqual(m.group(1), "blocked")
        self.assertNotIn('<img src="x"', r.dom)
        self.assertNotEqual(r.check.get("csp"), "0")
        self.assertTrue(any("trusted" in ln.lower() for ln in r.console_csp + r.log.splitlines()))

    def test_remount_leaves_one_fresh_self_check(self):
        r = self.R[("remount", "en", 760, "mac")]
        self.assertEqual(r.dom.count('name="mock-check"'), 1, r.dom[:3000])
        self.assertEqual(r.check.get("state"), "shell:remount")
        self.assertEqual(r.check.get("missing"), "")

    def test_production_bundle_has_no_demo_or_fixtures(self):
        self.assertFalse((self.stage_prod / "js" / "demo.js").exists())
        self.assertFalse((self.stage_prod / "fixtures").exists())
        for lang in LANGS:
            r = self.R[("prod-idle", lang, 760, "mac")]
            with self.subTest(lang=lang):
                self.assertEqual(r.check.get("state"), "idle")

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
