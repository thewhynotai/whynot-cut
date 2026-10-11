// Builds the host requests the panel's buttons send through PanelDataSource.run(). Pure functions so a test
// can check every payload against the v4 action schemas. null = the context needed is not there yet.
import type { ActionName, ExportFramesData, OpenProjectData, RenderReviewData } from "./contract.ts";
import type { PanelState } from "./source.ts";

export interface BuiltAction<D = object> {
  action: ActionName;
  data: D;
}

export function openProjectAction(s: PanelState): BuiltAction<OpenProjectData> | null {
  const path = s.context.project_path;
  return path ? { action: "open_project", data: { path } } : null;
}

/** times = the seconds to render; default = every QC frame of the item. */
export function exportFramesAction(s: PanelState, times?: number[]): BuiltAction<ExportFramesData> | null {
  const { sequence_name, out_dir, project_path } = s.context;
  const t = times ?? s.qc.map((q) => q.t_s);
  if (!sequence_name || !out_dir || t.length === 0) return null;
  return { action: "export_frames", data: { sequence_name, times: t, out_dir, project_path: project_path ?? null } };
}

export function renderReviewAction(s: PanelState): BuiltAction<RenderReviewData> | null {
  const { sequence_name, review_mp4 } = s.context;
  return sequence_name && review_mp4 ? { action: "render_review", data: { sequence_name, out_path: review_mp4 } } : null;
}

/**
 * Rebuild is a panel intent, not a host request: the engine turns it into a full rebuild (what
 * `reel ppro-build --force [--replace-edited]` does) and sends the host a complete build_project.
 * replace_edited is true because this is only built after the editor confirmed the edited-project warning in the panel.
 */
export interface RebuildInput {
  item: string;
  project_path: string;
  replace_edited: boolean;
}
export function rebuildInput(s: PanelState): RebuildInput | null {
  const project_path = s.context.project_path;
  return project_path ? { item: s.item, project_path, replace_edited: true } : null;
}
