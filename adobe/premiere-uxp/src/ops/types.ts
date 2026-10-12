// The shapes every host op shares. An op gets its validated `data` and an OpContext and returns the readback object;
// the adapter (src/host-adapter.ts) validates that readback against the action's $defs/readback before sending it.
// A failure is thrown as an OpError: `message` is the one plain sentence the editor sees (result.error), `how` what to
// do about it (result.how). Anything else thrown becomes "Premiere failed while running <action>: <message>".
import type { premierepro as Ppro } from "@adobe/premierepro";
import type { ActionName } from "../../../panel-ui/src/contract.ts";
import type { UxpFs } from "../uxp-types.ts";

export interface FrameTiming {
  /** how often an exported PNG's size is read while it is being written */
  pollMs: number;
  /** how long a PNG may take to appear after exportSequenceFrame returned true */
  appearMs: number;
  /** how long a PNG may keep growing before the frame is reported as unfinished */
  settleMs: number;
}

export const DEFAULT_TIMING: FrameTiming = { pollMs: 100, appearMs: 15_000, settleMs: 60_000 };

/** What an op may touch. Every member is injected, so node tests run the ops on fakes. */
export interface OpEnv {
  /** `require("premierepro")`, looked up per call so a failure to load becomes an ok:false result, not a crash */
  ppro: () => Ppro;
  /** UXP `require("fs")` (forward-slash paths work there; parity P1) */
  fs: () => UxpFs;
  /** `require("uxp").host.version` (Application.version is undefined on 26.5.2; parity P2) */
  hostVersion: () => string;
  /** the plugin bundle version (manifest version) */
  bundleVersion: string;
  sleep: (ms: number) => Promise<void>;
  now: () => number;
  timing?: Partial<FrameTiming>;
}

export interface OpContext {
  env: OpEnv;
  /** the request id */
  id: string;
  /** true once the daemon cancelled this command (or the socket dropped) */
  cancelled(): boolean;
  /** throws the cancelled OpError when cancelled: call it between steps */
  throwIfCancelled(): void;
  /** one progress event for the requester (`n` of `of` steps done) */
  progress(step: string, n?: number, of?: number): void;
  /** another command is running in this adapter */
  busy(): boolean;
}

export class OpError extends Error {
  how: string | undefined;
  constructor(message: string, how?: string) {
    super(message);
    this.name = "OpError";
    this.how = how;
  }
}

export const CANCELLED = "Cancelled before it finished.";
export const CANCELLED_HOW = "Nothing else was changed. Run the command again when you want it.";

export function cancelledError(): OpError {
  return new OpError(CANCELLED, CANCELLED_HOW);
}

/** One contract action implemented with Premiere's UXP API. `exclusive` ops run one at a time (they drive Premiere's
 *  active project, sequence and playhead); the others (ping, status) answer at once, even while one runs. */
export interface Op<D = never, R extends object = object> {
  action: ActionName;
  exclusive: boolean;
  run(data: D, ctx: OpContext): Promise<R>;
}
