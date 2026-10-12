// Small Premiere and path helpers the ops share. Path facts (docs/adobe/uxp-parity.md fact 1): Premiere reports
// project paths as `\\?\D:/...`; every readback strips that prefix (cleanPath) and gives the native form; Project.open
// and exportSequenceFrame need native backslash paths (nativePath); UXP fs works with forward slashes (fsPath).
import type { premierepro as Ppro, Project, Sequence } from "@adobe/premierepro";
import type { UxpFs, UxpStats } from "../uxp-types.ts";
import { cleanPath, nativePath } from "../uxp-host.ts";
import { OpError } from "./types.ts";
import type { OpEnv } from "./types.ts";

export { cleanPath, nativePath };

/** A Windows path (drive letter or UNC share) once the long-path prefix is gone. */
export function isWindowsPath(p: string): boolean {
  return /^(?:[A-Za-z]:[\\/]|\\\\|\/\/)/.test(cleanPath(p));
}

/** The native OS path of something Premiere reported: no `\\?\`, backslashes on Windows. */
export function reportedPath(p: string): string {
  return nativePath(p);
}

/** The form UXP's fs takes: no long-path prefix, forward slashes. */
export function fsPath(p: string): string {
  return cleanPath(p).replace(/\\/g, "/");
}

/** Path identity: no prefix, forward slashes, no trailing slash; Windows paths compare case-insensitively. */
export function pathKey(p: string): string {
  const k = fsPath(p).replace(/\/+$/, "");
  return isWindowsPath(p) ? k.toLowerCase() : k;
}

export function samePath(a: string, b: string): boolean {
  return pathKey(a) === pathKey(b);
}

export function getPpro(env: OpEnv): Ppro {
  try {
    const ppro = env.ppro();
    if (ppro) return ppro;
  } catch {
    // fall through
  }
  throw new OpError("Premiere's scripting API is not available to the WhyNot Cut panel.", "Restart Premiere Pro, then reopen the WhyNot Cut panel.");
}

/** The active project, or undefined when none is open (getActiveProject may resolve empty or throw). */
export async function activeProject(ppro: Ppro): Promise<Project | undefined> {
  try {
    return (await ppro.Project.getActiveProject()) ?? undefined;
  } catch {
    return undefined;
  }
}

export async function requireActiveProject(ppro: Ppro): Promise<Project> {
  const p = await activeProject(ppro);
  if (!p) throw new OpError("There is no open project: open a project in Premiere first.", "Open the item's project in Premiere, then run the command again.");
  return p;
}

/** Every open project (one per project view, de-duplicated by path), or null when Premiere cannot list them. */
export async function openProjects(ppro: Ppro): Promise<Project[] | null> {
  try {
    const ids = await ppro.ProjectUtils.getProjectViewIds();
    const out: Project[] = [];
    const seen = new Set<string>();
    for (const id of ids ?? []) {
      const p = await ppro.ProjectUtils.getProjectFromViewId(id);
      if (!p) continue;
      const key = pathKey(String(p.path ?? ""));
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(p);
    }
    return out;
  } catch {
    return null;
  }
}

/** The open project at `path`, looking at the active project first, then every project view. */
export async function findOpenProject(ppro: Ppro, path: string): Promise<Project | undefined> {
  const active = await activeProject(ppro);
  if (active && samePath(String(active.path ?? ""), path)) return active;
  for (const p of (await openProjects(ppro)) ?? []) {
    if (samePath(String(p.path ?? ""), path)) return p;
  }
  return undefined;
}

/**
 * Make the project at `path` the active one: nothing to do when it already is; otherwise Project.open with the native
 * backslash path and no options (parity O2: the forward-slash and \\?\ forms fail), which opens it or brings an open
 * one forward. Throws an OpError naming the path when Premiere refuses.
 */
export async function activateProject(env: OpEnv, ppro: Ppro, path: string): Promise<Project> {
  const active = await activeProject(ppro);
  if (active && samePath(String(active.path ?? ""), path)) return active;
  const native = nativePath(path);
  let opened: Project | undefined;
  let why = "";
  try {
    opened = (await ppro.Project.open(native)) ?? undefined;
  } catch (e) {
    why = e instanceof Error ? e.message : String(e);
  }
  if (opened) return opened;
  if (!(await statOf(env.fs(), fsPath(path)))) {
    throw new OpError(`There is no project file at ${native}.`, "Check the path, or rebuild the project, then run the command again.");
  }
  throw new OpError(
    `Premiere could not open the project at ${native}${why ? ` (${why})` : ""}.`,
    "Look for a dialog in Premiere (scratch disks, project modified, a newer project version), dismiss it, then run the command again.",
  );
}

export async function findSequence(project: Project, name: string): Promise<Sequence> {
  const seqs = (await project.getSequences()) ?? [];
  const seq = seqs.find((s) => s.name === name);
  if (!seq) {
    throw new OpError(
      `There is no sequence named "${name}" in the project ${project.name}.`,
      "Open the item's own project (or rebuild it), then run the command again.",
    );
  }
  return seq;
}

/** Make `seq` the active sequence unless it already is (compared by name; setActiveSequence otherwise). */
export async function activateSequence(project: Project, seq: Sequence): Promise<void> {
  let current: Sequence | undefined;
  try {
    current = (await project.getActiveSequence()) ?? undefined;
  } catch {
    current = undefined;
  }
  if (current && current.name === seq.name) return;
  const ok = await project.setActiveSequence(seq);
  if (ok === false) throw new OpError(`Premiere did not make "${seq.name}" the active sequence.`, "Open the sequence in the Timeline, then run the command again.");
}

/** lstat through UXP fs (promise API, else the *Sync twin); undefined when the path does not exist. */
export async function statOf(fs: UxpFs, path: string): Promise<UxpStats | undefined> {
  try {
    if (typeof fs.lstat === "function") return await fs.lstat(path);
    if (typeof fs.lstatSync === "function") return fs.lstatSync(path);
  } catch {
    return undefined;
  }
  return undefined;
}

/** mkdir -p one segment at a time (UXP's mkdir has no guaranteed `recursive`), with fs-form paths. */
export async function ensureDir(fs: UxpFs, dir: string): Promise<void> {
  let rest = fsPath(dir).replace(/\/+$/, "");
  // the root is never created: a drive (D:), a share (//server/share) or "/"
  const root = /^\/\/[^/]+\/[^/]+/.exec(rest)?.[0] ?? /^[A-Za-z]:/.exec(rest)?.[0] ?? "";
  rest = rest.slice(root.length);
  let acc = root;
  for (const part of rest.split("/").filter(Boolean)) {
    acc = `${acc}/${part}`;
    if (await statOf(fs, acc)) continue;
    try {
      if (typeof fs.mkdir === "function") await fs.mkdir(acc);
      else if (typeof fs.mkdirSync === "function") fs.mkdirSync(acc);
    } catch (e) {
      if (!(await statOf(fs, acc))) throw e;
    }
  }
}
