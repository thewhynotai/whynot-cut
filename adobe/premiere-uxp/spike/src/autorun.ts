// Hands-free auto-run (spike 0.1.5). On panel load and then every POLL_MS while the panel is open, look for
// <spike dir>/run-request.json = {"id": "<string>", "mode": "full" | "keep_open", "requested_at": "<iso>"}.
// A fresh request with an unseen id is claimed, run once, and answered with run-done-<id>.json. Claude writes the
// request and reads the done file + results file; nobody clicks. Pure logic over injected fs / clock / run, so the
// tests drive it with fakes. Nothing in here may throw out of poll(): a bad request must never crash the panel.
import { canRename, readText, removeFile, renameFile, statOf, writeText } from "./fsutil.ts";
import type { UxpFs } from "../../src/uxp-types.ts";

export const POLL_MS = 5000;
export const STALE_MS = 30 * 60 * 1000;

export type RunMode = "full" | "keep_open";

export interface RunSummary {
  results_file: string | null;
  /** the run completed and its results file was written */
  ok: boolean;
  pass: number;
  fail: number;
  na: number;
  /** only when ok is false */
  error?: string;
}

export interface AutoRunDeps {
  fs: UxpFs;
  /** `<home>/.whynot-cut/uxp-spike` */
  dir: string;
  now: () => number;
  /** a run (a button, or an earlier auto-run) is in progress */
  isBusy: () => boolean;
  run: (mode: RunMode, id: string) => Promise<RunSummary>;
  setStatus: (text: string) => void;
  /** arms one timer, returns its cancel function */
  schedule: (fn: () => void, ms: number) => () => void;
}

export type PollOutcome =
  | { kind: "none" }
  | { kind: "busy" }
  | { kind: "waiting" }
  | { kind: "malformed"; error: string }
  | { kind: "stale"; id: string }
  | { kind: "duplicate"; id: string }
  | { kind: "claim_failed"; id: string; error: string }
  | { kind: "ran"; id: string; summary: RunSummary }
  | { kind: "error"; error: string };

export interface AutoRunner {
  poll(): Promise<PollOutcome>;
  /** first poll now (panel load), then every POLL_MS; resolves when the first poll has finished */
  start(): Promise<void>;
  stop(): void;
  /** resolves when the poll in flight (if any) has finished */
  idle(): Promise<void>;
}

interface ParsedRequest {
  id: string;
  mode: RunMode;
  requested_at: string;
  requestedMs: number;
}

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** Validates a parsed request; returns the problem or the request. */
function validate(value: unknown): ParsedRequest | string {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return "the request is not a JSON object";
  const r = value as Record<string, unknown>;
  if (typeof r.id !== "string" || !SAFE_ID.test(r.id)) return '"id" must be a string of letters, digits, ".", "_" or "-" (max 64, starting with a letter or digit)';
  if (r.mode !== "full" && r.mode !== "keep_open") return '"mode" must be "full" or "keep_open"';
  if (typeof r.requested_at !== "string") return '"requested_at" must be an ISO time string';
  const requestedMs = Date.parse(r.requested_at);
  if (!Number.isFinite(requestedMs)) return '"requested_at" is not a valid ISO time';
  return { id: r.id, mode: r.mode, requested_at: r.requested_at, requestedMs };
}

export function createAutoRunner(deps: AutoRunDeps): AutoRunner {
  const { fs, dir } = deps;
  const requestPath = `${dir}/run-request.json`;
  const ran = new Set<string>();
  const badHandled = new Set<string>();
  let pendingBad: string | null = null;
  let polling = false;
  let current: Promise<unknown> = Promise.resolve();
  let cancel: (() => void) | null = null;
  let stopped = true;

  const iso = (ms: number) => new Date(ms).toISOString();

  /** Rename, else copy + delete. Returns false when the file could not be moved out of the way. */
  async function moveAside(from: string, to: string): Promise<boolean> {
    try {
      await renameFile(fs, from, to);
      return true;
    } catch {
      // fall through to copy + delete
    }
    try {
      await writeText(fs, to, await readText(fs, from));
      await removeFile(fs, from);
      return true;
    } catch {
      return false;
    }
  }

  async function alreadySeen(id: string): Promise<boolean> {
    if (ran.has(id)) return true;
    for (const name of [`run-request.${id}.claimed`, `run-claimed-${id}.json`, `run-done-${id}.json`]) {
      if ((await statOf(fs, `${dir}/${name}`)).exists) return true;
    }
    return false;
  }

  /** Claim by rename; else write run-claimed-<id>.json and delete the request. null = claimed, string = why not. */
  async function claim(id: string): Promise<string | null> {
    try {
      await renameFile(fs, requestPath, `${dir}/run-request.${id}.claimed`);
      return null;
    } catch {
      // no rename here (or it failed): leave a claim file, then try to remove the request
    }
    try {
      await writeText(fs, `${dir}/run-claimed-${id}.json`, JSON.stringify({ id, claimed_at: iso(deps.now()) }, null, 2));
    } catch (e) {
      return errText(e);
    }
    try {
      await removeFile(fs, requestPath);
    } catch {
      // the claim file is what stops a re-run; the leftover request is ignored by id
    }
    return null;
  }

  async function writeDone(id: string, body: Record<string, unknown>): Promise<void> {
    const path = `${dir}/run-done-${id}.json`;
    const text = JSON.stringify(body, null, 2);
    if (canRename(fs)) {
      try {
        const tmp = `${path}.tmp`;
        await writeText(fs, tmp, text);
        await renameFile(fs, tmp, path);
        return;
      } catch {
        // fall back to a direct write
      }
    }
    try {
      await writeText(fs, path, text);
    } catch (e) {
      deps.setStatus(`Auto-run ${id} finished but run-done-${id}.json could not be written: ${errText(e)}`);
    }
  }

  async function reportMalformed(text: string, error: string, id?: string): Promise<PollOutcome> {
    badHandled.add(text);
    pendingBad = null;
    const stamp = deps.now();
    const moved = `${dir}/run-request.bad-${stamp}.json`;
    const didMove = await moveAside(requestPath, moved);
    try {
      await writeText(
        fs,
        `${dir}/run-error-${stamp}.json`,
        JSON.stringify({ error, at: iso(stamp), ...(id ? { id } : {}), request_file: didMove ? moved : requestPath, raw: text.slice(0, 500) }, null, 2),
      );
    } catch {
      // nothing more to do; the status line still says it
    }
    deps.setStatus(`Auto-run request malformed: ${error}${didMove ? ` (moved to ${moved})` : ""}`);
    return { kind: "malformed", error };
  }

  async function pollOnce(): Promise<PollOutcome> {
    if (deps.isBusy()) return { kind: "busy" };
    if (!(await statOf(fs, requestPath)).exists) return { kind: "none" };
    let text: string;
    try {
      text = await readText(fs, requestPath);
    } catch (e) {
      return { kind: "error", error: `cannot read run-request.json: ${errText(e)}` };
    }
    if (badHandled.has(text)) return { kind: "none" };

    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      // maybe the writer is mid-write: only give up when the very same text is still there one poll later
      if (pendingBad !== text) {
        pendingBad = text;
        return { kind: "waiting" };
      }
      return reportMalformed(text, `not valid JSON (${errText(e)})`);
    }
    pendingBad = null;
    const req = validate(parsed);
    if (typeof req === "string") {
      const maybeId = (parsed as { id?: unknown } | null)?.id;
      return reportMalformed(text, req, typeof maybeId === "string" && SAFE_ID.test(maybeId) ? maybeId : undefined);
    }

    const { id, mode } = req;
    if (deps.now() - req.requestedMs > STALE_MS) {
      await moveAside(requestPath, `${dir}/run-request.${id}.stale`);
      deps.setStatus(`Auto-run ${id} ignored: stale (requested ${req.requested_at}, more than 30 minutes ago)`);
      return { kind: "stale", id };
    }
    if (await alreadySeen(id)) {
      if (await moveAside(requestPath, `${dir}/run-request.${id}.duplicate`)) deps.setStatus(`Auto-run ${id} ignored: this id already ran`);
      return { kind: "duplicate", id };
    }

    const why = await claim(id);
    if (why !== null) {
      deps.setStatus(`Auto-run ${id} could not claim the request (${why}); not run`);
      return { kind: "claim_failed", id, error: why };
    }
    ran.add(id);
    const startedAt = iso(deps.now());
    deps.setStatus(`Auto-run ${id} claimed - running ${mode}`);
    let summary: RunSummary;
    try {
      summary = await deps.run(mode, id);
    } catch (e) {
      summary = { results_file: null, ok: false, pass: 0, fail: 0, na: 0, error: `run failed: ${errText(e)}` };
    }
    await writeDone(id, {
      id,
      results_file: summary.results_file,
      ok: summary.ok,
      pass: summary.pass,
      fail: summary.fail,
      na: summary.na,
      started_at: startedAt,
      finished_at: iso(deps.now()),
      ...(summary.ok || !summary.error ? {} : { error: summary.error }),
    });
    deps.setStatus(
      summary.ok
        ? `Auto-run ${id} done: ${summary.pass} pass, ${summary.fail} fail, ${summary.na} n/a. Results: ${summary.results_file}`
        : `Auto-run ${id} finished with a problem: ${summary.error ?? "results file not written"}`,
    );
    return { kind: "ran", id, summary };
  }

  async function poll(): Promise<PollOutcome> {
    if (polling) return { kind: "busy" };
    polling = true;
    try {
      return await pollOnce();
    } catch (e) {
      return { kind: "error", error: errText(e) };
    } finally {
      polling = false;
    }
  }

  function arm(): void {
    if (stopped) return;
    cancel = deps.schedule(() => {
      if (stopped) return;
      current = poll().finally(arm);
    }, POLL_MS);
  }

  return {
    poll,
    async start() {
      stopped = false;
      current = poll().finally(arm);
      await current;
    },
    stop() {
      stopped = true;
      cancel?.();
      cancel = null;
    },
    async idle() {
      await current;
    },
  };
}
