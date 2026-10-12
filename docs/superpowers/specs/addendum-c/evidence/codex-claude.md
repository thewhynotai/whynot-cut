# WhyNot Cut on OpenAI Codex, and "AI actions" from the Premiere panel

Research date: 2026-10-13. Sources are official docs unless marked. Most `developers.openai.com/codex/*` URLs now 308-redirect to `learn.chatgpt.com/docs/*`, and the OpenAI docs call the desktop app the "ChatGPT desktop app". Codex docs moved and changed a lot in 2026, so check them again before building.

Labels: **[V]** = verified on an official page today. **[U]** = not verified (secondhand, inferred, or the docs say nothing). **[C]** = official pages contradict each other.

What is on disk now (`whynot-cut/`): 25 skills, **19** agent files (the brief says 20), `hooks/hooks.json` (a PreToolUse guard on `Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit`, plus SessionStart and SessionEnd), `bin/reel` and `bin/reel.cmd`, and `userConfig` (`clients_root`, `engine_home`). Skill frontmatter uses `allowed-tools`, `argument-hint` and `user-invocable`. Agent frontmatter uses `tools`, `model`, `color` and `skills`. `guard.py` (1,795 lines) tells subagents apart by the Claude-only `agent_type` field in the PreToolUse input.

---

## Part 1: OpenAI Codex (CLI, IDE extension, ChatGPT desktop app, cloud)

### 1. Skills: yes, the same SKILL.md format [V]
- **Where skills load from:** `.agents/skills` in the current directory, in each parent up to the repo root, and at the repo root. Also `$HOME/.agents/skills` for the user, `/etc/codex/skills` for admins, and the skills bundled with Codex. Symlinked skill folders are followed. Skills with the same `name` are not merged. https://learn.chatgpt.com/docs/build-skills
- **Frontmatter:** only `name` and `description` are required or documented. Optional Codex metadata goes in a separate `agents/openai.yaml` with `interface` (display name, icon, default prompt), `policy.allow_implicit_invocation` (default true) and `dependencies.tools` (MCP servers). [V]
  - Our Claude-only fields (`allowed-tools`, `argument-hint`, `user-invocable`) are not documented for Codex. They are probably ignored, and `allowed-tools` is certainly not enforced [U].
- **Progressive disclosure:** at the start Codex sees only each skill's name, description and path, and loads the full SKILL.md only when it picks the skill. The list is capped at 2% of the context window (8,000 characters if the window size is unknown), with descriptions shortened first. [V] With 25 skills that have long descriptions, some descriptions will be cut. Keep them short.
- **How a skill is called:** explicitly with `$skill-name` or the `/skills` picker in the CLI and IDE (`@` in ChatGPT), or implicitly when the task matches the description. Codex does not create a slash command per skill the way Claude Code creates `/whynot-cut:edit`. [V]
- **Enable or disable:** `[[skills.config]] path=… enabled=false` in `~/.codex/config.toml`. [V]
- **Custom prompts** (`~/.codex/prompts`) are deprecated in favour of skills. https://learn.chatgpt.com/docs/custom-prompts [V]. A third-party blog says they were removed in v0.117 [U].

### 2. Plugins and marketplaces: yes, and Claude-compatible in parts [V]
- **Plugin layout** (https://developers.openai.com/plugins/build/plugins):
  - A portable `plugin.json` at the plugin root, with `$schema` `agent-plugins.org/schemas/1.0.0`. The older `.codex-plugin/plugin.json` still works as an overlay.
  - `skills/<name>/SKILL.md`, an optional `mcp.json` (`mcpServers` with `type: "streamable-http"`, `url`, and auth types none, oauth, mixed or api_key), and an optional `hooks/hooks.json`.
  - OpenAI-specific settings go under `extensions.com.openai` (`hooks`, `apps`, `onboardingSkill`, `interface`).
- **What a plugin cannot carry:** subagents and commands are not plugin components in Codex. [V by absence]
- **Marketplace file:** `$REPO_ROOT/.agents/plugins/marketplace.json`, or `~/.agents/plugins/marketplace.json`. Codex also reads the legacy file `$REPO_ROOT/.claude-plugin/marketplace.json`. [V]
  - Source types: `local`, `url`, `git-subdir`, `npm`.
  - `policy.installation`: `AVAILABLE`, `INSTALLED_BY_DEFAULT` or `NOT_AVAILABLE`.
- **Install and update:**
  - `codex plugin marketplace add owner/repo [--ref main] [--sparse path]`, then `list`, `upgrade [name]` and `remove`. [V]
  - In the CLI, `/plugins` installs. In the desktop app, use the Plugins tab. After installing, start a new session.
  - Installed plugins are cached in `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/`. Enable a plugin per repo with `[plugins."name@marketplace"] enabled = true` in `.codex/config.toml`.
  - Plugins are **not supported in the IDE extension**. https://learn.chatgpt.com/docs/plugins [V]
- **Claude compatibility:** "OpenAI accepts legacy and Claude-compatible manifests". Codex sets `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` next to its own `PLUGIN_ROOT` and `PLUGIN_DATA`, so existing hook scripts can still find their files. [V] The docs never say that `.claude-plugin/plugin.json` itself is read as a manifest [U]. Ship a `.codex-plugin/plugin.json` overlay to be safe.
- **Public directory** ("Submit your Claude Code plugin to OpenAI", https://developers.openai.com/plugins/guides/submit-claude-plugin.md) [V]:
  - The portal converts the Claude manifest.
  - Agents and commands must be turned into skills.
  - **Hooks must be removed.** Plugins that have hooks can only be "installed manually in Codex desktop".
  - `userConfig`, monitors, channels, outputStyles and `dependencies` are not supported.
  - Public MCP servers must be remote HTTPS with OAuth 2.1, and local `.mcpb` bundles are rejected.
  - Conclusion: WhyNot Cut cannot go into OpenAI's public directory with its guard. Ship it through our own git marketplace instead.
- **[C] Hooks in plugins:** the plugin build page says plugin hooks are "supported only for manually installed Codex desktop plugins". The hooks page says plugin hooks load whenever the plugin is enabled and are reviewed in the CLI with `/hooks`. Test this on the CLI before relying on it.

### 3. Subagents: yes, in a different format and with no tools allowlist [V]
https://learn.chatgpt.com/docs/agent-configuration/subagents.md
- **Format:** one TOML file per agent, in `~/.codex/agents/` or `.codex/agents/` (project).
  - Required: `name`, `description`, `developer_instructions`.
  - Optional: `model`, `model_reasoning_effort`, `sandbox_mode`, `mcp_servers`, `skills.config`. Anything left out is inherited from the parent.
  - **There is no `tools` allowlist.** The closest control is per-agent `sandbox_mode = "read-only"`.
  - Built-in agents are `default`, `worker` and `explorer`.
- **Spawning:** Codex spawns subagents when asked directly, or when AGENTS.md or skill instructions ask it to delegate.
- **Concurrency:** capped by `agents.max_concurrent_threads_per_session` (`max_threads` is the legacy name). Older third-party sources give default 6 and `max_depth` 1 [U].
- **Sandbox inheritance:** subagents inherit the parent's sandbox. In the CLI they also inherit live overrides such as `--yolo`, even when the custom agent file sets something else.
- **Approvals:** "Subagents can't approve on their own." In a non-interactive run, an action that needs new approval fails back to the parent. [V]
- **Support:** CLI, desktop app and IDE. ChatGPT Work (cloud) has limits: no local sandbox or approval control.
- **Plugins cannot ship agents.** The agent TOML files must be installed into `.codex/agents/` (project) or `~/.codex/agents/` by our installer. [V by absence]

### 4. Hooks, sandbox and policies: blocking is possible; folder protection is partly config-only
**Hooks** (https://learn.chatgpt.com/docs/hooks) [V]:
- **Events:** PreToolUse, PermissionRequest, PostToolUse, Pre/PostCompact, UserPromptSubmit, SubagentStart/Stop, Stop, SessionStart, SessionEnd, Interrupt.
- **Config:** `hooks.json` or `[hooks]` in `~/.codex/` or `<repo>/.codex/`. Project hooks load only when the project is trusted. Hooks are on by default (`[features] hooks`; `codex_hooks` is a deprecated alias).
- **Blocking:** PreToolUse can block with `hookSpecificOutput.permissionDecision: "deny"`, with legacy `{"decision":"block"}`, or with exit code 2. `"ask"` is parsed but unsupported: the hook is marked failed and **the tool call goes ahead**.
- **Coverage:** shell (`Bash` and unified `exec_command`), `apply_patch` (matchable as `Edit` or `Write`; input in `tool_input.command` as **patch text**, not a `file_path`), and MCP and local function tools are all covered. Hosted tools such as WebSearch are not.
- **Trust:** every non-managed hook, including plugin hooks, is **skipped until the user trusts it** with `/hooks`. The trust is hash-based, so each plugin update needs a new review.
- **Windows:** a hook can set a `commandWindows` override.
- **SessionStart context:** SessionStart can return `additionalContext`. Our session-context hook carries over.
- **Subagent identity:** the PreToolUse input has **no `agent_type` or `agent_id`**. Only SubagentStart and SubagentStop carry them, and subagent hooks use the parent's `session_id`. **So our "subagents never approve" rule cannot be enforced by agent identity in Codex.**
- OpenAI's own limit: "Treat tool hooks as a useful guardrail, not a complete enforcement boundary."

**Sandbox and approvals** (https://learn.chatgpt.com/docs/agent-approvals-security) [V]:
- **Sandbox modes:** `read-only`, `workspace-write` (the default for Auto; network off), and `danger-full-access`. `--yolo` is short for `--dangerously-bypass-approvals-and-sandbox`.
- **Approval policies:**
  - `on-request` and `never` work.
  - `untrusted` is **retired** and "can prevent either client from starting". Use `[projects."<path>"] trust_level = "untrusted"` instead.
  - Granular policy: `approval_policy = { granular = {…} }`.
  - `approvals_reviewer = "auto_review"` hands approvals to a reviewer agent.
- **Always read-only:** `.git`, `.agents` and `.codex` inside writable roots.
- **Network:** `[sandbox_workspace_write] network_access`, plus a domain proxy. `allow_local_binding` defaults to **false, which blocks loopback**. This matters because `reel` talks to the Premiere and AE bridge on 127.0.0.1.

**Permission profiles** (beta, https://learn.chatgpt.com/docs/permissions.md) [V]. These are config-level read-only folders:
```toml
default_permissions = "whynot-client"
[permissions.whynot-client]
extends = ":workspace"
[permissions.whynot-client.filesystem.":workspace_roots"]
"." = "write"
"assets" = "read"
"data" = "read"
```
- Precedence is deny > write > read.
- Supported on macOS, Linux, WSL and native Windows. On Windows, MXC is recommended and needs Win 11 24H2 or 25H2. The "unelevated" fallback is weaker and does not support deny-read.
- Profiles cannot be combined with the older `sandbox_mode` settings.
- They govern only sandboxed commands. They do not cover MCP, web or Codex service traffic.
- Whether `apply_patch` edits are covered is **[U]**. The page only talks about "sandboxed commands". Keep the PreToolUse guard as a second layer.
- They only help when the client folder is a workspace root (Codex started in the client folder). If Codex runs from the clients root, the paths must be listed per client [U: path forms beyond `":workspace_roots"` not checked].

**Exec-policy rules** (experimental, https://learn.chatgpt.com/docs/agent-configuration/rules) [V]:
- Starlark `prefix_rule(pattern=[…], decision="allow"|"prompt"|"forbidden", justification=…)` in `rules/*.rules` next to any config layer. Project rules load only when trusted.
- Test with `codex execpolicy check`.
- Rules decide what may run **outside** the sandbox. Compound shell scripts with redirects or variables are matched as one unit.
- Useful as `prefix_rule(["reel"], "allow")`, so `reel` can reach loopback and the engine home. That means **the engine itself must enforce the source protections.**

### 5. MCP [V]
https://learn.chatgpt.com/docs/extend/mcp.md?surface=cli
- **Config:** `[mcp_servers.<name>]` in `~/.codex/config.toml`, or in a trusted project's `.codex/config.toml`.
- **Transports:** stdio uses `command`, `args` and `env`. Streamable HTTP uses `url`, `bearer_token_env_var`, `http_headers` or `env_http_headers`.
- **OAuth:** the default for HTTP, with `codex mcp login <name>` and `logout`.
- **Other keys:** `enabled_tools` and `disabled_tools`, `default_tools_approval_mode` (auto, prompt, writes or approve), `required`, startup timeout.
- **Add from the CLI:** `codex mcp add <name> --env K=V -- <cmd>`.
- **Magnific (HTTP) fits as-is.** In a plugin, declare it in `mcp.json`. Users can tune it with `[plugins."whynot-cut".mcp_servers.magnific]`.

### 6. Headless mode and auth [V], terms [U]
https://learn.chatgpt.com/docs/non-interactive-mode
- **`codex exec` flags:**
  - `--json` (JSONL events)
  - `--output-schema <file>`
  - `-o/--output-last-message`
  - `--sandbox` (the **default is read-only**)
  - `--skip-git-repo-check` (a git repo is otherwise required)
  - `--ephemeral` (no rollout files)
  - `--ignore-user-config`, `--ignore-rules`
  - `codex exec resume`, prompt from stdin (`-`)
  - `--full-auto` is deprecated.
- **Auth** (https://learn.chatgpt.com/docs/auth):
  - `exec` reuses the saved login. That can be ChatGPT (plan credits) or an API key (API pricing); `CODEX_API_KEY` works per invocation.
  - The docs say "API keys are still the recommended default for automation". ChatGPT-managed auth in CI is "advanced", for trusted runners, and "Do not use this workflow for public or open-source repositories".
  - Credentials live in `~/.codex/auth.json` or the OS keyring.
- **Third-party products:**
  - OpenAI's **"Sign in with ChatGPT"** (https://developers.openai.com/siwc, https://developers.openai.com/siwc/request-client-id) lets an app use a user's ChatGPT plan, including via the Codex app-server. It is "currently offered to a select group of commercial partners" (waitlist form). The open-source token-sharing flow has preview limits: no image generation, hosted MCP or file search. https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations
  - **Not found:** any OpenAI statement that a closed-source commercial product may launch the user's own installed `codex exec` under their ChatGPT login. A developer asked exactly this on 2026-09; the question is unanswered. https://github.com/openai/codex/discussions/48837 [U]
  - Practical answer: technically trivial, but the terms are unclear. Make it an explicit opt-in that the user starts ("use my Codex"), recommend an API key, and ask OpenAI before marketing it.

### 7. AGENTS.md and slash commands [V]
https://learn.chatgpt.com/docs/agent-configuration/agents-md
- **Load order:**
  1. Global: `~/.codex/AGENTS.override.md` or `AGENTS.md`.
  2. Each directory from the project root down to the cwd adds at most one file: `AGENTS.override.md`, then `AGENTS.md`, then names in `project_doc_fallback_filenames`.
  3. The files are joined root-down, so the nearest file wins.
- **Cap:** `project_doc_max_bytes` defaults to **32 KiB**.
- **Commands:** custom prompts and slash commands are deprecated; skills replace them.
- **Lead playbook:** the `edit` playbook can be summarised into an AGENTS.md (under 32 KiB) placed in the clients root, with the detail kept in skills.

### 8. Windows and macOS
- **Desktop app:** macOS from Feb 2026; Windows from 2026-03-04, native PowerShell with a Windows sandbox (TechRadar/Engadget, https://www.engadget.com/ai/openai-brings-its-codex-coding-app-to-windows-195345429.html).
- **CLI and IDE extension on Windows:** official, https://learn.chatgpt.com/docs/windows/windows-sandbox
  - Sandbox options: MXC (recommended; Win 11 24H2+), or the legacy elevated and unelevated sandboxes. WSL2 uses the Linux sandbox; WSL1 is unsupported from 0.115.
  - Windows 11 is the baseline. Windows 10 is "best effort" (1809+).
  - Child processes stop when the foreground command exits, so detached servers die. Our `reel` engine and bridge must not be started by Codex expecting them to persist.
- **CLI install:** standalone installer, npm or Homebrew. https://learn.chatgpt.com/docs/codex/cli [V]
- **Linux desktop app:** not available [U].

### 9. What carries over, what does not, and the minimum adapter

| Component | Carries over? | Adapter |
|---|---|---|
| 25 SKILL.md | Mostly. Same format, `name`/`description` read | Build step copies them to `skills/`, removes or ignores Claude-only fields, and rewrites "Claude", "Agent tool" and `/whynot-cut:x` wording to neutral or `$x`. Keep descriptions short (2% budget). |
| 19 agents/*.md | **No.** Different format, no tools allowlist, plugins can't ship agents | Generate `.codex/agents/*.toml` (`developer_instructions` = body; `sandbox_mode="read-only"` for read-only agents; map or omit `model`). The installer writes them to the project or user folder. |
| Slash commands / `user-invocable` | No | `$skill` calls. Document them in the help skill. |
| hooks.json guard | Partly. Hooks exist and can deny, but need user trust, are a "guardrail" only, have no `agent_type`, and `apply_patch` sends patch text | Add a Codex input shim to `guard.py`: parse `*** Add/Update/Delete File:` paths, accept `exec_command`, set `commandWindows`. **Move role rules (approve-plan, verdicts) into the engine.** |
| Read-only `assets/`, `data/` | Yes, by config (beta): permission profile entries `"assets"="read"`, `"data"="read"` | Shipped in project `.codex/config.toml` (trusted projects only), plus the engine-side check. |
| SessionStart context | Yes (`additionalContext`) | Same script. |
| `bin/reel` on PATH | No auto-PATH equivalent [U] | Skills call `${PLUGIN_ROOT}`-relative paths, or the installer puts `reel` on PATH. Add an exec-policy `allow` rule for `reel`. |
| Magnific HTTP MCP | Yes | `mcp.json` in the Codex plugin. |
| `userConfig` | **No** (not expanded by OpenAI) | The engine reads its own config (`~/.whynot-cut/config.json`). The `start` skill writes it. |
| Monitors, channels, statusline, outputStyles | No | Not needed for Codex v1. |
| Marketplace | Yes. Codex reads `.claude-plugin/marketplace.json` and also `.agents/plugins/marketplace.json` | Add `.agents/plugins/marketplace.json` and `.codex-plugin/plugin.json` in the same repo. |

**Effort (one developer who knows the repo), rough:**
- Skill and agent generator plus build: 3–4 days.
- AGENTS.md lead playbook and wording pass: 2–3 days.
- Guard shim plus moving role and approval enforcement into the engine: 4–5 days. This also benefits Claude.
- Permission profile, exec-policy rules, loopback and network settings for `reel` on Win and macOS: 3–4 days.
- Installer and update path (`codex plugin marketplace add`, `/hooks` trust step, agents copy): 2 days.
- End-to-end runs of edit, podcast and motion with Codex on Windows and macOS, plus evals: 5–8 days.
- **Total ≈ 4 weeks.**

**Risks (medium-high):**
- Prompts and agents are tuned and evaluated on Claude: Arabic transcript proofreading, medical and religious review, QC judgment.
- Codex subagents have no tool allowlist.
- The beta and experimental features (permission profiles, rules) and the hook trust UX may change.
- Codex docs moved domains this year.
- [C] Hooks support for CLI plugins is unclear.

**Must stay Claude-only for now (safety and quality):**
- **Full autopilot or batch runs.** Hooks are guardrails only, `ask` is unsupported, and agent identity is missing.
- **Medical and religious review** (`medical-reviewer`, `claim-checker`) unless Codex passes the same evals.
- **Approval and evidence gates** stay human-only for both backends (see below).
- **Channel- and monitor-based panel integration**, which is a Claude-only feature.

---

## Part 2: Claude-side features for "one ecosystem"

### 1. Channels: research preview [V]
https://code.claude.com/docs/en/channels and https://code.claude.com/docs/en/channels-reference
- **What a channel is:** a stdio MCP server that declares `capabilities.experimental['claude/channel']` and pushes `notifications/claude/channel` (`content`, plus `meta` that becomes `<channel …>` attributes).
- **Two-way:** add a reply tool.
- **Permission relay:** the server declares `claude/channel/permission`, receives `…/permission_request` (`request_id`, `tool_name`, `description`, `input_preview`) and answers `…/permission` with `allow` or `deny`. It covers Bash, Write and Edit prompts. Trust and MCP-consent dialogs are not relayed.
- **Running one:**
  - Each session must opt in with `--channels plugin:<name>@<marketplace>`.
  - During the preview only allowlisted plugins register: the claude-plugins-official set, or an org's `allowedChannelPlugins`.
  - Our own channel needs `--dangerously-load-development-channels plugin:whynot-cut@…` on every launch, with a full-screen confirmation. It is ignored with `-p` or the SDK.
  - Team and Enterprise orgs: blocked until an Owner sets `channelsEnabled`. Pro and Max users without an org skip these checks.
  - Needs claude.ai or Console auth. Not available on Bedrock, Vertex or Foundry.
- **Packaging:** the plugin manifest `channels: [{server, displayName, userConfig}]`. Getting onto the official allowlist needs an Anthropic partner contact.
- **Verdict:** a great fit technically (the panel posts events into the editor's open session, and permission prompts can show in the panel), but too much friction for 3.1.

### 2. Headless `claude -p` [V]
https://code.claude.com/docs/en/cli-reference and https://code.claude.com/docs/en/headless

**Flags that exist:**
- `--safe-mode` (no CLAUDE.md, skills, plugins, hooks or MCP; auth works normally)
- `--bare` (**requires `ANTHROPIC_API_KEY`**; never reads OAuth or the keychain)
- `--restricted` (v2.1.248+; removes command tools; loads only managed settings and `--settings`)
- `--tools ""` (built-ins off; does **not** remove MCP tools, so add `--disallowedTools "mcp__*"`)
- `--json-schema` together with `--output-format json`, which returns `structured_output`
- `--no-session-persistence`, `--model`, `--max-budget-usd`, `--max-turns`
- `--permission-mode dontAsk`, `--permission-prompts none` (v2.1.259+)
- `--system-prompt-file`, `--strict-mcp-config`

Without `--bare` or `--safe-mode`, `-p` runs the hooks and `.mcp.json` of the folder it starts in, with no trust dialog. Always start it from an empty temp folder.

**Locked-down text call (subscription login):**
```
claude -p --safe-mode --tools "" --disallowedTools "mcp__*" --permission-mode dontAsk --permission-prompts none --no-session-persistence --model sonnet --max-turns 1 --output-format json --json-schema <schema> --system-prompt-file <action.txt>   (stdin = input, cwd = empty temp dir)
```
With an API key, use `--bare` in place of `--safe-mode`.

**Which login it uses:** `-p` uses whatever login the CLI has, subscription or API key (`claude auth status` shows `authMethod`). Bare mode is API-key only.

**Rules for third-party apps:**
- https://code.claude.com/docs/en/agent-sdk/overview says: "Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK."
- Branding: "{YourAgentName} Powered by Claude" or "Claude Agent" are allowed. "Claude Code" naming and look-alike visuals are not.
- https://code.claude.com/docs/en/legal-and-compliance: developers "should use API key authentication… Anthropic does not permit third-party developers to offer Claude.ai login… or to route requests through Free, Pro, or Max plan credentials on behalf of their users." It still allows "an end user… signing in to the unmodified Claude Code binary with their own Claude subscription."
- Pro and Max limits "assume ordinary, individual usage".
- **[U] Whether a plugin's own engine may spawn `claude -p` with the user's subscription for panel buttons:** in my reading this is too close to "routing requests through plan credentials". Default to the user's own API key for one-shot calls, or get written approval.

### 3. Desktop deep links [V]
- **Desktop app:** `claude://code/new?q=<prompt>&folder=<abs path>` (`prompt` is an alias for `q`; `file` is not supported yet). https://support.claude.com/en/articles/14729294-open-claude-desktop-with-a-link
  - **The folder parameter is supported now.** Desktop always shows a confirmation dialog (link folders count as untrusted).
  - The prompt is **prefilled, not sent**, and is truncated at about 14,000 characters.
  - Works on macOS and Windows; the article also lists Linux [C with the desktop docs].
- **Terminal:** `claude-cli://open?cwd=<abs>&q=<≤5,000 chars>` (or `repo=owner/name`) opens a terminal session, prefilled, with a warning line. https://code.claude.com/docs/en/deep-links
  - The handler is registered after the first interactive prompt on that machine.
  - On Windows: `Start-Process "claude-cli://…"`.
- **From the CLI:** `claude --desktop` opens Desktop on the cwd (v2.1.285+, subscription).

### 4. Other new pieces that help a panel and session ecosystem [V unless marked]
- **Plugin monitors** (`experimental.monitors` or `monitors/monitors.json`; https://code.claude.com/docs/en/plugins-reference):
  - A shell command runs in the background for the whole interactive session, and each line it prints reaches Claude as a notification.
  - `when: "on-skill-invoke:<skill>"` starts it only when a given skill first runs.
  - Interactive sessions only (not `-p`). Not on Bedrock, Vertex or Foundry, or with telemetry or non-essential traffic disabled. On Windows it needs Git Bash, which we already require.
  - No `${user_config}` access.
  - Agent-started Monitor-tool watches can use a WebSocket but deny private and loopback addresses. A plugin monitor *script* can poll our loopback engine.
  - **Of the session hooks found, this one has the least friction, and it does not need a research-preview flag.**
- **`userConfig`** (types `string|number|boolean|directory|file`, `sensitive`, `options`, `/config` rows), the plugin `settings.json` (`agent`, `subagentStatusLine`) and `bin/` on PATH are all already used or usable.
- **Background agents and agent view:** `claude --bg "<task>"` returns a session id. Also `claude agents --json`, `claude logs/attach/stop <id>`. https://code.claude.com/docs/en/agent-view [not opened in detail]. The panel could offer "run the full edit in the background"; the same terms caveat as `-p` applies [U].
- **Remote Control:** drive a local session from claude.ai or mobile (`claude --rc`). It has no public API for local processes, so it is not a panel bridge. https://code.claude.com/docs/en/remote-control
- **`claude import codex`** (v2.1.213+) imports Codex config into Claude. It is the reverse direction, but shows that the configs map onto each other.

---

## Recommendation

### Codex support, in phases
**3.1: "Codex (preview)", about 4 weeks**
1. **One repo for both.**
   - Add `.codex-plugin/plugin.json`, `mcp.json` (Magnific) and `.agents/plugins/marketplace.json`.
   - A build script generates the Codex skill copies (neutral wording, `$skill` names) and `.codex/agents/*.toml` from the same sources. The Claude files stay the master copy.
   - Install with `codex plugin marketplace add thewhynot/whynot-cut`.
2. **Engine-side enforcement first.** This helps Claude too and is the real safety boundary.
   - `reel` refuses writes under any client's `assets/` and `data/`.
   - `reel approve-plan` and verdict commands require a human approval token that only the Premiere panel's approve button (or a typed confirmation in the main CLI) creates.
   - The hooks then become a second layer on both platforms.
3. **Codex config shipped in the clients root `.codex/`.**
   - A permission profile with `assets` and `data` set to `read` (beta).
   - An exec-policy rule `prefix_rule(["reel"], "allow")` so the engine can reach loopback and the engine home.
   - The guard hook with the Codex input shim and `commandWindows`.
   - An AGENTS.md lead playbook under 32 KiB.
   - The installer tells the user to run `/hooks` and trust the hooks once.
4. **Scope:** status, help, setup checks, podcast reels-plan, publish copy, transcript correction and the story-editor draft, all run under human gates. The Premiere build goes through `reel`, the same engine.
5. **Ship gate:** keep the "preview" label until the existing `evals/` suites pass on Codex on Windows and macOS.

**Later (3.2+):** the full `edit` pipeline and motion mode on Codex once evals match. An `openai.yaml` interface for the ChatGPT desktop app. Re-test plugin hooks on the CLI once the [C] contradiction is resolved.

**Never, or not until OpenAI changes things:**
- A listing in OpenAI's public directory (hooks are not allowed there).
- Unattended autopilot on Codex (no agent identity in hooks, `ask` unsupported).
- Medical or religious review on Codex without its own eval pass.
- Selling or bundling users' ChatGPT plan usage without a "Sign in with ChatGPT" partner agreement.

### "AI actions" from the Premiere panel

Typed actions only, for example `suggest_titles`, `rewrite_caption`, `shorten_statement`, `explain_qc_fail`, `pick_broll_terms`. Each has a JSON input and a JSON-Schema output. The model returns **data only**. The engine validates it and applies it through existing `reel` commands. The editor sees a diff and clicks apply.

**Three backends behind one engine interface (`reel ai-action`):**
1. **Claude, live session (default when a session is open):**
   - The WhyNot Cut plugin declares a **monitor**, `reel actions --watch`. It prints one line per queued panel action.
   - Claude in the editor's own interactive session handles the action with full plugin context, skills and guard hooks, then writes back with `reel action-result <id>`. The panel receives it over the existing loopback WebSocket.
   - Compliant: the user runs the unmodified Claude Code with their own login. No preview flag is needed.
   - Upgrade path: a WhyNot Cut **channel** with permission relay to the panel, opt-in for Pro and Max power users only, until it is allowlisted.
2. **One-shot without a session:**
   - Claude: `claude -p` locked down as in Part 2.2, from an empty temp folder, stdin input, schema output, `--max-turns 1` and a budget cap. **Default to the user's own `ANTHROPIC_API_KEY` (`--bare`).** Offer subscription mode only after written approval from Anthropic.
   - Codex: `codex exec --sandbox read-only --ephemeral --skip-git-repo-check --ignore-rules --output-schema s.json -o out.json` in an empty temp folder. Recommend `CODEX_API_KEY`. Allow "use my ChatGPT login" only as an explicit user opt-in with disclosure, and ask OpenAI first.
   - No tools, no MCP, a timeout (30–60 s) and a size cap on input.
3. **Hand-off (zero risk, always available):** a button that opens `claude://code/new?folder=<client>&q=<prefilled task>` (Desktop) or `claude-cli://open?cwd=…&q=…` (terminal). The editor reviews and presses Enter.

**Safety constraints, for both backends:**
- AI actions can never approve a plan, record a QC verdict, delete, or write client sources. Those stay human clicks in the panel, recorded by the engine.
- Transcript and footage text is untrusted input (prompt injection), so use schema-only outputs and no tools.
- The loopback WebSocket needs a per-session random token and an Origin check, because local web pages can reach `127.0.0.1`.
- Per-backend consent toggles in the panel, showing which account and billing will be used.
- Cost and time caps, and a log of every action (prompt hash, backend, model, result) in the project's evidence folder.
- Branding: "WhyNot Cut AI, powered by Claude" or "… with Codex". Never "Claude Code" as a feature name.

### Not verified / open questions
- Whether a closed-source plugin may launch the user's subscription-logged-in `claude -p` or `codex exec` for panel buttons. Ask Anthropic (sales or partner contact) and OpenAI (SIWC form or discussion #48837).
- [C] Codex plugin hooks on the CLI versus desktop-only.
- Whether permission profiles cover `apply_patch` edits.
- Whether Codex ignores the Claude-only skill frontmatter cleanly.
- Codex subagent default concurrency and depth.
- Linux support of Claude Desktop deep links.
- A Codex equivalent of `bin/` on PATH.
