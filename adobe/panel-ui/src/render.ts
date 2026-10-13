// Pure rendering: render(state, strings, ui) -> HTML string. Every dynamic value goes through esc().
// Paths and timecodes are wrapped in <bdi dir="ltr"> so they stay left-to-right inside Arabic text. Commands are never
// shown (Addendum C1.4): a text from the engine or a host goes through neutralise() (src/commands.ts) first.
// Markup is flexbox-friendly and uses only simple classes (UXP and CEP render the same CSS).
import { neutralise } from "./commands.ts";
import { exportFramesAction, openProjectAction, rebuildInput, renderReviewAction } from "./actions.ts";
import type { BuildInfo } from "./diagnostics.ts";
import { fmt } from "./i18n.ts";
import type { StringKey, Strings } from "./i18n.ts";
import { aspectPct, isSafeImg } from "./media.ts";
import { MONOGRAM_DATA_URI } from "./monogram.ts";
import { STEP_IDS } from "./source.ts";
import type { ConnectionState, PanelState, PipelineStep, QcFrame, StepId } from "./source.ts";

/** The one fix button a problem carries (Addendum C1.4: one plain sentence + one fix button, never a command).
 *  start-engine is wired to the whynotcut:// launcher later; today the shell only logs it. */
export type FixAction = "start-engine" | "retry" | "copy-diagnostics";
const FIX_ACTIONS: readonly FixAction[] = ["start-engine", "retry", "copy-diagnostics"];
const FIX_LABEL: Record<FixAction, StringKey> = {
  "start-engine": "action.start_engine",
  retry: "action.retry",
  "copy-diagnostics": "actions.diagnostics",
};

export interface Notice {
  kind: "ok" | "error";
  text: string;
  how?: string;
  /** an error's one fix button; default Copy diagnostics */
  fix?: FixAction;
  /** what Try again runs: the click that led to this notice (its data-action and data-* values). mount sets it when it
   *  shows the notice and dispatches it again with fresh state (the text typed now, the fingerprint on screen now) */
  again?: { action: string; attrs: Readonly<Record<string, string>> };
}

/** Why the engine link is down (DaemonSource.diagnosis code), set by the shell: the offline banner names it. */
export interface LinkInfo {
  code: string;
  /** set while the panel is waiting to try again */
  retry_in_s?: number;
}

/** View state that is not engine data: what is expanded, what the editor has typed so far. */
export interface UiState {
  logOpen: boolean;
  confirmRebuild: boolean;
  changeText: string;
  editorName: string;
  notice: Notice | null;
  /** a command is in flight: action buttons are disabled until it answers */
  working: boolean;
  /** the engine link's diagnosis; absent = the generic offline banner */
  link?: LinkInfo | null;
  /** the plugin's version and build stamp (shown in the log drawer, copied with the diagnostics); set by the shell */
  build?: BuildInfo | null;
}

export function initialUi(): UiState {
  return { logOpen: false, confirmRebuild: false, changeText: "", editorName: "", notice: null, working: false };
}

export function esc(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

const ltr = (text: unknown) => `<bdi dir="ltr">${esc(text)}</bdi>`;
const auto = (text: unknown) => `<bdi>${esc(text)}</bdi>`;
/** A sentence that may hold commands in `backticks`: each command becomes a left-to-right run (the backticks are markup). */
const withCommands = (text: unknown) => esc(text).replace(/`([^`]+)`/g, (_m, cmd: string) => `<bdi dir="ltr">${cmd}</bdi>`);

const STEP_GLYPH: Record<string, string> = { done: "✓", failed: "✕" };
const VERDICT_GLYPH: Record<string, string> = { pass: "✓", fail: "✕", pending: "…", media_pending: "…" };

function clockOf(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function pill(kind: "engine" | "claude" | "host", c: ConnectionState, t: Strings): string {
  let cls: string;
  let value: string;
  if (kind === "engine") {
    cls = c.engine === "connected" ? "ok" : "offline";
    value = t[`pill.engine.${c.engine === "connected" ? "connected" : "offline"}` as StringKey];
  } else if (kind === "claude") {
    const st = c.claude === "active" || c.claude === "idle" ? c.claude : "unknown";
    cls = st === "active" ? "ok" : st;
    value = t[`pill.claude.${st}` as StringKey];
  } else {
    const st = c.host.state === "uxp" || c.host.state === "cep" ? c.host.state : "offline";
    cls = st === "uxp" ? "ok" : st === "cep" ? "warn" : "offline";
    value = c.host.detail && st !== "offline" ? c.host.detail : t[`pill.host.${st}` as StringKey];
  }
  return `<span class="pill pill-${cls}" data-pill="${kind}"><span class="pill-k">${esc(t[`pill.${kind}` as StringKey])}</span><span class="pill-v">${esc(value)}</span></span>`;
}

function header(s: PanelState, t: Strings): string {
  const who = s.client ? `${auto(s.client)} <span class="sep">·</span> ${ltr(s.item)}` : esc(t["status.noclient"]);
  return (
    `<header class="hdr">` +
    `<div class="hdr-title"><img class="mono" src="${MONOGRAM_DATA_URI}" alt="" width="24" height="24"><span class="wordmark">${esc(t["product.name"])}</span></div>` +
    `<div class="hairline"></div>` +
    `<div class="who">${who}</div>` +
    `<div class="pills">${pill("engine", s.connection, t)}${pill("claude", s.connection, t)}${pill("host", s.connection, t)}</div>` +
    `</header>`
  );
}

/** A file name chip on its own row (the rebuild backup name). The row is a flex container, so the chip is never laid
 *  out inside running text (UXP draws inline-flex over the sentence). Never a command: commands are not shown. */
const cmdRow = (text: string) => `<div class="cmd-row"><span class="cmd">${ltr(text)}</span></div>`;

/** The one fix button of a problem (a secondary button: the screen's primary is the main action, Addendum B4). Copy
 *  diagnostics comes with the sentence that says what to do with the copy, unless the problem's own words already say
 *  what to do (withSend = false). */
function fixButton(fix: FixAction, t: Strings, withSend = true): string {
  const a = FIX_ACTIONS.includes(fix) ? fix : "copy-diagnostics";
  const send = a === "copy-diagnostics" && withSend ? `<div class="banner-line">${esc(t["notice.send_diagnostics"])}</div>` : "";
  return `${send}<div class="btn-row banner-fix"><button class="btn btn-secondary" data-action="${a}">${esc(t[FIX_LABEL[a]])}</button></div>`;
}

/** The fix for each link diagnosis: the engine is not there (or must start again) -> Start engine; it is there but
 *  refuses, or the panel cannot reach its port -> Copy diagnostics (the payload names the command that fixes it). */
const LINK_FIX: Readonly<Record<string, FixAction>> = {
  no_engine: "start-engine",
  down: "start-engine",
  unreachable: "start-engine",
  bad_engine_json: "start-engine",
  auth: "start-engine",
  no_welcome: "start-engine",
  lost: "start-engine",
  refused_host: "copy-diagnostics",
  refused_busy: "copy-diagnostics",
  refused: "copy-diagnostics",
  protocol: "copy-diagnostics",
  too_large: "copy-diagnostics",
  blocked: "copy-diagnostics",
};

/** The offline banner for a known link diagnosis, or null (unknown code: the generic banner), and the fix button it
 *  carries. One plain sentence (plus "tries again by itself" while it does) and one fix button; never a command. */
function linkBanner(link: LinkInfo, t: Strings): { html: string; fix: FixAction | null } | null {
  const code = String(link.code);
  const banner = (key: StringKey, fix: FixAction | null, extra = "") => ({
    html:
      `<div class="banner banner-error" role="alert" data-link="${esc(code)}"><div class="banner-text">` +
      `<div class="banner-line"><strong>${withCommands(t[key])}</strong></div>${extra}${fix ? fixButton(fix, t) : ""}</div></div>`,
    fix,
  });
  if (code === "connecting" || code === "idle") return banner("status.connecting", null);
  // the panel stopped its link (stop()): starting the engine is what brings it back
  if (code === "stopped") return banner("offline.stopped", "start-engine");
  const fix = Object.prototype.hasOwnProperty.call(LINK_FIX, code) ? LINK_FIX[code] : undefined;
  if (!fix) return null;
  const retry = typeof link.retry_in_s === "number" ? `<div class="banner-line">${esc(t["offline.retry"])}</div>` : "";
  return banner(`offline.${code}` as StringKey, fix, retry);
}

function banners(s: PanelState, t: Strings, ui: UiState): string {
  let out = "";
  /** the fix button the offline banner carries: a notice never repeats it (two identical buttons on one screen) */
  let bannerFix: FixAction | null = null;
  const linked = s.connection.engine === "offline" && ui.link ? linkBanner(ui.link, t) : null;
  if (linked) {
    out += linked.html;
    bannerFix = linked.fix;
  } else if (s.connection.engine === "offline") {
    out +=
      `<div class="banner banner-error" role="alert"><div class="banner-text"><div class="banner-line"><strong>${esc(t["offline.title"])}</strong></div>` +
      `${fixButton("start-engine", t)}</div></div>`;
    bannerFix = "start-engine";
  }
  if (ui.notice) {
    const n = ui.notice;
    const error = n.kind !== "ok";
    // only the command span of an engine or host text is held back (mount has put the full words in the log): the cause
    // and the remedy stay; a text with nothing else left reads "That did not work."
    const text = neutralise(n.text) ?? t["notice.failed"];
    const how = n.how ? neutralise(n.how) : null;
    const fix: FixAction = n.fix ?? "copy-diagnostics";
    const button = error && fix !== bannerFix ? fixButton(fix, t, !how) : "";
    out +=
      `<div class="banner banner-${error ? "error" : "ok"}" role="status" aria-live="polite">` +
      `<div class="banner-text"><div class="banner-line">${esc(text)}${how ? ` ${withCommands(how)}` : ""}</div>${button}</div>` +
      `<button class="banner-x" data-action="dismiss-notice" title="${esc(t["notice.dismiss"])}" aria-label="${esc(t["notice.dismiss"])}">✕</button></div>`;
  }
  return out;
}

function currentStep(steps: PipelineStep[]): PipelineStep | null {
  return steps.find((p) => p.state === "running") ?? steps.find((p) => p.state === "waiting") ?? steps.find((p) => p.state === "failed") ?? null;
}

function pipelineSection(s: PanelState, t: Strings): string {
  const byId = new Map<StepId, PipelineStep>(s.pipeline.map((p) => [p.id, p]));
  // The state goes into a class name: only known values get through, whatever the source sends.
  const KNOWN: readonly string[] = ["done", "running", "waiting", "pending", "failed"];
  const steps: PipelineStep[] = STEP_IDS.map((id) => {
    const p = byId.get(id);
    return p ? { ...p, state: KNOWN.includes(p.state) ? p.state : "pending" } : { id, state: "pending" };
  });
  const items = steps
    .map((p, i) => {
      const glyph = STEP_GLYPH[p.state] ?? String(i + 1);
      return `<li class="step step-${p.state}" data-step="${p.id}"><span class="step-dot">${glyph}</span><span class="step-name">${esc(t[`step.${p.id}` as StringKey])}</span></li>`;
    })
    .join("");
  const cur = currentStep(steps);
  let now: string;
  if (!cur) {
    now = `<div class="now now-idle">${esc(t["pipeline.idle"])}</div>`;
  } else {
    const pr = cur.progress;
    const pct = pr && pr.of > 0 ? Math.max(0, Math.min(100, Math.round((pr.n / pr.of) * 100))) : null;
    // each part is its own element: the row is a flex row, so nothing depends on bdi flowing inline
    const meta: string[] = [];
    if (pr) meta.push(`<span class="meta-item">${fmt(t["pipeline.progress"], { n: ltr(pr.n), of: ltr(pr.of) })}</span>`);
    if (cur.elapsed_s !== null && cur.elapsed_s !== undefined) meta.push(`<span class="meta-item">${esc(t["pipeline.elapsed"])} ${ltr(clockOf(cur.elapsed_s))}</span>`);
    const cancel =
      cur.state === "running" && cur.request_id
        ? `<button class="btn btn-small btn-secondary" data-action="cancel" data-id="${esc(cur.request_id)}">${esc(t["pipeline.cancel"])}</button>`
        : "";
    now =
      `<div class="now now-${cur.state}"><div class="now-row"><span class="now-name">${esc(t[`step.${cur.id}` as StringKey])}</span>` +
      `<span class="now-state">${esc(t[`step.state.${cur.state}` as StringKey])}</span>${cancel}</div>` +
      (pr && pr.step ? `<div class="now-step">${auto(pr.step)}</div>` : "") +
      (pct !== null ? `<div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><div class="progress-fill" style="width:${pct}%"></div></div>` : "") +
      (meta.length ? `<div class="now-meta">${meta.join('<span class="sep">·</span>')}</div>` : "") +
      `</div>`;
  }
  return `<section class="sec" aria-label="${esc(t["section.pipeline"])}"><h2 class="sec-title">${esc(t["section.pipeline"])}</h2><ol class="steps">${items}</ol>${now}</section>`;
}

function approvalSection(s: PanelState, t: Strings, ui: UiState): string {
  const a = s.approval;
  const head = `<h2 class="sec-title">${esc(t["section.approval"])}</h2>`;
  if (!a) return `<section class="sec" aria-label="${esc(t["section.approval"])}">${head}<p class="muted">${esc(t["approval.empty"])}</p></section>`;
  const offline = s.connection.engine === "offline";
  const name = (s.editor_name || ui.editorName).trim();
  const flagged = a.flagged
    .map((f) => {
      const kind = f.kind === "religious" ? "religious" : "medical";
      return `<li class="flag flag-${kind}"><span class="flag-kind">${esc(t[`approval.flagged.${kind}` as StringKey])}</span><span class="flag-text">${auto(f.text)}</span><span class="flag-tc">${ltr(f.tc)}</span></li>`;
    })
    .join("");
  const nameField = s.editor_name
    ? ""
    : `<label class="field"><span class="lbl">${esc(t["approval.editor"])}</span><input class="input" type="text" data-field="editor_name" value="${esc(ui.editorName)}" placeholder="${esc(t["approval.editor.placeholder"])}"></label>`;
  const approveOff = offline || ui.working || name === "";
  const changesOff = offline || ui.working || ui.changeText.trim() === "";
  return (
    `<section class="sec" aria-label="${esc(t["section.approval"])}">${head}<div class="card">` +
    `<div class="lbl">${esc(t["approval.summary"])}</div><p class="summary">${auto(a.summary)}</p>` +
    `<button class="btn btn-secondary" data-action="preview"${a.preview_mp4 ? "" : " disabled"}>${esc(t["approval.preview"])}</button>` +
    (a.flagged.length ? `<div class="lbl lbl-flag">${esc(t["approval.flagged"])}</div><ul class="flags">${flagged}</ul>` : "") +
    nameField +
    `<button class="btn btn-primary btn-block" data-action="approve" data-fingerprint="${esc(a.fingerprint)}"${approveOff ? " disabled" : ""}>${esc(t["approval.approve"])}</button>` +
    `<label class="field"><span class="lbl">${esc(t["approval.changes.label"])}</span><textarea class="input" rows="3" data-field="changes" placeholder="${esc(t["approval.changes.placeholder"])}">${esc(ui.changeText)}</textarea></label>` +
    `<button class="btn btn-secondary btn-block" data-action="request-changes"${changesOff ? " disabled" : ""}>${esc(t["approval.changes"])}</button>` +
    `</div></section>`
  );
}

function tile(q: QcFrame, t: Strings): string {
  const verdict = ["pass", "fail", "pending", "media_pending"].includes(q.verdict) ? q.verdict : "pending";
  const img =
    isSafeImg(q.thumb)
      ? `<img class="qc-img" src="${esc(q.thumb)}" alt="">`
      : `<span class="qc-noimg">${esc(t[`qc.${verdict}` as StringKey])}</span>`;
  const reexport =
    verdict === "pending" || verdict === "media_pending"
      ? `<button class="btn btn-small btn-secondary qc-redo" data-action="reexport" data-t="${esc(q.t_s)}">${esc(t["qc.reexport"])}</button>`
      : "";
  return (
    `<div class="qc-tile qc-${verdict}" data-t="${esc(q.t_s)}">` +
    `<button class="qc-thumb" data-action="seek" data-t="${esc(q.t_s)}" title="${esc(q.tc)}"><span class="qc-frame" style="padding-top:${aspectPct(q.w, q.h)}%">${img}</span></button>` +
    `<div class="qc-meta"><span class="qc-tc">${ltr(q.tc)}</span><span class="qc-verdict">${VERDICT_GLYPH[verdict]} ${esc(t[`qc.${verdict}` as StringKey])}</span></div>` +
    `<div class="qc-label">${auto(q.label)}</div>${reexport}</div>`
  );
}

function qcSection(s: PanelState, t: Strings): string {
  const head = `<h2 class="sec-title">${esc(t["section.qc"])}</h2>`;
  const body = s.qc.length
    ? `<div class="qc-grid">${s.qc.map((q) => tile(q, t)).join("")}</div><p class="muted hint">${esc(t["qc.hint"])}</p>`
    : `<p class="muted">${esc(t["qc.empty"])}</p>`;
  return `<section class="sec" aria-label="${esc(t["section.qc"])}">${head}${body}</section>`;
}

function actionsSection(s: PanelState, t: Strings, ui: UiState): string {
  const off = s.connection.engine === "offline" || ui.working;
  const btn = (action: string, label: StringKey, enabled: boolean, hostOnly = false) =>
    `<button class="btn btn-secondary btn-act" data-action="${action}"${enabled && (hostOnly || !off) ? "" : " disabled"}>${esc(t[label])}</button>`;
  const rebuildCard = ui.confirmRebuild
    ? `<div class="card card-warn" role="alertdialog" aria-label="${esc(t["rebuild.title"])}"><div class="lbl lbl-warn">${esc(t["rebuild.title"])}</div>` +
      `<p>${esc(t["rebuild.warning"])}</p><p>${esc(t["rebuild.backup"])}</p>${cmdRow(t["rebuild.backup_name"])}` +
      `<div class="btn-row"><button class="btn btn-primary" data-action="rebuild-confirm"${off ? " disabled" : ""}>${esc(t["rebuild.confirm"])}</button>` +
      `<button class="btn btn-secondary" data-action="rebuild-cancel">${esc(t["rebuild.cancel"])}</button></div></div>`
    : "";
  return (
    `<section class="sec" aria-label="${esc(t["section.actions"])}"><h2 class="sec-title">${esc(t["section.actions"])}</h2>` +
    (s.context.project_path ? `<div class="path">${ltr(s.context.project_path)}</div>` : "") +
    `<div class="actions">` +
    btn("open-project", "actions.open", openProjectAction(s) !== null) +
    btn("rebuild", "actions.rebuild", rebuildInput(s) !== null) +
    btn("export-frames", "actions.export", exportFramesAction(s) !== null) +
    btn("render-review", "actions.render", renderReviewAction(s) !== null) +
    btn("reveal", "actions.reveal", !!s.context.folder, true) +
    `<button class="btn btn-secondary btn-act" data-action="copy-diagnostics">${esc(t["actions.diagnostics"])}</button>` +
    `</div>${rebuildCard}</section>`
  );
}

function logSection(s: PanelState, t: Strings, ui: UiState): string {
  const toggle =
    `<button class="log-toggle" data-action="toggle-log" aria-expanded="${ui.logOpen ? "true" : "false"}">` +
    // UXP drops the whitespace between inline children: one explicit flex row, items separated by margins
    `<span class="log-row"><span class="caret">${ui.logOpen ? "▾" : "▸"}</span><span class="log-title">${esc(t["log.toggle"])}</span>` +
    `<span class="log-count">${esc(fmt(t["log.lines"], { n: s.log.length }))}</span></span></button>`;
  if (!ui.logOpen) return `<section class="sec sec-log">${toggle}</section>`;
  const lines = s.log.length
    ? `<ul class="log-lines">${s.log
        .slice(-100)
        .map((l) => `<li class="log-line log-${l.level === "warn" || l.level === "error" ? l.level : "info"}"><span class="log-ts">${esc(l.ts)}</span>${ltr(l.text)}</li>`)
        .join("")}</ul>`
    : `<p class="muted">${esc(t["log.empty"])}</p>`;
  const build = ui.build ? `<p class="muted hint log-build">${ltr(fmt(t["log.build"], { version: ui.build.version, build: ui.build.build }))}</p>` : "";
  return `<section class="sec sec-log">${toggle}${lines}${build}</section>`;
}

export function render(state: PanelState, t: Strings, ui: UiState = initialUi()): string {
  const rtl = state.language === "ar";
  return (
    `<div class="twn-panel ${rtl ? "twn-rtl" : "twn-ltr"}" dir="${rtl ? "rtl" : "ltr"}" lang="${rtl ? "ar" : "en"}">` +
    `<div class="twn-scroll">` +
    header(state, t) +
    `<main class="body">` +
    banners(state, t, ui) +
    pipelineSection(state, t) +
    approvalSection(state, t, ui) +
    qcSection(state, t) +
    actionsSection(state, t, ui) +
    logSection(state, t, ui) +
    `</main>` +
    `<footer class="foot">${ltr(t["footer.powered"])}</footer>` +
    `</div></div>`
  );
}

const shell = (t: Strings, rtl: boolean, inner: string) =>
  `<div class="twn-panel ${rtl ? "twn-rtl" : "twn-ltr"}" dir="${rtl ? "rtl" : "ltr"}" lang="${rtl ? "ar" : "en"}"><div class="twn-scroll"><main class="body">${inner}</main>` +
  `<footer class="foot">${ltr(t["footer.powered"])}</footer></div></div>`;

/** Shown before the first snapshot arrives. */
export function renderLoading(t: Strings, rtl = false): string {
  return shell(t, rtl, `<p class="muted">${esc(t["status.connecting"])}</p>`);
}

/** Shown when the panel cannot render or read its state: the message is visible, never a blank panel. */
export function renderError(t: Strings, rtl: boolean, title: string, message: string): string {
  return shell(
    t,
    rtl,
    `<div class="banner banner-error" role="alert"><span class="banner-text"><strong>${esc(title)}</strong> ${ltr(message)}</span></div>`,
  );
}
