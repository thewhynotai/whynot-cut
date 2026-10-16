// Perf marks of the panel (Addendum G2 hardening H3; budgets S1 first usable state <= 1.5 s, S2 click -> paint
// <= 100 ms). A PerfRecorder keeps a bounded buffer of {mark, t, ms?, rid?}; DaemonSource sends it to `reel serve` in
// `perf` batches (session.schema.json perf / perf_mark), only to a daemon whose welcome lists "perf", and the daemon
// appends them to <engine home>/logs/perf.jsonl, which `reel perf-report` reads. Nothing but these four keys leaves the
// panel: a mark from the fixed list, a time, a duration and a sample id (never a token, a path or a name).
//   panel.boot        the recorder is made (DaemonSource is constructed when the panel starts)
//   panel.first_paint mount put its first view on screen (the loading view)
//   link.welcome      the daemon accepted the hello (the first time)
//   link.first_state  the first engine state arrived
//   panel.usable      that state is on screen (S1 = its ms)
//   ui.click/ui.paint a sampled click and the first paint its handler made (S2 = ui.paint's ms); a click whose handler
//                     painted nothing records nothing
// The boot marks are kept once each and carry their ms since panel.boot. A source without a recorder (the mock, the
// offline source, the tests) gets NO_PERF: mount's calls do nothing.

export const PERF_MARKS = ["panel.boot", "panel.first_paint", "link.welcome", "link.first_state", "panel.usable", "ui.click", "ui.paint"] as const;
export type PerfMarkName = (typeof PERF_MARKS)[number];

export interface PerfMark {
  mark: PerfMarkName;
  /** epoch ms */
  t: number;
  /** the duration this mark closes, ms */
  ms?: number;
  /** pairs a ui.click with its ui.paint */
  rid?: string;
}

/** marks in one `perf` message (session.schema.json perf.marks maxItems) */
export const PERF_BATCH_MAX = 50;
/** marks kept while the daemon does not take them; later ones are dropped (counted) */
export const PERF_BUFFER_MAX = 200;
/** the share of clicks that are timed */
export const UI_SAMPLE_RATE = 0.2;
const MS_MAX = 3_600_000;
const RID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$/;
const ONCE: readonly PerfMarkName[] = ["panel.boot", "panel.first_paint", "link.welcome", "link.first_state", "panel.usable"];

export interface PerfSink {
  mark(mark: PerfMarkName, opts?: { ms?: number; rid?: string }): void;
  /** a click starts: timed when sampled */
  click(): void;
  /** a paint: closes the sampled click before it (ui.click + ui.paint) */
  painted(): void;
  /** the click's handler returned: a sampled click that painted nothing is forgotten */
  clickDone(): void;
}

export const NO_PERF: PerfSink = { mark() {}, click() {}, painted() {}, clickDone() {} };

/** The recorder a source carries (DaemonSource.perf), else the no-op. */
export function perfOf(source: unknown): PerfSink {
  const p = typeof source === "object" && source !== null ? (source as { perf?: unknown }).perf : undefined;
  return typeof p === "object" && p !== null && typeof (p as PerfSink).mark === "function" ? (p as PerfSink) : NO_PERF;
}

const round1 = (n: number) => Math.round(n * 10) / 10;

export class PerfRecorder implements PerfSink {
  private readonly now: () => number;
  private readonly random: () => number;
  private readonly sampleRate: number;
  private readonly boot: number;
  private buf: PerfMark[] = [];
  private seen = new Set<PerfMarkName>();
  private pending: { rid: string; t: number } | null = null;
  private seq = 0;
  /** marks dropped because the buffer was full */
  dropped = 0;

  constructor(opts: { now: () => number; random?: () => number; sampleRate?: number }) {
    this.now = opts.now;
    this.random = opts.random ?? Math.random;
    this.sampleRate = opts.sampleRate ?? UI_SAMPLE_RATE;
    this.boot = this.now();
    this.mark("panel.boot");
  }

  get size(): number {
    return this.buf.length;
  }

  has(mark: PerfMarkName): boolean {
    return this.seen.has(mark);
  }

  mark(mark: PerfMarkName, opts: { ms?: number; rid?: string } = {}): void {
    if (!(PERF_MARKS as readonly string[]).includes(mark)) return;
    if (ONCE.includes(mark)) {
      if (this.seen.has(mark)) return;
    }
    this.seen.add(mark);
    const t = this.now();
    const ms = opts.ms ?? (ONCE.includes(mark) && mark !== "panel.boot" ? t - this.boot : undefined);
    const m: PerfMark = { mark, t: Math.round(t) };
    if (typeof ms === "number" && Number.isFinite(ms) && ms >= 0 && ms <= MS_MAX) m.ms = round1(ms);
    if (typeof opts.rid === "string" && RID_RE.test(opts.rid)) m.rid = opts.rid;
    if (this.buf.length >= PERF_BUFFER_MAX) {
      this.dropped++;
      return;
    }
    this.buf.push(m);
  }

  click(): void {
    let r = 1;
    try {
      r = this.random();
    } catch {
      r = 1;
    }
    this.pending = Number.isFinite(r) && r < this.sampleRate ? { rid: `c-${++this.seq}`, t: this.now() } : null;
  }

  painted(): void {
    const p = this.pending;
    if (!p) return;
    this.pending = null;
    const ms = this.now() - p.t;
    this.buf.length < PERF_BUFFER_MAX ? this.buf.push({ mark: "ui.click", t: Math.round(p.t), rid: p.rid }) : this.dropped++;
    this.mark("ui.paint", { ms, rid: p.rid });
  }

  clickDone(): void {
    this.pending = null;
  }

  /** Up to max marks, oldest first, removed from the buffer. */
  take(max = PERF_BATCH_MAX): PerfMark[] {
    return this.buf.splice(0, Math.max(0, Math.min(max, PERF_BATCH_MAX)));
  }
}
