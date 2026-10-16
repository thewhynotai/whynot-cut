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
//! The build-time rule: dropping the meta must never LOOSEN the policy. For every directive the meta sets, the header
//! must set it too and allow nothing more, except Tauri's own documented needs (TAURI_EXTRA_SOURCES; frame-src is
//! Tauri's). `'none'` in the header is always at least as strict. Directives that are not source lists (e.g.
//! `require-trusted-types-for`, `trusted-types`) must be equal. Exact equality with the UI meta is a separate test
//! (tests/test_scaffold.py), so a stricter UI change cannot break the build, but a looser header can never ship.

/// Directives Tauri owns in the app (the isolation iframe origin is added by Tauri itself).
pub const TAURI_OWNED_DIRECTIVES: &[&str] = &["frame-src"];

/// Sources the header may add beyond the meta: the IPC custom protocol (connect-src) and the hash of tauri-utils'
/// isolation IFRAME_STYLE (style-src).
pub const TAURI_EXTRA_SOURCES: &[&str] =
    &["ipc:", "http://ipc.localhost", "'sha256-YEercZJImS+vUX2bz7vkQ0aA4rtBIPLuCEWz+yraQ/g='"];

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

fn is_source_list(name: &str) -> bool {
    name.ends_with("-src") || matches!(name, "base-uri" | "form-action" | "frame-ancestors")
}

/// Check that the header is never looser than `meta` (see the module doc). Err names the directive.
pub fn check_not_looser(meta: &str, header: &str) -> Result<(), String> {
    let (m, h) = (as_map(meta, "meta")?, as_map(header, "header")?);
    for (name, meta_sources) in &m {
        if TAURI_OWNED_DIRECTIVES.contains(&name.as_str()) {
            continue;
        }
        let Some(header_sources) = h.get(name) else {
            return Err(format!("the app CSP header lacks {name}, which the UI CSP meta sets: dropping the meta would loosen it"));
        };
        let looser = if is_source_list(name) {
            let strictest = header_sources.len() == 1 && header_sources[0] == "'none'";
            !strictest
                && header_sources
                    .iter()
                    .any(|s| !meta_sources.contains(s) && !TAURI_EXTRA_SOURCES.contains(&s.as_str()))
        } else {
            header_sources != meta_sources
        };
        if looser {
            return Err(format!(
                "the app CSP header is looser than the UI CSP meta on {name}: meta {meta_sources:?}, header {header_sources:?}"
            ));
        }
    }
    Ok(())
}

/// Return `html` without its CSP meta element, after checking that `header` is not looser than it.
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
    check_not_looser(&element[c..c + close], header)?;
    let after = if html[end..].starts_with("\r\n") { 2 } else if html[end..].starts_with('\n') { 1 } else { 0 };
    Ok(format!("{}{}", &html[..start], &html[end + after..]))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// tauri.conf.json app.security.csp (ET1-17 after the ET1-07 review).
    const HEADER: &str = "default-src 'self'; script-src 'self'; \
        style-src 'self' 'sha256-YEercZJImS+vUX2bz7vkQ0aA4rtBIPLuCEWz+yraQ/g='; img-src 'self'; font-src 'self'; \
        connect-src ipc: http://ipc.localhost; object-src 'none'; base-uri 'none'; form-action 'none'; \
        frame-ancestors 'none'; require-trusted-types-for 'script'; trusted-types 'none'";
    /// The UI meta after the ET1-07 review fix.
    const META: &str = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; \
        connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; \
        require-trusted-types-for 'script'; trusted-types 'none'";
    /// The UI meta as committed in 02bca77 (looser: data: images, no form-action, no Trusted Types).
    const META_02BCA77: &str = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; \
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
    fn the_reviewed_ui_meta_is_matched_by_the_header() {
        assert_eq!(check_not_looser(META, HEADER), Ok(()));
    }

    #[test]
    fn a_looser_earlier_meta_is_fine_because_the_header_is_stricter() {
        assert_eq!(check_not_looser(META_02BCA77, HEADER), Ok(()));
    }

    #[test]
    fn a_header_missing_a_meta_directive_is_refused() {
        let h = HEADER.replace(" form-action 'none';", "");
        assert!(check_not_looser(META, &h).unwrap_err().contains("form-action"));
        let h = HEADER.replace("; trusted-types 'none'", "");
        assert!(check_not_looser(META, &h).unwrap_err().contains("trusted-types"));
    }

    #[test]
    fn a_header_allowing_more_than_the_meta_is_refused() {
        let h = HEADER.replace("img-src 'self'", "img-src 'self' data:");
        assert!(check_not_looser(META, &h).unwrap_err().contains("img-src"));
        let h = HEADER.replace("connect-src ipc:", "connect-src https://example.com ipc:");
        assert!(check_not_looser(META, &h).unwrap_err().contains("connect-src"));
        let h = HEADER.replace("object-src 'none'", "object-src 'self'");
        assert!(check_not_looser(META, &h).unwrap_err().contains("object-src"));
    }

    #[test]
    fn only_tauris_own_hash_may_be_added_to_style_src() {
        let h = HEADER.replace("YEercZJImS+vUX2bz7vkQ0aA4rtBIPLuCEWz+yraQ/g=", "AAAA");
        assert!(check_not_looser(META, &h).unwrap_err().contains("style-src"));
    }

    #[test]
    fn none_in_the_header_is_always_strict_enough() {
        let h = HEADER.replace("font-src 'self'", "font-src 'none'");
        assert_eq!(check_not_looser(META, &h), Ok(()));
    }

    #[test]
    fn non_source_directives_must_be_equal() {
        let h = HEADER.replace("trusted-types 'none'", "trusted-types tauri");
        assert!(check_not_looser(META, &h).unwrap_err().contains("trusted-types"));
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
    fn a_meta_stricter_than_the_header_fails_instead_of_being_dropped() {
        let strict = META.replace("font-src 'self'", "font-src 'none'");
        assert!(strip_meta(&page(&strict), HEADER).unwrap_err().contains("font-src"));
    }

    #[test]
    fn two_metas_are_refused() {
        let twice = page(META).replace("<title>", &format!(
            "<meta http-equiv=\"Content-Security-Policy\" content=\"{META}\">\n<title>"));
        assert!(strip_meta(&twice, HEADER).is_err());
    }
}
