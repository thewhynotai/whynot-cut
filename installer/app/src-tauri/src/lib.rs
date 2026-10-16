//! WhyNot Cut Setup: the thin, network-free Tauri 2 shell over the Python installer core (ET1-17 scaffold).
//!
//! The UI may call only the commands registered in `run()` AND granted in `capabilities/main-window.json`
//! (build.rs declares them in the app manifest, so an ungranted command is refused by the ACL). Today that is one
//! stub, `app_info`. The bridge to the core is ET1-18, the id-based OS actions are ET1-19.

use serde::Serialize;
use tauri::Manager;

/// D-04: true only in a signed build. build.rs refuses `WNC_BUILD_SIGNED=true` in 3.0, so this is false here.
pub const BUILD_SIGNED: bool = cfg!(wnc_build_signed);

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

#[tauri::command]
fn app_info() -> AppInfo {
    app_info_for(BUILD_SIGNED)
}

/// A second launch hands over to the first instance and exits; the first one only comes to the front.
/// The second instance's argv and cwd are ignored on purpose: no input crosses that boundary.
fn focus_main_window<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}

/// Start the app.
pub fn run() {
    tauri::Builder::default()
        // single-instance must be the first plugin (upstream rule): the second process exits before anything else.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| focus_main_window(app)))
        .invoke_handler(tauri::generate_handler![app_info])
        .run(tauri::generate_context!())
        .expect("WhyNot Cut Setup could not start");
}

#[cfg(test)]
#[path = "../build_support/flags.rs"]
mod flags;

#[cfg(test)]
#[path = "../build_support/stage.rs"]
mod stage;

#[cfg(test)]
mod tests {
    use super::*;
    use tauri::ipc::Origin;

    const ISOLATION_STYLE_HASH: &str = "'sha256-YEercZJImS+vUX2bz7vkQ0aA4rtBIPLuCEWz+yraQ/g='";
    const CSP: &str = "default-src 'self'; script-src 'self'; \
                       style-src 'self' 'sha256-YEercZJImS+vUX2bz7vkQ0aA4rtBIPLuCEWz+yraQ/g='; img-src 'self' data:; \
                       font-src 'self'; connect-src ipc: http://ipc.localhost; object-src 'none'; \
                       base-uri 'none'; frame-ancestors 'none'";

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
        assert!(files.iter().any(|f| f == "index.html"));
        for f in &files {
            assert!(assets.get(&AssetKey::from(f.as_str())).is_some(), "ui/{f} missing from the app");
        }
        // 2. every vendor file, byte-equal to its one source in the repo
        let vendor: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(ui.join("vendor.json")).unwrap()).unwrap();
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
        // 4. the header is the only CSP in the app: no staged page keeps the meta (build_support/csp.rs)
        for f in files.iter().filter(|f| f.ends_with(".html")) {
            let html = assets.get(&AssetKey::from(f.as_str())).unwrap();
            let html = String::from_utf8_lossy(html.as_ref()).to_ascii_lowercase();
            assert!(!html.contains("content-security-policy"), "{f} still carries a CSP meta");
        }
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
            "__wnc_isolation_refused__",
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
