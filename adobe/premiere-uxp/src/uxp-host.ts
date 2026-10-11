// The Premiere UXP implementation of the panel's host adapter (PanelHost): the four things only the host app can do.
// Nothing here mutates the project, so none of it needs project.lockedAccess / executeTransaction: moving the playhead,
// opening a file in the Source Monitor, opening a folder and the clipboard are not edits and do not enter the undo stack.
// Every failure is thrown as a plain sentence; the panel shows it in its notice banner (never a blank panel).
import type { premierepro as Ppro } from "@adobe/premierepro";
import type { PanelHost } from "../../panel-ui/src/host.ts";
import type { Language } from "../../panel-ui/src/source.ts";

/** `require("uxp").shell`: openPath resolves "" on success and an error text otherwise. */
export interface UxpShell {
  openPath?: (path: string, developerText?: string) => Promise<string | undefined> | string | undefined;
}

export interface UxpHostDeps {
  /** `require("premierepro")`, looked up per call so a failure to load becomes a notice, not a crash at startup */
  getPpro: () => Ppro;
  getShell: () => UxpShell | undefined;
  /** the async clipboard write, or undefined when the plugin has no clipboard; it may also throw (no permission) */
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
  copyTitle: "Copy this text (it is selected: press Ctrl+C, or Cmd+C on a Mac)",
  copyFailed: "The panel cannot use the clipboard here. The text is shown below: select it and copy.",
  pathTitle: "Open this folder yourself (the path is selected: press Ctrl+C, or Cmd+C on a Mac)",
  pathFailed: "The panel could not open the folder. Its path is shown below.",
  close: "Close",
};
const AR: typeof EN = {
  badTime: "هذا الوقت غير صالح.",
  noProject: "افتح مشروعًا في Premiere أولًا.",
  noSequence: "لا يوجد تسلسل نشط. افتح تسلسل العنصر في الخط الزمني أولًا.",
  notMoved: "لم يحرّك Premiere مؤشر التشغيل.",
  noMonitor: "تعذّر على Premiere فتح هذا الملف في شاشة المصدر.",
  copyTitle: "انسخ هذا النص (محدّد الآن: اضغط Ctrl+C أو Cmd+C على Mac)",
  copyFailed: "لا تستطيع اللوحة استخدام الحافظة هنا. النص ظاهر بالأسفل: حدّده وانسخه.",
  pathTitle: "افتح هذا المجلد بنفسك (المسار محدّد الآن: اضغط Ctrl+C أو Cmd+C على Mac)",
  pathFailed: "تعذّر على اللوحة فتح المجلد. مساره ظاهر بالأسفل.",
  close: "إغلاق",
};

/** Premiere returns paths with a Windows long-path prefix (`\\?\D:/...`); editors should never see it. */
export function cleanPath(p: string): string {
  const unc = /^(?:\\\\\?\\|\/\/\?\/)UNC[\\/]/i;
  if (unc.test(p)) return "\\\\" + p.replace(unc, "");
  return p.replace(/^(?:\\\\\?\\|\/\/\?\/)/, "");
}

/** PanelHost with every method async (the adapter always awaits Premiere), so callers and tests can await rejections. */
export interface UxpPanelHost extends PanelHost {
  setPlayerPosition(t_s: number): Promise<void>;
  openInSourceMonitor(path: string): Promise<void>;
  revealPath(path: string): Promise<void>;
  copyText(text: string): Promise<void>;
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
      const ok = await deps.getPpro().SourceMonitor.openFilePath(path);
      if (ok === false) throw new Error(t().noMonitor);
    },

    async revealPath(path: string): Promise<void> {
      let failure: string | null = null;
      try {
        const open = deps.getShell()?.openPath;
        if (typeof open !== "function") throw new Error("shell.openPath is not available");
        const answer = await open.call(deps.getShell(), path);
        if (typeof answer === "string" && answer.trim() !== "") failure = answer;
      } catch (e) {
        failure = e instanceof Error ? e.message : String(e);
      }
      if (failure === null) return;
      deps.showText(cleanPath(path), t().pathTitle, t().close);
      throw new Error(t().pathFailed);
    },

    async copyText(text: string): Promise<void> {
      try {
        if (!deps.clipboardWriteText) throw new Error("clipboard is not available");
        await deps.clipboardWriteText(text);
        return;
      } catch {
        // no clipboard permission in the product manifest: fall through to the visible box
      }
      deps.showText(text, t().copyTitle, t().close);
      throw new Error(t().copyFailed);
    },
  };
}
