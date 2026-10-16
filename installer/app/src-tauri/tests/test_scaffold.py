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
       "img-src 'self'; font-src 'self'; connect-src ipc: http://ipc.localhost; object-src 'none'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; require-trusted-types-for 'script'; "
       "trusted-types 'none'")
# The UI meta as committed in 02bca77, before the ET1-07 review fix (data: images, no form-action, no Trusted Types).
# While ui/ still carries it, the exact-equality test says so and skips; the build-time rule (build_support/csp.rs:
# the header is never looser than the meta) holds either way.
UI_CSP_02BCA77 = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
                  "connect-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")

# Local IPC origins are the only URLs allowed anywhere in the config (they are inside the CSP).
LOCAL_IPC_URLS = {"http://ipc.localhost"}

HTTP_CLIENT_CRATES = {"reqwest", "hyper", "hyper-util", "ureq", "isahc", "curl", "curl-sys", "attohttpc",
                      # no TLS stack or HTTP/2 / WebSocket client either (review info)
                      "rustls", "native-tls", "openssl", "openssl-sys", "h2", "tungstenite", "tokio-tungstenite"}
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
        # built in code (run()) so it gets the navigation guard and the new-window refusal
        self.assertIs(w["create"], False)

    def test_main_window_gets_the_navigation_guard_and_refuses_new_windows_and_downloads(self):
        # Exact wiring (no wrapper closure that could add `|| true`); the guard function itself is unit-tested in
        # cargo (NAVIGATION_GUARD) and the live test (test_live.py) proves the behaviour in WebView2.
        text = strip_rust_comments((SRC_TAURI / "src" / "lib.rs").read_text(encoding="utf-8"))
        run = text[text.index("pub fn run()"):]
        self.assertEqual(text.count("WebviewWindowBuilder::from_config("), 1)
        build = run[run.index("WebviewWindowBuilder::from_config("):run.index(".build()?")]
        calls = re.findall(r"\.(on_\w+)\((.*?)\)\s*(?=\.|$)", build, flags=re.S)
        self.assertEqual(calls, [
            ("on_navigation", "NAVIGATION_GUARD"),
            ("on_new_window", "|_url, _features| tauri::webview::NewWindowResponse::Deny"),
            ("on_download", "|_webview, _event| false"),
            ("on_permission_request", "|_webview, _kind| tauri::webview::PermissionResponse::Deny"),
        ])
        self.assertRegex(text, r"pub const NAVIGATION_GUARD: fn\(&tauri::Url\) -> bool = is_app_url;")

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
        text = text[:text.index("#[cfg(test)]")]  # the unit tests register an extra, ungranted probe command
        handlers = re.findall(r"generate_handler!\[(.*?)\]", text, flags=re.S)
        self.assertEqual(len(handlers), 1)
        names = [h.strip() for h in handlers[0].split(",") if h.strip()]
        self.assertEqual([n.removeprefix("commands::") for n in names], ALLOWED_COMMANDS)
        self.assertTrue(all(n.startswith("commands::") for n in names), names)

    def test_isolation_hook_is_a_plain_pass_through(self):
        # Review I1: page script can skip the hook (raw __TAURI_INTERNALS__.postMessage, or using the isolation frame
        # as an encryption oracle), so it is no security layer. Tauri requires the hook to exist; ours forwards the
        # message unchanged and claims nothing. The boundary is the ACL + argument validation inside each command.
        js = (SRC_TAURI / "isolation" / "index.js").read_text(encoding="utf-8")
        code = re.sub(r"//[^\n]*", "", js)
        self.assertEqual(" ".join(code.split()),
                         "'use strict'; window.__TAURI_ISOLATION_HOOK__ = function (payload) { return payload; };")
        self.assertIn("not a security boundary", js)
        self.assertNotRegex(js, r"(?i)defen[cs]e in depth|allowlist|ALLOWED")
        node = shutil.which("node")
        if node:  # run it, not only read it
            r = subprocess.run([node, "-e", "const window = {}; " + js + ";"
                                " const p = {cmd: 'x', callback: 1, error: 2, payload: {a: [1]}, options: {}};"
                                " const q = window.__TAURI_ISOLATION_HOOK__(p);"
                                " if (q !== p || JSON.stringify(q) !== JSON.stringify({cmd: 'x', callback: 1, error: 2,"
                                " payload: {a: [1]}, options: {}})) process.exit(1);"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_ui_meta_csp_agrees_except_ipc_and_frames(self):
        # The UI's own meta (ET1-07) and our header must not drift. Allowed differences, all Tauri's own needs:
        # connect-src (the IPC origins), frame-src (the isolation iframe; Tauri adds its origin to the header itself)
        # and the isolation style hash in style-src.
        html = (APP / "ui" / "index.html").read_text(encoding="utf-8")
        m = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html)
        self.assertIsNotNone(m)

        def directives(csp: str) -> dict[str, str]:
            return {d.split()[0]: " ".join(d.split()[1:]) for d in (x.strip() for x in csp.split(";")) if d}
        if m.group(1) == UI_CSP_02BCA77:
            self.skipTest("ui/index.html still carries the 02bca77 CSP; the ET1-07 review fix has not landed")
        ui, ours = directives(m.group(1)), directives(CSP)
        ours["style-src"] = ours["style-src"].replace(" " + TAURI_ISOLATION_STYLE_HASH, "")
        for d in (ui.keys() | ours.keys()) - {"connect-src", "frame-src"}:
            self.assertEqual(ui.get(d), ours.get(d), d)
        self.assertEqual(ui.get("connect-src"), "'none'")
        self.assertEqual(ours["connect-src"], "ipc: http://ipc.localhost")


class DependencyTests(unittest.TestCase):
    def test_direct_dependencies_are_pinned_exactly(self):
        manifest = tomllib.loads(CARGO_TOML.read_text(encoding="utf-8"))
        tables = [(s, manifest.get(s, {})) for s in ("dependencies", "build-dependencies", "dev-dependencies")]
        for cfg, deps in manifest.get("target", {}).items():
            tables += [(f"target.{cfg}.{s}", deps.get(s, {})) for s in ("dependencies", "dev-dependencies")]
        for section, deps in tables:
            for name, spec in deps.items():
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

    def test_single_instance_plugin_is_windows_only(self):
        # Review M1: on macOS the plugin binds a fixed socket in the shared /tmp (squatting, argv leak). We use it
        # on Windows only (a session-local named mutex); macOS relies on LaunchServices + RunEvent::Reopen.
        manifest = tomllib.loads(CARGO_TOML.read_text(encoding="utf-8"))
        self.assertNotIn("tauri-plugin-single-instance", manifest["dependencies"])
        self.assertEqual(manifest["target"]["cfg(windows)"]["dependencies"]["tauri-plugin-single-instance"]["version"],
                         "=2.5.4")
        text = strip_rust_comments((SRC_TAURI / "src" / "lib.rs").read_text(encoding="utf-8"))
        self.assertRegex(text, r"#\[cfg\(windows\)\]\s*let builder = builder\.plugin\(tauri_plugin_single_instance::init")
        self.assertRegex(text, r"#\[cfg\(target_os = \"macos\"\)\]\s*if let tauri::RunEvent::Reopen")

    def test_single_instance_mutex_is_session_local_not_global(self):
        cargo = shutil.which("cargo")
        if not cargo:
            self.skipTest("cargo not on PATH (use the per-user toolchain from SPIKE-S0.md)")
        r = subprocess.run([cargo, "metadata", "--locked", "--format-version", "1", "--filter-platform",
                            "x86_64-pc-windows-msvc"], cwd=SRC_TAURI, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        pkg = next(p for p in json.loads(r.stdout)["packages"] if p["name"] == "tauri-plugin-single-instance")
        src = (pathlib.Path(pkg["manifest_path"]).parent / "src" / "platform_impl" / "windows.rs").read_text(
            encoding="utf-8")
        self.assertIn('let mutex_name = encode_wide(format!("{id}-sim"));', src)  # no namespace prefix = Local\\
        self.assertNotIn("Global\\", src)
        self.assertNotIn("Global\\\\", src)

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
            self.assertEqual("tauri-plugin-single-instance" in names, "windows" in target, target)


UNVALIDATED_ARG_TYPES = r"(String|&\s*str|str|Value|serde_json::Value|PathBuf|&\s*Path|Path|OsString|Vec<[^>]*>|" \
    r"HashMap<[^>]*>|BTreeMap<[^>]*>|Option<[^>]*>|Box<[^>]*>|u8|u16|u32|u64|u128|usize|i8|i16|i32|i64|i128|isize|" \
    r"f32|f64|bool|char|tauri::ipc::Request<'_>|Request<'_>|InvokeBody)"
INJECTED_ARG_TYPES = r"(tauri::)?(AppHandle|Window|WebviewWindow|Webview|State)(<[^>]*>)?"


def command_arg_violations(source: str) -> list[str]:
    """The rule for every #[tauri::command] (review I1): each argument the page sends is a type of ours that validates
    itself while it is deserialised (serde `try_from`, typed and bounded), never a raw String/number/Value/path/
    collection. Tauri-injected handles (AppHandle, Window, State, ...) are not page input."""
    out = []
    text = strip_rust_comments(source)
    for m in re.finditer(r"#\[tauri::command[^\]]*\]\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)\s*"
                         r"(?:<[^>]*>)?\((.*?)\)\s*(?:->|\{|where)", text, flags=re.S):
        name, params = m.group(1), m.group(2)
        depth, cur, parts = 0, "", []
        for ch in params:
            depth += ch in "<([" ; depth -= ch in ">)]"
            if ch == "," and depth == 0:
                parts.append(cur); cur = ""
            else:
                cur += ch
        parts.append(cur)
        for part in (x.strip() for x in parts if x.strip()):
            ty = part.split(":", 1)[1].strip() if ":" in part else part
            if re.fullmatch(INJECTED_ARG_TYPES, ty):
                continue
            if re.fullmatch(UNVALIDATED_ARG_TYPES, ty):
                out.append(f"{name}: {part} is a raw type; use a validating newtype (serde try_from)")
                continue
            tname = re.sub(r"<.*", "", ty).split("::")[-1]
            if not re.search(r"#\[serde\(try_from\s*=\s*\"[^\"]+\"\)\]\s*(?:#\[[^\]]*\]\s*)*"
                             r"pub(?:\([^)]*\))?\s+(?:struct|enum)\s+" + re.escape(tname) + r"\b", text):
                out.append(f"{name}: {part}: {tname} must be declared with #[serde(try_from = ...)] in the same crate")
    return out


class CommandArgumentRuleTests(unittest.TestCase):
    def test_every_command_validates_its_own_arguments(self):
        src = "\n".join(p.read_text(encoding="utf-8") for p in sorted((SRC_TAURI / "src").rglob("*.rs")))
        self.assertGreaterEqual(src.count("#[tauri::command]"), 1)
        self.assertEqual(command_arg_violations(src), [])

    def test_the_rule_checker_catches_raw_arguments(self):
        bad = """
        #[tauri::command]
        fn open(id: String, n: u32) -> () {}
        #[tauri::command]
        async fn pick(app: tauri::AppHandle, kind: Kind) -> () {}
        #[derive(Deserialize)]
        pub struct Kind(String);
        """
        self.assertEqual(len(command_arg_violations(bad)), 3, command_arg_violations(bad))
        good = """
        #[tauri::command]
        fn open(app: tauri::AppHandle, id: LinkId) -> Result<(), Error> {}
        #[derive(Deserialize)]
        #[serde(try_from = "String")]
        pub struct LinkId(String);
        """
        self.assertEqual(command_arg_violations(good), [])


class BuildRefusalTests(unittest.TestCase):
    """D-04 (review I4): a 3.0 build can never say it is signed. Each probe uses its own target folder."""

    def _check(self, sub: str, env_extra: dict) -> subprocess.CompletedProcess:
        cargo = shutil.which("cargo")
        if not cargo:
            self.skipTest("cargo not on PATH (use the per-user toolchain from SPIKE-S0.md)")
        base = os.environ.get("CARGO_TARGET_DIR") or str(pathlib.Path(os.environ.get("TEMP", "/tmp")) / "wnc-target")
        env = dict(os.environ, CARGO_TARGET_DIR=str(pathlib.Path(base) / "probe" / sub), **env_extra)
        env.pop("WNC_BUILD_SIGNED", None) if "WNC_BUILD_SIGNED" not in env_extra else None
        return subprocess.run([cargo, "check", "--locked", "--lib"], cwd=SRC_TAURI, env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace")

    def test_cfg_wnc_build_signed_fails_the_build(self):
        r = self._check("cfg-signed", {"RUSTFLAGS": "--cfg wnc_build_signed"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("D-04", r.stderr)

    def test_the_env_var_set_even_to_false_fails_the_build(self):
        r = self._check("env-signed", {"WNC_BUILD_SIGNED": "false"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("WNC_BUILD_SIGNED is set", r.stderr)


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

    def test_no_network_or_shared_tmp_paths_in_our_code(self):
        for p in authored_files():
            if p.suffix != ".rs":
                continue
            text = strip_rust_comments(p.read_text(encoding="utf-8"))
            for pat in [r"std::net", r"TcpStream", r"TcpListener", r"UdpSocket", r"tokio::net", r"UnixListener",
                        r"UnixStream", r"\"/tmp", r"/tmp/", r"temp_dir\(\)"]:
                if p.name == "stage.rs" and pat == r"temp_dir\(\)":
                    continue  # its unit tests make scratch folders in the (per-user, D:) TEMP
                self.assertIsNone(re.search(pat, text), f"{p.relative_to(SRC_TAURI)}: {pat}")

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
