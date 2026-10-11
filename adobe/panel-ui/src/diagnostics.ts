import { PROTOCOL } from "./contract.ts";
import type { PanelState } from "./source.ts";

/** Plain text a support person can read: what the panel shows, the context paths and the last log lines. */
export function diagnosticsText(s: PanelState): string {
  return JSON.stringify(
    {
      product: "WhyNot Cut panel",
      protocol: PROTOCOL,
      client: s.client,
      item: s.item,
      language: s.language,
      connection: s.connection,
      pipeline: s.pipeline.map((p) => ({ step: p.id, state: p.state, progress: p.progress ?? null, elapsed_s: p.elapsed_s ?? null })),
      context: s.context,
      approval_pending: s.approval !== null,
      qc: s.qc.map((q) => ({ t_s: q.t_s, verdict: q.verdict, label: q.label })),
      log: s.log.slice(-30),
    },
    null,
    2,
  );
}
