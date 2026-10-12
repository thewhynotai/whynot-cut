// The spike probes. Each one is independent (own try/catch + timing via runner.ts) and records what actually
// happened in `detail` - nothing here is assumed to work. Match names are discovered at runtime, never hard-coded
// guesses: the component chain is dumped into `detail` and components are picked by regex on match/display name.
import type {
  Component,
  CompoundAction,
  PointF,
  Project,
  ProjectItem,
  Sequence,
  VideoClipTrackItem,
  VideoComponentChain,
  premierepro as Ppro,
} from "@adobe/premierepro";
import { baseName, ensureDir, readText, statOf, writeText } from "./fsutil.ts";
import { toForwardSlashes } from "./home.ts";
import { cleanPath, isUnder, normPath, scratchPathProblem } from "./safety.ts";
import { jsonSafe, type ProbeDef, type ProbeOutcome } from "./runner.ts";
import type { UxpFs, UxpModule, UxpOs } from "../../src/uxp-types.ts";

/** The product's undo label. In the spike ONLY undo_transaction uses it (see txLabel). */
export const UNDO_LABEL = "WhyNot Cut build";

let currentOp = "spike";
/** Every other spike transaction is labelled with its probe, so Ctrl+Z after a run undoes undo_transaction, not a later probe. */
function txLabel(): string {
  return `WNC spike: ${currentOp}`;
}

/** Set by the UI: "Run (keep project open)" skips save_close_open so Edit > Undo can be inspected afterwards. */
export const skipSaveCloseOpen = { value: false };

export interface SpikeConfig {
  xml_path: string;
  work_dir: string;
  ws_url?: string;
  still_png?: string;
  /** opt-in: try EncoderManager.exportSequence (may start Media Encoder) */
  encoder_export?: boolean;
}

export interface TargetClip {
  clip: VideoClipTrackItem;
  trackIndex: number;
  source: "placed still" | "existing clip";
}

export interface Ctx {
  ppro: Ppro;
  fs: UxpFs;
  uxp: UxpModule;
  os: UxpOs | undefined;
  home: string | null;
  homeVia: string;
  stamp: string;
  config: SpikeConfig | null;
  configError: string | null;
  project?: Project;
  projectPath?: string;
  sequence?: Sequence;
  target?: TargetClip;
  /** set by export_frame when a form worked: exports one frame at a sequence time (used by keyframe_time_basis) */
  /** test hook: shorter polling for export_frame (defaults 1.5 s after a `false` return, 10 s after `true` / the d.ts forms) */
  timing?: { shortPollMs?: number; longPollMs?: number };
  exportFrameTo?: (t: number, base: string) => Promise<{ path: string; found: boolean; bytes: number | null; returned: unknown }>;
  /** what later probes expect to find again after save/close/open */
  expect: { videoTrackName?: string; renamedVideoTrackName?: string; markerCount?: number; sequenceName?: string };
  notes: string[];
}

// ---------------------------------------------------------------------------------------------- helpers

export function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function expect(cond: unknown, message: string): asserts cond {
  if (!cond) throw new Error(message);
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

interface StepRecord {
  step: string;
  ok: boolean;
  /** ISO start time: lets a long step be matched to a modal dialog someone had to click */
  at: string;
  ms: number;
  info?: unknown;
  error?: string;
}

/** Sub-steps inside one probe: each in its own try/catch so one failure still shows what the rest did. */
class Steps {
  readonly steps: StepRecord[] = [];
  async run<T>(step: string, fn: () => Promise<T>): Promise<T | undefined> {
    const t0 = Date.now();
    try {
      const info = await fn();
      this.steps.push({ step, ok: true, at: new Date(t0).toISOString(), ms: Date.now() - t0, ...(info === undefined ? {} : { info: jsonSafe(info) }) });
      return info;
    } catch (e) {
      // a step can keep what it measured even when it fails: throw Object.assign(new Error(msg), { info })
      const kept = (e as { info?: unknown } | null)?.info;
      this.steps.push({ step, ok: false, at: new Date(t0).toISOString(), ms: Date.now() - t0, error: errText(e), ...(kept === undefined ? {} : { info: jsonSafe(kept) }) });
      return undefined;
    }
  }
  outcome(extra: Record<string, unknown> = {}): ProbeOutcome {
    return { ok: this.steps.length > 0 && this.steps.every((s) => s.ok), detail: { ...extra, steps: this.steps } };
  }
}

function tickSeconds(ctx: Ctx, s: number) {
  return ctx.ppro.TickTime.createWithSeconds(s);
}

/** One undoable step: every mutation goes through lockedAccess -> executeTransaction, labelled "WhyNot Cut build". */
function tx(project: Project, build: (ca: CompoundAction) => void, label: string = txLabel()): boolean {
  let result = false;
  project.lockedAccess(() => {
    result = project.executeTransaction((ca) => build(ca), label);
  });
  return result;
}

function add(ca: CompoundAction, action: Parameters<CompoundAction["addAction"]>[0]): void {
  if (!ca.addAction(action)) throw new Error("CompoundAction.addAction returned false");
}

/** Refuse any project that is not inside the validated work_dir (path compared normalised: slashes, case). */
function assertScratchProject(ctx: Ctx, project: Project): void {
  const cfg = needConfig(ctx);
  const path = project.path;
  expect(path, "the project reports no path - refusing to touch a project outside work_dir");
  expect(isUnder(path, cfg.work_dir), `refusing to touch a project outside work_dir: ${path}`);
}

/**
 * The scratch project created by create_project in THIS run - never the user's active project. Every mutating
 * probe (and save_close_open) goes through here, so a failed create_project leaves the user's project untouched.
 */
async function getProject(ctx: Ctx): Promise<Project> {
  const p = ctx.project;
  expect(p, "no scratch project: create_project did not succeed in this run (refusing to use the active project)");
  assertScratchProject(ctx, p);
  return p;
}

/** Only the sequence import_fcp7_xml created in the scratch project. */
async function getSequence(ctx: Ctx): Promise<Sequence> {
  await getProject(ctx);
  const s = ctx.sequence;
  expect(s, "no scratch sequence: import_fcp7_xml did not succeed in this run");
  return s;
}

function needConfig(ctx: Ctx): SpikeConfig {
  expect(ctx.config, `config.json not loaded: ${ctx.configError ?? "unknown reason"}`);
  return ctx.config;
}

async function dumpChain(chain: VideoComponentChain): Promise<unknown[]> {
  const out: unknown[] = [];
  const n = chain.getComponentCount();
  for (let i = 0; i < n; i++) {
    const entry: Record<string, unknown> = { index: i };
    try {
      const c = chain.getComponentAtIndex(i);
      entry.matchName = await c.getMatchName();
      entry.displayName = await c.getDisplayName();
      const params: unknown[] = [];
      const pc = c.getParamCount();
      for (let j = 0; j < pc; j++) {
        try {
          const p = c.getParam(j);
          params.push({ i: j, name: p.displayName, keyframes: await p.areKeyframesSupported(), timeVarying: p.isTimeVarying() });
        } catch (e) {
          params.push({ i: j, error: errText(e) });
        }
      }
      entry.params = params;
    } catch (e) {
      entry.error = errText(e);
    }
    out.push(entry);
  }
  return out;
}

async function findComponent(chain: VideoComponentChain, rx: RegExp): Promise<{ comp: Component; index: number; matchName: string } | null> {
  const n = chain.getComponentCount();
  for (let i = 0; i < n; i++) {
    const comp = chain.getComponentAtIndex(i);
    const matchName = await comp.getMatchName();
    const displayName = await comp.getDisplayName();
    if (rx.test(matchName) || rx.test(displayName)) return { comp, index: i, matchName };
  }
  return null;
}

function findParam(comp: Component, rx: RegExp): { param: ReturnType<Component["getParam"]>; index: number } | null {
  const n = comp.getParamCount();
  for (let i = 0; i < n; i++) {
    const param = comp.getParam(i);
    if (rx.test(param.displayName)) return { param, index: i };
  }
  return null;
}

/** Two keyframes on one numeric param: set time-varying, add both, read the list + a mid-point value back. */
async function numericKeyframes(
  ctx: Ctx,
  project: Project,
  comp: Component,
  paramRx: RegExp,
  a: { t: number; v: number },
  b: { t: number; v: number },
): Promise<Record<string, unknown>> {
  const found = findParam(comp, paramRx);
  expect(found, `no param matching ${paramRx}`);
  const { param } = found;
  const supported = await param.areKeyframesSupported();
  expect(supported, `param "${param.displayName}" reports keyframes unsupported`);
  expect(tx(project, (ca) => add(ca, param.createSetTimeVaryingAction(true))), "setTimeVarying transaction returned false");
  const kA = param.createKeyframe(a.v);
  kA.position = tickSeconds(ctx, a.t);
  const kB = param.createKeyframe(b.v);
  kB.position = tickSeconds(ctx, b.t);
  expect(
    tx(project, (ca) => {
      add(ca, param.createAddKeyframeAction(kA));
      add(ca, param.createAddKeyframeAction(kB));
    }),
    "addKeyframe transaction returned false",
  );
  const times = param.getKeyframeListAsTickTimes().map((t) => t.seconds);
  const mid = await param.getValueAtTime(tickSeconds(ctx, (a.t + b.t) / 2));
  const atA = await param.getValueAtTime(tickSeconds(ctx, a.t));
  const atB = await param.getValueAtTime(tickSeconds(ctx, b.t));
  expect(times.length >= 2, `expected >= 2 keyframes, read back ${times.length}`);
  return { param: param.displayName, set: [a, b], read_back_times_s: times, value_at_a: atA, value_at_b: atB, value_at_mid: mid, timeVarying: param.isTimeVarying() };
}

/** The project item of config.still_png: found in the root bin, imported first when it is not there yet. */
async function stillItemFor(ctx: Ctx, project: Project): Promise<ProjectItem> {
  const { ppro } = ctx;
  const stillPath = ctx.config?.still_png;
  expect(stillPath, "config.json has no still_png");
  const norm = (x: string) => toForwardSlashes(x).toLowerCase();
  const wantBase = baseName(stillPath).toLowerCase();
  const findStill = async () => {
    const root = await project.getRootItem();
    const items = await root.getItems();
    for (const item of items) {
      try {
        const media = await ppro.ClipProjectItem.cast(item).getMediaFilePath();
        if (norm(media) === norm(stillPath)) return item;
      } catch {
        // bins and sequences have no media path
      }
    }
    return items.find((i) => i.name.toLowerCase() === wantBase || i.name.toLowerCase() === wantBase.replace(/\.[^.]+$/, "")) ?? null;
  };
  let item = await findStill();
  if (!item) {
    const imported = await project.importFiles([toForwardSlashes(stillPath)], true);
    expect(imported, "importFiles(still) returned false");
    for (let i = 0; i < 20 && !item; i++) {
      item = await findStill();
      if (!item) await sleep(500);
    }
  }
  expect(item, `still not found in the project after import: ${stillPath}`);
  return item;
}

/**
 * The clip the effect/keyframe probes work on: a placed still (config.still_png) or, failing that, a clip of the
 * scratch sequence created by import_fcp7_xml (getSequence never returns anything else).
 */
async function ensureTarget(ctx: Ctx): Promise<TargetClip> {
  if (ctx.target) return ctx.target;
  const { ppro } = ctx;
  const project = await getProject(ctx);
  const seq = await getSequence(ctx);
  const vCount = await seq.getVideoTrackCount();
  expect(vCount > 0, "sequence has no video tracks");
  const stillPath = ctx.config?.still_png;
  if (stillPath) {
    try {
      const item = await stillItemFor(ctx, project);
      const editor = ppro.SequenceEditor.getEditor(seq);
      const endT = await seq.getEndTime();
      const trackIndex = vCount - 1;
      const placed = item;
      expect(tx(project, (ca) => add(ca, editor.createOverwriteItemAction(placed, endT, trackIndex, 0))), "overwrite transaction returned false");
      const track = await seq.getVideoTrack(trackIndex);
      const clips = track.getTrackItems(ppro.Constants.TrackItemType.CLIP, false);
      let best: VideoClipTrackItem | null = null;
      let bestStart = -1;
      for (const c of clips) {
        const s = (await c.getStartTime()).seconds;
        if (s > bestStart) {
          best = c;
          bestStart = s;
        }
      }
      expect(best && bestStart >= endT.seconds - 0.05, `placed still not found past the sequence end (end=${endT.seconds}s, last clip starts ${bestStart}s)`);
      ctx.target = { clip: best, trackIndex, source: "placed still" };
      return ctx.target;
    } catch (e) {
      ctx.notes.push(`still placement failed, falling back to an existing clip: ${errText(e)}`);
    }
  }
  for (let ti = 0; ti < vCount; ti++) {
    const track = await seq.getVideoTrack(ti);
    const clips = track.getTrackItems(ppro.Constants.TrackItemType.CLIP, false);
    const first = clips[0];
    if (first) {
      ctx.target = { clip: first, trackIndex: ti, source: "existing clip" };
      return ctx.target;
    }
  }
  throw new Error("no clip to probe: still placement failed and the sequence has no video clips");
}

// ---------------------------------------------------------------------------------------------- probes

const hostInfo: ProbeDef<Ctx> = {
  op: "host_info",
  run: async (ctx) => {
    // Every part is its own step, so one failing API keeps the rest. Nothing here touches the clipboard API:
    // `navigator.clipboard` THROWS on a plugin without the clipboard permission (seen live on Premiere 26.5.2).
    const steps = new Steps();
    const host = ctx.uxp.host ?? {};
    const core = await steps.run("uxp_host", async () => {
      const versions = (ctx.uxp.versions ?? {}) as Record<string, unknown>;
      // `uxp.versions` has non-enumerable properties (JSON gives {}): read the keys explicitly
      const info = {
        name: host.name,
        version: host.version,
        uiLocale: host.uiLocale,
        uxp_version: versions.uxp,
        plugin_version: versions.plugin,
        uxp_versions_keys: Object.getOwnPropertyNames(versions),
        host_keys: Object.getOwnPropertyNames(host),
      };
      expect(info.name || info.version, "uxp.host has neither name nor version");
      return info;
    });
    // Informational only: on 26.5.2 Application.version resolves to an empty value, uxp.host.version is the source.
    await steps.run("premiere_version (informational)", async () => {
      const out: Record<string, unknown> = { host_version: host.version };
      try {
        const app = ctx.ppro.Application as unknown as Record<string, unknown>;
        const raw = app.version;
        out.raw = describeValue(raw);
        const awaited = typeof raw === "function" ? await (raw as () => unknown).call(app) : await raw;
        out.awaited = describeValue(awaited);
        out.application_version = awaited;
      } catch (e) {
        out.error = errText(e);
      }
      out.value = (typeof out.application_version === "string" && out.application_version) || host.version || null;
      out.source = typeof out.application_version === "string" && out.application_version ? "Application.version" : "uxp.host.version";
      return out;
    });
    await steps.run("background_color", async () => {
      const fn = host.getBackgroundColor;
      if (typeof fn !== "function") return { get_background_color: typeof fn, note: "not available in this host" };
      return { get_background_color: "function", value: jsonSafe(fn.call(host)) };
    });
    await steps.run("theme", async () => ({
      prefers_dark: (globalThis as { matchMedia?: (q: string) => { matches: boolean } }).matchMedia?.("(prefers-color-scheme: dark)")?.matches ?? null,
    }));
    // os.release() returns a compatibility string on UXP (6.2.9200 on Windows 11): not an OS build
    await steps.run("os", async () => ({ platform: ctx.os?.platform?.(), release_compat_string: ctx.os?.release?.(), arch: ctx.os?.arch?.() }));
    await steps.run("home_and_config", async () => ({ home: ctx.home, home_via: ctx.homeVia, config_loaded: ctx.config !== null, config_error: ctx.configError }));
    await steps.run("fs_members", async () => Object.fromEntries(["readFile", "writeFile", "mkdir", "lstat", "readdir", "readFileSync", "writeFileSync", "mkdirSync", "lstatSync", "existsSync"].map((k) => [k, typeof ctx.fs[k]])));
    await steps.run("globals", async () => ({
      WebSocket: typeof (globalThis as { WebSocket?: unknown }).WebSocket,
      fetch: typeof (globalThis as { fetch?: unknown }).fetch,
      TextDecoder: typeof TextDecoder,
    }));
    await steps.run("ppro_members", async () => ({ members: Object.getOwnPropertyNames(ctx.ppro).slice(0, 120) }));
    await steps.run("active_project (read-only)", async () => {
      const active = await ctx.ppro.Project.getActiveProject();
      return active ? { name: active.name, path: active.path } : null;
    });
    // ok = the core UXP host info was readable; the other steps are diagnostics and carry their own ok flags
    return { ok: core !== undefined, detail: { steps: steps.steps } };
  },
};

const wsLoopback: ProbeDef<Ctx> = {
  op: "ws_loopback",
  timeoutMs: 20_000,
  run: async (ctx) => {
    const url = ctx.config?.ws_url;
    if (!url) return { ok: null, detail: "pending reel serve (T6.2)" };
    const WS = (globalThis as { WebSocket?: new (url: string) => WebSocket }).WebSocket;
    expect(WS, "no WebSocket global in this UXP runtime");
    const t0 = Date.now();
    return await new Promise<ProbeOutcome>((resolve) => {
      const detail: Record<string, unknown> = { url };
      let settled = false;
      const done = (ok: boolean, extra: Record<string, unknown>) => {
        if (settled) return;
        settled = true;
        try {
          ws.close();
        } catch {
          // ignore
        }
        resolve({ ok, detail: { ...detail, ...extra, total_ms: Date.now() - t0 } });
      };
      const ws = new WS(url);
      const timer = setTimeout(() => done(false, { error: "no open/reply within 8 s", opened: detail.opened === true }), 8000);
      ws.onopen = () => {
        detail.opened = true;
        detail.connect_ms = Date.now() - t0;
        ws.send(JSON.stringify({ protocol: 4, id: "spike-ping", action: "ping", data: {}, expires_at: Date.now() / 1000 + 30 }));
        // a reply is a bonus; opening the loopback socket is the thing under test
        setTimeout(() => {
          clearTimeout(timer);
          done(true, { reply: null, note: "opened, no reply within 2 s (server may not echo)" });
        }, 2000);
      };
      ws.onmessage = (ev) => {
        clearTimeout(timer);
        done(true, { reply: String((ev as MessageEvent).data).slice(0, 500), round_trip_ms: Date.now() - t0 });
      };
      ws.onerror = (ev) => {
        clearTimeout(timer);
        done(false, { error: "websocket error", event: String((ev as { message?: string }).message ?? "error") });
      };
      ws.onclose = (ev) => {
        clearTimeout(timer);
        done(detail.opened === true, { closed: true, code: (ev as CloseEvent).code, reason: (ev as CloseEvent).reason });
      };
    });
  },
};

const createProject: ProbeDef<Ctx> = {
  op: "create_project",
  // live: createProject took ~33 s on Premiere 26.5.2
  timeoutMs: 180_000,
  run: async (ctx) => {
    const cfg = needConfig(ctx);
    const workDir = toForwardSlashes(cfg.work_dir).replace(/\/+$/, "");
    const problem = scratchPathProblem(workDir);
    expect(!problem, `work_dir rejected: ${problem}`);
    await ensureDir(ctx.fs, workDir);
    const path = `${workDir}/spike-${ctx.stamp}.prproj`;
    const project = await ctx.ppro.Project.createProject(path);
    expect(project, "createProject returned nothing");
    // adopt it only if Premiere really put it under work_dir; otherwise no later probe may touch anything
    assertScratchProject({ ...ctx, project }, project);
    ctx.project = project;
    ctx.projectPath = cleanPath(project.path);
    const active = await ctx.ppro.Project.getActiveProject();
    return {
      ok: true,
      detail: {
        requested: path,
        name: project.name,
        path: project.path,
        path_raw_json: JSON.stringify(project.path),
        path_normalised: normPath(project.path),
        is_active: active ? normPath(active.path) === normPath(project.path) : false,
        file_on_disk: await statOf(ctx.fs, ctx.projectPath),
      },
    };
  },
};

const importXml: ProbeDef<Ctx> = {
  op: "import_fcp7_xml",
  timeoutMs: 180_000,
  run: async (ctx) => {
    const cfg = needConfig(ctx);
    const project = await getProject(ctx);
    const xml = toForwardSlashes(cfg.xml_path);
    const xmlProblem = scratchPathProblem(xml);
    expect(!xmlProblem, `xml_path rejected: ${xmlProblem}`);
    const xmlStat = await statOf(ctx.fs, xml);
    expect(xmlStat.exists, `xml_path does not exist: ${xml}`);
    const before = await project.getSequences();
    const beforeIds = new Set(before.map((s) => s.guid.toString()));
    const t0 = Date.now();
    const importedOk = await project.importFiles([xml], true);
    const importMs = Date.now() - t0;
    // the sequence registers late after an XML import: poll
    let fresh: Sequence[] = [];
    let all: Sequence[] = before;
    for (let i = 0; i < 40 && fresh.length === 0; i++) {
      all = await project.getSequences();
      fresh = all.filter((s) => !beforeIds.has(s.guid.toString()));
      if (fresh.length === 0) await sleep(500);
    }
    const seq = fresh[fresh.length - 1];
    expect(seq, `importFiles returned ${importedOk} but it created no new sequence in the scratch project`);
    ctx.sequence = seq;
    ctx.expect.sequenceName = seq.name;
    const detail: Record<string, unknown> = {
      xml,
      xml_bytes: xmlStat.bytes,
      importFiles_returned: importedOk,
      import_ms: importMs,
      sequences_before: before.length,
      sequences_after: all.length,
      sequence: seq.name,
      new_sequences: fresh.map((s) => s.name),
    };
    try {
      await project.setActiveSequence(seq);
      detail.set_active = true;
    } catch (e) {
      detail.set_active_error = errText(e);
    }
    try {
      const vc = await seq.getVideoTrackCount();
      const ac = await seq.getAudioTrackCount();
      const v: unknown[] = [];
      for (let i = 0; i < vc; i++) {
        const track = await seq.getVideoTrack(i);
        v.push({ index: i, name: track.name, clips: track.getTrackItems(ctx.ppro.Constants.TrackItemType.CLIP, false).length });
      }
      const a: unknown[] = [];
      for (let i = 0; i < ac; i++) {
        const track = await seq.getAudioTrack(i);
        a.push({ index: i, name: track.name, clips: track.getTrackItems(ctx.ppro.Constants.TrackItemType.CLIP, false).length });
      }
      const frame = await seq.getFrameSize();
      detail.structure = {
        video_tracks: v,
        audio_tracks: a,
        frame: { width: frame.width, height: frame.height },
        timebase: await seq.getTimebase(),
        end_s: (await seq.getEndTime()).seconds,
      };
    } catch (e) {
      detail.structure_error = errText(e);
    }
    return { ok: Boolean(importedOk) && Boolean(seq), detail };
  },
};

// ---------------------------------------------------------------------------------------------- 0.1.2 helpers

/** Type / constructor / keys / value of anything, for logging values whose shape is the question. */
function describeValue(v: unknown): Record<string, unknown> {
  const t = typeof v;
  if (v === null || v === undefined || (t !== "object" && t !== "function")) return { type: t, value: v === undefined ? "undefined" : v };
  const o = v as Record<string, unknown>;
  let json: unknown;
  try {
    json = jsonSafe(v);
  } catch {
    json = "[unserialisable]";
  }
  return { type: t, constructor: (v as { constructor?: { name?: string } }).constructor?.name, own_keys: Object.getOwnPropertyNames(v), x: o.x, y: o.y, json };
}

function pointOf(v: unknown): { x: number; y: number } | null {
  const o = v as { x?: unknown; y?: unknown } | null | undefined;
  return o && typeof o.x === "number" && typeof o.y === "number" ? { x: o.x, y: o.y } : null;
}

/** Fail a step but keep what was measured: Steps.run stores `info` of a thrown error. */
function failWith(message: string, info: unknown): never {
  throw Object.assign(new Error(message), { info });
}

function errDetail(e: unknown): Record<string, unknown> {
  const o = (e ?? {}) as { message?: unknown; name?: unknown; code?: unknown; stack?: unknown };
  return { message: errText(e), name: o.name, code: o.code, own_keys: e && typeof e === "object" ? Object.getOwnPropertyNames(e) : [], stack: typeof o.stack === "string" ? o.stack.split("\n").slice(0, 6).join("\n") : undefined };
}

async function pollFile(fs: UxpFs, path: string, maxMs: number, everyMs = 250): Promise<{ found: boolean; bytes: number | null; after_ms: number }> {
  const t0 = Date.now();
  for (;;) {
    const st = await statOf(fs, path);
    if (st.exists && (st.bytes ?? 0) > 0) return { found: true, bytes: st.bytes, after_ms: Date.now() - t0 };
    if (Date.now() - t0 >= maxMs) return { found: false, bytes: st.bytes, after_ms: Date.now() - t0 };
    await sleep(everyMs);
  }
}

/** The plugin's own temp folder: a writable folder whose path has no spaces (the d.ts example uses `C:/temp/`). */
async function tempDir(ctx: Ctx): Promise<string | null> {
  try {
    const lfs = ctx.uxp.storage?.localFileSystem as { getTemporaryFolder?: () => Promise<{ nativePath?: string }> } | undefined;
    const folder = await lfs?.getTemporaryFolder?.();
    return folder?.nativePath ? cleanPath(folder.nativePath) : null;
  } catch {
    return null;
  }
}

interface ClipWindow {
  start_s: number;
  in_s: number;
  end_s: number;
  duration_s: number;
}

async function windowOf(clip: VideoClipTrackItem): Promise<ClipWindow> {
  const start = (await clip.getStartTime()).seconds;
  const inP = (await clip.getInPoint()).seconds;
  const end = (await clip.getEndTime()).seconds;
  return { start_s: start, in_s: inP, end_s: end, duration_s: end - start };
}

const EPS = 0.02;
const within = (t: number, lo: number, hi: number) => t >= lo - EPS && t <= hi + EPS;

/** Which time window each read-back keyframe time falls into: clip-local [0,dur], media [in,in+dur], sequence [start,end]. */
export function classifyTimes(times: number[], w: ClipWindow) {
  return {
    inside_local_window: times.map((t) => within(t, 0, w.duration_s)),
    inside_media_window: times.map((t) => within(t, w.in_s, w.in_s + w.duration_s)),
    inside_sequence_window: times.map((t) => within(t, w.start_s, w.end_s)),
  };
}

/** True when the three windows (clip-local, media, sequence) are pairwise disjoint, so any landing is decisive. */
export function windowsDisjoint(w: ClipWindow): boolean {
  const local: [number, number] = [0, w.duration_s];
  const media: [number, number] = [w.in_s, w.in_s + w.duration_s];
  const seq: [number, number] = [w.start_s, w.end_s];
  const overlap = (a: [number, number], b: [number, number]) => a[0] < b[1] + EPS && b[0] < a[1] + EPS;
  return !overlap(local, media) && !overlap(local, seq) && !overlap(media, seq);
}

type Settings = Awaited<ReturnType<Sequence["getSettings"]>>;

// ---------------------------------------------------------------------------------------------- sequence_settings

const CODEC_CANDIDATES = ["Apple ProRes 422 LT", "ProRes 422 LT", "Apple ProRes 422", "Apple ProRes 422 HQ", "Apple ProRes 422 Proxy", "GoPro CineForm", "Uncompressed YUV 10 bit 4:2:2", "apcs"];

/**
 * Preview codec. The d.ts has no codec list or enum; the only value the API hands out is what getPreviewCodec()
 * returns ("Animation" on the imported sequence). So: discover what the runtime exposes, prove the setter works by
 * round-tripping the value the API returned, then try display names. Setter return values are always kept.
 */
async function previewCodecProbe(ctx: Ctx, project: Project, seq: Sequence): Promise<Record<string, unknown>> {
  const { ppro } = ctx;
  const s0 = await seq.getSettings();
  const orig = await s0.getPreviewCodec();
  const origFormat = await s0.getPreviewFileFormat();
  const names = (o: unknown, rx: RegExp) => (o && (typeof o === "object" || typeof o === "function") ? Object.getOwnPropertyNames(o).filter((n) => rx.test(n)) : []);
  const discovery = {
    orig_codec: orig,
    orig_file_format: origFormat,
    sequence_settings_static_members: names(ppro.SequenceSettings, /codec|format|preview/i),
    settings_instance_members: names(Object.getPrototypeOf(s0), /codec|format|preview/i),
    ppro_members_matching: names(ppro, /codec|preset|format/i),
    constants_members_matching: names(ppro.Constants, /codec|preview|format/i),
  };
  const attempt = async (label: string, change: (s: Settings) => Promise<unknown>) => {
    const rec: Record<string, unknown> = { label };
    const t0 = Date.now();
    try {
      const s = await seq.getSettings();
      rec.setter_returned = await change(s);
      rec.transaction_returned = tx(project, (ca) => add(ca, seq.createSetSettingsAction(s)));
      const after = await seq.getSettings();
      rec.read_codec = await after.getPreviewCodec();
      rec.read_file_format = await after.getPreviewFileFormat();
    } catch (e) {
      rec.error = errText(e);
    }
    rec.ms = Date.now() - t0;
    return rec;
  };
  const attempts: Array<Record<string, unknown>> = [];
  attempts.push(await attempt(`file format round trip "${origFormat}"`, (s) => s.setPreviewFileFormat(origFormat)));
  const round = await attempt(`codec round trip "${orig}" (the value the API returned)`, (s) => s.setPreviewCodec(orig));
  attempts.push(round);
  let accepted: string | null = null;
  for (const candidate of CODEC_CANDIDATES) {
    if (candidate === orig) continue;
    const rec = await attempt(`codec -> "${candidate}"`, (s) => s.setPreviewCodec(candidate));
    rec.wanted = candidate;
    rec.took = rec.read_codec === candidate;
    attempts.push(rec);
    if (rec.took) {
      accepted = candidate;
      attempts.push(await attempt(`restore "${orig}"`, (s) => s.setPreviewCodec(orig)));
      break;
    }
  }
  const info = { discovery, round_trip_works: round.read_codec === orig && !round.error, accepted_candidate: accepted, attempts };
  if (!info.round_trip_works) failWith("setPreviewCodec(current value) did not read back: the setter does not work as called", info);
  if (!accepted) failWith(`no candidate value took (read-back stayed "${orig}"); see attempts for each setter return value`, info);
  return info;
}

const sequenceSettings: ProbeDef<Ctx> = {
  op: "sequence_settings",
  run: async (ctx) => {
    const { ppro } = ctx;
    const project = await getProject(ctx);
    const seq = await getSequence(ctx);
    const steps = new Steps();

    const initial = await steps.run("read_all", async () => {
      const s = await seq.getSettings();
      const frame = await s.getVideoFrameRect();
      const preview = await s.getPreviewFrameRect();
      return {
        preview_codec: await s.getPreviewCodec(),
        preview_file_format: await s.getPreviewFileFormat(),
        composite_in_linear_color: await s.getCompositeInLinearColor(),
        maximum_bit_depth: await s.getMaximumBitDepth(),
        max_render_quality: await s.getMaxRenderQuality(),
        editing_mode: await s.getEditingMode(),
        video_frame_rect: { width: frame.width, height: frame.height },
        preview_frame_rect: { width: preview.width, height: preview.height },
        pixel_aspect_ratio: await s.getVideoPixelAspectRatio(),
        field_type: await s.getVideoFieldType(),
        frame_rate: s.getVideoFrameRate().value,
        audio_channel_type: await s.getAudioChannelType(),
        audio_channel_count: await s.getAudioChannelCount(),
      };
    });

    await steps.run("preview_codec: discover, round trip, try display names", () => previewCodecProbe(ctx, project, seq));

    // The engine's targets (ppro_build.py): linear colour on, 8-bit, no max render quality.
    const apply = async (label: string, change: (s: Settings) => Promise<unknown>, read: (s: Settings) => Promise<unknown>, want: unknown) => {
      const before = await read(await seq.getSettings());
      const s = await seq.getSettings();
      const setterResult = await change(s);
      expect(tx(project, (ca) => add(ca, seq.createSetSettingsAction(s))), `${label}: createSetSettingsAction transaction returned false`);
      const after = await read(await seq.getSettings());
      const info = { before, wanted: want, after, setter_returned: setterResult };
      if (JSON.stringify(after) !== JSON.stringify(want)) failWith(`${label}: read back ${JSON.stringify(after)} but wanted ${JSON.stringify(want)} (before ${JSON.stringify(before)})`, info);
      return info;
    };
    await steps.run("composite_in_linear_color=true", () => apply("compositeInLinearColor", (s) => s.setCompositeInLinearColor(true), (s) => s.getCompositeInLinearColor(), true));
    await steps.run("maximum_bit_depth=false", () => apply("maximumBitDepth", (s) => s.setMaximumBitDepth(false), (s) => s.getMaximumBitDepth(), false));
    await steps.run("max_render_quality=false", () => apply("maxRenderQuality", (s) => s.setMaxRenderQuality(false), (s) => s.getMaxRenderQuality(), false));
    await steps.run("toggle_each_bool_and_back", async () => {
      const out: Record<string, unknown> = {};
      for (const [name, get, set] of [
        ["composite_in_linear_color", (s: Settings) => s.getCompositeInLinearColor(), (s: Settings, v: boolean) => s.setCompositeInLinearColor(v)],
        ["maximum_bit_depth", (s: Settings) => s.getMaximumBitDepth(), (s: Settings, v: boolean) => s.setMaximumBitDepth(v)],
        ["max_render_quality", (s: Settings) => s.getMaxRenderQuality(), (s: Settings, v: boolean) => s.setMaxRenderQuality(v)],
      ] as const) {
        const orig = await get(await seq.getSettings());
        const flipped = !orig;
        const s1 = await seq.getSettings();
        await set(s1, flipped);
        tx(project, (ca) => add(ca, seq.createSetSettingsAction(s1)));
        const afterFlip = await get(await seq.getSettings());
        const s2 = await seq.getSettings();
        await set(s2, orig);
        tx(project, (ca) => add(ca, seq.createSetSettingsAction(s2)));
        const afterBack = await get(await seq.getSettings());
        out[name] = { orig, flipped_to: flipped, read_after_flip: afterFlip, read_after_restore: afterBack, ok: afterFlip === flipped && afterBack === orig };
        expect(afterFlip === flipped && afterBack === orig, `${name}: toggle did not round-trip`);
      }
      return out;
    });
    await steps.run("preview_frame_rect=video_frame_rect", async () => {
      const s = await seq.getSettings();
      const frame = await s.getVideoFrameRect();
      const rect = new ppro.RectF();
      rect.width = frame.width;
      rect.height = frame.height;
      const setterResult = await s.setPreviewFrameRect(rect);
      expect(tx(project, (ca) => add(ca, seq.createSetSettingsAction(s))), "createSetSettingsAction transaction returned false");
      const after = await (await seq.getSettings()).getPreviewFrameRect();
      expect(after.width === frame.width && after.height === frame.height, `preview rect read back ${after.width}x${after.height}, wanted ${frame.width}x${frame.height}`);
      return { wanted: { width: frame.width, height: frame.height }, after: { width: after.width, height: after.height }, setter_returned: setterResult };
    });
    return steps.outcome({ initial: initial ?? null });
  },
};

// ---------------------------------------------------------------------------------------------- export_frame

interface ExportAttempt {
  id: string;
  ext: string;
  filename: (name: string) => string;
  filepath: string;
  dir: string;
  /** the d.ts example forms: always give them the full poll */
  longPoll: boolean;
}

/**
 * Every filename / filepath spelling worth trying for one target folder `dir` (forward slashes, no trailing slash).
 * For the plugin temp folder only the two forms that name the full path and end the folder with a separator are used:
 * a bare name joined to a folder without a separator would put the file next to the folder, outside it.
 */
function exportForms(kind: string, dir: string, ext: string): ExportAttempt[] {
  const back = dir.replace(/\//g, "\\");
  const mk = (id: string, filename: (n: string) => string, filepath: string, longPoll = false): ExportAttempt => ({ id: `${kind}:${id}:${ext}`, ext, filename, filepath, dir, longPoll });
  const all = [
    mk("name + dir/", (n) => n, `${dir}/`),
    mk("full path + dir/ (d.ts example form)", (n) => `${dir}/${n}`, `${dir}/`, true),
    mk("full path + dir (no trailing slash)", (n) => `${dir}/${n}`, dir),
    mk("name + dir\\ (backslashes)", (n) => n, `${back}\\`),
    mk("full path\\ + dir\\ (backslashes)", (n) => `${back}\\${n}`, `${back}\\`),
    mk("full path\\ + dir (backslashes, no trailing)", (n) => `${back}\\${n}`, back),
    mk("name + dir (no trailing slash)", (n) => n, dir),
  ];
  return kind === "temp" ? all.filter((a) => /^temp:full path/.test(a.id) && !/no trailing/.test(a.id)) : all;
}

/** Poll several candidate paths; returns the first that appears (non-empty). */
async function pollAny(fs: UxpFs, paths: string[], maxMs: number, everyMs = 250): Promise<{ found: boolean; path: string | null; bytes: number | null; after_ms: number }> {
  const t0 = Date.now();
  for (;;) {
    for (const p of paths) {
      const st = await statOf(fs, p);
      if (st.exists && (st.bytes ?? 0) > 0) return { found: true, path: p, bytes: st.bytes, after_ms: Date.now() - t0 };
    }
    if (Date.now() - t0 >= maxMs) return { found: false, path: null, bytes: null, after_ms: Date.now() - t0 };
    await sleep(everyMs);
  }
}

const exportFrame: ProbeDef<Ctx> = {
  op: "export_frame",
  timeoutMs: 300_000,
  run: async (ctx) => {
    const cfg = needConfig(ctx);
    const { ppro } = ctx;
    const project = await getProject(ctx);
    const seq = await getSequence(ctx);
    const steps = new Steps();
    const workDir = `${cleanPath(cfg.work_dir)}/frames`;
    await ensureDir(ctx.fs, workDir);

    const prep = await steps.run("prepare: activate sequence, size, media state", async () => {
      const info: Record<string, unknown> = {};
      for (const [k, fn] of [
        ["openSequence", () => project.openSequence(seq)],
        ["setActiveSequence", () => project.setActiveSequence(seq)],
      ] as const) {
        try {
          info[k] = await fn();
        } catch (e) {
          info[`${k}_error`] = errText(e);
        }
      }
      try {
        info.done_analyzing_for_video_effects = await seq.isDoneAnalyzingForVideoEffects();
      } catch (e) {
        info.done_analyzing_error = errText(e);
      }
      const frame = await seq.getFrameSize();
      const endS = (await seq.getEndTime()).seconds;
      let firstStart = Infinity;
      const track0 = await seq.getVideoTrack(0);
      for (const c of track0.getTrackItems(ppro.Constants.TrackItemType.CLIP, false)) firstStart = Math.min(firstStart, (await c.getStartTime()).seconds);
      const t1 = Math.min(endS - 0.1, (Number.isFinite(firstStart) ? firstStart : 0) + 0.5);
      const t2 = Math.max(0, Math.min(endS - 0.1, endS * 0.4));
      const offline: string[] = [];
      try {
        const items = await (await project.getRootItem()).getItems();
        for (const item of items) {
          try {
            if (await ppro.ClipProjectItem.cast(item).isOffline()) offline.push(item.name);
          } catch {
            // bins and sequences have no offline state
          }
        }
      } catch (e) {
        info.media_state_error = errText(e);
      }
      return { ...info, width: frame.width, height: frame.height, sequence_end_s: endS, first_v1_clip_start_s: Number.isFinite(firstStart) ? firstStart : null, t1, t2, offline_items: offline };
    });
    if (!prep) return steps.outcome();
    const { width, height, t1, t2 } = prep;

    const dirs: Array<{ kind: string; dir: string }> = [{ kind: "work", dir: workDir }];
    const tmp = await steps.run("temp folder (no spaces in the path)", async () => {
      const d = await tempDir(ctx);
      expect(d, "uxp.storage.localFileSystem.getTemporaryFolder() gave no path");
      return { dir: d, has_spaces: /\s/.test(d) };
    });
    if (tmp) dirs.push({ kind: "temp", dir: tmp.dir });

    const findings: string[] = [];
    const run = async (a: ExportAttempt, t: number, tag: string, movePlayhead: boolean) => {
      const name = `exp_${ctx.stamp}_${tag}.${a.ext}`;
      const expected = `${a.dir}/${name}`;
      const rec: Record<string, unknown> = { form: a.id, filename: a.filename(name), filepath: a.filepath, t_s: t, move_playhead: movePlayhead };
      if (movePlayhead) {
        try {
          rec.setPlayerPosition = await seq.setPlayerPosition(tickSeconds(ctx, t));
        } catch (e) {
          rec.setPlayerPosition_error = errText(e);
        }
      }
      const t0 = Date.now();
      try {
        rec.returned = await ppro.Exporter.exportSequenceFrame(seq, tickSeconds(ctx, t), a.filename(name), a.filepath, width, height);
      } catch (e) {
        rec.error = errDetail(e);
      }
      rec.call_ms = Date.now() - t0;
      // also look where a separator-less join of folder and name would put the file (next to the folder, not in it)
      const slash = a.dir.lastIndexOf("/");
      const joined = `${a.dir}${name}`;
      const parentJoined = `${a.dir.slice(0, slash)}/${a.dir.slice(slash + 1)}${name}`;
      const candidates = [...new Set([expected, joined, parentJoined])];
      const poll = await pollAny(ctx.fs, candidates, a.longPoll || rec.returned === true ? (ctx.timing?.longPollMs ?? 10_000) : (ctx.timing?.shortPollMs ?? 1_500), 50);
      rec.expected_path = expected;
      rec.polled_paths = candidates;
      rec.found = poll.found;
      rec.found_at = poll.path;
      rec.bytes = poll.bytes;
      rec.found_after_ms = poll.after_ms;
      if (poll.found && poll.path !== expected) {
        rec.separator_less_join = true;
        findings.push(`FINDING: form "${a.id}" wrote the file at ${poll.path} instead of ${expected}: the folder and the file name were joined WITHOUT a separator (file ended up outside ${a.dir}/)`);
      }
      return rec;
    };

    let winner: ExportAttempt | undefined;
    await steps.run("frame 1: try every form until a file appears", async () => {
      const list: Array<{ a: ExportAttempt; move: boolean }> = [];
      for (const d of dirs) for (const a of exportForms(d.kind, d.dir, "png")) list.push({ a, move: false });
      for (const ext of ["jpg", "tif", "bmp"]) list.push({ a: exportForms("work", workDir, ext)[1] as ExportAttempt, move: false });
      for (const a of exportForms("work", workDir, "png").slice(0, 2)) list.push({ a, move: true });
      const attempts: Array<Record<string, unknown>> = [];
      let n = 0;
      for (const { a, move } of list) {
        const rec = await run(a, t1, `f1_${++n}`, move);
        attempts.push(rec);
        if (rec.found) {
          winner = a;
          break;
        }
      }
      const info = { width, height, winner: winner?.id ?? null, findings, attempts };
      if (!winner) failWith(`no export form produced a file (${attempts.length} attempts, returned values: ${[...new Set(attempts.map((r) => String(r.returned)))].join(", ")})`, info);
      return info;
    });
    await steps.run("frame 2: the winning form at a second time", async () => {
      const forms = winner ? [winner] : exportForms("work", workDir, "png").slice(0, 2);
      const attempts: Array<Record<string, unknown>> = [];
      for (const a of forms) {
        const rec = await run(a, t2, "f2", false);
        attempts.push(rec);
        if (rec.found) return { winner: a.id, attempts };
      }
      return failWith("second frame not produced", { attempts });
    });
    if (winner) {
      const w = winner;
      /** Used by the time-basis probe to render frames at known sequence times. */
      ctx.exportFrameTo = async (t: number, base: string) => {
        const rec = await run(w, t, base.replace(/[^A-Za-z0-9_-]/g, "_"), false);
        return { path: String(rec.found_at ?? rec.expected_path), found: rec.found === true, bytes: (rec.bytes as number | null) ?? null, returned: rec.returned };
      };
    }
    return steps.outcome({ out_dir: workDir, winner: winner?.id ?? null, findings });
  },
};

// ---------------------------------------------------------------------------------------------- keyframes

const keyframes: ProbeDef<Ctx> = {
  op: "keyframes_motion_opacity_crop",
  timeoutMs: 180_000,
  run: async (ctx) => {
    const project = await getProject(ctx);
    const steps = new Steps();
    const target = await steps.run("place_still_or_pick_clip", async () => {
      const t = await ensureTarget(ctx);
      return { source: t.source, track_index: t.trackIndex, start_s: (await t.clip.getStartTime()).seconds, end_s: (await t.clip.getEndTime()).seconds, in_point_s: (await t.clip.getInPoint()).seconds, notes: ctx.notes.slice() };
    });
    if (target && ctx.target) await stillKeyframes(ctx, project, steps, ctx.target);
    return steps.outcome();
  },
};

/** Motion Position: the failing call is isolated (inspect, createKeyframe per value form, time-varying, add). */
async function positionKeyframes(ctx: Ctx, project: Project, steps: Steps, motion: Component): Promise<void> {
  const { ppro } = ctx;
  const found = findParam(motion, /^position$/i);
  if (!found) {
    await steps.run("position: find param", async () => failWith("no param matching /^position$/", { params: Array.from({ length: motion.getParamCount() }, (_, i) => motion.getParam(i).displayName) }));
    return;
  }
  const { param } = found;
  const seq = await getSequence(ctx);
  const frame = await seq.getFrameSize();
  const inspected = await steps.run("position: inspect start value and values at 0 s / 1 s", async () => {
    const sv = await param.getStartValue();
    const at0 = await param.getValueAtTime(tickSeconds(ctx, 0));
    const at1 = await param.getValueAtTime(tickSeconds(ctx, 1));
    const inner = (sv as unknown as { value?: { value?: unknown } } | undefined)?.value?.value;
    const base = pointOf(inner) ?? pointOf(at0);
    return {
      keyframes_supported: await param.areKeyframesSupported(),
      time_varying: param.isTimeVarying(),
      start_value: describeValue(sv),
      start_value_value: describeValue((sv as unknown as { value?: unknown } | undefined)?.value),
      start_value_inner: describeValue(inner),
      value_at_0s: describeValue(at0),
      value_at_1s: describeValue(at1),
      frame: { width: frame.width, height: frame.height },
      base,
      units: base ? (base.x <= 2 && base.y <= 2 ? "normalised 0-1" : "pixels") : "unknown",
      inner,
    };
  });
  const base = inspected?.base ?? { x: 0.5, y: 0.5 };
  const normalised = base.x <= 2 && base.y <= 2;
  const startObj = inspected?.inner;
  const builders: Array<[string, (x: number, y: number) => unknown]> = [
    ["new PointF(x, y)", (x, y) => new ppro.PointF(x, y)],
    ["PointF(x, y) without new", (x, y) => (ppro.PointF as unknown as (a: number, b: number) => PointF)(x, y)],
    [
      "new PointF() then .x/.y",
      (x, y) => {
        const p = new ppro.PointF();
        p.x = x;
        p.y = y;
        return p;
      },
    ],
    ["plain {x, y}", (x, y) => ({ x, y })],
    ["array [x, y]", (x, y) => [x, y]],
    ["the start value object as returned", () => startObj],
    ["new PointF in the other unit system", (x, y) => (normalised ? new ppro.PointF(x * frame.width, y * frame.height) : new ppro.PointF(x / frame.width, y / frame.height))],
  ];
  const good = await steps.run("position: createKeyframe with each value form", async () => {
    const results: Array<Record<string, unknown>> = [];
    const ok: string[] = [];
    for (const [name, make] of builders) {
      try {
        const kf = param.createKeyframe(make(base.x, base.y) as PointF);
        results.push({ form: name, ok: true, keyframe_value: describeValue((kf as unknown as { value?: unknown }).value) });
        ok.push(name);
      } catch (e) {
        results.push({ form: name, ok: false, error: errText(e) });
      }
    }
    if (ok.length === 0) failWith("createKeyframe rejected every value form", { results });
    return { results, accepted_forms: ok };
  });
  if (!good) return;
  await steps.run("position: createSetTimeVaryingAction(true)", async () => {
    expect(tx(project, (ca) => add(ca, param.createSetTimeVaryingAction(true))), "setTimeVarying transaction returned false");
    return { time_varying: param.isTimeVarying() };
  });
  const dx = normalised ? 0.05 : 50;
  for (const name of good.accepted_forms) {
    const make = builders.find((b) => b[0] === name)?.[1];
    if (!make) continue;
    const done = await steps.run(`position: addKeyframe x2 via "${name}"`, async () => {
      const kA = param.createKeyframe(make(base.x, base.y) as PointF);
      kA.position = tickSeconds(ctx, 0);
      const kB = param.createKeyframe(make(base.x + dx, base.y) as PointF);
      kB.position = tickSeconds(ctx, 1);
      expect(
        tx(project, (ca) => {
          add(ca, param.createAddKeyframeAction(kA));
          add(ca, param.createAddKeyframeAction(kB));
        }),
        "addKeyframe transaction returned false",
      );
      const times = param.getKeyframeListAsTickTimes().map((t) => t.seconds);
      expect(times.length >= 2, `expected >= 2 position keyframes, read back ${times.length}`);
      return { read_back_times_s: times, value_at_0s: describeValue(await param.getValueAtTime(tickSeconds(ctx, 0))), value_at_1s: describeValue(await param.getValueAtTime(tickSeconds(ctx, 1))), set: { from: base, to: { x: base.x + dx, y: base.y } } };
    });
    if (done) break;
  }
}

/** Crop: Motion's built-in "Crop Left/Top/Right/Bottom" and the separate effect `AE.ADBE AECrop`. */
async function cropKeyframes(ctx: Ctx, project: Project, steps: Steps, chain: VideoComponentChain, motion: { comp: Component } | null): Promise<void> {
  const { ppro } = ctx;
  if (motion) {
    const m = motion.comp;
    await steps.run("crop: Motion built-in Crop params", async () => {
      const out: Array<Record<string, unknown>> = [];
      for (const name of ["Crop Left", "Crop Top", "Crop Right", "Crop Bottom"]) {
        const f = findParam(m, new RegExp(`^${name}$`, "i"));
        if (!f) {
          out.push({ name, found: false });
          continue;
        }
        const sv = await f.param.getStartValue();
        out.push({ name, found: true, index: f.index, keyframes_supported: await f.param.areKeyframesSupported(), start_value: describeValue((sv as unknown as { value?: { value?: unknown } } | undefined)?.value?.value) });
      }
      if (out.some((o) => o.found === false)) failWith("Motion lacks some Crop params", out);
      return out;
    });
    await steps.run("crop: Motion Crop Left 0->100", () => numericKeyframes(ctx, project, m, /^crop left$/i, { t: 0, v: 0 }, { t: 1, v: 100 }));
    await steps.run("crop: Motion Crop Right 0->10", () => numericKeyframes(ctx, project, m, /^crop right$/i, { t: 0, v: 0 }, { t: 1, v: 10 }));
  }
  await steps.run("crop effect AE.ADBE AECrop: create, append, Left 0->10", async () => {
    const names = await ppro.VideoFilterFactory.getMatchNames();
    const pick = names.find((n) => n === "AE.ADBE AECrop") ?? names.find((n) => /AECrop/i.test(n));
    expect(pick, "no filter named AE.ADBE AECrop in VideoFilterFactory.getMatchNames()");
    const before = chain.getComponentCount();
    const comp = await ppro.VideoFilterFactory.createComponent(pick);
    expect(tx(project, (ca) => add(ca, chain.createAppendComponentAction(comp))), "append transaction returned false");
    const crop = await findComponent(chain, /AECrop/i);
    expect(crop, `crop effect not found in the chain after append (chain ${before} -> ${chain.getComponentCount()})`);
    const params = Array.from({ length: crop.comp.getParamCount() }, (_, i) => crop.comp.getParam(i).displayName);
    const left = await numericKeyframes(ctx, project, crop.comp, /^left$/i, { t: 0, v: 0 }, { t: 1, v: 10 });
    return { used: pick, chain_before: before, chain_after: chain.getComponentCount(), params, left };
  });
}

/** Motion / Opacity / Crop keyframes on the target clip (the placed still, else a clip of the scratch sequence). */
async function stillKeyframes(ctx: Ctx, project: Project, steps: Steps, target: TargetClip): Promise<void> {
  const { ppro } = ctx;
  const clip = target.clip;
  const chain = await steps.run("get_component_chain", async () => await clip.getComponentChain());
  if (!chain) return;
  await steps.run("dump_component_chain", async () => await dumpChain(chain));

  const motion = await findComponent(chain, /ADBE Motion/i);
  await steps.run("motion_found", async () => {
    expect(motion, "no component matching /ADBE Motion/ in the chain");
    return { matchName: motion.matchName };
  });
  if (motion) {
    await steps.run("motion.scale 100->110", () => numericKeyframes(ctx, project, motion.comp, /^scale$/i, { t: 0, v: 100 }, { t: 1, v: 110 }));
    await steps.run("motion.rotation 0->5", () => numericKeyframes(ctx, project, motion.comp, /^rotation$/i, { t: 0, v: 0 }, { t: 1, v: 5 }));
    await positionKeyframes(ctx, project, steps, motion.comp);
    await steps.run("motion.scale interpolation -> bezier at 1s", async () => {
      const found = findParam(motion.comp, /^scale$/i);
      expect(found, "no scale param");
      const { param } = found;
      expect(tx(project, (ca) => add(ca, param.createSetInterpolationAtKeyframeAction(tickSeconds(ctx, 1), ppro.Keyframe.INTERPOLATION_MODE_BEZIER))), "interpolation transaction returned false");
      const kf = param.getKeyframePtr(tickSeconds(ctx, 1));
      return { mode: await kf.getTemporalInterpolationMode(), wanted: ppro.Keyframe.INTERPOLATION_MODE_BEZIER };
    });
  }

  const opacity = await findComponent(chain, /ADBE Opacity/i);
  await steps.run("opacity_found", async () => {
    expect(opacity, "no component matching /ADBE Opacity/ in the chain");
    return { matchName: opacity.matchName };
  });
  if (opacity) await steps.run("opacity 100->0", () => numericKeyframes(ctx, project, opacity.comp, /^opacity$/i, { t: 0, v: 100 }, { t: 1, v: 0 }));

  await cropKeyframes(ctx, project, steps, chain, motion);
}

// ---------------------------------------------------------------------------------------------- keyframe_time_basis

/**
 * Which time basis does Premiere apply to keyframe positions? UXP stores and returns whatever was given, so only a
 * rendered frame can tell. On a clip whose clip-local [0,dur], media [in,in+dur] and sequence [start,end] windows are
 * pairwise disjoint, ONE basis at a time keys opacity 100 -> 0 over 1 s, then frames are exported at known sequence
 * times (decode them offline: a fade to black shows only in the basis Premiere really uses). Keys are removed between
 * bases. The values from getValueAtTime at the three candidate times are logged too.
 */
async function basisScenarios(ctx: Ctx, project: Project, steps: Steps, label: string, used: string, clip: VideoClipTrackItem, w: ClipWindow): Promise<void> {
  const chain = await steps.run(`${label}: get component chain`, async () => await clip.getComponentChain());
  if (!chain) return;
  const opacity = await findComponent(chain, /ADBE Opacity/i);
  const found = opacity ? findParam(opacity.comp, /^opacity$/i) : null;
  if (!found) {
    await steps.run(`${label}: find Opacity param`, async () => failWith("no Opacity param", { has_component: opacity !== null }));
    return;
  }
  const { param } = found;
  const fractions = [0.25, 0.5, 0.75];
  const frames = async (tag: string) => {
    if (!ctx.exportFrameTo) return "export unavailable (export_frame found no working form): read-back only";
    const out: Array<Record<string, unknown>> = [];
    for (const f of fractions) out.push({ sequence_time_s: w.start_s + f, local_fraction_s: f, ...(await ctx.exportFrameTo(w.start_s + f, `tb_${label}_${tag}_${f}`)) });
    return out;
  };
  await steps.run(`${label}: baseline frames (no keys)`, async () => ({ clip_used: used, clip: w, disjoint_windows: windowsDisjoint(w), keys_on_opacity: param.getKeyframeListAsTickTimes().length, frames: await frames("baseline") }));
  const bases: Array<[string, string, number]> = [
    ["A", "zero-relative (clip-local)", 0],
    ["B", "in-point-relative (media time)", w.in_s],
    ["C", "start-relative (sequence time)", w.start_s],
  ];
  for (const [key, name, t0] of bases) {
    await steps.run(`${label}: basis ${key} ${name}, keys at ${t0.toFixed(3)} s and +1 s`, async () => {
      expect(tx(project, (ca) => add(ca, param.createSetTimeVaryingAction(true))), "setTimeVarying transaction returned false");
      const kA = param.createKeyframe(100);
      kA.position = tickSeconds(ctx, t0);
      const kB = param.createKeyframe(0);
      kB.position = tickSeconds(ctx, t0 + 1);
      expect(
        tx(project, (ca) => {
          add(ca, param.createAddKeyframeAction(kA));
          add(ca, param.createAddKeyframeAction(kB));
        }),
        "addKeyframe transaction returned false",
      );
      const times = param.getKeyframeListAsTickTimes().map((t) => t.seconds);
      const values: Record<string, unknown> = {};
      for (const f of fractions) {
        values[`at_sequence_time_start+${f}`] = await param.getValueAtTime(tickSeconds(ctx, w.start_s + f));
        values[`at_local_time_${f}`] = await param.getValueAtTime(tickSeconds(ctx, f));
        values[`at_media_time_in+${f}`] = await param.getValueAtTime(tickSeconds(ctx, w.in_s + f));
      }
      const rendered = await frames(`${key}`);
      // clear the keys again so the next basis starts clean
      const clear = tx(project, (ca) => {
        for (const t of times) add(ca, param.createRemoveKeyframeAction(tickSeconds(ctx, t)));
      });
      const left = param.getKeyframeListAsTickTimes().length;
      return { clip_used: used, clip: w, requested_times_s: [t0, t0 + 1], read_back_times_s: times, ...classifyTimes(times, w), disjoint_windows: windowsDisjoint(w), values, frames: rendered, cleared: clear, keys_left_after_clear: left };
    });
  }
}

/** Place a FRESH copy of the still (own track if the API creates one, else a free time on the top track), keys-free. */
async function placeFreshStill(ctx: Ctx, project: Project, seq: Sequence): Promise<{ clip: VideoClipTrackItem; info: Record<string, unknown> }> {
  const { ppro } = ctx;
  const item = await stillItemFor(ctx, project);
  const editor = ppro.SequenceEditor.getEditor(seq);
  const vBefore = await seq.getVideoTrackCount();
  const endT = (await seq.getEndTime()).seconds;
  const atS = endT + 1;
  const attempts: Array<Record<string, unknown>> = [];
  for (const [how, index] of [
    ["own new track (index = track count)", vBefore],
    ["top existing track at a free time", vBefore - 1],
  ] as const) {
    const rec: Record<string, unknown> = { how, track_index: index };
    attempts.push(rec);
    try {
      rec.transaction_returned = tx(project, (ca) => add(ca, editor.createOverwriteItemAction(item, tickSeconds(ctx, atS), index, 0)));
      const count = await seq.getVideoTrackCount();
      rec.video_tracks_after = count;
      if (index >= count) continue;
      const track = await seq.getVideoTrack(index);
      let best: VideoClipTrackItem | null = null;
      let bestStart = -1;
      for (const c of track.getTrackItems(ppro.Constants.TrackItemType.CLIP, false)) {
        const st = (await c.getStartTime()).seconds;
        if (st >= atS - 0.05 && st > bestStart) {
          best = c;
          bestStart = st;
        }
      }
      if (!best) continue;
      return { clip: best, info: { still_item: item.name, placed_at_s: atS, own_track: index >= vBefore, track_index: index, how, attempts } };
    } catch (e) {
      rec.error = errText(e);
    }
  }
  return failWith("could not place a fresh copy of the still", { attempts });
}

const keyframeTimeBasis: ProbeDef<Ctx> = {
  op: "keyframe_time_basis",
  timeoutMs: 300_000,
  run: async (ctx) => {
    const project = await getProject(ctx);
    const seq = await getSequence(ctx);
    const steps = new Steps();
    const holder: { clip?: VideoClipTrackItem; w?: ClipWindow; used?: string } = {};
    await steps.run("xml clip: pick one with in-point > duration and move it so the three windows are disjoint", async () => {
      const vCount = await seq.getVideoTrackCount();
      // never the clip other probes already keyed or edited (the placed still, or the existing clip the keyframes probe fell back to)
      const otherUse = ctx.target ? { track: ctx.target.trackIndex, w: await windowOf(ctx.target.clip) } : null;
      const near = (a: number, b: number) => Math.abs(a - b) < 1e-3;
      const candidates: Array<{ ti: number; clip: VideoClipTrackItem; w: ClipWindow }> = [];
      for (let ti = 0; ti < vCount; ti++) {
        const track = await seq.getVideoTrack(ti);
        for (const clip of track.getTrackItems(ctx.ppro.Constants.TrackItemType.CLIP, false)) {
          const w = await windowOf(clip);
          if (!(w.in_s > w.duration_s + EPS && w.duration_s >= 2)) continue;
          if (otherUse && otherUse.track === ti && near(otherUse.w.start_s, w.start_s) && near(otherUse.w.in_s, w.in_s)) continue;
          candidates.push({ ti, clip, w });
        }
      }
      const attempts: Array<Record<string, unknown>> = [];
      for (const c of candidates) {
        const seqEnd = (await seq.getEndTime()).seconds;
        const wanted = Math.max(seqEnd, c.w.in_s + c.w.duration_s) + 1;
        const rec: Record<string, unknown> = { track_index: c.ti, before: c.w };
        attempts.push(rec);
        try {
          rec.move_returned = tx(project, (ca) => add(ca, c.clip.createMoveAction(tickSeconds(ctx, wanted - c.w.start_s))));
          const after = await windowOf(c.clip);
          rec.after = after;
          rec.disjoint_windows = windowsDisjoint(after);
          if (windowsDisjoint(after)) {
            holder.clip = c.clip;
            holder.w = after;
            holder.used = `xml clip, video track index ${c.ti}, moved (original start ${c.w.start_s.toFixed(3)} s, in ${c.w.in_s.toFixed(3)} s)`;
            return { track_index: c.ti, before: c.w, after, disjoint_windows: true, attempts };
          }
        } catch (e) {
          rec.error = errText(e);
        }
      }
      return failWith("no clip with in-point > duration and duration >= 2 s could be moved into disjoint windows in the imported scratch sequence", { candidates: candidates.length, attempts });
    });
    if (holder.clip && holder.w && holder.used) await basisScenarios(ctx, project, steps, "xml_clip", holder.used, holder.clip, holder.w);

    holder.clip = undefined;
    const fresh = await steps.run("fresh still: place a new copy for this probe only (no keys, no effects)", async () => {
      const placed = await placeFreshStill(ctx, project, seq);
      const w = await windowOf(placed.clip);
      holder.clip = placed.clip;
      holder.w = w;
      holder.used = `fresh copy of the still, video track index ${placed.info.track_index} (${placed.info.own_track ? "own new track" : "top existing track"}), start ${w.start_s.toFixed(3)} s`;
      const chain = await placed.clip.getComponentChain();
      return { ...placed.info, ...w, disjoint_windows: windowsDisjoint(w), components_in_chain: chain.getComponentCount(), is_target_clip_of_other_probes: ctx.target ? (await windowOf(ctx.target.clip)).start_s === w.start_s : false };
    });
    if (fresh && holder.clip && holder.w && holder.used) await basisScenarios(ctx, project, steps, "fresh_still", holder.used, holder.clip, holder.w);
    return steps.outcome();
  },
};

// ---------------------------------------------------------------------------------------------- effects

interface EffectSpec {
  key: string;
  match: string;
  params: Array<{ rx: RegExp; value: number | boolean }>;
}

/** Exact match names, verified live (docs/adobe/uxp-parity.md "Measured facts" 4). */
const EFFECT_SPECS: EffectSpec[] = [
  { key: "gaussian_blur_legacy", match: "AE.ADBE Gaussian Blur 2", params: [{ rx: /^blurriness$/i, value: 90 }, { rx: /repeat edge pixels/i, value: true }] },
  { key: "sharpen", match: "AE.ADBE Sharpen", params: [{ rx: /sharpen amount/i, value: 50 }] },
  { key: "noise", match: "AE.ADBE_Noise_FX", params: [{ rx: /^intensity$/i, value: 30 }] },
  { key: "lumetri", match: "AE.ADBE Lumetri", params: [] },
];

function sameValue(a: unknown, b: unknown): boolean {
  if (typeof a === "number" && typeof b === "number") return Math.abs(a - b) < 1e-6;
  return a === b;
}

/** Create + append one effect by its exact match name, set each listed param statically, read each back. */
async function addEffect(ctx: Ctx, project: Project, chain: VideoComponentChain, matchNames: string[], match: string, params: EffectSpec["params"]): Promise<Record<string, unknown>> {
  const { ppro } = ctx;
  expect(matchNames.includes(match), `"${match}" is not in VideoFilterFactory.getMatchNames()`);
  const before = chain.getComponentCount();
  const comp = await ppro.VideoFilterFactory.createComponent(match);
  expect(tx(project, (ca) => add(ca, chain.createAppendComponentAction(comp))), "append transaction returned false");
  const after = chain.getComponentCount();
  expect(after === before + 1, `chain had ${before} components, ${after} after append`);
  const added = chain.getComponentAtIndex(after - 1);
  const paramNames = Array.from({ length: added.getParamCount() }, (_, j) => added.getParam(j).displayName);
  const info: Record<string, unknown> = { used: match, chain_before: before, chain_after: after, added_match_name: await added.getMatchName(), added_display_name: await added.getDisplayName(), params: paramNames, set: [] as unknown[] };
  let failed = 0;
  for (const p of params) {
    const rec: Record<string, unknown> = { param: String(p.rx), value: p.value };
    try {
      const f = findParam(added, p.rx);
      expect(f, `no param matching ${p.rx} among ${paramNames.join(", ")}`);
      const kf = f.param.createKeyframe(p.value);
      rec.param_name = f.param.displayName;
      rec.transaction_returned = tx(project, (ca) => add(ca, f.param.createSetValueAction(kf)));
      rec.read_back = describeValue(await f.param.getValueAtTime(tickSeconds(ctx, 0)));
      const start = await f.param.getStartValue();
      rec.start_value = describeValue((start as unknown as { value?: { value?: unknown } } | undefined)?.value?.value);
      rec.matches = sameValue((rec.read_back as { value?: unknown }).value, p.value) || sameValue((rec.start_value as { value?: unknown }).value, p.value);
      if (!rec.matches) failed++;
    } catch (e) {
      rec.error = errText(e);
      failed++;
    }
    (info.set as unknown[]).push(rec);
  }
  if (failed > 0) failWith(`${failed} static value(s) did not read back`, info);
  return info;
}

const effects: ProbeDef<Ctx> = {
  op: "effects_by_match_name",
  timeoutMs: 120_000,
  run: async (ctx) => {
    const { ppro } = ctx;
    const project = await getProject(ctx);
    const steps = new Steps();
    const holder: { matchNames: string[]; displayNames: string[] } = { matchNames: [], displayNames: [] };
    const lists = await steps.run("list_filters", async () => {
      const matchNames = await ppro.VideoFilterFactory.getMatchNames();
      const displayNames = await ppro.VideoFilterFactory.getDisplayNames();
      const file = `${ctx.config ? toForwardSlashes(ctx.config.work_dir).replace(/\/+$/, "") : "."}/filters-${ctx.stamp}.json`;
      try {
        await writeText(ctx.fs, file, JSON.stringify({ matchNames, displayNames }, null, 1));
        ctx.notes.push(file);
      } catch {
        // the lists are still counted below
      }
      holder.matchNames = matchNames;
      holder.displayNames = displayNames;
      return { match_names: matchNames.length, display_names: displayNames.length, parallel_arrays: matchNames.length === displayNames.length, file };
    });
    const target = await steps.run("target_clip", async () => {
      const t = await ensureTarget(ctx);
      return { source: t.source, track_index: t.trackIndex };
    });
    if (!lists || !target || !ctx.target) return steps.outcome();
    const chain = await steps.run("get_component_chain", async () => await ctx.target!.clip.getComponentChain());
    if (!chain) return steps.outcome();
    for (const spec of EFFECT_SPECS) {
      await steps.run(`${spec.key}: ${spec.match} create + append + static values`, () => addEffect(ctx, project, chain, holder.matchNames, spec.match, spec.params));
    }
    // The NEW "Gaussian Blur" (display name) is AE.Impact_Blur_FX with other params: record them separately.
    await steps.run("AE.Impact_Blur_FX (display 'Gaussian Blur'): params", async () => {
      expect(holder.matchNames.includes("AE.Impact_Blur_FX"), "AE.Impact_Blur_FX is not in the filter list");
      const before = chain.getComponentCount();
      const comp = await ppro.VideoFilterFactory.createComponent("AE.Impact_Blur_FX");
      expect(tx(project, (ca) => add(ca, chain.createAppendComponentAction(comp))), "append transaction returned false");
      const added = chain.getComponentAtIndex(chain.getComponentCount() - 1);
      const params: Array<Record<string, unknown>> = [];
      for (let j = 0; j < added.getParamCount(); j++) {
        const p = added.getParam(j);
        params.push({ i: j, name: p.displayName, keyframes_supported: await p.areKeyframesSupported() });
      }
      return { chain_before: before, chain_after: chain.getComponentCount(), match: await added.getMatchName(), display: await added.getDisplayName(), params };
    });
    return steps.outcome({ filters_total: lists.match_names, filters_file: lists.file });
  },
};

// ---------------------------------------------------------------------------------------------- clip edits, transitions, tracks

const clipEdits: ProbeDef<Ctx> = {
  op: "clip_edits_transitions_tracks",
  timeoutMs: 120_000,
  run: async (ctx) => {
    const { ppro } = ctx;
    const project = await getProject(ctx);
    const seq = await getSequence(ctx);
    const steps = new Steps();
    const target = await steps.run("target: the placed still", async () => {
      const t = await ensureTarget(ctx);
      expect(t.source === "placed still", "the still was not placed; this probe edits only the placed still, never an XML clip");
      return { track_index: t.trackIndex, ...(await windowOf(t.clip)) };
    });
    if (!target || !ctx.target) return steps.outcome();
    const clip = ctx.target.clip;
    const trackIndex = ctx.target.trackIndex;
    const readWindow = async () => ({ ...(await windowOf(clip)), out_s: (await clip.getOutPoint()).seconds });
    const edit = (label: string, make: () => Parameters<CompoundAction["addAction"]>[0]) =>
      steps.run(label, async () => {
        const before = await readWindow();
        const returned = tx(project, (ca) => add(ca, make()));
        const after = await readWindow();
        return { transaction_returned: returned, before, after };
      });
    await edit("createSetEndAction(end - 2 s)", () => clip.createSetEndAction(tickSeconds(ctx, target.end_s - 2)));
    await edit("createSetStartAction(start + 0.5 s)", () => clip.createSetStartAction(tickSeconds(ctx, target.start_s + 0.5)));
    await edit("createMoveAction(+1 s) (an offset: 'shifting it by a number of seconds')", () => clip.createMoveAction(tickSeconds(ctx, 1)));
    await edit("createSetInPointAction(in + 0.5 s)", () => clip.createSetInPointAction(tickSeconds(ctx, target.in_s + 0.5)));
    await steps.run("createSetOutPointAction(out - 0.5 s)", async () => {
      const before = await readWindow();
      const returned = tx(project, (ca) => add(ca, clip.createSetOutPointAction(tickSeconds(ctx, before.out_s - 0.5))));
      return { transaction_returned: returned, before, after: await readWindow() };
    });
    await steps.run("rename clip + disable/enable", async () => {
      const nameBefore = await clip.getName();
      tx(project, (ca) => add(ca, clip.createSetNameAction("WNC placed still")));
      const nameAfter = await clip.getName();
      tx(project, (ca) => add(ca, clip.createSetDisabledAction(true)));
      const disabled = await clip.isDisabled();
      tx(project, (ca) => add(ca, clip.createSetDisabledAction(false)));
      const enabled = !(await clip.isDisabled());
      expect(nameAfter === "WNC placed still" && disabled && enabled, `name "${nameAfter}", disabled ${disabled}, re-enabled ${enabled}`);
      return { nameBefore, nameAfter, disabled, enabled };
    });
    await steps.run("video transition: list, create, add to the still's start", async () => {
      const names = await ppro.TransitionFactory.getVideoTransitionMatchNames();
      const pick = names.find((n) => /cross dissolve/i.test(n)) ?? names.find((n) => /dissolve/i.test(n)) ?? names[0];
      expect(pick, `no transitions listed (${names.length})`);
      const track = await seq.getVideoTrack(trackIndex);
      const count = () => track.getTrackItems(ppro.Constants.TrackItemType.TRANSITION, false).length;
      const before = count();
      const transition = ppro.TransitionFactory.createVideoTransition(pick);
      const options = new ppro.AddTransitionOptions().setDuration(tickSeconds(ctx, 0.5)).setApplyToStart(true);
      const returned = tx(project, (ca) => add(ca, clip.createAddVideoTransitionAction(transition, options)));
      const after = count();
      return { listed: names.length, first_names: names.slice(0, 12), used: pick, transition_items_before: before, transition_items_after: after, transaction_returned: returned };
    });
    await steps.run("add a video track by overwriting at index = track count (d.ts: 'a new track will be created')", async () => {
      const item = await clip.getProjectItem();
      const editor = ppro.SequenceEditor.getEditor(seq);
      const vBefore = await seq.getVideoTrackCount();
      const endT = await seq.getEndTime();
      const returned = tx(project, (ca) => add(ca, editor.createOverwriteItemAction(item, tickSeconds(ctx, endT.seconds + 1), vBefore, 0)));
      const vAfter = await seq.getVideoTrackCount();
      return { video_tracks_before: vBefore, video_tracks_after: vAfter, transaction_returned: returned, track_added: vAfter === vBefore + 1 };
    });
    await steps.run("remove the clip placed on the new track (TrackItemSelection + createRemoveItemsAction)", async () => {
      const editor = ppro.SequenceEditor.getEditor(seq);
      const vCount = await seq.getVideoTrackCount();
      const track = await seq.getVideoTrack(vCount - 1);
      const items = track.getTrackItems(ppro.Constants.TrackItemType.CLIP, false);
      const victim = items[items.length - 1];
      expect(victim, "no clip on the last video track to remove");
      let removed: boolean | null = null;
      ppro.TrackItemSelection.createEmptySelection((selection) => {
        selection.addItem(victim);
        removed = tx(project, (ca) => add(ca, editor.createRemoveItemsAction(selection, false, ppro.Constants.MediaType.VIDEO)));
      });
      const left = (await seq.getVideoTrack(vCount - 1)).getTrackItems(ppro.Constants.TrackItemType.CLIP, false).length;
      return { clips_before: items.length, clips_after: left, transaction_returned: removed };
    });
    return steps.outcome();
  },
};

// ---------------------------------------------------------------------------------------------- scratch disks

const SCRATCH_FOLDER_TYPES = ["CAPTURE", "AUDIO_PREVIEW", "VIDEO_PREVIEW", "AUTO_SAVE", "CCL_LIBRARIES", "CAPSULE_MEDIA"] as const;

/**
 * Premiere shows "Scratch Disk Error" when a project's scratch disks are unavailable. Right after createProject: read the
 * project's scratch settings, set every type to "same as project" and read back. Each step is timestamped (`at`, `ms`).
 */
const scratchDisk: ProbeDef<Ctx> = {
  op: "scratch_disk",
  timeoutMs: 120_000,
  run: async (ctx) => {
    const { ppro } = ctx;
    const project = await getProject(ctx);
    const steps = new Steps();
    const enumFolderType = ppro.Constants.ScratchDiskFolderType as unknown as Record<string, number>;
    const readAll = async (settings: { getScratchDiskPath: (t: never) => string }) => {
      const out: Record<string, unknown> = {};
      for (const name of SCRATCH_FOLDER_TYPES) {
        const key = name as string;
        try {
          out[key] = settings.getScratchDiskPath(enumFolderType[key] as never);
        } catch (e) {
          out[key] = `error: ${errText(e)}`;
        }
      }
      return out;
    };
    const before = await steps.run("getScratchDiskSettings + read each folder type", async () => {
      const s = await ppro.ProjectSettings.getScratchDiskSettings(project);
      return { enum_values: enumFolderType, paths: await readAll(s as never) };
    });
    void before;
    await steps.run("set every type to SAME_AS_PROJECT + createSetScratchDiskSettingsAction", async () => {
      const s = await ppro.ProjectSettings.getScratchDiskSettings(project);
      const sameEnum = (ppro.Constants.ScratchDiskFolder as unknown as Record<string, number>).SAME_AS_PROJECT;
      const sameStatic = (ppro.ScratchDiskSettings as unknown as Record<string, unknown>).FOLDER_SAME_AS_PROJECT;
      const setters: Array<Record<string, unknown>> = [];
      for (const name of SCRATCH_FOLDER_TYPES) {
        const rec: Record<string, unknown> = { type: name };
        try {
          rec.returned_enum_value = s.setScratchDiskPath(enumFolderType[name as string] as never, sameEnum as never);
        } catch (e) {
          rec.error_enum_value = errText(e);
          try {
            rec.returned_static_value = s.setScratchDiskPath(enumFolderType[name as string] as never, sameStatic as never);
          } catch (e2) {
            rec.error_static_value = errText(e2);
          }
        }
        setters.push(rec);
      }
      const returned = tx(project, (ca) => add(ca, ppro.ProjectSettings.createSetScratchDiskSettingsAction(project, s)));
      const fresh = await ppro.ProjectSettings.getScratchDiskSettings(project);
      const after = await readAll(fresh as never);
      const info = { same_as_project_enum: sameEnum, same_as_project_static: sameStatic, setters, transaction_returned: returned, paths_after: after };
      if (!returned) failWith("createSetScratchDiskSettingsAction transaction returned false", info);
      return info;
    });
    return steps.outcome();
  },
};

/** Renames V2 and A2 only: V1 / A1 belong to undo_transaction, whose Ctrl+Z check must stay unambiguous. */
const trackRename: ProbeDef<Ctx> = {
  op: "track_rename",
  run: async (ctx) => {
    const project = await getProject(ctx);
    const seq = await getSequence(ctx);
    const steps = new Steps();
    await steps.run("video_track_1 (V2)", async () => {
      expect((await seq.getVideoTrackCount()) > 1, "sequence has no second video track");
      const track = await seq.getVideoTrack(1);
      const before = track.name;
      const wanted = "WNC Spike V2";
      expect(tx(project, (ca) => add(ca, track.createSetNameAction(wanted))), "rename transaction returned false");
      const after = (await seq.getVideoTrack(1)).name;
      expect(after === wanted, `video track read back "${after}", wanted "${wanted}" (was "${before}")`);
      ctx.expect.renamedVideoTrackName = after;
      return { before, after };
    });
    await steps.run("audio_track_1 (A2)", async () => {
      expect((await seq.getAudioTrackCount()) > 1, "sequence has no second audio track");
      const track = await seq.getAudioTrack(1);
      const before = track.name;
      const wanted = "WNC Spike A2";
      expect(tx(project, (ca) => add(ca, track.createSetNameAction(wanted))), "rename transaction returned false");
      const after = (await seq.getAudioTrack(1)).name;
      expect(after === wanted, `audio track read back "${after}", wanted "${wanted}" (was "${before}")`);
      return { before, after };
    });
    return steps.outcome();
  },
};

async function markerSnapshot(ctx: Ctx, seq: Sequence) {
  const markers = await ctx.ppro.Markers.getMarkers(seq);
  return markers.getMarkers().map((m) => ({ name: m.getName(), type: m.getType(), start_s: m.getStart().seconds, duration_s: m.getDuration().seconds, comments: m.getComments(), color_index: m.getColorIndex() }));
}

const markers: ProbeDef<Ctx> = {
  op: "markers",
  run: async (ctx) => {
    const { ppro } = ctx;
    const project = await getProject(ctx);
    const seq = await getSequence(ctx);
    const steps = new Steps();
    const before = await steps.run("read_existing", async () => await markerSnapshot(ctx, seq));
    await steps.run("add_two_markers", async () => {
      const markersObj = await ppro.Markers.getMarkers(seq);
      expect(
        tx(project, (ca) => {
          add(ca, markersObj.createAddMarkerAction("WNC spike marker 1", ppro.Marker.MARKER_TYPE_COMMENT, tickSeconds(ctx, 2), tickSeconds(ctx, 0), "first marker"));
          add(ca, markersObj.createAddMarkerAction("WNC spike marker 2", ppro.Marker.MARKER_TYPE_COMMENT, tickSeconds(ctx, 3), tickSeconds(ctx, 1), "second marker, 1 s long"));
        }),
        "add markers transaction returned false",
      );
      const after = await markerSnapshot(ctx, seq);
      const m1 = after.find((m) => m.name === "WNC spike marker 1");
      const m2 = after.find((m) => m.name === "WNC spike marker 2");
      expect(m1 && m2, `markers not found after add: ${JSON.stringify(after)}`);
      expect(Math.abs(m1.start_s - 2) < 0.05 && Math.abs(m2.start_s - 3) < 0.05 && Math.abs(m2.duration_s - 1) < 0.05, `marker times wrong: ${JSON.stringify([m1, m2])}`);
      ctx.expect.markerCount = after.length;
      return { before_count: before?.length ?? null, after };
    });
    await steps.run("set_color_by_index", async () => {
      const list = (await ppro.Markers.getMarkers(seq)).getMarkers().filter((m) => m.getName() === "WNC spike marker 2");
      const m = list[0];
      expect(m, "marker 2 not found");
      expect(tx(project, (ca) => add(ca, m.createSetColorByIndexAction(ppro.Constants.MarkerColor.RED))), "set colour transaction returned false");
      const after = (await ppro.Markers.getMarkers(seq)).getMarkers().find((x) => x.getName() === "WNC spike marker 2");
      expect(after && after.getColorIndex() === ppro.Constants.MarkerColor.RED, `colour index read back ${after?.getColorIndex()}, wanted ${ppro.Constants.MarkerColor.RED}`);
      return { color_index: after.getColorIndex() };
    });
    return steps.outcome();
  },
};

const undoTransaction: ProbeDef<Ctx> = {
  op: "undo_transaction",
  run: async (ctx) => {
    const { ppro } = ctx;
    const project = await getProject(ctx);
    const seq = await getSequence(ctx);
    const steps = new Steps();
    // Is there any undo / history API at all? (the d.ts has none; check what the runtime really exposes)
    await steps.run("history API discovery (undo step count)", async () => {
      const names = (o: unknown) => (o && (typeof o === "object" || typeof o === "function") ? Object.getOwnPropertyNames(o) : []);
      const rx = /undo|redo|history/i;
      const found = {
        ppro_members: names(ppro).filter((n) => rx.test(n)),
        project_members: [...names(project), ...names(Object.getPrototypeOf(project))].filter((n) => rx.test(n)),
        sequence_members: [...names(seq), ...names(Object.getPrototypeOf(seq))].filter((n) => rx.test(n)),
      };
      return { ...found, history_step_count: found.ppro_members.length + found.project_members.length + found.sequence_members.length === 0 ? "not exposed by the API" : "see members" };
    });
    await steps.run("one_transaction_three_actions", async () => {
      const track = await seq.getVideoTrack(0);
      const aTrack = await seq.getAudioTrack(0);
      const markersObj = await ppro.Markers.getMarkers(seq);
      const stateOf = async () => ({ v1: (await seq.getVideoTrack(0)).name, a1: (await seq.getAudioTrack(0)).name, markers: (await ppro.Markers.getMarkers(seq)).getMarkers().map((m) => m.getName()) });
      const before = await stateOf();
      const wanted = "WNC Undo Test";
      const returned = tx(project, (ca) => {
        add(ca, track.createSetNameAction(wanted));
        add(ca, markersObj.createAddMarkerAction("WNC undo marker", ppro.Marker.MARKER_TYPE_COMMENT, tickSeconds(ctx, 4), tickSeconds(ctx, 0), "added in the same transaction"));
        add(ca, aTrack.createSetNameAction("WNC Undo Test A1"));
      }, UNDO_LABEL);
      expect(returned, "executeTransaction returned false");
      const after = await stateOf();
      expect(after.v1 === wanted && after.markers.length === before.markers.length + 1, `track "${after.v1}", markers ${before.markers.length}->${after.markers.length}`);
      ctx.expect.videoTrackName = after.v1;
      ctx.expect.markerCount = after.markers.length;
      return {
        undo_label: UNDO_LABEL,
        executeTransaction_returned: returned,
        state_before: before,
        state_after: after,
        manual_check: `Window \u25b8 History: the last entry is '${UNDO_LABEL}'; press Ctrl+Z once; V1 name back to "${before.v1}", A1 back to "${before.a1}", marker 'WNC undo marker' gone (before: ${JSON.stringify(before.markers)}). Then Ctrl+Shift+Z to redo.`,
      };
    });
    return steps.outcome();
  },
};

const OPEN_NOTE = "Project.open: a modal 'Scratch Disk Error' or 'Project Modified' dialog may block here; note which step shows it (see each step's `at` timestamp)";

const saveCloseOpen: ProbeDef<Ctx> = {
  op: "save_close_open",
  timeoutMs: 300_000,
  run: async (ctx) => {
    if (skipSaveCloseOpen.value) return { ok: null, detail: "skipped (Run, keep project open) so Window > History can be inspected" };
    const { ppro } = ctx;
    const project = await getProject(ctx);
    const steps = new Steps();
    const rawPath = project.path;
    const path = cleanPath(rawPath);
    await steps.run("save (explicit)", async () => {
      const before = await statOf(ctx.fs, path);
      const saved = await project.save();
      const st = await statOf(ctx.fs, path);
      expect(saved && st.exists && (st.bytes ?? 0) > 0, `save returned ${saved}; file ${JSON.stringify(st)}`);
      return { path_raw_json: JSON.stringify(rawPath), path, bytes_before: before.bytes, bytes_after: st.bytes, note: "each step carries `at` (ISO start) and `ms`: the dialog is attributed to the step whose ms is long" };
    });
    const isProject = await steps.run("Project.isProject(path) before closing", async () => ({ clean: ppro.Project.isProject(path), raw: ppro.Project.isProject(rawPath) }));
    void isProject;
    await steps.run("close (setPromptIfDirty(false) after the explicit save)", async () => {
      const closed = await project.close(new ppro.CloseProjectOptions().setPromptIfDirty(false).setSaveWorkspace(false).setShowCancelButton(false));
      expect(closed, "project.close returned false");
      ctx.project = undefined;
      ctx.sequence = undefined;
      ctx.target = undefined;
      return { closed };
    });
    const variants: Array<{ label: string; p: string; opts: boolean }> = [
      { label: "cleaned forward-slash path, no options", p: path, opts: false },
      { label: "raw \\\\?\\ path as Premiere reported it, no options", p: rawPath, opts: false },
      { label: "cleaned path + all four dialog-suppression options (the 0.1.1 call)", p: path, opts: true },
      { label: "backslash path, no options", p: path.replace(/\//g, "\\"), opts: false },
    ];
    let reopened: Project | undefined;
    for (const [i, v] of variants.entries()) {
      reopened = await steps.run(`open attempt ${i + 1}: ${v.label}`, async () => {
        const diag: Record<string, unknown> = { path_used_json: JSON.stringify(v.p), note: OPEN_NOTE };
        try {
          const options = v.opts ? new ppro.OpenProjectOptions().setShowConvertProjectDialog(false).setShowLocateFileDialog(false).setShowWarningDialog(false).setAddToMRUList(false) : undefined;
          const p = options ? await ppro.Project.open(v.p, options) : await ppro.Project.open(v.p);
          expect(p, "Project.open returned nothing");
          return p;
        } catch (e) {
          return failWith(`Project.open failed: ${errText(e)}`, { ...diag, error: errDetail(e) });
        }
      });
      if (reopened) break;
    }
    if (reopened) {
      const p = reopened;
      await steps.run("verify persisted (track name, marker count)", async () => {
        ctx.project = p;
        assertScratchProject(ctx, p);
        const seqs = await p.getSequences();
        const seq = seqs.find((s) => s.name === ctx.expect.sequenceName) ?? seqs[0];
        expect(seq, "no sequences after reopen");
        ctx.sequence = seq;
        const v1 = (await seq.getVideoTrack(0)).name;
        const markerCount = (await ppro.Markers.getMarkers(seq)).getMarkers().length;
        expect(ctx.expect.videoTrackName === undefined || v1 === ctx.expect.videoTrackName, `V1 name after reopen "${v1}", expected "${ctx.expect.videoTrackName}"`);
        const v2 = (await seq.getVideoTrack(1)).name;
        expect(ctx.expect.renamedVideoTrackName === undefined || v2 === ctx.expect.renamedVideoTrackName, `V2 name after reopen "${v2}", expected "${ctx.expect.renamedVideoTrackName}"`);
        expect(ctx.expect.markerCount === undefined || markerCount === ctx.expect.markerCount, `markers after reopen ${markerCount}, expected ${ctx.expect.markerCount}`);
        return { sequences: seqs.length, sequence: seq.name, v1_name: v1, v2_name: v2, markers: markerCount };
      });
    }
    return steps.outcome();
  },
};

const saveAs: ProbeDef<Ctx> = {
  op: "save_as",
  timeoutMs: 180_000,
  run: async (ctx) => {
    if (skipSaveCloseOpen.value) return { ok: null, detail: "skipped (Run, keep project open)" };
    const cfg = needConfig(ctx);
    if (!ctx.project) return { ok: null, detail: "no open scratch project (the reopen in save_close_open did not succeed)" };
    const project = await getProject(ctx);
    const steps = new Steps();
    await steps.run("saveAs a copy under work_dir", async () => {
      const target = `${cleanPath(cfg.work_dir)}/spike-${ctx.stamp}-copy.prproj`;
      const before = project.path;
      const returned = await project.saveAs(target);
      const after = project.path;
      assertScratchProject(ctx, project);
      const st = await statOf(ctx.fs, cleanPath(after));
      expect(returned && st.exists, `saveAs returned ${returned}; file ${JSON.stringify(st)}`);
      return { target, path_before_json: JSON.stringify(before), path_after_json: JSON.stringify(after), project_object_now_points_to_copy: normPath(after) === normPath(target), bytes: st.bytes };
    });
    return steps.outcome();
  },
};

/**
 * adobe.md names ProjectUtils.getProjectViewIds as the only way to activate another open project. Other open projects
 * belong to the editor: their names and paths are NOT written to the results, only whether each view is the scratch one.
 */
const projectViews: ProbeDef<Ctx> = {
  op: "project_views",
  run: async (ctx) => {
    const { ppro } = ctx;
    const cfg = needConfig(ctx);
    const steps = new Steps();
    await steps.run("ProjectUtils.getProjectViewIds + getProjectFromViewId", async () => {
      const ids = await ppro.ProjectUtils.getProjectViewIds();
      const views: Array<{ name_is_scratch: boolean }> = [];
      let scratch: { name: string; path_json: string } | null = null;
      for (const id of ids) {
        const p = await ppro.ProjectUtils.getProjectFromViewId(id);
        const isScratch = isUnder(p.path, cfg.work_dir);
        views.push({ name_is_scratch: isScratch });
        if (isScratch) scratch = { name: p.name, path_json: JSON.stringify(p.path) };
      }
      expect(ids.length > 0, "no project views");
      return { count: ids.length, views, scratch_project: scratch };
    });
    return steps.outcome();
  },
};

/** X1: Premiere's encoder as the frame-export fallback. Off unless config.json has "encoder_export": true (may open AME). */
const encoderExport: ProbeDef<Ctx> = {
  op: "encoder_export",
  timeoutMs: 240_000,
  run: async (ctx) => {
    const cfg = needConfig(ctx);
    if (cfg.encoder_export !== true) return { ok: null, detail: 'off: set "encoder_export": true in config.json to try EncoderManager.exportSequence (may start Media Encoder)' };
    const { ppro } = ctx;
    await getProject(ctx);
    const seq = await getSequence(ctx);
    const steps = new Steps();
    const dir = `${cleanPath(cfg.work_dir)}/encoder`;
    await ensureDir(ctx.fs, dir);
    await steps.run("EncoderManager.exportSequence(IMMEDIATELY) without a preset", async () => {
      const mgr = ppro.EncoderManager.getManager();
      const out = `${dir}/spike-${ctx.stamp}.mp4`;
      const returned = await mgr.exportSequence(seq, ppro.Constants.ExportType.IMMEDIATELY, out, undefined, true);
      const poll = await pollFile(ctx.fs, out, 60_000, 500);
      const info = { is_ame_installed: mgr.isAMEInstalled, output: out, returned, ...poll };
      if (!poll.found) failWith("no output file appeared", info);
      return info;
    });
    return steps.outcome();
  },
};

/** Read-only probes: safe without a validated config. Every other probe changes a project, so it needs one. */
const READ_ONLY_OPS = new Set(["host_info", "ws_loopback"]);

/**
 * scratch_disk runs right after create_project. undo_transaction is the LAST mutating probe (just before save_close_open),
 * so that after the run Window > History ends with "WhyNot Cut build" and one Ctrl+Z undoes exactly that transaction.
 * With keepOpen the run stops right after it (nothing closes the project or adds history).
 */
export function buildProbes(opts: { keepOpen?: boolean } = {}): ProbeDef<Ctx>[] {
  const all = [hostInfo, wsLoopback, createProject, scratchDisk, importXml, sequenceSettings, exportFrame, keyframes, keyframeTimeBasis, effects, clipEdits, trackRename, markers, projectViews, undoTransaction, saveCloseOpen, saveAs, encoderExport];
  const list = opts.keepOpen ? all.slice(0, all.indexOf(undoTransaction) + 1) : all;
  return list.map((def) => ({
    ...def,
    run: async (ctx: Ctx): Promise<ProbeOutcome> => {
      currentOp = def.op;
      if (!READ_ONLY_OPS.has(def.op) && !ctx.config) return { ok: null, detail: `no config (${ctx.configError ?? "config.json not loaded"})` };
      return def.run(ctx);
    },
  }));
}

// ---------------------------------------------------------------------------------------------- context

export async function loadConfig(fs: UxpFs, dir: string): Promise<{ config: SpikeConfig | null; error: string | null }> {
  try {
    const text = await readText(fs, `${dir}/config.json`);
    const parsed = JSON.parse(text) as Partial<SpikeConfig>;
    const missing = (["xml_path", "work_dir"] as const).filter((k) => typeof parsed[k] !== "string" || parsed[k] === "");
    if (missing.length) return { config: null, error: `config.json is missing: ${missing.join(", ")}` };
    // Everything the spike reads or writes must live under .../Editing Plugin/whynot-test/ (never WhyNot Clients).
    // A config that fails is treated as missing, so only the read-only probes run.
    for (const key of ["work_dir", "xml_path", "still_png"] as const) {
      const value = parsed[key];
      if (typeof value !== "string" || value === "") continue;
      const problem = scratchPathProblem(value);
      if (problem) return { config: null, error: `config.json rejected: ${key} (${normPath(value)}) ${problem}` };
    }
    if (typeof parsed.ws_url === "string" && !/^ws:\/\/(127\.0\.0\.1|localhost)(:\d+)?(\/|$)/i.test(parsed.ws_url)) {
      return { config: null, error: `config.json rejected: ws_url must be a ws://127.0.0.1 address` };
    }
    return { config: parsed as SpikeConfig, error: null };
  } catch (e) {
    return { config: null, error: `cannot read ${dir}/config.json: ${errText(e)}` };
  }
}
