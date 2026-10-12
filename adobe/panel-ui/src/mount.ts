// mount(root, source, host): renders the panel into root, re-renders on every state change and wires the
// buttons by event delegation (one click and one input listener on the root). The host adapter does the
// things only the host app can do (playhead, Source Monitor, reveal, clipboard).
// Every problem on screen is one plain sentence and one fix button (Addendum C1.4): Start engine, Try again (runs the
// last action again) or Copy diagnostics. A text from the engine or a host that holds a command is not shown; it goes
// to the log drawer, through the panel's own log lines (merged with the source's, newest last).
import { exportFramesAction, openProjectAction, rebuildInput, renderReviewAction } from "./actions.ts";
import type { BuiltAction } from "./actions.ts";
import { diagnosticsText, START_ENGINE_COMMAND } from "./diagnostics.ts";
import type { HostOutcome, PanelHost } from "./host.ts";
import { fmt, stringsFor } from "./i18n.ts";
import { hasCommand, initialUi, render, renderError, renderLoading } from "./render.ts";
import type { FixAction, UiState } from "./render.ts";
import type { LogLine, PanelDataSource, PanelState, Result } from "./source.ts";

/** the panel's own log lines kept (the source keeps its own) */
const LOCAL_LOG_MAX = 50;

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

export function mount(root: MountRoot, source: PanelDataSource, host: PanelHost): MountHandle {
  const ui: UiState = initialUi();
  let state: PanelState | null = null;
  let off: (() => void) | null = null;
  let live = true;
  /** the panel's own log lines: button presses the engine cannot log yet, texts held back from the screen */
  const localLog: LogLine[] = [];
  /** "Try again" runs this: the last action, the same way */
  let lastRun: (() => void) | null = null;

  /** The state as shown: the source's log lines and the panel's own, in time order (a stable sort keeps each list's order). */
  function view(s: PanelState): PanelState {
    if (!localLog.length) return s;
    return { ...s, log: [...s.log, ...localLog].sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0)).slice(-200) };
  }

  function addLog(level: LogLine["level"], text: string): void {
    localLog.push({ ts: new Date().toISOString().slice(11, 19), level, text: text.slice(0, 4000) });
    if (localLog.length > LOCAL_LOG_MAX) localLog.splice(0, localLog.length - LOCAL_LOG_MAX);
  }

  /** An error's one fix: an engine action while the engine is not running -> Start engine; an action failed -> Try
   *  again; else Copy diagnostics. A host-only action (reveal, copy, seek) never asks to start the engine. */
  function fixFor(engine: boolean): FixAction {
    if (engine && state?.connection.engine === "offline") return "start-engine";
    return lastRun ? "retry" : "copy-diagnostics";
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

  function setNotice(r: Result | null, okText?: string, error?: unknown, engine = true): void {
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
    // render shows neither a text nor a how that holds a command: the full words go to the log drawer
    if (hasCommand(text) || hasCommand(how)) addLog("error", how ? `${text} ${how}` : text);
    ui.notice = { kind: "error", text, ...(how ? { how } : {}), fix: fixFor(engine) };
  }

  /** Runs one command and shows its outcome. lock = disable the action buttons meanwhile (engine commands, not host nudges). */
  async function perform(fn: () => Promise<Result | void> | Result | void, okText?: string, lock = true, retry?: () => void): Promise<boolean> {
    lastRun = retry ?? (() => void perform(fn, okText, lock));
    ui.notice = null;
    if (lock) {
      ui.working = true;
      paint();
    }
    let ok = true;
    try {
      const r = await fn();
      if (r && !r.ok) ok = false;
      setNotice(r ?? null, okText, undefined, lock);
    } catch (e) {
      ok = false;
      setNotice(null, undefined, e, lock);
    }
    if (lock) ui.working = false;
    paint();
    return ok;
  }

  /** Reveal / Copy: the host tries the real thing first ("done" -> a short ok notice) and falls back to a visible box
   *  ("shown" or nothing -> no banner: the box is the outcome). Only a real failure is a red banner. */
  async function hostShow(fn: () => Promise<HostOutcome | void> | HostOutcome | void, okKey: "notice.opened" | "notice.copied"): Promise<void> {
    lastRun = () => void hostShow(fn, okKey);
    ui.notice = null;
    try {
      const outcome = await fn();
      ui.notice = outcome === "done" ? { kind: "ok", text: strings()[okKey] } : null;
    } catch (e) {
      setNotice(null, undefined, e, false);
    }
    paint();
  }

  function missing(): void {
    ui.notice = { kind: "error", text: strings()["notice.missing"] };
    paint();
  }

  function runBuilt(built: BuiltAction | null, okText?: string): Promise<boolean> | void {
    if (!built) return missing();
    return perform(() => source.run(built.action, built.data), okText ?? strings()["notice.ok"]);
  }

  function handleClick(e: PanelEvent): void {
    const el = e.target?.closest("[data-action]") ?? null;
    if (!el || !state) return;
    const action = el.getAttribute("data-action");
    const t = strings();
    const s = state;
    switch (action) {
      case "approve": {
        const fingerprint = el.getAttribute("data-fingerprint") ?? "";
        const name = (s.editor_name || ui.editorName).trim();
        if (!name || !fingerprint) return;
        void perform(() => source.approve({ item: s.item, editor_name: name, fingerprint }), t["notice.approved"]).then((ok) => {
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
        void perform(() => source.requestChanges({ item: s.item, editor_name: name, text }), t["notice.changes"]).then((ok) => {
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
        void perform(() => host.setPlayerPosition(t_s), undefined, false);
        return;
      }
      case "reexport": {
        const t_s = Number(el.getAttribute("data-t"));
        if (!Number.isFinite(t_s)) return;
        void runBuilt(exportFramesAction(s, [t_s]));
        return;
      }
      case "preview": {
        const mp4 = s.approval?.preview_mp4;
        if (mp4) void perform(() => host.openInSourceMonitor(mp4), undefined, false);
        return;
      }
      case "open-project":
        void runBuilt(openProjectAction(s));
        return;
      case "export-frames":
        void runBuilt(exportFramesAction(s));
        return;
      case "render-review":
        void runBuilt(renderReviewAction(s));
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
        // Try again shows the confirm card again: a rebuild replaces the editor's edits, so it is never re-run unasked
        void perform(() => source.rebuild(input), t["notice.ok"], true, () => {
          ui.notice = null;
          ui.confirmRebuild = true;
          paint();
        });
        return;
      }
      case "reveal": {
        const folder = s.context.folder;
        if (!folder) return missing();
        void hostShow(() => host.revealPath(folder), "notice.opened");
        return;
      }
      case "copy-diagnostics":
        void hostShow(() => host.copyText(diagnosticsText(view(s), ui.build, ui.link)), "notice.copied");
        return;
      case "start-engine":
        // wired to the launcher (whynotcut://engine/start) once it ships; today a log line that names what will run
        addLog("info", fmt(t["log.start_engine"], { command: START_ENGINE_COMMAND }));
        paint();
        return;
      case "retry": {
        const again = lastRun;
        ui.notice = null;
        if (again) again();
        else paint();
        return;
      }
      case "cancel": {
        const id = el.getAttribute("data-id");
        if (id) void perform(() => source.cancel(id));
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
      lastRun = null; // the handler itself broke: Copy diagnostics, not a re-run of an earlier action
      setNotice(null, undefined, err);
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
