// Tauri isolation hook (ET1-17). Tauri's isolation pattern requires this function; ours forwards every message
// unchanged.
// It is not a security boundary: page script can skip it (raw __TAURI_INTERNALS__.postMessage, or the isolation
// frame used as an encryption oracle; review I1), so nothing here may filter or validate. The boundary is the ACL
// (capabilities/main-window.json) plus argument validation inside every Rust command (src/lib.rs, "the rule").
'use strict';
window.__TAURI_ISOLATION_HOOK__ = function (payload) {
  return payload;
};
