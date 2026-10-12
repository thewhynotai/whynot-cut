import { PROTOCOL } from "./contract.ts";
import type { PanelState } from "./source.ts";

/** Only these fields are copied: a whitelist, so a daemon that adds a port, token or URL to its state never leaks it. */
function pick(from: unknown, keys: readonly string[]): Record<string, unknown> {
  const src = (from && typeof from === "object" ? from : {}) as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  for (const k of keys) if (k in src) out[k] = src[k];
  return out;
}

function connectionOf(c: PanelState["connection"] | null | undefined): Record<string, unknown> {
  return { ...pick(c, ["engine", "claude"]), host: pick(c?.host, ["state", "detail"]) };
}

/** Which plugin build is running: the version and a build stamp (short git hash + build time), so two builds of the
 *  same version can be told apart on a live machine. The shell sets it (UiState.build). */
export interface BuildInfo {
  version: string;
  build: string;
}

/** Plain text a support person can read: what the panel shows, the context paths and the last log lines. */
export function diagnosticsText(s: PanelState, build?: BuildInfo | null): string {
  return JSON.stringify(
    {
      product: "WhyNot Cut panel",
      ...(build ? { plugin: { version: String(build.version), build: String(build.build) } } : {}),
      protocol: PROTOCOL,
      client: s.client,
      item: s.item,
      language: s.language,
      connection: connectionOf(s.connection),
      pipeline: s.pipeline.map((p) => ({ step: p.id, state: p.state, progress: p.progress ?? null, elapsed_s: p.elapsed_s ?? null })),
      context: pick(s.context, ["project_path", "sequence_name", "folder", "out_dir", "review_mp4"]),
      approval_pending: s.approval !== null,
      qc: s.qc.map((q) => ({ t_s: q.t_s, verdict: q.verdict, label: q.label })),
      log: s.log.slice(-30),
    },
    null,
    2,
  );
}
