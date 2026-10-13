# Frozen CEP bridge 3.1.1 (the legacy family)

The bridge installed on the owner's PC before 3.0 (`%APPDATA%\Adobe\CEP\extensions\ai.thewhynot.cut.bridge`,
ExtensionBundleVersion 3.1.1). Copied byte for byte from `adobe/cep-bridge/` at the commit before T6.3 Task 4
(`git show HEAD:adobe/cep-bridge/js/bridge.js`, `git show HEAD:adobe/cep-bridge/CSXS/manifest.xml`), when Task 4
rewrote that shell as bundle 3.0.0.

During 3.0 the engine still drives this bridge (design decision 3, "legacy, exactly 3.1.1"): its heartbeat has no
`protocol`, the engine syncs the libraries into `<engine home>/{ppro,ae}-scripts` and sends `script:`, and the libraries
end with the aliases `var NHPP = WNCPP;` / `var NHAE = WNCAE;`. `tests/test_bridge_queue.py` (`TestBridgeJsLegacy311`)
runs the engine against this file in node. Never edit these files; the family is removed in 3.1.

| file | sha256 |
|---|---|
| `bridge.js` (`js/bridge.js`) | `7506b0701341d0ac68c845e74849a3ab741fd822d3b1a570be449f7b456d58d9` |
| `manifest.xml` (`CSXS/manifest.xml`) | `1035a42c41a82bc81233506a1b6a4dbc9ea2c0fa7e6fd81db873007348290824` |
