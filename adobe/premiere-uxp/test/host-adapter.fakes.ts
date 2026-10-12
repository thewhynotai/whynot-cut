// Test doubles for the UXP host adapter: a fake `premierepro` built from the shapes in premierepro.d.ts 26.5.0 and the
// measured live behaviour of docs/adobe/uxp-parity.md (Project.open only takes a native backslash path, project.path
// carries the `\\?\` prefix with forward slashes, exportSequenceFrame wants a bare file name plus a backslash folder
// ending in `\` and returns false otherwise, the PNG grows on disk before it is complete), a fake UXP `fs`, a fake socket
// and the ajv contract checks (the same strictness as test/contract.test.ts).
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import type { ValidateFunction } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { cancelledError } from "../src/ops/types.ts";
import type { OpContext, OpEnv } from "../src/ops/types.ts";
import type { HostSocket } from "../src/host-adapter.ts";

// ---- contract (ajv) ---------------------------------------------------------------------------------------------

const CONTRACT_DIR = fileURLToPath(new URL("../../../whynot-cut/engine/reel/contract/", import.meta.url));
const ID_BASE = "https://thewhynot.ai/whynot-cut/contract/4/";
const ajv = new Ajv2020({ strictSchema: true, strictTypes: false, strictRequired: false, strictTuples: false, allErrors: true });
(addFormats as unknown as (a: unknown) => void)(ajv);
for (const f of readdirSync(CONTRACT_DIR).filter((n) => n.endsWith(".schema.json"))) {
  ajv.addSchema(JSON.parse(readFileSync(join(CONTRACT_DIR, f), "utf8")));
}

export function schemaFn(file: string, def?: string): ValidateFunction {
  const fn = ajv.getSchema(`${ID_BASE}${file}.schema.json${def ? `#/$defs/${def}` : ""}`);
  if (!fn) throw new Error(`no schema ${file} ${def ?? ""}`);
  return fn;
}

const errs = (fn: ValidateFunction, prefix = "") => (fn.errors ?? []).map((e) => `${prefix}${e.instancePath || "/"}: ${e.message}`);

/** A session message as the daemon validates it on receipt (session.schema.json $defs/message). */
export function sessionErrors(msg: unknown): string[] {
  const fn = schemaFn("session", "message");
  return fn(msg) ? [] : errs(fn);
}

/** The result as the router checks it (contract.validate_result): envelope + the action's readback when ok. */
export function resultErrors(res: { action?: string; ok?: boolean; readback?: unknown }): string[] {
  const env = schemaFn("result");
  const out = env(res) ? [] : errs(env);
  if (res && res.ok === true && typeof res.action === "string") {
    const rb = schemaFn(res.action, "readback");
    if (!rb(res.readback)) out.push(...errs(rb, "/readback"));
  }
  return out;
}

// ---- fake UXP fs ------------------------------------------------------------------------------------------------

/** Files keyed by the exact path string; a file's size steps through `growth` one lstat at a time (then stays). */
export class FakeFs {
  files = new Map<string, { sizes: number[]; reads: number }>();
  dirs = new Set<string>();
  calls: string[] = [];
  write(path: string, sizes: number[]): void {
    this.files.set(path, { sizes, reads: 0 });
  }
  lstat = async (path: string) => {
    this.calls.push(`lstat ${path}`);
    const f = this.files.get(path);
    if (f) {
      const size = f.sizes[Math.min(f.reads, f.sizes.length - 1)] ?? 0;
      f.reads++;
      return { size, isFile: () => true, isDirectory: () => false };
    }
    if (this.dirs.has(path)) return { size: 0, isFile: () => false, isDirectory: () => true };
    throw new Error(`ENOENT: ${path}`);
  };
  mkdir = async (path: string) => {
    this.calls.push(`mkdir ${path}`);
    this.dirs.add(path);
  };
}

// ---- fake premierepro -----------------------------------------------------------------------------------------

export interface FakeParam { displayName: string; start?: unknown; throws?: boolean }
export interface FakeComponent { match: string; display: string; params: FakeParam[] }
export interface FakeClip { name: string; components: FakeComponent[] }
export interface FakeSequenceSpec { name: string; video?: FakeClip[][]; audio?: FakeClip[][]; width?: number; height?: number }

const tick = (seconds: number) => ({ seconds, ticks: String(Math.round(seconds * 254016000000)) });

function chainOf(clip: FakeClip) {
  return {
    getComponentCount: () => clip.components.length,
    getComponentAtIndex: (i: number) => {
      const c = clip.components[i];
      if (!c) throw new Error("index out of range");
      return {
        getMatchName: async () => c.match,
        getDisplayName: async () => c.display,
        getParamCount: () => c.params.length,
        getParam: (j: number) => {
          const p = c.params[j];
          if (!p) throw new Error("param index out of range");
          return {
            displayName: p.displayName,
            getStartValue: async () => {
              if (p.throws) throw new Error("unreadable");
              return { value: { value: p.start } };
            },
          };
        },
      };
    },
  };
}

export class FakeSequence {
  name: string;
  position = 0;
  setPlayerPositionReturns = true;
  calls: string[];
  spec: FakeSequenceSpec;
  constructor(spec: FakeSequenceSpec, calls: string[]) {
    this.spec = spec;
    this.name = spec.name;
    this.calls = calls;
  }
  async getFrameSize() {
    return { x: 0, y: 0, width: this.spec.width ?? 1080, height: this.spec.height ?? 1920 };
  }
  async setPlayerPosition(t: { seconds: number }) {
    this.calls.push(`setPlayerPosition ${this.name} ${t.seconds}`);
    if (this.setPlayerPositionReturns) this.position = t.seconds;
    return this.setPlayerPositionReturns;
  }
  async getPlayerPosition() {
    return tick(this.position);
  }
  private track(kind: "video" | "audio", i: number) {
    const clips = this.spec[kind]?.[i];
    if (!clips) throw new Error(`no ${kind} track ${i}`);
    return {
      name: `${kind === "video" ? "Video" : "Audio"} ${i + 1}`,
      getTrackItems: (type: number, _empty: boolean) =>
        type !== 1
          ? []
          : clips.map((c) => ({ getName: async () => c.name, getComponentChain: async () => chainOf(c) })),
    };
  }
  async getVideoTrackCount() {
    return this.spec.video?.length ?? 0;
  }
  async getAudioTrackCount() {
    return this.spec.audio?.length ?? 0;
  }
  async getVideoTrack(i: number) {
    return this.track("video", i);
  }
  async getAudioTrack(i: number) {
    return this.track("audio", i);
  }
}

export class FakeProject {
  sequences: FakeSequence[];
  active: FakeSequence | undefined;
  saveReturns = true;
  closeReturns = true;
  closeOptions: unknown;
  /** `path` is the plain native path; Premiere reports it as \\?\D:/... (fact 1) */
  native: string;
  private pp: FakePremiere;
  constructor(native: string, seqs: FakeSequenceSpec[], pp: FakePremiere) {
    this.native = native;
    this.pp = pp;
    this.sequences = seqs.map((s) => new FakeSequence(s, pp.calls));
    this.active = this.sequences[0];
  }
  get path(): string {
    return /^[A-Za-z]:\\/.test(this.native) ? `\\\\?\\${this.native.replace(/\\/g, "/")}` : this.native;
  }
  get name(): string {
    return this.native.split(/[\\/]/).pop() ?? "";
  }
  async getSequences() {
    return this.sequences;
  }
  async getActiveSequence() {
    return this.active;
  }
  async setActiveSequence(s: FakeSequence) {
    this.pp.calls.push(`setActiveSequence ${s.name}`);
    this.active = s;
    return true;
  }
  async openSequence(s: FakeSequence) {
    this.pp.calls.push(`openSequence ${s.name}`);
    this.active = s;
    return true;
  }
  async save() {
    this.pp.calls.push(`save ${this.name}`);
    return this.saveReturns;
  }
  async close(options: unknown) {
    this.pp.calls.push(`close ${this.name}`);
    this.closeOptions = options;
    if (this.closeReturns) {
      this.pp.projects = this.pp.projects.filter((p) => p !== this);
      if (this.pp.active === this) this.pp.active = this.pp.projects[0];
    }
    return this.closeReturns;
  }
  lockedAccess(cb: () => void) {
    this.pp.calls.push("lockedAccess");
    cb();
  }
  executeTransaction(build: (ca: { addAction: (a: unknown) => boolean }) => void, label?: string) {
    this.pp.calls.push(`executeTransaction ${label}`);
    const actions: unknown[] = [];
    build({ addAction: (a) => (actions.push(a), true) });
    this.pp.transactions.push({ label, actions });
    return this.pp.transactionReturns;
  }
}

/** Projects on "disk" that Project.open can open: native path -> sequences. */
export class FakePremiere {
  calls: string[] = [];
  projects: FakeProject[] = [];
  active: FakeProject | undefined;
  disk = new Map<string, FakeSequenceSpec[]>();
  transactions: Array<{ label?: string; actions: unknown[] }> = [];
  transactionReturns = true;
  viewIdsThrow = false;
  /** sizes the exported PNG reports on successive lstat calls (it appears before it is fully written: fact 13) */
  frameGrowth = [0, 120_000, 900_000, 1_610_035];
  exportReturns: (t: number) => boolean = () => true;
  /** exportSequenceFrame returned true but nothing reached the disk */
  exportWritesNothing = false;

  fs: FakeFs;
  constructor(fs: FakeFs) {
    this.fs = fs;
  }

  addOpen(native: string, seqs: FakeSequenceSpec[], { active = true } = {}): FakeProject {
    const p = new FakeProject(native, seqs, this);
    this.projects.push(p);
    if (active || !this.active) this.active = p;
    return p;
  }

  readonly api = {
    Project: {
      getActiveProject: async () => this.active,
      open: async (path: string, options?: unknown) => {
        this.calls.push(`Project.open ${path}${options ? " +options" : ""}`);
        // measured: forward slashes and the raw \\?\ form fail with "Failed to open the project"
        if (path.includes("/") || path.startsWith("\\\\?\\")) throw new Error("Failed to open the project");
        const open = this.projects.find((p) => p.native === path);
        if (open) {
          this.active = open;
          return open;
        }
        const seqs = this.disk.get(path);
        if (!seqs) throw new Error("Failed to open the project");
        return this.addOpen(path, seqs);
      },
    },
    ProjectUtils: {
      getProjectViewIds: async () => {
        if (this.viewIdsThrow) throw new Error("not available");
        return this.projects.map((_, i) => ({ id: `guid-${i}` }));
      },
      getProjectFromViewId: async (g: { id: string }) => this.projects[Number(g.id.slice(5))],
    },
    TickTime: { createWithSeconds: (s: number) => tick(s) },
    CloseProjectOptions: class {
      opts: Record<string, boolean> = {};
      setPromptIfDirty(v: boolean) { this.opts.promptIfDirty = v; return this; }
      setSaveWorkspace(v: boolean) { this.opts.saveWorkspace = v; return this; }
      setShowCancelButton(v: boolean) { this.opts.showCancelButton = v; return this; }
      setIsAppBeingPreparedToQuit(v: boolean) { this.opts.quit = v; return this; }
    },
    Constants: { TrackItemType: { EMPTY: 0, CLIP: 1, TRANSITION: 2, PREVIEW: 3, FEEDBACK: 4 } },
    Exporter: {
      exportSequenceFrame: async (seq: FakeSequence, time: { seconds: number }, filename: string, filepath: string, w: number, h: number) => {
        this.calls.push(`export ${seq.name} ${time.seconds} ${filename} ${filepath} ${w}x${h}`);
        // measured (Q1): only a bare file name plus a backslash folder with a trailing backslash works; the rest is false
        if (/[\\/]/.test(filename) || filepath.includes("/") || !filepath.endsWith("\\")) return false;
        if (!this.exportReturns(time.seconds)) return false;
        if (!this.exportWritesNothing) this.fs.write(`${filepath.replace(/\\/g, "/")}${filename}`, this.frameGrowth);
        return true;
      },
    },
  };
}

// ---- env, socket ------------------------------------------------------------------------------------------------

export function makeEnv(over: Partial<{ ppro: unknown; fs: FakeFs; hostVersion: string }> = {}) {
  const fs = over.fs ?? new FakeFs();
  const pp = new FakePremiere(fs);
  let clock = 1_000_000;
  const sleeps: number[] = [];
  const env: OpEnv = {
    ppro: () => (over.ppro ?? pp.api) as never,
    fs: () => fs as never,
    hostVersion: () => over.hostVersion ?? "26.5.2",
    bundleVersion: "3.0.0",
    sleep: async (ms: number) => {
      sleeps.push(ms);
      clock += ms;
      // a real macrotask turn: an op that polls in a loop must not starve the test's settle()
      await new Promise((r) => setImmediate(r));
    },
    now: () => clock,
  };
  return { env, pp, fs, sleeps, advance: (ms: number) => void (clock += ms), now: () => clock };
}

export class FakeSocket implements HostSocket {
  sent: unknown[] = [];
  closed: { code?: number; reason?: string } | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  sendThrows = false;
  send(text: string): void {
    if (this.sendThrows) throw new Error("socket is closed");
    this.sent.push(JSON.parse(text));
  }
  close(code?: number, reason?: string): void {
    this.closed = { code, reason };
  }
  /** the daemon sends a message */
  deliver(msg: unknown): void {
    this.onmessage?.({ data: typeof msg === "string" ? msg : JSON.stringify(msg) } as MessageEvent);
  }
  /** the connection drops */
  drop(): void {
    this.onclose?.({ code: 1006 } as CloseEvent);
  }
  of<T = Record<string, unknown>>(type: string): T[] {
    return this.sent.filter((m) => (m as { type?: string }).type === type) as T[];
  }
}

export function request(action: string, data: unknown, id = `req-${action.replace(/_/g, "-")}`, expiresInS = 600) {
  return {
    type: "command",
    request: { protocol: 4, id, action, data, expires_at: new Date(Date.now() + expiresInS * 1000).toISOString() },
  };
}

/** Let queued microtasks and the fake sleeps run until `done()` or the step budget is spent. */
export async function settle(done: () => boolean = () => false, steps = 2000): Promise<void> {
  for (let i = 0; i < steps && !done(); i++) await new Promise((r) => setImmediate(r));
}

export const WIN_PROJECT = "D:\\0 Work\\Clients\\EP02TEST_R02\\07_premiere\\project\\EP02TEST_R02_RE_EDIT.prproj";
export const WIN_OTHER = "D:\\0 Work\\Clients\\EP02TEST_R01\\07_premiere\\project\\EP02TEST_R01_RE_EDIT.prproj";
export const SEQ = "EP02TEST_R02_RE_EDIT";

export function editClip(): FakeClip {
  return {
    name: "EP02TEST.mp4 [hold]",
    components: [
      { match: "AE.ADBE Opacity", display: "Opacity", params: [{ displayName: "Opacity", start: 100 }, { displayName: "Blend Mode", start: 18 }] },
      {
        match: "AE.ADBE Motion",
        display: "Motion",
        params: [
          { displayName: "Position", start: [0.427413, 0.5] },
          { displayName: "Scale", start: 177.77799987793 },
          { displayName: " ", start: true },
          { displayName: "Crop Left", start: 0 },
        ],
      },
      { match: "AE.ADBE Lumetri", display: "Lumetri Color", params: [{ displayName: "Look", start: { r: 1, g: 0, b: 0, a: 1 } }, { displayName: "Broken", throws: true }] },
    ],
  };
}

/** An OpContext for calling an op directly (what the adapter builds per command). */
export function opCtx(env: OpEnv, over: { busy?: boolean; cancelAfterProgress?: number } = {}) {
  const progressed: Array<{ step: string; n?: number; of?: number }> = [];
  let cancelled = false;
  const ctx: OpContext = {
    env,
    id: "test-1",
    cancelled: () => cancelled,
    throwIfCancelled: () => {
      if (cancelled) throw cancelledError();
    },
    progress: (step, n, of) => {
      progressed.push({ step, n, of });
      if (over.cancelAfterProgress !== undefined && progressed.length >= over.cancelAfterProgress) cancelled = true;
    },
    busy: () => over.busy ?? false,
  };
  return { ctx, progressed, cancel: () => void (cancelled = true) };
}
