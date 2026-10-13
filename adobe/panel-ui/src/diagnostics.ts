import { PROTOCOL } from "./contract.ts";
import type { PanelState } from "./source.ts";

// Commands live here and in the log drawer only (Addendum C1.4): the editor's screen shows one plain sentence and one fix
// button, never a command. The Copy diagnostics payload names the command that fixes the link problem, so whoever
// helps the editor (support, or the editor's Claude session) can run it.

/** The command that fixes each link diagnosis (DaemonSource.diagnosis code): the engine is not there -> start it; it is
 *  there but refuses -> doctor. Shown nowhere on screen; it goes into diagnostics and DaemonSource's log line. */
export const LINK_FIX_COMMAND: Readonly<Record<string, string>> = {
  no_engine: "reel serve --ensure",
  down: "reel serve --ensure",
  unreachable: "reel serve --ensure",
  bad_engine_json: "reel serve --ensure",
  auth: "reel serve --ensure",
  no_welcome: "reel serve --ensure",
  lost: "reel serve --ensure",
  refused_host: "reel doctor",
  refused_busy: "reel doctor",
  refused: "reel doctor",
  protocol: "reel doctor",
  too_large: "reel doctor",
  blocked: "reel serve --status",
};

/** What "Start engine" will do through the launcher (the whynotcut:// scheme, not wired yet): today it is only named
 *  in the log line the button writes. */
export const START_ENGINE_COMMAND = "reel serve --ensure";

/** The fix command for a link code, or null (connecting, connected, stopped, an unknown code). */
export function linkFixCommand(code: unknown): string | null {
  return typeof code === "string" && Object.prototype.hasOwnProperty.call(LINK_FIX_COMMAND, code) ? LINK_FIX_COMMAND[code]! : null;
}

/** A Result code (an extra field on the Result) for an answer that is the same every time it is asked, e.g. an intent the
 *  engine has no panel side for yet (serve/app.py NOT_YET): the panel offers Copy diagnostics, never Try again. */
export const NOT_YET_CODE = "NOT_YET";

/** The token scrub for every log line (DaemonSource's and the panel's own): the engine's token, when known, and any
 *  token-looking run (64 hex digits, the engine.json token's shape) become "[token]", so a text that quotes a token
 *  never puts it in the log drawer or the Copy diagnostics payload. */
export function scrubToken(text: string, token?: string | null): string {
  const known = token ? text.split(token).join("[token]") : text;
  return known.replace(/(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])/gi, "[token]");
}

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

/** Plain text a support person can read: what the panel shows, the context paths, the link diagnosis with the command
 *  that fixes it, and the last log lines. */
export function diagnosticsText(s: PanelState, build?: BuildInfo | null, link?: { code: string } | null): string {
  const code = link && typeof link.code === "string" ? link.code.slice(0, 64) : null;
  const fix = linkFixCommand(code);
  return JSON.stringify(
    {
      product: "WhyNot Cut panel",
      ...(build ? { plugin: { version: String(build.version), build: String(build.build) } } : {}),
      protocol: PROTOCOL,
      client: s.client,
      item: s.item,
      language: s.language,
      connection: connectionOf(s.connection),
      ...(code ? { link: { code, ...(fix ? { fix } : {}) } } : {}),
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
