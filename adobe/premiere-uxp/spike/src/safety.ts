// Path safety for the spike. The spike only ever works inside `.../Editing Plugin/whynot-test/` and never near
// real client folders (`D:/WhyNot Clients`). config.json paths that fail this are rejected: the config is then
// treated as missing, so only the read-only probes run.
import { toForwardSlashes } from "./home.ts";

/** Forward slashes, lower case, no trailing slash: the comparison form for every safety check. */
export function normPath(p: string): string {
  return toForwardSlashes(p.trim()).replace(/\/+/g, "/").replace(/\/+$/, "").toLowerCase();
}

export function isUnder(path: string, root: string): boolean {
  const p = normPath(path);
  const r = normPath(root);
  return r !== "" && (p === r || p.startsWith(`${r}/`));
}

const ABSOLUTE = /^([a-z]:)?\//;
const SCRATCH_ROOT = /(^|\/)editing plugin\/whynot-test(\/|$)/;
const CLIENTS = /(^|\/)whynot clients(\/|$)/;

/** Why `path` may not be used by the spike, or null when it is fine. */
export function scratchPathProblem(path: string): string | null {
  const n = normPath(path);
  if (n === "") return "empty path";
  if (!ABSOLUTE.test(n)) return "not an absolute path";
  if (n.split("/").includes("..")) return "contains a '..' segment";
  if (CLIENTS.test(n)) return "inside WhyNot Clients (real client files are off limits)";
  if (!SCRATCH_ROOT.test(n)) return "not under .../Editing Plugin/whynot-test/";
  return null;
}
