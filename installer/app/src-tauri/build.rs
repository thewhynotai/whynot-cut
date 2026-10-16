// WhyNot Cut Setup build script (ET1-17).
// 1. D-04: resolve WNC_BUILD_SIGNED (3.0 accepts only unset/false; see build_support/flags.rs).
// 2. Stage the UI bundle: installer/app/ui + ui/vendor.json -> src-tauri/ui-dist (= frontendDist, gitignored);
//    each page's CSP meta must agree with the app's CSP header and is dropped from the staged copy.
// 3. tauri-build with an app manifest that lists our commands, so each one needs an explicit capability grant
//    (without it, Tauri lets the local UI call every registered app command).

#[path = "build_support/flags.rs"]
mod flags;
#[path = "build_support/stage.rs"]
mod stage;

use std::env;
use std::path::PathBuf;

fn vendor_files(json: &str) -> Vec<stage::VendorFile> {
    let v: serde_json::Value = serde_json::from_str(json).expect("ui/vendor.json is not valid JSON");
    v["files"]
        .as_array()
        .expect("ui/vendor.json needs a files[] array")
        .iter()
        .map(|f| stage::VendorFile {
            to: f["to"].as_str().expect("vendor.json files[].to must be a string").to_owned(),
            from: f["from"].as_str().expect("vendor.json files[].from must be a string").to_owned(),
        })
        .collect()
}

fn main() {
    let manifest = PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("cargo sets CARGO_MANIFEST_DIR"));

    // 1. D-04
    println!("cargo:rerun-if-env-changed={}", flags::ENV);
    println!("cargo:rustc-check-cfg=cfg(wnc_build_signed)");
    match flags::resolve_signed(env::var(flags::ENV).ok().as_deref()) {
        Ok(true) => println!("cargo:rustc-cfg=wnc_build_signed"),
        Ok(false) => {}
        Err(e) => panic!("{e}"),
    }

    // 2. The UI bundle
    let ui = manifest.join("../ui");
    let repo = manifest.join("../../..");
    let vendor_json = ui.join("vendor.json");
    let vendor = vendor_files(&std::fs::read_to_string(&vendor_json).expect("cannot read ui/vendor.json"));
    // The app's CSP header; each staged page's CSP meta must agree with it and is then dropped
    // (build_support/csp.rs explains why the header must be the only policy under the isolation pattern).
    let conf: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(manifest.join("tauri.conf.json")).expect("cannot read tauri.conf.json"),
    )
    .expect("tauri.conf.json is not valid JSON");
    let header_csp = conf["app"]["security"]["csp"].as_str().expect("app.security.csp must be a string");
    let sources = stage::stage(&ui, &repo, &vendor, &manifest.join("ui-dist"), header_csp)
        .unwrap_or_else(|e| panic!("staging the UI bundle failed: {e}"));
    println!("cargo:rerun-if-changed={}", ui.display()); // a folder: cargo watches every file in it
    for s in sources {
        println!("cargo:rerun-if-changed={}", s.display());
    }
    for local in ["capabilities", "isolation", "icons", "tauri.conf.json"] {
        println!("cargo:rerun-if-changed={}", manifest.join(local).display());
    }

    // 3. tauri-build: the app commands the UI may call (each still needs a grant in capabilities/).
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(&["app_info"])),
    )
    .expect("tauri-build failed");
}
