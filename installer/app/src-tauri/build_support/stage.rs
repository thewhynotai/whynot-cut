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

/// `ui/stage.json` (owned by the UI track): `files` = exactly what ships (ui/-relative), `dev_only` = never shipped.
/// Every file under ui/ (except the metadata in SKIP_TOP) must be in one of the two.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct StageList {
    pub files: Vec<String>,
    pub dev_only: Vec<String>,
}

/// One `files[]` entry of `ui/vendor.json`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VendorFile {
    pub to: String,
    pub from: String,
}

/// Names in the top level of `ui/` that are never shipped: build metadata and a stray local vendor copy.
pub const SKIP_TOP: &[&str] = &["vendor.json", "stage.json", "vendor"];

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

/// The quoted string right after `at` (skipping spaces and one optional `(`), if any.
/// A call form `("x")` counts only when the literal is the whole argument; `import("a/" + name)` is computed at run
/// time and cannot be checked here.
fn quoted_after(text: &str, at: usize) -> Option<String> {
    let rest = text[at..].trim_start();
    let (rest, call) = match rest.strip_prefix('(') {
        Some(r) => (r.trim_start(), true),
        None => (rest, false),
    };
    let quote = rest.chars().next().filter(|c| *c == '"' || *c == '\'')?;
    let body = &rest[1..];
    let end = body.find(quote)?;
    if call && !body[end + 1..].trim_start().starts_with(')') {
        return None;
    }
    Some(body[..end].to_owned())
}

fn is_ident(c: char) -> bool {
    c.is_ascii_alphanumeric() || c == '_' || c == '$'
}

/// Module specifiers a JS file loads, with `true` for a dynamic `import("x")`: `import "x"`, `import ... from "x"`,
/// `export ... from "x"`, `import("x")`.
pub fn js_imports(text: &str) -> Vec<(String, bool)> {
    let mut out = Vec::new();
    for kw in ["import", "from"] {
        for (i, _) in text.match_indices(kw) {
            let before = text[..i].chars().next_back();
            let after = text[i + kw.len()..].chars().next();
            if before.is_some_and(is_ident) || after.is_some_and(is_ident) {
                continue;
            }
            if let Some(s) = quoted_after(text, i + kw.len()) {
                let dynamic = kw == "import" && text[i + kw.len()..].trim_start().starts_with('(');
                out.push((s, dynamic));
            }
        }
    }
    out
}

/// The specifiers of `js_imports`, static and dynamic alike (tests).
#[cfg(test)]
pub fn js_specifiers(text: &str) -> Vec<String> {
    js_imports(text).into_iter().map(|(s, _)| s).collect()
}

/// `src` / `href` values in an HTML page.
pub fn html_references(text: &str) -> Vec<String> {
    let mut out = Vec::new();
    for attr in [" src=", " href="] {
        for (i, _) in text.match_indices(attr) {
            if let Some(s) = quoted_after(text, i + attr.len()) {
                out.push(s);
            }
        }
    }
    out
}

/// Resolve a local reference against the folder of the file that makes it (relative to dest).
/// None = not a local file reference (another scheme, a bare module name, an in-page anchor).
fn resolve_local(from_dir: &str, spec: &str, js: bool) -> Option<Result<String, String>> {
    let spec = spec.split(['?', '#']).next().unwrap_or("");
    if spec.is_empty() || spec.contains(':') || spec.starts_with("//") {
        return None;
    }
    if js && !(spec.starts_with("./") || spec.starts_with("../") || spec.starts_with('/')) {
        return None; // a bare specifier: no import map in this bundle, so the browser would refuse it anyway
    }
    let mut parts: Vec<&str> = if spec.starts_with('/') { Vec::new() } else {
        from_dir.split('/').filter(|p| !p.is_empty()).collect()
    };
    for seg in spec.split('/') {
        match seg {
            "" | "." => {}
            ".." => {
                if parts.pop().is_none() {
                    return Some(Err(format!("{spec:?} climbs out of the bundle")));
                }
            }
            s => parts.push(s),
        }
    }
    Some(Ok(parts.join("/")))
}

fn under(path: &str, entries: &[String]) -> bool {
    entries.iter().any(|x| path == x || path.starts_with(&format!("{x}/")))
}

/// Files under `root` as `/`-joined relative paths, skipping SKIP_TOP at the top; a link anywhere is an error.
fn list_files(root: &Path) -> Result<Vec<String>, String> {
    fn walk(root: &Path, d: &Path, rel: &str, out: &mut Vec<String>) -> Result<(), String> {
        let mut entries: Vec<_> = fs::read_dir(d)
            .map_err(|e| format!("{}: {e}", d.display()))?
            .collect::<Result<_, _>>()
            .map_err(|e| format!("{}: {e}", d.display()))?;
        entries.sort_by_key(|e| e.file_name());
        for e in entries {
            let name = e.file_name();
            if rel.is_empty() && SKIP_TOP.iter().any(|s| name == *s) {
                continue;
            }
            let p = e.path();
            if is_link(&p)? {
                return Err(format!("refusing a link in the UI tree: {}", p.display()));
            }
            let child = format!("{rel}{}", name.to_string_lossy());
            if p.is_dir() {
                walk(root, &p, &format!("{child}/"), out)?;
            } else {
                out.push(child);
            }
        }
        Ok(())
    }
    let mut out = Vec::new();
    walk(root, root, "", &mut out)?;
    Ok(out)
}

/// Every local `src`/`href` of a staged page and every relative import of a staged module must name a staged file.
/// One exception: a literal dynamic `import("x")` of a `dev_only` file (the demo body, loaded only for `?demo=`).
fn check_references(dest: &Path, dev_only: &[String]) -> Result<(), String> {
    for f in list_files(dest)? {
        let (js, html) = (f.ends_with(".js") || f.ends_with(".mjs"), f.ends_with(".html"));
        if !js && !html {
            continue;
        }
        let text = fs::read_to_string(dest.join(&f)).map_err(|e| format!("{f}: {e}"))?;
        let refs = if js { js_imports(&text) } else { html_references(&text).into_iter().map(|s| (s, false)).collect() };
        let dir = f.rsplit_once('/').map(|(d, _)| d).unwrap_or("");
        for (spec, dynamic) in refs {
            match resolve_local(dir, &spec, js) {
                None => {}
                Some(Err(e)) => return Err(format!("{f}: {e}")),
                Some(Ok(target)) => {
                    if dynamic && under(&target, dev_only) {
                        continue;
                    }
                    if !dest.join(&target).is_file() {
                        return Err(format!("{f} refers to {spec:?} ({target}), which is not in the staged bundle"));
                    }
                }
            }
        }
    }
    Ok(())
}

fn copy_file(from: &Path, to: &Path, header_csp: &str) -> Result<(), String> {
    fs::create_dir_all(to.parent().expect("a file has a parent")).map_err(|e| format!("{}: {e}", to.display()))?;
    if from.extension().is_some_and(|e| e.eq_ignore_ascii_case("html")) {
        let html = fs::read_to_string(from).map_err(|e| format!("{}: {e}", from.display()))?;
        let html = csp::strip_meta(&html, header_csp).map_err(|e| format!("{}: {e}", from.display()))?;
        fs::write(to, html).map_err(|e| format!("{}: {e}", to.display()))
    } else {
        fs::copy(from, to).map(|_| ()).map_err(|e| format!("{} -> {}: {e}", from.display(), to.display()))
    }
}

/// Validate `ui/stage.json` against the ui/ tree; returns the files to ship.
fn check_list(ui: &Path, list: &StageList) -> Result<Vec<String>, String> {
    for x in list.files.iter().chain(&list.dev_only) {
        safe_rel(x)?;
    }
    if let Some(x) = list.files.iter().find(|f| under(f, &list.dev_only)) {
        return Err(format!("ui/stage.json lists {x:?} in both files and dev_only"));
    }
    if !list.files.iter().any(|f| f == "index.html") {
        return Err("ui/stage.json files must include index.html".into());
    }
    for f in &list.files {
        let p = ui.join(safe_rel(f)?);
        if !p.is_file() || is_link(&p)? {
            return Err(format!("ui/stage.json ships {f:?}, which is missing or not a regular file"));
        }
    }
    for x in &list.dev_only {
        if fs::symlink_metadata(ui.join(safe_rel(x)?)).is_err() {
            return Err(format!("ui/stage.json dev_only names {x:?}, which is not in ui/ (stale list?)"));
        }
    }
    for f in list_files(ui)? {
        if !list.files.contains(&f) && !under(&f, &list.dev_only) {
            return Err(format!("ui/{f} is in neither files nor dev_only of ui/stage.json"));
        }
    }
    Ok(list.files.clone())
}

/// Replace `dest` with the UI bundle plus the vendor files. With a stage list (`ui/stage.json`), exactly its `files`
/// ship; without one (a dev tree before the UI track adds it), all of ui/ minus SKIP_TOP. Every staged `.html` loses
/// its CSP meta after csp::strip_meta checks the header is not looser than it, and every local reference in the staged
/// pages and modules must resolve inside the bundle. Returns the vendor sources (absolute) so build.rs can emit
/// `rerun-if-changed` for each.
pub fn stage(ui: &Path, repo: &Path, vendor: &[VendorFile], list: Option<&StageList>, dest: &Path, header_csp: &str)
    -> Result<Vec<PathBuf>, String> {
    if !ui.join("index.html").is_file() {
        return Err(format!("the UI bundle has no index.html: {}", ui.display()));
    }
    // Validate everything before touching dest.
    let ship = match list {
        Some(l) => check_list(ui, l)?,
        None => list_files(ui)?,
    };
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
    fs::create_dir_all(dest).map_err(|e| format!("{}: {e}", dest.display()))?;
    for f in &ship {
        let rel = safe_rel(f)?;
        copy_file(&ui.join(&rel), &dest.join(&rel), header_csp)?;
    }
    let mut sources = Vec::with_capacity(plan.len());
    for (from, to) in plan {
        copy_file(&from, &dest.join(&to), header_csp)?;
        sources.push(from);
    }
    check_references(dest, list.map(|l| l.dev_only.as_slice()).unwrap_or(&[]))?;
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

    fn sl(files: &[&str], dev_only: &[&str]) -> StageList {
        StageList {
            files: files.iter().map(|p| p.to_string()).collect(),
            dev_only: dev_only.iter().map(|p| p.to_string()).collect(),
        }
    }

    #[test]
    fn a_stage_list_ships_exactly_its_files_plus_vendor() {
        let (repo, ui, dest) = fixture();
        write(&ui.join("js/demo.js"), "export const demo = 1;");
        write(&ui.join("stage.json"), "{}");
        let list = sl(&["index.html", "js/main.js"], &["js/demo.js"]);
        stage(&ui, &repo, &[vf("vendor/brand/tokens.css", "brand/tokens.css")], Some(&list), &dest, H).unwrap();
        assert_eq!(listing(&dest), ["index.html", "js/main.js", "vendor/brand/tokens.css"]);
    }

    #[test]
    fn a_ui_file_in_neither_list_is_refused() {
        let (repo, ui, dest) = fixture();
        write(&ui.join("js/new.js"), "export {};");
        let err = stage(&ui, &repo, &[], Some(&sl(&["index.html", "js/main.js"], &[])), &dest, H).unwrap_err();
        assert!(err.contains("js/new.js"), "{err}");
    }

    #[test]
    fn a_listed_file_that_is_missing_is_refused() {
        let (repo, ui, dest) = fixture();
        let err = stage(&ui, &repo, &[], Some(&sl(&["index.html", "js/main.js", "js/gone.js"], &[])), &dest, H)
            .unwrap_err();
        assert!(err.contains("js/gone.js"), "{err}");
    }

    #[test]
    fn a_file_in_both_lists_or_an_unsafe_path_is_refused() {
        let (repo, ui, dest) = fixture();
        assert!(stage(&ui, &repo, &[], Some(&sl(&["index.html", "js/main.js"], &["js/main.js"])), &dest, H)
            .unwrap_err()
            .contains("js/main.js"));
        assert!(stage(&ui, &repo, &[], Some(&sl(&["index.html", "../ui/js/main.js"], &[])), &dest, H).is_err());
    }

    #[test]
    fn a_static_import_of_a_dev_only_module_is_refused() {
        let (repo, ui, dest) = fixture();
        write(&ui.join("js/demo.js"), "export const demo = 1;");
        write(&ui.join("js/main.js"), "import { demo } from \"./demo.js\";\nexport {};\n");
        let err = stage(&ui, &repo, &[], Some(&sl(&["index.html", "js/main.js"], &["js/demo.js"])), &dest, H)
            .unwrap_err();
        assert!(err.contains("demo.js"), "{err}");
    }

    #[test]
    fn a_dynamic_import_of_a_dev_only_module_is_allowed_but_not_of_a_missing_one() {
        let (repo, ui, dest) = fixture();
        write(&ui.join("js/demo.js"), "export const demo = 1;");
        write(&ui.join("js/main.js"), "if (q) { const d = await import(\"./demo.js\"); }\nexport {};\n");
        let list = sl(&["index.html", "js/main.js"], &["js/demo.js"]);
        stage(&ui, &repo, &[], Some(&list), &dest, H).unwrap();
        write(&ui.join("js/main.js"), "const d = await import(\"./gone.js\");\nexport {};\n");
        assert!(stage(&ui, &repo, &[], Some(&list), &dest, H).unwrap_err().contains("gone.js"));
    }

    #[test]
    fn a_stage_list_still_drops_the_csp_meta() {
        let (repo, ui, dest) = fixture();
        write(&ui.join("index.html"),
              "<head>\n<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self'; connect-src 'none'\">\n</head>");
        stage(&ui, &repo, &[], Some(&sl(&["index.html", "js/main.js"], &[])), &dest, H).unwrap();
        assert_eq!(fs::read_to_string(dest.join("index.html")).unwrap(), "<head>\n</head>");
    }

    #[test]
    fn a_computed_dynamic_import_is_not_checked_statically() {
        // demo.js: import("../fixtures/" + name + ".js") exists only in a test staging; not a literal specifier.
        assert_eq!(js_specifiers("const m = await import(\"../fixtures/\" + name + \".js\");"), Vec::<String>::new());
        assert_eq!(js_specifiers("const m = import( './b.js' );"), ["./b.js"]);
    }

    #[test]
    fn a_page_referring_to_a_missing_file_is_refused() {
        let (repo, ui, dest) = fixture();
        write(&ui.join("index.html"), "<script src=\"js/gone.js\"></script><link rel=\"stylesheet\" href=\"css/a.css\">");
        let err = stage(&ui, &repo, &[], None, &dest, H).unwrap_err();
        assert!(err.contains("js/gone.js"), "{err}");
    }

    #[test]
    fn local_references_resolve_including_vendor_files() {
        let (repo, ui, dest) = fixture();
        write(&ui.join("index.html"),
              "<link rel=\"stylesheet\" href=\"vendor/brand/tokens.css\"><script type=\"module\" src=\"js/main.js\"></script>");
        write(&ui.join("js/main.js"), "import \"./b.js\";\nexport * from './b.js';\nconst m = import(\"./b.js\");\n");
        write(&ui.join("js/b.js"), "export {};");
        stage(&ui, &repo, &[vf("vendor/brand/tokens.css", "brand/tokens.css")], None, &dest, H).unwrap();
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
                                          vf("vendor/fonts/a.ttf", "fonts/a.ttf")], None, &dest, H).unwrap();
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
        stage(&ui, &repo, &[], None, &dest, H).unwrap();
        assert_eq!(fs::read_to_string(dest.join("index.html")).unwrap(), "<head>
</head>");
        assert_eq!(fs::read_to_string(ui.join("index.html")).unwrap(), page);
    }

    #[test]
    fn staging_fails_when_the_header_would_be_looser_than_the_meta() {
        let (repo, ui, dest) = fixture();
        write(&ui.join("index.html"),
              "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; connect-src 'none'\">");
        assert!(stage(&ui, &repo, &[], None, &dest, H).unwrap_err().contains("default-src"));
    }

    #[test]
    fn restaging_removes_stale_files() {
        let (repo, ui, dest) = fixture();
        write(&dest.join("old/left-over.js"), "x");
        stage(&ui, &repo, &[], None, &dest, H).unwrap();
        assert_eq!(listing(&dest), ["index.html", "js/main.js"]);
    }

    #[test]
    fn refuses_a_destination_outside_vendor() {
        let (repo, ui, dest) = fixture();
        let err = stage(&ui, &repo, &[vf("js/main.js", "brand/tokens.css")], None, &dest, H).unwrap_err();
        assert!(err.contains("vendor/"), "{err}");
    }

    #[test]
    fn refuses_traversal_in_either_path() {
        let (repo, ui, dest) = fixture();
        assert!(stage(&ui, &repo, &[vf("vendor/../x.css", "brand/tokens.css")], None, &dest, H).is_err());
        assert!(stage(&ui, &repo, &[vf("vendor/x.css", "../outside.css")], None, &dest, H).is_err());
    }

    #[test]
    fn refuses_a_missing_vendor_source() {
        let (repo, ui, dest) = fixture();
        let err = stage(&ui, &repo, &[vf("vendor/x.css", "brand/missing.css")], None, &dest, H).unwrap_err();
        assert!(err.contains("brand/missing.css"), "{err}");
    }

    #[test]
    fn refuses_a_ui_without_index_html() {
        let (repo, ui, dest) = fixture();
        fs::remove_file(ui.join("index.html")).unwrap();
        assert!(stage(&ui, &repo, &[], None, &dest, H).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn refuses_a_symlink_in_the_ui_tree() {
        let (repo, ui, dest) = fixture();
        std::os::unix::fs::symlink(repo.join("brand"), ui.join("js/link")).unwrap();
        let err = stage(&ui, &repo, &[], None, &dest, H).unwrap_err();
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
        let err = stage(&ui, &repo, &[], None, &dest, H).unwrap_err();
        assert!(err.contains("link"), "{err}");
    }
}
