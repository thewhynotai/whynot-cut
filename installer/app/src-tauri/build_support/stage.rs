//! Stage the UI bundle for Tauri: `installer/app/ui/**` + the files `ui/vendor.json` maps from their one source in
//! the repo (brand tokens, fonts, the monogram), into `src-tauri/ui-dist/` (gitignored), which is `frontendDist`.
//! This is the build-time twin of `installer/app/tests/_harness.py::stage()` (without the test fixtures), as the
//! ET1-07 hand-off asks. Shared by build.rs and the lib's unit tests; std only (build.rs parses vendor.json).
//!
//! Safety: never follows a link. A symlink or junction anywhere in the source tree, as a vendor source, or as the
//! destination is refused (an error, not a skip). Vendor paths must be plain relative paths (no `..`, no root, no
//! drive) and every destination must sit under `vendor/`.

use std::fs;
use std::path::{Component, Path, PathBuf};

#[path = "csp.rs"]
pub mod csp;

/// One `files[]` entry of `ui/vendor.json`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VendorFile {
    pub to: String,
    pub from: String,
}

/// Names in the top level of `ui/` that are never shipped: build metadata and a stray local vendor copy.
pub const SKIP_TOP: &[&str] = &["vendor.json", "vendor"];

/// A plain relative path: only normal components, at least one, `/` separators only.
pub fn safe_rel(raw: &str) -> Result<PathBuf, String> {
    let bad = |why: &str| Err(format!("unsafe path {raw:?}: {why}"));
    if raw.is_empty() {
        return bad("empty");
    }
    if raw.contains('\\') || raw.contains(':') {
        return bad("only '/' separators, no drive or stream");
    }
    if raw.starts_with('/') {
        return bad("absolute");
    }
    let mut out = PathBuf::new();
    for part in raw.split('/') {
        if part.is_empty() || part == "." || part == ".." {
            return bad("empty, '.' or '..' component");
        }
        out.push(part);
    }
    // Belt and braces: the platform must agree that every component is a normal one.
    if !out.components().all(|c| matches!(c, Component::Normal(_))) {
        return bad("not a plain relative path");
    }
    Ok(out)
}

fn is_link(p: &Path) -> Result<bool, String> {
    // symlink_metadata never follows; on Windows a junction (a name-surrogate reparse point) reports is_symlink.
    let md = fs::symlink_metadata(p).map_err(|e| format!("{}: {e}", p.display()))?;
    Ok(md.file_type().is_symlink())
}

fn copy_tree(src: &Path, dst: &Path, top: bool, header_csp: &str) -> Result<(), String> {
    fs::create_dir_all(dst).map_err(|e| format!("{}: {e}", dst.display()))?;
    let mut entries: Vec<_> = fs::read_dir(src)
        .map_err(|e| format!("{}: {e}", src.display()))?
        .collect::<Result<_, _>>()
        .map_err(|e| format!("{}: {e}", src.display()))?;
    entries.sort_by_key(|e| e.file_name());
    for entry in entries {
        let name = entry.file_name();
        if top && SKIP_TOP.iter().any(|s| name == *s) {
            continue;
        }
        let from = entry.path();
        if is_link(&from)? {
            return Err(format!("refusing a link in the UI tree: {}", from.display()));
        }
        let to = dst.join(&name);
        if from.is_dir() {
            copy_tree(&from, &to, false, header_csp)?;
        } else if from.extension().is_some_and(|e| e.eq_ignore_ascii_case("html")) {
            let html = fs::read_to_string(&from).map_err(|e| format!("{}: {e}", from.display()))?;
            let html = csp::strip_meta(&html, header_csp).map_err(|e| format!("{}: {e}", from.display()))?;
            fs::write(&to, html).map_err(|e| format!("{}: {e}", to.display()))?;
        } else {
            fs::copy(&from, &to).map_err(|e| format!("{} -> {}: {e}", from.display(), to.display()))?;
        }
    }
    Ok(())
}

/// Replace `dest` with a fresh copy of `ui` (minus SKIP_TOP) plus the vendor files. Returns the vendor sources
/// (absolute) so build.rs can emit `rerun-if-changed` for each.
/// Every staged `.html` loses its CSP meta after csp::strip_meta checks it agrees with `header_csp`.
pub fn stage(ui: &Path, repo: &Path, vendor: &[VendorFile], dest: &Path, header_csp: &str)
    -> Result<Vec<PathBuf>, String> {
    if !ui.join("index.html").is_file() {
        return Err(format!("the UI bundle has no index.html: {}", ui.display()));
    }
    // Validate everything before touching dest.
    let mut plan = Vec::with_capacity(vendor.len());
    for f in vendor {
        let to = safe_rel(&f.to)?;
        if !f.to.starts_with("vendor/") {
            return Err(format!("vendor destination {:?} must be under vendor/", f.to));
        }
        let from = repo.join(safe_rel(&f.from)?);
        if !from.is_file() || is_link(&from)? {
            return Err(format!("vendor source {:?} is missing or not a regular file", f.from));
        }
        plan.push((from, to));
    }
    if dest.exists() || is_link(dest).unwrap_or(false) {
        if is_link(dest)? {
            return Err(format!("refusing a link as the staging folder: {}", dest.display()));
        }
        // std's remove_dir_all does not follow links inside the tree (it removes the link itself).
        fs::remove_dir_all(dest).map_err(|e| format!("{}: {e}", dest.display()))?;
    }
    copy_tree(ui, dest, true, header_csp)?;
    let mut sources = Vec::with_capacity(plan.len());
    for (from, to) in plan {
        let out = dest.join(&to);
        fs::create_dir_all(out.parent().expect("vendor/ prefix gives a parent"))
            .map_err(|e| format!("{}: {e}", out.display()))?;
        fs::copy(&from, &out).map_err(|e| format!("{} -> {}: {e}", from.display(), out.display()))?;
        sources.push(from);
    }
    Ok(sources)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static N: AtomicUsize = AtomicUsize::new(0);
    const H: &str = "default-src 'self'; connect-src ipc: http://ipc.localhost";

    fn scratch() -> PathBuf {
        let d = std::env::temp_dir().join(format!(
            "wnc-et1-17-stage-{}-{}",
            std::process::id(),
            N.fetch_add(1, Ordering::SeqCst)
        ));
        if d.exists() {
            fs::remove_dir_all(&d).unwrap();
        }
        fs::create_dir_all(&d).unwrap();
        d
    }

    fn write(p: &Path, s: &str) {
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(p, s).unwrap();
    }

    fn vf(to: &str, from: &str) -> VendorFile {
        VendorFile { to: to.into(), from: from.into() }
    }

    /// repo/{brand/tokens.css, fonts/a.ttf} and repo/installer/app/ui/{index.html, js/main.js, vendor.json, vendor/x}
    fn fixture() -> (PathBuf, PathBuf, PathBuf) {
        let root = scratch();
        let repo = root.join("repo");
        let ui = repo.join("installer/app/ui");
        write(&repo.join("brand/tokens.css"), ":root{}");
        write(&repo.join("fonts/a.ttf"), "font");
        write(&ui.join("index.html"), "<!doctype html>");
        write(&ui.join("js/main.js"), "export {}");
        write(&ui.join("vendor.json"), "{}");
        write(&ui.join("vendor/stale.css"), "stale");
        (repo, ui, root.join("dist"))
    }

    fn listing(dir: &Path) -> Vec<String> {
        let mut out = Vec::new();
        fn walk(base: &Path, d: &Path, out: &mut Vec<String>) {
            for e in fs::read_dir(d).unwrap() {
                let p = e.unwrap().path();
                if p.is_dir() {
                    walk(base, &p, out);
                } else {
                    out.push(p.strip_prefix(base).unwrap().to_string_lossy().replace('\\', "/"));
                }
            }
        }
        walk(dir, dir, &mut out);
        out.sort();
        out
    }

    #[test]
    fn safe_rel_accepts_plain_relative_paths() {
        assert_eq!(safe_rel("vendor/fonts/a.ttf").unwrap(), PathBuf::from("vendor/fonts/a.ttf"));
        assert_eq!(safe_rel("brand/tokens.css").unwrap(), PathBuf::from("brand/tokens.css"));
    }

    #[test]
    fn safe_rel_refuses_escapes_roots_drives_and_backslashes() {
        for raw in ["", ".", "../x", "vendor/../../x", "/etc/passwd", "C:/x", "C:x", "\\\\srv\\share\\x",
                    "vendor\\x", "vendor/./x", "vendor//x"] {
            assert!(safe_rel(raw).is_err(), "{raw:?} must be refused");
        }
    }

    #[test]
    fn stages_the_ui_plus_vendor_files_and_skips_metadata() {
        let (repo, ui, dest) = fixture();
        let sources = stage(&ui, &repo, &[vf("vendor/brand/tokens.css", "brand/tokens.css"),
                                          vf("vendor/fonts/a.ttf", "fonts/a.ttf")], &dest, H).unwrap();
        assert_eq!(listing(&dest), ["index.html", "js/main.js", "vendor/brand/tokens.css", "vendor/fonts/a.ttf"]);
        assert_eq!(fs::read_to_string(dest.join("vendor/brand/tokens.css")).unwrap(), ":root{}");
        assert_eq!(sources, [repo.join("brand/tokens.css"), repo.join("fonts/a.ttf")]);
    }

    #[test]
    fn staged_html_loses_an_agreeing_csp_meta_and_the_source_keeps_it() {
        let (repo, ui, dest) = fixture();
        let page = "<head>
<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self'; connect-src 'none'\">
</head>";
        write(&ui.join("index.html"), page);
        stage(&ui, &repo, &[], &dest, H).unwrap();
        assert_eq!(fs::read_to_string(dest.join("index.html")).unwrap(), "<head>
</head>");
        assert_eq!(fs::read_to_string(ui.join("index.html")).unwrap(), page);
    }

    #[test]
    fn staging_fails_when_the_meta_drifts_from_the_header() {
        let (repo, ui, dest) = fixture();
        write(&ui.join("index.html"),
              "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src *; connect-src 'none'\">");
        assert!(stage(&ui, &repo, &[], &dest, H).unwrap_err().contains("default-src"));
    }

    #[test]
    fn restaging_removes_stale_files() {
        let (repo, ui, dest) = fixture();
        write(&dest.join("old/left-over.js"), "x");
        stage(&ui, &repo, &[], &dest, H).unwrap();
        assert_eq!(listing(&dest), ["index.html", "js/main.js"]);
    }

    #[test]
    fn refuses_a_destination_outside_vendor() {
        let (repo, ui, dest) = fixture();
        let err = stage(&ui, &repo, &[vf("js/main.js", "brand/tokens.css")], &dest, H).unwrap_err();
        assert!(err.contains("vendor/"), "{err}");
    }

    #[test]
    fn refuses_traversal_in_either_path() {
        let (repo, ui, dest) = fixture();
        assert!(stage(&ui, &repo, &[vf("vendor/../x.css", "brand/tokens.css")], &dest, H).is_err());
        assert!(stage(&ui, &repo, &[vf("vendor/x.css", "../outside.css")], &dest, H).is_err());
    }

    #[test]
    fn refuses_a_missing_vendor_source() {
        let (repo, ui, dest) = fixture();
        let err = stage(&ui, &repo, &[vf("vendor/x.css", "brand/missing.css")], &dest, H).unwrap_err();
        assert!(err.contains("brand/missing.css"), "{err}");
    }

    #[test]
    fn refuses_a_ui_without_index_html() {
        let (repo, ui, dest) = fixture();
        fs::remove_file(ui.join("index.html")).unwrap();
        assert!(stage(&ui, &repo, &[], &dest, H).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn refuses_a_symlink_in_the_ui_tree() {
        let (repo, ui, dest) = fixture();
        std::os::unix::fs::symlink(repo.join("brand"), ui.join("js/link")).unwrap();
        let err = stage(&ui, &repo, &[], &dest, H).unwrap_err();
        assert!(err.contains("link"), "{err}");
    }

    #[cfg(windows)]
    #[test]
    fn refuses_a_symlink_in_the_ui_tree() {
        let (repo, ui, dest) = fixture();
        // Creating a symlink needs Developer Mode or a privilege on Windows; without it this case cannot be built
        // here, so the test says so and checks nothing (the unix twin runs on the macOS CI runner).
        if std::os::windows::fs::symlink_file(repo.join("brand/tokens.css"), ui.join("js/link.css")).is_err() {
            eprintln!("symlink creation not permitted on this machine; case covered on unix");
            return;
        }
        let err = stage(&ui, &repo, &[], &dest, H).unwrap_err();
        assert!(err.contains("link"), "{err}");
    }
}
