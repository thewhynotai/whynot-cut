// Path safety for the spike. The spike only ever works inside `.../Editing Plugin/whynot-test/` and never near
// real client folders (`D:/WhyNot Clients`). config.json paths that fail this are rejected: the config is then
// treated as missing, so only the read-only probes run.
import { toForwardSlashes } from "./home.ts";

/**
 * Forward slashes with the Windows long-path / device prefix removed, case preserved:
 * `\\?\D:/x` and `//?/D:/x` -> `D:/x`; `\\?\UNC\srv\share` -> `//srv/share`. Premiere reports project paths this way.
 */
export function cleanPath(p: string): string {
  let s = toForwardSlashes(p.trim());
  if (/^\/\/\?\/UNC\//i.test(s)) s = `//${s.slice(8)}`;
  else if (/^\/\/\?\//.test(s)) s = s.slice(4);
  const lead = s.startsWith("//") ? "//" : "";
  return (lead + s.slice(lead.length).replace(/\/{2,}/g, "/")).replace(/(.)\/+$/, "$1");
}

/** Comparison form for every safety check: cleanPath + lower case + no trailing slash. */
export function normPath(p: string): string {
  return cleanPath(p).toLowerCase();
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
