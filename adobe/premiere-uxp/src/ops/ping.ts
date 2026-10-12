// ping (ping.schema.json $defs/premiere): liveness and identity. The version is uxp.host.version (Application.version
// is undefined on 26.5.2, parity P2); UXP has no build number, so `build` is left out. project: the active project's
// native path ('' when none); projects_open: how many projects are open (null when Premiere cannot list them; never 0 with an active project).
import type { PingPremiereReadback } from "../../../panel-ui/src/contract.ts";
import { activeProject, getPpro, hostVersionOf, openProjects, reportedPath } from "./premiere.ts";
import type { Op } from "./types.ts";

export type PingData = Record<string, never>;

export const ping: Op<PingData, PingPremiereReadback> = {
  action: "ping",
  exclusive: false,
  async run(_data, ctx) {
    const ppro = getPpro(ctx.env);
    const active = await activeProject(ppro);
    const open = await openProjects(ppro);
    return {
      version: hostVersionOf(ctx.env),
      project: active ? reportedPath(String(active.path ?? "")) : "",
      // the active project is open even when the view list misses it
      projects_open: open === null ? null : Math.max(open.length, active ? 1 : 0),
    };
  },
};
