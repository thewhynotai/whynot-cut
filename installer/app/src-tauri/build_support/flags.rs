//! D-04 build flag `WNC_BUILD_SIGNED`, shared by build.rs (which enforces it) and the lib's unit tests.
//!
//! 3.0 builds are unsigned "internal" builds (Addendum F; signing is phase 2). In 3.0 the app's answer is a literal
//! `false` (src/lib.rs `BUILD_SIGNED`), and both ways to claim otherwise fail the build:
//! - the environment variable `WNC_BUILD_SIGNED` set to ANY value (even `false`, or bytes that are not UTF-8): this
//!   module, called from build.rs;
//! - `--cfg wnc_build_signed` (RUSTFLAGS or a `.cargo/config.toml`): a `compile_error!` in src/lib.rs.
//!
//! Phase 2 replaces both with a real signature check in tools/release.py.

use std::ffi::OsStr;

/// The environment variable read at build time.
pub const ENV: &str = "WNC_BUILD_SIGNED";

/// Resolve `WNC_BUILD_SIGNED` (None = unset). In 3.0 only "unset" is accepted, and it means unsigned.
pub fn resolve_signed(raw: Option<&OsStr>) -> Result<bool, String> {
    match raw {
        None => Ok(false),
        Some(v) => Err(format!(
            "{ENV} is set ({v:?}): 3.0 builds are always unsigned internal builds (D-04); unset it. Signing is \
             phase 2"
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::OsString;

    #[test]
    fn unset_means_unsigned() {
        assert_eq!(resolve_signed(None), Ok(false));
    }

    #[test]
    fn any_value_is_refused_in_3_0_even_false() {
        for raw in ["true", "false", "", "TRUE", "1", "0", "yes"] {
            let err = resolve_signed(Some(OsStr::new(raw))).unwrap_err();
            assert!(err.contains("phase 2") && err.contains(ENV), "{raw:?}: {err}");
        }
    }

    #[test]
    fn a_value_that_is_not_utf8_is_refused_not_treated_as_unset() {
        #[cfg(windows)]
        let raw = {
            use std::os::windows::ffi::OsStringExt;
            OsString::from_wide(&[0xD800]) // a lone surrogate: not valid UTF-16, so not UTF-8 either
        };
        #[cfg(unix)]
        let raw = {
            use std::os::unix::ffi::OsStringExt;
            OsString::from_vec(vec![0xff, 0xfe])
        };
        assert!(raw.to_str().is_none());
        assert!(resolve_signed(Some(&raw)).is_err());
    }
}
