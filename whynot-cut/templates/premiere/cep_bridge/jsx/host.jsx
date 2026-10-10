// Minimal host script. Real logic lives in the skill (templates/premiere/nh_ppro_lib.jsx) and is
// loaded per job by the bridge, only from that whitelisted folder.
function nhBridgeAlive() { return "ok " + app.version; }
