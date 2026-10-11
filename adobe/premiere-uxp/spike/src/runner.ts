// Probe runner: every probe runs in its own try/catch with its own timing and a timeout. Nothing thrown by a
// probe (or by the progress callback) ever escapes - a failing probe is recorded as ok:false with message + stack.

export interface ProbeOutcome {
  /** true = works, false = does not work, null = not decided (skipped / pending something external). */
  ok: boolean | null;
  detail: unknown;
}

export interface ProbeDef<C> {
  op: string;
  timeoutMs?: number;
  run: (ctx: C) => Promise<ProbeOutcome>;
}

export interface OpResult {
  op: string;
  ok: boolean | null;
  ms: number;
  detail: unknown;
  error: string | null;
  stack?: string;
}

export const DEFAULT_TIMEOUT_MS = 90_000;

/** JSON-serialisable copy of anything a probe returns (cycles, bigint, functions, undefined, Errors). */
export function jsonSafe(value: unknown): unknown {
  const seen = new WeakSet<object>();
  const text = JSON.stringify(value, (_key, v: unknown) => {
    if (typeof v === "bigint") return v.toString();
    if (typeof v === "function") return `[function ${v.name || "anonymous"}]`;
    if (typeof v === "symbol") return v.toString();
    if (v instanceof Error) return { name: v.name, message: v.message, stack: v.stack };
    if (v !== null && typeof v === "object") {
      if (seen.has(v)) return "[circular]";
      seen.add(v);
    }
    return v;
  });
  return text === undefined ? null : JSON.parse(text);
}

function describe(err: unknown): { message: string; stack?: string } {
  if (err instanceof Error) return { message: err.message, stack: err.stack };
  if (err && typeof err === "object" && "message" in err) {
    const e = err as { message: unknown; stack?: unknown };
    return { message: String(e.message), stack: typeof e.stack === "string" ? e.stack : undefined };
  }
  return { message: String(err) };
}

export async function runProbe<C>(def: ProbeDef<C>, ctx: C, now: () => number = Date.now): Promise<OpResult> {
  const started = now();
  const timeoutMs = def.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error(`timed out after ${timeoutMs} ms`)), timeoutMs);
    });
    const outcome = await Promise.race([Promise.resolve().then(() => def.run(ctx)), timeout]);
    return { op: def.op, ok: outcome.ok, ms: now() - started, detail: jsonSafe(outcome.detail), error: null };
  } catch (err) {
    const { message, stack } = describe(err);
    return { op: def.op, ok: false, ms: now() - started, detail: null, error: message, ...(stack ? { stack } : {}) };
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

export async function runAll<C>(
  defs: ProbeDef<C>[],
  ctx: C,
  onProgress?: (done: OpResult, all: OpResult[]) => void | Promise<void>,
): Promise<OpResult[]> {
  const results: OpResult[] = [];
  for (const def of defs) {
    const r = await runProbe(def, ctx);
    results.push(r);
    try {
      await onProgress?.(r, results);
    } catch {
      // progress reporting (UI / results file) must never abort the run
    }
  }
  return results;
}
