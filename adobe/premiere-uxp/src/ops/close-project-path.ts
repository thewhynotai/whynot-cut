// close_project_path (close_project_path.schema.json): save, then close the project at a path if it is open (the
// engine closes a project before rebuilding it). Close never prompts (parity O4: CloseProjectOptions with
// promptIfDirty / saveWorkspace / showCancelButton false after an explicit save), so a failed save stops here and the
// project stays open: nothing unsaved is ever thrown away. Not open -> {closed: false, reason: "not open"}.
// `save` ("always" | "if_clean", T6.3) is accepted; UXP has no dirty flag measured yet, so both modes save first and the
// readback says dirty: null (unknown, never clean), saved: true and dirty_api: null (the engine keeps its signature check).
import { findOpenProject, getPpro, nativePath, reportedPath } from "./premiere.ts";
import { OpError } from "./types.ts";
import type { Op } from "./types.ts";

export interface CloseProjectPathData { path: string; save?: "always" | "if_clean" }
export interface CloseProjectPathReadback {
  closed: boolean;
  path?: string;
  reason?: string;
  dirty?: boolean | null;
  saved?: boolean;
  dirty_api?: string | null;
}

export const closeProjectPath: Op<CloseProjectPathData, CloseProjectPathReadback> = {
  action: "close_project_path",
  exclusive: true,
  async run(data, ctx) {
    const ppro = getPpro(ctx.env);
    const project = await findOpenProject(ppro, data.path);
    if (!project) return { closed: false, reason: "not open" };
    const path = reportedPath(String(project.path ?? "")) || nativePath(data.path);
    ctx.progress(`Saving ${path}`, 0, 2);
    if (!(await project.save())) {
      throw new OpError(`Premiere could not save ${path}, so it was left open.`, "Save the project in Premiere (File > Save), then run the command again.");
    }
    ctx.throwIfCancelled();
    ctx.progress(`Closing ${path}`, 1, 2);
    const options = new ppro.CloseProjectOptions().setPromptIfDirty(false).setSaveWorkspace(false).setShowCancelButton(false);
    const closed = await project.close(options);
    const unknown = { dirty: null, saved: true, dirty_api: null };
    return closed ? { closed: true, path, ...unknown } : { closed: false, path, reason: "Premiere did not close it", ...unknown };
  },
};
