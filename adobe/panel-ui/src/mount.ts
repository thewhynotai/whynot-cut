// mount(root, source, host): renders the panel into root, re-renders on every state change and wires the
// buttons by event delegation (one click and one input listener on the root). The host adapter does the
// things only the host app can do (playhead, Source Monitor, reveal, clipboard).
// Every problem on screen is one plain sentence and one fix button (Addendum C1.4): Start engine, Try again or Copy
// diagnostics. Try again belongs to the notice it is on: the notice keeps the click that led to it, and Try again
// dispatches that click again with the state as it is now. A command inside an engine or host text is not shown (render
// neutralises the span, src/commands.ts); the full words go to the log drawer, through the panel's own log lines
// (token-scrubbed like DaemonSource's, and merged with the source's by time, newest last).
import { exportFramesAction, openProjectAction, rebuildInput, renderReviewAction } from "./actions.ts";
import type { BuiltAction } from "./actions.ts";
import { neutralise } from "./commands.ts";
import { diagnosticsText, NOT_YET_CODE, scrubToken, START_ENGINE_COMMAND } from "./diagnostics.ts";
import type { HostOutcome, PanelHost } from "./host.ts";
import { EN, fmt, stringsFor } from "./i18n.ts";
import { initialUi, render, renderError, renderLoading } from "./render.ts";
import type { FixAction, Notice, UiState } from "./render.ts";
import type { LogLine, PanelDataSource, PanelState, Result } from "./source.ts";

/** the panel's own log lines kept (the source keeps its own) */
const LOCAL_LOG_MAX = 50;
/** the data-* values a click carries that its handler reads (Try again dispatches them again) */
const CLICK_ATTRS = ["data-t", "data-id", "data-fingerprint"] as const;

/** The slice of a DOM element the panel uses; real elements and the test fake both satisfy it. */
export interface PanelElement {
  getAttribute(name: string): string | null;
  closest(selector: string): PanelElement | null;
  value?: string;
  disabled?: boolean;
  selectionStart?: number | null;
  selectionEnd?: number | null;
  focus?(): void;
  setSelectionRange?(start: number, end: number): void;
}
export interface PanelEvent {
  target: PanelElement | null;
}
export interface MountRoot {
  innerHTML: string;
  addEventListener(type: string, fn: (e: PanelEvent) => void): void;
  removeEventListener(type: string, fn: (e: PanelEvent) => void): void;
  querySelector?(selector: string): PanelElement | null;
  ownerDocument?: { activeElement?: PanelElement | null } | null;
}

/** Lets a shell pass a real HTMLElement without a cast at every call site. */
export function asMountRoot(el: unknown): MountRoot {
  return el as MountRoot;
}

export interface MountHandle {
  /** resolves when the first snapshot has been rendered (or failed) */
  ready: Promise<void>;
  ui: UiState;
  unmount(): void;
}

/** A click, as Try again replays it: the data-action and the data-* values. */
type Click = NonNullable<Notice["again"]>;

/** A log line with the epoch ms it was written at (the merge key). */
type TimedLine = LogLine & { at: number };

const DAY_MS = 24 * 60 * 60 * 1000;

/** The epoch ms of a source log line: its own `at` when it carries one, else its "HH:MM:SS" (UTC, as DaemonSource
 *  writes it) on the most recent day that does not put it in the future. */
export function logEpoch(l: LogLine, now: number): number {
  const own = (l as Partial<TimedLine>).at;
  if (typeof own === "number" && Number.isFinite(own)) return own;
  const m = /^(\d{2}):(\d{2}):(\d{2})/.exec(String(l.ts));
  if (!m) return now;
  const midnight = now - (now % DAY_MS);
  const t = midnight + ((Number(m[1]) * 60 + Number(m[2])) * 60 + Number(m[3])) * 1000;
  return t > now + 60_000 ? t - DAY_MS : t;
}

export function mount(root: MountRoot, source: PanelDataSource, host: PanelHost): MountHandle {
  const ui: UiState = initialUi();
  let state: PanelState | null = null;
  let off: (() => void) | null = null;
  let live = true;
  /** the panel's own log lines: button presses the engine cannot log yet, the full words of a text held back */
  const localLog: TimedLine[] = [];

  /** The state as shown: the source's log lines and the panel's own, merged by the full time they were written (epoch
   *  ms, not the "HH:MM:SS" text, so a line from before midnight sorts before one after it; a stable sort keeps lines of
   *  the same ms in their list's order), the newest 200. */
  function view(s: PanelState): PanelState {
    if (!localLog.length) return s;
    const now = Date.now();
    const merged = [...s.log.map((l) => ({ line: l, at: logEpoch(l, now) })), ...localLog.map((l) => ({ line: l as LogLine, at: l.at }))]
      .sort((a, b) => a.at - b.at)
      .slice(-200)
      .map(({ line }): LogLine => ({ ts: line.ts, level: line.level, text: line.text }));
    return { ...s, log: merged };
  }

  /** A line in the panel's own log: token-scrubbed (diagnostics.scrubToken, as DaemonSource's lines are), capped. */
  function addLog(level: LogLine["level"], text: string): void {
    const at = Date.now();
    localLog.push({ ts: new Date(at).toISOString().slice(11, 19), level, text: scrubToken(String(text)).slice(0, 4000), at });
    if (localLog.length > LOCAL_LOG_MAX) localLog.splice(0, localLog.length - LOCAL_LOG_MAX);
  }

  /** An error's one fix: an engine action while the engine is not running -> Start engine; an answer that is the same
   *  every time (NOT_YET: not available from the panel yet) or nothing to repeat -> Copy diagnostics; else Try again.
   *  A host-only action (reveal, copy, seek) never asks to start the engine. */
  function fixFor(engine: boolean, r: Result | null, again: Click | null): FixAction {
    if (engine && state?.connection.engine === "offline") return "start-engine";
    const code = r ? (r as Result & { code?: unknown }).code : undefined;
    if (code === NOT_YET_CODE || /not available from the panel/i.test(r?.error ?? "")) return "copy-diagnostics";
    return again ? "retry" : "copy-diagnostics";
  }

  const strings = () => stringsFor(state?.language === "ar" ? "ar" : "en");

  const isRtl = () => state?.language === "ar";

  /** Shows an error view in place of the panel. Never throws. */
  function showError(titleKey: "error.render" | "error.snapshot", e: unknown): void {
    const message = e instanceof Error ? e.message : String(e);
    try {
      root.innerHTML = renderError(strings(), isRtl(), strings()[titleKey], message);
    } catch {
      root.innerHTML = `<p>${message.replace(/[<>&"]/g, "?")}</p>`;
    }
  }

  /** Renders the state. A throw (a daemon payload that is slightly off) becomes a visible error view, never a blank panel
   *  and never an exception into the source's emit loop or an unhandled rejection. The next good state repaints. */
  function paint(): void {
    if (!live || !state) return;
    try {
      const doc = root.ownerDocument;
      const active = doc?.activeElement ?? null;
      const field = active?.getAttribute ? active.getAttribute("data-field") : null;
      const selStart = active?.selectionStart ?? null;
      const selEnd = active?.selectionEnd ?? null;
      root.innerHTML = render(view(state), strings(), ui);
      if (field && root.querySelector) {
        const el = root.querySelector(`[data-field="${field}"]`);
        if (el?.focus) {
          el.focus();
          if (selStart !== null && selEnd !== null && el.setSelectionRange) el.setSelectionRange(selStart, selEnd);
        }
      }
    } catch (e) {
      showError("error.render", e);
    }
  }

  function setNotice(r: Result | null, okText?: string, error?: unknown, engine = true, again: Click | null = null): void {
    const t = strings();
    let text: string | null = null;
    let how: string | undefined;
    if (error !== undefined) text = error instanceof Error ? error.message : String(error);
    else if (r && !r.ok) {
      text = r.error || t["notice.failed"];
      how = r.how || undefined;
    }
    if (text === null) {
      ui.notice = okText ? { kind: "ok", text: okText } : null;
      return;
    }
    // render shows a text or how without its command span: the full words go to the log drawer
    if (neutralise(text) !== text || (how !== undefined && neutralise(how) !== how)) addLog("error", how ? `${text} ${how}` : text);
    const fix = fixFor(engine, r, again);
    ui.notice = { kind: "error", text, ...(how ? { how } : {}), fix, ...(fix === "retry" && again ? { again } : {}) };
  }

  /** Runs one command and shows its outcome. lock = disable the action buttons meanwhile (engine commands, not host
   *  nudges). again = the click Try again dispatches when this fails. */
  async function perform(fn: () => Promise<Result | void> | Result | void, okText?: string, lock = true, again: Click | null = null): Promise<boolean> {
    ui.notice = null;
    if (lock) {
      ui.working = true;
      paint();
    }
    let ok = true;
    try {
      const r = await fn();
      if (r && !r.ok) ok = false;
      setNotice(r ?? null, okText, undefined, lock, again);
    } catch (e) {
      ok = false;
      setNotice(null, undefined, e, lock, again);
    }
    if (lock) ui.working = false;
    paint();
    return ok;
  }

  /** Reveal / Copy: the host tries the real thing first ("done" -> a short ok notice) and falls back to a visible box
   *  ("shown" or nothing -> no banner: the box is the outcome). Only a real failure is a red banner. */
  async function hostShow(fn: () => Promise<HostOutcome | void> | HostOutcome | void, okKey: "notice.opened" | "notice.copied", again: Click): Promise<void> {
    ui.notice = null;
    try {
      const outcome = await fn();
      ui.notice = outcome === "done" ? { kind: "ok", text: strings()[okKey] } : null;
    } catch (e) {
      setNotice(null, undefined, e, false, again);
    }
    paint();
  }

  function missing(): void {
    ui.notice = { kind: "error", text: strings()["notice.missing"] };
    paint();
  }

  function runBuilt(built: BuiltAction | null, again: Click, okText?: string): Promise<boolean> | void {
    if (!built) return missing();
    return perform(() => source.run(built.action, built.data), okText ?? strings()["notice.ok"], true, again);
  }

  /** The click as Try again replays it. */
  function clickOf(action: string, el: PanelElement): Click {
    const attrs: Record<string, string> = {};
    for (const k of CLICK_ATTRS) {
      const v = el.getAttribute(k);
      if (v !== null) attrs[k] = v;
    }
    return { action, attrs };
  }

  /** Try again: the click that led to the notice on screen, dispatched again with the state as it is NOW (the text typed
   *  now, the editor's name now, the approval card's fingerprint now), so its follow-ups run the normal way. A failed
   *  rebuild opens its confirm card again: a rebuild replaces the editor's edits, so it never runs unasked. */
  function retry(): void {
    const again = ui.notice?.again ?? null;
    ui.notice = null;
    if (!again) return paint();
    if (again.action === "rebuild-confirm") {
      ui.confirmRebuild = true;
      return paint();
    }
    const attrs = again.attrs;
    const el: PanelElement = {
      getAttribute: (n) => (n === "data-action" ? again.action : Object.prototype.hasOwnProperty.call(attrs, n) ? attrs[n]! : null),
      closest: () => el,
    };
    dispatch(again.action, el, true);
  }

  function handleClick(e: PanelEvent): void {
    const el = e.target?.closest("[data-action]") ?? null;
    if (!el) return;
    dispatch(el.getAttribute("data-action"), el, false);
  }

  /** One click. replay = Try again dispatches it (the approval fingerprint is the one on screen now). */
  function dispatch(action: string | null, el: PanelElement, replay: boolean): void {
    if (!state || !action) return;
    const t = strings();
    const s = state;
    const again = clickOf(action, el);
    switch (action) {
      case "approve": {
        const fingerprint = (replay ? s.approval?.fingerprint : el.getAttribute("data-fingerprint")) ?? "";
        const name = (s.editor_name || ui.editorName).trim();
        if (!name || !fingerprint) return;
        void perform(() => source.approve({ item: s.item, editor_name: name, fingerprint }), t["notice.approved"], true, again).then((ok) => {
          if (ok) {
            ui.changeText = "";
            paint();
          }
        });
        return;
      }
      case "request-changes": {
        const text = ui.changeText.trim();
        const name = (s.editor_name || ui.editorName).trim();
        if (!text || !name) return;
        void perform(() => source.requestChanges({ item: s.item, editor_name: name, text }), t["notice.changes"], true, again).then((ok) => {
          if (ok) {
            ui.changeText = "";
            paint();
          }
        });
        return;
      }
      case "seek": {
        const t_s = Number(el.getAttribute("data-t"));
        if (!Number.isFinite(t_s)) return;
        void perform(() => host.setPlayerPosition(t_s), undefined, false, again);
        return;
      }
      case "reexport": {
        const t_s = Number(el.getAttribute("data-t"));
        if (!Number.isFinite(t_s)) return;
        void runBuilt(exportFramesAction(s, [t_s]), again);
        return;
      }
      case "preview": {
        const mp4 = s.approval?.preview_mp4;
        if (mp4) void perform(() => host.openInSourceMonitor(mp4), undefined, false, again);
        return;
      }
      case "open-project":
        void runBuilt(openProjectAction(s), again);
        return;
      case "export-frames":
        void runBuilt(exportFramesAction(s), again);
        return;
      case "render-review":
        void runBuilt(renderReviewAction(s), again);
        return;
      case "rebuild":
        if (!rebuildInput(s)) return missing();
        ui.confirmRebuild = true;
        paint();
        return;
      case "rebuild-cancel":
        ui.confirmRebuild = false;
        paint();
        return;
      case "rebuild-confirm": {
        ui.confirmRebuild = false;
        const input = rebuildInput(s);
        if (!input) return missing();
        // Try again on its notice opens this confirm card again (retry()): never a rebuild unasked
        void perform(() => source.rebuild(input), t["notice.ok"], true, again);
        return;
      }
      case "reveal": {
        const folder = s.context.folder;
        if (!folder) return missing();
        void hostShow(() => host.revealPath(folder), "notice.opened", again);
        return;
      }
      case "copy-diagnostics":
        void hostShow(() => host.copyText(diagnosticsText(view(s), ui.build, ui.link)), "notice.copied", again);
        return;
      case "start-engine":
        // wired to the launcher (whynotcut://engine/start) once it ships; today a log line that names what will run, in
        // English like every log line, and the log drawer opens so the press visibly does something
        addLog("info", fmt(EN["log.start_engine"], { command: START_ENGINE_COMMAND }));
        ui.logOpen = true;
        paint();
        return;
      case "retry":
        retry();
        return;
      case "cancel": {
        const id = el.getAttribute("data-id");
        if (id) void perform(() => source.cancel(id), undefined, true, again);
        return;
      }
      case "toggle-log":
        ui.logOpen = !ui.logOpen;
        paint();
        return;
      case "dismiss-notice":
        ui.notice = null;
        paint();
        return;
      default:
        return;
    }
  }

  /** A handler that throws (a state that is slightly off) becomes a notice, not an exception in the event loop. */
  function onClick(e: PanelEvent): void {
    try {
      handleClick(e);
    } catch (err) {
      setNotice(null, undefined, err); // the handler itself broke: Copy diagnostics, never a re-run
      paint();
    }
  }

  function onInput(e: PanelEvent): void {
    const el = e.target?.closest("[data-field]") ?? null;
    if (!el) return;
    const value = el.value ?? "";
    const field = el.getAttribute("data-field");
    // Update the buttons in place: a full re-render would drop the caret while the editor types.
    if (field === "changes") {
      ui.changeText = value;
      const b = root.querySelector?.('[data-action="request-changes"]');
      if (b) b.disabled = value.trim() === "" || ui.working || state?.connection.engine === "offline";
    } else if (field === "editor_name") {
      ui.editorName = value;
      const b = root.querySelector?.('[data-action="approve"]');
      if (b) b.disabled = value.trim() === "" || ui.working || state?.connection.engine === "offline";
    }
  }

  root.addEventListener("click", onClick);
  root.addEventListener("input", onInput);

  // Subscribe first, then ask for the snapshot: a change that lands in between is not lost, and a pushed
  // state that arrives before the snapshot answers wins (it is newer).
  root.innerHTML = renderLoading(stringsFor("en"));
  let pushed = false;
  off = source.subscribe((next) => {
    pushed = true;
    state = next;
    paint();
  });
  const ready = source
    .snapshot()
    .then((s) => {
      if (!live || pushed) return;
      state = s;
      paint();
    })
    .catch((e: unknown) => {
      // paint() cannot throw, so this is only a snapshot() that failed; a state pushed meanwhile stays on screen.
      if (live && !pushed) showError("error.snapshot", e);
    });

  return {
    ready,
    ui,
    unmount() {
      live = false;
      off?.();
      off = null;
      root.removeEventListener("click", onClick);
      root.removeEventListener("input", onInput);
    },
  };
}
