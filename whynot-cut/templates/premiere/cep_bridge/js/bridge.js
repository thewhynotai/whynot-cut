/* WhyNot Cut Bridge (by The Why Not AI): lets the whynot-cut plugin run ITS OWN Premiere scripts, on macOS and Windows.
   Polls <engine home>/ppro-queue for *.job.json, evaluates a whitelisted JSX (only files inside <engine home>/ppro-scripts,
   which `reel setup` syncs from the plugin) with a data file, writes *.result.json. A fixed folder is used because the
   plugin's own install path changes on every update. Writes a heartbeat so the pipeline knows the bridge is running.
   <engine home> comes from bridge-config.json (written at install), else ~/.whynot-cut, else a legacy home. */
(function () {
  var req = (window.cep_node && window.cep_node.require) || window.require;
  var fs = req('fs'), path = req('path'), os = req('os');
  var HOME = os.homedir();
  var VERSION = '3.0.0';
  function extensionDir() {
    try {
      var p = decodeURI(window.__adobe_cep__.getSystemPath('extension')).replace(/^file:\/+/, '');
      if (!/^[A-Za-z]:/.test(p)) { p = '/' + p; }
      if (fs.existsSync(p)) { return p; }
    } catch (e) {}
    return os.platform() === 'win32'
      ? path.join(process.env.APPDATA || path.join(HOME, 'AppData', 'Roaming'), 'Adobe', 'CEP', 'extensions', 'ai.thewhynot.cut.bridge')
      : path.join(HOME, 'Library', 'Application Support', 'Adobe', 'CEP', 'extensions', 'ai.thewhynot.cut.bridge');
  }
  function engineHome() {
    try {
      var cfg = JSON.parse(fs.readFileSync(path.join(extensionDir(), 'bridge-config.json'), 'utf8'));
      if (cfg.base && fs.existsSync(cfg.base)) { return cfg.base; }
    } catch (e) {}
    var cands = ['.whynot-cut', '.reel-editor', '.dr-nahla-editor'];
    for (var i = 0; i < cands.length; i++) {
      if (fs.existsSync(path.join(HOME, cands[i]))) { return path.join(HOME, cands[i]); }
    }
    return path.join(HOME, '.whynot-cut');
  }
  var BASE = engineHome();
  if (!fs.existsSync(BASE)) { fs.mkdirSync(BASE, { recursive: true }); }
  BASE = fs.realpathSync(BASE);
  var QUEUE = path.join(BASE, 'ppro-queue');
  var ALLOWED = path.join(BASE, 'ppro-scripts') + path.sep;
  var busy = false;
  // the running job; a lost evalScript callback must not block the queue forever (callers give up after <= 15 min)
  var current = null, currentFile = null, startedAt = 0;
  var JOB_TIMEOUT_MS = 20 * 60 * 1000;
  var stateEl = document.getElementById('state'), logEl = document.getElementById('log');

  function log(m) {
    var line = new Date().toLocaleTimeString() + '  ' + m;
    logEl.textContent = (line + '\n' + logEl.textContent).slice(0, 4000);
  }
  function ensureQueue() {
    if (!fs.existsSync(QUEUE)) { fs.mkdirSync(QUEUE, { recursive: true, mode: 448 }); }
    try { fs.chmodSync(QUEUE, 448); } catch (e) {}
  }
  function heartbeat() {
    try {
      fs.writeFileSync(path.join(QUEUE, 'bridge.heartbeat'),
        JSON.stringify({ at: Date.now(), busy: busy, version: VERSION, who: (document.getElementById('state') ? 'ui' : 'bg') }));
    } catch (e) {}
  }
  function finish(job, file, payload) {
    try { fs.writeFileSync(path.join(QUEUE, job.id + '.result.json'), JSON.stringify(payload)); }
    catch (e) { log('could not write result for ' + job.id + ': ' + e); }
    try { fs.unlinkSync(file); } catch (e) {}
    if (current === job.id) { busy = false; current = null; currentFile = null; }
  }
  function runJob(file) {
    var job;
    try { job = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { try { fs.unlinkSync(file); } catch (e2) {} return; }
    var running = file.replace(/\.job\.json$/, '.running');
    // atomic claim: if the panel and the background copy both see the job, only one rename succeeds
    try { fs.renameSync(file, running); } catch (e) { return; }
    var script;
    try { script = fs.realpathSync(job.script); } catch (e) {
      log('REJECTED missing script: ' + job.script);
      return finish(job, running, { ok: false, error: 'script not found: ' + e.message, script: job.script, at: Date.now() });
    }
    if (script.indexOf(ALLOWED) !== 0) {
      log('REJECTED script outside ppro-scripts: ' + script);
      return finish(job, running, { ok: false, error: 'script not in whitelisted folder', script: script, at: Date.now() });
    }
    busy = true; current = job.id; currentFile = running; startedAt = Date.now();
    stateEl.textContent = 'running ' + job.id + ' (' + (job.action || '') + ')';
    log('run ' + job.id + ' ' + (job.action || ''));
    var code = '$.evalFile(new File(' + JSON.stringify(script) + ')); NHPP.run(' + JSON.stringify(job.data_file) + ');';
    window.__adobe_cep__.evalScript(code, function (res) {
      if (current !== job.id) { log('late result ignored ' + job.id); return; }   // already timed out
      var ok = res !== 'EvalScript error.';
      log((ok ? 'done ' : 'ERROR ') + job.id);
      stateEl.textContent = 'idle — watching queue';
      finish(job, running, { ok: ok, result: res, at: Date.now() });
    });
  }
  function tick() {
    heartbeat();
    if (busy && Date.now() - startedAt > JOB_TIMEOUT_MS) {
      log('TIMEOUT ' + current + ' — no reply from Premiere; queue released');
      stateEl.textContent = 'idle — watching queue';
      finish({ id: current }, currentFile, { ok: false, error: 'no reply from Premiere within ' + (JOB_TIMEOUT_MS / 60000) + ' min', at: Date.now() });
    }
    if (busy) { return; }
    var jobs;
    try { jobs = fs.readdirSync(QUEUE).filter(function (f) { return /\.job\.json$/.test(f); }).sort(); } catch (e) { return; }
    if (jobs.length) { runJob(path.join(QUEUE, jobs[0])); }
  }
  try {
    ensureQueue();
    stateEl.textContent = 'idle — watching queue';
    log('WhyNot Cut Bridge ' + VERSION + ' started; queue ' + QUEUE);
    setInterval(tick, 1000);
  } catch (e) {
    stateEl.textContent = 'FAILED to start: ' + e;
  }
})();
