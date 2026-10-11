/*  whynot-cut — After Effects motion library (ExtendScript, ES3).
    Renders a compiled motion-plan.json (frames and pixels decided by the engine) as a native AE project: one comp per
    scene, persistent layers and audio in MAIN_<reel id>, brand colours linked to BRAND_CONTROLS. Loaded after
    nh_ae_lib.jsx (helpers NH.*) by nh_ae_bridge.jsx, or embedded in a fallback script. Never writes files except
    app.project.save().
*/
var NHM = NHM || {};
