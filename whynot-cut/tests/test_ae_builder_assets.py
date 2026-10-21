# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""ae_builder.generate and the client's assets (review 0d84730 P3-4, P3-5).

P3-4: the logo and the images the build script hands After Effects come from the asset manifest read through
`client_db.load(paths, ...)`: root-relative values become absolute paths under the client root (a mutant that reads
the wrong folder falls back to an empty manifest and the logo silently vanishes).
P3-5: an asset file that is missing (or is not a regular file) is a warning in the result, one English and one Egyptian
Arabic line naming the asset's role and its path relative to the client (never an absolute path from outside); the
build itself still succeeds. Which paths count as inside the client is client_db's call (rel_under), not ae_builder's.
Run:  bash tools/test.sh -p test_ae_builder_assets.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import ae_builder, common  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402

LOGO_D = "output/client_database/derivatives/logo.png"
PHOTO_D = "output/client_database/derivatives/photo.png"
ARABIC = re.compile("[؀-ۿ]")


def nh_data(jsx: Path) -> dict:
    text = jsx.read_text(encoding="utf-8")
    start = text.index("var WNC_DATA = ") + len("var WNC_DATA = ")
    return json.JSONDecoder().raw_decode(text[start:])[0]


class TestAeBuilderAssets(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aeassets_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "Client عميل"
        for d in ("assets", "data"):
            (self.root / d).mkdir(parents=True)
        write_json(self.root / common.CLIENT_PROFILE_REL / "sequence-settings.json",
                   {"general": {"timebase": 30, "ntsc": True}})
        self.p = Paths(self.root, "V1")
        self.p.ensure_project()
        self.root = self.p.root                       # Paths resolves it
        self.events = [{"event_id": "GFX_001", "template": "glass_card", "start_frame": 0, "end_frame": 48,
                        "params": {"image": "assets/photo.jpg"}}]

    def manifest(self, logo=LOGO_D, photo=PHOTO_D):
        write_json(self.p.client_db / "asset-manifest.json", {"assets": [
            {"rel": "assets/Logo.png", "category": "logo", "file": "assets/Logo.png", "display_derivative": logo},
            {"rel": "assets/photo.jpg", "category": "photo", "file": "assets/photo.jpg", "display_derivative": photo}]})

    def put(self, *rels):
        for rel in rels:
            f = self.root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"\x89PNG")

    def build(self):
        write_json(self.p.p("01_analysis/timeline-spec.json"),
                   {"fps": 30000 / 1001, "duration_frames": 240, "events": self.events, "main_segments": []})
        with common.use_context(common.Context(self.p.root)):
            ctx_fps = common.seq_fps()
            res = ae_builder.generate(self.p)
        self.assertAlmostEqual(res["fps"], ctx_fps, places=6)
        self.assertTrue(Path(res["jsx"]).is_file())    # the build script is written whatever is missing
        return res, nh_data(Path(res["jsx"]))

    def asset_warnings(self, res):
        return [w for w in res["warnings"] if "After Effects" in w or ARABIC.search(w)]

    def assert_one_pair(self, res, role_en, role_ar, shown):
        ws = self.asset_warnings(res)
        en = [w for w in ws if not ARABIC.search(w)]
        ar = [w for w in ws if ARABIC.search(w)]
        self.assertEqual((len(en), len(ar)), (1, 1), res["warnings"])
        self.assertIn(role_en, en[0])
        self.assertIn(role_ar, ar[0])
        for w in (en[0], ar[0]):
            self.assertIn(shown, w)
            self.assertNotIn(str(self.tmp), w)                         # never an absolute path
            self.assertNotIn(str(self.tmp).replace("\\", "/"), w)

    # ------------------------------------------------------------------ P3-4
    def test_logo_and_image_paths_are_absolute_under_the_client(self):
        self.manifest()
        self.put(LOGO_D, PHOTO_D)
        res, data = self.build()
        logo, img = data["logo"], data["events"][0]["params"]["image_path"]
        self.assertEqual(Path(logo), self.root / LOGO_D)
        self.assertEqual(Path(img), self.root / PHOTO_D)
        for v in (logo, img):
            self.assertTrue(Path(v).is_absolute(), v)
            Path(v).relative_to(self.root)                             # under the client root
        self.assertEqual(res["warnings"], [])                          # assets that exist: no warning

    # ------------------------------------------------------------------ P3-5
    def test_a_missing_logo_is_one_en_and_one_ar_warning(self):
        self.manifest()
        self.put(PHOTO_D)
        res, data = self.build()
        self.assertEqual(Path(data["logo"]), self.root / LOGO_D)       # still handed on: the JSX logs and skips it
        self.assert_one_pair(res, "logo", "اللوجو", LOGO_D)
        self.assertNotIn("photo", " ".join(res["warnings"]))

    def test_a_missing_image_is_one_en_and_one_ar_warning(self):
        self.manifest()
        self.put(LOGO_D)
        self.events.append(dict(self.events[0], event_id="GFX_002", start_frame=60, end_frame=90))   # same image twice
        res, _ = self.build()
        self.assert_one_pair(res, "image", "الصورة", PHOTO_D)
        self.assertNotIn("logo", " ".join(res["warnings"]))

    def test_an_image_not_in_the_manifest_is_checked_too(self):
        self.manifest()
        self.put(LOGO_D, PHOTO_D)
        self.events[0]["params"]["image"] = "assets/new/pic.png"
        res, _ = self.build()
        self.assert_one_pair(res, "image", "الصورة", "assets/new/pic.png")

    def test_a_folder_is_not_a_file(self):
        self.manifest()
        self.put(PHOTO_D)
        (self.root / LOGO_D).mkdir(parents=True)
        res, _ = self.build()
        self.assert_one_pair(res, "logo", "اللوجو", LOGO_D)

    def test_no_logo_in_the_manifest_is_not_this_warning(self):
        """No logo at all is the needs-you `logo` item's business (client database), not a missing file."""
        write_json(self.p.client_db / "asset-manifest.json", {"assets": []})
        self.events = []
        res, data = self.build()
        self.assertIsNone(data["logo"])
        self.assertEqual(res["warnings"], [])

    def test_a_missing_file_outside_the_client_never_shows_its_absolute_path(self):
        outside = self.tmp / "Other Client" / "derivatives" / "logo.png"
        self.manifest(logo=str(outside))
        self.put(PHOTO_D)
        res, _ = self.build()
        self.assert_one_pair(res, "logo", "اللوجو", "logo.png")       # the name only: client_db says it is not ours

    def test_a_missing_file_through_a_junction_shows_the_client_relative_path(self):
        if os.name != "nt":
            self.skipTest("Windows junctions")
        target = self.tmp / "elsewhere"
        target.mkdir()
        link = self.root / "assets" / "junc"
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        if r.returncode:
            self.skipTest("mklink /J failed here")
        self.addCleanup(os.rmdir, link)                                # the link only, before the tree goes
        self.manifest(logo="assets/junc/logo.png")
        self.put(PHOTO_D)
        res, data = self.build()
        self.assert_one_pair(res, "logo", "اللوجو", "assets/Logo.png")    # refused by load: its manifest entry
        self.assertIsNone(data["logo"])
        self.assertTrue(target.is_dir())

    # ------------------------------------------------------------------ review c84f652 P2: only the client's own files
    def other_client(self, name: str) -> Path:
        f = self.tmp / "Other Client" / "derivatives" / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"OTHER CLIENT")
        return f

    def test_another_clients_logo_is_never_handed_on(self):
        logo = self.other_client("logo.png")
        self.manifest(logo=str(logo))
        self.put(PHOTO_D)
        res, data = self.build()
        self.assertIsNone(data["logo"])
        self.assert_one_pair(res, "logo", "اللوجو", "logo.png")
        self.assertIn("outside the client folder", " ".join(res["warnings"]))
        self.assertIn("برّه فولدر العميل", " ".join(res["warnings"]))
        self.assertNotIn("Other Client", json.dumps(data))

    def test_another_clients_image_is_never_handed_on(self):
        photo = self.other_client("photo.png")
        self.manifest(photo=str(photo))
        self.put(LOGO_D)
        res, data = self.build()
        self.assertIsNone(data["events"][0]["params"]["image_path"])
        self.assert_one_pair(res, "image", "الصورة", "photo.png")
        self.assertNotIn("Other Client", json.dumps(data))

    def test_a_plan_image_outside_the_client_is_never_handed_on(self):
        self.other_client("pic.png")
        self.manifest()
        self.put(LOGO_D, PHOTO_D)
        self.events[0]["params"]["image"] = "../Other Client/derivatives/pic.png"
        res, data = self.build()
        self.assertIsNone(data["events"][0]["params"]["image_path"])       # the plan's own words stay as written
        self.assert_one_pair(res, "image", "الصورة", "pic.png")


class TestPsBuilderAssets(unittest.TestCase):
    """ps_builder (review c84f652 P2): a Photoshop job's image and the logo are the client's own files or nothing."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="psassets_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "Client عميل"
        for d in ("assets", "data"):
            (self.root / d).mkdir(parents=True)
        self.p = Paths(self.root, "V1")
        self.p.ensure_project()
        self.root = self.p.root

    def generate(self, logo_file: str, image_file: str):
        from lib import ps_builder
        write_json(self.p.client_db / "asset-manifest.json", {"assets": [
            {"rel": "assets/Logo.png", "category": "logo", "file": logo_file, "display_derivative": None},
            {"rel": "assets/photo.jpg", "category": "photo", "file": image_file, "display_derivative": None}]})
        write_json(self.p.p("01_analysis/edit-decisions.json"), {"global": {"photoshop_jobs": [
            {"id": "PS1", "image": "assets/photo.jpg", "headline": "عنوان"}]}})
        with common.use_context(common.Context(self.p.root)):
            res = ps_builder.generate(self.p)
        text = Path(res["jsx"]).read_text(encoding="utf-8")
        start = text.index("var WNC_PS = ") + len("var WNC_PS = ")
        return res, json.JSONDecoder().raw_decode(text[start:])[0]

    def test_the_clients_own_files_are_handed_on(self):
        for rel in ("assets/Logo.png", "assets/photo.jpg"):
            (self.root / rel).write_bytes(b"own")
        res, data = self.generate("assets/Logo.png", "assets/photo.jpg")
        self.assertEqual(res["errors"], [])
        self.assertEqual(Path(data["logo"]), self.root / "assets/Logo.png")
        self.assertEqual(Path(data["jobs"][0]["image"]), self.root / "assets/photo.jpg")

    def test_another_clients_files_are_never_handed_on(self):
        other = self.tmp / "Other Client"
        other.mkdir()
        for n in ("logo.png", "photo.jpg"):
            (other / n).write_bytes(b"OTHER CLIENT")
        res, data = self.generate(str(other / "logo.png"), str(other / "photo.jpg"))
        self.assertIsNone(data["logo"])
        self.assertEqual(len(res["errors"]), 1, res["errors"])
        self.assertIn("PS1", res["errors"][0])
        self.assertIn("outside the client folder", res["errors"][0])
        self.assertNotIn("Other Client", json.dumps(data))


class TestPreviewsAndPublishAssets(unittest.TestCase):
    """previews (stills) and publish (thumbnails) (review c84f652 P2): the logo and a manifest image are the client's
    own files or nothing, for drawing and for the stills' hash alike."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pvassets_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "Client عميل"
        for d in ("assets", "data"):
            (self.root / d).mkdir(parents=True)
        self.p = Paths(self.root, "V1")
        self.p.ensure_project()
        self.root = self.p.root
        self.other = self.tmp / "Other Client" / "logo.png"
        self.other.parent.mkdir(parents=True)
        self.other.write_bytes(b"OTHER CLIENT")
        (self.root / "assets" / "Logo.png").write_bytes(b"own")

    def test_the_logo_and_images_drawn_and_hashed_are_the_clients_own(self):
        from lib import client_db, previews
        own = {"rel": "assets/Logo.png", "category": "logo", "file": "assets/Logo.png",
               "display_derivative": "assets/Logo.png"}
        bad = {"rel": "assets/Other.png", "category": "logo", "file": str(self.other),
               "display_derivative": str(self.other)}
        for first, want in ((own, self.root / "assets" / "Logo.png"), (bad, None)):
            with self.subTest(logo=first["display_derivative"]):
                man = client_db.resolved(self.root, "asset-manifest.json", {"assets": [json.loads(json.dumps(first))]})
                got = previews._client_logo(self.p, man)
                self.assertEqual(Path(got) if got else None, want)
                with common.use_context(common.Context(self.p.root)):
                    shared = previews._shared_inputs(self.p, {}, man)
                self.assertEqual(shared["logo"][1] is None, want is None)
                self.assertNotIn("Other Client", json.dumps(shared))
                assets = {a["rel"]: a for a in man["assets"]}
                img = previews._image_file(self.p, assets, first["rel"])
                self.assertEqual(Path(img) if img else None, want)
        self.assertIsNone(previews._image_file(self.p, {}, "../Other Client/logo.png"))     # a plan path outside

    def test_the_stills_draw_through_the_same_helpers(self):
        """render_all draws the logo and images it hashes (the helpers above): never a raw manifest value."""
        import inspect
        from lib import previews
        src = inspect.getsource(previews.render_all)
        self.assertIn("logo = _client_logo(paths, man)", src)
        self.assertIn('p["image_path"] = _image_file(paths, assets, p["image"])', src)
        self.assertNotIn('a["display_derivative"]', src)

    def test_publish_takes_the_logo_through_the_same_check(self):
        src = (SK / "engine" / "reel" / "lib" / "publish.py").read_text(encoding="utf-8")
        self.assertIn("client_db.inside_file(", src)
        self.assertNotRegex(src, r'logo = next\(\(a\.get\("display_derivative"\) for a')


if __name__ == "__main__":
    unittest.main()
