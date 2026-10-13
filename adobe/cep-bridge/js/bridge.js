/* WhyNot Cut 3.0.0 (by The Why Not AI): the CEP side of the WhyNot Cut engine in Premiere and After Effects, on macOS
   and Windows. One bundle, host-aware: in Premiere the hidden daemon polls <engine home>/ppro-queue (entry WNCPP), in
   After Effects <engine home>/ae-queue (entry WNCAE). For each *.job.json it evaluates one of the libraries bundled in
   <extension>/jsx/ with the job's data file and writes *.result.json, then a heartbeat every second.

   Two copies of this script load (CSXS/manifest.xml): the hidden daemon (daemon.html) is the ONLY copy that works the
   queue; the visible After Effects panel (ui/index.html) loads it to read the daemon's state and never claims a job.

   <engine home> comes from ~/.whynot-cut/bridge/config.json (written by the installer and the engine; a regular file,
   never a link), else the first of ~/.whynot-cut, ~/.reel-editor, ~/.dr-nahla-editor that holds an engine (a runtime
   `current` file or a venv), else ~/.whynot-cut.

   Queue protocol 4 (engine/reel/lib/cep_queue.py documents every file):
     heartbeat  {at, busy, role, host, hostVersion, bundle, version (= bundle), protocol: 4, build, libs {name: sha256},
                current, action}; `build` from <extension>/build.json, `libs` hashed from <extension>/jsx/ at start.
     job        {id, action, lib | script, data_file, submitted, expires_at}. `lib` names a bundled library of this
                host (resolved inside <extension>/jsx/, realpath confined). `script` is the compatibility path: accepted
                only directly inside <engine home>/<scripts>/ with an allowlisted file name. Anything else is answered
                {ok: false, error: "script not allowed"}. A job past its `expires_at` is answered {ok: false, error:
                "expired"} and never run; `<id>.claimed` marks the claim (the engine's result timeout starts there). */
(function () {
  var req = (window.cep_node && window.cep_node.require) || window.require;
  var fs = req('fs'), path = req('path'), os = req('os'), crypto = req('crypto');
  var HOME = os.homedir();
  var BUNDLE = '3.0.0', PROTOCOL = 4;
  var VERSION = BUNDLE;           // the heartbeat's `version` (= bundle): what engines before protocol 4 read
  var HOSTS = {
    PPRO: { queue: 'ppro-queue', scripts: 'ppro-scripts', entry: 'WNCPP', lib: 'wnc_ppro_lib.jsx' },
    AEFT: { queue: 'ae-queue', scripts: 'ae-scripts', entry: 'WNCAE', lib: 'wnc_ae_bridge.jsx' }
  };
  // every library the bundle carries in jsx/ (hashed into the heartbeat; the AE entry loads the other two itself)
  var LIBS = ['wnc_ppro_lib.jsx', 'wnc_ae_bridge.jsx', 'wnc_ae_lib.jsx', 'wnc_motion_lib.jsx'];
  var HOST_ENV = {};
  try { HOST_ENV = JSON.parse(window.__adobe_cep__.getHostEnvironment()) || {}; } catch (e) {}
  var HOST = HOSTS[HOST_ENV.appName] ? HOST_ENV.appName : 'PPRO';
  var HOST_VERSION = HOST_ENV.appVersion ? String(HOST_ENV.appVersion) : null;
  var CFG = HOSTS[HOST];
  var EXT_ID = '';
  try { EXT_ID = String(window.__adobe_cep__.getExtensionId() || ''); } catch (e) {}
  // the visible panel's id ends in .panel; every other copy (the daemon, an older CEP without ids) is the daemon
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
    // ~/.whynot-cut/bridge/config.json {schema: 1, engine_home, launcher, written_by, at}: always under the user home,
    // user-only, no secret, never inside the extension. A link or anything but a regular file is ignored.
    try {
      var cfgFile = path.join(HOME, '.whynot-cut', 'bridge', 'config.json');
      if (fs.lstatSync(cfgFile).isFile()) {
        var cfg = JSON.parse(fs.readFileSync(cfgFile, 'utf8'));
        if (cfg && cfg.schema === 1 && typeof cfg.engine_home === 'string' && path.isAbsolute(cfg.engine_home) &&
            fs.existsSync(cfg.engine_home)) { return cfg.engine_home; }
      }
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
  var EXT = extensionDir();
  var JSX_DIR = path.join(EXT, 'jsx');
  try { JSX_DIR = fs.realpathSync(JSX_DIR); } catch (e) {}
  function readBuild() {
    try {
      var b = JSON.parse(fs.readFileSync(path.join(EXT, 'build.json'), 'utf8'));
      return typeof b.build === 'string' ? b.build : null;
    } catch (e) { return null; }
  }
  function hashLibs() {
    var out = {};
    for (var i = 0; i < LIBS.length; i++) {
      try {
        out[LIBS[i]] = crypto.createHash('sha256').update(fs.readFileSync(path.join(JSX_DIR, LIBS[i]))).digest('hex');
      } catch (e) {}
    }
    return out;
  }
  var BUILD = readBuild(), LIB_SHA = hashLibs();

  var BASE = engineHome();
  if (ROLE === 'daemon' && !fs.existsSync(BASE)) { fs.mkdirSync(BASE, { recursive: true }); }
  try { BASE = fs.realpathSync(BASE); } catch (e) {}
  var QUEUE = path.join(BASE, CFG.queue);
  var HEARTBEAT = path.join(QUEUE, 'bridge.heartbeat');
  var SCRIPTS = path.join(BASE, CFG.scripts);
  var busy = false;
  // the running job; a lost evalScript callback must not block the queue forever (callers give up after <= 15 min)
  var current = null, currentFile = null, currentAction = '', startedAt = 0;
  var JOB_TIMEOUT_MS = 20 * 60 * 1000;
  // the panel counts the daemon gone when it has not beaten for this long (display only: the panel never works the
  // queue). Kept ABOVE the engine's heartbeat window (cep_queue.status max_age_s = 5 s)
  var DAEMON_STALE_MS = 6500;
  var stateEl = document.getElementById('state'), logEl = document.getElementById('log');

  function show(t) { if (stateEl) { stateEl.textContent = t; } }
  function log(m) {
    if (!logEl) { return; }
    var line = new Date().toLocaleTimeString() + '  ' + m;
    logEl.textContent = (line + '\n' + logEl.textContent).slice(0, 4000);
  }
  function readBeat() {
    try { return JSON.parse(fs.readFileSync(HEARTBEAT, 'utf8')); } catch (e) { return null; }
  }

  if (ROLE === 'panel') {
    // the panel (ui/js/panel.js renders it): the daemon's state, read-only. No claim, no heartbeat, no folder made
    window.WNC_BRIDGE = { role: ROLE, host: HOST, bundle: BUNDLE, queue: QUEUE, staleMs: DAEMON_STALE_MS,
                          loadedAt: Date.now(), readBeat: readBeat };
    return;
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
      writeAtomic(HEARTBEAT, JSON.stringify({ at: Date.now(), busy: busy, role: ROLE, host: HOST,
                                              hostVersion: HOST_VERSION, bundle: BUNDLE, version: VERSION,
                                              protocol: PROTOCOL, build: BUILD, libs: LIB_SHA, current: current,
                                              action: currentAction || null }));
    } catch (e) {}
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
  // Windows paths compare without case (a drive letter or folder typed in another case is the same folder)
  function samePath(a, b) {
    return os.platform() === 'win32' ? a.toLowerCase() === b.toLowerCase() : a === b;
  }
  // the file to evaluate for `job`: {file} or {error, ...}. `lib` = this host's bundled library, inside jsx/ after
  // links are resolved; `script` = the compatibility path, directly inside <engine home>/<scripts>/ with the same
  // allowlisted file name. Nothing else runs.
  function resolveScript(job) {
    var deny = { error: 'script not allowed', lib: job.lib, script: job.script };
    if (job.lib !== undefined && job.lib !== null) {
      if (job.lib !== CFG.lib) { return deny; }
      var lib;
      try { lib = fs.realpathSync(path.join(JSX_DIR, job.lib)); } catch (e) {
        return { error: 'script not found: ' + e.message, lib: job.lib };
      }
      return samePath(path.dirname(lib), JSX_DIR) && path.basename(lib) === CFG.lib ? { file: lib } : deny;
    }
    if (typeof job.script !== 'string' || path.basename(job.script) !== CFG.lib) { return deny; }
    var dir, parent, script;
    try { dir = fs.realpathSync(SCRIPTS); parent = fs.realpathSync(path.dirname(job.script)); } catch (e) { return deny; }
    if (!samePath(parent, dir)) { return deny; }
    try { script = fs.realpathSync(job.script); } catch (e) {
      return { error: 'script not found: ' + e.message, script: job.script };
    }
    return samePath(path.dirname(script), dir) && path.basename(script) === CFG.lib ? { file: script } : deny;
  }
  function runJob(file) {
    var job, running = file.replace(/\.job\.json$/, '.running');
    try { job = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) {
      if (e.code === 'ENOENT') { return; }                 // the engine cancelled it this instant
      try { fs.renameSync(file, running); } catch (e2) { return; }
      return finish({ id: path.basename(file).replace(/\.job\.json$/, '') }, running,
                    { ok: false, error: 'unreadable job: ' + e, at: Date.now() });
    }
    // atomic claim: if the engine cancels at the same moment, only one rename succeeds
    try { fs.renameSync(file, running); } catch (e) { return; }
    if (expired(job)) {
      log('EXPIRED ' + job.id + ' (' + (job.action || '') + ') - not run');
      return finish(job, running, { ok: false, error: 'expired', expires_at: job.expires_at, at: Date.now() });
    }
    try { fs.writeFileSync(path.join(QUEUE, job.id + '.claimed'), JSON.stringify({ at: Date.now(), by: ROLE })); } catch (e) {}
    var r = resolveScript(job);
    if (!r.file) {
      log('REJECTED ' + job.id + ': ' + r.error);
      r.ok = false; r.at = Date.now();
      return finish(job, running, r);
    }
    busy = true; current = job.id; currentFile = running; currentAction = job.action || ''; startedAt = Date.now();
    heartbeat();
    show('running ' + job.id + ' (' + currentAction + ')');
    log('run ' + job.id + ' ' + currentAction);
    var code = '$.evalFile(new File(' + JSON.stringify(r.file) + ')); ' + CFG.entry + '.run(' + JSON.stringify(job.data_file) + ');';
    window.__adobe_cep__.evalScript(code, function (res) {
      if (current !== job.id) { log('late result ignored ' + job.id); return; }   // already timed out
      var ok = res !== 'EvalScript error.';
      log((ok ? 'done ' : 'ERROR ') + job.id);
      show('idle - watching the queue');
      finish(job, running, { ok: ok, result: res, at: Date.now() });
    });
  }
  function tick() {
    heartbeat();
    if (busy && Date.now() - startedAt > JOB_TIMEOUT_MS) {
      log('TIMEOUT ' + current + ' - no reply from ' + HOST + '; queue released');
      show('idle - watching the queue');
      finish({ id: current }, currentFile, { ok: false, error: 'no reply from ' + HOST + ' within ' + (JOB_TIMEOUT_MS / 60000) + ' min', at: Date.now() });
    }
    if (busy) { return; }
    var jobs;
    try { jobs = fs.readdirSync(QUEUE).filter(function (f) { return /\.job\.json$/.test(f); }).sort(); } catch (e) { return; }
    if (jobs.length) { runJob(path.join(QUEUE, jobs[0])); }
  }
  try {
    ensureQueue();
    heartbeat();
    show('idle - watching the queue');
    log('WhyNot Cut ' + BUNDLE + ' (' + HOST + ', ' + ROLE + ', build ' + (BUILD || 'unknown') + ') started; queue ' + QUEUE);
    setInterval(tick, 1000);
  } catch (e) {
    show('FAILED to start: ' + e);
  }
})();
