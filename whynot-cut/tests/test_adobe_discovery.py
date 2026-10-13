"""3.0 T2.11: one Adobe app discovery (plat.find_adobe_apps / newest_app / aerender_path / adobe_report).

Windows: registry (HKLM\\SOFTWARE\\Adobe\\<app>\\<ver>), App Paths, the Program Files scan. macOS: mdfind by bundle id,
/Applications and ~/Applications, (Beta) builds. Overrides WHYNOT_PREMIERE_APP, WHYNOT_AE_APP, WHYNOT_AERENDER.
Every test injects the registry reader, the mdfind runner and the folders: nothing reads the real registry.
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine" / "reel"))

from lib import plat  # noqa: E402
from lib.errors import Guidance  # noqa: E402

APP_PATHS = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\"


class FakeRegistry:
    """HKLM as {key path: {value name: value}}; subkeys come from the longer paths."""

    def __init__(self, tree=None):
        self.tree = dict(tree or {})

    def values(self, path):
        return dict(self.tree.get(path, {}))

    def subkeys(self, path):
        pre = path + "\\"
        return sorted({k[len(pre):].split("\\")[0] for k in self.tree if k.startswith(pre)})


class NoRegistry:
    def values(self, path):
        raise AssertionError("the registry is a Windows thing; this platform never reads it")

    subkeys = values


def touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


def win_sources(env=None, registry=None, program_dirs=(), file_version=None):
    """file_version: exe path -> version (a dict keyed by the exe's file name, or a callable); default: unreadable."""
    if isinstance(file_version, dict):
        table = file_version
        file_version = lambda p: table.get(Path(p).name)                      # noqa: E731
    return plat.AdobeSources(env=env or {}, registry=registry or FakeRegistry(), os_name="windows",
                             program_dirs=list(program_dirs), mdfind=None, mac_app_dirs=[],
                             file_version=file_version or (lambda p: None))


def mac_sources(app_dirs, mdfind, env=None):
    return plat.AdobeSources(env=env or {}, registry=NoRegistry(), os_name="macos", program_dirs=[],
                             mdfind=mdfind, mac_app_dirs=list(app_dirs))


class WindowsLayout(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.pf = self.tmp / "Program Files"

    def adobe(self, folder, exe):
        return touch(self.pf / "Adobe" / folder / exe)

    def premiere(self, year=2026):
        return self.adobe(f"Adobe Premiere Pro {year}", "Adobe Premiere Pro.exe")

    def ae(self, year=2026):
        exe = self.adobe(f"Adobe After Effects {year}", "Support Files/AfterFX.exe")
        touch(exe.parent / "aerender.exe")
        return exe

    def photoshop(self, year=2026):
        return self.adobe(f"Adobe Photoshop {year}", "Photoshop.exe")


class WindowsRegistry(WindowsLayout):
    def test_premiere_found_through_the_registry_even_without_an_install_path_value(self):
        # the real Premiere 26 key has no InstallPath: only presets / plug-in paths below the app folder
        exe = self.premiere()
        app = exe.parent
        reg = FakeRegistry({
            "SOFTWARE\\Adobe\\Premiere Pro\\26.0": {
                "SequencePresetsPath": str(app / "Settings" / "SequencePresets"),
                "PluginInstallPath": str(app / "Plug-ins" / "Common"),
                "CommonPluginInstallPath": str(self.pf / "Adobe" / "Common" / "Plug-ins" / "7.0" / "MediaCore")},
            "SOFTWARE\\Adobe\\Premiere Pro\\CurrentVersion": {"": "26.0"}})
        a = plat.newest_app("premiere", win_sources(registry=reg, file_version={"Adobe Premiere Pro.exe": "26.5.2.5"}))
        self.assertEqual(Path(a["exe"]), exe)
        self.assertEqual(Path(a["folder"]), app)
        self.assertEqual((a["source"], a["version"], a["year"], a["name"]),
                         ("registry", "26.5.2.5", 2026, "Adobe Premiere Pro 2026"))

    def test_after_effects_install_path_is_the_support_files_folder(self):
        exe = self.ae()
        reg = FakeRegistry({"SOFTWARE\\Adobe\\After Effects\\26.0": {"InstallPath": str(exe.parent) + "\\"}})
        a = plat.newest_app("after_effects", win_sources(registry=reg))
        self.assertEqual(Path(a["exe"]), exe)
        self.assertEqual(Path(a["folder"]), exe.parent.parent)
        self.assertEqual(a["source"], "registry")

    def test_photoshop_application_path(self):
        exe = self.photoshop()
        reg = FakeRegistry({"SOFTWARE\\Adobe\\Photoshop\\200.0": {"ApplicationPath": str(exe.parent) + "\\"}})
        a = plat.newest_app("photoshop", win_sources(registry=reg))
        self.assertEqual((Path(a["exe"]), a["source"]), (exe, "registry"))

    def test_the_newest_version_wins_whatever_order_the_registry_lists_them(self):
        old, new = self.premiere(2025), self.premiere(2026)
        reg = FakeRegistry({
            "SOFTWARE\\Adobe\\Premiere Pro\\25.0": {"InstallPath": str(old.parent)},
            "SOFTWARE\\Adobe\\Premiere Pro\\26.0": {"InstallPath": str(new.parent)}})
        apps = plat.find_adobe_apps("premiere", win_sources(registry=reg))
        self.assertEqual([Path(a["exe"]) for a in apps], [new, old])
        self.assertEqual(Path(plat.newest_app("premiere", win_sources(registry=reg))["exe"]), new)

    def test_a_stale_registry_entry_without_the_exe_is_ignored(self):
        reg = FakeRegistry({"SOFTWARE\\Adobe\\Premiere Pro\\26.0": {"InstallPath": str(self.pf / "Gone")}})
        self.assertIsNone(plat.newest_app("premiere", win_sources(registry=reg)))

    def test_custom_install_folder_without_a_year_ranks_by_registry_version(self):
        a25 = touch(self.tmp / "tools" / "PPro A" / "Adobe Premiere Pro.exe")
        a26 = touch(self.tmp / "tools" / "PPro B" / "Adobe Premiere Pro.exe")
        reg = FakeRegistry({"SOFTWARE\\Adobe\\Premiere Pro\\25.6": {"InstallPath": str(a25.parent)},
                            "SOFTWARE\\Adobe\\Premiere Pro\\26.0": {"InstallPath": str(a26.parent)}})
        self.assertEqual(Path(plat.newest_app("premiere", win_sources(registry=reg))["exe"]), a26)


class WindowsAppPathsAndScan(WindowsLayout):
    def test_app_paths_default_value_is_read_with_its_quotes_removed(self):
        exe = self.premiere()
        reg = FakeRegistry({APP_PATHS + "Adobe Premiere Pro.exe": {"": f'"{exe}"', "Path": str(exe.parent) + "\\"}})
        a = plat.newest_app("premiere", win_sources(registry=reg))
        self.assertEqual((Path(a["exe"]), a["source"]), (exe, "app-paths"))

    def test_app_paths_for_after_effects_resolves_the_app_folder(self):
        exe = self.ae()
        reg = FakeRegistry({APP_PATHS + "AfterFX.exe": {"": str(exe), "Path": str(exe.parent) + "\\"}})
        a = plat.newest_app("after_effects", win_sources(registry=reg))
        self.assertEqual((Path(a["exe"]), Path(a["folder"]), a["source"]), (exe, exe.parent.parent, "app-paths"))

    def test_program_files_scan_still_finds_every_app(self):
        self.premiere(), self.ae(), self.photoshop()
        self.adobe("Adobe Media Encoder 2026", "Adobe Media Encoder.exe")
        src = win_sources(program_dirs=[self.pf])
        self.assertEqual({a["key"] for a in plat.find_adobe_apps(None, src)},
                         {"premiere", "after_effects", "photoshop", "media_encoder"})
        self.assertEqual(plat.newest_app("premiere", src)["source"], "scan")

    def test_one_install_seen_by_registry_app_paths_and_scan_is_one_app_with_the_best_source(self):
        exe = self.premiere()
        reg = FakeRegistry({"SOFTWARE\\Adobe\\Premiere Pro\\26.0": {"InstallPath": str(exe.parent)},
                            APP_PATHS + "Adobe Premiere Pro.exe": {"": str(exe)}})
        apps = plat.find_adobe_apps("premiere", win_sources(registry=reg, program_dirs=[self.pf]))
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["source"], "registry")
        self.assertEqual(apps[0]["sources"], ["registry", "app-paths", "scan"])
        self.assertEqual(apps[0]["reg_version"], "26.0")

    def test_a_beta_build_is_never_preferred_to_a_release_but_found_when_alone(self):
        beta = self.adobe("Adobe Premiere Pro (Beta)", "Adobe Premiere Pro.exe")
        src = win_sources(program_dirs=[self.pf])
        only = plat.newest_app("premiere", src)
        self.assertEqual((Path(only["exe"]), only["beta"]), (beta, True))
        rel = self.premiere(2025)
        apps = plat.find_adobe_apps("premiere", src)
        self.assertEqual([Path(a["exe"]) for a in apps], [rel, beta])

    def test_nothing_installed_gives_nothing(self):
        src = win_sources(program_dirs=[self.pf])
        self.assertEqual(plat.find_adobe_apps(None, src), [])
        self.assertIsNone(plat.newest_app("premiere", src))
        self.assertIsNone(plat.aerender_path(src))


class Overrides(WindowsLayout):
    def test_premiere_override_to_an_exe_wins_over_discovery(self):
        self.premiere(2026)
        other = touch(self.tmp / "portable" / "Adobe Premiere Pro.exe")
        src = win_sources(env={"WHYNOT_PREMIERE_APP": str(other)}, program_dirs=[self.pf])
        a = plat.newest_app("premiere", src)
        self.assertEqual((Path(a["exe"]), a["source"]), (other, "override"))
        self.assertEqual(len(plat.find_adobe_apps("premiere", src)), 2)

    def test_premiere_override_may_name_the_install_folder(self):
        exe = self.premiere(2024)
        src = win_sources(env={"WHYNOT_PREMIERE_APP": str(exe.parent)})
        a = plat.newest_app("premiere", src)
        self.assertEqual((Path(a["exe"]), a["source"], a["year"]), (exe, "override", 2024))

    def test_after_effects_override_may_name_the_app_folder_above_support_files(self):
        exe = self.ae(2025)
        src = win_sources(env={"WHYNOT_AE_APP": str(exe.parent.parent)})
        self.assertEqual(Path(plat.newest_app("after_effects", src)["exe"]), exe)

    def test_a_missing_override_is_guidance_that_names_the_variable(self):
        for var, key in (("WHYNOT_PREMIERE_APP", "premiere"), ("WHYNOT_AE_APP", "after_effects")):
            with self.subTest(var=var):
                src = win_sources(env={var: str(self.tmp / "nope")}, program_dirs=[self.pf])
                with self.assertRaises(Guidance) as cm:
                    plat.newest_app(key, src)
                self.assertIn(var, cm.exception.error)
                self.assertIn(str(self.tmp / "nope"), cm.exception.error)
                self.assertIn(var, cm.exception.how)

    def test_an_override_does_not_break_other_apps(self):
        self.photoshop()
        src = win_sources(env={"WHYNOT_PREMIERE_APP": str(self.tmp / "nope")}, program_dirs=[self.pf])
        self.assertEqual(plat.newest_app("photoshop", src)["key"], "photoshop")

    def test_an_empty_override_is_ignored(self):
        self.premiere()
        src = win_sources(env={"WHYNOT_PREMIERE_APP": "  "}, program_dirs=[self.pf])
        self.assertEqual(plat.newest_app("premiere", src)["source"], "scan")

    def test_override_folder_without_the_app_in_it_is_guidance(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        with self.assertRaises(Guidance) as cm:
            plat.newest_app("premiere", win_sources(env={"WHYNOT_PREMIERE_APP": str(empty)}))
        self.assertIn("WHYNOT_PREMIERE_APP", cm.exception.error)

    def test_aerender_override_is_validated_and_wins(self):
        self.ae()
        mine = touch(self.tmp / "custom" / "aerender.exe")
        src = win_sources(env={"WHYNOT_AERENDER": str(mine)}, program_dirs=[self.pf])
        self.assertEqual(plat.aerender_path(src), mine)
        self.assertEqual(plat.aerender_info(src), {"path": str(mine), "source": "override"})
        bad = win_sources(env={"WHYNOT_AERENDER": str(self.tmp / "nope.exe")}, program_dirs=[self.pf])
        with self.assertRaises(Guidance) as cm:
            plat.aerender_path(bad)
        self.assertIn("WHYNOT_AERENDER", cm.exception.error)
        self.assertIn("WHYNOT_AERENDER", cm.exception.how)

    def test_aerender_override_to_a_folder_is_not_an_executable(self):
        with self.assertRaises(Guidance):
            plat.aerender_path(win_sources(env={"WHYNOT_AERENDER": str(self.tmp)}))

    def test_aerender_sits_next_to_the_newest_after_effects_that_has_one(self):
        exe = self.ae(2026)
        (exe.parent / "aerender.exe").unlink()                      # 2026 is broken; 2025 is whole
        old = self.ae(2025)
        src = win_sources(program_dirs=[self.pf])
        self.assertEqual(plat.aerender_path(src), old.parent / "aerender.exe")
        self.assertEqual(plat.aerender_info(src)["source"], "scan")

    def test_aerender_follows_the_ae_override(self):
        self.ae(2026)
        old = self.ae(2024)
        src = win_sources(env={"WHYNOT_AE_APP": str(old)}, program_dirs=[self.pf])
        self.assertEqual(plat.aerender_path(src), old.parent / "aerender.exe")

    def test_environment_is_read_at_call_time(self):
        self.premiere()
        other = touch(self.tmp / "p2" / "Adobe Premiere Pro.exe")
        real = dict(patch_os=mock.patch.object(plat, "IS_WIN", True), patch_mac=mock.patch.object(plat, "IS_MAC", False),
                    dirs=mock.patch.object(plat, "_program_dirs", lambda: [self.pf]),
                    reg=mock.patch.object(plat, "WinRegistry", FakeRegistry))
        with real["patch_os"], real["patch_mac"], real["dirs"], real["reg"]:
            with mock.patch.dict("os.environ", {"WHYNOT_PREMIERE_APP": str(other)}):
                self.assertEqual(Path(plat.newest_app("premiere")["exe"]), other)
            with mock.patch.dict("os.environ", {"WHYNOT_PREMIERE_APP": ""}):
                self.assertEqual(plat.newest_app("premiere")["source"], "scan")


class MacDiscovery(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.apps = self.tmp / "Applications"
        self.user_apps = self.tmp / "home" / "Applications"
        self.asked = []

    def bundle(self, base: Path, folder, name, version=None):
        app = base / folder / f"{name}.app" if folder else base / f"{name}.app"
        (app / "Contents").mkdir(parents=True)
        if version:
            (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": version}))
        return app

    def mdfind(self, results):
        def run(query):
            self.asked.append(query)
            return [str(p) for p in results]
        return run

    def src(self, results=(), env=None):
        return mac_sources([self.apps, self.user_apps], self.mdfind(results), env)

    def test_mdfind_asks_for_each_app_by_bundle_identifier(self):
        plat.find_adobe_apps(None, self.src())
        joined = "\n".join(self.asked)
        for bid in ("com.adobe.PremierePro*", "com.adobe.AfterEffects*", "com.adobe.Photoshop*"):
            self.assertIn(f"kMDItemCFBundleIdentifier == '{bid}'", joined)

    def test_app_found_by_mdfind_outside_applications(self):
        app = self.bundle(self.tmp / "Volumes" / "Fast", None, "Adobe Premiere Pro 2026", "26.0.1")
        a = plat.newest_app("premiere", self.src([app]))
        self.assertEqual((Path(a["exe"]), a["source"], a["version"], a["year"]),
                         (app, "mdfind", "26.0.1", 2026))
        self.assertEqual(a["name"], "Adobe Premiere Pro 2026")

    def test_applications_and_user_applications_are_scanned(self):
        sys_app = self.bundle(self.apps, "Adobe Premiere Pro 2025", "Adobe Premiere Pro 2025", "25.2")
        usr_app = self.bundle(self.user_apps, None, "Adobe Photoshop 2026", "27.0")
        src = self.src()
        self.assertEqual(Path(plat.newest_app("premiere", src)["exe"]), sys_app)
        self.assertEqual(Path(plat.newest_app("premiere", src)["folder"]), sys_app.parent)
        ps = plat.newest_app("photoshop", src)
        self.assertEqual((Path(ps["exe"]), ps["source"]), (usr_app, "scan"))

    def test_same_bundle_from_mdfind_and_scan_is_one_app_listing_both_sources(self):
        app = self.bundle(self.apps, "Adobe Premiere Pro 2026", "Adobe Premiere Pro 2026", "26.0")
        apps = plat.find_adobe_apps("premiere", self.src([app]))
        self.assertEqual(len(apps), 1)
        self.assertEqual((apps[0]["source"], apps[0]["sources"]), ("mdfind", ["mdfind", "scan"]))

    def test_newest_year_then_version_wins(self):
        a25 = self.bundle(self.apps, "Adobe Premiere Pro 2025", "Adobe Premiere Pro 2025", "25.6")
        a26 = self.bundle(self.apps, "Adobe Premiere Pro 2026", "Adobe Premiere Pro 2026", "26.0")
        for results in ([a25, a26], [a26, a25]):
            self.assertEqual(Path(plat.newest_app("premiere", self.src(results))["exe"]), a26)

    def test_beta_builds_are_found_but_not_preferred(self):
        beta = self.bundle(self.apps, "Adobe Premiere Pro (Beta)", "Adobe Premiere Pro (Beta)", "27.0")
        self.assertTrue(plat.newest_app("premiere", self.src())["beta"])
        rel = self.bundle(self.apps, "Adobe Premiere Pro 2026", "Adobe Premiere Pro 2026", "26.0")
        apps = plat.find_adobe_apps("premiere", self.src([beta, rel]))
        self.assertEqual([Path(a["exe"]) for a in apps], [rel, beta])

    def test_mdfind_noise_is_ignored(self):
        good = self.bundle(self.apps, "Adobe After Effects 2026", "Adobe After Effects 2026", "26.0")
        trash = self.bundle(self.tmp / ".Trash", None, "Adobe After Effects 2024", "24.0")
        render = self.bundle(self.apps, "Adobe After Effects 2026", "Adobe After Effects Render Engine")
        nested = self.bundle(good / "Contents" / "Helpers", None, "Adobe After Effects Helper")
        gone = self.tmp / "Applications" / "Adobe After Effects 2023.app"          # a stale Spotlight entry
        other = self.bundle(self.apps, None, "Some Other Adobe Thing")
        apps = plat.find_adobe_apps("after_effects", self.src([good, trash, render, nested, gone, other]))
        self.assertEqual([Path(a["exe"]) for a in apps], [good])

    def test_a_failing_mdfind_falls_back_to_the_scan(self):
        app = self.bundle(self.apps, "Adobe Premiere Pro 2026", "Adobe Premiere Pro 2026", "26.0")

        def broken(query):
            raise OSError("mdfind: not found")
        src = mac_sources([self.apps], broken)
        self.assertEqual(Path(plat.newest_app("premiere", src)["exe"]), app)

    def test_missing_info_plist_gives_no_version_but_still_an_app(self):
        app = self.bundle(self.apps, "Adobe Photoshop 2026", "Adobe Photoshop 2026")
        a = plat.newest_app("photoshop", self.src())
        self.assertEqual((Path(a["exe"]), a["version"]), (app, None))

    def test_aerender_is_in_the_after_effects_folder(self):
        app = self.bundle(self.apps, "Adobe After Effects 2026", "Adobe After Effects 2026", "26.0")
        self.assertIsNone(plat.aerender_path(self.src()))
        aer = touch(app.parent / "aerender")
        self.assertEqual(plat.aerender_path(self.src()), aer)

    def test_mac_override_names_the_bundle(self):
        mine = self.bundle(self.tmp / "portable", None, "Adobe Premiere Pro 2023", "23.0")
        self.bundle(self.apps, "Adobe Premiere Pro 2026", "Adobe Premiere Pro 2026", "26.0")
        a = plat.newest_app("premiere", self.src(env={"WHYNOT_PREMIERE_APP": str(mine)}))
        self.assertEqual((Path(a["exe"]), a["source"]), (mine, "override"))
        with self.assertRaises(Guidance) as cm:
            plat.newest_app("premiere", self.src(env={"WHYNOT_PREMIERE_APP": str(self.tmp / "no.app")}))
        self.assertIn("WHYNOT_PREMIERE_APP", cm.exception.error)

    def test_the_registry_is_never_touched_on_a_mac(self):
        self.bundle(self.apps, "Adobe Premiere Pro 2026", "Adobe Premiere Pro 2026", "26.0")
        plat.find_adobe_apps(None, self.src())              # NoRegistry raises AssertionError on any read

    def test_linux_finds_nothing_and_does_not_crash(self):
        src = plat.AdobeSources(env={}, registry=NoRegistry(), os_name="linux", program_dirs=[], mdfind=None,
                                mac_app_dirs=[])
        self.assertEqual(plat.find_adobe_apps(None, src), [])


class Report(WindowsLayout):
    def test_report_lists_version_path_source_and_names(self):
        exe, ae = self.premiere(), self.ae()
        reg = FakeRegistry({"SOFTWARE\\Adobe\\Premiere Pro\\26.0": {"InstallPath": str(exe.parent)}})
        rep = plat.adobe_report(win_sources(registry=reg, program_dirs=[self.pf],
                                            file_version={"Adobe Premiere Pro.exe": "26.5.2.5"}))
        p = rep["found"]["premiere"]
        self.assertEqual((p["name"], p["version"], Path(p["path"]), p["source"]),
                         ("Adobe Premiere Pro 2026", "26.5.2.5", exe, "registry"))
        self.assertEqual(rep["found"]["after_effects"]["source"], "scan")
        self.assertIsNone(rep["found"]["photoshop"])
        self.assertEqual(rep["names"]["premiere"], "Adobe Premiere Pro 2026")
        self.assertIsNone(rep["names"]["photoshop"])
        self.assertEqual(Path(rep["aerender"]["path"]), ae.parent / "aerender.exe")
        self.assertEqual(rep["problems"], [])
        self.assertEqual(len(rep["all"]), 2)

    def test_report_never_raises_on_a_bad_override_and_says_which_variable(self):
        self.ae()
        src = win_sources(env={"WHYNOT_PREMIERE_APP": str(self.tmp / "nope"), "WHYNOT_AERENDER": str(self.tmp / "x")},
                          program_dirs=[self.pf])
        rep = plat.adobe_report(src)
        self.assertIsNone(rep["found"]["premiere"])
        self.assertEqual(rep["found"]["after_effects"]["name"], "Adobe After Effects 2026")
        self.assertIsNone(rep["aerender"])
        vars_ = " ".join(p["error"] for p in rep["problems"])
        self.assertIn("WHYNOT_PREMIERE_APP", vars_)
        self.assertIn("WHYNOT_AERENDER", vars_)
        self.assertTrue(all(p["how"] for p in rep["problems"]))


class RealVersion(WindowsLayout):
    """3.0 T2.11 fix 1 (I1): the version is the app's own (the exe's file version), never the registry key name."""

    def test_the_exe_file_version_is_reported_and_the_registry_key_name_never_is(self):
        pre, ae, ps = self.premiere(), self.ae(), self.photoshop()
        self.adobe("Adobe Media Encoder 2026", "Adobe Media Encoder.exe")
        reg = FakeRegistry({
            "SOFTWARE\\Adobe\\Premiere Pro\\26.0": {"InstallPath": str(pre.parent)},
            "SOFTWARE\\Adobe\\After Effects\\26.0": {"InstallPath": str(ae.parent)},
            "SOFTWARE\\Adobe\\Photoshop\\200.0": {"ApplicationPath": str(ps.parent) + "\\"}})
        fv = {"Adobe Premiere Pro.exe": "26.5.2.5", "AfterFX.exe": "26.5.0.89", "Photoshop.exe": "27.11.0.26",
              "Adobe Media Encoder.exe": "26.5.2.2"}
        src = win_sources(registry=reg, program_dirs=[self.pf], file_version=fv)
        got = {a["key"]: a["version"] for a in plat.find_adobe_apps(None, src)}
        self.assertEqual(got, {"premiere": "26.5.2.5", "after_effects": "26.5.0.89", "photoshop": "27.11.0.26",
                               "media_encoder": "26.5.2.2"})
        self.assertNotIn("200.0", got.values())
        self.assertEqual(plat.newest_app("photoshop", src)["reg_version"], "200.0")        # kept apart, for ranking
        rep = plat.adobe_report(src)
        self.assertEqual(rep["found"]["photoshop"]["version"], "27.11.0.26")
        self.assertEqual(rep["found"]["media_encoder"]["version"], "26.5.2.2")             # found by scan only

    def test_a_consumer_can_compare_the_real_version(self):
        exe = self.premiere()
        reg = FakeRegistry({"SOFTWARE\\Adobe\\Premiere Pro\\26.0": {"InstallPath": str(exe.parent)}})
        a = plat.newest_app("premiere", win_sources(registry=reg, file_version={"Adobe Premiere Pro.exe": "26.5.2.5"}))
        self.assertGreaterEqual(plat._vtuple(a["version"]), (26, 5))          # the registry key "26.0" would say CEP

    def test_unreadable_file_version_gives_none_and_the_registry_key_only_ranks(self):
        # T2.16 (T2.11 re-review M-a): the same year (26.x), and the OLDER registry version has the lexically larger
        # path, so only reg_version can put the newer one first (year and the exe-path tiebreak would not)
        old = touch(self.tmp / "tools" / "B" / "Adobe Premiere Pro.exe")
        new = touch(self.tmp / "tools" / "A" / "Adobe Premiere Pro.exe")
        reg = FakeRegistry({"SOFTWARE\\Adobe\\Premiere Pro\\26.0": {"InstallPath": str(old.parent)},
                            "SOFTWARE\\Adobe\\Premiere Pro\\26.5": {"InstallPath": str(new.parent)}})
        apps = plat.find_adobe_apps("premiere", win_sources(registry=reg))
        self.assertEqual([Path(a["exe"]) for a in apps], [new, old])
        self.assertEqual([(a["version"], a["reg_version"]) for a in apps], [(None, "26.5"), (None, "26.0")])

    def test_a_failing_reader_is_none_not_a_crash(self):
        self.premiere()

        def boom(path):
            raise OSError("locked")
        a = plat.newest_app("premiere", win_sources(program_dirs=[self.pf], file_version=boom))
        self.assertIsNone(a["version"])
        self.assertEqual(a["source"], "scan")

    def test_override_installs_get_their_version_too(self):
        exe = self.premiere(2024)
        src = win_sources(env={"WHYNOT_PREMIERE_APP": str(exe.parent)},
                          file_version={"Adobe Premiere Pro.exe": "24.6.1.3"})
        self.assertEqual(plat.newest_app("premiere", src)["version"], "24.6.1.3")

    def test_version_formatting_drops_trailing_zero_parts(self):
        self.assertEqual(plat._fmt_version((26, 5, 2, 5)), "26.5.2.5")
        self.assertEqual(plat._fmt_version((26, 5, 0, 89)), "26.5.0.89")
        self.assertEqual(plat._fmt_version((26, 5, 0, 0)), "26.5")
        self.assertEqual(plat._fmt_version((26, 0, 0, 0)), "26.0")
        self.assertIsNone(plat._fmt_version((0, 0, 0, 0)))

    def test_the_real_reader_reads_a_real_exe_and_survives_nonsense(self):
        self.assertIsNone(plat._win_file_version(self.tmp / "nope.exe"))
        junk = touch(self.tmp / "junk.exe")                                   # no version resource
        self.assertIsNone(plat._win_file_version(junk))
        if plat.IS_WIN:
            v = plat._win_file_version(sys.executable)                        # python.exe carries its own version
            self.assertRegex(v or "", r"^\d+\.\d+")
            self.assertEqual(plat._vtuple(v)[0], sys.version_info[0])
        src = plat.AdobeSources(env={}, registry=FakeRegistry(), os_name="macos")      # not Windows: never reads
        self.assertIsNone(src.file_version(junk))


class RankingByVersion(WindowsLayout):
    """M1: a custom-folder install (no year in the name) is ranked by its version, not as year 0."""

    def custom(self, name):
        return touch(self.tmp / "tools" / name / "Adobe Premiere Pro.exe")

    def test_a_newer_custom_folder_install_beats_an_older_stock_one(self):
        stock = self.premiere(2025)
        mine = self.custom("PPro")
        reg = FakeRegistry({"SOFTWARE\\Adobe\\Premiere Pro\\26.0": {"InstallPath": str(mine.parent)}})
        for fv in ({"Adobe Premiere Pro.exe": "26.5.2.5"}, None):              # readable, and registry key only
            with self.subTest(file_version=fv):
                src = win_sources(registry=reg, program_dirs=[self.pf], file_version=fv)
                apps = plat.find_adobe_apps("premiere", src)
                self.assertEqual([Path(a["exe"]) for a in apps], [mine, stock])
                self.assertEqual(apps[0]["year"], 2026)

    def test_an_older_custom_folder_install_does_not_beat_a_newer_stock_one(self):
        stock = self.premiere(2026)
        mine = self.custom("OldPPro")
        reg = FakeRegistry({"SOFTWARE\\Adobe\\Premiere Pro\\25.6": {"InstallPath": str(mine.parent)}})
        src = win_sources(registry=reg, program_dirs=[self.pf], file_version={"Adobe Premiere Pro.exe": "25.6.0.1"})
        self.assertEqual(Path(plat.newest_app("premiere", src)["exe"]), stock)

    def test_photoshop_year_follows_its_own_version_numbering(self):
        ps = touch(self.tmp / "tools" / "PS" / "Photoshop.exe")
        reg = FakeRegistry({"SOFTWARE\\Adobe\\Photoshop\\200.0": {"ApplicationPath": str(ps.parent) + "\\"}})
        a = plat.newest_app("photoshop", win_sources(registry=reg, file_version={"Photoshop.exe": "27.11.0.26"}))
        self.assertEqual(a["year"], 2026)                                     # Photoshop 27 = 2026; "200.0" is no year
        b = plat.newest_app("photoshop", win_sources(registry=reg))
        self.assertEqual(b["year"], 0)


class OverrideNames(WindowsLayout):
    """I2: an override that is a FILE must be the app's own exe (case-insensitive), else Guidance naming the variable."""

    def test_other_exes_are_refused_for_premiere_and_after_effects(self):
        notepad = touch(self.tmp / "Windows" / "notepad.exe")
        aer = self.ae().parent / "aerender.exe"
        cases = (("WHYNOT_PREMIERE_APP", "premiere", notepad), ("WHYNOT_AE_APP", "after_effects", notepad),
                 ("WHYNOT_AE_APP", "after_effects", aer))
        for var, key, exe in cases:
            with self.subTest(var=var, exe=exe.name):
                with self.assertRaises(Guidance) as cm:
                    plat.newest_app(key, win_sources(env={var: str(exe)}, program_dirs=[self.pf]))
                self.assertIn(var, cm.exception.error)
                self.assertIn(exe.name, cm.exception.error)
                self.assertIn(var, cm.exception.how)

    def test_the_right_exe_is_accepted_whatever_its_case(self):
        mine = touch(self.tmp / "p" / "ADOBE PREMIERE PRO.EXE")
        a = plat.newest_app("premiere", win_sources(env={"WHYNOT_PREMIERE_APP": str(mine)}))
        self.assertEqual((Path(a["exe"]), a["source"]), (mine, "override"))
        fx = touch(self.tmp / "ae" / "Support Files" / "afterfx.exe")
        a = plat.newest_app("after_effects", win_sources(env={"WHYNOT_AE_APP": str(fx)}))
        self.assertEqual(Path(a["exe"]), fx)

    def test_aerender_override_must_be_aerender(self):
        notepad = touch(self.tmp / "Windows" / "notepad.exe")
        with self.assertRaises(Guidance) as cm:
            plat.aerender_path(win_sources(env={"WHYNOT_AERENDER": str(notepad)}))
        self.assertIn("WHYNOT_AERENDER", cm.exception.error)
        self.assertIn("aerender.exe", cm.exception.error)
        upper = touch(self.tmp / "x" / "AERENDER.EXE")
        self.assertEqual(plat.aerender_path(win_sources(env={"WHYNOT_AERENDER": str(upper)})), upper)

    def test_the_report_turns_a_wrong_exe_into_a_problem(self):
        notepad = touch(self.tmp / "Windows" / "notepad.exe")
        rep = plat.adobe_report(win_sources(env={"WHYNOT_AE_APP": str(notepad)}, program_dirs=[self.pf]))
        self.assertIsNone(rep["found"]["after_effects"])
        self.assertIn("WHYNOT_AE_APP", rep["problems"][0]["error"])


class RaisingLookup(WindowsLayout):
    """M2: doctor is the diagnostic that must survive: any failure becomes a problem, nothing escapes."""

    def test_report_records_a_crashing_lookup_as_a_problem(self):
        class Broken:
            def subkeys(self, path):
                raise PermissionError("access denied")
            values = subkeys
        rep = plat.adobe_report(win_sources(registry=Broken(), program_dirs=[self.pf]))
        self.assertTrue(all(v is None for v in rep["found"].values()))
        self.assertIsNone(rep["aerender"])
        self.assertEqual(len(rep["problems"]), 1)                        # one report line, not one per app
        self.assertIn("Adobe app lookup failed: PermissionError: access denied", rep["problems"][0]["error"])
        self.assertTrue(rep["problems"][0]["how"])

    def test_the_other_apps_still_report_when_one_lookup_fails(self):
        self.photoshop()
        real = plat.find_adobe_apps

        def flaky(key=None, sources=None):
            if key == "premiere":
                raise RuntimeError("boom")
            return real(key, sources)
        with mock.patch.object(plat, "find_adobe_apps", flaky):
            rep = plat.adobe_report(win_sources(program_dirs=[self.pf]))
        self.assertEqual(rep["found"]["photoshop"]["name"], "Adobe Photoshop 2026")
        self.assertIsNone(rep["found"]["premiere"])
        self.assertIn("RuntimeError: boom", rep["problems"][0]["error"])


class MdfindCache(unittest.TestCase):
    """M6: one Spotlight answer per query per process (30 s), failures included: a stalled Spotlight costs 15 s once."""

    def setUp(self):
        plat._MDFIND_CACHE.clear()
        self.addCleanup(plat._MDFIND_CACHE.clear)

    def src(self):
        return plat.AdobeSources(env={}, registry=NoRegistry(), os_name="macos", program_dirs=[], mac_app_dirs=[])

    def test_the_default_runner_asks_spotlight_once_for_repeated_lookups(self):
        ran = mock.Mock(return_value=mock.Mock(stdout="/Applications/Adobe Premiere Pro 2026/x.app\n"))
        with mock.patch.object(plat.subprocess, "run", ran):
            for _ in range(3):
                plat.find_adobe_apps("premiere", self.src())
        self.assertEqual(ran.call_count, 1)
        self.assertEqual(ran.call_args[0][0], ["mdfind", "kMDItemCFBundleIdentifier == 'com.adobe.PremierePro*'"])

    def test_a_timeout_is_cached_and_the_scan_still_answers(self):
        import subprocess
        ran = mock.Mock(side_effect=subprocess.TimeoutExpired("mdfind", 15))
        with mock.patch.object(plat.subprocess, "run", ran):
            self.assertEqual(plat.find_adobe_apps("premiere", self.src()), [])
            self.assertEqual(plat.find_adobe_apps("premiere", self.src()), [])
        self.assertEqual(ran.call_count, 1)

    def test_the_answer_expires_and_injected_runners_are_never_cached(self):
        ran = mock.Mock(return_value=mock.Mock(stdout=""))
        clock = mock.Mock(side_effect=[100.0, 101.0, 140.0, 140.0])
        with mock.patch.object(plat.subprocess, "run", ran), mock.patch("time.monotonic", clock):
            plat._run_mdfind("q")
            plat._run_mdfind("q")                  # 1 s later: cached
            plat._run_mdfind("q")                  # 40 s later: asked again
        self.assertEqual(ran.call_count, 2)
        asked = []
        fake = plat.AdobeSources(env={}, registry=NoRegistry(), os_name="macos", program_dirs=[], mac_app_dirs=[],
                                 mdfind=lambda q: asked.append(q) or [])
        plat.find_adobe_apps("premiere", fake)
        plat.find_adobe_apps("premiere", fake)
        self.assertEqual(len(asked), 2)


class FakeWinreg:
    """A stand-in for the winreg module: HKLM as {(path, view flag): {"keys": [...], "values": [(name, data, type)]}}.
    A key listed in `deny` raises PermissionError from OpenKey; `broken_enum` raises mid-enumeration."""
    HKEY_LOCAL_MACHINE = "HKLM"
    KEY_READ = 0x20019
    KEY_WOW64_64KEY = 0x0100
    KEY_WOW64_32KEY = 0x0200

    def __init__(self, tree, deny=(), broken_enum=()):
        self.tree, self.deny, self.broken_enum, self.opened = tree, set(deny), set(broken_enum), []

    def OpenKey(self, hive, path, reserved, access):                        # noqa: N802
        self.opened.append((hive, path, reserved, access))
        view = access & (self.KEY_WOW64_64KEY | self.KEY_WOW64_32KEY)
        if (path, view) in self.deny:
            raise PermissionError("access denied")
        if (path, view) not in self.tree:
            raise FileNotFoundError(path)
        return FakeKey(self, (path, view))

    def EnumKey(self, key, i):                                              # noqa: N802
        names = key.data.get("keys", [])
        if key.id in self.broken_enum and i >= 1:
            raise PermissionError("denied mid-enumeration")
        if i >= len(names):
            raise OSError("no more data")
        return names[i]

    def EnumValue(self, key, i):                                            # noqa: N802
        vals = key.data.get("values", [])
        if i >= len(vals):
            raise OSError("no more data")
        return vals[i]


class FakeKey:
    def __init__(self, reg, kid):
        self.reg, self.id, self.data = reg, kid, reg.tree[kid]
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True


class RealRegistryReader(unittest.TestCase):
    def test_without_winreg_the_reader_is_empty_and_quiet(self):
        with mock.patch.dict(sys.modules, {"winreg": None}):                 # import winreg -> ImportError (macOS)
            reg = plat.WinRegistry()
            self.assertEqual(reg.values("SOFTWARE\\Adobe"), {})
            self.assertEqual(reg.subkeys("SOFTWARE\\Adobe"), [])

    def reader(self, tree, **kw):
        fake = FakeWinreg(tree, **kw)
        patcher = mock.patch.dict(sys.modules, {"winreg": fake})
        patcher.start()
        self.addCleanup(patcher.stop)
        return plat.WinRegistry(), fake

    V64, V32 = FakeWinreg.KEY_WOW64_64KEY, FakeWinreg.KEY_WOW64_32KEY
    PATH = "SOFTWARE\\Adobe\\Premiere Pro"

    def test_the_64_bit_view_is_opened_read_only_first_then_the_32_bit_one(self):
        reg, fake = self.reader({(self.PATH, self.V64): {"keys": ["26.0"]}, (self.PATH, self.V32): {"keys": ["25.0"]}})
        self.assertEqual(reg.subkeys(self.PATH), ["26.0", "25.0"])
        self.assertEqual([(h, p, r, a) for h, p, r, a in fake.opened],
                         [("HKLM", self.PATH, 0, FakeWinreg.KEY_READ | self.V64),
                          ("HKLM", self.PATH, 0, FakeWinreg.KEY_READ | self.V32)])

    def test_subkeys_of_both_views_merge_without_duplicates(self):
        reg, _ = self.reader({(self.PATH, self.V64): {"keys": ["26.0", "25.0"]},
                              (self.PATH, self.V32): {"keys": ["25.0", "24.0"]}})
        self.assertEqual(reg.subkeys(self.PATH), ["26.0", "25.0", "24.0"])

    def test_a_missing_or_denied_key_is_skipped_and_the_other_view_still_answers(self):
        reg, _ = self.reader({(self.PATH, self.V64): {"keys": ["26.0"]}, (self.PATH, self.V32): {"keys": ["25.0"]}},
                             deny=[(self.PATH, self.V64)])
        self.assertEqual(reg.subkeys(self.PATH), ["25.0"])                   # PermissionError is an OSError
        only32, _ = self.reader({(self.PATH, self.V32): {"keys": ["25.0"]}})  # no key in the 64-bit view at all
        self.assertEqual(only32.subkeys(self.PATH), ["25.0"])
        self.assertEqual(only32.subkeys("SOFTWARE\\Nothing"), [])
        self.assertEqual(only32.values("SOFTWARE\\Nothing"), {})

    def test_an_error_in_the_middle_of_an_enumeration_keeps_what_was_read(self):
        reg, _ = self.reader({(self.PATH, self.V64): {"keys": ["26.0", "25.0", "24.0"]}},
                             broken_enum=[(self.PATH, self.V64)])
        self.assertEqual(reg.subkeys(self.PATH), ["26.0"])

    def test_values_keep_text_only_expand_variables_and_prefer_the_64_bit_view(self):
        var = "%WNC_TEST_PF%" if plat.IS_WIN else "$WNC_TEST_PF"
        tree = {(self.PATH + "\\26.0", self.V64): {"values": [("InstallPath", var + "/Adobe", 2),
                                                               ("Count", 7, 4), ("Blob", b"\x01", 3)]},
                (self.PATH + "\\26.0", self.V32): {"values": [("InstallPath", "other", 1), ("Extra", "x", 1)]}}
        reg, _ = self.reader(tree)
        with mock.patch.dict("os.environ", {"WNC_TEST_PF": "C:/PF"}):
            vals = reg.values(self.PATH + "\\26.0")
        self.assertEqual(vals, {"InstallPath": "C:/PF/Adobe", "Extra": "x"})

    def test_the_keys_are_closed_after_reading(self):
        keys = []
        reg, fake = self.reader({(self.PATH, self.V64): {"keys": ["26.0"]}})
        real_open = fake.OpenKey
        fake.OpenKey = lambda *a: keys.append(real_open(*a)) or keys[-1]
        reg.subkeys(self.PATH)
        self.assertTrue(keys and all(k.closed for k in keys))

    def test_discovery_through_the_real_reader_with_a_fake_winreg(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        exe = touch(Path(td.name) / "Adobe Premiere Pro 2026" / "Adobe Premiere Pro.exe")
        reg, _ = self.reader({(self.PATH + "\\26.0", self.V32): {"values": [("InstallPath", str(exe.parent), 1)]},
                              (self.PATH, self.V32): {"keys": ["26.0", "CurrentVersion"]}})
        src = plat.AdobeSources(env={}, registry=reg, os_name="windows", program_dirs=[], mdfind=None,
                                mac_app_dirs=[], file_version=lambda p: "26.5.2.5")
        a = plat.newest_app("premiere", src)
        self.assertEqual((Path(a["exe"]), a["source"], a["version"], a["reg_version"]),
                         (exe, "registry", "26.5.2.5", "26.0"))


class SetupAndDoctor(unittest.TestCase):
    """reel setup installs the bridge when only After Effects exists (the same CEP bundle serves both)."""

    def run_setup(self, apps, doctor_fixes=()):
        import cli
        installs = []
        printed = []
        args = mock.Mock(force=False, check=False, no_bridge=False)
        lookup = apps if callable(apps) else (lambda key: apps.get(key))
        with mock.patch.object(plat, "newest_app", lookup), \
                mock.patch.object(cli, "run_setup_env", lambda **kw: {"ok": True}), \
                mock.patch.object(cli, "doctor_in_engine", lambda: {"fixes": list(doctor_fixes)}), \
                mock.patch.object(cli, "out", printed.append), \
                mock.patch("lib.ppro_bridge.install", lambda: installs.append(1) or {"installed": "x"}):
            cli.cmd_setup(args)
        return installs, printed[0]

    def test_installs_with_premiere_only_after_effects_only_or_both(self):
        for apps in ({"premiere": {"name": "P"}}, {"after_effects": {"name": "AE"}},
                     {"premiere": {"name": "P"}, "after_effects": {"name": "AE"}}):
            with self.subTest(apps=sorted(apps)):
                installs, rep = self.run_setup(apps)
                self.assertEqual(installs, [1])
                self.assertEqual(rep["bridge_install"], {"installed": "x"})

    def test_doctor_reports_each_app_with_version_path_and_source_and_the_bad_variable(self):
        from lib import onboard
        found = {"premiere": None, "photoshop": None, "media_encoder": None,
                 "after_effects": {"name": "Adobe After Effects 2026", "version": "26.0", "year": 2026,
                                   "path": "C:/AE/AfterFX.exe", "folder": "C:/AE", "source": "registry",
                                   "sources": ["registry"], "beta": False, "others": []}}
        report = {"found": found, "names": {k: (v or {}).get("name") for k, v in found.items()}, "all": [],
                  "aerender": {"path": "C:/AE/aerender.exe", "source": "registry"},
                  "problems": [{"error": "WHYNOT_PREMIERE_APP is set to X, but nothing is there.",
                                "how": "Set WHYNOT_PREMIERE_APP to Adobe Premiere Pro's .exe"}]}
        with mock.patch.object(plat, "adobe_report", lambda *a, **k: report):
            rep = onboard.doctor()
        self.assertEqual(rep["adobe_found"]["after_effects"]["source"], "registry")
        self.assertEqual(rep["adobe_found"]["after_effects"]["version"], "26.0")
        self.assertEqual(rep["adobe_apps"]["after_effects"], "Adobe After Effects 2026")
        self.assertIsNone(rep["adobe_apps"]["premiere"])
        self.assertEqual(rep["aerender"]["source"], "registry")
        items = [f["item"] for f in rep["fixes"]]
        self.assertTrue(any("WHYNOT_PREMIERE_APP" in i for i in items), items)
        if not rep["premiere_bridge"]["installed"]:                        # After Effects alone still gets the bridge
            self.assertIn("WhyNot Cut extension (After Effects)", items)

    def stale_premiere_variable(self, ae=None):
        err = "WHYNOT_PREMIERE_APP is set to X, but nothing is there."
        how = "Set WHYNOT_PREMIERE_APP to Adobe Premiere Pro's .exe or its install folder."

        def lookup(key):
            if key == "premiere":
                raise Guidance(err, how, "WHYNOT_PREMIERE_APP")
            return ae
        return lookup, err, how

    def test_a_stale_override_does_not_abort_setup_before_the_report(self):
        lookup, err, how = self.stale_premiere_variable()
        installs, rep = self.run_setup(lookup)                               # used to raise Guidance out of cmd_setup
        self.assertEqual(installs, [])
        self.assertEqual(rep["bridge_install"], "skipped: " + err)
        self.assertIn("doctor", rep)
        self.assertIn(how, rep["next"])                                      # the problem is in the report's next steps

    def test_the_stale_override_is_listed_once_when_the_doctor_already_has_it(self):
        lookup, err, how = self.stale_premiere_variable()
        _, rep = self.run_setup(lookup, doctor_fixes=[{"item": err, "who": "editor", "fix": how}])
        self.assertEqual(rep["next"].count(how), 1)

    def test_a_stale_premiere_override_still_installs_the_bridge_for_after_effects(self):
        lookup, err, how = self.stale_premiere_variable(ae={"name": "AE"})
        installs, rep = self.run_setup(lookup)
        self.assertEqual(installs, [1])
        self.assertEqual(rep["bridge_install"], {"installed": "x"})
        self.assertIn(how, rep["next"])

    def doctor_items(self, premiere_bad, ae):
        from lib import onboard
        found = {"premiere": None, "photoshop": None, "media_encoder": None,
                 "after_effects": ({"name": "Adobe After Effects 2026", "version": "26.5", "year": 2026,
                                    "path": "C:/AE/AfterFX.exe", "folder": "C:/AE", "source": "registry",
                                    "sources": ["registry"], "beta": False, "others": []} if ae else None)}
        problems = ([{"error": "WHYNOT_PREMIERE_APP is set to X, but nothing is there.",
                      "how": "Set WHYNOT_PREMIERE_APP to Adobe Premiere Pro's .exe"}] if premiere_bad else [])
        report = {"found": found, "names": {k: (v or {}).get("name") for k, v in found.items()}, "all": [],
                  "aerender": None, "problems": problems}
        with mock.patch.object(plat, "adobe_report", lambda *a, **k: report):
            return onboard.doctor()

    def test_doctor_does_not_say_install_premiere_when_the_variable_is_the_problem(self):
        rep = self.doctor_items(premiere_bad=True, ae=False)
        items = [f["item"] for f in rep["fixes"]]
        self.assertNotIn("Adobe Premiere Pro", items)
        self.assertTrue(any("WHYNOT_PREMIERE_APP" in i for i in items), items)

    def test_doctor_still_says_install_premiere_when_it_really_is_missing(self):
        rep = self.doctor_items(premiere_bad=False, ae=False)
        self.assertIn("Adobe Premiere Pro", [f["item"] for f in rep["fixes"]])

    def test_the_after_effects_bridge_fix_survives_a_bad_premiere_variable(self):
        rep = self.doctor_items(premiere_bad=True, ae=True)
        items = [f["item"] for f in rep["fixes"]]
        self.assertNotIn("Adobe Premiere Pro", items)
        if not rep["premiere_bridge"]["installed"]:
            self.assertIn("WhyNot Cut extension (After Effects)", items)

    def test_the_sandbox_drops_the_adobe_override_variables(self):
        import _isolation
        for name in ("WHYNOT_PREMIERE_APP", "WHYNOT_AE_APP", "WHYNOT_AERENDER"):
            self.assertIn(name, _isolation._DROP)
            self.assertNotIn(name, __import__("os").environ)

    def test_skips_and_says_so_when_neither_exists(self):
        installs, rep = self.run_setup({})
        self.assertEqual(installs, [])
        self.assertIn("Premiere Pro or After Effects", rep["bridge_install"])

class BridgeInfoAndDoctor(unittest.TestCase):
    """3.0 T6.3 Task 5: doctor's bridge_info reads ~/.whynot-cut/bridge/config.json and the installed build.json
    (family, product, build, signed), never bridge-config.json; the fix texts follow (signed needs no PlayerDebugMode,
    the legacy 3.1.1 is amber, the extension comes from the installer when the plugin carries no source)."""

    def setUp(self):
        import json
        import shutil
        from lib import cep_bundle, ppro_bridge
        self.json, self.cep_bundle, self.ppro_bridge = json, cep_bundle, ppro_bridge
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ext = self.tmp / "cep" / cep_bundle.EXT_ID
        self.cfg = self.tmp / "user" / ".whynot-cut" / "bridge" / "config.json"
        self.q = self.tmp / "home" / "ppro-queue"
        self.debug = {}
        self.alive = False
        for p in (mock.patch.object(plat, "cep_extensions_dir", lambda: self.tmp / "cep"),
                  mock.patch.object(cep_bundle, "config_path", lambda: self.cfg),
                  mock.patch.object(plat, "player_debug_mode", lambda: dict(self.debug)),
                  mock.patch.object(plat, "debug_mode_ok", lambda modes=None: bool((modes or {}).get("ok"))),
                  mock.patch.object(ppro_bridge, "queue_dir", lambda: self.q),
                  mock.patch.object(ppro_bridge, "status", lambda *a, **k: {"alive": self.alive, "detail": "x"})):
            p.start()
            self.addCleanup(p.stop)

    def bundle(self, signed=False):
        b = self.cep_bundle.assemble(self.ext)
        if signed:
            (b / "META-INF").mkdir()
            (b / "META-INF" / "signatures.xml").write_text("<signatures/>", encoding="utf-8")
        return self.json.loads((b / "build.json").read_text(encoding="utf-8"))

    def legacy(self):
        (self.ext / "CSXS").mkdir(parents=True)
        (self.ext / "CSXS" / "manifest.xml").write_text(
            '<ExtensionManifest ExtensionBundleId="ai.thewhynot.cut.bridge" ExtensionBundleVersion="3.1.1">',
            encoding="utf-8")
        (self.ext / "bridge-config.json").write_text(self.json.dumps({"base": "D:/x", "version": "9.9.9"}),
                                                     encoding="utf-8")

    def doctor(self, premiere=True, ae=False):
        from lib import onboard
        found = {"premiere": {"name": "Adobe Premiere Pro 2026"} if premiere else None, "photoshop": None,
                 "media_encoder": None, "after_effects": {"name": "Adobe After Effects 2026"} if ae else None}
        report = {"found": found, "names": {k: (v or {}).get("name") for k, v in found.items()}, "all": [],
                  "aerender": None, "problems": []}
        with mock.patch.object(plat, "adobe_report", lambda *a, **k: report):
            return onboard.doctor()

    def test_nothing_installed(self):
        from lib import onboard
        br = onboard.bridge_info()
        self.assertEqual((br["installed"], br["family"], br["product"], br["build"], br["signed"], br["config"]),
                         (False, None, None, None, False, None))
        self.assertFalse(br["loads"])
        fix = [f for f in self.doctor()["fixes"] if f["item"] == "WhyNot Cut extension (Premiere)"]
        self.assertEqual(len(fix), 1)
        self.assertIn("reel setup", fix[0]["fix"])                       # this checkout carries the source
        with mock.patch.object(self.cep_bundle, "source_dir", lambda: self.tmp / "none"):
            fix = [f for f in self.doctor()["fixes"] if f["item"] == "WhyNot Cut extension (Premiere)"][0]
        self.assertEqual((fix["who"], fix["fix"]),
                         ("editor", "install WhyNot Cut with its installer (the signed extension comes with it)"))

    def test_config_json_and_build_json(self):
        from lib import onboard
        build = self.bundle(signed=True)
        shim = self.tmp / "home" / "bin" / self.cep_bundle.LAUNCHER_NAME
        shim.parent.mkdir(parents=True)
        shim.write_text("x", encoding="utf-8")
        self.cep_bundle.write_config(self.tmp / "home", written_by="installer")
        self.q.mkdir(parents=True)
        beat = {"at": 1, "engine_start": {"at": 1, "outcome": "running"}}
        (self.q / "bridge.heartbeat").write_text(self.json.dumps(beat), encoding="utf-8")
        br = onboard.bridge_info()
        self.assertEqual((br["installed"], br["family"], br["product"], br["version"], br["build"], br["signed"]),
                         (True, "bundle", "3.0.0", "3.0.0", build["build"], True))
        self.assertEqual(br["config"]["written_by"], "installer")
        self.assertEqual(br["queue_base"], str((self.tmp / "home").resolve()))
        self.assertEqual(br["launcher"], str(shim.resolve()))
        self.assertEqual(br["config_file"], str(self.cfg))
        self.assertEqual(br["engine_start"], {"at": 1, "outcome": "running"})
        self.assertEqual((br["debug_mode_ok"], br["debug_mode_needed"], br["loads"]), (False, False, True))

    def test_a_signed_bundle_needs_no_player_debug_mode(self):
        self.bundle(signed=True)
        items = [f["item"] for f in self.doctor()["fixes"]]
        self.assertFalse(any("PlayerDebugMode" in i for i in items), items)
        self.assertIn("WhyNot Cut is not running in Premiere", items)
        self.alive = True
        rep = self.doctor()
        self.assertTrue(rep["ready"]["premiere_build"])
        self.assertFalse(any("WhyNot Cut extension" in f["item"] for f in rep["fixes"]), rep["fixes"])

    def test_an_unsigned_bundle_needs_player_debug_mode(self):
        self.bundle(signed=False)
        items = [f["item"] for f in self.doctor()["fixes"]]
        self.assertIn("Adobe PlayerDebugMode (lets Premiere load this unsigned WhyNot Cut extension)", items)
        self.assertNotIn("WhyNot Cut is not running in Premiere", items)  # it cannot load yet: that fix comes first
        self.assertFalse(self.doctor()["ready"]["premiere_build"])
        self.debug = {"ok": True}
        self.alive = True
        self.assertTrue(self.doctor()["ready"]["premiere_build"])

    def test_an_unsigned_bundle_without_a_source_is_flagged_amber(self):
        self.bundle(signed=False)
        with mock.patch.object(self.cep_bundle, "source_dir", lambda: self.tmp / "none"):
            fixes = self.doctor()["fixes"]
        (f,) = [f for f in fixes if f["item"] == "the installed WhyNot Cut extension is an unsigned build"]
        self.assertEqual((f["level"], f["optional"]), ("amber", True))

    def test_the_legacy_family_is_amber_and_bridge_config_json_is_never_read(self):
        from lib import onboard
        self.legacy()
        br = onboard.bridge_info()
        self.assertEqual((br["family"], br["product"], br["build"]), ("legacy", "3.1.1", None))   # not 9.9.9
        self.assertIsNone(br["queue_base"])                                                    # not D:/x
        (f,) = [f for f in self.doctor()["fixes"] if "older bridge" in f["item"]]
        self.assertEqual((f["level"], f["optional"]), ("amber", True))
        self.assertIn("3.1.1", f["item"])
        import inspect
        self.assertNotIn("bridge-config", inspect.getsource(onboard))

    def test_an_older_bridge_of_ours_must_be_updated(self):
        """T6.3 Task 6: an unsigned 3.1.0 of ours is replaced by the install (family legacy) but the queue no longer
        drives it, so the doctor asks to update it (not the optional amber of 3.1.1)."""
        self.legacy()
        manifest = self.ext / "CSXS" / "manifest.xml"
        manifest.write_text(manifest.read_text(encoding="utf-8").replace("3.1.1", "3.1.0"), encoding="utf-8")
        fixes = self.doctor()["fixes"]
        (f,) = [f for f in fixes if "WhyNot Cut extension 3.1.0" in f["item"]]
        self.assertIn("update it", f["item"])
        self.assertNotIn("optional", f)
        self.assertFalse(any("older bridge" in x["item"] for x in fixes))

    def test_after_effects_alone_gets_the_extension_fix(self):
        items = [f["item"] for f in self.doctor(premiere=False, ae=True)["fixes"]]
        self.assertIn("WhyNot Cut extension (After Effects)", items)
        self.assertFalse(any("Bridge" in i for i in items), items)
        items = [f["item"] for f in self.doctor(premiere=False, ae=False)["fixes"]]
        self.assertNotIn("WhyNot Cut extension (After Effects)", items)


if __name__ == "__main__":
    unittest.main()
