# WhyNot Cut 3.0 — Addendum C: one ecosystem (Claude · engine · Premiere · After Effects)

| | |
|---|---|
| Date | 2026-10-13 |
| Requested by | Yunus, in his words: «راجع مشاكل الربط مع كلود وبريمير عشان يكونوا كلهم ايكوسيستم واحد فيه سهوله في الاستخدام والتنفيذ يكون سهل جدا» ("review the connection problems between Claude and Premiere so it's all one ecosystem, easy to use, and very easy to run") |
| Evidence | `evidence/ecosystem.md`: the integration map as built, 20 ranked frictions with file:line, the target design, 20 test scenarios E1–E20, plan mapping. `evidence/codex-claude.md`: Claude headless, monitors, channels, deep links, policy |
| Commit | The executor commits this folder to `docs/superpowers/specs/addendum-c/` (single writer) |

## C0. The problem in one line
Claude and the Premiere panel use **two separate roads** into Premiere that never meet:
- **Claude's road:** `reel` → file queue → the unsigned CEP bridge, so PlayerDebugMode is still needed.
- **The panel's road:** UXP → `reel serve`. Nothing starts it for a real user. The panel is empty, its buttons say
  "not implemented", "Claude unknown" is hard-coded, and its error text tells the editor to type a command.

Setup also happens in three places, and three panels are visible. Details and evidence are in
`evidence/ecosystem.md` §1–§2.

## C1. The target (binding for 3.0)
1. **One road.** Every `reel` host command goes through `reel serve`, which routes to UXP when it can and to CEP
   otherwise. The file queue stays only as the engine's internal fallback (T6.7 moves earlier).
2. **The engine is always on.** One launcher script in `~/.whynot-cut/bin` and four starters:
   - a per-user login item, on by default;
   - the hidden CEP extension, which starts with Premiere and After Effects and can launch the launcher;
   - an async SessionStart hook + a lazy ensure inside every `reel` host command;
   - the panel's "Start" button via the `whynotcut://` scheme (spike 0.1.6 decides).
3. **One visible panel per app,** named "WhyNot Cut" in both.
   - Premiere: the UXP panel only.
   - After Effects: the CEP panel, AEFT-only, renamed.
   - Spike and dev ids are removed by the installer and `doctor --fix`; `adobe/tools/dev-install.mjs` handles dev
     installs.
4. **No commands on screen, ever.** Every problem shows one sentence and one fix button. Commands live only in the log
   drawer. A panel-ui test fails on any `reel …` or backtick command string outside the log.
5. **Panel ↔ Claude both ways (new T6.2b):**
   - the engine fills the panel from the evidence files (`active.json` → PanelState);
   - panel intents (approve, request changes, rebuild, run a tool) are written as evidence files: approve becomes
     `plan-approval.json {by:editor, via:panel, fingerprint}`;
   - a running Claude session hears them live through a **plugin monitor** (`reel watch --panel`);
   - a new session hears them through SessionStart and `reel next`. Claude channels stay P2.
6. **A real Claude pill**, built from `find_claude`, `claude auth status`, `installed_plugins.json` and session
   activity. States: not installed · sign in · plugin outdated · ready · working · waiting for you.
7. **AI buttons in the panel** are a closed list of single-shot text jobs: fix captions, suggest titles, summarise.
   They return JSON, the engine validates it, and the editor presses Apply. The engine runs them, never the panel.
   Backends in this order:
   1. **The open Claude Code session** via the monitor. This is the editor's normal use of their own account.
   2. **The editor's Anthropic API key** (`userConfig` sensitive), running a locked-down
      `claude -p --safe-mode --tools "" --disallowedTools "mcp__*" --no-session-persistence --max-turns 1 --json-schema …`,
      or the SDK.
   3. **A deep link** that opens Claude with the task prefilled, for the editor to send.

   **Using the editor's subscription login for one-shot `claude -p` is opt-in and off by default**, until Anthropic
   confirms in writing that a third-party tool may do it (new **H14**). The docs say third-party products may not
   route requests through Free/Pro/Max credentials on behalf of users. Kalam's FR-6 runs through the same runner and
   rules: its idea is unchanged, only the default backend moves. WhyNot Cut never shows a claude.ai login. Branding
   is "WhyNot Cut · Powered by Claude".
8. **Self-healing:**
   - a build stamp in every panel package, checked against `expected.json` by the daemon, so a stale panel shows
     "Restart Premiere" as one card;
   - UPIA hardened: start Creative Cloud, remove-first, parse the output, check `/list all`, verify the build stamp,
     because UPIA can exit 0 on failure and skips same-version files;
   - Adobe updates staged and applied when the hosts are closed;
   - restarts done by Claude under the standing permission (test projects or nothing unsaved).
9. **Setup in one place.** The installer sets up the whole machine and opens a **new** Claude session. The panel's
   first run shows a checklist with a "Set up my first client" button. `/whynot-cut:start` only does the client and
   preferences and skips everything already green. No PlayerDebugMode on the normal path.
10. **One version everywhere:** "WhyNot Cut 3.0.0". The CEP bundle follows the product version, so the
    "newer bridge kept" rule changes.
11. **Security stays intact and gets tighter:**
    - the guard covers Read, Grep and Glob on `~/.whynot-cut/bridge/**` (the token);
    - it blocks Claude's WS/HTTP calls to the daemon and `--via panel` approvals;
    - AI jobs have no tools and run from an empty working dir;
    - the CEP extension may launch only the fixed launcher;
    - the UXP manifest network list goes back to loopback.

## C2. Do NOW (before more panel screens are built), from ecosystem.md §5.1
1. Register `reel serve` + the SessionStart ensure (executor).
2. Remove the command texts from the panel; fix the daemon's fallback text that names commands which don't exist.
3. The hello message carries `build`, and the daemon compares it with `expected.json` (schema field now).
4. Final intents contract + engine-state shape (T6.2b), so B-T2 screens bind to real data.
5. CEP manifest split (AE-only visible panel named "WhyNot Cut"; daemon + launcher), config outside the bundle, product
   version. Sign once, after this.
6. `dev-install.mjs`; stop installing dev ids next to release ids; decide the release UXP id/name now.
7. Spike 0.1.6: the `whynotcut://` link + consent, any Premiere quit/restart API, the loopback `network.domains` list.

## C3. Plan changes (full table: `evidence/ecosystem.md` §5.2)
- **D5 rewritten:** the panel never launches an agentic Claude. The engine may run tool-less single-shot text jobs
  (C1.7).
- **New T6.2b:** engine state + intents + Claude probe + `reel watch --panel` + `reel wait-approval` + `ai_jobs`
  runner.
- **T6.7 moves earlier.**
- **T7.1 step 7b (new):** launcher + login item + URL scheme.
- **Other tasks extended** as in §5.2: T3.4, T3.10, T6.2, T6.3, T6.5/B-T2, T6.6, T6.8, T6.10, T7.1, T7.4, T7.5,
  T7.6, T7.8, T7.9, B-T7.
- **Gate 6 adds scenarios E1–E20,** and every one must pass. Examples:
  - fresh boot with Premiere first and no Claude;
  - the engine killed mid-job;
  - approve in the panel with a live session (Claude continues within 5 s without typing);
  - Claude signed out or not installed;
  - stale panel after an update;
  - one panel per app;
  - an Arabic-named user with a custom home;
  - the guard blocking token reads and self-approval;
  - a non-technical walkthrough with zero «مش فاهم» moments;
  - uninstall.
- **Risk register adds:** a policy risk for the subscription CLI from third-party tools (H14, API-key fallback);
  UPIA silent failures.

## C4. Human items
- **H14:** written confirmation from Anthropic (support or partner contact) on whether WhyNot Cut may run the editor's
  own logged-in `claude` CLI for one-shot text jobs. Until then that backend stays opt-in and off.
- H5 (release UXP id) is still pending, but the release **name** must be decided now (C2.6). Default: "WhyNot Cut".
