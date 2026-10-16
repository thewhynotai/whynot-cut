// Tauri isolation hook (ET1-17). Every IPC message from the UI passes through this sandboxed iframe before Tauri
// encrypts it. Defence in depth on top of the capability file: a command that is not ours is renamed to one that
// does not exist, so Rust refuses it through the normal error path (the UI's promise rejects; nothing hangs).
// Keep ALLOWED equal to capabilities/main-window.json (tests/test_scaffold.py checks both against one list).
'use strict';
(function () {
  const ALLOWED = Object.freeze(['app_info']);
  const REFUSED = '__wnc_isolation_refused__';
  window.__TAURI_ISOLATION_HOOK__ = function (payload) {
    // Tauri calls this only for objects carrying callback + error (isIsolationPayload in its isolation.js).
    if (typeof payload.cmd !== 'string' || ALLOWED.indexOf(payload.cmd) === -1) {
      payload.cmd = REFUSED;
    }
    return payload;
  };
})();
