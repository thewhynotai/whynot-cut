//! D-04 build flag `WNC_BUILD_SIGNED`, shared by build.rs (which enforces it) and the lib's unit tests.
//!
//! 3.0 builds are unsigned "internal" builds (Addendum F; signing is phase 2). The flag therefore accepts only
//! "unset" or `false`. `true` is refused at build time, so no 3.0 binary can ever say it is signed. Phase 2 lifts
//! this together with a real signature check in tools/release.py.

/// The environment variable read at build time.
pub const ENV: &str = "WNC_BUILD_SIGNED";

/// Resolve the raw value of `WNC_BUILD_SIGNED` (None = unset). Ok(false) is the only accepted outcome in 3.0.
pub fn resolve_signed(raw: Option<&str>) -> Result<bool, String> {
    match raw {
        None | Some("false") => Ok(false),
        Some("true") => Err(format!(
            "{ENV}=true is refused: 3.0 builds are unsigned internal builds (D-04); signing is phase 2"
        )),
        Some(other) => Err(format!("{ENV} must be unset or \"false\", got {other:?}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unset_means_unsigned() {
        assert_eq!(resolve_signed(None), Ok(false));
    }

    #[test]
    fn explicit_false_means_unsigned() {
        assert_eq!(resolve_signed(Some("false")), Ok(false));
    }

    #[test]
    fn true_is_refused_in_3_0() {
        let err = resolve_signed(Some("true")).unwrap_err();
        assert!(err.contains("phase 2"), "{err}");
    }

    #[test]
    fn anything_else_is_refused_not_guessed() {
        for raw in ["", "TRUE", "False", "1", "0", "yes", " false", "false "] {
            assert!(resolve_signed(Some(raw)).is_err(), "{raw:?} must be refused");
        }
    }
}
