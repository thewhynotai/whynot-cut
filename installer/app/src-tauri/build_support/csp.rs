//! The UI's CSP `<meta>` versus the app's CSP header (`app.security.csp`). Shared by build.rs (via stage.rs) and the
//! lib's unit tests; std only.
//!
//! Why the staged copy drops the meta (proven live in WebView2, task-ET1-17-report.md): Tauri's isolation pattern
//! injects an iframe whose origin is random per build (`http://isolation-<uuid>.localhost` on Windows, the scheme
//! `isolation-<uuid>:` on macOS) plus one `<style>` to hide it. Tauri adds both to the HEADER it sends, but a static
//! meta cannot name them, and a second (meta) policy intersects with the header: the iframe is blocked, every IPC call
//! hangs, and the iframe shows as a box. So in the app the header is the one policy (it also carries
//! `frame-ancestors`, which a meta cannot), and the meta stays in `ui/` for the file:// UI tests.
//!
//! The meta may be dropped only when it AGREES with the header: every directive equal, except the header's
//! documented Tauri needs (connect-src for the IPC origins, frame-src, and the isolation style hash). A meta that
//! drifts fails the build.

/// Directives where the header may differ from the meta (Tauri's own IPC/isolation needs).
pub const TAURI_OWNED_DIRECTIVES: &[&str] = &["connect-src", "frame-src"];

/// Sources the header may add to other directives (the hash of tauri-utils' isolation IFRAME_STYLE).
pub const TAURI_EXTRA_SOURCES: &[&str] = &["'sha256-YEercZJImS+vUX2bz7vkQ0aA4rtBIPLuCEWz+yraQ/g='"];

/// Parse a policy into (directive, sources) pairs in order. Names are lower-cased; sources keep their case.
pub fn directives(policy: &str) -> Vec<(String, Vec<String>)> {
    policy
        .split(';')
        .filter_map(|d| {
            let mut words = d.split_whitespace();
            let name = words.next()?.to_ascii_lowercase();
            Some((name, words.map(str::to_owned).collect()))
        })
        .collect()
}

fn as_map(policy: &str, which: &str) -> Result<std::collections::BTreeMap<String, Vec<String>>, String> {
    let mut map = std::collections::BTreeMap::new();
    for (name, sources) in directives(policy) {
        if map.insert(name.clone(), sources).is_some() {
            return Err(format!("the {which} CSP names {name} twice"));
        }
    }
    Ok(map)
}

/// Check that `meta` agrees with `header` (see the module doc). Err names the first directive that differs.
pub fn check_agrees(meta: &str, header: &str) -> Result<(), String> {
    let (m, h) = (as_map(meta, "meta")?, as_map(header, "header")?);
    let names: std::collections::BTreeSet<&String> = m.keys().chain(h.keys()).collect();
    for name in names {
        if TAURI_OWNED_DIRECTIVES.contains(&name.as_str()) {
            continue;
        }
        let hv: Option<Vec<&String>> =
            h.get(name).map(|v| v.iter().filter(|s| !TAURI_EXTRA_SOURCES.contains(&s.as_str())).collect());
        let mv: Option<Vec<&String>> = m.get(name).map(|v| v.iter().collect());
        if hv != mv {
            return Err(format!("the UI CSP meta and the app CSP header differ on {name}: meta {mv:?}, header {hv:?}"));
        }
    }
    Ok(())
}

/// Return `html` without its CSP meta element, after checking that it agrees with `header`.
/// No meta: returned unchanged. More than one: an error (ambiguous).
pub fn strip_meta(html: &str, header: &str) -> Result<String, String> {
    const KEY: &str = "http-equiv=\"content-security-policy\"";
    let lower = html.to_ascii_lowercase(); // ASCII lower-casing keeps every byte offset
    let hits: Vec<usize> = lower.match_indices(KEY).map(|(i, _)| i).collect();
    match hits.len() {
        0 => return Ok(html.to_owned()),
        1 => {}
        n => return Err(format!("{n} CSP meta elements in one page")),
    }
    let at = hits[0];
    let start = lower[..at].rfind("<meta").ok_or("a CSP http-equiv outside a <meta> element")?;
    let end = at + lower[at..].find('>').ok_or("an unterminated CSP <meta> element")? + 1;
    let element = &html[start..end];
    let c = element.to_ascii_lowercase().find("content=\"").ok_or("a CSP <meta> without content=\"...\"")? + 9;
    let close = element[c..].find('"').ok_or("an unterminated CSP content attribute")?;
    check_agrees(&element[c..c + close], header)?;
    let after = if html[end..].starts_with("\r\n") { 2 } else if html[end..].starts_with('\n') { 1 } else { 0 };
    Ok(format!("{}{}", &html[..start], &html[end + after..]))
}

#[cfg(test)]
mod tests {
    use super::*;

    const HEADER: &str = "default-src 'self'; script-src 'self'; \
        style-src 'self' 'sha256-YEercZJImS+vUX2bz7vkQ0aA4rtBIPLuCEWz+yraQ/g='; img-src 'self' data:; \
        font-src 'self'; connect-src ipc: http://ipc.localhost; object-src 'none'; base-uri 'none'; \
        frame-ancestors 'none'";
    const META: &str = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; \
        font-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'";

    fn page(meta: &str) -> String {
        format!(
            "<!doctype html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n\
             <meta http-equiv=\"Content-Security-Policy\" content=\"{meta}\">\n\
             <title>t</title>\n</head>\n<body></body>\n</html>\n"
        )
    }

    #[test]
    fn parses_directives_in_order() {
        let d = directives(" Default-Src 'self' ;img-src 'self'  data: ;; ");
        assert_eq!(
            d,
            vec![
                ("default-src".to_string(), vec!["'self'".to_string()]),
                ("img-src".to_string(), vec!["'self'".to_string(), "data:".to_string()]),
            ]
        );
    }

    #[test]
    fn the_ui_meta_agrees_with_the_header() {
        assert_eq!(check_agrees(META, HEADER), Ok(()));
    }

    #[test]
    fn a_looser_meta_is_refused() {
        let loose = META.replace("script-src 'self'", "script-src 'self' 'unsafe-inline'");
        assert!(check_agrees(&loose, HEADER).unwrap_err().contains("script-src"));
    }

    #[test]
    fn a_stricter_or_missing_directive_is_refused() {
        let no_img = META.replace("img-src 'self' data:; ", "");
        assert!(check_agrees(&no_img, HEADER).unwrap_err().contains("img-src"));
        let extra = format!("{META}; worker-src 'none'");
        assert!(check_agrees(&extra, HEADER).unwrap_err().contains("worker-src"));
    }

    #[test]
    fn the_header_may_add_only_the_isolation_hash_to_other_directives() {
        let other_hash = HEADER.replace("YEercZJImS+vUX2bz7vkQ0aA4rtBIPLuCEWz+yraQ/g=", "AAAA");
        assert!(check_agrees(META, &other_hash).unwrap_err().contains("style-src"));
    }

    #[test]
    fn strips_exactly_the_csp_meta() {
        let out = strip_meta(&page(META), HEADER).unwrap();
        assert!(!out.contains("Content-Security-Policy"));
        assert_eq!(out, page(META).replace(&format!(
            "<meta http-equiv=\"Content-Security-Policy\" content=\"{META}\">\n"), ""));
        assert!(out.contains("<meta charset=\"utf-8\">"));
    }

    #[test]
    fn a_page_without_meta_is_unchanged() {
        let html = "<!doctype html><title>x</title>";
        assert_eq!(strip_meta(html, HEADER).unwrap(), html);
    }

    #[test]
    fn a_drifting_meta_fails_instead_of_being_dropped() {
        let loose = META.replace("object-src 'none'", "object-src *");
        assert!(strip_meta(&page(&loose), HEADER).is_err());
    }

    #[test]
    fn two_metas_are_refused() {
        let twice = page(META).replace("<title>", &format!(
            "<meta http-equiv=\"Content-Security-Policy\" content=\"{META}\">\n<title>"));
        assert!(strip_meta(&twice, HEADER).is_err());
    }
}
