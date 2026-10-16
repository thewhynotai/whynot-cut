//! WhyNot Cut Setup: the thin, network-free Tauri 2 shell over the Python installer core (ET1-17 scaffold).
//!
//! # The security boundary
//! The UI may call only the commands registered in `run()` AND granted in `capabilities/main-window.json`. build.rs
//! declares them in the app manifest, so the ACL refuses any registered command that is not granted. That ACL, plus
//! argument validation inside every command, IS the boundary. The isolation hook (isolation/index.js) is not one:
//! page script can skip it (review I1), so it only forwards messages.
//!
//! # The rule for every `#[tauri::command]` (ET1-18/19 follow it; tests/test_scaffold.py enforces it)
//! Every argument the page sends is a type of ours that validates itself while it is deserialised
//! (`#[serde(try_from = "...")]`: typed, bounded, ids from a fixed set), never a raw `String`, number, `Value`, path
//! or collection. Never trust anything because "the UI or the hook already checked it".
//!
//! Today there is one command, the `app_info` stub. The bridge to the core is ET1-18, the id-based OS actions ET1-19.

use serde::Serialize;
#[cfg(any(windows, target_os = "macos"))]
use tauri::Manager;

/// D-04: 3.0 builds are always unsigned "internal" builds. A literal, not a cfg or an env var: build.rs refuses
/// `WNC_BUILD_SIGNED` set to anything, and `--cfg wnc_build_signed` stops the compile below. Phase 2 (real signing)
/// replaces this with a checked value.
pub const BUILD_SIGNED: bool = false;

#[cfg(wnc_build_signed)]
compile_error!("--cfg wnc_build_signed is refused: 3.0 builds are always unsigned internal builds (D-04); signing is phase 2");

/// What the UI learns about this build: the version and whether to show the "internal build" chip.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct AppInfo {
    pub version: &'static str,
    pub signed: bool,
    pub internal_build: bool,
}

/// The `app_info` answer for a given signing state (the command passes `BUILD_SIGNED`).
pub fn app_info_for(signed: bool) -> AppInfo {
    AppInfo { version: env!("CARGO_PKG_VERSION"), signed, internal_build: !signed }
}

/// The commands the UI may call (each also needs its grant in capabilities/main-window.json and its name in build.rs).
/// A module, not the crate root: `pub` command functions there clash with the names tauri's macro exports.
pub mod commands {
    use super::{app_info_for, AppInfo, BUILD_SIGNED};

    /// Takes no arguments (nothing from the page to validate).
    #[tauri::command]
    pub fn app_info() -> AppInfo {
        app_info_for(BUILD_SIGNED)
    }
}

/// Bring the one window to the front: a second launch on Windows (single-instance plugin) or a reopen on macOS
/// (LaunchServices). Whatever the second launch carried (argv, cwd) is ignored on purpose.
#[cfg(any(windows, target_os = "macos"))]
fn focus_main_window<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}

/// The app's own origin, the only place the window may navigate to: `http://tauri.localhost` on Windows (Tauri's
/// custom protocol over WebView2), `tauri://localhost` on macOS/Linux. CSP does not govern navigation, so this does.
/// Tauri itself always lets its isolation iframe load (`isolation-<uuid>`), and that check runs before ours; on
/// macOS that pre-allowance may also cover a top-level navigation to that scheme (review L6, a UI-only DoS; the
/// ET1-22 Mac selftest checks it).
pub fn is_app_url(url: &tauri::Url) -> bool {
    is_app_url_on(url, cfg!(windows))
}

/// `is_app_url` for a given platform (testable on every OS).
pub fn is_app_url_on(url: &tauri::Url, windows: bool) -> bool {
    let (scheme, host) = if windows { ("http", "tauri.localhost") } else { ("tauri", "localhost") };
    url.scheme() == scheme
        && url.host_str() == Some(host)
        && url.port().is_none()
        && url.username().is_empty()
        && url.password().is_none()
}

/// The navigation guard the main window gets: the function itself, no wrapper (unit-tested here, wiring checked by
/// tests/test_scaffold.py, behaviour proven live by tests/test_live.py).
pub const NAVIGATION_GUARD: fn(&tauri::Url) -> bool = is_app_url;

/// Start the app.
pub fn run() {
    let builder = tauri::Builder::default();
    // Windows: one instance per session: the plugin's named mutex `<identifier>-sim` has no `Global\` prefix, so it
    // lives in the session-local namespace. It must be the first plugin (upstream rule).
    // macOS: no plugin (its fixed socket in the shared /tmp could be squatted, review M1). LaunchServices keeps one
    // instance of the .app, and a second open arrives as RunEvent::Reopen below.
    #[cfg(windows)]
    let builder = builder.plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| focus_main_window(app)));
    let app = builder
        .invoke_handler(tauri::generate_handler![commands::app_info])
        .setup(|app| {
            // The window is declared in tauri.conf.json with create:false and built here, so it gets the guards:
            // navigation only within the bundle, no new windows (window.open, target=_blank), no downloads, and
            // every web permission request (camera, microphone, location, clipboard read, notifications, repeated
            // automatic downloads, ...) denied without a prompt: the installer UI needs none of them.
            let conf = app
                .config()
                .app
                .windows
                .iter()
                .find(|w| w.label == "main")
                .cloned()
                .ok_or("tauri.conf.json has no main window")?;
            tauri::WebviewWindowBuilder::from_config(app.handle(), &conf)?
                .on_navigation(NAVIGATION_GUARD)
                .on_new_window(|_url, _features| tauri::webview::NewWindowResponse::Deny)
                .on_download(|_webview, _event| false)
                .on_permission_request(|_webview, _kind| tauri::webview::PermissionResponse::Deny)
                .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("WhyNot Cut Setup could not start");
    app.run(|_app, _event| {
        #[cfg(target_os = "macos")]
        if let tauri::RunEvent::Reopen { .. } = _event {
            focus_main_window(_app);
        }
    });
}

#[cfg(test)]
#[path = "../build_support/flags.rs"]
mod flags;

#[cfg(test)]
#[path = "../build_support/stage.rs"]
mod stage;

#[cfg(test)]
mod tests {
    use super::commands::app_info;
    use super::*;
    use tauri::ipc::Origin;

    const ISOLATION_STYLE_HASH: &str = "'sha256-YEercZJImS+vUX2bz7vkQ0aA4rtBIPLuCEWz+yraQ/g='";
    const CSP: &str = "default-src 'self'; script-src 'self'; \
                       style-src 'self' 'sha256-YEercZJImS+vUX2bz7vkQ0aA4rtBIPLuCEWz+yraQ/g='; img-src 'self'; \
                       font-src 'self'; connect-src ipc: http://ipc.localhost; object-src 'none'; \
                       base-uri 'none'; form-action 'none'; frame-ancestors 'none'; \
                       require-trusted-types-for 'script'; trusted-types 'none'";

    fn context() -> tauri::Context<tauri::Wry> {
        tauri::generate_context!()
    }

    // --- app_info -------------------------------------------------------------------------------------------

    #[test]
    fn app_info_reports_the_crate_version() {
        assert_eq!(app_info().version, env!("CARGO_PKG_VERSION"));
        assert!(!app_info().version.is_empty());
    }

    #[test]
    fn this_build_is_unsigned_and_internal() {
        assert!(!BUILD_SIGNED);
        let info = app_info();
        assert!(!info.signed);
        assert!(info.internal_build);
    }

    #[test]
    fn internal_build_is_exactly_not_signed() {
        assert!(app_info_for(false).internal_build);
        assert!(!app_info_for(true).internal_build);
        assert!(app_info_for(true).signed);
    }

    #[test]
    fn app_info_serialises_to_exactly_three_keys() {
        let v = serde_json::to_value(app_info()).unwrap();
        let mut keys: Vec<_> = v.as_object().unwrap().keys().cloned().collect();
        keys.sort();
        assert_eq!(keys, ["internal_build", "signed", "version"]);
        assert_eq!(v["version"], env!("CARGO_PKG_VERSION"));
        assert_eq!(v["signed"], false);
        assert_eq!(v["internal_build"], true);
    }

    // --- the compiled context (what generate_context! actually embedded) -------------------------------------

    #[test]
    fn compiled_pattern_is_isolation() {
        let ctx = context();
        match ctx.pattern() {
            // codegen suffixes a random id per build: "isolation-<uuid>"
            tauri::Pattern::Isolation { schema, .. } => assert!(schema.starts_with("isolation-"), "{schema}"),
            other => panic!("expected the isolation pattern, got {other:?}"),
        }
    }

    #[test]
    fn compiled_config_has_the_exact_csp_and_no_dev_url() {
        let ctx = context();
        let conf = ctx.config();
        assert_eq!(conf.app.security.csp.as_ref().map(|c| c.to_string()).as_deref(), Some(CSP));
        assert!(conf.app.security.dev_csp.is_none());
        assert!(conf.build.dev_url.is_none());
        assert!(!conf.app.with_global_tauri);
        assert!(conf.app.security.freeze_prototype);
    }

    #[test]
    fn csp_style_hash_is_the_one_tauri_injects_for_the_isolation_iframe() {
        // Tauri's isolation injector appends <style>IFRAME_STYLE</style> to hide its iframe. Without this hash the
        // style is blocked and the iframe shows as a box in the page (seen live). A Tauri bump that changes the text
        // fails here instead of in the window.
        use base64::Engine as _;
        use sha2::Digest as _;
        let style = tauri::utils::pattern::isolation::IFRAME_STYLE;
        let hash = base64::engine::general_purpose::STANDARD.encode(sha2::Sha256::digest(style.as_bytes()));
        assert_eq!(ISOLATION_STYLE_HASH, format!("'sha256-{hash}'"));
        assert!(CSP.contains(ISOLATION_STYLE_HASH));
    }

    #[test]
    fn compiled_assets_hold_the_whole_staged_ui() {
        use std::path::Path;
        use tauri::utils::assets::AssetKey;
        let ctx = context();
        let assets = ctx.assets();
        let ui = Path::new(env!("CARGO_MANIFEST_DIR")).join("../ui");
        // 1. every file of ui/ except the build metadata
        fn walk(base: &Path, d: &Path, out: &mut Vec<String>) {
            for e in std::fs::read_dir(d).unwrap() {
                let p = e.unwrap().path();
                let rel = p.strip_prefix(base).unwrap().to_string_lossy().replace('\\', "/");
                if rel == "vendor.json" || rel == "vendor" {
                    continue;
                }
                if p.is_dir() {
                    walk(base, &p, out);
                } else {
                    out.push(rel);
                }
            }
        }
        let mut files = Vec::new();
        walk(&ui, &ui, &mut files);
        let vendor: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(ui.join("vendor.json")).unwrap()).unwrap();
        // With ui/stage.json, exactly its files ship and nothing in dev_only does.
        if let Ok(text) = std::fs::read_to_string(ui.join("stage.json")) {
            let list: serde_json::Value = serde_json::from_str(&text).unwrap();
            let strs = |k: &str| -> Vec<String> {
                list[k].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_owned()).collect()
            };
            files.retain(|f| f != "stage.json");
            let (ship, dev) = (strs("files"), strs("dev_only"));
            for d in &dev {
                assert!(assets.get(&AssetKey::from(d.as_str())).is_none(), "dev_only {d} is shipped");
            }
            files.retain(|f| ship.contains(f));
            assert_eq!(files.len(), ship.len(), "every listed file exists in ui/");
        }
        assert!(files.iter().any(|f| f == "index.html"));
        for f in &files {
            assert!(assets.get(&AssetKey::from(f.as_str())).is_some(), "ui/{f} missing from the app");
        }
        // 2. every vendor file, byte-equal to its one source in the repo
        let entries = vendor["files"].as_array().unwrap();
        assert!(!entries.is_empty());
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
        for e in entries {
            let (to, from) = (e["to"].as_str().unwrap(), e["from"].as_str().unwrap());
            let got = assets.get(&AssetKey::from(to)).unwrap_or_else(|| panic!("{to} missing from the app"));
            assert_eq!(got.as_ref(), std::fs::read(repo.join(from)).unwrap().as_slice(), "{to} differs from {from}");
        }
        // 3. build metadata is not shipped
        assert!(assets.get(&AssetKey::from("vendor.json")).is_none());
        assert!(assets.get(&AssetKey::from("stage.json")).is_none());
        // 4. the header is the only CSP in the app: no staged page keeps the meta (build_support/csp.rs)
        for f in files.iter().filter(|f| f.ends_with(".html")) {
            let html = assets.get(&AssetKey::from(f.as_str())).unwrap();
            let html = String::from_utf8_lossy(html.as_ref()).to_ascii_lowercase();
            assert!(!html.contains("content-security-policy"), "{f} still carries a CSP meta");
        }
    }

    // --- navigation guard -------------------------------------------------------------------------------------

    fn u(s: &str) -> tauri::Url {
        s.parse().unwrap()
    }

    #[test]
    fn windows_allows_only_its_own_origin() {
        for ok in ["http://tauri.localhost/", "http://tauri.localhost/index.html?lang=ar&os=win#top",
                   "http://tauri.localhost/js/main.js"] {
            assert!(is_app_url_on(&u(ok), true), "{ok} must be allowed");
        }
        for bad in ["https://tauri.localhost/", "http://tauri.localhost:8080/", "http://user@tauri.localhost/",
                    "http://u:p@tauri.localhost/", "http://tauri.localhost.evil.example/", "http://evil.example/",
                    "https://wa.me/201000000000", "http://ipc.localhost/app_info", "http://localhost/",
                    "tauri://localhost/", "file:///C:/Windows/win.ini", "about:blank", "javascript:alert(1)",
                    "data:text/html,hi", "blob:http://tauri.localhost/x"] {
            assert!(!is_app_url_on(&u(bad), true), "{bad} must be refused");
        }
    }

    #[test]
    fn macos_allows_only_its_own_origin() {
        assert!(is_app_url_on(&u("tauri://localhost/index.html"), false));
        for bad in ["http://tauri.localhost/", "tauri://evil/", "tauri://localhost.evil/", "https://localhost/",
                    "tauri://user@localhost/", "file:///etc/passwd", "about:blank"] {
            assert!(!is_app_url_on(&u(bad), false), "{bad} must be refused");
        }
    }


    // --- what is embedded: never the demo body or a test file, whatever the lists say -------------------------

    #[test]
    fn no_demo_or_test_file_is_embedded() {
        let ctx = context();
        let keys: Vec<String> = ctx.assets().iter().map(|(k, _)| k.into_owned()).collect();
        assert!(keys.iter().any(|k| k.ends_with("index.html")), "{keys:?}");
        for k in &keys {
            let k = k.trim_start_matches('/');
            assert!(!stage::never_ships(k), "{k} is embedded");
            assert!(!k.ends_with("demo.js") && !k.ends_with("stage.json") && !k.ends_with("vendor.json"), "{k}");
        }
    }

    // --- D-04 -------------------------------------------------------------------------------------------------

    #[test]
    fn build_signed_is_a_literal_false_in_3_0() {
        // `--cfg wnc_build_signed` cannot flip it: that cfg is a compile_error! (tests/test_scaffold.py builds it).
        const { assert!(!BUILD_SIGNED) };
        assert!(!cfg!(wnc_build_signed));
    }

    // --- the navigation guard is the function the builder gets ----------------------------------------------

    #[test]
    fn the_navigation_guard_given_to_the_builder_refuses_other_origins() {
        let guard: fn(&tauri::Url) -> bool = NAVIGATION_GUARD;
        assert!(guard(&u(if cfg!(windows) { "http://tauri.localhost/index.html" } else { "tauri://localhost/" })));
        for bad in ["https://example.com/", "http://127.0.0.1:9/", "file:///C:/x", "about:blank", "data:text/html,x"] {
            assert!(!guard(&u(bad)), "{bad}");
        }
    }

    #[test]
    fn the_main_window_is_built_in_code_with_the_guards() {
        // create:false in the config, so run() builds it with on_navigation + on_new_window (Deny).
        let ctx = context();
        assert!(!ctx.config().app.windows[0].create);
    }

    #[test]
    fn compiled_window_sizes_and_title() {
        let ctx = context();
        let w = &ctx.config().app.windows;
        assert_eq!(w.len(), 1);
        assert_eq!((w[0].label.as_str(), w[0].title.as_str()), ("main", "WhyNot Cut"));
        assert_eq!((w[0].width, w[0].height), (760.0, 540.0));
        assert_eq!((w[0].min_width, w[0].min_height), (Some(640.0), Some(480.0)));
    }

    // --- the resolved ACL -------------------------------------------------------------------------------------

    #[test]
    fn acl_allows_app_info_for_the_main_window_only() {
        let mut ctx = context();
        let auth = ctx.runtime_authority_mut();
        assert!(auth.resolve_access("app_info", "main", "main", &Origin::Local).is_some());
        assert!(auth.resolve_access("app_info", "other", "other", &Origin::Local).is_none());
        let remote = Origin::Remote { url: "https://example.com/".parse().unwrap() };
        assert!(auth.resolve_access("app_info", "main", "main", &remote).is_none());
    }

    #[test]
    fn acl_refuses_every_other_command() {
        let mut ctx = context();
        let auth = ctx.runtime_authority_mut();
        for cmd in [
            "secret_command",
            "plugin:event|listen",
            "plugin:event|emit",
            "plugin:window|close",
            "plugin:window|set_title",
            "plugin:webview|create_webview_window",
            "plugin:app|version",
            "plugin:path|resolve_directory",
            "plugin:resources|close",
            "plugin:menu|new",
            "plugin:tray|new",
            "plugin:image|new",
            "plugin:single-instance|anything",
            "plugin:shell|execute",
            "plugin:shell|open",
            "plugin:opener|open_url",
            "plugin:fs|read_file",
            "plugin:http|fetch",
            "plugin:updater|check",
            "plugin:dialog|open",
        ] {
            assert!(auth.resolve_access(cmd, "main", "main", &Origin::Local).is_none(), "{cmd} must be refused");
        }
    }
}
