"""3.0 Addendum G12 (pulled forward as a PREVIEW): `tools/release.py handoff`, the Windows + Mac hand-off folders.

Every test builds a tiny temp git repo shaped like the real one (plugin.json, components.json, installer, guide PDF,
LOCKED-AREAS.md, MAC-INBOX.md, PROGRESS.md, gitignored .ccx / .zxp in whynot-cut/adobe/) and runs the handoff on it
into a temp folder; nothing is cloned from the real repo and no ffmpeg runs (the sample client maker is injected).
The real LOCKED-AREAS.md / MAC-INBOX.md at the repo root are checked to exist and parse.
Run:  tools/test.sh -k handoff   (or python -m unittest discover -s whynot-cut/tests -p test_release_handoff.py)
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
REPO = SK.parent
RELEASE = REPO / "tools" / "release.py"
GIT = shutil.which("git")
ORIGIN = "https://github.com/example-org/example-repo.git"


def _load_release():
    spec = importlib.util.spec_from_file_location("whynot_release_handoff", RELEASE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rel = _load_release()


def git(cwd, *args) -> str:
    return subprocess.run([GIT, "-c", "user.name=T", "-c", "user.email=t@example.com", "-c", "core.autocrlf=false",
                           "-c", "commit.gpgsign=false", *args], cwd=str(cwd), check=True,
                          capture_output=True, text=True).stdout.strip()


def make_zip(path: Path, members: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for n, data in members.items():
            z.writestr(n, data)


_TEMPLATE = {}


def _template_repo() -> Path:
    """Built once per run (git is slow on a loaded Windows machine); every test gets a copy."""
    if "path" not in _TEMPLATE:
        _TEMPLATE["td"] = tempfile.TemporaryDirectory()
        _TEMPLATE["path"] = _build_template(Path(_TEMPLATE["td"].name) / "template")
    return _TEMPLATE["path"]


def _build_template(root: Path) -> Path:
    root.mkdir(parents=True)
    files = {
        "README.md": "# fixture\n",
        ".claude-plugin/marketplace.json": json.dumps({"name": "fixture", "plugins": []}),
        "whynot-cut/.claude-plugin/plugin.json": json.dumps({"name": "whynot-cut", "version": "9.9.9"}),
        "whynot-cut/README.md": "plugin readme\n",
        "whynot-cut/bin/reel": "#!/bin/sh\necho reel\n",
        "whynot-cut/setup/components.json": json.dumps({
            "bridge": {"cep": {"bundle": "<release>", "zxp": "<release>", "sha256": "<release>"},
                       "uxp": {"version": "<release>", "ccx": "<release>", "sha256": "<release>"}}}, indent=2) + "\n",
        "whynot-cut/installer/install.ps1": "# install.ps1 fixture\n",
        "whynot-cut/installer/install.sh": "#!/bin/bash\n# install.sh fixture\n",
        "whynot-cut/installer/README.md": "# installer readme fixture\n",
        "whynot-cut/docs/WhyNot-Cut-Guide-AR.pdf": "%PDF-1.4 fixture guide\n",
        "whynot-cut/profiles/_template/profile.json": "{}\n",
        "whynot-cut/profiles/example-clinic/profile.json": json.dumps({"id": "example-clinic"}),
        "whynot-cut/adobe/.gitignore": "*.ccx\n*.zxp\n",
        "whynot-cut/evals/_fixtures/example-clinic.sh": "# fixture generator stand-in\n",
        "LOCKED-AREAS.md": (REPO / "LOCKED-AREAS.md").read_text(encoding="utf-8"),
        "MAC-INBOX.md": (REPO / "MAC-INBOX.md").read_text(encoding="utf-8"),
        "PROGRESS.md": ("## Phase table\n\n| Phase | State | Tag | Verified |\n|---|---|---|---|\n"
                        "| 0 Baseline | **passed** | v9.9.9-p0 | Verified: x |\n"
                        "| 1 Ship-blockers | **passed** | v9.9.9-p1 | Verified: y |\n"
                        "| 2 Next | **in progress** | | |\n"),
        ".gitignore": "node_modules/\n",
    }
    for rel_path, text in files.items():
        p = root / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))
    git(root, "init", "-q", "-b", "release/3.0")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "first")
    (root / "README.md").write_text("# fixture v2\n", encoding="utf-8")
    git(root, "commit", "-q", "-am", "second")
    git(root, "remote", "add", "origin", ORIGIN)
    # the built (gitignored) Adobe artefacts
    make_zip(root / "whynot-cut/adobe/WhyNotCut-Premiere-9.9.9.ccx", {"manifest.json": "{}"})
    make_zip(root / "whynot-cut/adobe/WhyNotCut-Bridge-9.9.9.zxp",
             {"mimetype": "application/vnd.adobe.air-ucf-package+zip", "CSXS/manifest.xml": "<x/>",
              "META-INF/signatures.xml": "<signatures/>"})
    return root


def make_repo(root: Path, signed_zxp=True, extra_tracked=None, origin=ORIGIN) -> Path:
    """A tiny repo shaped like WhyNotCut: branch release/3.0, two commits, origin set, .ccx + signed .zxp built."""
    shutil.copytree(_template_repo(), root)
    if not signed_zxp:
        make_zip(root / "whynot-cut/adobe/WhyNotCut-Bridge-9.9.9.zxp",
                 {"mimetype": "application/vnd.adobe.air-ucf-package+zip", "CSXS/manifest.xml": "<x/>"})
    if origin is None:
        git(root, "remote", "remove", "origin")
    elif origin != ORIGIN:
        git(root, "remote", "set-url", "origin", origin)
    if extra_tracked:
        for rel_path, text in extra_tracked.items():
            p = root / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "extra")
    return root


def fake_sample(repo_dir: Path, dest: Path):
    """Stand-in for the example-clinic fixture: a fictional client folder (no ffmpeg)."""
    (dest / "data" / "Raw").mkdir(parents=True)
    (dest / "data" / "Raw" / "C0239.MP4").write_bytes(b"\x00fake")
    (dest / ".whynot-client").write_text('{"whynot_client": 1}\n', encoding="utf-8")
    (dest / "assets").mkdir()
    (dest / "assets" / "brand-brief.md").write_text("# Example Clinic (fictional)\n", encoding="utf-8")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@unittest.skipUnless(GIT, "git not on PATH")
class HandoffCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.out = self.tmp / "Final Out"

    def tearDown(self):
        self._td.cleanup()

    def run_handoff(self, repo, **kw):
        kw.setdefault("label", "PREVIEW-9.9.9-p3")
        kw.setdefault("preview", True)
        kw.setdefault("sample_maker", fake_sample)
        kw.setdefault("log", lambda *a, **k: None)
        return rel.handoff(repo, self.out, **kw)


_SHARED = {}


def tearDownModule():
    for d in (_SHARED, _TEMPLATE):
        if "td" in d:
            d["td"].cleanup()


@unittest.skipUnless(GIT, "git not on PATH")
class SharedRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "summary" not in _SHARED:
            _SHARED["td"] = tempfile.TemporaryDirectory()
            tmp = Path(_SHARED["td"].name)
            _SHARED["repo"] = make_repo(tmp / "src")
            _SHARED["out"] = tmp / "Final Out"
            _SHARED["summary"] = rel.handoff(_SHARED["repo"], _SHARED["out"], label="PREVIEW-9.9.9-p3", preview=True,
                                             sample_maker=fake_sample, log=lambda *a, **k: None)
        cls.repo, cls.out, cls.summary = _SHARED["repo"], _SHARED["out"], _SHARED["summary"]


class TestLayout(SharedRun):
    """Read-only checks on ONE successful hand-off (shared: git is slow on a loaded machine)."""

    def test_layout(self):
        repo, summary = self.repo, self.summary
        win, mac = self.out / "Windows", self.out / "Mac"
        for name in ("whynot-cut-9.9.9.zip", "install.ps1", "install.sh", "README-installer.md",
                     "WhyNotCut-Premiere-9.9.9.ccx", "WhyNotCut-Bridge-9.9.9.zxp", "WhyNot-Cut-Guide-AR.pdf",
                     "README-AR.md", "checksums.txt"):
            self.assertTrue((win / name).is_file(), name)
        self.assertTrue((mac / "repo" / ".git").is_dir())
        self.assertTrue((mac / "sample-client" / "data" / "Raw" / "C0239.MP4").is_file())
        for name in ("START-HERE.md", "دليل-الماك.md"):
            self.assertTrue((mac / name).is_file(), name)
        self.assertTrue((self.out / "WHAT-WORKS-NOW-AR.md").is_file())
        self.assertTrue((self.out / "LABEL.txt").is_file())
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         sorted(["Windows", "Mac", "WHAT-WORKS-NOW-AR.md", "LABEL.txt"]))
        self.assertFalse(self.out.with_name(self.out.name + ".new").exists())
        self.assertFalse(self.out.with_name(self.out.name + ".prev").exists())

        head = git(repo, "rev-parse", "HEAD")
        label = (self.out / "LABEL.txt").read_text(encoding="utf-8")
        self.assertIn("PREVIEW-9.9.9-p3", label)
        self.assertIn(head, label)
        self.assertRegex(label, r"\d{4}-\d{2}-\d{2}")
        self.assertEqual(summary["sha"], head)

        zip_sha = sha(win / "whynot-cut-9.9.9.zip")
        readme = (win / "README-AR.md").read_text(encoding="utf-8")
        self.assertIn("irm https://dl.thewhynot.ai/install.ps1 | iex", readme)
        self.assertIn("-Source", readme)
        self.assertIn("-SourceSha256 " + zip_sha, readme)
        self.assertIn("whynot-cut-9.9.9.zip", readme)

        start = (mac / "START-HERE.md").read_text(encoding="utf-8")
        self.assertTrue(start.lstrip().startswith("# "))
        self.assertIn("PREVIEW", start.split("## ")[0])          # the banner is at the top, before any section
        self.assertIn("p3", start.split("## ")[0])
        for must in ("mac/dev", "MAC-INBOX.md", "LOCKED-AREAS.md", "whynot-cut/installer/**", "guide-ar/**",
                     "H13", "bash tools/test.sh", "mac-test-report.md", "Never push to `release/3.0`",
                     "gh auth login", "PlayerDebugMode", "install.sh", head):
            self.assertIn(must, start, must)
        self.assertNotIn("mac/preview", start)
        self.assertNotIn("{{", start)
        guide = (mac / "دليل-الماك.md").read_text(encoding="utf-8")
        self.assertIn("gh auth login", guide)
        self.assertIn("Read ../START-HERE.md and do it", guide)
        self.assertIn("https://claude.ai/install.sh", guide)
        what = (self.out / "WHAT-WORKS-NOW-AR.md").read_text(encoding="utf-8")
        self.assertIn("v9.9.9-p1", what)                          # passed phases come from PROGRESS.md
        self.assertIn("(Next)", what)                             # the phase in progress is named
        self.assertNotIn("{{", what + guide + readme)

    def test_zip_holds_the_plugin_and_pins_the_artefacts(self):
        repo = self.repo
        win = self.out / "Windows"
        with zipfile.ZipFile(win / "whynot-cut-9.9.9.zip") as z:
            names = z.namelist()
            comp = json.loads(z.read("whynot-cut-marketplace/whynot-cut/setup/components.json"))
            reel_mode = z.getinfo("whynot-cut-marketplace/whynot-cut/bin/reel").external_attr >> 16
        self.assertIn("whynot-cut-marketplace/whynot-cut/.claude-plugin/plugin.json", names)
        self.assertIn("whynot-cut-marketplace/whynot-cut/adobe/WhyNotCut-Premiere-9.9.9.ccx", names)
        self.assertEqual(comp["bridge"]["uxp"]["sha256"], sha(win / "WhyNotCut-Premiere-9.9.9.ccx"))
        self.assertEqual(comp["bridge"]["cep"]["sha256"], sha(win / "WhyNotCut-Bridge-9.9.9.zxp"))
        self.assertEqual(reel_mode & 0o777, 0o755)
        self.assertFalse([n for n in names if n.endswith(("PROGRESS.md", "LOCKED-AREAS.md", "MAC-INBOX.md"))])
        # the source repo's own components.json is untouched
        self.assertIn("<release>", (repo / "whynot-cut/setup/components.json").read_text(encoding="utf-8"))

    def test_checksums_match_every_file(self):
        win = self.out / "Windows"
        listed = {}
        for line in (win / "checksums.txt").read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            digest, name = line.split("  ", 1)
            listed[name] = digest
        files = {p.name for p in win.iterdir() if p.is_file() and p.name != "checksums.txt"}
        self.assertEqual(set(listed), files)
        for name, digest in listed.items():
            self.assertEqual(digest, sha(win / name), name)

    def test_generated_text_has_no_real_client_name(self):
        toks = rel.real_client_tokens()
        hits = []
        for p in self.out.rglob("*"):
            if not p.is_file() or (self.out / "Mac" / "repo") in p.parents or p.suffix in (".zip", ".ccx", ".zxp",
                                                                                           ".pdf", ".MP4"):
                continue
            low = p.read_text(encoding="utf-8", errors="ignore").lower()
            hits += [(str(p), t) for t in toks if t in low]
        self.assertEqual(hits, [])

    def test_clone_has_history_branch_and_origin(self):
        repo = self.repo
        clone = self.out / "Mac" / "repo"
        self.assertEqual(git(clone, "remote", "get-url", "origin"), ORIGIN)
        self.assertEqual(git(clone, "rev-parse", "--abbrev-ref", "HEAD"), "release/3.0")
        self.assertEqual(git(clone, "rev-parse", "HEAD"), git(repo, "rev-parse", "HEAD"))
        self.assertEqual(git(clone, "rev-list", "--count", "HEAD"), "2")
        self.assertEqual(git(clone, "status", "--porcelain"), "")
        # no remote-tracking ref pretends GitHub already has the local commits (the first `git fetch` fills them)
        self.assertEqual(git(clone, "for-each-ref", "refs/remotes/origin"), "")
        # the gitignored artefacts are not cloned
        self.assertFalse(list((clone / "whynot-cut" / "adobe").glob("*.ccx")))


class TestUnsignedZxp(HandoffCase):
    def test_unsigned_zxp_is_excluded(self):
        repo = make_repo(self.tmp / "src", signed_zxp=False)
        summary = self.run_handoff(repo)
        win = self.out / "Windows"
        self.assertFalse(list(win.glob("*.zxp")))
        with zipfile.ZipFile(win / "whynot-cut-9.9.9.zip") as z:
            self.assertFalse([n for n in z.namelist() if n.endswith(".zxp")])
            comp = json.loads(z.read("whynot-cut-marketplace/whynot-cut/setup/components.json"))
        self.assertEqual(comp["bridge"]["cep"]["zxp"], "<release>")
        reasons = " ".join(e["why"] for e in summary["excluded"])
        self.assertIn("WhyNotCut-Bridge-9.9.9.zxp", " ".join(e["file"] for e in summary["excluded"]))
        self.assertIn("signatures.xml", reasons)
        self.assertIn("WhyNotCut-Bridge-9.9.9.zxp", (self.out / "LABEL.txt").read_text(encoding="utf-8"))

    def test_signed_check(self):
        z = self.tmp / "a.zxp"
        make_zip(z, {"META-INF/signatures.xml": "<s/>"})
        self.assertTrue(rel.zxp_signed(z))
        make_zip(z, {"mimetype": "x"})
        self.assertFalse(rel.zxp_signed(z))
        z.write_bytes(b"not a zip")
        self.assertFalse(rel.zxp_signed(z))




class TestSwap(HandoffCase):
    def test_overwrite_replaces_the_old_output(self):
        repo = make_repo(self.tmp / "src")
        self.out.mkdir()
        (self.out / "old.txt").write_text("old", encoding="utf-8")
        self.run_handoff(repo)
        self.assertFalse((self.out / "old.txt").exists())
        self.assertTrue((self.out / "LABEL.txt").is_file())
        self.assertFalse(self.out.with_name(self.out.name + ".prev").exists())
        self.assertFalse(self.out.with_name(self.out.name + ".new").exists())

    def test_prev_is_kept_until_the_new_output_is_in_place(self):
        repo = make_repo(self.tmp / "src")
        self.out.mkdir()
        (self.out / "old.txt").write_text("old", encoding="utf-8")
        prev, new = self.out.with_name(self.out.name + ".prev"), self.out.with_name(self.out.name + ".new")
        seen = []

        def rename(a, b):
            if Path(a) == new:
                seen.append(((prev / "old.txt").is_file(), new.is_dir(), self.out.exists()))
            os.replace(a, b)
        self.run_handoff(repo, rename=rename)
        self.assertEqual(seen, [(True, True, False)])

    def test_a_failed_swap_restores_the_old_output(self):
        repo = make_repo(self.tmp / "src")
        self.out.mkdir()
        (self.out / "old.txt").write_text("old", encoding="utf-8")
        new = self.out.with_name(self.out.name + ".new")

        def rename(a, b):
            if Path(a) == new:
                raise OSError("simulated: the folder is open in Explorer")
            os.replace(a, b)
        with self.assertRaises(rel.HandoffError):
            self.run_handoff(repo, rename=rename)
        self.assertEqual((self.out / "old.txt").read_text(encoding="utf-8"), "old")
        self.assertFalse(self.out.with_name(self.out.name + ".prev").exists())
        self.assertFalse(new.exists())

    def test_a_failed_build_leaves_the_old_output_alone(self):
        repo = make_repo(self.tmp / "src")
        self.out.mkdir()
        (self.out / "old.txt").write_text("old", encoding="utf-8")

        def broken(repo_dir, dest):
            raise RuntimeError("ffmpeg exploded")
        with self.assertRaises(Exception):
            self.run_handoff(repo, sample_maker=broken)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["old.txt"])
        self.assertFalse(self.out.with_name(self.out.name + ".new").exists())
        self.assertFalse(self.out.with_name(self.out.name + ".prev").exists())

    def test_a_leftover_prev_without_output_is_restored_first(self):
        """A run killed between the two renames leaves only <out>.prev: the next run treats it as the last good one."""
        repo = make_repo(self.tmp / "src")
        prev = self.out.with_name(self.out.name + ".prev")
        prev.mkdir()
        (prev / "old.txt").write_text("old", encoding="utf-8")
        new = self.out.with_name(self.out.name + ".new")

        def rename(a, b):
            if Path(a) == new:
                raise OSError("simulated")
            os.replace(a, b)
        with self.assertRaises(rel.HandoffError):
            self.run_handoff(repo, rename=rename)
        self.assertTrue((self.out / "old.txt").is_file())
        self.assertFalse(prev.exists())


class TestNoRealClientName(HandoffCase):
    def test_tokens_come_from_test_plugin(self):
        toks = rel.real_client_tokens()
        self.assertGreaterEqual(len(toks), 4)
        self.assertTrue(all(t == t.lower() for t in toks))

    def test_a_real_name_in_the_sample_is_refused(self):
        repo = make_repo(self.tmp / "src")
        token = rel.real_client_tokens()[-1]

        def leaky(repo_dir, dest):
            fake_sample(repo_dir, dest)
            (dest / "assets" / "note.md").write_text(f"client: {token}\n", encoding="utf-8")
        with self.assertRaises(rel.HandoffError) as cm:
            self.run_handoff(repo, sample_maker=leaky)
        self.assertIn("note.md", str(cm.exception))
        self.assertFalse(self.out.exists())


class TestDryRun(HandoffCase):
    def test_dry_run_writes_nothing(self):
        repo = make_repo(self.tmp / "src")
        before = sorted(str(p) for p in self.tmp.rglob("*"))
        lines = []
        summary = self.run_handoff(repo, dry_run=True, log=lambda *a, **k: lines.append(" ".join(map(str, a))))
        after = sorted(str(p) for p in self.tmp.rglob("*"))
        self.assertEqual(before, after)
        self.assertFalse(self.out.exists())
        self.assertTrue(summary["dry_run"])
        self.assertTrue(any("Windows" in ln for ln in lines))

    def test_cli_dry_run(self):
        repo = make_repo(self.tmp / "src")
        rc = rel.main(["handoff", "--out", str(self.out), "--repo", str(repo), "--preview", "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertFalse(self.out.exists())


class TestClone(HandoffCase):
    def test_credentials_in_the_origin_url_are_dropped(self):
        repo = make_repo(self.tmp / "src", origin="https://someone:ghp_secret@github.com/example-org/example-repo.git")
        self.run_handoff(repo)
        self.assertEqual(git(self.out / "Mac" / "repo", "remote", "get-url", "origin"), ORIGIN)

    def test_no_origin_is_refused(self):
        repo = make_repo(self.tmp / "src", origin=None)
        with self.assertRaises(rel.HandoffError):
            self.run_handoff(repo)
        self.assertFalse(self.out.exists())


class TestSecretScan(HandoffCase):
    def test_a_planted_env_file_is_refused(self):
        repo = make_repo(self.tmp / "src", extra_tracked={"whynot-cut/config/prod.env": "TOKEN=x\n"})
        with self.assertRaises(rel.HandoffError) as cm:
            self.run_handoff(repo)
        self.assertIn("prod.env", str(cm.exception))
        self.assertFalse(self.out.exists())
        self.assertFalse(self.out.with_name(self.out.name + ".new").exists())

    def test_scan_finds_every_kind(self):
        d = self.tmp / "tree"
        for f in (".env", "a/b.env", "k.pem", "k.key", "c.p12", "x/credentials.json", ".venv/pyvenv.cfg",
                  "adobe/node_modules/m/i.js", "out/renders/a.mp4", "whynot-cut/evals/results/r.json",
                  "ok/readme.md", "ok/keyboard.md", ".git/config"):
            p = d / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x", encoding="utf-8")
        found = rel.scan_secrets(d)
        self.assertEqual(sorted(found), sorted([".env", "a/b.env", "k.pem", "k.key", "c.p12", "x/credentials.json",
                                                ".venv", "adobe/node_modules", "out/renders",
                                                "whynot-cut/evals/results"]))


class TestSampleClientMaker(HandoffCase):
    def test_the_fixture_gets_the_engine_ffmpeg_and_the_four_steps(self):
        """The real maker sources the fixture and overrides its find_ffmpeg with the engine's ffmpeg (no real run)."""
        try:
            rel.find_bash()
        except rel.HandoffError:
            self.skipTest("no bash")
        repo = self.tmp / "clone"
        fx = repo / "whynot-cut" / "evals" / "_fixtures" / "example-clinic.sh"
        fx.parent.mkdir(parents=True)
        fx.write_text('make_clinic() { mkdir -p "$1"; echo "ff=$(find_ffmpeg) prof=$2" > "$1/calls.txt"; }\n'
                      'add_references() { echo refs >> "$1/calls.txt"; }\n'
                      'add_project() { echo "project $2" >> "$1/calls.txt"; }\n'
                      'add_episode_plan() { echo plan >> "$1/calls.txt"; }\n', encoding="utf-8")
        ff = self.tmp / "tools dir" / "ffmpeg-fake.exe"
        ff.parent.mkdir()
        ff.write_bytes(b"x")
        dest = self.tmp / "Mac" / "sample-client"
        dest.parent.mkdir()
        from unittest import mock
        with mock.patch.dict(os.environ, {"WHYNOT_FFMPEG": str(ff)}):
            rel.make_sample_client(repo, dest)
        calls = (dest / "calls.txt").read_text(encoding="utf-8").split("\n")
        self.assertEqual(calls[0], f"ff={ff.as_posix()} prof=profile")
        self.assertEqual(calls[1:4], ["refs", "project C0239", "plan"])


class TestPassedPhases(unittest.TestCase):
    TABLE = ("| Phase | State | Tag | Verified |\n|---|---|---|---|\n"
             "| 0 Baseline | **passed** | v9.9.9-p0 | x |\n"
             "| 1 Ship-blockers | | | |\n"
             "| 2 Engine | **in progress** | | |\n"
             "| 3 Plugin layer | | | |\n")

    def test_progress_rows(self):
        passed, active = rel.passed_phases(self.TABLE)
        self.assertEqual(passed, [("0", "Baseline", "v9.9.9-p0")])
        self.assertEqual(active, [("2", "Engine")])

    def test_a_gate_tag_counts_as_passed_when_progress_lags(self):
        """The committed PROGRESS.md can lag; the gate tag `v<version>-p<N>` is the record of a passed gate."""
        passed, active = rel.passed_phases(self.TABLE, tags=["v9.9.9-p0", "v9.9.9-p1", "v9.9.9-p2", "v2.2.1",
                                                             "v9.9.8-p3"], version="9.9.9")
        self.assertEqual(passed, [("0", "Baseline", "v9.9.9-p0"), ("1", "Ship-blockers", "v9.9.9-p1"),
                                  ("2", "Engine", "v9.9.9-p2")])
        self.assertEqual(active, [])


def make_dir_link(link: Path, target: Path) -> bool:
    """A directory junction (Windows, no admin needed) or symlink (elsewhere); False when the OS refuses."""
    try:
        if os.name == "nt":
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
            return r.returncode == 0 and link.exists()
        os.symlink(target, link, target_is_directory=True)
        return True
    except OSError:
        return False


class TestLinks(HandoffCase):
    """COORDINATION rule 15: no junction/symlink in the clone; the swap and every delete never follow a link."""

    def test_scan_finds_a_junction_and_does_not_walk_into_it(self):
        live = self.tmp / "live"
        (live / "inner").mkdir(parents=True)
        (live / "inner" / "x.env").write_text("x", encoding="utf-8")
        tree = self.tmp / "tree"
        tree.mkdir()
        if not make_dir_link(tree / "linked", live):
            self.skipTest("cannot create a directory link here")
        self.assertEqual(rel.scan_links(tree), ["linked"])
        self.assertEqual(rel.scan_secrets(tree), [])          # never walked through the link

    def test_rmtree_refuses_a_link_and_leaves_the_target(self):
        live = self.tmp / "live"
        live.mkdir()
        (live / "keep.txt").write_text("keep", encoding="utf-8")
        link = self.tmp / "out.prev"
        if not make_dir_link(link, live):
            self.skipTest("cannot create a directory link here")
        with self.assertRaises(rel.HandoffError):
            rel._rmtree(link)
        self.assertTrue((live / "keep.txt").is_file())

    def test_a_linked_output_folder_is_refused(self):
        repo = make_repo(self.tmp / "src")
        live = self.tmp / "live"
        live.mkdir()
        (live / "keep.txt").write_text("keep", encoding="utf-8")
        if not make_dir_link(self.out, live):
            self.skipTest("cannot create a directory link here")
        with self.assertRaises(rel.HandoffError):
            self.run_handoff(repo)
        self.assertTrue((live / "keep.txt").is_file())


class TestRepoCoordinationFiles(unittest.TestCase):
    """The two-machine loop: LOCKED-AREAS.md and MAC-INBOX.md exist at the repo root and parse."""

    def test_locked_areas_parse(self):
        areas = rel.parse_locked_areas((REPO / "LOCKED-AREAS.md").read_text(encoding="utf-8"))
        globs = [g for g, _why in areas]
        for must in ("whynot-cut/evals/**", "whynot-cut/hooks/**", "whynot-cut/output-styles/**",
                     "whynot-cut/skills/status/**", "adobe/**", "whynot-cut/engine/reel/serve/**",
                     "whynot-cut/installer/**", "guide-ar/**"):
            self.assertIn(must, globs)
        self.assertTrue(all(why for _g, why in areas))

    def test_locked_areas_empty_is_an_error(self):
        with self.assertRaises(ValueError):
            rel.parse_locked_areas("# Locked areas\n\n## Locked now\n\n(nothing)\n")

    def test_mac_inbox_parses(self):
        text = (REPO / "MAC-INBOX.md").read_text(encoding="utf-8")
        self.assertEqual(rel.parse_mac_inbox(text), [])
        for field in rel.INBOX_FIELDS:
            self.assertIn(f"- {field}:", text)
        sample = text.replace("(none yet)", "### 2026-10-20: fonts on macOS\n- Added: ~/Library/Fonts lookup\n"
                              "- Commits: abc1234\n- Tests: test_fonts (macOS 26 pass)\n"
                              "- Needs Windows verification: tools/test.sh -k fonts\n- Status: open\n")
        entries = rel.parse_mac_inbox(sample)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "2026-10-20: fonts on macOS")
        self.assertEqual(entries[0]["Status"], "open")

    def test_mac_inbox_entry_missing_a_field_is_an_error(self):
        text = (REPO / "MAC-INBOX.md").read_text(encoding="utf-8").replace(
            "(none yet)", "### 2026-10-20: x\n- Added: y\n- Status: open\n")
        with self.assertRaises(ValueError):
            rel.parse_mac_inbox(text)


if __name__ == "__main__":
    unittest.main()
