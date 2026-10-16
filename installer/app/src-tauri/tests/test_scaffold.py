"""ET1-17: static checks of the Tauri 2 scaffold (config, capabilities, dependency tree, source scans).

Run (stdlib only, no pytest needed):
    python -I -m unittest discover -s installer/app/src-tauri/tests -p "test_*.py" -v

The cargo-tree test needs the per-user toolchain on PATH (SPIKE-S0.md). Without cargo it is skipped and says so;
the Cargo.lock checks still run. The Rust side (app_info, the compiled context, the resolved ACL) is in `cargo test`.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import tomllib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SRC_TAURI = HERE.parent
APP = SRC_TAURI.parent
REPO = APP.parent.parent
CONF = SRC_TAURI / "tauri.conf.json"
CAPS = SRC_TAURI / "capabilities"
CARGO_TOML = SRC_TAURI / "Cargo.toml"
CARGO_LOCK = SRC_TAURI / "Cargo.lock"

# The ONE list of commands the UI may call. Every other place (build.rs AppManifest, generate_handler!, the
# capability file, the isolation hook) must say exactly this. ET1-18/19 extend it here first (red), then there.
ALLOWED_COMMANDS = ["app_info"]
CAPABILITY_ID = "main-window"
GRANTED_PERMISSIONS = ["allow-app-info"]

# Tauri's own needs on top of the UI meta (ET1-07), proven live in WebView2 (task-ET1-17-report.md):
# - connect-src: the IPC custom protocol (ipc: on macOS, http://ipc.localhost on Windows);
# - style-src: the hash of the ONE <style> Tauri's isolation injector adds to hide its iframe
#   (tauri-utils IFRAME_STYLE "#__tauri_isolation__ { display: none !important }"; cargo test re-derives it).
TAURI_ISOLATION_STYLE_HASH = "'sha256-YEercZJImS+vUX2bz7vkQ0aA4rtBIPLuCEWz+yraQ/g='"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' " + TAURI_ISOLATION_STYLE_HASH + "; "
       "img-src 'self' data:; font-src 'self'; connect-src ipc: http://ipc.localhost; object-src 'none'; "
       "base-uri 'none'; frame-ancestors 'none'")

# Local IPC origins are the only URLs allowed anywhere in the config (they are inside the CSP).
LOCAL_IPC_URLS = {"http://ipc.localhost"}

HTTP_CLIENT_CRATES = {"reqwest", "hyper", "hyper-util", "ureq", "isahc", "curl", "curl-sys", "attohttpc"}
FORBIDDEN_PLUGINS = {"tauri-plugin-shell", "tauri-plugin-http", "tauri-plugin-fs", "tauri-plugin-opener",
                     "tauri-plugin-updater", "tauri-plugin-dialog", "tauri-plugin-process",
                     "tauri-plugin-websocket", "tauri-plugin-upload", "tauri-plugin-deep-link"}
ALLOWED_PLUGINS = {"tauri-plugin-single-instance"}
# The targets we ship (Windows: CI MSVC + this PC's gnullvm dev build; macOS: both arches).
DESKTOP_TARGETS = ["x86_64-pc-windows-msvc", "x86_64-pc-windows-gnullvm", "aarch64-apple-darwin",
                   "x86_64-apple-darwin"]

# Our own source files (what the scans read). Generated folders and this test file are not ours to scan.
def authored_files() -> list[pathlib.Path]:
    out = []
    for p in sorted(SRC_TAURI.rglob("*")):
        rel = p.relative_to(SRC_TAURI).as_posix()
        if not p.is_file() or rel.startswith(("target/", "gen/", "ui-dist/", "tests/", "icons/")):
            continue
        if p.suffix in {".rs", ".json", ".toml", ".js", ".html"} and p.name != "Cargo.lock":
            out.append(p)
    return out


def load_conf() -> dict:
    return json.loads(CONF.read_text(encoding="utf-8"))


def all_strings(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for k, v in node.items() for s in all_strings(k) + all_strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in all_strings(v)]
    return []


def lock_packages() -> dict[str, list[str]]:
    data = tomllib.loads(CARGO_LOCK.read_text(encoding="utf-8"))
    pk: dict[str, list[str]] = {}
    for p in data["package"]:
        pk.setdefault(p["name"], []).append(p["version"])
    return pk


def strip_rust_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


class ConfigTests(unittest.TestCase):
    def test_csp_is_exact(self):
        self.assertEqual(load_conf()["app"]["security"]["csp"], CSP)

    def test_no_dev_csp_and_no_csp_modification_escape_hatches(self):
        sec = load_conf()["app"]["security"]
        self.assertNotIn("devCsp", sec)
        self.assertFalse(sec.get("dangerousDisableAssetCspModification", False))
        self.assertNotIn("assetProtocol", sec)  # off by default; never turned on in the scaffold
        self.assertNotIn("dangerousRemoteDomainIpcAccess", sec)

    def test_no_dev_url_or_build_commands(self):
        build = load_conf().get("build", {})
        for key in ("devUrl", "beforeDevCommand", "beforeBuildCommand", "beforeBundleCommand"):
            self.assertNotIn(key, build)

    def test_no_remote_url_anywhere_in_config_or_capabilities(self):
        files = [CONF, *sorted(CAPS.glob("*.json"))]
        for f in files:
            for s in all_strings(json.loads(f.read_text(encoding="utf-8"))):
                for url in re.findall(r"[a-z][a-z0-9+.-]*://[^\s;'\"]*", s, flags=re.I):
                    self.assertIn(url, LOCAL_IPC_URLS, f"{f.name}: remote URL {url!r}")
        self.assertNotIn("$schema", load_conf(), "a remote schema URL is still a remote URL")

    def test_frontend_is_the_staged_local_ui_bundle(self):
        conf = load_conf()
        self.assertEqual(conf["build"]["frontendDist"], "ui-dist")
        for w in conf["app"]["windows"]:
            self.assertNotIn("url", w, "the window loads the bundled index.html only")
            # http://tauri.localhost on Windows; the CSP's http://ipc.localhost depends on it
            self.assertFalse(w.get("useHttpsScheme", False))

    def test_isolation_pattern_is_on(self):
        pattern = load_conf()["app"]["security"]["pattern"]
        self.assertEqual(pattern["use"], "isolation")
        iso = SRC_TAURI / pattern["options"]["dir"]
        self.assertTrue((iso / "index.html").is_file())
        self.assertIn("__TAURI_ISOLATION_HOOK__", (iso / "index.js").read_text(encoding="utf-8"))
        manifest = tomllib.loads(CARGO_TOML.read_text(encoding="utf-8"))
        self.assertIn("isolation", manifest["dependencies"]["tauri"]["features"],
                      "without the feature codegen silently falls back to brownfield")
        self.assertIn("isolation", manifest["build-dependencies"]["tauri-build"]["features"])

    def test_with_global_tauri_is_false(self):
        self.assertIs(load_conf()["app"]["withGlobalTauri"], False)

    def test_freeze_prototype_is_on(self):
        self.assertIs(load_conf()["app"]["security"]["freezePrototype"], True)

    def test_one_window_with_the_sizes_and_title(self):
        wins = load_conf()["app"]["windows"]
        self.assertEqual(len(wins), 1)
        w = wins[0]
        self.assertEqual((w["label"], w["title"]), ("main", "WhyNot Cut"))
        self.assertEqual((w["width"], w["height"], w["minWidth"], w["minHeight"]), (760, 540, 640, 480))

    def test_bundle_is_minimal(self):
        bundle = load_conf()["bundle"]
        self.assertIs(bundle["active"], False)
        self.assertLessEqual(set(bundle), {"active", "icon"})


class CapabilityTests(unittest.TestCase):
    def test_config_enables_exactly_one_capability(self):
        self.assertEqual(load_conf()["app"]["security"]["capabilities"], [CAPABILITY_ID])

    def test_capability_folder_holds_only_that_capability(self):
        self.assertEqual(sorted(p.name for p in CAPS.iterdir()), [f"{CAPABILITY_ID}.json"])

    def test_capability_grants_only_our_commands(self):
        cap = json.loads((CAPS / f"{CAPABILITY_ID}.json").read_text(encoding="utf-8"))
        self.assertEqual(cap["identifier"], CAPABILITY_ID)
        self.assertEqual(cap["windows"], ["main"])
        self.assertEqual(cap["permissions"], GRANTED_PERMISSIONS)
        self.assertEqual(GRANTED_PERMISSIONS, ["allow-" + c.replace("_", "-") for c in ALLOWED_COMMANDS])
        self.assertNotIn("remote", cap, "no remote origin may reach the IPC")
        self.assertIs(cap.get("local", True), True)
        self.assertNotIn("webviews", cap)
        self.assertNotIn("platforms", cap)
        for perm in cap["permissions"]:
            self.assertNotIsInstance(perm, dict, "no scoped/plugin permission objects")
            self.assertFalse(perm.startswith("core:"), f"core permission granted: {perm}")
            self.assertNotIn(":", perm, f"plugin permission granted: {perm}")

    def test_build_rs_declares_the_same_app_commands(self):
        text = strip_rust_comments((SRC_TAURI / "build.rs").read_text(encoding="utf-8"))
        m = re.search(r"AppManifest::new\(\)\s*\.commands\(&\[(.*?)\]\)", text, flags=re.S)
        self.assertIsNotNone(m, "build.rs must declare the app commands (so they need a capability)")
        self.assertEqual(re.findall(r'"([^"]+)"', m.group(1)), ALLOWED_COMMANDS)

    def test_invoke_handler_registers_the_same_commands(self):
        text = strip_rust_comments((SRC_TAURI / "src" / "lib.rs").read_text(encoding="utf-8"))
        handlers = re.findall(r"generate_handler!\[(.*?)\]", text, flags=re.S)
        self.assertEqual(len(handlers), 1)
        self.assertEqual([h.strip() for h in handlers[0].split(",") if h.strip()], ALLOWED_COMMANDS)

    def test_isolation_hook_allows_the_same_commands(self):
        js = (SRC_TAURI / "isolation" / "index.js").read_text(encoding="utf-8")
        m = re.search(r"const ALLOWED = Object\.freeze\(\[(.*?)\]\)", js, flags=re.S)
        self.assertIsNotNone(m)
        self.assertEqual(re.findall(r"'([^']+)'", m.group(1)), ALLOWED_COMMANDS)

    def test_ui_meta_csp_agrees_except_ipc_and_frames(self):
        # The UI's own meta (ET1-07) and our header must not drift. Allowed differences, all Tauri's own needs:
        # connect-src (the IPC origins), frame-src (the isolation iframe; Tauri adds its origin to the header itself)
        # and the isolation style hash in style-src.
        html = (APP / "ui" / "index.html").read_text(encoding="utf-8")
        m = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html)
        self.assertIsNotNone(m)

        def directives(csp: str) -> dict[str, str]:
            return {d.split()[0]: " ".join(d.split()[1:]) for d in (x.strip() for x in csp.split(";")) if d}
        ui, ours = directives(m.group(1)), directives(CSP)
        ours["style-src"] = ours["style-src"].replace(" " + TAURI_ISOLATION_STYLE_HASH, "")
        for d in (ui.keys() | ours.keys()) - {"connect-src", "frame-src"}:
            self.assertEqual(ui.get(d), ours.get(d), d)


class DependencyTests(unittest.TestCase):
    def test_direct_dependencies_are_pinned_exactly(self):
        manifest = tomllib.loads(CARGO_TOML.read_text(encoding="utf-8"))
        for section in ("dependencies", "build-dependencies", "dev-dependencies"):
            for name, spec in manifest.get(section, {}).items():
                version = spec if isinstance(spec, str) else spec.get("version", "")
                self.assertTrue(version.startswith("="), f"{section}.{name} = {version!r} is not pinned")
        self.assertEqual(manifest["dependencies"]["tauri"]["version"], "=2.12.4")
        self.assertEqual(manifest["build-dependencies"]["tauri-build"]["version"], "=2.7.3")

    def test_lockfile_is_committed_beside_the_manifest(self):
        self.assertTrue(CARGO_LOCK.is_file())
        r = subprocess.run(["git", "ls-files", "--error-unmatch", str(CARGO_LOCK)], cwd=REPO,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, "Cargo.lock must be tracked (Addendum E2.1 #6)")

    def test_lockfile_has_no_forbidden_plugin(self):
        pk = lock_packages()
        self.assertEqual(sorted(FORBIDDEN_PLUGINS & pk.keys()), [])
        plugins = {n for n in pk if n.startswith("tauri-plugin")}
        self.assertLessEqual(plugins, ALLOWED_PLUGINS, plugins - ALLOWED_PLUGINS)

    def test_cargo_tree_of_every_desktop_target_has_no_http_client(self):
        cargo = shutil.which("cargo")
        if not cargo:
            self.skipTest("cargo not on PATH (use the per-user toolchain from SPIKE-S0.md)")
        # --locked: the resolution is exactly Cargo.lock; cargo may fetch (crates.io, checksummed) the manifests of
        # target-only crates it has not seen yet (e.g. the MSVC-only ones on this gnullvm PC).
        for target in DESKTOP_TARGETS:
            r = subprocess.run([cargo, "tree", "--locked", "--target", target, "-e", "normal,build",
                                "--prefix", "none", "--format", "{p}"],
                               cwd=SRC_TAURI, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr)
            names = {ln.split()[0] for ln in r.stdout.splitlines() if ln.strip()}
            self.assertGreater(len(names), 50, f"{target}: suspiciously small tree")
            self.assertIn("tauri", names)
            self.assertEqual(sorted(names & HTTP_CLIENT_CRATES), [], target)
            self.assertEqual(sorted(names & FORBIDDEN_PLUGINS), [], target)


class SourceScanTests(unittest.TestCase):
    SPAWN = [r"Command::new", r"std::process::Command", r"process::Command", r"tokio::process", r"\.spawn\(",
             r"CreateProcess", r"ShellExecute", r"WinExec", r"\bexecv", r"posix_spawn", r"tauri_plugin_shell",
             r"\bopen::that", r"tauri_plugin_opener", r"\bopener::"]
    WEAKEN = [r"Set-MpPreference", r"Add-MpPreference", r"spctl\s+--master-disable", r"xattr\s+-d", r"netsh\s+advfirewall",
              r"EnableLUA", r"\bcurl\b", r"\|\s*(ba)?sh\b", r"\birm\b", r"\biex\b", r"Invoke-Expression",
              r"-EncodedCommand", r"claude\s*code", r"thewhynot\.ai/(download|data|help)"]

    def test_scanned_set_is_not_empty(self):
        names = {p.relative_to(SRC_TAURI).as_posix() for p in authored_files()}
        for must in ("build.rs", "src/main.rs", "src/lib.rs", "tauri.conf.json", "isolation/index.js"):
            self.assertIn(must, names)

    def test_no_process_spawning_in_our_code(self):
        for p in authored_files():
            if p.suffix != ".rs":
                continue
            text = strip_rust_comments(p.read_text(encoding="utf-8"))
            for pat in self.SPAWN:
                self.assertIsNone(re.search(pat, text), f"{p.relative_to(SRC_TAURI)}: {pat}")

    def test_no_machine_weakening_pipe_to_shell_or_unlive_links(self):
        for p in authored_files():
            text = p.read_text(encoding="utf-8")
            for pat in self.WEAKEN:
                self.assertIsNone(re.search(pat, text, flags=re.I), f"{p.relative_to(SRC_TAURI)}: {pat}")


class RepoHygieneTests(unittest.TestCase):
    def test_build_output_and_generated_folders_are_ignored(self):
        for rel in ("target/x", "gen/schemas/x", "ui-dist/index.html"):
            r = subprocess.run(["git", "check-ignore", "-q", str(SRC_TAURI / rel)], cwd=REPO)
            self.assertEqual(r.returncode, 0, f"{rel} must be gitignored")


if __name__ == "__main__":
    unittest.main()
