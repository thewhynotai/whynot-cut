/* WhyNot Cut 3.0.0 (by The Why Not AI): the CEP side of the WhyNot Cut engine in Premiere and After Effects, on macOS
   and Windows. One bundle, host-aware: in Premiere the hidden daemon polls <engine home>/ppro-queue (entry WNCPP), in
   After Effects <engine home>/ae-queue (entry WNCAE). For each *.job.json it evaluates one of the libraries bundled in
   <extension>/jsx/ with the job's data file and writes *.result.json, and a heartbeat every 2 s.

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
                "expired"} and never run; `<id>.claimed` marks the claim (the engine's result timeout starts there).

   Engine start (daemon only; docs/adobe/cep-bridge.md "Spawn allowlist"): at start and every 30 s, when
   ~/.whynot-cut/bridge/engine.json is missing or its pid is dead, the daemon starts the engine through ONE fixed file:
   config.json `launcher`, accepted only when it is an absolute path to a regular file whose realpath is
   realpath(engine_home)/bin/wnc-engine.cmd (Windows) or wnc-engine (macOS), with none of " % ^ & | < > ! in it, on
   Windows inside %USERPROFILE%, and on macOS owned by this user and not group- or world-writable. What is spawned is
   that checked realpath, never the configured string. No arguments, no shell string built from anything else.
   At most one attempt per 30 s; after 5 failed attempts it keeps trying, one attempt every 5 minutes (outcome gave_up
   between attempts, heartbeat `engine_retry: 'slow'`). Of engine.json only the pid
   is parsed: the token in it is never kept or logged. The heartbeat's `engine_start` {at, outcome, reason} says what
   happened: running | no_launcher | refused | spawned | spawn_error | failed | gave_up; `reason` is a fixed code
   (refused: which check; gave_up: 'gave_up'; else null), never a path.

   Queue durability (hardening H2): at start every `<id>.running` a previous run left gets the result {ok: false,
   error: 'interrupted', reason: 'bridge restarted', claimed: true} and is never run again; a result that cannot be written is retried
   3 times (1 s, 2 s, 4 s apart) and then a minimal `<id>.error` marker {ok: false, error: 'result write failed', at}
   is written, so the engine and `reel serve` see a failed job at once.

   Lean footprint (hardening H6). The daemon wakes for three reasons only:
     - the heartbeat, every HEARTBEAT_MS (2 s; cep_queue.status counts a beat older than 5 s as dead, and the panel
       role 6.5 s), and every SAFETY_EVERY-th beat (10 s) the safety tick: a queue scan (a missed watch event costs at
       most 10 s), the job timeout, re-arming a lost watch. The engine check rides on the beat: every 30 s, backing off
       30 -> 60 -> 120 s while the engine runs and no job came (any job, or an engine that is not running, resets it);
     - fs.watch on the queue folder: a name ending in .job.json (or no name: macOS may give none) asks for one scan,
       WATCH_SETTLE_MS later, so a burst of duplicate events is one scan; every other name (this daemon's own
       heartbeat and result writes) is ignored, but it proves the watch is alive. Until the watch has delivered an event
       (its first heartbeat write does at once) and after a watch error or a watch that throws, the queue is scanned
       every FALLBACK_SCAN_MS (1 s) as before; the safety tick re-arms the watch, and a watch that stays deaf for
       WATCH_DEAF_MS (its own heartbeat writes stop showing) is dropped for the same fallback;
     - a job's own life: its evalScript answer, a result retry when due, the next scan right after a job ends.
   No evalScript runs on a timer: the host is touched only when a job runs (the job, and the host_busy probe or bind
   below just before it).

   host_busy (H6), in every heartbeat: "exporting" | "rendering" | "idle" | "unknown", from memory (no host call):
     - Premiere: this daemon's own export job (export_frames, the audio exports) is "exporting". Else app.encoder's
       job events, bound once before the first job (an ExtendScript handler per event dispatching the CSXS event
       ENCODER_EVENT), counted: queued +1, complete / error / canceled -1. A count above 0 is "exporting" while an
       event came within ENCODER_STALE_MS; past it, or a count that went below 0 (a missed queued), or progress with
       nothing queued, the count is reset and the value is "unknown" until the next queued event. "idle" only after
       one full queued -> done cycle proved the events reach this daemon. No bind, or a bind that failed: "unknown".
     - After Effects: app.project.renderQueue.rendering, probed with one short evalScript just before each job (the
       panel's status check is a job too), believed for HOST_BUSY_TTL_MS, then "unknown".
     The live behaviour is unverified (docs/adobe/evidence/h6-live-checklist.md). */
(function () {
  var req = (window.cep_node && window.cep_node.require) || window.require;
  var fs = req('fs'), path = req('path'), os = req('os'), crypto = req('crypto');
  var IS_WIN = os.platform() === 'win32';
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
  // ~/.whynot-cut/bridge/config.json {schema: 1, engine_home, launcher, written_by, at}: always under the user home,
  // user-only, no secret, never inside the extension. A link or anything but a regular file is ignored; so is a config
  // whose engine_home is not an absolute path to an existing folder. Read fresh on every call (the installer may write
  // it while the app runs).
  function readConfig() {
    try {
      var cfgFile = path.join(HOME, '.whynot-cut', 'bridge', 'config.json');
      if (fs.lstatSync(cfgFile).isFile()) {
        var cfg = JSON.parse(fs.readFileSync(cfgFile, 'utf8'));
        if (cfg && cfg.schema === 1 && typeof cfg.engine_home === 'string' && path.isAbsolute(cfg.engine_home) &&
            fs.existsSync(cfg.engine_home)) { return cfg; }
      }
    } catch (e) {}
    return null;
  }
  // config.json first, else the fallback below. Self-contained: tests lift this function out of the file on its own
  // (test_wrappers, test_runtime), where readConfig does not exist and only the fallback runs
  function engineHome() {
    var cfg = typeof readConfig === 'function' ? readConfig() : null;
    if (cfg) { return cfg.engine_home; }
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
  // H6 timings (see the header)
  var HEARTBEAT_MS = 2000, SAFETY_EVERY = 5, FALLBACK_SCAN_MS = 1000, WATCH_SETTLE_MS = 50, WATCH_DEAF_MS = 10000;

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
    window.WNC_BRIDGE = { role: ROLE, host: HOST, hostVersion: HOST_VERSION, bundle: BUNDLE, build: BUILD,
                          queue: QUEUE, staleMs: DAEMON_STALE_MS, loadedAt: Date.now(), readBeat: readBeat };
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
                                              action: currentAction || null, engine_start: engineStart,
                                              engine_retry: engineSlow ? 'slow' : null, host_busy: hostBusy() }));
    } catch (e) {}
  }
  // Result delivery (hardening H2). A result that cannot be written (disk full, a locked folder) is tried 3 more times,
  // 1 s, 2 s and 4 s apart (on later ticks, never blocking one), the job staying claimed (`<id>.running`) meanwhile and
  // the queue free for the next job. After the last failed try a minimal `<id>.error` marker {ok, error, at} is
  // written (no path, no text from the file system) and the job file is removed: the engine and `reel serve` read a
  // marker, or a job that vanished with no result, as a failed job instead of waiting for their timeout.
  var RESULT_RETRY_MS = [1000, 2000, 4000];
  var pendingResults = [];                   // [{id, file, payload, tries (made so far), due (ms epoch)}]
  function writeResult(id, payload) {
    try { writeAtomic(path.join(QUEUE, id + '.result.json'), JSON.stringify(payload)); return true; }
    catch (e) { log('could not write result for ' + id + ': ' + e); return false; }
  }
  function giveUpResult(p) {
    try { writeAtomic(path.join(QUEUE, p.id + '.error'), JSON.stringify({ ok: false, error: 'result write failed', at: Date.now() })); }
    catch (e) {
      // no marker either: the job is simply gone (a failed job to the engine), and its claim marker goes with it
      log('could not write the error marker for ' + p.id + ': ' + e);
      try { fs.unlinkSync(path.join(QUEUE, p.id + '.claimed')); } catch (e2) {}
    }
    try { fs.unlinkSync(p.file); } catch (e) {}
  }
  function retryResults() {
    var now = Date.now(), keep = [];
    for (var i = 0; i < pendingResults.length; i++) {
      var p = pendingResults[i];
      if (now < p.due) { keep.push(p); continue; }
      if (writeResult(p.id, p.payload)) {
        log('result for ' + p.id + ' written after ' + (p.tries + 1) + ' tries');
        try { fs.unlinkSync(p.file); } catch (e) {}
        continue;
      }
      p.tries += 1;
      if (p.tries > RESULT_RETRY_MS.length) { log('GAVE UP writing the result for ' + p.id + '; error marker'); giveUpResult(p); continue; }
      p.due = now + RESULT_RETRY_MS[p.tries - 1];
      keep.push(p);
    }
    pendingResults = keep;
    scheduleRetry();
  }
  // one timer for the earliest due retry (none when nothing waits)
  var retryTimer = null;
  function scheduleRetry() {
    if (retryTimer !== null) { clearTimeout(retryTimer); retryTimer = null; }
    if (!pendingResults.length) { return; }
    var due = pendingResults[0].due;
    for (var i = 1; i < pendingResults.length; i++) { if (pendingResults[i].due < due) { due = pendingResults[i].due; } }
    retryTimer = setTimeout(function () { retryTimer = null; retryResults(); }, Math.max(0, due - Date.now()));
  }
  function finish(job, file, payload) {
    if (writeResult(job.id, payload)) {
      try { fs.unlinkSync(file); } catch (e) {}
    } else {
      pendingResults.push({ id: job.id, file: file, payload: payload, tries: 1, due: Date.now() + RESULT_RETRY_MS[0] });
      scheduleRetry();
    }
    if (current === job.id) {
      busy = false; current = null; currentFile = null; currentAction = '';
      heartbeat();                             // the engine sees the queue free at once, not at the next beat
    }
    scheduleScan();                            // the next job, if any, without waiting for an event
  }
  // A bridge that restarted: every `<id>.running` in the queue was claimed by a previous run that never finished it
  // (this daemon is the only worker of its queue and holds no job yet). Each gets {ok:false, error:'interrupted',
  // reason:'bridge restarted', claimed:true} (the host may still have run it) and is never run again; a job that already has its result only loses the stale file.
  function recoverOrphans() {
    var names;
    try { names = fs.readdirSync(QUEUE); } catch (e) { return; }
    names.sort().forEach(function (name) {
      var m = /^([\w.-]+)\.running$/.exec(name);
      if (!m) { return; }
      var file = path.join(QUEUE, name);
      if (fs.existsSync(path.join(QUEUE, m[1] + '.result.json'))) { try { fs.unlinkSync(file); } catch (e) {} return; }
      log('interrupted ' + m[1] + ' (bridge restarted)');
      finish({ id: m[1] }, file, { ok: false, error: 'interrupted', reason: 'bridge restarted', claimed: true, at: Date.now() });
    });
  }
  function expired(job) {
    var t = job && job.expires_at ? Date.parse(job.expires_at) : NaN;
    return !isNaN(t) && Date.now() > t;
  }
  // Windows paths compare without case (a drive letter or folder typed in another case is the same folder)
  function samePath(a, b) {
    return IS_WIN ? a.toLowerCase() === b.toLowerCase() : a === b;
  }

  // ---- engine start: the fixed launcher only (see the header) ----
  var ENGINE_CHECK_MS = 30000, ENGINE_IDLE_MAX_MS = 120000, ENGINE_MAX_FAILURES = 5, ENGINE_SLOW_MS = 5 * 60 * 1000;
  var LAUNCHER_NAME = IS_WIN ? 'wnc-engine.cmd' : 'wnc-engine';
  var LAUNCHER_META = /["%^&|<>!]/;            // cmd.exe acts on these even inside quotes (% and ! expand)
  var ENGINE_JSON = path.join(HOME, '.whynot-cut', 'bridge', 'engine.json');
  var engineStart = null, engineCheckedAt = null, engineFailures = 0, enginePending = false, engineSlow = false;
  // H6: the check interval while the engine runs: 30 s after the first check that finds it running, then doubled up
  // to 120 s by each further check that finds it running with no job since the previous one; a job, or an engine that
  // is not running, sets it back to 30 s
  var engineEvery = ENGINE_CHECK_MS, jobSinceEngineCheck = false, engineWasAlive = false;
  // engine.json holds the engine's token: the reviver keeps only `pid`, so nothing else of the file is held, and no
  // error text (a parse error can quote the file) is ever logged
  function enginePid() {
    try {
      var rec = JSON.parse(fs.readFileSync(ENGINE_JSON, 'utf8'), function (k, v) {
        return k === '' || k === 'pid' ? v : undefined;
      });
      var pid = rec && rec.pid;
      return typeof pid === 'number' && pid > 0 && pid % 1 === 0 ? pid : null;
    } catch (e) { return null; }
  }
  function engineAlive() {
    var pid = enginePid();
    if (pid === null) { return false; }
    try { process.kill(pid, 0); return true; } catch (e) { return !!e && e.code === 'EPERM'; }
  }
  // the user's profile folder (Windows: %USERPROFILE%), resolved; null when it cannot be resolved
  function profileDir() {
    var p = IS_WIN && typeof process.env.USERPROFILE === 'string' && path.isAbsolute(process.env.USERPROFILE)
      ? process.env.USERPROFILE : HOME;
    try { return fs.realpathSync(p); } catch (e) { return null; }
  }
  function inside(child, parent) {
    var rel = path.relative(IS_WIN ? parent.toLowerCase() : parent, IS_WIN ? child.toLowerCase() : child);
    return !!rel && rel.split(path.sep)[0] !== '..' && !path.isAbsolute(rel);
  }
  // {file, cwd} when config.json names an acceptable launcher (file, cwd = the checked realpaths), else
  // {outcome: 'no_launcher' | 'refused', reason: <fixed code>, why: <log text>}
  function launcherFrom(cfg) {
    if (!cfg || cfg.launcher === null || cfg.launcher === undefined) { return { outcome: 'no_launcher', reason: null }; }
    var refuse = function (code, why) { return { outcome: 'refused', reason: code, why: why }; };
    var l = cfg.launcher;
    if (typeof l !== 'string' || !path.isAbsolute(l)) { return refuse('not_absolute', 'not an absolute path'); }
    if (LAUNCHER_META.test(l) || LAUNCHER_META.test(cfg.engine_home)) {
      return refuse('metachar_in_path', 'a refused character in the path');
    }
    var st, real, home, want;
    try { st = fs.statSync(l); } catch (e) { return refuse('not_found', 'missing'); }
    if (!st.isFile()) { return refuse('not_a_file', 'not a regular file'); }
    try {
      real = fs.realpathSync(l);
      home = fs.realpathSync(cfg.engine_home);
      want = path.join(home, 'bin', LAUNCHER_NAME);
    } catch (e) { return refuse('unresolvable', 'cannot be resolved'); }
    if (!samePath(real, want)) { return refuse('not_the_launcher', 'not <engine home>/bin/' + LAUNCHER_NAME); }
    if (LAUNCHER_META.test(real)) { return refuse('metachar_in_path', 'a refused character in the path'); }
    if (IS_WIN) {
      var prof = profileDir();
      if (!prof || !inside(real, prof)) { return refuse('outside_profile', 'outside the user profile folder'); }
    } else {
      var rs;
      try { rs = fs.statSync(real); } catch (e) { return refuse('not_found', 'missing'); }
      if (typeof process.getuid !== 'function' || rs.uid !== process.getuid()) {
        return refuse('not_owner', 'not owned by this user');
      }
      if (rs.mode & 18) { return refuse('writable_by_others', 'group- or world-writable'); }      // 18 = 0o022
    }
    return { file: real, cwd: home };                       // both resolved: what was checked
  }
  function spawnLauncher(l) {
    var cp = req('child_process');
    var opts = { detached: true, windowsHide: true, stdio: 'ignore', cwd: l.cwd };
    if (IS_WIN) {
      var shell = process.env.ComSpec;
      if (!(typeof shell === 'string' && path.isAbsolute(shell) && /^cmd\.exe$/i.test(path.basename(shell)))) {
        shell = 'C:\\Windows\\System32\\cmd.exe';
      }
      // node's own shell form: verbatim (node must not escape the quotes into \"), and /s strips ONE pair of outer
      // quotes, so the quoted path is quoted once more: cmd.exe then runs "<launcher>" whole, spaces included
      // (measured: a single pair fails with a space in the path, exit 1)
      opts.windowsVerbatimArguments = true;
      return cp.spawn(shell, ['/d', '/s', '/c', '""' + l.file + '""'], opts);
    }
    return cp.spawn(l.file, [], opts);
  }
  // engine_start {at, outcome, reason}: `reason` is a fixed code (never a path); `why` goes to the log only
  function setEngineStart(outcome, why, reason) {
    if (!engineStart || engineStart.outcome !== outcome) { log('engine start: ' + outcome + (why ? ' (' + why + ')' : '')); }
    engineStart = { at: Date.now(), outcome: outcome, reason: reason || null };
  }
  // After ENGINE_MAX_FAILURES failed attempts the daemon does not stop: it keeps trying, one attempt every
  // ENGINE_SLOW_MS (the outcome stays gave_up between attempts and the heartbeat says engine_retry 'slow'); an engine
  // that comes up ends the slow retry
  function engineFailed(outcome) {
    engineFailures += 1;
    if (engineFailures >= ENGINE_MAX_FAILURES) {
      engineSlow = true;
      return setEngineStart('gave_up', engineFailures + ' failed attempts; it tries again every 5 minutes', 'gave_up');
    }
    setEngineStart(outcome);
  }
  function engineCheck() {
    var alive = engineAlive();
    var idle = !jobSinceEngineCheck && !busy;
    jobSinceEngineCheck = false;
    engineEvery = alive && idle && engineWasAlive ? Math.min(engineEvery * 2, ENGINE_IDLE_MAX_MS) : ENGINE_CHECK_MS;
    engineWasAlive = alive;
    if (enginePending) {                       // the attempt 30 s ago: did the engine come up?
      enginePending = false;
      if (!alive) { engineFailed('failed'); if (engineSlow) { return; } }
    }
    if (alive) { engineFailures = 0; engineSlow = false; return setEngineStart('running'); }
    var l = launcherFrom(readConfig());
    if (!l.file) { return setEngineStart(l.outcome, l.why, l.reason); }
    var child;
    try { child = spawnLauncher(l); } catch (e) { return engineFailed('spawn_error'); }
    enginePending = true;
    setEngineStart('spawned');
    // a launcher that cannot run, or exits non-zero, is a failed attempt now; a zero exit waits for the next check
    var settle = function (outcome) {
      if (enginePending) { enginePending = false; engineFailed(outcome); }
    };
    try {
      child.on('error', function () { settle('spawn_error'); });
      child.on('exit', function (code) { if (code !== 0) { settle('failed'); } });
      child.unref();
    } catch (e) {}
  }
  function engineTick() {
    var every = engineSlow && !enginePending ? ENGINE_SLOW_MS : enginePending ? ENGINE_CHECK_MS : engineEvery;
    if (engineCheckedAt !== null && Date.now() - engineCheckedAt < every) { return; }
    engineCheckedAt = Date.now();
    try { engineCheck(); } catch (e) { log('engine start check failed'); }
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
    // the id is the job file's name (readdir: never a path); every result / claim path is built from it. A JSON id
    // that differs, or a name outside ^[\w.-]+$, is answered "bad job id" inside the queue and never run
    var fileId = path.basename(file).replace(/\.job\.json$/, '');
    var jsonId = job && typeof job === 'object' ? job.id : undefined;
    if (!job || typeof job !== 'object') { job = {}; }
    job.id = fileId;
    if (jsonId !== fileId || !/^[\w.-]+$/.test(fileId)) {
      log('REJECTED ' + fileId + ': bad job id');
      return finish(job, running, { ok: false, error: 'bad job id', at: Date.now() });
    }
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
    jobSinceEngineCheck = true;
    heartbeat();
    show('running ' + job.id + ' (' + currentAction + ')');
    log('run ' + job.id + ' ' + currentAction);
    hostTouch();                               // host_busy: the bind / probe rides on this job (queued before it)
    var code = '$.evalFile(new File(' + JSON.stringify(r.file) + ')); ' + CFG.entry + '.run(' + JSON.stringify(job.data_file) + ');';
    window.__adobe_cep__.evalScript(code, function (res) {
      if (current !== job.id) { log('late result ignored ' + job.id); return; }   // already timed out
      var ok = res !== 'EvalScript error.';
      log((ok ? 'done ' : 'ERROR ') + job.id);
      show('idle - watching the queue');
      finish(job, running, { ok: ok, result: res, at: Date.now() });
    });
  }
  // ---- host_busy (H6; see the header) ----
  var HOST_BUSY_TTL_MS = 15000, ENCODER_STALE_MS = 120000;
  var EXPORT_ACTIONS = { 'export_frames': 1, 'WNC_AUDIO.exportRange': 1, 'WNC_AUDIO.exportClipAudio': 1 };
  var ENCODER_EVENT = 'ai.thewhynot.cut.encoder';
  // one ExtendScript call: binds the five encoder events once per ExtendScript engine (a global guard: a reloaded
  // daemon never binds twice); each handler dispatches ENCODER_EVENT with its kind
  var ENCODER_BIND = '(function () { if ($.global.__wncEncoderBound) { return "bound"; } try {' +
    ' if (typeof CSXSEvent === "undefined") { new ExternalObject("lib:PlugPlugExternalObject"); }' +
    ' var send = function (k) { return function () { try { var e = new CSXSEvent(); e.type = "' + ENCODER_EVENT + '";' +
    ' e.data = k; e.dispatch(); } catch (x) {} }; };' +
    ' app.encoder.bind("onEncoderJobQueued", send("queued")); app.encoder.bind("onEncoderJobComplete", send("complete"));' +
    ' app.encoder.bind("onEncoderJobError", send("error")); app.encoder.bind("onEncoderJobCanceled", send("canceled"));' +
    ' app.encoder.bind("onEncoderJobProgress", send("progress"));' +
    ' $.global.__wncEncoderBound = true; return "bound"; } catch (e) { return "unavailable"; } })()';
  var AE_PROBE = '(function () { try { return app.project.renderQueue.rendering ? "rendering" : "idle"; }' +
    ' catch (e) { return "unknown"; } })()';
  var enc = { tried: false, bound: false, proven: false, count: 0, at: 0, doubt: false };
  var aeProbe = { value: null, at: 0 };
  function hostBusy() {
    var now = Date.now();
    if (HOST === 'AEFT') { return aeProbe.value && now - aeProbe.at < HOST_BUSY_TTL_MS ? aeProbe.value : 'unknown'; }
    if (busy && EXPORT_ACTIONS[currentAction]) { return 'exporting'; }
    if (!enc.bound) { return 'unknown'; }
    if (enc.count > 0) {
      if (now - enc.at < ENCODER_STALE_MS) { return 'exporting'; }
      enc.count = 0; enc.doubt = true;         // a done event was missed: never a stuck "exporting"
    }
    return enc.proven && !enc.doubt ? 'idle' : 'unknown';
  }
  function onEncoderEvent(ev) {
    var kind = ev && typeof ev === 'object' ? ev.data : ev;
    var before = hostBusy();
    if (kind === 'queued') {
      if (enc.count === 0) { enc.doubt = false; }
      enc.count += 1;
    } else if (kind === 'complete' || kind === 'error' || kind === 'canceled') {
      enc.count -= 1;
      if (enc.count < 0) { enc.count = 0; enc.doubt = true; }        // a queued was missed
      else if (enc.count === 0 && !enc.doubt) { enc.proven = true; }
    } else if (kind === 'progress') {
      if (enc.count === 0) { enc.count = 1; enc.doubt = true; }      // rendering, but its queued was missed
    } else { return; }
    enc.at = Date.now();
    if (hostBusy() !== before) { heartbeat(); }                     // a change shows at once (progress never writes)
  }
  // the host call that rides on a job: Premiere binds the encoder events once, After Effects probes its render queue
  function hostTouch() {
    var cep = window.__adobe_cep__;
    if (HOST === 'AEFT') {
      try {
        cep.evalScript(AE_PROBE, function (res) {
          if (res === 'rendering' || res === 'idle' || res === 'unknown') { aeProbe.value = res; aeProbe.at = Date.now(); }
        });
      } catch (e) {}
      return;
    }
    if (enc.tried) { return; }
    enc.tried = true;
    try {
      if (typeof cep.addEventListener !== 'function') { return; }
      cep.addEventListener(ENCODER_EVENT, onEncoderEvent);
      cep.evalScript(ENCODER_BIND, function (res) {
        enc.bound = res === 'bound';
        log('encoder events: ' + (enc.bound ? 'bound' : 'unavailable'));
      });
    } catch (e) {}
  }

  // ---- the queue: fs.watch, the heartbeat and the safety tick (H6; see the header) ----
  var watcher = null, fallbackTimer = null, scanTimer = null, lastWatchEvent = 0, beats = 0, watchNote = '';
  // the log says each watch trouble once, not on every re-arm
  function watchLog(note) {
    if (note !== watchNote) { watchNote = note; if (note) { log(note); } }
  }
  function scanQueue() {
    if (busy) { return; }
    var jobs;
    try { jobs = fs.readdirSync(QUEUE).filter(function (f) { return /\.job\.json$/.test(f); }).sort(); } catch (e) { return; }
    for (var i = 0; i < jobs.length && !busy; i++) { runJob(path.join(QUEUE, jobs[i])); }
  }
  // one scan WATCH_SETTLE_MS from now, however many events ask for it meanwhile
  function scheduleScan() {
    if (scanTimer !== null) { return; }
    scanTimer = setTimeout(function () {
      scanTimer = null;
      try { scanQueue(); } catch (e) { log('queue scan failed'); }
    }, WATCH_SETTLE_MS);
  }
  function startFallback() {
    if (fallbackTimer === null) { fallbackTimer = setInterval(function () { try { scanQueue(); } catch (e) {} }, FALLBACK_SCAN_MS); }
  }
  function stopFallback() {
    if (fallbackTimer !== null) { clearInterval(fallbackTimer); fallbackTimer = null; }
  }
  function onWatch(type, name) {
    lastWatchEvent = Date.now();
    if (fallbackTimer !== null) { stopFallback(); watchLog(''); } // proven: events reach this daemon
    if (name === null || name === undefined || /\.job\.json$/.test(String(name))) { scheduleScan(); }
  }
  function dropWatch(why) {
    var w = watcher;
    watcher = null;
    if (w) { try { w.close(); } catch (e) {} }
    watchLog('queue watch ' + why + '; scanning every ' + (FALLBACK_SCAN_MS / 1000) + ' s');
    startFallback();
    scheduleScan();                            // whatever arrived while it failed
  }
  // until the watch has delivered an event (its own next heartbeat write does) the queue is scanned every
  // FALLBACK_SCAN_MS too
  function armWatch() {
    if (watcher) { return; }
    startFallback();
    lastWatchEvent = Date.now();
    try {
      var w = fs.watch(QUEUE, { persistent: true }, onWatch);
      watcher = w;
      w.on('error', function () { if (watcher === w) { dropWatch('error'); } });
    } catch (e) {
      watcher = null;
      watchLog('queue watch unavailable; scanning every ' + (FALLBACK_SCAN_MS / 1000) + ' s');
    }
  }
  function safetyTick() {
    if (busy && Date.now() - startedAt > JOB_TIMEOUT_MS) {
      log('TIMEOUT ' + current + ' - no reply from ' + HOST + '; queue released');
      show('idle - watching the queue');
      finish({ id: current }, currentFile, { ok: false, error: 'no reply from ' + HOST + ' within ' + (JOB_TIMEOUT_MS / 60000) + ' min', at: Date.now() });
    }
    if (watcher && Date.now() - lastWatchEvent > WATCH_DEAF_MS) { dropWatch('deaf'); }
    if (!watcher) { armWatch(); }
    scanQueue();
  }
  function beat() {
    engineTick();
    heartbeat();
    beats += 1;
    if (beats % SAFETY_EVERY === 0) { safetyTick(); }
  }
  try {
    ensureQueue();
    recoverOrphans();
    engineTick();
    heartbeat();
    show('idle - watching the queue');
    log('WhyNot Cut ' + BUNDLE + ' (' + HOST + ', ' + ROLE + ', build ' + (BUILD || 'unknown') + ') started; queue ' + QUEUE);
    armWatch();
    scanQueue();
    setInterval(beat, HEARTBEAT_MS);
  } catch (e) {
    show('FAILED to start: ' + e);
  }
})();
