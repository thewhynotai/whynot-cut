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


def win_sources(env=None, registry=None, program_dirs=()):
    return plat.AdobeSources(env=env or {}, registry=registry or FakeRegistry(), os_name="windows",
                             program_dirs=list(program_dirs), mdfind=None, mac_app_dirs=[])


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
        a = plat.newest_app("premiere", win_sources(registry=reg))
        self.assertEqual(Path(a["exe"]), exe)
        self.assertEqual(Path(a["folder"]), app)
        self.assertEqual((a["source"], a["version"], a["year"], a["name"]),
                         ("registry", "26.0", 2026, "Adobe Premiere Pro 2026"))

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
        self.assertEqual(apps[0]["version"], "26.0")

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
        rep = plat.adobe_report(win_sources(registry=reg, program_dirs=[self.pf]))
        p = rep["found"]["premiere"]
        self.assertEqual((p["name"], p["version"], Path(p["path"]), p["source"]),
                         ("Adobe Premiere Pro 2026", "26.0", exe, "registry"))
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


class RealRegistryReader(unittest.TestCase):
    def test_without_winreg_the_reader_is_empty_and_quiet(self):
        with mock.patch.dict(sys.modules, {"winreg": None}):                 # import winreg -> ImportError (macOS)
            reg = plat.WinRegistry()
            self.assertEqual(reg.values("SOFTWARE\\Adobe"), {})
            self.assertEqual(reg.subkeys("SOFTWARE\\Adobe"), [])


class SetupAndDoctor(unittest.TestCase):
    """reel setup installs the bridge when only After Effects exists (the same CEP bundle serves both)."""

    def run_setup(self, apps):
        import cli
        installs = []
        printed = []
        args = mock.Mock(force=False, check=False, no_bridge=False)
        with mock.patch.object(plat, "newest_app", lambda key: apps.get(key)), \
                mock.patch.object(cli, "run_setup_env", lambda **kw: {"ok": True}), \
                mock.patch.object(cli, "doctor_in_engine", lambda: {"fixes": []}), \
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
            self.assertIn("WhyNot Cut Bridge (After Effects)", items)

    def test_skips_and_says_so_when_neither_exists(self):
        installs, rep = self.run_setup({})
        self.assertEqual(installs, [])
        self.assertIn("Premiere Pro or After Effects", rep["bridge_install"])


if __name__ == "__main__":
    unittest.main()
