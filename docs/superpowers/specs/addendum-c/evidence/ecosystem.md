# WhyNot Cut 3.0 — End-to-end "one ecosystem" review (Claude · engine · Premiere · After Effects)

| | |
|---|---|
| Date | 2026-10-13 (Cairo night of 12→13 Oct) |
| Code | `release/3.0` @ `6961ccf` + the uncommitted working tree (other sessions are editing it) |
| Mode | Strictly read-only: no edits, no git operations, no processes started or stopped, Adobe apps untouched |
| Point of view | A non-technical video editor who wants "open Premiere → it works", never a terminal command |
| Evidence | `file:line` in the repo (paths relative to `WhyNotCut/`), live files under `C:\Users\LOQ\.whynot-cut\`, the side-session notes `%APPDATA%\Claude\side-session-notes\local_263cabbf…\STATUS-*.md`, Claude Code docs (code.claude.com, cited where used) |

## ملخص ليونس (بالعامية)

النهارده البلاجن جوه بريمير **مش متوصّل بأي حاجة لوحده**: محدش بيشغّل "المحرك" (`reel serve`) غير جلسة تطوير، والأمر اللي البانل بيقولك تكتبه (`reel serve --ensure`) **مش موجود أصلاً** في `reel`. ولما بيتوصّل، البانل بيبان فاضي، وزرار Approve بيرد "لسه مش متعمل"، وClaude بيبان "unknown" لأنه مكتوب كده ثابت في الكود. وClaude نفسه لسه بيبني في بريمير عن طريق الـ CEP Bridge القديم اللي محتاج PlayerDebugMode.
الحل اللي في التقرير: المحرك يشتغل **لوحده** (مع تسجيل الدخول للويندوز + من جوه بريمير/أفتر إفكتس + من Claude)، **بانل واحد** في كل برنامج، كل رسالة خطأ معاها **زرار** بدل أمر، Approve من البانل يوصل لـ Claude **فوراً** وهو شغال، وأزرار "ذكاء" في البانل تشتغل على حساب Claude المتسطّب عندك من غير ما تفتح شات. ولازم شوية حاجات تتعمل **دلوقتي** في تراك Adobe قبل ما يتبني فوق الوضع الحالي (القسم 5).

---

## 1. Integration map — as built today (not as planned)

### 1.1 Picture

```
 Editor
   │ chat (Claude desktop Code tab / CLI)                     │ clicks in Premiere / After Effects
   ▼                                                          ▼
 Claude session ── plugin whynot-cut (INSTALLED: 2.2.1)    UXP "WhyNot Cut" 3.0.0 (dev id)  +  UXP "WhyNot Cut Spike" 0.1.4
   │  hooks: SessionStart(context) PreToolUse(guard)         │  DaemonSource (requester)    │ host link (Premiere ops)
   │         SessionEnd(lease)  — NO `serve --ensure`        │  reads ~/.whynot-cut/bridge/engine.json, ws://127.0.0.1:<port>/session
   │  runs `reel …` (bin/ on PATH)                           ▼                              ▼
   ▼                                              reel serve daemon (only if someone started it by hand;
 reel CLI (engine) ── no `serve` subcommand           `python -m serve` from the repo in dev sessions)
   │  ppro-* / ae-* / motion-build                        │ router: UXP session → UxpAdapter, else → FileQueueAdapter
   ▼                                                      ▼
 file queue ~/.whynot-cut/ppro-queue, ae-queue  ◄─────────┘
   ▼
 CEP "WhyNot Cut Bridge" 3.1.1 (unsigned; PlayerDebugMode=1 in HKCU CSXS.12)
   ├─ hidden "daemon" extension (auto-starts on ApplicationActivate, Node enabled) — works the queue, writes bridge.heartbeat
   └─ visible panel "WhyNot Cut Bridge" (AutoVisible) — in Premiere AND After Effects
```

Two separate roads into Premiere exist, and they do not meet: **Claude's pipeline → file queue → CEP**, and **the
UXP panel → daemon → (UXP host link | file queue)**. Claude never uses the daemon or UXP; the panel never sees
Claude's work.

### 1.2 Link by link

| # | Link | How it starts | How it authenticates | When the other side is missing | Version handshake | What the editor sees |
|---|---|---|---|---|---|---|
| L1 | Editor ↔ Claude session | The editor opens Claude (desktop Code tab or CLI). The installer's last step opens `claude://code/new?q=%2Fwhynot-cut%3Astart` (`whynot-cut/installer/core/wnc_installer/system.py:53`) | claude.ai login of the editor | No Claude: nothing in WhyNot Cut runs except an offline panel | — | — |
| L2 | Claude → `reel` | `bin/` of the **enabled plugin version** is on PATH only for sessions started after install/update (`skills/start/SKILL.md:27-34`) | none (local user) | An older plugin's `reel` first on PATH = G66 (`skills/start/SKILL.md:28-34`) | `reel --version` prints "WhyNot Cut <v>"; every blocked message carries it (`bin/reel` `tag()`) | "restart Claude Code" instructions |
| L3 | Hooks | `hooks/hooks.json`: SessionStart = `session_context.py`, PreToolUse = `guard.py` (matcher `Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit`, line 6), SessionEnd = lease release | — | No Git Bash on Windows → hooks don't run (D8; installer T7.3 provisions it) | Guard heartbeat `guard-ok` (3.0 only; the installed 2.2.1 writes none — `~/.claude/plugins/data/whynot-cut-thewhynot-ai/` is empty) | Session context line "Premiere bridge: alive / not responding (start Premiere)" — **CEP heartbeat only** (`hooks/session_context.py:200-205`, `:359`) |
| L4 | `reel` → CEP bridge | `ppro_bridge.submit` → `cep_queue.submit` file queue (`engine/reel/lib/ppro_bridge.py:144-163`); AE same via `ae_bridge` | File permissions only (queue dir chmod 0700, a no-op on Windows) | Premiere closed → `{"ok":false,"error":"bridge not running"}` (`ppro_bridge.py:154`) | `expect_version=BRIDGE_VERSION` ("3.1.1", `ppro_bridge.py:21`); mismatch → "restart <app>" (`lib/cep_queue.py:125-139`) | Claude relays the sentence |
| L5 | `reel serve` lifecycle | **Nobody, for a real user.** `serve` is not in the `reel` command table (`engine/reel/cli.py:1269-1315`); not in hooks.json; the installer has no login item. The registration lines + hook line were handed to the executor and are still pending (STATUS-adobe.md "Round 2 — registration + hook"). Today's live daemon (pid 123992, started 2026-10-12 22:22 UTC, `logs/serve-audit.log` last line) was started from the repo in a dev session | 256-bit token in `bridge/engine.json` (user-only ACL), Host must be `127.0.0.1:<port>`/`localhost:<port>`, Origin allowlist = exact `file://` (fix 304cc06/14e7b0a after 111 rejected rows on 2026-10-12 18:28-18:52 UTC in `serve-audit.log`) | No daemon → panel "engine not running"; daemon of another version → `ensure` would restart it (`serve/daemon.py` docstring) but nothing calls `ensure` | engine.json `{version, protocol}`; `welcome.daemon_version` | — |
| L6 | UXP panel → daemon (DaemonSource) | Panel load (`adobe/premiere-uxp/src/main.ts`), reads `<os.homedir()>/.whynot-cut/bridge/engine.json` (`src/uxp-transport.ts:60`, `:117`), WS `hello{kind:"panel"}`, polls `snapshot` every 2 s, backoff 1-15 s | token from engine.json in `hello` | Daemon missing → banner "The WhyNot Cut engine is not running. In your Claude session run: `reel serve --ensure`" (`panel-ui/src/render.ts:109-118`, `daemon-source.ts:138`, `i18n/en.json:18-19`) | **Protocol only** (`serve/app.py:365-372`); the panel's `version` is sent but never compared | Offline banner with a terminal command |
| L7 | UXP host link → daemon | Same load; `hello{kind:"uxp", capabilities:[ping,status,open_project,set_player_position,export_frames,close_project_path,clip_components]}` (audit 18:52:40) | token | — | protocol | Host pill "Premiere Pro 26.5.2" |
| L8 | Daemon → CEP queue | Router picks UXP if a connected session has the capability, else `FileQueueAdapter` (`serve/router.py:3-15`) | — | CEP not loaded → ok:false "bridge not running" | CEP name map in `contract/cep.py` | Result toast |
| L9 | Panel → Claude (approve / request changes / rebuild) | Panel sends intents | — | **Always** answered `ok:false` "not implemented in the serve core yet — Use the reel CLI … (e.g. `reel approve` / `reel build`)" (`serve/app.py:70-72`, `:450-451`). Those two command names do not exist (real: `approve-plan`, `ppro-build`). No `panel-requests.json`, no `via:"panel"` anywhere in the engine (grep: 0 hits) | — | Toast with wrong commands |
| L10 | Claude → panel (state) | `snapshot` → `messages.state()` | — | The daemon state is a stub: client "", item "", pipeline [], approval null, `claude:"unknown"` **hard-coded** (`serve/messages.py:76-86`); the panel merges only `connection` (`panel-ui/src/daemon-source.ts:8-10`) | — | Connected but empty panel; Claude pill "unknown" (the owner's "Claude unknown") |
| L11 | After Effects | Same CEP bundle (HostList PPRO+AEFT, `templates/premiere/cep_bridge/CSXS/manifest.xml`) | — | AE closed → `ae-*` "bridge not running" | BRIDGE_VERSION | Unbranded "WhyNot Cut Bridge" status panel (`cep_bridge/index.html`) |
| L12 | Installer → everything | `installer/install.ps1` → core steps; Adobe step installs signed ZXP (none exists yet: components `bridge.cep.zxp = "<release>"`) and the `.ccx` via UPIA | — | Hosts running → "close X, then run the installer again" (`wnc_installer/adobe.py:283-286`) | sha256 of the artefact vs state.json (`adobe.py:261-270`) | Checklist |

### 1.3 What this PC shows right now (live, read-only)

- Claude plugin **installed = 2.2.1** (`~/.claude/plugins/installed_plugins.json`, cache `2.1.1/` and `2.2.1/`): the editor's
  real sessions have **no** `reel serve`, no 3.0 hooks, no panel support at all. Every 3.0 panel success so far was a
  dev session running repo code.
- `bridge/engine.json`: daemon 3.0.0, protocol 4, port 50563, pid 123992 alive (`tasklist`). Premiere is not running.
- UXP (`%APPDATA%\Adobe\UXP\PluginsInfo\v1\premierepro.json`): **two** enabled plugins, "WhyNot Cut Spike" 0.1.4 and
  "WhyNot Cut" 3.0.0 with id `ai.thewhynot.cut.dev`. The repo spike is already 0.1.5 (not installed).
- CEP: `ai.thewhynot.cut.bridge` 3.1.1 with a **visible** panel "WhyNot Cut Bridge" (`AutoVisible` true, manifest lines
  27/30) + hidden daemon; `bridge-config.json` written **inside** the extension (T6.3 wants it out before signing).
- `HKCU\Software\Adobe\CSXS.12\PlayerDebugMode = 1` (the unsigned bridge depends on it).
- `ppro-queue/bridge.heartbeat` = `{version:"3.1.1", host:"PPRO", role:"daemon"}` (stale, Premiere closed).
- `logs/serve.log` empty; `serve-audit.log` 61 KB, mostly the Origin rejections of 2026-10-12.

### 1.4 What happens today in the six situations an editor meets

| Situation | Today |
|---|---|
| S1 Fresh boot, open Premiere first, no Claude | No daemon. Panel: "engine not running — In your Claude session run `reel serve --ensure`". The editor has no Claude session; even with one, that command does not exist (L5). Dead end. The CEP bridge loads (PlayerDebugMode on) but nothing drives it |
| S2 Claude open, Premiere closed | Pipeline runs up to the build; `ppro-build` → "bridge not running"; SessionStart said "start Premiere". OK-ish, but text only |
| S3 Both open | Claude builds through CEP (works, 3.1.1). The UXP panel stays offline (no daemon). With a dev-started daemon: connected, empty, "Claude unknown", Approve → "not implemented" with wrong command names |
| S4 After a plugin/panel update | New Claude session needed for skills/bin (Phase 0 note "Needs you: open a new Claude session"); UXP same-version reinstall silently keeps old files (STATUS-adobe.md lines 66-70); no stale-panel detection (protocol-only check) |
| S5 After Effects | Only the unbranded CEP status panel; motion builds via file queue; no approvals, no engine link |
| S6 No Claude installed / not signed in | Panel offline; no explanation that Claude is the missing piece; the Claude pill cannot know |

---

## 2. Friction and failure list (ranked by harm to a non-technical editor)

Severity: **S1** = blocks the editor or silently disconnects; **S2** = a technical step or a confusing state; **S3** = polish.

| # | Sev | Friction / failure | Evidence | Editor impact | Fix |
|---|---|---|---|---|---|
| F1 | S1 | **Nobody starts the engine daemon.** `serve` is not a `reel` subcommand; no SessionStart `--ensure`; no login item; UXP cannot spawn; the CEP daemon could but doesn't | `cli.py:1269-1315` (no `serve`); `hooks/hooks.json:12-19`; installer has no Run-key/LaunchAgent (grep "Run\\", "LaunchAgent": 0 hits); STATUS-adobe "Lines for the executor" still unapplied | Panel is offline forever for a real user | §3.2: register `serve` (5 lines ready), SessionStart async `--ensure`, per-user login item, CEP daemon spawns a fixed shim, panel "Start engine" button |
| F2 | S1 | **The panel's fix is a terminal command — and it doesn't exist.** Daemon's own fallback text names two non-existent commands | `panel-ui/src/render.ts:109-118` (`reel serve --ensure`, `reel doctor`), `daemon-source.ts:138`, `i18n/en.json:19` "In your Claude session run:"; `serve/app.py:71` "`reel approve` / `reel build`" | «مش فاهم حاجه»; he types into the wrong place or gives up | Never show commands in the panel (Addendum B4.4 already says "no raw codes"); one sentence + one button; commands go only to the log drawer / Copy diagnostics. Fix `NOT_YET_HOW` names now |
| F3 | S1 | **Connected panel is empty and its buttons don't work.** Engine-state part of `reel serve` never written: stub state, intents refused, Claude pill hard-coded "unknown" | `serve/messages.py:76-86` (`"claude": "unknown"`); `serve/app.py:450-451`; `daemon-source.ts:8-10` "The daemon's state is a stub" | The "Claude unknown" he saw; "the plugin does nothing" | §3.5: T6.2b "engine state" (active item, pipeline, approvals, QC, Claude probe) + intents writing evidence files |
| F4 | S1 | **Claude's pipeline bypasses the daemon and UXP.** `ppro-*`/`ae-*` go to the file queue only; T6.2's "every reel host command uses the daemon when it's up" not done; T6.7 not done | `lib/ppro_bridge.py:144-163`; no `engine.json` reader under `lib/` (grep) | Two roads; the UXP plugin only helps the panel; Claude still needs CEP + PlayerDebugMode | T6.7 routing in the engine: `reel` host commands → daemon (`/command` with token) when up, else queue; daemon picks UXP/CEP |
| F5 | S1 | **PlayerDebugMode still required** (the "10 rounds" problem). Bridge unsigned, T6.3 not started (`adobe/cep-bridge/` does not exist; sources still `templates/premiere/cep_bridge`). The start/setup skills still walk the editor through `reg add` in PowerShell | `skills/start/SKILL.md:51-57`; `skills/setup/SKILL.md:41-47`; registry CSXS.12=1; `ppro_bridge.py:126-137` "editor_must_run" | The worst historical friction stays for every new editor | T6.3 signed ZXP is a hard prerequisite of "easy"; then delete the PlayerDebugMode path from start/setup (keep only in setup-doctor as a red diagnosis) |
| F6 | S2 | **Three panels visible** (Spike, WhyNot Cut [dev], WhyNot Cut Bridge), and the CEP status panel also in AE. Nothing removes dev panels; the CEP visible panel is AutoVisible in both hosts | `PluginsInfo/v1/premierepro.json` (spike 0.1.4 + `ai.thewhynot.cut.dev`); `cep_bridge/CSXS/manifest.xml:27,30` | «مش فاهم حاجه»; he opens the wrong panel | §3.3: one panel per app; CEP visible extension only for AEFT; installer/doctor `--fix` removes `ai.thewhynot.cut.spike` and `.dev`; release asserts no spike |
| F7 | S1 | **UPIA traps not handled**: exit 0 on failure (CC desktop not running → "status = -642", exit 0); same version → "Installation Successful" but files not replaced; installer trusts `rc` only, no `/list all` check, no remove-first; UXP manifest version is pinned to `plugin.json` so every dev rebuild is "same version" | STATUS-adobe.md lines 61-70; `wnc_installer/adobe.py:253-257`; `adobe/README.md:77`, `:100` | Silent stale panel ("I updated but nothing changed"), or "installed" when it isn't | §3.4: build stamp in the `.ccx`, remove→install→verify, parse output, start CC desktop or fall back to double-click; daemon detects stale panel by build stamp |
| F8 | S1 | **Panel → Claude does not exist.** No intents, no `panel-requests.json`, no `via:"panel"` approval, SessionStart/`reel next` don't mention the panel; T6.6 not started | grep `panel-requests` / `via=` in `engine/`: 0; `hooks/session_context.py:356-366` | Approving in Premiere does nothing; he must also type in chat | §3.5(a): intents write evidence; `reel next`/SessionStart show them; a plugin **monitor** wakes the running session |
| F9 | S2 | **Status sources disagree.** SessionStart and `reel ppro-status` look only at the CEP heartbeat ("start Premiere") even when the UXP panel is connected; doctor knows nothing about UXP, the daemon, or Claude | `session_context.py:200-205`; `lib/onboard.py` (no uxp/serve); daemon `_state` uses UXP first (`serve/app.py:474-490`) | Claude says "start Premiere" while Premiere is open | One status function in the engine (daemon `/status` + CEP heartbeat + UXP sessions) used by doctor, SessionStart, ppro-status and the panel |
| F10 | S2 | **New Claude session after install/update; old `reel` on PATH (G66)**; the editor's PC still runs 2.2.1 | `skills/start/SKILL.md:27-34`; PROGRESS Phase 0 "Needs you"; `installed_plugins.json` 2.2.1 | Repeated "restart Claude Code"; mixed versions | Installer finishes by opening a **new** Claude session (deep link, §3.6); hooks/skills call `"${CLAUDE_PLUGIN_ROOT}/bin/reel"` by absolute path; panel pill shows "Claude plugin 2.2.1 — update" |
| F11 | S2 | **Restarts done by the editor, by instruction.** Installer refuses while hosts run ("close X, then run the installer again"); CEP needs a host restart after install; UXP after UPIA; nothing is staged for later | `wnc_installer/adobe.py:283-286`, `:309`; `ppro_bridge.py:130-137` | Several Premiere restarts + opening Creative Cloud by hand | Stage panel updates and apply them automatically when Premiere is closed (engine watches); the panel shows one "Restart Premiere to finish the update" card |
| F12 | S2 | **Setup is spread over three places and repeated.** Installer installs engine + panels; `/whynot-cut:start` re-does engine (`reel setup`), bridge and PlayerDebugMode; the panel has no first-run | `skills/start/SKILL.md:35-57`; `skills/setup/SKILL.md:20-47` | Duplicate questions, technical steps after a "successful" install | §3.6: installer = machine; panel first-run = checklist + "Set up my first client"; start skill = client + preferences only, reading `state.json`/doctor |
| F13 | S2 | **Version zoo.** Product 3.0.0; CEP bridge 3.1.1 (higher than the product); spike 0.1.x; UXP "dev" id; protocol 4; installed plugin 2.2.1; `ppro_bridge.install` keeps a "newer" bridge, so a product-numbered 3.0.x bridge would be refused | `ppro_bridge.py:21`, `:99-104`; heartbeat 3.1.1; `premierepro.json` | "Which version do I have?" — support pain | One product version shown everywhere; bridge/build stamps only in diagnostics; replace the "newer bridge kept" rule by a build-family rule |
| F14 | S2 | **Deep link to open Claude is unverified.** Installer uses `claude://code/new?q=…`; Claude docs document `claude://code/new` with required `ssh_host` (q alone UNCERTAIN), and `claude-cli://open?q=…&cwd=…` for the terminal (handler registers only after the first interactive session) | `system.py:53`; code.claude.com/docs/en/desktop, /deep-links | Installer's last step may open nothing; the editor doesn't know what to type | Measure in T7.9; fallback screen with a big "Copy" of `/whynot-cut:start` + the Claude app opened plainly |
| F15 | S2 | **Security holes to close before intents ship.** Guard matcher excludes Read/Grep/Glob, so Claude can read the token in `engine.json`; no guard patterns for WS/HTTP to 127.0.0.1; hello `kind:"panel"` is self-declared; UXP manifest `network.domains: "all"` (plan said loopback only) | `hooks/hooks.json:6`; `guard.py` (no `engine.json`/`127.0.0.1` rules); `serve/app.py:381-389`; `adobe/premiere-uxp/plugin/manifest.json` | A Claude mistake could approve its own plan through the panel channel | §3.8 |
| F16 | S2 | **Engine home vs panel discovery.** The panel only reads `~/.whynot-cut/bridge/engine.json`; custom homes rely on the daemon's discovery copy (fine), but the SessionStart pointer may blank an installer-chosen `engine_home` (installer Request 10) → daemon/engine on the wrong home | `uxp-transport.ts:60`; STATUS-installer.md "Request 10" | Silent "engine not running" after choosing D:\ for the engine | Apply Request 10; the shim (§3.2) reads the same pointer; E13 test |
| F17 | S3 | **"Reveal folder"/open MP4 pops an Adobe consent dialog each time** (1.8-32 s, not remembered) | `docs/adobe/uxp-parity.md` row H3 | Odd dialogs | Route "Reveal/Open" through the engine (`os.startfile`/`open`) — no consent dialog; keep `shell.openPath` as fallback |
| F18 | S3 | **After Effects has no real panel** (B-T4/T6.8 pending) | `cep_bridge/index.html` | AE feels like a different product | B-T4 on the same kit, named "WhyNot Cut" |
| F19 | S3 | **Origin rule is one exact string.** A future UXP that sends another Origin → panel says "Reinstall the WhyNot Cut panel" (wrong advice) | `serve/security.py` ALLOWED_ORIGINS_EXACT; `daemon-source.ts:600-603` | Another "Host/Origin" scare | Daemon audits unknown origins and returns a typed reason; panel says "WhyNot Cut needs an update for this Premiere version" + Copy diagnostics; doctor flags it |
| F20 | S3 | **Dev artefacts on the editor's machine**: spike config/auto-run file, `_leaked-by-tests` queue folder, two plugin caches | `~/.whynot-cut/uxp-spike/`, `ppro-queue/_leaked-by-tests-2026-10-11/` | Clutter in diagnostics | `doctor --fix` tidy list (never client data) |

### Top 10 (for the summary)
F1 engine never started · F2 commands instead of buttons (and non-existent ones) · F3 connected-but-empty panel, "Claude unknown" · F4 two roads, Claude bypasses UXP/daemon · F5 PlayerDebugMode still required · F7 UPIA silent failures / same-version stale panel · F8 no panel→Claude path · F6 three visible panels · F11 manual restarts · F12/F10 setup repeated over installer/start/new session.

---

## 3. Target "one ecosystem" design (buildable within 3.0)

### 3.0 Principles
1. **The engine is a service**, not something Claude starts: running whenever the editor is logged in; every surface heals it.
2. **One product, one version, one panel per app** ("WhyNot Cut"). Bridge/spike/protocol are internal words.
3. **No command ever on the editor's screen.** One sentence + one button. Commands live in the log drawer / Copy diagnostics.
4. **Claude is the brain, the panel is the hands and the approvals.** Approving, viewing, rebuilding and single-shot AI
   actions work from the panel; long multi-step edits stay visible in a Claude session.
5. **Security stays:** token, loopback, Host/Origin, guard, and Claude can never approve through the panel.

### 3.1 Target picture

```
                           ┌──────────── per-user login item (default ON) ─────────┐
 installer ─ writes ─► ~/.whynot-cut/bin/wnc-engine(.cmd) "shim" ─► reel serve --ensure (detached)
                           ▲            ▲                 ▲                ▲
                 CEP daemon ext   SessionStart hook   "Start engine"    every `reel` host command
                 (Node spawn,     (async, --ensure)   button (URL       (lazy ensure)
                  Premiere + AE)                       scheme / Claude)
                                                │
 reel serve (127.0.0.1, token) ── engine state: active client/item, pipeline, approvals, QC, Claude probe
   │  routes ALL host ops (from Claude's reel AND from the panel): UXP if connected+capable, else CEP queue
   │  intents from the panel → evidence files (plan-approval.json via:panel, panel-requests.json)
   │  AI jobs (closed list) → local `claude -p` (tool-less) | API key | disabled
   ▼
 Premiere: ONE UXP panel "WhyNot Cut" (+ hidden CEP daemon for red ops & engine start)
 After Effects: ONE CEP panel "WhyNot Cut" (same panel-ui kit)
   ▲
 running Claude session ◄── plugin monitor `reel watch` prints "Editor approved C0239 in Premiere" → Claude continues
```

### 3.2 Engine availability: one shim, four starters

**The shim (new, T7.1 + T6.2):** `~/.whynot-cut/bin/wnc-engine.cmd` (Windows) / `wnc-engine` (macOS), written by the
installer and refreshed by every SessionStart. It never depends on PATH or on the versioned plugin cache path:
- reads `~/.whynot-cut/plugin-root.json` `{root, version, at}` — written by the installer and by SessionStart from
  `CLAUDE_PLUGIN_ROOT` (fallback: `~/.claude/plugins/installed_plugins.json`, entry `whynot-cut@thewhynot-ai`);
- runs `<runtimes/<current>/Scripts/pythonw.exe | bin/python> -s -B -P <root>/engine/reel/serve/__main__.py --ensure --quiet`
  (the module path `serve/daemon.py` already uses; `ensure` is idempotent, single-instance by `serve.lock`, and replaces
  a daemon of another version).

**Starters (all converge on the shim; any one is enough):**
1. **Per-user login item — installed by default** (no admin): Windows `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\WhyNotCutEngine`
   = the runtime's `pythonw.exe` + shim script (no console flash; rewritten whenever `current` changes in `reel setup`
   / `reel update`); macOS `~/Library/LaunchAgents/ai.thewhynot.cut.engine.plist` (`RunAtLoad`, `--foreground`,
   `KeepAlive` so launchd restarts it). Cost: one idle Python (~30 MB, measured `tasklist` 31,600 K). Installer
   question: none (strongest default per the owner's rule); doctor shows it; uninstall removes it.
2. **CEP hidden daemon extension** (already auto-starts on `ApplicationActivate` in Premiere *and* AE, Node enabled,
   `manifest.xml:44-56`): on start and every 30 s while `engine.json` is missing or its pid is dead →
   `child_process.spawn(<shim from ~/.whynot-cut/bridge/config.json>, [], {detached:true, windowsHide:true}).unref()`.
   Fixed path, no arguments from the network. Lands with T6.3 (before signing).
3. **SessionStart** (`hooks.json`): `{"type":"command","async":true,"command":"bash \"${CLAUDE_PLUGIN_ROOT}/bin/reel\" serve --ensure --quiet >/dev/null 2>&1 || true"}`
   (`async` hooks exist per code.claude.com/docs/en/hooks; the sync form from STATUS-adobe also works, ≤ ~1 s). Plus
   **lazy ensure** in every `reel` host command (it needs the daemon for routing anyway, F4).
4. **Panel "Start the engine" button** (manual fallback when 1-3 failed, e.g. login item disabled and the bridge not
   loaded): UXP `shell.openExternal("whynotcut://engine/start")` → per-user URL protocol
   `HKCU\Software\Classes\whynotcut` (macOS: `CFBundleURLTypes` in a tiny helper app) → shim. Needs
   `launchProcess.schemes += "whynotcut"` and a spike measurement (consent dialog?). If unavailable: the button opens
   Claude instead (SessionStart starts the engine).

**Panel offline behaviour:** while offline, poll `engine.json` every 1 s (cheap) and connect immediately when it appears;
show "Starting WhyNot Cut…" for the first 10 s (starters 1-2 usually win), then "WhyNot Cut isn't running" + **[Start]**.

### 3.3 One visible panel per app
- **Premiere:** only UXP "WhyNot Cut" under Window ▸ UXP Plugins. Release id `ai.thewhynot.cut` (Adobe-distributed id
  after H5); never ship `.dev`. The CEP bundle in Premiere = the hidden daemon only: the visible panel extension's
  HostList becomes **AEFT only** (it still processes red ops — T3b mono pairs, C1 caption track, O1 createProject —
  and starts the engine).
- **After Effects:** the CEP visible panel renamed **"WhyNot Cut"** (Window ▸ Extensions (Legacy) ▸ WhyNot Cut) on the
  panel-ui kit (B-T4). Bundle name "WhyNot Cut", not "Bridge".
- **Spike:** dev-only. `tools/release.py` asserts no spike `.ccx`/id in `dist/`; installer and `reel doctor --fix`
  run `UPIA /remove` for `ai.thewhynot.cut.spike` and `ai.thewhynot.cut.dev` once the release id is installed
  (read `%APPDATA%\Adobe\UXP\PluginsInfo\v1\premierepro.json` — a plain JSON file — to know what is there).
- **Developer machine:** `adobe/tools/dev-install.mjs` = UPIA `/remove` → `/install` → verify, so dev builds never
  stay stale and never need a version bump.

### 3.4 Self-healing
- **One status model** (engine-computed, shown identically in panel, `reel doctor`, SessionStart):
  `engine` · `premiere link` (UXP session / CEP heartbeat) · `after effects link` · `claude` (§3.5c) · `panel up to date`.
  Each red state = one sentence + one button: Start engine · Restart Premiere · Open Claude · Sign in to Claude ·
  Update WhyNot Cut · Copy diagnostics.
- **Version/staleness handshake:** `release.py` writes `build.json {product, build, sha}` into the `.ccx` and the ZXP,
  and `whynot-cut/adobe/expected.json` into the plugin. Panel `hello.client` adds `build`. The daemon compares with
  `expected.json` and returns `welcome.update = {panel: "ok"|"stale"|"newer"}`. Stale → card "WhyNot Cut was updated —
  restart Premiere to load it" (and the staged reinstall below). The CEP heartbeat's version mismatch
  (`cep_queue.py:125-139`) is surfaced the same way.
- **UPIA hardening (installer + `reel update` + doctor --fix):** start Creative Cloud desktop if not running (UPIA needs
  it); when the installed folder's `build.json` differs → `/remove <id>` then `/install`; success only if the output
  contains "Installation Successful" **and** `/list all` shows the id/version **and** the installed `build.json` sha
  matches; else amber with "double-click WhyNotCut-Premiere-3.0.0.ccx" as the one step.
- **Staged updates instead of "close Premiere and run again":** if Premiere/AE is running, write
  `~/.whynot-cut/pending/adobe.json`; the daemon polls (30 s, only while pending) for both hosts closed and applies
  it, or the login-item start applies it before Premiere launches. The panel shows "Update ready — it installs the next
  time Premiere is closed".
- **Restart prompts by the panel:** the panel cannot quit Premiere (no API measured — add to spike 0.1.6). It shows the
  card; the engine saves nothing on its own. When CEP was just installed and no heartbeat appears within 60 s of a
  Premiere start, the panel says "Restart Premiere once to finish installing".
- **Auto-reconnect:** keep DaemonSource's backoff (1-15 s) + the engine.json poll above. A command cut by a reconnect
  ends `ok:false` with **[Try again]**.
- **Doctor:** new sections Adobe panels (UXP ids/versions from PluginsInfo, spike/dev presence, CEP signed?, heartbeat
  age, UXP session live), Engine service (login item, shim, daemon status/version, sessions), Claude (§3.5c).
  `--fix`: remove dev panels, restart a wrong-version daemon, rewrite the shim/login item, re-run a staged update.

### 3.5 Panel ↔ Claude, both ways

**(a) Panel → running Claude session**
1. **Engine state (new T6.2b):** every `reel` writer command updates `~/.whynot-cut/state/active.json`
   `{client_root, item, stage, session_id, claude_pid, at}`; the daemon reads it plus the item's evidence files
   (`plan.json`, `plan-approval.json`, `qc-*.json`, previews, `ppro-build-result.json`) to fill `PanelState`
   (client · item, pipeline strip, approval card with fingerprint, QC tiles). No new truth: the panel shows what the
   evidence files say.
2. **Intents write evidence, never chat:** `approve` → the same code path as `reel approve-plan` with
   `{by:"editor", via:"panel", editor_name, at, fingerprint}` (fingerprint must equal the current plan's, T1.4);
   `request_changes` → append to `<item>/panel-requests.json` + `NEEDS-YOU.md`; `rebuild` → if the plan is approved and
   unchanged the engine runs `ppro-build` itself (no Claude needed), else it becomes a request.
3. **Delivery to Claude, three layers:**
   - *Always (no live session):* SessionStart + `reel next` print "Yunus approved C0239 in Premiere at 14:02" and
     pending requests (T6.6 text, T3.4).
   - *Live, buildable now:* a **plugin monitor** (`monitors/monitors.json`, `when: "always"`; code.claude.com plugin
     manifest reference) running `reel watch --panel` — a long-lived command that prints one line per new panel event
     (approval, request, rebuild result). Claude Code feeds each line into the running interactive session, so
     "approve in Premiere → Claude continues" works without typing. Interactive sessions only; Windows needs Git Bash
     (already guaranteed by T7.3). Inside a gate, the lead skill can instead run the Monitor tool on
     `reel wait-approval --item <ID>` (30-min max per watch).
   - *Channels (P2, opt-in):* research preview; a community plugin's channel needs
     `--dangerously-load-development-channels` every session unless allowlisted; Team/Enterprise orgs must enable
     channels; Desktop Code tab support undocumented (code.claude.com/docs/en/channels, /channels-reference). Not a
     3.0 default. Keep the event format identical so a channel can replace the monitor later.
4. **No live session:** the panel shows "Claude will pick this up when you open it" + **[Open Claude]**.

**(b) "AI actions" in the panel, on the editor's own Claude**
- The **engine** (never the panel) runs a closed list of single-shot text jobs (`ai_jobs`: Kalam correction FR-6,
  caption fix, title/hook suggestions, publish copy draft). Command:
  `claude -p --safe-mode --tools "" --disallowedTools "mcp__*" --no-session-persistence --max-turns 1 --output-format json --json-schema <file>`
  with the prompt on stdin, `cwd` = an empty temp dir under the engine home, `CLAUDE_PLUGIN_*` scrubbed from env,
  timeout + tree kill (`lib/parallel.kill_tree`). All flags exist (cli-reference); `--safe-mode` disables plugins,
  hooks, MCP and CLAUDE.md, so the guard does not run but nothing can run either (no tools). Output is
  schema-validated, then the code gates apply (Kalam FR-9 faithfulness, FR-10 `rules.enforce`). The result is shown
  for the editor to apply.
- **Backends, in order:** (1) local Claude Code CLI (found with `tools/find_claude.py` rules; uses the editor's
  `/login`); (2) an Anthropic API key the editor saved (owner-only file; `claude -p --bare` with `ANTHROPIC_API_KEY`
  in the child env, or the SDK — Kalam "api" backend); (3) none → button disabled: "Needs Claude — install Claude and
  sign in" **[Open guide]**. WhyNot Cut never offers a claude.ai login itself (Agent SDK policy:
  code.claude.com/docs/en/agent-sdk/overview). Open point: the docs don't address a third-party app spawning the
  user's CLI — WhyNot Cut ships *as a Claude Code plugin*, but get written clearance from Anthropic before release
  (risk register), with the API-key backend as the fallback.
- **Multi-step work ("Make my edit", "Set up a client", "Edit the new videos") is not headless:** the panel writes a
  panel request and, if a session is live, the monitor delivers it; otherwise **[Open Claude]** opens Claude on the
  prompt (`claude-cli://open?q=/whynot-cut:autopilot&cwd=<client>` for CLI users; Desktop link per T7.9
  measurement). The editor watches and steers. **D5 revised:** "The panel never launches an agentic Claude. The engine
  may run tool-less `claude -p` for the closed list of single-shot text jobs."

**(c) A real "Claude" pill** (daemon probe, cached 5 min, refreshed on click)

| Check | How | Pill text |
|---|---|---|
| CLI installed | `find_claude` rules (PATH, desktop-bundled CLI, npm/native) | "Claude not installed" **[Open guide]** |
| Signed in | `claude auth status` (JSON by default; exit 0 = logged in, `authMethod`) | "Sign in to Claude" **[Open Claude]** |
| Plugin version | `~/.claude/plugins/installed_plugins.json` `whynot-cut@thewhynot-ai` vs product | "Claude has WhyNot Cut 2.2.1 — update" **[Update]** (runs the installer's claude step) |
| Session active | `active.json` age + `claude_pid` alive + 3.0 guard heartbeat `guard-ok` | "Working on C0239 (2 min ago)" / "Ready" / "Waiting for you" (NEEDS-YOU count) |

`ClaudeState` in `panel-ui/src/source.ts:22-23` grows from `active|idle|unknown` to
`not_installed|signed_out|plugin_outdated|ready|working|waiting`; "Never a login state" in that comment changes —
it is a local probe of the editor's own CLI, not a login offered by WhyNot Cut.

### 3.6 Setup in one place
1. **Installer = the whole machine** (engine, model, Git Bash, Claude plugin, signed CEP, UXP with verify, fonts,
   **shim + login item + URL scheme**, removes dev panels, starts the daemon, writes `state.json`). Final screen:
   "Open Premiere → Window ▸ UXP Plugins ▸ WhyNot Cut" + opens a **new** Claude session on `/whynot-cut:start`
   (solves "new session needed"; deep link verified in T7.9, fallback = copy box).
2. **Panel first run** (if Premiere is opened first): a checklist from the daemon's status — Engine ✓, Premiere link ✓,
   Claude ✓ (signed in, plugin 3.0.0), Clients folder ? → one button **[Set up my first client]** → opens Claude on
   `/whynot-cut:start`.
3. **`/whynot-cut:start` = client + preferences only.** It reads `reel doctor` (which reads `state.json`) and skips
   every green item; engine install and bridge install only for the zip-without-installer path; PlayerDebugMode
   removed from the normal path.
4. **One checklist definition** (ids + AR/EN strings) shared by installer screen (B-T5), panel first-run and start skill.

### 3.7 Naming and versions
- The editor sees **"WhyNot Cut 3.0.0"** everywhere: panel header/log drawer, AE panel, installer, `reel --version`,
  doctor, Claude pill, Copy diagnostics. Protocol 4, CEP bundle/build stamps, UXP build → diagnostics only.
- CEP bundle version follows the product from 3.0.0 on; `ppro_bridge.install`'s "installed bridge is newer, kept it"
  (`ppro_bridge.py:99-104`) changes to: bundle id family + `build.json`; 3.1.x is treated as the 2.x bridge and replaced.
- Names: panels "WhyNot Cut"; the daemon "WhyNot Cut engine"; no "Bridge", "Spike", "dev", "serve" in the UI.

### 3.8 Security (kept intact, tightened where the ecosystem adds surface)
- Unchanged: 127.0.0.1 bind, token in user-only `engine.json`, Host check, exact Origin allowlist, size/rate caps, no
  run-script endpoint, schema-validated commands, audit log.
- **Guard (T6.6):** add `Read|Grep|Glob` to the PreToolUse matcher for `~/.whynot-cut/bridge/**` (token) and refuse
  Bash/PowerShell patterns that open WebSocket/HTTP to `127.0.0.1`/`localhost` with `/session`, `/approve`,
  `/request`, or read `engine.json`; block `reel approve-plan --via panel` from Claude.
- **Intents only from `kind:"panel"` sessions**; `kind` is self-declared, so the guard is the control for Claude
  mistakes and the audit + SessionStart line ("approved in Premiere at 14:02") makes any forged approval visible to the
  editor. Threat model unchanged: mistakes, not a malicious local process.
- **AI jobs:** tool-less, empty cwd, stdin prompt, no secrets in argv/logs, schema-validated, applied only by an editor
  click; never able to approve or call `reel`.
- **Spawning:** CEP spawns only the fixed shim path from `bridge/config.json` (written by the installer, outside the
  signed bundle); the URL handler accepts only `whynotcut://engine/start`.
- **UXP manifest:** `network.domains` back to the loopback entries (re-measure; "all" today) ; `launchProcess` scheme
  list = `file` + `whynotcut` only.
- **Login item:** per user, no elevation, removed by uninstall; doctor shows it.

---

## 4. Ecosystem test plan (scripted, Windows live; macOS when H6)

Precondition for every live run: PlayerDebugMode **off** (Gate 6 rule), installed **release** artefacts (not dev),
a `whynot-test` client. Timings measured with the panel's log drawer timestamps + `serve-audit.log`.

| ID | Scenario | Steps | Pass criteria |
|---|---|---|---|
| E1 | Fresh boot → Premiere first | Reboot; log in; open Premiere; open WhyNot Cut panel; no Claude | ≤ 10 s after the panel opens: Engine ✓, Premiere ✓, Claude pill shows a precise state; **no command text on screen**; audit shows `started` by the login item |
| E2 | Login item off → CEP starts the engine | Disable the Run entry; stop daemon (`reel serve --stop`); open Premiere | Daemon started by the CEP extension ≤ 15 s; panel connects by itself |
| E3 | After Effects first | Same as E2 with AE | Engine started; AE "WhyNot Cut" panel connected; motion status visible |
| E4 | Engine dies mid-session | Kill daemon pid while the panel is open, then mid-`export_frames` | Panel "Reconnecting…" then ✓ ≤ 20 s (a starter restarts it); the cut command ends `ok:false` with **[Try again]**; no zombie job in the queue |
| E5 | Claude open, Premiere closed | `/whynot-cut:edit` to the build stage | One sentence "Open Premiere to build"; opening Premiere → build continues on retry; Claude's build goes through the daemon (audit row with `session` of the reel client) and UXP when connected |
| E6 | Approve in the panel, live session | At the plan gate click Approve in Premiere | `plan-approval.json` `{by:editor, via:panel, fingerprint==plan}`; the running session receives the monitor line and continues ≤ 5 s with no typing |
| E7 | Approve with no session | Approve, then open a new Claude session | SessionStart shows "approved in Premiere at HH:MM"; `reel next` = build |
| E8 | Request changes | Text "shorter hook" in the panel | Appears in `reel next`, NEEDS-YOU badge +1; live session gets it via monitor |
| E9 | Claude closed → AI button | Quit Claude; run "Fix captions" (Kalam correction) | Runs via `claude -p` tool-less ≤ 60 s; result shown for apply; `claude -p` stream contains no tool use; faithfulness gate stats in log |
| E10 | Claude signed out / not installed / API key | `claude auth logout`; then hide the CLI; then save an API key | Pill "Sign in to Claude" [Open Claude]; then "Claude not installed" with disabled AI buttons; then AI works via API key; WhyNot Cut never shows a claude.ai login |
| E11 | Plugin outdated in Claude | Keep Claude plugin 2.2.1, install 3.0 panel | Pill "Claude has WhyNot Cut 2.2.1 — update"; [Update] fixes it; next session `reel --version` 3.0.0 |
| E12 | Update → stale panel | Install a new build while Premiere is open | "Update ready — installs when Premiere is closed"; after closing, staged UPIA runs; next open: installed `build.json` = new; a deliberately old panel is flagged "restart Premiere" within 5 s of connecting |
| E13 | Same-version rebuild | Dev: rebuild 3.0.0, `dev-install` | remove→install→verify; installed `build.json` sha = new |
| E14 | UPIA failure | Quit Creative Cloud desktop; run installer | Installer starts CC or reports amber with one step; never reports ok on "status = -642" |
| E15 | One panel per app | Upgrade this PC (spike + dev + Bridge present) | Window ▸ UXP Plugins: exactly one "WhyNot Cut"; Premiere Window ▸ Extensions (Legacy): none of ours; AE: one "WhyNot Cut" |
| E16 | Custom engine home + Arabic/space username | Install to `D:\WhyNotCut`, user "يونس Test" | Panel connects via discovery copy; pointer not blanked by SessionStart (Request 10) |
| E17 | Security | Claude: `Read ~/.whynot-cut/bridge/engine.json`; Bash python WS hello kind panel + approve; `reel approve-plan --via panel` | All blocked by the guard with a clear reason; audit shows nothing accepted |
| E18 | Two Claude sessions + panel | Two sessions on two clients | Pill shows the item of the active lease; approvals go to the right item; lease rules unchanged |
| E19 | Non-technical walkthrough | B-T7 tasks + "engine not running" + "Claude signed out" in Arabic | Every task finished from the panel without typing any command; time per task recorded; zero "مش فاهم" moments logged |
| E20 | Uninstall | `-Uninstall` | Login item, URL scheme, shim, daemon, panels removed; client folders untouched |

Automated (CI-able): shim resolution (pointer → installed_plugins fallback); Run-key/LaunchAgent writer (sandboxed);
`build.json` compare; UPIA output parser; `claude auth status` parser; `ai_jobs` argv builder (no secrets, exact flags);
intents → evidence files (fingerprint mismatch refused); `reel watch --panel` line format; guard patterns (E17);
panel-ui test "no `reel ` / backtick command in any non-log string".

---

## 5. What must change in the current 3.0 plan

### 5.1 NOW (Adobe track / executor, before more is built on the current shape — avoids rework)
1. **Register `reel serve` + SessionStart ensure** (executor; the 5 lines + hook in STATUS-adobe are ready) — T6.2.
   Every later item depends on it.
2. **Kill command texts in the panel** (B-T1/B-T2): replace `OFFLINE_COMMAND` (`render.ts:109-118`), `START_HOW`
   (`daemon-source.ts:138`), `offline.hint`, and fix `NOT_YET_HOW` names (`serve/app.py:71`). Kit gets the
   "status line + one fix button" pattern and the first-run checklist screen.
3. **Hello carries `build`; daemon compares with `expected.json`** (T6.2/T6.5 contract) — add the field to
   `session.schema.json` now, before more panels exist.
4. **Intents contract final** (`approve{item, fingerprint, editor_name}`, `request_changes{item, text}`,
   `rebuild{item, replace_edited}` → `reply{ok, how}`) and the engine-state shape (`active.json`), so B-T2 screens bind
   to real data — new **T6.2b "engine state + intents"**.
5. **CEP manifest split before signing** (T6.3): visible panel AEFT-only and renamed "WhyNot Cut"; daemon extension
   gets the shim spawn; `bridge-config.json` out of the bundle; bundle version = product. Signing after this, once.
6. **`adobe/tools/dev-install.mjs`** (remove→install→verify) and stop installing dev ids alongside release ids on
   Yunus's PC; decide the release UXP id/name now (H5 can stay pending; the name must not be "dev").
7. **Spike 0.1.6 measurements:** `shell.openExternal("whynotcut://…")` + consent; any premierepro quit/restart API;
   `network.domains` loopback list works; UXP hide/show events.

### 5.2 Mapped plan changes

| Plan item | Change |
|---|---|
| D5 | "The panel never launches an agentic Claude; the engine may run tool-less `claude -p` for a closed list of single-shot text jobs (Kalam FR-6 et al.). Live panel→session delivery = plugin monitor in 3.0; channels P2." |
| D13 / Addendum B | Panel shows no commands (B4.4 made explicit); product version only; names "WhyNot Cut" in both apps |
| R10 | Add "no manual restarts except one 'Restart Premiere' card; no Creative Cloud opening by hand" |
| T6.2 | + login-item-independent `ensure` from three starters; lazy ensure in `reel` host commands; offline engine.json poll |
| **T6.2b (new)** | Engine state (`active.json`, evidence → PanelState), intents → evidence files, Claude probe, `reel watch --panel`, `reel wait-approval`, `ai_jobs` runner |
| T6.3 | Manifest split, shim spawn, product version, build.json, `config.json` outside the bundle; then sign |
| T6.5 / B-T2 | First-run checklist, status line + fix buttons, Claude pill states, update/stale card, NEEDS-YOU badge from `NEEDS-YOU.md`; Reveal/Open via the engine (no consent dialog) |
| T6.6 | Guard: Read/Grep/Glob on `bridge/**`, WS/HTTP patterns, `--via panel` block; threat model adds AI jobs and the shim/URL scheme |
| T6.7 | Moves earlier: all `reel` host commands route via the daemon (UXP if capable, else CEP) — one road |
| T6.8 / B-T4 | AE panel "WhyNot Cut" on the kit, connected to the daemon (not just the queue) |
| T6.9 | Add E1-E20 (§4) to Gate 6 |
| T6.10 | start/setup/help/status/premiere-craft rewritten: no PlayerDebugMode on the normal path; panel-first wording |
| T3.4 | SessionStart: panel approvals/requests, async ensure, write `plugin-root.json`; plugin `monitors/monitors.json` (`reel watch --panel`, `when: always`) |
| T3.10 | `help`/`status` mention the panel and the three verbs; `reel board` feeds the panel too |
| Addendum A #10 / T6.14 | Kalam FR-6 runs through the shared `ai_jobs` runner (same flags, same gates); API-key backend shared |
| T7.1 step 7 | UPIA hardening (CC running, remove-first, output parse, `/list all`, build.json verify); remove spike/dev ids |
| **T7.1 step 7b (new)** | Shim + login item (Run key / LaunchAgent) + `whynotcut://` URL scheme + start the daemon |
| T7.1 step 12 | Deep link measured (`claude://code/new` q-only is undocumented; `claude-cli://open?q=&cwd=`); copy-box fallback; always a **new** session |
| T7.4 | Staged Adobe updates applied when hosts are closed; `reel update` rewrites the login item when `current` changes; daemon restart on version change |
| T7.5 | Doctor sections: Adobe panels, Engine service, Claude (CLI/auth/plugin version/session) + `--fix` actions |
| T7.6 | `release.py`: build.json in `.ccx`/ZXP, `expected.json`, assert no spike/dev id, product version in every manifest |
| T7.8 | Uninstall removes login item, URL scheme, shim, stops the daemon |
| T7.9 | Clean-account run includes E1, E14, E16 |
| Risk register | "Third-party spawning of the user's Claude CLI — policy not documented" → ask Anthropic; fallback API key |
| B-T7 | Usability tasks add "engine not running", "Claude signed out", "panel out of date" — each solved by one click |

### 5.3 Not in 3.0 (backlog with trigger)
- Claude Code channel (trigger: WhyNot Cut channel allowlisted or Desktop support documented).
- AE UXP (trigger: AE 27 public UXP; deadline Dec 2028, unchanged).
- Headless agentic "Make my edit" from the panel (trigger: a sanctioned background-session API usable by plugins).
