// The data source the plugin mounts until the engine daemon exists (reel serve, task T6.2): it reports the engine as
// "not running" and never fakes pipeline data. The header's Host pill comes from the real UXP host info, so the panel
// is honest about the one thing it can know. Every command answers ok:false with a v4 result and what to do about it.
import type { ActionName } from "../../panel-ui/src/contract.ts";
import { STEP_IDS } from "../../panel-ui/src/source.ts";
import type { Language, PanelDataSource, PanelState, Result } from "../../panel-ui/src/source.ts";

export interface OfflineInfo {
  /** `require("uxp").host.version`, e.g. "26.5.2" (Application.version came back empty in the live spike) */
  hostVersion?: string | undefined;
  /** `require("uxp").host.uiLocale`, e.g. "en_US" or "ar_AE" */
  uiLocale?: string | undefined;
}

/** What to do, in the words the editor is told: plain words, never a command (Addendum C1.4, C2.2). The panel's banner
 *  carries the Start engine button; the command lives only in the log drawer and the Copy diagnostics payload. */
export const OFFLINE_HOW = "Open your Claude session to start the engine, then wait a moment.";
const OFFLINE_ERROR = "The WhyNot Cut engine is not running.";
const OFFLINE_HOW_AR = "افتح جلسة Claude لتشغيل المحرّك، ثم انتظر قليلًا.";
const OFFLINE_ERROR_AR = "محرّك WhyNot Cut لا يعمل.";

export function languageOf(uiLocale: string | null | undefined): Language {
  return typeof uiLocale === "string" && /^ar([_-]|$)/i.test(uiLocale.trim()) ? "ar" : "en";
}

export function hostDetailOf(version: string | null | undefined): string {
  const v = typeof version === "string" ? version.trim() : "";
  return v ? `Premiere Pro ${v}` : "Premiere Pro";
}

export class OfflineSource implements PanelDataSource {
  private readonly language: Language;
  private readonly hostDetail: string;

  constructor(info: OfflineInfo = {}) {
    this.language = languageOf(info.uiLocale);
    this.hostDetail = hostDetailOf(info.hostVersion);
  }

  async snapshot(): Promise<PanelState> {
    return {
      connection: { engine: "offline", claude: "unknown", host: { state: "uxp", detail: this.hostDetail } },
      client: "",
      item: "",
      language: this.language,
      editor_name: "",
      context: { project_path: null, sequence_name: null, folder: null, out_dir: null, review_mp4: null },
      pipeline: STEP_IDS.map((id) => ({ id, state: "pending" as const, progress: null, elapsed_s: null, request_id: null })),
      approval: null,
      qc: [],
      log: [],
    };
  }

  subscribe(): () => void {
    return () => {};
  }

  async approve(): Promise<Result> {
    return this.refused("approve");
  }

  async requestChanges(): Promise<Result> {
    return this.refused("request_changes");
  }

  async run(action: ActionName): Promise<Result> {
    return this.refused(action);
  }

  async rebuild(): Promise<Result> {
    return this.refused("build_project");
  }

  async cancel(): Promise<void> {}

  private refused(action: string): Result {
    const ar = this.language === "ar";
    return { ok: false, action, error: ar ? OFFLINE_ERROR_AR : OFFLINE_ERROR, how: ar ? OFFLINE_HOW_AR : OFFLINE_HOW };
  }
}
