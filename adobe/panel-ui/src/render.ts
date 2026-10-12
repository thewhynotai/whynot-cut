// Pure rendering: render(state, strings, ui) -> HTML string. Every dynamic value goes through esc().
// Commands, paths and timecodes are wrapped in <bdi dir="ltr"> so they stay left-to-right inside Arabic text.
// Markup is flexbox-friendly and uses only simple classes (UXP and CEP render the same CSS).
import { exportFramesAction, openProjectAction, rebuildInput, renderReviewAction } from "./actions.ts";
import { fmt } from "./i18n.ts";
import type { StringKey, Strings } from "./i18n.ts";
import { MONOGRAM_DATA_URI } from "./monogram.ts";
import { STEP_IDS } from "./source.ts";
import type { ConnectionState, PanelState, PipelineStep, QcFrame, StepId } from "./source.ts";

export interface Notice {
  kind: "ok" | "error";
  text: string;
  how?: string;
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
// data:image, file: and plugin: URLs and relative paths only: a thumbnail never makes the panel fetch from the network.
const SAFE_IMG = /^(?:data:image\/|file:|plugin:|(?![a-z][a-z0-9+.-]*:|\/\/)\S)/i;

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

function banners(s: PanelState, t: Strings, ui: UiState): string {
  let out = "";
  if (s.connection.engine === "offline") {
    out += `<div class="banner banner-error" role="alert"><span class="banner-text"><strong>${esc(t["offline.title"])}</strong> ${esc(t["offline.hint"])} <span class="cmd">${ltr("reel doctor")}</span></span></div>`;
  }
  if (ui.notice) {
    const n = ui.notice;
    out +=
      `<div class="banner banner-${n.kind === "ok" ? "ok" : "error"}" role="status" aria-live="polite">` +
      `<span class="banner-text">${esc(n.text)}${n.how ? ` ${withCommands(n.how)}` : ""}</span>` +
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

/** Height as a percentage of the width for the frame box. Default 9:16; invalid w/h fall back; clamped to 40..300. */
function aspectPct(q: QcFrame): number {
  const ok = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n) && n > 0;
  const pct = ok(q.w) && ok(q.h) ? (q.h / q.w) * 100 : (1920 / 1080) * 100;
  return Math.round(Math.max(40, Math.min(300, pct)) * 100) / 100;
}

function tile(q: QcFrame, t: Strings): string {
  const verdict = ["pass", "fail", "pending", "media_pending"].includes(q.verdict) ? q.verdict : "pending";
  const img =
    q.thumb && SAFE_IMG.test(q.thumb)
      ? `<img class="qc-img" src="${esc(q.thumb)}" alt="">`
      : `<span class="qc-noimg">${esc(t[`qc.${verdict}` as StringKey])}</span>`;
  const reexport =
    verdict === "pending" || verdict === "media_pending"
      ? `<button class="btn btn-small btn-secondary qc-redo" data-action="reexport" data-t="${esc(q.t_s)}">${esc(t["qc.reexport"])}</button>`
      : "";
  return (
    `<div class="qc-tile qc-${verdict}" data-t="${esc(q.t_s)}">` +
    `<button class="qc-thumb" data-action="seek" data-t="${esc(q.t_s)}" title="${esc(q.tc)}"><span class="qc-frame" style="padding-top:${aspectPct(q)}%">${img}</span></button>` +
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
      `<p>${esc(t["rebuild.warning"])}</p><p>${esc(t["rebuild.backup"])} <span class="cmd">${ltr("name_prev_date-time.prproj")}</span></p>` +
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
    `<span class="caret">${ui.logOpen ? "▾" : "▸"}</span><span class="log-title">${esc(t["log.toggle"])}</span>` +
    `<span class="log-count">${esc(fmt(t["log.lines"], { n: s.log.length }))}</span></button>`;
  if (!ui.logOpen) return `<section class="sec sec-log">${toggle}</section>`;
  const lines = s.log.length
    ? `<ul class="log-lines">${s.log
        .slice(-100)
        .map((l) => `<li class="log-line log-${l.level === "warn" || l.level === "error" ? l.level : "info"}"><span class="log-ts">${esc(l.ts)}</span>${ltr(l.text)}</li>`)
        .join("")}</ul>`
    : `<p class="muted">${esc(t["log.empty"])}</p>`;
  return `<section class="sec sec-log">${toggle}${lines}</section>`;
}

export function render(state: PanelState, t: Strings, ui: UiState = initialUi()): string {
  const rtl = state.language === "ar";
  return (
    `<div class="twn-panel ${rtl ? "twn-rtl" : "twn-ltr"}" dir="${rtl ? "rtl" : "ltr"}" lang="${rtl ? "ar" : "en"}">` +
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
    `</div>`
  );
}

const shell = (t: Strings, rtl: boolean, inner: string) =>
  `<div class="twn-panel ${rtl ? "twn-rtl" : "twn-ltr"}" dir="${rtl ? "rtl" : "ltr"}" lang="${rtl ? "ar" : "en"}"><main class="body">${inner}</main>` +
  `<footer class="foot">${ltr(t["footer.powered"])}</footer></div>`;

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
