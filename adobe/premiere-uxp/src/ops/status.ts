// status (status.schema.json): what the plugin reports about itself. busy = another command is running in this
// adapter; project = the active project's native path, null when none.
import type { StatusReadback } from "../../../panel-ui/src/contract.ts";
import { PROTOCOL } from "../../../panel-ui/src/contract.ts";
import { activeProject, getPpro, reportedPath } from "./premiere.ts";
import type { Op } from "./types.ts";

export type StatusData = Record<string, never>;

export const status: Op<StatusData, StatusReadback> = {
  action: "status",
  exclusive: false,
  async run(_data, ctx) {
    const active = await activeProject(getPpro(ctx.env));
    return {
      host: "premiere",
      hostVersion: ctx.env.hostVersion(),
      bundle: ctx.env.bundleVersion,
      protocol: PROTOCOL,
      busy: ctx.busy(),
      project: active ? reportedPath(String(active.path ?? "")) : null,
    };
  },
};
