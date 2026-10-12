// The Premiere UXP implementation of the panel's host adapter (PanelHost): the four things only the host app can do.
// Nothing here mutates the project, so none of it needs project.lockedAccess / executeTransaction: moving the playhead,
// opening a file in the Source Monitor, opening a folder and the clipboard are not edits and do not enter the undo stack.
// Every real failure is thrown as a plain sentence; the panel shows it in its notice banner (never a blank panel).
// The two "show it to me" helpers (reveal folder, copy diagnostics) never fail: the product manifest grants clipboard
// (readAndWrite) and launchProcess (file scheme; .mp4 / .mov / .prproj and "" for folders; owner decision 2026-10-12),
// so they try navigator.clipboard / shell.openPath first and report "done"; if that throws or answers with an error
// (permission refused, consent dialog declined, an extension the manifest does not list) they fall back to a visible,
// selected box and report "shown". Neither outcome is an error.
import type { premierepro as Ppro } from "@adobe/premierepro";
import type { HostOutcome, PanelHost } from "../../panel-ui/src/host.ts";
import type { Language } from "../../panel-ui/src/source.ts";

/** `require("uxp").shell`: openPath resolves "" on success and an error text otherwise. */
export interface UxpShell {
  openPath?: (path: string, developerText?: string) => Promise<string | undefined> | string | undefined;
}

export interface UxpHostDeps {
  /** `require("premierepro")`, looked up per call so a failure to load becomes a notice, not a crash at startup */
  getPpro: () => Ppro;
  getShell: () => UxpShell | undefined;
  /** the async clipboard write, or undefined when it is not there; it may also throw (permission refused) */
  clipboardWriteText: ((text: string) => Promise<void>) | undefined;
  /** show text the editor can copy by hand (title is already in the panel's language) */
  showText: (text: string, title: string, closeLabel: string) => void;
  language: () => Language;
}

const EN = {
  badTime: "That time is not valid.",
  noProject: "Open a project in Premiere first.",
  noSequence: "There is no active sequence. Open the item's sequence in the Timeline first.",
  notMoved: "Premiere did not move the playhead.",
  noMonitor: "Premiere could not open that file in the Source Monitor.",
  openWhy: "WhyNot Cut wants to open this location on your computer.",
  copyTitle: "Copy this text (it is selected: press Ctrl+C, or Cmd+C on a Mac)",
  pathTitle: "Folder path (it is selected: press Ctrl+C, or Cmd+C on a Mac, to copy it)",
  close: "Close",
};
const AR: typeof EN = {
  badTime: "هذا الوقت غير صالح.",
  noProject: "افتح مشروعًا في Premiere أولًا.",
  noSequence: "لا يوجد تسلسل نشط. افتح تسلسل العنصر في الخط الزمني أولًا.",
  notMoved: "لم يحرّك Premiere مؤشر التشغيل.",
  noMonitor: "تعذّر على Premiere فتح هذا الملف في شاشة المصدر.",
  openWhy: "يريد WhyNot Cut فتح هذا الموقع على جهازك.",
  copyTitle: "انسخ هذا النص (محدّد الآن: اضغط Ctrl+C أو Cmd+C على Mac)",
  pathTitle: "مسار المجلد (محدّد الآن: اضغط Ctrl+C أو Cmd+C على Mac لنسخه)",
  close: "إغلاق",
};

/** Premiere returns paths with a Windows long-path prefix (`\\?\D:/...`); editors should never see it. */
export function cleanPath(p: string): string {
  const unc = /^(?:\\\\\?\\|\/\/\?\/)UNC[\\/]/i;
  if (unc.test(p)) return "\\\\" + p.replace(unc, "");
  return p.replace(/^(?:\\\\\?\\|\/\/\?\/)/, "");
}

/**
 * The path as the host APIs want it: no long-path prefix, and backslashes for a Windows path (a drive letter or a UNC
 * share, also when written //server/share). Live parity: Project.open and exportSequenceFrame only work with backslash
 * paths; macOS paths are left alone.
 */
export function nativePath(p: string): string {
  const clean = cleanPath(p);
  return /^(?:[A-Za-z]:[\\/]|\\\\|\/\/)/.test(clean) ? clean.replace(/\//g, "\\") : clean;
}

/** PanelHost with every method async (the adapter always awaits Premiere), so callers and tests can await rejections. */
export interface UxpPanelHost extends PanelHost {
  setPlayerPosition(t_s: number): Promise<void>;
  openInSourceMonitor(path: string): Promise<void>;
  revealPath(path: string): Promise<HostOutcome>;
  copyText(text: string): Promise<HostOutcome>;
}

export function createUxpHost(deps: UxpHostDeps): UxpPanelHost {
  const t = () => (deps.language() === "ar" ? AR : EN);

  return {
    async setPlayerPosition(t_s: number): Promise<void> {
      if (typeof t_s !== "number" || !Number.isFinite(t_s) || t_s < 0) throw new Error(t().badTime);
      const ppro = deps.getPpro();
      let project: Awaited<ReturnType<typeof ppro.Project.getActiveProject>> | undefined;
      try {
        project = await ppro.Project.getActiveProject();
      } catch {
        project = undefined;
      }
      if (!project) throw new Error(t().noProject);
      let sequence: Awaited<ReturnType<typeof project.getActiveSequence>> | undefined;
      try {
        sequence = await project.getActiveSequence();
      } catch {
        sequence = undefined;
      }
      if (!sequence) throw new Error(t().noSequence);
      const moved = await sequence.setPlayerPosition(ppro.TickTime.createWithSeconds(t_s));
      if (moved === false) throw new Error(t().notMoved);
    },

    async openInSourceMonitor(path: string): Promise<void> {
      const ok = await deps.getPpro().SourceMonitor.openFilePath(nativePath(path));
      if (ok === false) throw new Error(t().noMonitor);
    },

    async revealPath(path: string): Promise<HostOutcome> {
      const native = nativePath(path);
      try {
        const shell = deps.getShell();
        const open = shell?.openPath;
        if (typeof open !== "function") throw new Error("shell.openPath is not available");
        // developerText is what Adobe's one-time consent dialog shows the editor
        const answer = await open.call(shell, native, t().openWhy);
        if (typeof answer !== "string" || answer.trim() === "") return "done";   // "" = the host opened it
      } catch {
        // refused, declined or not listed in launchProcess: fall through to the visible box
      }
      deps.showText(native, t().pathTitle, t().close);
      return "shown";
    },

    async copyText(text: string): Promise<HostOutcome> {
      try {
        if (!deps.clipboardWriteText) throw new Error("clipboard is not available");
        await deps.clipboardWriteText(text);
        return "done";
      } catch {
        // clipboard refused or missing: fall through to the visible box
      }
      deps.showText(text, t().copyTitle, t().close);
      return "shown";
    },
  };
}
