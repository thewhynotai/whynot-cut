// mount(root, source, host): renders the panel into root, re-renders on every state change and wires the
// buttons by event delegation (one click and one input listener on the root). The host adapter does the
// things only the host app can do (playhead, Source Monitor, reveal, clipboard).
import { exportFramesAction, openProjectAction, rebuildAction, renderReviewAction } from "./actions.ts";
import type { BuiltAction } from "./actions.ts";
import { diagnosticsText } from "./diagnostics.ts";
import type { PanelHost } from "./host.ts";
import { stringsFor } from "./i18n.ts";
import { initialUi, render, renderLoading } from "./render.ts";
import type { UiState } from "./render.ts";
import type { PanelDataSource, PanelState, Result } from "./source.ts";

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

  const strings = () => stringsFor(state?.language ?? "en");

  function paint(): void {
    if (!live || !state) return;
    const doc = root.ownerDocument;
    const active = doc?.activeElement ?? null;
    const field = active?.getAttribute ? active.getAttribute("data-field") : null;
    const selStart = active?.selectionStart ?? null;
    const selEnd = active?.selectionEnd ?? null;
    root.innerHTML = render(state, strings(), ui);
    if (field && root.querySelector) {
      const el = root.querySelector(`[data-field="${field}"]`);
      if (el?.focus) {
        el.focus();
        if (selStart !== null && selEnd !== null && el.setSelectionRange) el.setSelectionRange(selStart, selEnd);
      }
    }
  }

  function setNotice(r: Result | null, okText?: string, error?: unknown): void {
    const t = strings();
    if (error !== undefined) ui.notice = { kind: "error", text: error instanceof Error ? error.message : String(error) };
    else if (r && !r.ok) ui.notice = { kind: "error", text: r.error || t["notice.failed"], ...(r.how ? { how: r.how } : {}) };
    else ui.notice = okText ? { kind: "ok", text: okText } : null;
  }

  /** Runs one command and shows its outcome. lock = disable the action buttons meanwhile (engine commands, not host nudges). */
  async function perform(fn: () => Promise<Result | void> | Result | void, okText?: string, lock = true): Promise<boolean> {
    ui.notice = null;
    if (lock) {
      ui.working = true;
      paint();
    }
    let ok = true;
    try {
      const r = await fn();
      if (r && !r.ok) ok = false;
      setNotice(r ?? null, okText);
    } catch (e) {
      ok = false;
      setNotice(null, undefined, e);
    }
    if (lock) ui.working = false;
    paint();
    return ok;
  }

  function missing(): void {
    ui.notice = { kind: "error", text: strings()["notice.missing"] };
    paint();
  }

  function runBuilt(built: BuiltAction | null, okText?: string): Promise<boolean> | void {
    if (!built) return missing();
    return perform(() => source.run(built.action, built.data), okText ?? strings()["notice.ok"]);
  }

  function onClick(e: PanelEvent): void {
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
        if (!rebuildAction(s)) return missing();
        ui.confirmRebuild = true;
        paint();
        return;
      case "rebuild-cancel":
        ui.confirmRebuild = false;
        paint();
        return;
      case "rebuild-confirm": {
        ui.confirmRebuild = false;
        void runBuilt(rebuildAction(s));
        return;
      }
      case "reveal": {
        const folder = s.context.folder;
        if (!folder) return missing();
        void perform(() => host.revealPath(folder), undefined, false);
        return;
      }
      case "copy-diagnostics":
        void perform(() => host.copyText(diagnosticsText(s)), t["notice.copied"], false);
        return;
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
      if (live && !state) root.innerHTML = renderLoading(stringsFor("en"), false, e instanceof Error ? e.message : String(e));
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
