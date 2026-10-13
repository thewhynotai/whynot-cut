// WhyNot Cut host script (3.0.0). The real logic lives in the bundled libraries (jsx/wnc_*.jsx), evaluated per job by
// js/bridge.js, only from this folder.
var WNC_HOST = WNC_HOST || {};
WNC_HOST.alive = function () { return "ok " + app.version; };
