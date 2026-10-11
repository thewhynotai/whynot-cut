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
  // Only an object that is its OWN ancestor is "[circular]". The same object referenced twice (a shared, non-circular
  // reference) is serialised both times: the 0.1.2 live results must not lose data to a WeakSet "seen" check.
  const ancestors: object[] = [];
  const walk = (input: unknown): unknown => {
    const v = input;
    if (typeof v === "bigint") return v.toString();
    if (typeof v === "function") return `[function ${v.name || "anonymous"}]`;
    if (typeof v === "symbol") return v.toString();
    if (v === undefined) return undefined;
    if (v === null || typeof v !== "object") return typeof v === "number" && !Number.isFinite(v) ? null : v;
    const obj: object = v instanceof Error ? { name: v.name, message: v.message, stack: v.stack } : v;
    const withToJson = obj as { toJSON?: unknown };
    if (typeof withToJson.toJSON === "function") {
      try {
        return walk((withToJson.toJSON as () => unknown).call(obj));
      } catch {
        return String(obj);
      }
    }
    if (ancestors.includes(obj)) return "[circular]";
    ancestors.push(obj);
    try {
      if (Array.isArray(obj)) return obj.map((item: unknown) => walk(item) ?? null);
      const out: Record<string, unknown> = {};
      for (const key of Object.keys(obj)) {
        let child: unknown;
        try {
          child = (obj as Record<string, unknown>)[key];
        } catch {
          child = "[unreadable]";
        }
        const w = walk(child);
        if (w !== undefined) out[key] = w;
      }
      return out;
    } finally {
      ancestors.pop();
    }
  };
  const result = walk(value);
  return result === undefined ? null : result;
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
