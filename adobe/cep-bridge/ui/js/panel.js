/* WhyNot Cut panel (After Effects; 3.0.0, minimal until the designed panel of Addendum E): one sentence about the
   hidden daemon, read from its heartbeat through window.WNC_BRIDGE (js/bridge.js, panel role), and Copy diagnostics.
   Status only: the panel never works the queue, never starts the engine and shows no commands. The states:
     running    the daemon beats                          "WhyNot Cut is running in After Effects."
     busy       the daemon beats with a job               "WhyNot Cut is working in After Effects."
     starting   the panel just loaded, or the daemon is   "Starting WhyNot Cut…"
                starting the engine (engine_start "spawned")
     not loaded no fresh beat after the grace period      "WhyNot Cut isn't running in After Effects: restart After
                                                           Effects" */
(function () {
  var el = document.getElementById('state'), btn = document.getElementById('copy');
  var APP = { AEFT: 'After Effects', PPRO: 'Premiere Pro' };
  var START_GRACE_MS = 10000;          // the daemon loads with the app; give it this long before saying it is not there
  var COPY_LABEL = 'Copy diagnostics';
  function appName(b) { return (b && APP[b.host]) || 'After Effects'; }
  function freshBeat(b) {
    var hb = b ? b.readBeat() : null;
    return hb && hb.role === 'daemon' && Date.now() - hb.at < b.staleMs ? hb : null;
  }
  function sentence() {
    var b = window.WNC_BRIDGE, app = appName(b), hb = freshBeat(b);
    if (hb) {
      if (hb.busy) { return 'WhyNot Cut is working in ' + app + '.'; }
      if (hb.engine_start && hb.engine_start.outcome === 'spawned') { return 'Starting WhyNot Cut…'; }
      return 'WhyNot Cut is running in ' + app + '.';
    }
    if (b && Date.now() - b.loadedAt < START_GRACE_MS) { return 'Starting WhyNot Cut…'; }
    return 'WhyNot Cut isn’t running in ' + app + ': restart ' + app;
  }
  function render() {
    try { el.textContent = sentence(); } catch (e) { el.textContent = 'WhyNot Cut isn’t running: restart the app'; }
  }
  // what support needs, as JSON: the bundle, the host, the daemon's last heartbeat (it holds no secret)
  function diagnostics() {
    var b = window.WNC_BRIDGE || {}, hb = null;
    try { hb = b.readBeat ? b.readBeat() : null; } catch (e) {}
    return JSON.stringify({ product: 'WhyNot Cut', bundle: b.bundle || null, build: b.build || null,
                            host: b.host || null, hostVersion: b.hostVersion || null, panel_loaded_at: b.loadedAt || null,
                            now: Date.now(), state: el.textContent, queue: b.queue || null, heartbeat: hb }, null, 1);
  }
  // CEP's Chromium may refuse the async clipboard: then a hidden textarea and execCommand('copy')
  function copyByTextarea(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { return document.execCommand('copy'); } catch (e) { return false; } finally { document.body.removeChild(ta); }
  }
  function flash(label) {
    btn.textContent = label;
    setTimeout(function () { btn.textContent = COPY_LABEL; }, 2000);
  }
  function copyDiagnostics() {
    var text = diagnostics();
    var fallback = function () { flash(copyByTextarea(text) ? 'Copied' : 'Could not copy'); };
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text).then(function () { flash('Copied'); }, fallback);
      }
    } catch (e) {}
    fallback();
  }
  if (btn) { btn.addEventListener('click', copyDiagnostics); }
  render();
  setInterval(render, 1000);
})();
