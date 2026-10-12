// open_project (open_project.schema.json): open the project at a path, or bring it forward when it is already open.
// Project.open gets the native backslash path and no options (parity O2, measured: the forward-slash and \\?\ forms
// fail). The readback path is Premiere's own, without the \\?\ prefix. A refusal is ok:false with the path in it.
import type { OpenProjectData, OpenProjectReadback } from "../../../panel-ui/src/contract.ts";
import { activateProject, getPpro, nativePath, reportedPath } from "./premiere.ts";
import type { Op } from "./types.ts";

export const openProject: Op<OpenProjectData, OpenProjectReadback> = {
  action: "open_project",
  exclusive: true,
  async run(data, ctx) {
    const ppro = getPpro(ctx.env);
    ctx.progress(`Opening ${nativePath(data.path)}`, 0, 1);
    const project = await activateProject(ctx.env, ppro, data.path);
    return { opened: true, project: reportedPath(String(project.path ?? "")) || nativePath(data.path) };
  },
};
