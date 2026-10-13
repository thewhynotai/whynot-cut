/* WhyNot Cut Bridge (by The Why Not AI): lets the whynot-cut plugin run ITS OWN Premiere and After Effects scripts, on
   macOS and Windows. One bundle, host-aware: in Premiere it polls <engine home>/ppro-queue and evaluates only files in
   <engine home>/ppro-scripts (entry NHPP); in After Effects it uses ae-queue / ae-scripts (entry NHAE). For each
   *.job.json it evaluates the whitelisted JSX with a data file and writes *.result.json. A fixed folder is used because the
   plugin's own install path changes on every update. Writes a heartbeat so the pipeline knows the bridge is running.
   <engine home> comes from bridge-config.json (written at install), else the first of ~/.whynot-cut, ~/.reel-editor,
   ~/.dr-nahla-editor that holds an engine (a runtime `current` file or a venv), else ~/.whynot-cut.
   Two copies of this script load (manifest.xml): the hidden daemon works the queue; the visible panel only shows the
   daemon's state, and works the queue itself only while no daemon heartbeat is fresh (the daemon did not load).
   Queue protocol 3.1.1 (engine/reel/lib/cep_queue.py documents every file): a job past its `expires_at` is answered
   {ok:false, error:"expired"} and never run; `<id>.claimed` marks the claim (the engine's result timeout starts there). */
(function () {
  var req = (window.cep_node && window.cep_node.require) || window.require;
  var fs = req('fs'), path = req('path'), os = req('os');
  var HOME = os.homedir();
  var VERSION = '3.1.1';
  var HOSTS = {
    PPRO: { queue: 'ppro-queue', scripts: 'ppro-scripts', entry: 'NHPP' },
    AEFT: { queue: 'ae-queue', scripts: 'ae-scripts', entry: 'NHAE' }
  };
  function hostId() {
    try { return JSON.parse(window.__adobe_cep__.getHostEnvironment()).appName || 'PPRO'; } catch (e) { return 'PPRO'; }
  }
  var HOST = hostId();
  if (!HOSTS[HOST]) { HOST = 'PPRO'; }
  var CFG = HOSTS[HOST];
  var EXT_ID = '';
  try { EXT_ID = String(window.__adobe_cep__.getExtensionId() || ''); } catch (e) {}
  // an unknown id (an older CEP) keeps the old behaviour: this copy works the queue
  var ROLE = /\.panel$/.test(EXT_ID) ? 'panel' : 'daemon';
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
    // same rule as bin/reel, reel.cmd and plat.engine_home(): a home counts only with an engine inside, the runtime's
    // `current` file (3.0) or a venv folder (WhyNot Cut's SessionStart hook creates ~/.whynot-cut for
    // plugin-options.json alone)
    var cands = ['.whynot-cut', '.reel-editor', '.dr-nahla-editor'];
    for (var i = 0; i < cands.length; i++) {
      var d = path.join(HOME, cands[i]), cur = path.join(d, 'current');
      var hasCurrent = false;
      try { hasCurrent = fs.statSync(cur).isFile(); } catch (e2) {}
      if (hasCurrent || fs.existsSync(path.join(d, 'venv'))) { return d; }
    }
    return path.join(HOME, '.whynot-cut');
  }
  var BASE = engineHome();
  if (!fs.existsSync(BASE)) { fs.mkdirSync(BASE, { recursive: true }); }
  BASE = fs.realpathSync(BASE);
  var QUEUE = path.join(BASE, CFG.queue);
  var HEARTBEAT = path.join(QUEUE, 'bridge.heartbeat');
  var ALLOWED = path.join(BASE, CFG.scripts) + path.sep;
  var busy = false;
  // the running job; a lost evalScript callback must not block the queue forever (callers give up after <= 15 min)
  var current = null, currentFile = null, currentAction = '', startedAt = 0;
  var JOB_TIMEOUT_MS = 20 * 60 * 1000;
  // the panel takes over when the daemon has not beaten for this long. Keep it ABOVE the engine's heartbeat window
  // (cep_queue.status max_age_s = 5 s): while the engine still counts the daemon alive, the panel must not compete
  var DAEMON_STALE_MS = 6500;
  var loadedAt = Date.now(), working = (ROLE === 'daemon');
  var stateEl = document.getElementById('state'), logEl = document.getElementById('log');

  function log(m) {
    var line = new Date().toLocaleTimeString() + '  ' + m;
    logEl.textContent = (line + '\n' + logEl.textContent).slice(0, 4000);
  }
  function ensureQueue() {
    if (!fs.existsSync(QUEUE)) { fs.mkdirSync(QUEUE, { recursive: true, mode: 448 }); }
    try { fs.chmodSync(QUEUE, 448); } catch (e) {}
  }
  // write then rename: a reader never sees half a file (Windows refuses the rename while a reader has the file open:
  // then write in place, the engine retries a torn read)
  function writeAtomic(file, text) {
    var tmp = file + '.' + ROLE + '.tmp';
    try { fs.writeFileSync(tmp, text); fs.renameSync(tmp, file); return; } catch (e) {}
    try { fs.unlinkSync(tmp); } catch (e2) {}
    fs.writeFileSync(file, text);
  }
  function heartbeat() {
    try {
      writeAtomic(HEARTBEAT, JSON.stringify({ at: Date.now(), busy: busy, version: VERSION, host: HOST, role: ROLE,
                                              current: current, action: currentAction || null }));
    } catch (e) {}
  }
  function readBeat() {
    try { return JSON.parse(fs.readFileSync(HEARTBEAT, 'utf8')); } catch (e) { return null; }
  }
  function finish(job, file, payload) {
    try { writeAtomic(path.join(QUEUE, job.id + '.result.json'), JSON.stringify(payload)); }
    catch (e) { log('could not write result for ' + job.id + ': ' + e); }
    try { fs.unlinkSync(file); } catch (e) {}
    if (current === job.id) { busy = false; current = null; currentFile = null; currentAction = ''; }
  }
  function expired(job) {
    var t = job && job.expires_at ? Date.parse(job.expires_at) : NaN;
    return !isNaN(t) && Date.now() > t;
  }
  function runJob(file) {
    var job, running = file.replace(/\.job\.json$/, '.running');
    try { job = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) {
      if (e.code === 'ENOENT') { return; }                 // the engine cancelled it this instant
      try { fs.renameSync(file, running); } catch (e2) { return; }
      return finish({ id: path.basename(file).replace(/\.job\.json$/, '') }, running,
                    { ok: false, error: 'unreadable job: ' + e, at: Date.now() });
    }
    // atomic claim: if two copies (or a cancelling engine) race for the job, only one rename succeeds
    try { fs.renameSync(file, running); } catch (e) { return; }
    if (expired(job)) {
      log('EXPIRED ' + job.id + ' (' + (job.action || '') + ') — not run');
      return finish(job, running, { ok: false, error: 'expired', expires_at: job.expires_at, at: Date.now() });
    }
    try { fs.writeFileSync(path.join(QUEUE, job.id + '.claimed'), JSON.stringify({ at: Date.now(), by: ROLE })); } catch (e) {}
    var script;
    try { script = fs.realpathSync(job.script); } catch (e) {
      log('REJECTED missing script: ' + job.script);
      return finish(job, running, { ok: false, error: 'script not found: ' + e.message, script: job.script, at: Date.now() });
    }
    if (script.indexOf(ALLOWED) !== 0) {
      log('REJECTED script outside ' + CFG.scripts + ': ' + script);
      return finish(job, running, { ok: false, error: 'script not in whitelisted folder', script: script, at: Date.now() });
    }
    busy = true; current = job.id; currentFile = running; currentAction = job.action || ''; startedAt = Date.now();
    heartbeat();
    stateEl.textContent = 'running ' + job.id + ' (' + currentAction + ')';
    log('run ' + job.id + ' ' + currentAction);
    var code = '$.evalFile(new File(' + JSON.stringify(script) + ')); ' + CFG.entry + '.run(' + JSON.stringify(job.data_file) + ');';
    window.__adobe_cep__.evalScript(code, function (res) {
      if (current !== job.id) { log('late result ignored ' + job.id); return; }   // already timed out
      var ok = res !== 'EvalScript error.';
      log((ok ? 'done ' : 'ERROR ') + job.id);
      stateEl.textContent = 'idle — watching queue';
      finish(job, running, { ok: ok, result: res, at: Date.now() });
    });
  }
  // the panel: show the daemon's state; work the queue only while the daemon is not beating
  function panelShouldWork() {
    var hb = readBeat();
    var daemon = hb && hb.role === 'daemon' && Date.now() - hb.at < DAEMON_STALE_MS;
    if (daemon) {
      if (working && !busy) { working = false; log('background bridge running: this panel shows its state only'); }
      if (!working) {
        stateEl.textContent = hb.busy ? 'running ' + hb.current + ' (' + (hb.action || '') + ') in the background'
                                      : 'idle — the background bridge is watching the queue';
      }
      return working;
    }
    if (!working && Date.now() - loadedAt >= DAEMON_STALE_MS) {
      working = true;
      stateEl.textContent = 'idle — watching queue';
      log('background bridge not running: this panel works the queue');
    }
    return working;
  }
  function tick() {
    if (ROLE === 'panel' && !panelShouldWork()) { return; }
    heartbeat();
    if (busy && Date.now() - startedAt > JOB_TIMEOUT_MS) {
      log('TIMEOUT ' + current + ' — no reply from ' + HOST + '; queue released');
      stateEl.textContent = 'idle — watching queue';
      finish({ id: current }, currentFile, { ok: false, error: 'no reply from ' + HOST + ' within ' + (JOB_TIMEOUT_MS / 60000) + ' min', at: Date.now() });
    }
    if (busy) { return; }
    var jobs;
    try { jobs = fs.readdirSync(QUEUE).filter(function (f) { return /\.job\.json$/.test(f); }).sort(); } catch (e) { return; }
    if (jobs.length) { runJob(path.join(QUEUE, jobs[0])); }
  }
  try {
    ensureQueue();
    stateEl.textContent = ROLE === 'daemon' ? 'idle — watching queue' : 'looking for the background bridge…';
    log('WhyNot Cut Bridge ' + VERSION + ' (' + HOST + ', ' + ROLE + ') started; queue ' + QUEUE);
    setInterval(tick, 1000);
  } catch (e) {
    stateEl.textContent = 'FAILED to start: ' + e;
  }
})();
