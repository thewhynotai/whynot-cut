/* WhyNot Cut panel (After Effects; 3.0.0, minimal): one sentence about the hidden daemon, read from its heartbeat
   through window.WNC_BRIDGE (js/bridge.js, panel role). Status only: the panel never works the queue and shows no
   commands. */
(function () {
  var el = document.getElementById('state');
  var APP = { AEFT: 'After Effects', PPRO: 'Premiere Pro' };
  var START_GRACE_MS = 10000;          // the daemon loads with the app; give it this long before saying it is not there
  function sentence() {
    var b = window.WNC_BRIDGE;
    var app = (b && APP[b.host]) || 'After Effects';
    var hb = b ? b.readBeat() : null;
    if (hb && hb.role === 'daemon' && Date.now() - hb.at < b.staleMs) {
      return hb.busy ? 'WhyNot Cut is working in ' + app + '.' : 'WhyNot Cut is running in ' + app + '.';
    }
    if (b && Date.now() - b.loadedAt < START_GRACE_MS) { return 'Starting WhyNot Cut…'; }
    return 'WhyNot Cut isn’t running in ' + app + ': restart ' + app;
  }
  function render() {
    try { el.textContent = sentence(); } catch (e) { el.textContent = 'WhyNot Cut isn’t running: restart the app'; }
  }
  render();
  setInterval(render, 1000);
})();
