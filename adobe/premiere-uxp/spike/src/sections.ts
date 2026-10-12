// Spike 0.1.6: the results file's two new sections and the results-document shape (one place, so the panel and the
// tests agree). `ops` keeps the Premiere probes exactly as 0.1.5 wrote them; `ui_probes` and `eco_probes` are maps of
// probe name -> the runner's OpResult ({op, ok, ms, detail, error}).
import { runProbe, type OpResult } from "./runner.ts";
import type { GuideView, RunMode, RunSummary } from "./autorun.ts";
import { ENGINE_START_URL, hideShowProbe, loopbackProbe, openExternalProbe, quitRestartNamesProbe, type EcoCtx } from "./eco-probes.ts";
import { UI_PROBES, type UiCtx } from "./ui-probes.ts";

export const UI_PROBE_NAMES = ["fonts", "svg", "box_shadow", "gradient", "kit_code"] as const;
export const ECO_PROBE_NAMES = ["quit_restart_names", "loopback", "hide_show", "open_external"] as const;

export interface Sections {
  ui_probes: Record<string, OpResult>;
  eco_probes: Record<string, OpResult>;
}

export interface ResultsDoc {
  spike: string;
  premiere: string;
  uxp: string | null;
  at: string;
  home: string | null;
  home_via: string;
  results_file: string;
  config: unknown;
  config_error: string | null;
  mode: RunMode;
  kept_project_open: boolean;
  notes: string[];
  auto_run_id?: string;
  style_guide_view?: GuideView;
  ops: OpResult[];
  ui_probes: Record<string, OpResult>;
  eco_probes: Record<string, OpResult>;
}

/** pass / fail / n/a over the ui + eco sections (the style_guide mode's summary; the other modes count `ops` as before). */
export function sectionCounts(s: Sections): Pick<RunSummary, "pass" | "fail" | "na"> {
  const all = [...Object.values(s.ui_probes), ...Object.values(s.eco_probes)];
  const pass = all.filter((o) => o.ok === true).length;
  const fail = all.filter((o) => o.ok === false).length;
  return { pass, fail, na: all.length - pass - fail };
}

/** The probe a mode does not run, recorded as n/a with the reason (so every results file has the same keys). */
export const notRun = (op: string, why: string): OpResult => ({ op, ok: null, ms: 0, detail: `not run: ${why}`, error: null });

/** Before the Premiere probes: every UI probe, then the quick ecosystem probes (names, loopback, hide/show so far). */
export async function runPreSections(
  sections: Sections,
  ui: UiCtx,
  eco: EcoCtx,
  onStep: (label: string) => void | Promise<void> = () => {},
): Promise<void> {
  for (const def of UI_PROBES) {
    await onStep(`UI probe ${def.op}`);
    sections.ui_probes[def.op] = await runProbe(def, ui);
  }
  for (const def of [quitRestartNamesProbe, loopbackProbe, hideShowProbe]) {
    await onStep(`Ecosystem probe ${def.op}`);
    sections.eco_probes[def.op] = await runProbe(def, eco);
  }
  await onStep("ui + eco probes done");
}

/** After the Premiere probes: openExternal in mode "full" only (last, so a consent dialog blocks nothing else), and the
 *  lifecycle events up to the end of the run. */
export async function runPostSections(mode: RunMode, sections: Sections, eco: EcoCtx, onStep: (label: string) => void | Promise<void> = () => {}): Promise<void> {
  if (mode === "full") {
    await onStep(`Ecosystem probe open_external (${ENGINE_START_URL})`);
    sections.eco_probes.open_external = await runProbe(openExternalProbe, eco);
  } else {
    sections.eco_probes.open_external = notRun("open_external", 'mode "full" only');
  }
  sections.eco_probes.hide_show = await runProbe(hideShowProbe, eco);
}
