"""T4.6 Music in motion videos: licensed tracks from data/Music (a JSON licence per track or per folder), chosen by the
recipe's mood, ducked under the dialogue with level keyframes, laid in After Effects as one MUSIC layer. No licence ->
no music + exactly one NEEDS-YOU item; nothing is ever written into the client's data/ or assets/.

Case ids (L*, F*, A*, M*, K*, R*, X*, P*, B*) are the ones in the T4.6 case list. Run:
    bash tools/test.sh -p test_t46_music.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
import json
import math
import os
import random
import shutil
import sys
import tempfile
import unicodedata
import unittest
from time import time_ns
import wave
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402
from test_podcast import ff  # noqa: E402  (functions only)
from test_motion import (FakeAE, good_script, jsx_fn, motion_plan_fixture, rb_from_plan, test_font,  # noqa: E402
                         use_machine_fonts)

AE_TPL = SK / "templates" / "after_effects"


# --------------------------------------------------------------------------- helpers
def tone(path: Path, secs: float = 1.0, freq: int = 300) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ff("-f", "lavfi", "-i", f"sine=f={freq}:r=48000:d={secs}", "-ac", "2", "-c:a", "pcm_s16le", str(path))
    return path


def lic(**kw) -> dict:
    d = {"license": "CC0-1.0", "source": "test library"}
    d.update(kw)
    return d


def put_lic(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def tree_hash(*dirs: Path) -> str:
    h = hashlib.sha1()
    for d in dirs:
        if not d.exists():
            h.update(b"<none>" + str(d).encode("utf-8"))
            continue
        for f in sorted(p for p in d.rglob("*") if p.is_file()):
            h.update(f.relative_to(d).as_posix().encode("utf-8"))
            h.update(f.read_bytes())
    return h.hexdigest()


def music_needs(plan: dict | None) -> list[dict]:
    """The music NEEDS-YOU items of a compiled plan. Single place that knows the shape (Q2: the T4.7 contract may
    rename it), so only this helper changes if it does."""
    return [x for x in ((plan or {}).get("needs_you") or []) if x.get("kind") == "music"]


def interp(keys: list, frame: float) -> float:
    """The level (dB) at `frame` with After Effects' linear-in-dB interpolation between keys."""
    if frame <= keys[0][0]:
        return keys[0][1]
    for (f0, v0), (f1, v1) in zip(keys, keys[1:]):
        if f0 <= frame <= f1:
            return v0 if f1 == f0 else v0 + (v1 - v0) * (frame - f0) / (f1 - f0)
    return keys[-1][1]


def by_name(catalog: list[dict]) -> dict:
    return {Path(e["rel"]).name: e for e in catalog}


def make_link(link: Path, target: Path) -> bool:
    """A directory junction (Windows) / symlink (else) for F7; False when the OS refuses (no privilege)."""
    try:
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(target, link, target_is_directory=True)
        return True
    except OSError:
        return False


def remove_link(link: Path):
    """Removes the link itself, never what it points to (rule 15)."""
    if os.path.islink(link) or (hasattr(os.path, "isjunction") and os.path.isjunction(link)):
        os.rmdir(link) if os.name == "nt" else os.unlink(link)


class MusicDir(unittest.TestCase):
    """A bare client root with data/Music (no motion project): catalog and licence tests."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "CLIENT"
        self.music = self.root / "data" / "Music"
        self.music.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def cat(self):
        from lib.motion_audio import music_catalog
        return by_name(music_catalog(self.root))


# --------------------------------------------------------------------------- licences (L*)
class TestLicences(MusicDir):
    def test_L1_no_licence_file(self):
        tone(self.music / "tense_dark.wav")
        e = self.cat()["tense_dark.wav"]
        self.assertFalse(e["licensed"])
        self.assertIsNone(e["licence"])
        self.assertRegex(e["why"], r"(?i)no licen[cs]e")

    def test_track_sidecar_licence(self):
        tone(self.music / "a.wav")
        put_lic(self.music / "a.wav.licence.json", lic())
        e = self.cat()["a.wav"]
        self.assertTrue(e["licensed"], e["why"])
        self.assertEqual(e["licence"]["license"], "CC0-1.0")
        self.assertEqual(e["licence"]["via"], "track")

    def test_license_spelling_accepted(self):
        tone(self.music / "a.wav")
        put_lic(self.music / "a.wav.license.json", lic())
        tone(self.music / "sub" / "b.wav")
        put_lic(self.music / "sub" / "license.json", lic(files="*"))
        c = self.cat()
        self.assertTrue(c["a.wav"]["licensed"], c["a.wav"]["why"])
        self.assertTrue(c["b.wav"]["licensed"], c["b.wav"]["why"])
        self.assertEqual(c["b.wav"]["licence"]["via"], "folder")

    def test_L2_folder_licence_lists_other_tracks(self):
        tone(self.music / "a.wav")
        tone(self.music / "b.wav")
        put_lic(self.music / "licence.json", lic(files=["a.wav"]))
        c = self.cat()
        self.assertTrue(c["a.wav"]["licensed"], c["a.wav"]["why"])
        self.assertFalse(c["b.wav"]["licensed"])
        self.assertIn("b.wav", c["b.wav"]["why"])

    def test_L3_star_covers_that_folder_only(self):
        tone(self.music / "a.wav")
        tone(self.music / "sub" / "c.wav")
        put_lic(self.music / "licence.json", lic(files="*"))
        c = self.cat()
        self.assertTrue(c["a.wav"]["licensed"])
        self.assertFalse(c["c.wav"]["licensed"], "a folder licence never covers its subfolders")

    def test_folder_licence_without_files_key_is_not_a_licence(self):
        tone(self.music / "a.wav")
        put_lic(self.music / "licence.json", lic())
        e = self.cat()["a.wav"]
        self.assertFalse(e["licensed"])
        self.assertRegex(e["why"], r"files")

    def test_L4_empty_licence(self):
        tone(self.music / "a.wav")
        tone(self.music / "b.wav")
        (self.music / "a.wav.licence.json").write_bytes(b"")
        (self.music / "b.wav.licence.json").write_text("  \n\t", encoding="utf-8")
        c = self.cat()
        for n in ("a.wav", "b.wav"):
            self.assertFalse(c[n]["licensed"])
            self.assertRegex(c[n]["why"], r"(?i)empty")

    def test_L5_unreadable_licences_never_raise(self):
        for n in ("bad.wav", "utf16.wav", "bin.wav", "dir.wav", "bom.wav"):
            tone(self.music / n)
        (self.music / "bad.wav.licence.json").write_text('{"license": "CC0-1.0", ', encoding="utf-8")
        (self.music / "utf16.wav.licence.json").write_bytes(json.dumps(lic()).encode("utf-16"))
        (self.music / "bin.wav.licence.json").write_bytes(bytes(range(256)) * 4)
        (self.music / "dir.wav.licence.json").mkdir()
        (self.music / "bom.wav.licence.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(lic()).encode("utf-8"))
        c = self.cat()
        for n in ("bad.wav", "utf16.wav", "bin.wav", "dir.wav"):
            self.assertFalse(c[n]["licensed"], n)
            self.assertTrue(c[n]["why"], n)
        self.assertTrue(c["bom.wav"]["licensed"], c["bom.wav"]["why"])   # a UTF-8 BOM is still valid JSON text

    def test_L6_wrong_format(self):
        cases = {
            "arr.wav": [lic()], "str.wav": "CC0-1.0", "nolic.wav": {"source": "x"},
            "gpl.wav": lic(license="GPL-3.0"), "ccby.wav": lic(license="CC-BY-4.0"),
            "comm.wav": lic(license="commercial"), "nosrc.wav": lic(source=""),
        }
        want = {"arr.wav": r"(?i)object|format", "str.wav": r"(?i)object|format", "nolic.wav": r"license",
                "gpl.wav": r"GPL-3\.0", "ccby.wav": r"(?i)attribution", "comm.wav": r"(?i)proof", "nosrc.wav": r"(?i)source"}
        for n, data in cases.items():
            tone(self.music / n)
            put_lic(self.music / f"{n}.licence.json", json.dumps(data) if not isinstance(data, dict) else data)
        c = self.cat()
        for n in cases:
            self.assertFalse(c[n]["licensed"], n)
            self.assertRegex(c[n]["why"], want[n], n)
        tone(self.music / "ccby_ok.wav")
        put_lic(self.music / "ccby_ok.wav.licence.json", lic(license="CC-BY-4.0", attribution="Music: X (CC BY 4.0)"))
        e = self.cat()["ccby_ok.wav"]
        self.assertTrue(e["licensed"], e["why"])
        self.assertEqual(e["licence"]["attribution"], "Music: X (CC BY 4.0)")

    def test_L7_licence_names_a_different_track(self):
        tone(self.music / "y.wav")
        put_lic(self.music / "x.wav.licence.json", lic())                 # a sidecar of a track that is not there
        tone(self.music / "sub" / "z.wav")
        put_lic(self.music / "sub" / "licence.json", lic(files=["other.wav"]))
        c = self.cat()
        self.assertFalse(c["y.wav"]["licensed"])
        self.assertFalse(c["z.wav"]["licensed"])

    def test_L8_broken_track_licence_does_not_fall_back_to_the_folder(self):
        tone(self.music / "a.wav")
        put_lic(self.music / "a.wav.licence.json", '{"license": ')
        put_lic(self.music / "licence.json", lic(files="*"))
        e = self.cat()["a.wav"]
        self.assertFalse(e["licensed"], "a broken track licence never widens to the folder licence")
        self.assertIn("a.wav.licence.json", e["why"])

    def test_L9_music_json_license_string_is_not_a_licence(self):
        tone(self.music / "a.wav")
        write_json(self.music / "music.json", {"tracks": [{"file": "a.wav", "moods": ["tense"], "license": "royalty free"}]})
        e = self.cat()["a.wav"]
        self.assertFalse(e["licensed"])
        self.assertEqual(e["moods"], ["tense"])          # music.json still gives the moods

    def test_L9b_bare_pdf_or_txt_is_not_a_licence(self):
        tone(self.music / "a.wav")
        (self.music / "a.wav.licence.pdf").write_bytes(b"%PDF-1.4 receipt")
        (self.music / "LICENCE.txt").write_text("all tracks licensed", encoding="utf-8")
        self.assertFalse(self.cat()["a.wav"]["licensed"])

    def test_L10_proof(self):
        for n in ("missing.wav", "file.wav", "id.wav"):
            tone(self.music / n)
        put_lic(self.music / "missing.wav.licence.json", lic(license="commercial", proof="receipt-missing.pdf"))
        (self.music / "receipt.pdf").write_bytes(b"%PDF-1.4 receipt")
        put_lic(self.music / "file.wav.licence.json", lic(license="commercial", proof="receipt.pdf"))
        put_lic(self.music / "id.wav.licence.json", lic(license="commercial", proof="INV-2026-0042"))
        c = self.cat()
        self.assertFalse(c["missing.wav"]["licensed"])
        self.assertIn("receipt-missing.pdf", c["missing.wav"]["why"])
        self.assertTrue(c["file.wav"]["licensed"], c["file.wav"]["why"])
        self.assertTrue(c["id.wav"]["licensed"], c["id.wav"]["why"])

    def test_I1_deep_nesting_and_oversize_never_raise(self):
        tone(self.music / "deep.wav")
        tone(self.music / "big.wav")
        (self.music / "deep.wav.licence.json").write_text('{"a": ' + "[" * 30000 + "]" * 30000 + "}", encoding="utf-8")
        self.assertLess((self.music / "deep.wav.licence.json").stat().st_size, 64 * 1024)
        put_lic(self.music / "big.wav.licence.json", lic(note="x" * 70000))
        c = self.cat()
        self.assertFalse(c["deep.wav"]["licensed"])
        self.assertRegex(c["deep.wav"]["why"], r"(?i)nest|json")
        self.assertFalse(c["big.wav"]["licensed"])
        self.assertIn("64 KB", c["big.wav"]["why"])

    def test_I2_proof_paths(self):
        (self.music / "receipt.pdf").write_bytes(b"%PDF-1.4 receipt")
        (self.music / "sub").mkdir()
        (self.music / "sub" / "receipts").mkdir()
        (self.music / "sub" / "receipts" / "r.pdf").write_bytes(b"%PDF-1.4 r")
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "receipt.pdf").write_bytes(b"%PDF-1.4 elsewhere")
        cases = {"up.wav": "../receipt.pdf", "abs.wav": str(self.music / "receipt.pdf"),
                 "docx.wav": "receipt.docx", "dotted.wav": "INV.2026", "inside.wav": "receipts/r.pdf",
                 "id.wav": "INV-2026-0042", "site.wav": "Artlist.io order 88123", "mail.wav": "shop@example.com"}
        for n, proof in cases.items():
            tone(self.music / "sub" / n)
            put_lic(self.music / "sub" / f"{n}.licence.json", lic(license="commercial", proof=proof))
        c = self.cat()
        for n in ("up.wav", "abs.wav", "docx.wav"):
            self.assertFalse(c[n]["licensed"], n)
            self.assertRegex(c[n]["why"], r"(?i)proof", n)
        for n in ("inside.wav", "id.wav", "dotted.wav", "site.wav", "mail.wav"):     # M1: dotted ids are ids
            self.assertTrue(c[n]["licensed"], (n, c[n]["why"]))

    def test_I2_proof_through_a_link_is_refused(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "receipt.pdf").write_bytes(b"%PDF-1.4 elsewhere")
        link = self.music / "rc"
        if not make_link(link, outside):
            self.skipTest("this machine refuses to create a directory link")
        self.addCleanup(remove_link, link)
        tone(self.music / "a.wav")
        put_lic(self.music / "a.wav.licence.json", lic(license="commercial", proof="rc/receipt.pdf"))
        e = self.cat()["a.wav"]
        self.assertFalse(e["licensed"])
        self.assertRegex(e["why"], r"(?i)proof")

    def test_attribution_must_be_a_non_empty_string(self):
        for n, kw in (("num.wav", dict(license="CC-BY-4.0", attribution=123)),
                      ("blank.wav", dict(license="CC-BY-4.0", attribution="  ")),
                      ("list.wav", dict(attribution=["x"]))):
            tone(self.music / n)
            put_lic(self.music / f"{n}.licence.json", lic(**kw))
        c = self.cat()
        for n in ("num.wav", "blank.wav", "list.wav"):
            self.assertFalse(c[n]["licensed"], n)
            self.assertRegex(c[n]["why"], r"(?i)attribution", n)

    def test_client_licence(self):
        """The client's own jingle: license "client" with a source, no proof (as motion_qc accepts it)."""
        tone(self.music / "jingle.wav")
        tone(self.music / "nosrc.wav")
        put_lic(self.music / "jingle.wav.licence.json", {"license": "client", "source": "the client's own jingle"})
        put_lic(self.music / "nosrc.wav.licence.json", {"license": "client"})
        c = self.cat()
        self.assertTrue(c["jingle.wav"]["licensed"], c["jingle.wav"]["why"])
        self.assertEqual(c["jingle.wav"]["licence"]["license"], "client")
        self.assertFalse(c["nosrc.wav"]["licensed"])

    def test_every_spelling_of_the_track_licence_must_agree(self):
        """_one_of reads every sibling whose name matches (NFC/NFD, case), not just two spellings."""
        name = unicodedata.normalize("NFC", "أغنية.wav")
        nfd = unicodedata.normalize("NFD", name)
        self.assertNotEqual(name, nfd)
        tone(self.music / name)
        put_lic(self.music / f"{name}.licence.json", lic())
        put_lic(self.music / f"{nfd}.licence.json", lic())
        put_lic(self.music / f"{name}.license.json", lic())
        self.assertTrue(self.cat()[name]["licensed"])
        put_lic(self.music / f"{nfd}.licence.json", lic(license="MIT"))
        e = self.cat()[name]
        self.assertFalse(e["licensed"])
        self.assertRegex(e["why"], r"(?i)disagree")

    def test_M7_empty_allowed_list_means_none(self):
        from lib import motion_config
        tone(self.music / "a.wav")
        tone(self.music / "b.wav")
        put_lic(self.music / "a.wav.licence.json", lic())
        put_lic(self.music / "b.wav.licence.json", {"license": "client", "source": "own jingle"})
        with mock.patch.object(motion_config, "motion_cfg", return_value={"licenses_allowed": []}):
            c = self.cat()
        self.assertFalse(c["a.wav"]["licensed"], "[] allows no library licence")
        self.assertTrue(c["b.wav"]["licensed"], c["b.wav"]["why"])         # the client's own music stays allowed

    def test_M10_values_are_stripped(self):
        tone(self.music / "a.wav")
        tone(self.music / "sub" / "b.wav")
        put_lic(self.music / "a.wav.licence.json", {"license": " CC0-1.0 ", "source": " lib "})
        put_lic(self.music / "sub" / "licence.json", {"license": "commercial\t", "source": "shop",
                                                       "proof": " INV-9 ", "files": [" b.wav "]})
        c = self.cat()
        self.assertTrue(c["a.wav"]["licensed"], c["a.wav"]["why"])
        self.assertEqual(c["a.wav"]["licence"]["license"], "CC0-1.0")
        self.assertTrue(c["b.wav"]["licensed"], c["b.wav"]["why"])

    def test_M3_licence_reads_refuse_links_and_special_files(self):
        """lstat first, a regular file only, at most 64 KB + 1 bytes from one handle."""
        import stat as _stat
        from lib import motion_audio
        f = put_lic(self.music / "a.wav.licence.json", lic())
        st = os.stat(f)
        fake = os.stat_result((_stat.S_IFLNK | 0o777,) + tuple(st)[1:])
        with mock.patch.object(motion_audio.os, "lstat", return_value=fake):
            data, why = motion_audio._read_licence(f)
        self.assertIsNone(data)
        self.assertRegex(why, r"(?i)link")
        tgt = put_lic(self.tmp / "elsewhere.json", lic())
        link = self.music / "b.wav.licence.json"
        tone(self.music / "b.wav")
        try:
            os.symlink(tgt, link)
        except (OSError, NotImplementedError):
            link = None
        if link is not None:
            self.addCleanup(lambda: os.path.lexists(link) and os.unlink(link))
            data, why = motion_audio._read_licence(link)
            self.assertIsNone(data)
            e = motion_audio._draft_for({"rel": "data/Music/b.wav", "file": str(self.music / "b.wav")}, self.root, {})
            self.assertEqual(e["license"], "commercial")                    # nothing taken from the linked file
            self.assertEqual(e.get("_licence_file_said"), None)
            self.assertFalse(self.cat()["b.wav"]["licensed"])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFOs on this OS")
    def test_M3_fifo_licence_is_skipped(self):
        from lib import motion_audio
        tone(self.music / "a.wav")
        fifo = self.music / "a.wav.licence.json"
        os.mkfifo(fifo)
        data, why = motion_audio._read_licence(fifo)                      # returns at once, never blocks
        self.assertIsNone(data)
        self.assertFalse(self.cat()["a.wav"]["licensed"])

    def test_M1_a_file_swapped_after_the_check_is_refused(self):
        from lib import motion_audio
        f = put_lic(self.music / "a.wav.licence.json", lic())
        other = put_lic(self.tmp / "other.json", lic(source="swapped in"))
        real_open = os.open

        def swapped(path, flags, *a, **kw):                               # the name now points at another file
            return real_open(other if str(path) == str(f) else path, flags, *a, **kw)
        with mock.patch.object(motion_audio.os, "open", side_effect=swapped):
            data, why = motion_audio._read_licence(f)
        self.assertIsNone(data)
        self.assertRegex(why, r"(?i)changed while reading")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFOs on this OS")
    def test_M2_a_fifo_named_like_a_track_is_skipped(self):
        from lib import motion_audio
        os.mkfifo(self.music / "pipe_tense.wav")
        tone(self.music / "ok_tense.wav")
        self.assertEqual([e["rel"] for e in motion_audio.music_catalog(self.root)], ["data/Music/ok_tense.wav"])
        motion_audio.music_state(self.root)                                # returns, never blocks on the pipe

    def test_M2_content_id_refuses_a_non_regular_file(self):
        from lib import motion_audio
        d = self.music / "dir_tense.wav"
        d.mkdir()
        self.assertIsNone(motion_audio._content_id(d)[0])

    def test_M9_music_list_returns_unknown_moods(self):
        from lib.recipes import music_library
        tone(self.music / "حزين_غريب.wav")
        lib = {x["rel"]: x for x in music_library(self.root)}
        self.assertEqual(lib["data/Music/حزين_غريب.wav"]["unknown_moods"], ["غريب"])

    def test_F2_plain_reason_never_reads_the_file_name(self):
        """Minor 2: a track named attribution.wav / proof.wav / source.wav reads by its real problem, not its name."""
        from lib import motion_audio
        tone(self.music / "attribution.wav")
        (self.music / "attribution.wav.licence.json").write_bytes(b"")             # empty: can't be read
        tone(self.music / "proof.wav")
        put_lic(self.music / "proof.wav.licence.json", {"license": "CC0-1.0"})      # no source
        tone(self.music / "files.wav")
        put_lic(self.music / "files.wav.licence.json", lic(license="GPL-3.0"))      # type not allowed
        c = self.cat()
        en, _ar = motion_audio._plain(c["attribution.wav"])
        self.assertIn("can't be read", en)
        self.assertNotIn("credit line", en)
        en, _ar = motion_audio._plain(c["proof.wav"])
        self.assertIn("source", en)
        self.assertNotIn("proof", en.replace("proof.wav", ""))
        en, _ar = motion_audio._plain(c["files.wav"])
        self.assertIn("GPL-3.0", en)

    def test_F2_plain_reason_by_code_for_odd_names_and_values(self):
        """P3-1 / P3-2 (review c4fb7a6): the editor's reason comes from the reason code, never from the text, so a
        name in another letter case, a licence name holding a trigger word, or a proof value holding one reads right."""
        from lib import motion_audio
        cases = {
            "e/proof.wav": ("proof.wav.licence.json", b"", "can't be read"),                     # empty, name says proof
            "c/Proof.WAV": ("proof.wav.licence.json", b"", "can't be read"),                     # other letter case
            "v/a.wav": ("a.wav.licence.json", json.dumps(lic(license="commercial", proof="attribution text.pdf")),
                        "purchase proof"),                                                         # the value says attribution
            "s/source.wav": ("source.wav.licence.json", json.dumps(lic(license="GPL-3.0")), "isn't allowed"),
        }
        for rel, (lname, body, want) in cases.items():
            t = self.music / rel
            tone(t)
            f = t.parent / lname
            f.write_bytes(body if isinstance(body, bytes) else body.encode("utf-8"))
        d = self.music / "d"
        tone(d / "Proof.wav")
        put_lic(d / "Proof.wav.licence.json", lic())
        put_lic(d / "proof.wav.license.json", lic(license="MIT"))                                # disagree, other case
        c = self.cat()
        for rel, (_l, _b, want) in cases.items():
            en, _ar = motion_audio._plain(c[Path(rel).name])
            self.assertIn(want, en, rel)
        en, _ar = motion_audio._plain(c["Proof.wav"])
        self.assertIn("two licence files", en)
        self.assertNotIn("credit line", motion_audio._plain(c["a.wav"])[0])

    def test_P3_3_a_hard_linked_licence_is_not_a_licence(self):
        tone(self.music / "a.wav")
        src = put_lic(self.tmp / "shared.json", lic())
        try:
            os.link(src, self.music / "a.wav.licence.json")
        except OSError:
            self.skipTest("no hard links here")
        e = self.cat()["a.wav"]
        self.assertFalse(e["licensed"])
        self.assertRegex(e["why"], r"(?i)hard")

    def test_F5_hand_pick_with_another_letter_case_on_a_case_sensitive_system(self):
        """Minor 5 (macOS): resolve() keeps the given case there and paths compare case-sensitively; given_rel compares
        each component with _key, so data/music/Tense_Dark.WAV still names data/Music/tense_dark.wav."""
        from lib import motion_audio
        tone(self.music / "tense_dark.wav")

        def strict_relative_to(self_, other):                         # a case-sensitive comparison, as on macOS
            a, b = self_.parts, Path(other).parts
            if a[:len(b)] != b:
                raise ValueError(f"{self_} is not in the subpath of {other}")
            return Path(*a[len(b):])
        with mock.patch.object(Path, "resolve", lambda self_, strict=False: Path(os.path.abspath(self_))), \
                mock.patch.object(Path, "relative_to", strict_relative_to):
            rel = motion_audio.given_rel(self.root, "data/music/Tense_Dark.WAV")
        self.assertIsNotNone(rel)
        self.assertEqual(rel.casefold(), "data/music/tense_dark.wav")
        self.assertTrue(rel.startswith("data/Music/"))

    def test_L11_two_spellings_that_disagree(self):
        tone(self.music / "a.wav")
        tone(self.music / "b.wav")
        put_lic(self.music / "a.wav.licence.json", lic())
        put_lic(self.music / "a.wav.license.json", lic(license="CC-BY-4.0", attribution="X"))
        put_lic(self.music / "b.wav.licence.json", lic())
        put_lic(self.music / "b.wav.license.json", lic())
        c = self.cat()
        self.assertFalse(c["a.wav"]["licensed"])
        self.assertRegex(c["a.wav"]["why"], r"(?i)both|disagree")
        self.assertTrue(c["b.wav"]["licensed"], c["b.wav"]["why"])


# --------------------------------------------------------------------------- music folder (F*) + names (A*)
class TestCatalog(MusicDir):
    def test_F1_no_music_folder(self):
        from lib.motion_audio import music_catalog
        shutil.rmtree(self.music)
        self.assertEqual(music_catalog(self.root), [])
        self.assertFalse(self.music.exists(), "the catalog never creates data/Music")

    def test_F2_only_junk(self):
        from lib.motion_audio import music_catalog
        (self.music / ".DS_Store").write_bytes(b"\0" * 10)
        (self.music / "._a.wav").write_bytes(b"\0\x05\x16\x07")      # macOS AppleDouble
        put_lic(self.music / "licence.json", lic(files="*"))
        self.assertEqual(music_catalog(self.root), [])

    def test_F3_undecodable_tracks(self):
        (self.music / "junk.wav").write_bytes(os.urandom(4096))
        (self.music / "zero.wav").write_bytes(b"")
        tone(self.music / "ok.wav", 2.0)
        put_lic(self.music / "licence.json", lic(files="*"))
        c = self.cat()
        self.assertFalse(c["junk.wav"]["decodes"])
        self.assertFalse(c["zero.wav"]["decodes"])
        self.assertTrue(c["ok.wav"]["decodes"])
        self.assertAlmostEqual(c["ok.wav"]["duration_s"], 2.0, delta=0.05)

    def test_F6_nested_folder_with_its_own_licence(self):
        tone(self.music / "Calm" / "calm_warm.wav")
        put_lic(self.music / "Calm" / "licence.json", lic(files="*"))
        e = self.cat()["calm_warm.wav"]
        self.assertTrue(e["licensed"], e["why"])
        self.assertEqual(e["rel"], "data/Music/Calm/calm_warm.wav")

    def test_F7_links_inside_data_music_are_not_followed(self):
        from lib.motion_audio import music_catalog
        outside = self.tmp / "outside"
        tone(outside / "stolen_tense.wav")
        put_lic(outside / "licence.json", lic(files="*"))
        link = self.music / "linked"
        if not make_link(link, outside):
            self.skipTest("this machine refuses to create a directory link")
        self.addCleanup(remove_link, link)
        rels = [e["rel"] for e in music_catalog(self.root)]
        self.assertFalse(any("stolen" in r for r in rels), rels)

    def test_arabic_mood_words_map_to_the_recipe_moods(self):
        """Pre-mortem 1: Arabic mood words (file name or music.json), NFC, no diacritics, alef forms unified, the
        article dropped, map to the recipes' English moods; an unknown Arabic word is kept as unknown."""
        tone(self.music / "توتر.wav")
        tone(self.music / "الإثَارة_01.wav")                    # article + hamza alef + a fatha
        tone(self.music / "x.wav")
        tone(self.music / "حزين_غريب.wav")
        tone(self.music / "hope_energy.wav")
        write_json(self.music / "music.json", {"tracks": [{"file": "x.wav", "moods": ["أمل", "هادئ"]}]})
        c = self.cat()
        self.assertIn("tense", c["توتر.wav"]["moods"])
        self.assertIn("tense", c["الإثَارة_01.wav"]["moods"])
        self.assertIn("uplifting", c["x.wav"]["moods"])             # أمل -> hope
        self.assertIn("soft", c["x.wav"]["moods"])                  # هادئ -> calm
        self.assertIn("piano", c["حزين_غريب.wav"]["moods"])          # حزين -> sad
        self.assertEqual(c["حزين_غريب.wav"]["unknown_moods"], ["غريب"])
        self.assertEqual(c["توتر.wav"]["unknown_moods"], [])
        self.assertIn("upbeat", c["hope_energy.wav"]["moods"])       # the English concept words map too
        self.assertIn("uplifting", c["hope_energy.wav"]["moods"])

    def test_A1_arabic_names(self):
        tone(self.music / "هادئ_دافئ.wav")
        write_json(self.music / "music.json", {"tracks": [{"file": "هادئ_دافئ.wav", "moods": ["warm", "curious"]}]})
        put_lic(self.music / "licence.json", lic(files=["هادئ_دافئ.wav"]))
        e = self.cat()["هادئ_دافئ.wav"]
        self.assertTrue(e["licensed"], e["why"])
        self.assertEqual(e["moods"], ["warm", "curious"])
        self.assertEqual(e["rel"], "data/Music/هادئ_دافئ.wav")

    def test_A2_mixed_names_with_rtl_marks(self):
        name = "calm_هادئ‏ 01.mp3"
        ff("-f", "lavfi", "-i", "sine=f=300:r=48000:d=1", "-ac", "2", "-c:a", "libmp3lame", str(self.music / name))
        put_lic(self.music / f"{name}.licence.json", lic())
        e = self.cat()[name]
        self.assertTrue(e["licensed"], e["why"])
        self.assertTrue(e["decodes"])

    def test_A3_nfd_name_matches_nfc_licence(self):
        nfc = unicodedata.normalize("NFC", "أغنية_tense.wav")
        nfd = unicodedata.normalize("NFD", nfc)
        self.assertNotEqual(nfc, nfd)
        tone(self.music / nfd)
        put_lic(self.music / "licence.json", lic(files=[nfc]))
        e = next(iter(self.cat().values()))
        self.assertTrue(e["licensed"], e["why"])

    def test_A4_case_insensitive_names(self):
        tone(self.music / "Track.WAV")
        put_lic(self.music / "licence.json", lic(files=["track.wav"]))
        e = self.cat()["Track.WAV"]
        self.assertTrue(e["licensed"], e["why"])

    def test_P3_no_ffprobe_never_crashes(self):
        from lib import motion_audio
        tone(self.music / "a.wav")
        put_lic(self.music / "licence.json", lic(files="*"))
        with mock.patch.object(motion_audio, "probe_duration", side_effect=FileNotFoundError("ffprobe")):
            e = by_name(motion_audio.music_catalog(self.root))["a.wav"]
        self.assertFalse(e["decodes"])
        self.assertTrue(e["licensed"])

    def test_music_list_shows_the_licence_status(self):
        """`reel music --list` (recipes.music_library) tells the director which tracks motion videos may use."""
        from lib.recipes import music_library
        tone(self.music / "a.wav")
        tone(self.music / "b.wav")
        put_lic(self.music / "a.wav.licence.json", lic())
        write_json(self.music / "music.json", {"tracks": [{"file": "b.wav", "license": "Artlist #123"}]})
        lib = {x["rel"]: x for x in music_library(self.root)}
        self.assertTrue(lib["data/Music/a.wav"]["licensed"])
        self.assertFalse(lib["data/Music/b.wav"]["licensed"])
        self.assertEqual(lib["data/Music/b.wav"]["license"], "Artlist #123")   # shown as given, not a licence
        self.assertRegex(lib["data/Music/b.wav"]["licence_why"], r"(?i)no licen[cs]e")

    def test_music_list_never_walks_a_junction(self):
        from lib.recipes import music_library
        outside = self.tmp / "outside"
        tone(outside / "stolen_tense.wav")
        put_lic(outside / "licence.json", lic(files="*"))
        link = self.music / "linked"
        if not make_link(link, outside):
            self.skipTest("this machine refuses to create a directory link")
        self.addCleanup(remove_link, link)
        tone(self.music / "own.wav")
        lib = music_library(self.root)
        self.assertEqual([x["rel"] for x in lib], ["data/Music/own.wav"])
        self.assertFalse(any(x["licensed"] for x in lib))

    def test_catalog_never_writes(self):
        from lib.motion_audio import music_catalog
        tone(self.music / "a.wav")
        put_lic(self.music / "licence.json", lic(files="*"))
        before = tree_hash(self.root)
        music_catalog(self.root)
        music_catalog(self.root)
        self.assertEqual(tree_hash(self.root), before)


# --------------------------------------------------------------------------- selection (M*, D4)
def entry(rel, moods, dur=60.0, licensed=True, decodes=True):
    return {"rel": f"data/Music/{rel}", "file": f"/x/{rel}", "moods": moods, "licensed": licensed, "decodes": decodes,
            "duration_s": dur, "licence": lic() if licensed else None, "why": "" if licensed else "no licence"}


class TestPick(unittest.TestCase):
    def pick(self, cat, moods=("tense", "dark", "cinematic"), dur=14.0):
        from lib.motion_audio import pick_track
        return pick_track(cat, list(moods), dur)

    def test_M1_no_match(self):
        self.assertIsNone(self.pick([entry("happy.wav", ["happy"])]))

    def test_M3_higher_score_wins(self):
        cat = [entry("a.wav", ["tense"]), entry("z.wav", ["tense", "dark"])]
        self.assertEqual(self.pick(cat)["rel"], "data/Music/z.wav")

    def test_M2_ties_are_deterministic(self):
        cat = [entry("b.wav", ["tense"], 30), entry("a.wav", ["tense"], 5), entry("c.wav", ["tense"], 20),
               entry("C2.wav", ["tense"], 20)]
        picks = set()
        rnd = random.Random(4)
        for _ in range(6):
            rnd.shuffle(cat)
            picks.add(self.pick(cat)["rel"])
        # covering track, least overrun, then the name casefolded ("c.wav" < "c2.wav"; raw order would put "C2" first)
        self.assertEqual(picks, {"data/Music/c.wav"})

    def test_D4_short_track_only_when_nothing_longer_ties(self):
        self.assertEqual(self.pick([entry("short.wav", ["tense"], 5), entry("long.wav", ["tense"], 40)])["rel"],
                         "data/Music/long.wav")
        self.assertEqual(self.pick([entry("short.wav", ["tense"], 5)])["rel"], "data/Music/short.wav")
        # mood first: a better-fitting short track beats a longer weaker one
        self.assertEqual(self.pick([entry("short.wav", ["tense", "dark"], 5), entry("long.wav", ["tense"], 40)])["rel"],
                         "data/Music/short.wav")

    def test_unlicensed_and_undecodable_are_never_picked(self):
        cat = [entry("u.wav", ["tense", "dark", "cinematic"], licensed=False),
               entry("d.wav", ["tense", "dark", "cinematic"], decodes=False), entry("ok.wav", ["dark"])]
        self.assertEqual(self.pick(cat)["rel"], "data/Music/ok.wav")
        self.assertIsNone(self.pick(cat[:2]))

    def test_M4_no_moods_no_pick(self):
        self.assertIsNone(self.pick([entry("a.wav", ["tense"])], moods=()))

    def test_moods_casefold(self):
        self.assertEqual(self.pick([entry("a.wav", ["Tense"])])["rel"], "data/Music/a.wav")


# --------------------------------------------------------------------------- ducking (K*)
class TestDucking(unittest.TestCase):
    def duck(self, speech, n=300, fps=30.0, level=-24.0, **kw):
        from lib.motion_audio import duck_keyframes
        return duck_keyframes(speech, n, fps, level, **kw)

    def D(self):
        from lib.motion_audio import DUCK_DEFAULTS
        return DUCK_DEFAULTS

    def well_formed(self, keys, n):
        frames = [k[0] for k in keys]
        self.assertTrue(all(isinstance(f, int) for f in frames), keys)
        self.assertEqual(frames, sorted(set(frames)), "sorted, one key per frame")
        self.assertGreaterEqual(frames[0], 0)
        self.assertLessEqual(frames[-1], n)
        d = self.D()
        self.assertTrue(all(d["floor_db"] <= k[1] <= d["free_max_db"] for k in keys), keys)
        self.assertEqual(keys[0], [0, d["floor_db"]])
        self.assertEqual(keys[-1], [n, d["floor_db"]])

    def free(self, level):
        d = self.D()
        return min(level + d["lift_db"], d["free_max_db"])

    def test_K1_no_dialogue(self):
        keys = self.duck([])
        self.well_formed(keys, 300)
        self.assertEqual({v for _, v in keys}, {self.D()["floor_db"], self.free(-24)})
        self.assertAlmostEqual(interp(keys, 150), self.free(-24))

    def test_K2_dialogue_everywhere(self):
        keys = self.duck([[0, 300]])
        self.well_formed(keys, 300)
        self.assertNotIn(self.free(-24), {v for _, v in keys})
        self.assertAlmostEqual(interp(keys, 150), -24)

    def test_duck_under_speech_and_lift_in_a_long_gap(self):
        keys = self.duck([[100, 200]])
        self.well_formed(keys, 300)
        for f in (100, 150, 200):
            self.assertAlmostEqual(interp(keys, f), -24, msg=f)
        self.assertAlmostEqual(interp(keys, 60), self.free(-24))
        self.assertAlmostEqual(interp(keys, 225), self.free(-24))

    def test_K3_short_gap_stays_ducked(self):
        keys = self.duck([[30, 100], [110, 200]])                     # 10 frames = 333 ms < attack + release + hold
        for f in range(100, 111):
            self.assertAlmostEqual(interp(keys, f), -24, msg=f)

    def test_K4_gap_at_the_threshold_is_lifted(self):
        d = self.D()
        fps = 20.0
        thr = (d["attack_ms"] + d["release_ms"] + d["hold_ms"]) * fps / 1000
        self.assertEqual(thr, int(thr), "pick fps so the threshold is a whole number of frames")
        thr = int(thr)
        lifted = self.duck([[20, 100], [100 + thr, 300]], n=400, fps=fps)
        self.assertGreater(interp(lifted, 100 + thr / 2), -24 + 0.5)
        flat = self.duck([[20, 100], [100 + thr - 1, 300]], n=400, fps=fps)
        for f in range(100, 100 + thr):
            self.assertAlmostEqual(interp(flat, f), -24, msg=f)

    def test_K5_overlapping_speech_merges(self):
        self.assertEqual(self.duck([[30, 150], [100, 200]]), self.duck([[30, 200]]))
        self.assertEqual(self.duck([[100, 200], [30, 150]]), self.duck([[30, 200]]), "order does not matter")

    def test_K6_speech_at_the_edges(self):
        keys = self.duck([[0, 10], [290, 300]])
        self.well_formed(keys, 300)
        keys = self.duck([[0, 400]], n=300)                           # speech past the end is clipped
        self.well_formed(keys, 300)

    def test_K7_random_cases_are_well_formed(self):
        rnd = random.Random(46)
        for _ in range(200):
            n = rnd.randint(1, 900)
            sp = []
            for _ in range(rnd.randint(0, 8)):
                a = rnd.randint(0, n)
                sp.append([a, min(n, a + rnd.randint(0, 120))])
            keys = self.duck(sp, n=n, fps=rnd.choice([23.976, 25.0, 29.97, 30.0, 60.0]), level=rnd.uniform(-40, -12))
            self.well_formed(keys, n)

    def test_K8_level_bounds(self):
        d = self.D()
        for bad in (d["level_min_db"] - 1, d["level_max_db"] + 1, float("nan")):
            with self.assertRaises(ValueError):
                self.duck([[0, 100]], level=bad)
        for ok in (d["level_min_db"], d["level_max_db"]):
            self.well_formed(self.duck([[0, 100]], level=ok), 300)

    def test_duck_cfg_is_clamped_to_the_schema_bounds(self):
        from lib import motion_audio, motion_config
        over = {"music": {"level_min_db": -80, "level_max_db": 0, "free_max_db": -3, "lift_db": "x", "attack_ms": -5}}
        with mock.patch.object(motion_config, "motion_cfg", return_value=over):
            c = motion_audio.duck_cfg()
        self.assertEqual(c["level_min_db"], -40.0)
        self.assertEqual(c["level_max_db"], -12.0)
        self.assertEqual(c["free_max_db"], -12.0)
        self.assertEqual(c["lift_db"], motion_audio.DUCK_DEFAULTS["lift_db"])       # not a number: the default
        self.assertEqual(c["attack_ms"], motion_audio.DUCK_DEFAULTS["attack_ms"])   # M8: negative -> the default
        with mock.patch.object(motion_config, "motion_cfg", return_value={"music": {"level_min_db": -30}}):
            self.assertEqual(motion_audio.duck_cfg()["level_min_db"], -30.0)            # narrowing is allowed

    def test_I3_floor_is_clamped(self):
        from lib import motion_audio, motion_config
        for given, want in ((0, -48.0), (-200, -96.0), (-70, -70.0)):
            with mock.patch.object(motion_config, "motion_cfg", return_value={"music": {"floor_db": given}}):
                self.assertEqual(motion_audio.duck_cfg()["floor_db"], want, given)

    def test_I3_free_level_never_below_the_speech_level(self):
        """free_max_db under the level (-30 vs -24): the gaps stay at the level, the bed never gets louder under
        speech than between phrases and nothing is inverted."""
        keys = self.duck([[100, 200]], level=-24, cfg={"free_max_db": -30})
        self.well_formed_loose(keys, 300)
        self.assertTrue(all(v <= -24 + 1e-9 for _, v in keys), keys)
        self.assertAlmostEqual(interp(keys, 60), -24)
        self.assertAlmostEqual(interp(keys, 150), -24)

    def well_formed_loose(self, keys, n):
        frames = [k[0] for k in keys]
        self.assertEqual(frames, sorted(set(frames)))
        self.assertEqual(keys[0][0], 0)
        self.assertEqual(keys[-1][0], n)

    def test_free_level_is_capped(self):
        keys = self.duck([], level=-14)
        self.assertAlmostEqual(max(v for _, v in keys), self.D()["free_max_db"])

    def test_track_end_before_video_end(self):
        """D4: a short track ends with its own fade-out; no key after its last frame."""
        keys = self.duck([[0, 100]], n=300, end_frame=150)
        self.assertEqual(keys[-1], [150, self.D()["floor_db"]])
        self.assertTrue(all(f <= 150 for f, _ in keys))

    def test_ntsc_rates(self):
        for fps in (29.97, 23.976):
            keys = self.duck([[48, 120]], n=240, fps=fps)
            self.well_formed(keys, 240)
            self.assertAlmostEqual(interp(keys, 84), -24)


# --------------------------------------------------------------------------- mix (K9, F5)
class TestMix(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dia = self.tmp / "dia.wav"
        ff("-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "10", "-c:a", "pcm_s16le", str(self.dia))
        self.mus = tone(self.tmp / "mus.wav", 30, 1000)
        self.keys = [[0, -60.0], [15, -16.0], [100, -16.0], [110, -24.0], [200, -24.0], [212, -16.0], [240, -16.0],
                     [300, -60.0]]
        self.plan = {"fps": 30.0, "duration_frames": 300,
                     "audio": {"dialogue": str(self.dia), "sfx": [],
                               "music": {"file": str(self.mus), "level_db": -24.0, "keyframes": self.keys,
                                         "fade_out_frames": 60}}}

    @staticmethod
    def frames_db(path: Path, ref: Path, frame: int, fps=30.0) -> float:
        def rms(p, a, b):
            with wave.open(str(p), "rb") as w:
                w.setpos(a)
                raw = w.readframes(b - a)
            import numpy as np
            x = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
            return float(np.sqrt(np.mean(x ** 2)))
        a, b = int(frame * 48000 / fps), int((frame + 1) * 48000 / fps)
        return 20 * math.log10(rms(path, a, b) / rms(ref, a, b))

    def test_K9_mix_follows_the_keys_in_db(self):
        from lib.motion_audio import mix
        out = mix(self.plan, self.tmp, self.tmp / "mix.wav")
        self.assertAlmostEqual(self.frames_db(out, self.mus, 50), -16, delta=0.2)
        self.assertAlmostEqual(self.frames_db(out, self.mus, 150), -24, delta=0.2)
        # inside the 100->110 ramp: AE interpolates in dB, so the mix must too (amplitude-linear is ~1 dB off here)
        ts = [105 + i / 200 for i in range(200)]
        want = 10 * math.log10(sum(10 ** (interp(self.keys, t) / 10) for t in ts) / len(ts))
        self.assertAlmostEqual(self.frames_db(out, self.mus, 105), want, delta=0.2)

    def test_F5_long_track_is_decoded_only_as_far_as_needed(self):
        import subprocess
        from lib.motion_audio import mix
        real = subprocess.run
        calls = []

        def spy(cmd, *a, **kw):
            calls.append(list(cmd))
            return real(cmd, *a, **kw)
        with mock.patch("subprocess.run", side_effect=spy):
            mix(self.plan, self.tmp, self.tmp / "mix.wav")
        mcalls = [c for c in calls if str(self.mus) in c]
        self.assertTrue(mcalls, calls)
        self.assertTrue(all("-t" in c for c in mcalls), mcalls)


# --------------------------------------------------------------------------- read-back (R4, R5)
def rb_audio(plan: dict) -> list[dict]:
    """MAIN's audio layers as a faithful After Effects read-back reports them: keys [frame, left dB, right dB]."""
    a = plan["audio"]
    out = [{"name": "DIALOGUE", "keys": []}]
    m = a.get("music")
    if m:
        out.append({"name": "MUSIC", "keys": [[k[0], k[1], k[1]] for k in m["keyframes"]],
                    "out_frame": m.get("end_frame", plan.get("duration_frames")),
                    "file": Path(str(m["file"]).replace("\\", "/")).name})
    out += [{"name": f"SFX_{c['kind']}_{i + 1}", "keys": []} for i, c in enumerate(a.get("sfx") or [])]
    return out


class TestReadbackAudio(unittest.TestCase):
    def setUp(self):
        from lib.motion_config import format_spec
        self.fmt = format_spec("9x16")
        self.plan = {"scenes": [], "persistent": {},
                     "audio": {"dialogue": "d.wav", "sfx": [{"kind": "pop", "file": "pop.wav", "frame": 10}],
                               "music": {"file": "D:/c/data/Music/m.wav", "level_db": -24.0, "end_frame": 300,
                                         "keyframes": [[0, -60.0], [15, -24.0], [285, -24.0], [300, -60.0]]}}}

    def cmp(self, audio, plan=None):
        from lib.motion_readback import compare
        rb = {"scenes": [], "missing_or_substituted": []}
        if audio is not None:
            rb["audio"] = audio
        return compare(plan or self.plan, rb, self.fmt, {})

    def test_faithful(self):
        r = self.cmp(rb_audio(self.plan))
        self.assertTrue(r["ok"], r)

    def test_R4_duplicate_audio_layers_fail(self):
        for dup in ("MUSIC", "DIALOGUE"):
            a = rb_audio(self.plan)
            a.append(dict(next(x for x in a if x["name"] == dup)))
            r = self.cmp(a)
            self.assertFalse(r["ok"], dup)
            self.assertTrue(any(dup in f for f in r["failures"]), r["failures"])

    def test_missing_or_unplanned_music_fails(self):
        a = [x for x in rb_audio(self.plan) if x["name"] != "MUSIC"]
        self.assertFalse(self.cmp(a)["ok"])
        plan = json.loads(json.dumps(self.plan))
        plan["audio"]["music"] = None
        self.assertFalse(self.cmp(rb_audio(self.plan), plan)["ok"], "a MUSIC layer the plan does not have")
        self.assertTrue(self.cmp(rb_audio(plan), plan)["ok"])

    def test_R5_keys_must_match(self):
        a = rb_audio(self.plan)
        a[1]["keys"][1][1] = -23.0
        self.assertFalse(self.cmp(a)["ok"])
        a = rb_audio(self.plan)
        a[1]["keys"].pop(2)
        self.assertFalse(self.cmp(a)["ok"])
        a = rb_audio(self.plan)
        a[1]["keys"][1][2] = -23.0                                     # the right channel is read too
        self.assertFalse(self.cmp(a)["ok"])
        a = rb_audio(self.plan)
        a[1]["keys"][1][1] = a[1]["keys"][1][2] = -24.004              # AE float noise
        self.assertTrue(self.cmp(a)["ok"])

    def test_music_layer_end_and_source_file(self):
        """Review minor: MUSIC's out frame matches the plan's end_frame (+-1 frame) and its source is the planned file."""
        for off, ok in ((0, True), (1, True), (-1, True), (2, False), (-30, False)):
            a = rb_audio(self.plan)
            a[1]["out_frame"] = 300 + off
            self.assertEqual(self.cmp(a)["ok"], ok, off)
        a = rb_audio(self.plan)
        a[1]["file"] = "other.wav"
        r = self.cmp(a)
        self.assertFalse(r["ok"])
        self.assertTrue(any("other.wav" in f for f in r["failures"]), r["failures"])
        a = rb_audio(self.plan)
        a[1]["file"] = "M.WAV"                                         # the same file, as NTFS / APFS spell it
        self.assertTrue(self.cmp(a)["ok"])

    def test_RL5_floor_keys_match_any_value_at_or_below_minus_48(self):
        a = rb_audio(self.plan)
        a[1]["keys"][0][1:] = [-48.0, -48.0]                           # AE clamped the planned -60 floor
        self.assertTrue(self.cmp(a)["ok"])
        a[1]["keys"][-1][1:] = [-96.0, -70.0]
        self.assertTrue(self.cmp(a)["ok"])
        a = rb_audio(self.plan)
        a[1]["keys"][0][1:] = [-47.0, -47.0]                           # above the floor band: a real difference
        self.assertFalse(self.cmp(a)["ok"])
        a = rb_audio(self.plan)
        a[1]["keys"][1][1:] = [-24.5, -24.5]                           # every other key keeps its exact tolerance
        self.assertFalse(self.cmp(a)["ok"])

    def test_old_bridge_without_audio_readback_warns(self):
        r = self.cmp(None)
        self.assertTrue(r["ok"], r)
        self.assertTrue(any("audio" in w.lower() for w in r["warnings"]), r["warnings"])


# --------------------------------------------------------------------------- JSX (B3)
class TestMusicJSX(unittest.TestCase):
    def test_B3_music_layer_uses_the_plan_keys(self):
        src = (AE_TPL / "wnc_motion_lib.jsx").read_text(encoding="utf-8")
        body = jsx_fn(src, "WNCM.audio")
        self.assertIn("keyframes", body)
        self.assertIn("setValuesAtTimes", body)

    def run_audio(self, music: dict, duration=300) -> dict:
        """WNCM.audio driven in node with a fake MAIN comp: the MUSIC layer's outPoint and Audio Levels calls."""
        src = (AE_TPL / "wnc_motion_lib.jsx").read_text(encoding="utf-8")
        plan = {"duration_frames": duration, "audio": {"dialogue": "d.wav", "music": music, "sfx": []}}
        js = """
var WNCM = {}; WNCM.t = function (c, f) { return f * c.frameDuration; };
var WNC = {footage: function (p) { return {path: p}; }};
var made = [];
function Layer() { var me = this; this.calls = [];
  this.lv = {setValue: function (v) { me.calls.push(["set", v]); },
             setValueAtTime: function (t, v) { me.calls.push(["at", t, v]); },
             setValuesAtTimes: function (t, v) { me.calls.push(["many", t, v]); }}; }
Layer.prototype.property = function () { var lv = this.lv; return {property: function () { return lv; }}; };
Layer.prototype.moveToEnd = function () {};
var main = {frameDuration: 0.04, layers: {add: function (it) { var L = new Layer(); made.push(L); return L; }}};
""" + jsx_fn(src, "WNCM.audio") + """
WNCM.audio(main, PLAN);
var m = made.filter(function (L) { return L.name === "MUSIC"; });
console.log(JSON.stringify({n: m.length, out: m.length ? m[0].outPoint : null, calls: m.length ? m[0].calls : []}));
""".replace("PLAN", json.dumps(plan))
        from test_motion import node_run
        return json.loads(node_run(self, js).strip().splitlines()[-1])

    def test_B3_keys_go_in_with_one_call(self):
        r = self.run_audio({"file": "m.wav", "level_db": -24, "fade_out_frames": 50, "end_frame": 300,
                            "keyframes": [[0, -60], [12, -24], [250, -24], [300, -60]]})
        self.assertEqual(r["n"], 1)
        self.assertAlmostEqual(r["out"], 12.0)
        self.assertEqual([c[0] for c in r["calls"]], ["many"])
        times, vals = r["calls"][0][1], r["calls"][0][2]
        self.assertEqual([round(t / 0.04) for t in times], [0, 12, 250, 300])
        self.assertEqual(vals, [[-60, -60], [-24, -24], [-24, -24], [-60, -60]])

    def test_B3_no_keys_keeps_the_old_fade_at_the_layer_end(self):
        """A plan without keyframes (compiled before T4.6): flat level, held until end - fade_out, -48 dB at the
        layer's own end: the video's end, or a short track's end_frame (looks & motion review)."""
        for end_frame, end in ((None, 300), (0, 300), (150, 150), (400, 300)):
            mu = {"file": "m.wav", "level_db": -24, "fade_out_frames": 50}
            if end_frame is not None:
                mu["end_frame"] = end_frame
            r = self.run_audio(mu)
            self.assertAlmostEqual(r["out"], end * 0.04, msg=end_frame)
            self.assertEqual(r["calls"][0], ["set", [-24, -24]], end_frame)
            at = [(round(c[1] / 0.04), c[2]) for c in r["calls"] if c[0] == "at"]
            self.assertEqual(at, [(end - 50, [-24, -24]), (end, [-48, -48])], end_frame)

    def test_bridge_reads_audio_layers_back(self):
        src = (AE_TPL / "wnc_ae_bridge.jsx").read_text(encoding="utf-8")
        a = src.index("WNCAE.actions.readback = function")
        body = src[a:]
        self.assertIn("out.audio", body)
        self.assertIn("hasAudio", body)

    def test_bridge_audio_readback_runs(self):
        """WNCAE.actions.readback driven in node with a fake project: only DIALOGUE / MUSIC / SFX_* layers that carry
        audio, both channels of every Audio Levels key, the layer's out frame and its decoded source file name."""
        src = (AE_TPL / "wnc_ae_bridge.jsx").read_text(encoding="utf-8")
        a = src.index("WNCAE.actions.readback = function")
        b = src.find("\nvar NHAE", a)
        js = r"""
var WNCAE = {actions: {}}; var WNC = {findComp: function () { return null; }}; var WNCM = {};
var File = {decode: function (s) { return decodeURIComponent(s); }};
function CompItem() {} function TextLayer() {} function ShapeLayer() {}
function lvl(keys) { return {numKeys: keys.length, keyTime: function (q) { return keys[q - 1][0]; },
                             keyValue: function (q) { return keys[q - 1][1]; }}; }
function AL(name, hasAudio, inP, outP, keys, file) {
  this.name = name; this.hasAudio = hasAudio; this.inPoint = inP; this.outPoint = outP; this._lv = lvl(keys);
  this.source = file ? {file: {name: file}} : {}; }
AL.prototype.property = function () { var lv = this._lv; return {property: function () { return lv; }}; };
var main = new CompItem(); main.name = "MAIN_R1"; main.frameDuration = 0.04; main.duration = 12;
var layers = [new AL("S01_kinetic_quote", false, 0, 4, [], null), new AL("DIALOGUE", true, 0, 12, [], "dia.wav"),
  new AL("MUSIC", true, 0, 6, [[0, [-60, -60]], [0.48, [-24, -23.5]], [6, [-60, -60]]], "%D8%B9%D9%88%D8%AF%20song.wav"),
  new AL("SFX_pop_1", true, 0.4, 1, [], "pop.wav"), new AL("VOICE_LEVEL", true, 0, 12, [], null)];
main.numLayers = layers.length;
main.layer = function (i) { return typeof i === "number" ? layers[i - 1] : null; };
var app = {project: {numItems: 1, item: function () { return main; }}, fonts: {missingOrSubstitutedFonts: []}};
""" + src[a:b if b > 0 else len(src)] + r"""
var out = WNCAE.actions.readback({job: {plan: {reel_id: "R1", scenes: []}}});
console.log(JSON.stringify(out.audio));
"""
        from test_motion import node_run
        audio = json.loads(node_run(self, js).strip().splitlines()[-1])
        self.assertEqual([x["name"] for x in audio], ["DIALOGUE", "MUSIC", "SFX_pop_1"])
        mus = audio[1]
        self.assertEqual(mus["keys"], [[0, -60, -60], [12, -24, -23.5], [150, -60, -60]])
        self.assertEqual(mus["out_frame"], 150)
        self.assertEqual(mus["file"], "عود song.wav")


# --------------------------------------------------------------------------- frozen pre-T4.6 fingerprint
FROZEN_CFG = {"t46": "frozen motion.json"}
FROZEN_FP = "a086b8f218e8496da4f8d58fc8d1139383b7bf4a"     # b61f808's fingerprint() of frozen_fixture() + FROZEN_CFG


def frozen_fixture(base: Path) -> Paths:
    """Fixed bytes only (no timestamps): the pre-T4.6 fingerprint of this project is FROZEN_FP."""
    p = Paths(base / "FROZEN", "EP1_R01_MO")
    files = {"00_inputs/source.json": '{"kind": "motion_reel", "recipe": {"type": "drama", "music": {"mood": ["tense"], '
                                      '"level_db": -26}}, "format": "9x16", "direction": "rtl"}',
             "01_analysis/motion-script.json": '{"reel_id": "EP1_R01_MO", "scenes": []}',
             "02_transcription/words.json": '{"words": [{"id": 1, "word": "كلمه", "start_ms": 0, "end_ms": 300}]}',
             "06_audio/dialogue/pauses.json": '{"keep_ms": [[0, 1000]]}'}
    for rel, text in files.items():
        f = p.p(rel)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(text.encode("utf-8"))
    bt = p.client_db / "branding/brand-tokens.json"
    bt.parent.mkdir(parents=True, exist_ok=True)
    bt.write_bytes(b'{"roles": {"primary": {"hex": "#20ACAF"}}}')
    return p


# --------------------------------------------------------------------------- the compiled motion plan
class MusicPlanCase(unittest.TestCase):
    """One motion project (drama recipe: moods tense/dark/cinematic, -26 dB) per class; each test starts with an empty
    data/Music and the good script."""
    TMP_SUB = ""

    @classmethod
    def setUpClass(cls):
        if test_font() is None:
            raise unittest.SkipTest("no test font for HarfBuzz fitting")
        cls.tmp = Path(tempfile.mkdtemp())
        base = cls.tmp / cls.TMP_SUB if cls.TMP_SUB else cls.tmp
        base.mkdir(parents=True, exist_ok=True)
        cls.root, cls.ep, cls.reel = motion_plan_fixture(base)
        cls.src_bytes = cls.reel.p("00_inputs/source.json").read_bytes()

    @classmethod
    def tearDownClass(cls):
        common.set_context(None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        common.set_context(self.root)
        self.music = self.root / "data" / "Music"
        remove_link(self.music)                                         # never rmtree through a link
        shutil.rmtree(self.music, ignore_errors=True)
        self.music.mkdir(parents=True)
        shutil.rmtree(self.reel.p("06_audio/licence-drafts"), ignore_errors=True)
        self.reel.p("00_inputs/source.json").write_bytes(self.src_bytes)

    def compile(self, music="__unset__"):
        from lib.motion_plan import compile_motion
        s = good_script()
        if music != "__unset__":
            s["music"] = music
        write_json(self.reel.p("01_analysis/motion-script.json"), s)
        self.reel.p("01_analysis/motion-plan.json").unlink(missing_ok=True)
        r = compile_motion(self.reel)
        p = self.reel.p("01_analysis/motion-plan.json")
        return r, (read_json(p) if p.exists() else None)

    def licensed(self, name="tense_dark.wav", secs=30.0, **kw) -> Path:
        f = tone(self.music / name, secs)
        put_lic(self.music / f"{name}.licence.json", lic(**kw))
        return f

    def assert_no_music_one_need(self, r, plan, mention=None):
        self.assertTrue(r["ok"], r["errors"])
        self.assertIsNone(plan["audio"]["music"])
        needs = music_needs(plan)
        self.assertEqual(len(needs), 1, plan.get("needs_you"))
        if mention:
            self.assertIn(mention, needs[0]["text"] + " " + needs[0].get("why", ""))
        return needs[0]


class TestMusicPlan(MusicPlanCase):
    def test_auto_pick_by_recipe_mood(self):
        self.licensed("tense_dark.wav")
        tone(self.music / "happy_light.wav", 30)
        put_lic(self.music / "happy_light.wav.licence.json", lic())
        r, plan = self.compile()
        self.assertTrue(r["ok"], r["errors"])
        m = plan["audio"]["music"]
        self.assertEqual(m["rel"], "data/Music/tense_dark.wav")
        self.assertEqual(m["level_db"], -26.0)
        self.assertTrue(m["keyframes"])
        self.assertEqual(music_needs(plan), [])
        asset = [a for a in plan["assets"] if a["ref"] == "data/Music/tense_dark.wav"]
        self.assertEqual(len(asset), 1)
        self.assertEqual(asset[0]["license"], "CC0-1.0")

    def test_keys_in_the_plan_duck_under_the_fixture_dialogue(self):
        from lib.motion_audio import DUCK_DEFAULTS
        self.licensed()
        r, plan = self.compile()
        self.assertTrue(r["ok"], r["errors"])
        keys = plan["audio"]["music"]["keyframes"]
        n = plan["duration_frames"]
        self.assertEqual(keys[0], [0, DUCK_DEFAULTS["floor_db"]])
        self.assertEqual(keys[-1], [n, DUCK_DEFAULTS["floor_db"]])
        self.assertAlmostEqual(interp(keys, round(6 * plan["fps"])), -26.0)   # 6 s: the words never stop there
        self.assertTrue(all(DUCK_DEFAULTS["floor_db"] <= v <= DUCK_DEFAULTS["free_max_db"] for _, v in keys))

    def test_L1_X1_unlicensed_track_refusal(self):
        tone(self.music / "tense_dark.wav", 30)
        data_before = tree_hash(self.root / "data", self.root / "assets")
        r, plan = self.compile()
        self.assert_no_music_one_need(r, plan)
        self.assertEqual(tree_hash(self.root / "data", self.root / "assets"), data_before)
        mdir = self.reel.p("06_audio/music")
        self.assertFalse(mdir.exists() and any(mdir.iterdir()), "no music copied anywhere")

    def test_F1_no_music_folder(self):
        shutil.rmtree(self.music)
        r, plan = self.compile()
        self.assert_no_music_one_need(r, plan)
        self.assertFalse(self.music.exists())

    def test_F2_empty_music_folder(self):
        r, plan = self.compile()
        self.assert_no_music_one_need(r, plan)

    def test_M1_no_mood_match(self):
        self.licensed("happy_light.wav")
        r, plan = self.compile()
        self.assert_no_music_one_need(r, plan, mention="tense")

    def test_M4_recipe_without_mood(self):
        self.licensed()
        src = read_json(self.reel.p("00_inputs/source.json"))
        src["recipe"].pop("music", None)
        write_json(self.reel.p("00_inputs/source.json"), src)
        r, plan = self.compile()
        self.assert_no_music_one_need(r, plan)

    def test_M5_explicit_choice_beats_mood(self):
        self.licensed("happy_light.wav")
        r, plan = self.compile({"file": "data/Music/happy_light.wav"})
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(plan["audio"]["music"]["rel"], "data/Music/happy_light.wav")
        self.assertTrue(any("mood" in w for w in r["warnings"]), r["warnings"])
        self.assertEqual(music_needs(plan), [])

    def test_M6_music_off(self):
        self.licensed()
        r, plan = self.compile(False)
        self.assertTrue(r["ok"], r["errors"])
        self.assertIsNone(plan["audio"]["music"])
        self.assertEqual(music_needs(plan), [])

    def test_M7_explicit_unlicensed_file(self):
        tone(self.music / "tense_dark.wav", 30)
        r, plan = self.compile({"file": "data/Music/tense_dark.wav"})
        self.assert_no_music_one_need(r, plan, mention="tense_dark.wav")

    def test_M7b_explicit_unlicensed_with_a_licensed_alternative_is_still_one_item(self):
        tone(self.music / "chosen.wav", 30)
        self.licensed("tense_dark.wav")
        r, plan = self.compile({"file": "data/Music/chosen.wav"})
        self.assert_no_music_one_need(r, plan, mention="chosen.wav")

    def test_M8_paths_outside_data_music_are_errors(self):
        self.licensed()
        tone(self.root / "assets" / "x.wav")
        for bad in ("assets/x.wav", "data/Music/../../assets/x.wav", str(self.root / "assets" / "x.wav")):
            r, _ = self.compile({"file": bad})
            self.assertFalse(r["ok"], bad)
            self.assertTrue(any("data/Music" in e for e in r["errors"]), r["errors"])

    def test_P2_backslash_path(self):
        self.licensed()
        r, plan = self.compile({"file": "data\\Music\\tense_dark.wav"})
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(plan["audio"]["music"]["rel"], "data/Music/tense_dark.wav")

    def test_K8_level_bounds_in_the_script(self):
        self.licensed()
        r, _ = self.compile({"file": "data/Music/tense_dark.wav", "level_db": -41})
        self.assertFalse(r["ok"])
        self.assertTrue(any("-40" in e and "-12" in e for e in r["errors"]), r["errors"])
        r, plan = self.compile({"file": "data/Music/tense_dark.wav", "level_db": -40})
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(plan["audio"]["music"]["level_db"], -40.0)

    def test_F3_undecodable_explicit_track(self):
        (self.music / "tense_dark.wav").write_bytes(os.urandom(2048))
        put_lic(self.music / "tense_dark.wav.licence.json", lic())
        r, plan = self.compile({"file": "data/Music/tense_dark.wav"})
        self.assert_no_music_one_need(r, plan, mention="tense_dark.wav")

    def test_F4_short_track_fades_at_its_own_end(self):
        from lib.motion_audio import DUCK_DEFAULTS
        self.licensed("tense_dark.wav", secs=5.0)
        r, plan = self.compile()
        self.assertTrue(r["ok"], r["errors"])
        keys = plan["audio"]["music"]["keyframes"]
        end = int(5.0 * plan["fps"] + 1e-6)                          # never past the track's own end
        self.assertLess(end, plan["duration_frames"])
        self.assertEqual(keys[-1], [end, DUCK_DEFAULTS["floor_db"]])
        self.assertTrue(any("short" in w for w in r["warnings"]), r["warnings"])

    def test_needs_you_key_always_present(self):
        self.licensed()
        r, plan = self.compile()
        self.assertTrue(r["ok"], r["errors"])
        self.assertIn("needs_you", plan)
        self.assertEqual(music_needs(plan), [])
        r, plan = self.compile(False)
        self.assertIn("needs_you", plan)
        self.assertIsInstance(plan["needs_you"], list)

    def test_needs_you_item_shape(self):
        """T4.7 contract: kind, text (EN), text_ar, why, ref (track rel path, or data/Music when no track chosen)."""
        tone(self.music / "tense_dark.wav", 30)
        _, plan = self.compile({"file": "data/Music/tense_dark.wav"})
        it = self.assert_no_music_one_need(_, plan)
        self.assertEqual(set(it), {"kind", "text", "text_ar", "why", "ref"})
        self.assertEqual(it["ref"], "data/Music/tense_dark.wav")
        self.assertTrue(all(isinstance(it[k], str) and it[k].strip() for k in ("text", "text_ar", "why")), it)
        self.assertRegex(it["text_ar"], r"[؀-ۿ]")
        _, plan = self.compile()                                        # auto: no track chosen
        self.assertEqual(self.assert_no_music_one_need(_, plan)["ref"], "data/Music")

    def test_R1_recompile_is_identical(self):
        self.licensed()
        _, p1 = self.compile()
        _, p2 = self.compile()
        self.assertEqual(p1["audio"]["music"], p2["audio"]["music"])
        self.assertEqual(p1.get("needs_you"), p2.get("needs_you"))

    def test_R1b_refusal_recompile_is_identical(self):
        _, p1 = self.compile()
        _, p2 = self.compile()
        self.assertEqual(p1["needs_you"], p2["needs_you"])
        self.assertEqual(len(music_needs(p2)), 1)

    def fp_with(self, music):
        from lib.motion_plan import fingerprint
        s = good_script()
        if music != "__unset__":
            s["music"] = music
        write_json(self.reel.p("01_analysis/motion-script.json"), s)
        return fingerprint(self.reel)

    def test_I1_fingerprint_follows_only_what_the_choice_reads(self):
        chosen = self.licensed("tense_dark.wav", secs=3.0)
        off0, hand0, auto0 = (self.fp_with(False), self.fp_with({"file": "data/Music/tense_dark.wav"}),
                              self.fp_with("__unset__"))
        self.licensed("other_tense.wav", secs=3.0)                        # a track added for another video
        self.assertEqual(self.fp_with(False), off0, "music off reads no track")
        self.assertEqual(self.fp_with({"file": "data/Music/tense_dark.wav"}), hand0, "a hand pick reads its track only")
        self.assertNotEqual(self.fp_with("__unset__"), auto0, "the auto pick reads the whole library")
        put_lic(self.music / "tense_dark.wav.licence.json", lic(source="edited"))
        self.assertNotEqual(self.fp_with({"file": "data/Music/tense_dark.wav"}), hand0, "its licence changed")
        put_lic(self.music / "tense_dark.wav.licence.json", lic())
        self.assertEqual(self.fp_with({"file": "data/Music/tense_dark.wav"}), hand0)
        tone(chosen, 3.0, freq=777)                                         # same length, other sound
        self.assertNotEqual(self.fp_with({"file": "data/Music/tense_dark.wav"}), hand0, "its track was replaced")
        self.assertEqual(self.fp_with(False), off0)

    def junction_music(self, whole_data: bool):
        """data/Music (or the whole data/) reached through a junction / symlink; undone by the cleanup (the link is
        removed as a link, the real folder renamed back; nothing is deleted through a link)."""
        real = self.tmp / ("real-data" if whole_data else "real-music")
        if whole_data:
            data = self.root / "data"
            os.rename(data, real)
            if not make_link(data, real):
                os.rename(real, data)
                self.skipTest("this machine refuses to create a directory link")
            self.addCleanup(lambda: (remove_link(data), os.rename(real, data)))
            music = real / "Music"
            music.mkdir(exist_ok=True)
        else:
            os.rmdir(self.music)
            real.mkdir()
            if not make_link(self.music, real):
                self.music.mkdir()
                self.skipTest("this machine refuses to create a directory link")
            self.addCleanup(lambda: (remove_link(self.music), shutil.rmtree(real, True)))
            music = real
        tone(music / "tense_dark.wav", 3.0)
        put_lic(music / "tense_dark.wav.licence.json", lic())

    def check_clean_with_junction(self, whole_data: bool):
        from lib import ae_bridge, motion_qc, plat
        from lib.motion_build import preconditions
        from lib.motion_plan import fingerprint
        from serve import engine_state as ES
        self.junction_music(whole_data)
        for music in ({"file": "data/Music/tense_dark.wav"}, "__unset__"):
            r, plan = self.compile(music)
            if music != "__unset__":
                self.assertFalse(r["ok"])
                self.assertTrue(any("not an audio track under data/Music" in e for e in r["errors"]), r["errors"])
            elif r["ok"]:
                self.assertIsNone(plan["audio"]["music"], "music is never read through a link")
            fingerprint(self.reel)
            motion_qc.motion_next(self.reel)
            with mock.patch.object(plat, "newest_app", return_value={"name": "AE", "exe": "AfterFX.exe"}), \
                    mock.patch.object(ae_bridge, "status", return_value={"alive": False, "detail": "test"}):
                probs, _ctx = preconditions(self.reel)
            self.assertTrue(probs)
            home = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, home, True)
            with common.use_context(common.Context(root=self.root, home=home)):
                ES._plan_fingerprint(ES._Item(common.Paths(self.root, self.reel.video_id)), True)

    def test_I1_junctioned_data_music_is_clean(self):
        self.check_clean_with_junction(False)

    def test_I1_junctioned_data_is_clean(self):
        self.check_clean_with_junction(True)

    def test_M5_recipe_without_mood_reads_no_track(self):
        src = read_json(self.reel.p("00_inputs/source.json"))
        src["recipe"].pop("music", None)
        write_json(self.reel.p("00_inputs/source.json"), src)
        tone(self.music / "bad_tense.wav", 30)
        put_lic(self.music / "bad_tense.wav.licence.json", lic(license="GPL-3.0"))
        fp0 = self.fp_with("__unset__")
        r, plan = self.compile()
        self.assert_no_music_one_need(r, plan)
        self.assertFalse(any("not valid" in w for w in r["warnings"]), r["warnings"])
        self.licensed("other_tense.wav", secs=3.0)
        self.assertEqual(self.fp_with("__unset__"), fp0, "no mood: the choice reads no track")

    def test_M8_some_licensed_some_damaged_is_worded_apart(self):
        (self.music / "broken_tense.wav").write_bytes(os.urandom(4096))
        put_lic(self.music / "broken_tense.wav.licence.json", lic())          # licensed, cannot be played
        tone(self.music / "nolic_tense.wav", 30)                               # playable, no licence
        r, plan = self.compile()
        it = self.assert_no_music_one_need(r, plan)
        self.assertNotIn("None of the music", it["text"])
        self.assertIn("broken_tense.wav", it["text"])
        self.assertIn("can't be played", it["text"])
        self.assertIn("nolic_tense.wav", it["text"])
        shutil.rmtree(self.music)
        self.music.mkdir()
        tone(self.music / "nolic_tense.wav", 30)
        r, plan = self.compile()
        self.assertIn("None of the music", self.assert_no_music_one_need(r, plan)["text"])

    def test_M10_nfd_and_nfc_names_give_the_same_fingerprint(self):
        nfc = unicodedata.normalize("NFC", "أغنية_tense.wav")
        nfd = unicodedata.normalize("NFD", nfc)
        tone(self.music / nfc, 3.0)
        put_lic(self.music / "licence.json", lic(files="*"))
        fps = (self.fp_with("__unset__"), self.fp_with({"file": f"data/Music/{nfc}"}))
        os.rename(self.music / nfc, self.music / nfd)                    # the same name, as macOS may store it
        # the script text is hashed as written, so the hand pick keeps its NFC spelling; the track state must match
        self.assertEqual((self.fp_with("__unset__"), self.fp_with({"file": f"data/Music/{nfc}"})), fps)

    def test_M3_panel_reads_only_the_licences_the_choice_reads(self):
        """engine_state._motion_inputs: a hard-linked licence of an UNUSED track (refused by the panel's reader) and
        an 8 MB+ music.json with music off never take the approval card away."""
        from serve import engine_state as ES
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        self.licensed("tense_dark.wav", secs=3.0)
        tone(self.music / "unused.wav", 1.0)
        src = put_lic(self.tmp / "shared-licence.json", lic())
        try:
            os.link(src, self.music / "unused.wav.licence.json")
        except OSError:
            self.skipTest("no hard links here")
        (self.music / "music.json").write_bytes(b'{"tracks": []}' + b" " * (8 * 1024 * 1024 + 10))

        def card(music):
            r, _ = self.compile(music)
            self.assertTrue(r["ok"], r["errors"])
            with common.use_context(common.Context(root=self.root, home=home)):
                it = ES._Item(common.Paths(self.root, self.reel.video_id))
                return ES._plan_fingerprint(it, True)
        self.assertIsNotNone(card(False), "music off: no music file is an input")
        self.assertIsNotNone(card({"file": "data/Music/tense_dark.wav"}), "hand pick: only its own licence")

    def test_M4_panel_walks_data_music_once_per_item(self):
        from serve import engine_state as ES
        from lib import motion_audio  # noqa: F401
        tone(self.music / "a.wav", 1.0)
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        real_walk = os.walk
        calls = []

        def walk(top, *a, **kw):
            if Path(top).name == "Music":
                calls.append(top)
            return real_walk(top, *a, **kw)
        self.compile(False)
        with common.use_context(common.Context(root=self.root, home=home)), mock.patch.object(ES.os, "walk", walk):
            it = ES._Item(common.Paths(self.root, self.reel.video_id))
            it.watched(), it.listed(), it._motion_inputs()
        self.assertEqual(len(calls), 1, calls)

    def test_F1_panel_follows_an_absolute_or_linked_hand_pick(self):
        """Minor 1: the panel finds the hand-picked track the way the CLI fingerprint does (given_rel), so replacing
        its bytes changes the panel's cache key; for an absolute path and for a symlink inside data/Music."""
        from serve import engine_state as ES
        f = self.licensed("tense_dark.wav", secs=1.0)
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        act = {"client_root": self.root, "item": self.reel.video_id}
        givens = [str(f.resolve())]
        alias = self.music / "alias.wav"
        try:
            os.symlink(f, alias)
            self.addCleanup(lambda: os.path.lexists(alias) and os.unlink(alias))
            givens.append("data/Music/alias.wav")
        except (OSError, NotImplementedError):
            pass                                                          # no symlink rights here: absolute only
        for given in givens:
            r, _ = self.compile({"file": given})
            self.assertTrue(r["ok"], (given, r["errors"]))
            k0 = ES.PanelFields()._signature(act, home)
            st = f.stat()
            tone(f, 1.0, freq=777)
            os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 5 * 10 ** 9))
            self.assertNotEqual(ES.PanelFields()._signature(act, home), k0, given)

    def test_P3_4_same_size_same_mtime_licence_edit_moves_the_panel_key(self):
        """The licence files the choice reads are content-hashed in the panel's cache key, like the gate files."""
        from serve import engine_state as ES
        f = self.licensed("tense_dark.wav", secs=1.0)
        lf = put_lic(self.music / "tense_dark.wav.licence.json", lic(source="aaaa"))
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        act = {"client_root": self.root, "item": self.reel.video_id}
        for music in ("__unset__", {"file": "data/Music/tense_dark.wav"}):
            put_lic(lf, lic(source="aaaa"))
            self.compile(music)
            st = lf.stat()
            k0 = ES.PanelFields()._signature(act, home)
            lf.write_text(lf.read_text(encoding="utf-8").replace("aaaa", "bbbb"), encoding="utf-8")
            os.utime(lf, ns=(st.st_atime_ns, st.st_mtime_ns))
            self.assertEqual((lf.stat().st_size, lf.stat().st_mtime_ns), (st.st_size, st.st_mtime_ns))
            self.assertNotEqual(ES.PanelFields()._signature(act, home), k0, music)
        self.assertTrue(f.exists())

    def test_P3_5_arabic_wording(self):
        tone(self.music / "tense_x.wav", 30)
        self.licensed("calm_soft.wav")
        r, plan = self.compile()
        it = self.assert_no_music_one_need(r, plan)
        self.assertIn("tense، dark، cinematic", it["text_ar"])          # Arabic list separator between the tags
        self.assertNotIn("tense, dark", it["text_ar"])
        shutil.rmtree(self.music)
        self.music.mkdir()
        self.junction_music(False)
        r, plan = self.compile()
        it = self.assert_no_music_one_need(r, plan)
        self.assertNotIn("shortcut", it["text"].lower())
        self.assertNotIn("shortcut", it["text_ar"].lower())
        self.assertNotIn("واصل له لينك", it["text_ar"])
        self.assertIn("متوصّل بلينك", it["text_ar"])

    def test_F3_mood_mismatch_text_is_arabic_and_names_each_track_once(self):
        """Minor 3: text_ar has no English sentence parts; a fitting unlicensed track is named once."""
        tone(self.music / "tense_x.wav", 30)                               # fits, no licence
        self.licensed("calm_soft.wav")                                      # licensed, no fit
        self.licensed("حزين_غريب.wav")                                      # licensed, no fit, an unknown word
        r, plan = self.compile()
        it = self.assert_no_music_one_need(r, plan)
        for eng in ("moods ", "Arabic mood words not known", "more)", "fits the mood", "no licence file"):
            self.assertNotIn(eng, it["text_ar"], eng)
        self.assertNotIn("tense_x.wav: no licence file", it["text"])
        self.assertNotIn("tense_x.wav: ملوش", it["text_ar"])
        self.assertIn("tense_x.wav fits the mood but lacks a valid licence", it["text"])
        self.assertIn("غريب", it["text_ar"])

    def test_F4_auto_pick_behind_a_junction_says_why(self):
        for whole in (False, True):
            with self.subTest(whole_data=whole):
                self.junction_music(whole)
                r, plan = self.compile()
                it = self.assert_no_music_one_need(r, plan)
                self.assertIn("link", it["text"])
                self.assertNotIn("There is no music in data/Music", it["text"])
                self.doCleanups()
                self.music.mkdir(parents=True, exist_ok=True)

    def test_M3_residual_an_oversized_licence_never_fails_the_panel_closed(self):
        """The engine reads a licence file at most 64 KB + 1 bytes (no link, regular file), so a licence over the
        panel's 8 MB cap is just an invalid licence: the approval card stays, for the auto pick too."""
        from serve import engine_state as ES
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        self.licensed("tense_dark.wav", secs=3.0)
        tone(self.music / "big_tense.wav", 1.0)
        (self.music / "big_tense.wav.licence.json").write_bytes(b"{" + b" " * (8 * 1024 * 1024 + 10) + b"}")
        for music in ("__unset__", {"file": "data/Music/big_tense.wav"}):
            r, _ = self.compile(music)
            with common.use_context(common.Context(root=self.root, home=home)):
                it = ES._Item(common.Paths(self.root, self.reel.video_id))
                if r["ok"]:
                    self.assertIsNotNone(ES._plan_fingerprint(it, True), music)
                self.assertTrue(it.inputs_ok(it._motion_inputs()), music)

    def test_M4_watched_tracks_follow_the_choice(self):
        from serve import engine_state as ES
        self.licensed("tense_dark.wav", secs=1.0)
        tone(self.music / "other.wav", 1.0)
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)

        def tracks(music):
            self.compile(music)
            with common.use_context(common.Context(root=self.root, home=home)):
                w = ES._Item(common.Paths(self.root, self.reel.video_id)).watched()
            return sorted(Path(x).name for x in w if Path(x).suffix == ".wav")
        self.assertEqual(tracks(False), [])
        self.assertEqual(tracks({"file": "data/Music/tense_dark.wav"}), ["tense_dark.wav"])
        self.assertEqual(tracks("__unset__"), ["other.wav", "tense_dark.wav"])

    def test_M11_fingerprint_never_probes(self):
        from lib import motion_audio
        self.licensed("tense_dark.wav", secs=3.0)
        fp0 = self.fp_with("__unset__")
        with mock.patch.object(motion_audio, "probe_duration", side_effect=AssertionError("probed")):
            self.assertEqual(self.fp_with("__unset__"), fp0)
            self.assertEqual(self.fp_with({"file": "data/Music/tense_dark.wav"}),
                             self.fp_with({"file": "data/Music/tense_dark.wav"}))

    def test_I2_panel_sees_music_changes(self):
        """serve/engine_state: data/Music and its licence files are panel inputs, so adding a licence changes the key
        the panel recomputes on (and the motion inputs the approve state reads)."""
        from serve import engine_state as ES
        tone(self.music / "Sub" / "tense_dark.wav", 3.0)
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        act = {"client_root": self.root, "item": self.reel.video_id}
        cache = ES.PanelFields()
        k0 = cache._signature(act, home)
        self.assertIsNotNone(k0)
        lf = put_lic(self.music / "Sub" / "tense_dark.wav.licence.json", lic())
        k1 = cache._signature(act, home)
        self.assertNotEqual(k0, k1, "adding a licence changes what the panel recomputes")
        with common.use_context(common.Context(root=self.root, home=home)):
            it = ES._Item(common.Paths(self.root, self.reel.video_id))
            watched = [str(Path(x).resolve()) for x in it.watched()]
            self.assertIn(str(lf.resolve()), watched)                     # watched, not an input (follow-up M-3)
            self.assertIn(str(self.music.resolve()), watched)
        put_lic(lf, lic(source="edited"))
        os.utime(lf, ns=(time_ns() + 10 ** 9, time_ns() + 10 ** 9))
        self.assertNotEqual(cache._signature(act, home), k1, "editing it does too")

    def test_M2_a_draft_moved_unchanged_is_not_a_licence(self):
        tone(self.music / "tense_dark.wav", 30)
        write_json(self.music / "music.json", {"tracks": [{"file": "tense_dark.wav", "license": "CC0 from a site"}]})
        r, plan = self.compile({"file": "data/Music/tense_dark.wav"})
        self.assert_no_music_one_need(r, plan)
        d = self.reel.p("06_audio/licence-drafts/tense_dark.wav.licence.json")
        draft = json.loads(d.read_text(encoding="utf-8"))
        self.assertEqual(draft["source"], "")
        self.assertEqual(draft["_music_json_said"], "CC0 from a site")
        shutil.copyfile(d, self.music / "tense_dark.wav.licence.json")   # the editor moves it without filling it in
        from lib.motion_audio import music_catalog
        e = next(x for x in music_catalog(self.root) if x["rel"] == "data/Music/tense_dark.wav")
        self.assertFalse(e["licensed"], "an unfilled draft never licenses a track")

    def test_M4_a_fitting_track_rejected_only_for_its_licence_is_named(self):
        tone(self.music / "tense_dark.wav", 30)                           # fits the drama mood, no licence
        self.licensed("happy_light.wav")                                  # licensed, does not fit
        r, plan = self.compile()
        it = self.assert_no_music_one_need(r, plan)
        for field in ("text", "text_ar"):
            self.assertIn("tense_dark.wav", it[field], field)
        self.assertIn("no licence for tense_dark.wav", it["why"])          # the technical reason stays in why
        self.assertIn("tense_dark.wav fits the mood but lacks a valid licence", it["text"])     # M-11 grammar
        self.assertIn("no licence file", it["text"])
        self.assertIn("ملوش ملف ترخيص", it["text_ar"])

    def test_M9_invalid_licence_warnings_only_for_tracks_the_choice_reads(self):
        self.licensed("tense_dark.wav")
        tone(self.music / "bad_tense.wav", 30)
        put_lic(self.music / "bad_tense.wav.licence.json", lic(license="GPL-3.0"))

        def bad_warn(r):
            return [w for w in r["warnings"] if "bad_tense.wav" in w and "not valid" in w]
        r, _ = self.compile()
        self.assertEqual(len(bad_warn(r)), 1, "auto pick: every track is considered")
        r, _ = self.compile({"file": "data/Music/tense_dark.wav"})
        self.assertEqual(bad_warn(r), [], "hand pick: only the chosen track")
        r, _ = self.compile(False)
        self.assertEqual(bad_warn(r), [], "music off: none")
        r, _ = self.compile({"file": "data/Music/bad_tense.wav"})
        self.assertEqual(len(bad_warn(r)), 1)

    def test_R2_R3_licence_changes_make_the_plan_stale(self):
        from lib.motion_plan import fingerprint
        tone(self.music / "tense_dark.wav", 30)
        self.compile()
        fp0 = fingerprint(self.reel)
        put_lic(self.music / "tense_dark.wav.licence.json", lic())
        fp1 = fingerprint(self.reel)
        self.assertNotEqual(fp0, fp1, "adding a licence changes the fingerprint")
        (self.music / "tense_dark.wav.licence.json").unlink()
        self.assertEqual(fingerprint(self.reel), fp0, "removing it again goes back")
        put_lic(self.music / "licence.json", lic(files="*"))
        self.assertNotEqual(fingerprint(self.reel), fp0, "a folder licence counts too")

    def test_no_tracks_leaves_the_fingerprint_as_before(self):
        """Clients without music: T4.6 must not turn approved motion plans stale. The value was computed with the
        pre-T4.6 fingerprint (b61f808) for this fixed fixture, not with T4.6 itself."""
        from lib import motion_plan
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        fx = frozen_fixture(base)
        with mock.patch.object(motion_plan, "motion_cfg", return_value=FROZEN_CFG):
            self.assertEqual(motion_plan.fingerprint(fx), FROZEN_FP)
            music = fx.root / "data" / "Music"
            (music / "notes").mkdir(parents=True)
            (music / "notes" / "readme.txt").write_text("x", encoding="utf-8")
            self.assertEqual(motion_plan.fingerprint(fx), FROZEN_FP, "a non-audio file is not a track")

    def test_fingerprint_sees_a_same_length_replacement_but_not_a_copy(self):
        f = self.licensed(secs=3.0)
        for music in ("__unset__", {"file": "data/Music/tense_dark.wav"}):   # the auto pick and a hand pick
            tone(f, 3.0)
            fp0 = self.fp_with(music)
            st = f.stat()
            os.utime(f, (st.st_atime + 3600, st.st_mtime + 3600))        # a copied folder: new times, same bytes
            self.assertEqual(self.fp_with(music), fp0, music)
            tone(f, 3.0, freq=777)                                       # another track of the very same length
            self.assertEqual(f.stat().st_size, st.st_size)
            self.assertNotEqual(self.fp_with(music), fp0, music)

    def test_I1_bad_licences_never_break_the_fingerprint(self):
        from lib.motion_plan import fingerprint
        tone(self.music / "deep.wav", 2)
        tone(self.music / "big" / "big.wav", 2)
        (self.music / "deep.wav.licence.json").write_text('{"a": ' + "[" * 30000 + "]" * 30000 + "}", encoding="utf-8")
        put_lic(self.music / "big" / "licence.json", lic(files="*", note="x" * 70000))
        r, plan = self.compile(False)
        self.assertTrue(r["ok"], r["errors"])
        fingerprint(self.reel)

    def test_I3_reasons_of_the_unlicensed_tracks(self):
        tone(self.music / "a_tense.wav", 30)                                       # no licence file
        tone(self.music / "b_tense.wav", 30)
        put_lic(self.music / "b_tense.wav.licence.json", lic(license="GPL-3.0"))  # invalid
        tone(self.music / "c_tense.wav", 30)
        (self.music / "c_tense.wav.licence.json").write_bytes(b"")              # invalid (empty)
        tone(self.music / "d_tense.wav", 30)                                       # a 4th: not listed
        r, plan = self.compile()
        it = self.assert_no_music_one_need(r, plan)
        for field in ("why", "text", "text_ar"):
            self.assertIn("a_tense.wav", it[field], field)
            self.assertIn("GPL-3.0", it[field], field)
            self.assertIn("c_tense.wav", it[field], field)
            self.assertNotIn("d_tense.wav", it[field], field)
        self.assertIn("1 more", it["why"])
        bad = [w for w in r["warnings"] if "licence file" in w and "not valid" in w]
        self.assertEqual(len(bad), 2, r["warnings"])
        self.assertTrue(any("b_tense.wav" in w for w in bad) and any("c_tense.wav" in w for w in bad), bad)

    def test_arabic_named_track_is_picked_for_its_mood(self):
        self.licensed("توتر.wav")
        r, plan = self.compile()
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(plan["audio"]["music"]["rel"], "data/Music/توتر.wav")
        self.assertEqual(music_needs(plan), [])

    def test_unknown_arabic_mood_word_is_in_the_reasons(self):
        self.licensed("غريب.wav")
        r, plan = self.compile()
        it = self.assert_no_music_one_need(r, plan)
        for field in ("why", "text", "text_ar"):
            self.assertIn("غريب", it[field], field)

    def drafts(self) -> dict:
        d = self.reel.p("06_audio/licence-drafts")
        return {f.relative_to(d).as_posix(): f.read_bytes() for f in sorted(d.rglob("*")) if f.is_file()} \
            if d.exists() else {}

    def test_licence_draft_for_the_chosen_unlicensed_track(self):
        """Pre-mortem 2: a filled licence draft in the project's output/, never in data/; the item points to it."""
        tone(self.music / "Calm" / "tense_dark.wav", 30)
        write_json(self.music / "music.json", {"tracks": [{"file": "tense_dark.wav", "license": "Artlist #123"}]})
        data_before = tree_hash(self.root / "data", self.root / "assets")
        r, plan = self.compile({"file": "data/Music/Calm/tense_dark.wav"})
        it = self.assert_no_music_one_need(r, plan)
        self.assertEqual(tree_hash(self.root / "data", self.root / "assets"), data_before)
        d = self.drafts()
        self.assertIn("Calm/tense_dark.wav.licence.json", d)
        draft = json.loads(d["Calm/tense_dark.wav.licence.json"].decode("utf-8"))
        self.assertIn(draft["license"], ("commercial",))                 # guessed, the editor confirms it
        self.assertEqual(draft["source"], "")                             # M2: never filled in by the engine
        self.assertEqual(draft["_music_json_said"], "Artlist #123")
        for k in ("attribution", "proof"):
            self.assertIn(k, draft)
        self.assertEqual(draft["_move_to"], "data/Music/Calm/tense_dark.wav.licence.json")
        self.assertIn("README.txt", d)
        self.assertIn("data/Music/Calm/tense_dark.wav.licence.json", d["README.txt"].decode("utf-8"))
        where = "output/projects/EP12_R01_MO/06_audio/licence-drafts/Calm/tense_dark.wav.licence.json"
        self.assertIn(where, it["text"])
        self.assertIn(where, it["text_ar"])

    def test_licence_drafts_for_the_unlicensed_mood_tracks_are_idempotent(self):
        tone(self.music / "a_tense.wav", 30)
        tone(self.music / "b_tense.wav", 30)
        put_lic(self.music / "b_tense.wav.licence.json", lic(license="GPL-3.0", source="a forum"))
        tone(self.music / "happy.wav", 30)                               # no mood fit: no draft
        r, plan = self.compile()
        self.assert_no_music_one_need(r, plan)
        d1 = self.drafts()
        self.assertEqual(sorted(k for k in d1 if k.endswith(".json")),
                         ["a_tense.wav.licence.json", "b_tense.wav.licence.json"])
        b = json.loads(d1["b_tense.wav.licence.json"].decode("utf-8"))
        self.assertEqual(b["source"], "")                                # M2: never filled in by the engine
        self.assertEqual(b["_licence_file_said"]["source"], "a forum")   # what the broken licence already said
        self.compile()
        self.assertEqual(self.drafts(), d1, "a second run writes the same files, byte for byte")
        f = self.reel.p("06_audio/licence-drafts/a_tense.wav.licence.json")
        f.write_text('{"license": "CC0-1.0", "source": "being filled in"}', encoding="utf-8")
        self.compile()
        self.assertEqual(f.read_text(encoding="utf-8"), '{"license": "CC0-1.0", "source": "being filled in"}',
                         "a draft the editor is filling in is never overwritten")

    def test_no_drafts_when_music_is_off_or_licensed(self):
        tone(self.music / "tense_dark.wav", 30)
        self.compile(False)
        self.assertEqual(self.drafts(), {})
        put_lic(self.music / "tense_dark.wav.licence.json", lic())
        self.compile()
        self.assertEqual(self.drafts(), {})

    def test_I4_licence_template_in_the_needs_item(self):
        tone(self.music / "tense_dark.wav", 30)
        for music in ("__unset__", {"file": "data/Music/tense_dark.wav"}):
            r, plan = self.compile(music)
            why = self.assert_no_music_one_need(r, plan)["why"]
            for k in ('"license"', '"source"', '"attribution"', '"proof"', '"files"', "CC0-1.0", "commercial", "client"):
                self.assertIn(k, why, (music, k))
            self.assertIn("نموذج", why)
            for ar in ("الإسناد", "الإثبات", "الفولدر"):                    # M6: the field notes in Arabic too
                self.assertIn(ar, why, (music, ar))

    def test_editor_text_has_no_developer_words(self):
        """Review minor: the editor reads these; no engine commands, script fields or recipe jargon."""
        banned = ("motion-plan", "music.file", "recipe", "licence json", "license json", "leave the music to the editor",
                  "ريسيبي", "سكريبت", "متعلّم", "للمونتير", "utf-8", "json object", "nested", "regular file", "malformed")
        cases = [("no folder", lambda: shutil.rmtree(self.music), "__unset__"),
                 ("unlicensed", lambda: tone(self.music / "tense_dark.wav", 30), "__unset__"),
                 ("explicit", lambda: tone(self.music / "tense_dark.wav", 30), {"file": "data/Music/tense_dark.wav"}),
                 ("no match", lambda: self.licensed("happy_light.wav"), "__unset__"),
                 ("broken", lambda: (self.music / "x.wav").write_bytes(os.urandom(999)) and
                  put_lic(self.music / "x.wav.licence.json", lic()), {"file": "data/Music/x.wav"}),
                 ("bad json", lambda: tone(self.music / "tense_dark.wav", 30) and
                  put_lic(self.music / "tense_dark.wav.licence.json", "[1, 2"), {"file": "data/Music/tense_dark.wav"}),
                 ("not object", lambda: tone(self.music / "tense_dark.wav", 30) and
                  put_lic(self.music / "tense_dark.wav.licence.json", "[1, 2]"), "__unset__"),
                 ("utf16", lambda: tone(self.music / "tense_dark.wav", 30) and
                  (self.music / "tense_dark.wav.licence.json").write_bytes(json.dumps(lic()).encode("utf-16")),
                  "__unset__")]
        for name, setup, music in cases:
            shutil.rmtree(self.music, ignore_errors=True)
            self.music.mkdir(parents=True)
            setup()
            r, plan = self.compile(music)
            it = self.assert_no_music_one_need(r, plan)
            for field in ("text", "text_ar"):
                low = it[field].lower()
                for w in banned:
                    self.assertNotIn(w, low, (name, field, w))
            for eng in ("moods ", "Arabic mood words not known", "more)", "fits the mood", "no licence file",
                        "can't be read", "isn't allowed"):
                self.assertNotIn(eng, it["text_ar"], (name, eng))
            md = self.reel.p("01_analysis/motion-plan.md").read_text(encoding="utf-8")
            self.assertNotIn("none — music:", md, name)
            if name == "no match":
                self.assertIn("متصنّف على المود", it["text_ar"])

    def test_X1_handoff_lists_music_once(self):
        from lib.handoff import motion_readme
        tone(self.music / "tense_dark.wav", 30)
        r, plan = self.compile()
        self.assertTrue(r["ok"], r["errors"])
        text = motion_readme(self.reel).read_text(encoding="utf-8")
        needs = text.split("## Needs you", 1)[1].split("\n## ", 1)[0]
        self.assertEqual(sum(1 for ln in needs.splitlines() if "music" in ln.lower()), 1, needs)

    def test_I4_handoff_shows_the_licence_template(self):
        from lib.handoff import motion_readme
        tone(self.music / "tense_dark.wav", 30)
        r, _ = self.compile()
        self.assertTrue(r["ok"], r["errors"])
        text = motion_readme(self.reel).read_text(encoding="utf-8")
        for k in ('"license"', '"source"', '"attribution"', '"proof"', '"files"', "CC0-1.0"):
            self.assertIn(k, text, k)

    def test_handoff_names_the_music_licence(self):
        from lib.handoff import motion_readme
        self.licensed(license="CC-BY-4.0", attribution="Music: Test Artist (CC BY 4.0)")
        r, _ = self.compile()
        self.assertTrue(r["ok"], r["errors"])
        text = motion_readme(self.reel).read_text(encoding="utf-8")
        self.assertIn("data/Music/tense_dark.wav", text)
        self.assertIn("Music: Test Artist (CC BY 4.0)", text)


class TestArabicClientPath(MusicPlanCase):
    TMP_SUB = "عميل-موسيقى"

    def test_A5_arabic_root_and_track(self):
        from lib.motion_build import write_job
        name = "توتر_tense_dark.wav"
        self.licensed(name)
        r, plan = self.compile()
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(plan["audio"]["music"]["rel"], f"data/Music/{name}")
        self.assertTrue(Path(plan["audio"]["music"]["file"]).exists())
        job = write_job(self.reel)
        job_text = job.read_text(encoding="ascii")                      # the job stays ASCII (escaped)
        self.assertEqual(json.loads(job_text)["plan"]["audio"]["music"]["rel"], f"data/Music/{name}")


# --------------------------------------------------------------------------- build with a fake After Effects (B*)
class TestMusicBuild(MusicPlanCase):
    def setUp(self):
        super().setUp()
        use_machine_fonts(self)
        from lib import ae_bridge, ae_probe, motion_build, plat
        self.ae = FakeAE(readback=lambda job: dict(rb_from_plan(job), audio=rb_audio(job["plan"])))
        for obj, attr, val in ((ae_bridge, "submit", self.ae.submit), (ae_bridge, "status", self.ae.status),
                               (ae_probe, "verdict_ok", lambda v: v == "26.0"),
                               (plat, "newest_app", lambda key: {"name": "Adobe After Effects 2026", "exe": "AfterFX.exe"})):
            p = mock.patch.object(obj, attr, val)
            p.start()
            self.addCleanup(p.stop)
        self.mb = motion_build
        for f in (motion_build.aep_path(self.reel), self.reel.p("04_after_effects/motion-build-result.json")):
            f.unlink(missing_ok=True)
        shutil.rmtree(self.reel.p("04_after_effects/project/backups"), ignore_errors=True)
        common.set_status(self.reel, "ANALYZED", "test reset")

    def approve(self):
        from lib.motion_plan import fingerprint
        write_json(self.reel.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor",
                                                                   "plan_fingerprint": fingerprint(self.reel)})

    def test_B1_licensed_music_reaches_after_effects(self):
        self.licensed()
        r, _ = self.compile()
        self.assertTrue(r["ok"], r["errors"])
        self.approve()
        b = self.mb.build(self.reel)
        self.assertEqual(b["status"], "PROJECT_ASSEMBLED", b)
        m = self.ae.jobs[-1]["plan"]["audio"]["music"]
        self.assertEqual(m["rel"], "data/Music/tense_dark.wav")
        self.assertTrue(m["keyframes"])
        self.assertTrue(b["comparison"]["ok"], b["comparison"])

    def test_R4_rebuild_twice_one_music_layer_each(self):
        self.licensed()
        self.compile()
        self.approve()
        for _ in range(2):
            self.assertEqual(self.mb.build(self.reel)["status"], "PROJECT_ASSEMBLED")
        self.assertEqual(len(self.ae.jobs), 2)
        self.assertTrue(all(j["plan"]["audio"]["music"] for j in self.ae.jobs))

        def doubled(job):
            a = rb_audio(job["plan"])
            a.append(dict(next(x for x in a if x["name"] == "MUSIC")))
            return dict(rb_from_plan(job), audio=a)
        self.ae.readback = doubled
        b = self.mb.build(self.reel)
        self.assertEqual(b["status"], "FAILED")
        self.assertTrue(any("MUSIC" in x for x in b["reasons"]), b["reasons"])

    def test_B2_unlicensed_builds_without_music(self):
        tone(self.music / "tense_dark.wav", 30)
        r, plan = self.compile()
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(len(music_needs(plan)), 1)
        self.approve()
        b = self.mb.build(self.reel)
        self.assertEqual(b["status"], "PROJECT_ASSEMBLED", b)
        self.assertIsNone(self.ae.jobs[-1]["plan"]["audio"]["music"])

    def test_R3_licence_removed_after_approval_refuses_the_build(self):
        self.licensed()
        self.compile()
        self.approve()
        (self.music / "tense_dark.wav.licence.json").unlink()
        b = self.mb.build(self.reel)
        self.assertEqual(b["status"], "REFUSED", b)
        self.assertTrue(any("stale" in x and "music/licences" in x for x in b["reasons"]), b["reasons"])
        self.assertEqual(self.ae.jobs, [])

    def test_same_length_replacement_after_approval_refuses_the_build(self):
        f = self.licensed(secs=3.0)
        self.compile()
        self.approve()
        tone(f, 3.0, freq=777)
        b = self.mb.build(self.reel)
        self.assertEqual(b["status"], "REFUSED", b)
        self.assertEqual(self.ae.jobs, [])


if __name__ == "__main__":
    unittest.main()
