// The spike probes. Each one is independent (own try/catch + timing via runner.ts) and records what actually
// happened in `detail` - nothing here is assumed to work. Match names are discovered at runtime, never hard-coded
// guesses: the component chain is dumped into `detail` and components are picked by regex on match/display name.
import type {
  Component,
  CompoundAction,
  PointF,
  Project,
  Sequence,
  VideoClipTrackItem,
  VideoComponentChain,
  premierepro as Ppro,
} from "@adobe/premierepro";
import { baseName, ensureDir, readText, statOf, writeText } from "./fsutil.ts";
import { toForwardSlashes } from "./home.ts";
import { jsonSafe, type ProbeDef, type ProbeOutcome } from "./runner.ts";
import type { UxpFs, UxpModule, UxpOs } from "./uxp-types.ts";

export const UNDO_LABEL = "WhyNot Cut build";

/** Set by the UI: "Run (keep project open)" skips save_close_open so Edit > Undo can be inspected afterwards. */
export const skipSaveCloseOpen = { value: false };

export interface SpikeConfig {
  xml_path: string;
  work_dir: string;
  ws_url?: string;
  still_png?: string;
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
  /** what later probes expect to find again after save/close/open */
  expect: { videoTrackName?: string; markerCount?: number; sequenceName?: string };
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
      this.steps.push({ step, ok: true, ms: Date.now() - t0, ...(info === undefined ? {} : { info: jsonSafe(info) }) });
      return info;
    } catch (e) {
      this.steps.push({ step, ok: false, ms: Date.now() - t0, error: errText(e) });
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
function tx(project: Project, build: (ca: CompoundAction) => void, label: string = UNDO_LABEL): boolean {
  let result = false;
  project.lockedAccess(() => {
    result = project.executeTransaction((ca) => build(ca), label);
  });
  return result;
}

function add(ca: CompoundAction, action: Parameters<CompoundAction["addAction"]>[0]): void {
  if (!ca.addAction(action)) throw new Error("CompoundAction.addAction returned false");
}

async function getProject(ctx: Ctx): Promise<Project> {
  if (ctx.project) return ctx.project;
  const p = await ctx.ppro.Project.getActiveProject();
  expect(p, "no active project (create_project did not succeed)");
  ctx.project = p;
  return p;
}

async function getSequence(ctx: Ctx): Promise<Sequence> {
  if (ctx.sequence) return ctx.sequence;
  const project = await getProject(ctx);
  const s = await project.getActiveSequence();
  expect(s, "no active sequence (import_fcp7_xml did not succeed)");
  ctx.sequence = s;
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
  expect(times.length >= 2, `expected >= 2 keyframes, read back ${times.length}`);
  return { param: param.displayName, set: [a, b], read_back_times_s: times, value_at_mid: mid, timeVarying: param.isTimeVarying() };
}

/** The clip the effect/keyframe probes work on: a placed still (config.still_png) or, failing that, any clip. */
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
      const norm = (s: string) => toForwardSlashes(s).toLowerCase();
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
    const host = ctx.uxp.host ?? {};
    const detail: Record<string, unknown> = {
      host: { name: host.name, version: host.version, uiLocale: host.uiLocale },
      uxp_versions: ctx.uxp.versions ?? null,
      premiere_version: null,
      get_background_color: typeof host.getBackgroundColor,
      background_color: null,
      host_keys: Object.getOwnPropertyNames(host),
      os: { platform: ctx.os?.platform?.(), release: ctx.os?.release?.(), arch: ctx.os?.arch?.() },
      home: ctx.home,
      home_via: ctx.homeVia,
      config_loaded: ctx.config !== null,
      config_error: ctx.configError,
      fs_members: Object.fromEntries(
        ["readFile", "writeFile", "mkdir", "lstat", "readdir", "readFileSync", "writeFileSync", "mkdirSync", "lstatSync", "existsSync"].map((k) => [k, typeof ctx.fs[k]]),
      ),
      globals: {
        WebSocket: typeof (globalThis as { WebSocket?: unknown }).WebSocket,
        fetch: typeof (globalThis as { fetch?: unknown }).fetch,
        clipboard: typeof (globalThis as { navigator?: { clipboard?: unknown } }).navigator?.clipboard,
        TextDecoder: typeof TextDecoder,
      },
      ppro_members: Object.getOwnPropertyNames(ctx.ppro).slice(0, 120),
    };
    try {
      detail.premiere_version = await ctx.ppro.Application.version;
    } catch (e) {
      detail.premiere_version_error = errText(e);
    }
    if (typeof host.getBackgroundColor === "function") {
      try {
        detail.background_color = jsonSafe(host.getBackgroundColor());
      } catch (e) {
        detail.background_color_error = errText(e);
      }
    }
    try {
      detail.prefers_dark = (globalThis as { matchMedia?: (q: string) => { matches: boolean } }).matchMedia?.("(prefers-color-scheme: dark)")?.matches ?? null;
    } catch {
      detail.prefers_dark = null;
    }
    try {
      const active = await ctx.ppro.Project.getActiveProject();
      detail.active_project = active ? { name: active.name, path: active.path } : null;
    } catch (e) {
      detail.active_project_error = errText(e);
    }
    return { ok: Boolean(host.name || host.version), detail };
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
  run: async (ctx) => {
    const cfg = needConfig(ctx);
    const workDir = toForwardSlashes(cfg.work_dir).replace(/\/+$/, "");
    await ensureDir(ctx.fs, workDir);
    const path = `${workDir}/spike-${ctx.stamp}.prproj`;
    const project = await ctx.ppro.Project.createProject(path);
    expect(project, "createProject returned nothing");
    ctx.project = project;
    ctx.projectPath = toForwardSlashes(project.path || path);
    const active = await ctx.ppro.Project.getActiveProject();
    return {
      ok: true,
      detail: {
        requested: path,
        name: project.name,
        path: project.path,
        is_active: active ? toForwardSlashes(active.path) === toForwardSlashes(project.path) : false,
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
    const seq = fresh[fresh.length - 1] ?? all[all.length - 1];
    expect(seq, `importFiles returned ${importedOk} but the project has no sequence`);
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

    // The engine's targets (ppro_build.py): ProRes 422 LT previews, linear colour on, 8-bit, no max render quality.
    const apply = async (label: string, change: (s: Awaited<ReturnType<Sequence["getSettings"]>>) => Promise<unknown>, read: (s: Awaited<ReturnType<Sequence["getSettings"]>>) => Promise<unknown>, want: unknown) => {
      const before = await read(await seq.getSettings());
      const s = await seq.getSettings();
      const setterResult = await change(s);
      expect(tx(project, (ca) => add(ca, seq.createSetSettingsAction(s))), `${label}: createSetSettingsAction transaction returned false`);
      const after = await read(await seq.getSettings());
      const info = { before, wanted: want, after, setter_returned: setterResult };
      expect(JSON.stringify(after) === JSON.stringify(want), `${label}: read back ${JSON.stringify(after)} but wanted ${JSON.stringify(want)} (before ${JSON.stringify(before)})`);
      return info;
    };
    await steps.run("preview_codec=apcs (ProRes 422 LT)", () => apply("previewCodec", (s) => s.setPreviewCodec("apcs"), (s) => s.getPreviewCodec(), "apcs"));
    await steps.run("composite_in_linear_color=true", () => apply("compositeInLinearColor", (s) => s.setCompositeInLinearColor(true), (s) => s.getCompositeInLinearColor(), true));
    await steps.run("maximum_bit_depth=false", () => apply("maximumBitDepth", (s) => s.setMaximumBitDepth(false), (s) => s.getMaximumBitDepth(), false));
    await steps.run("max_render_quality=false", () => apply("maxRenderQuality", (s) => s.setMaxRenderQuality(false), (s) => s.getMaxRenderQuality(), false));
    await steps.run("toggle_each_bool_and_back", async () => {
      const out: Record<string, unknown> = {};
      for (const [name, get, set] of [
        ["composite_in_linear_color", (s: Awaited<ReturnType<Sequence["getSettings"]>>) => s.getCompositeInLinearColor(), (s: Awaited<ReturnType<Sequence["getSettings"]>>, v: boolean) => s.setCompositeInLinearColor(v)],
        ["maximum_bit_depth", (s: Awaited<ReturnType<Sequence["getSettings"]>>) => s.getMaximumBitDepth(), (s: Awaited<ReturnType<Sequence["getSettings"]>>, v: boolean) => s.setMaximumBitDepth(v)],
        ["max_render_quality", (s: Awaited<ReturnType<Sequence["getSettings"]>>) => s.getMaxRenderQuality(), (s: Awaited<ReturnType<Sequence["getSettings"]>>, v: boolean) => s.setMaxRenderQuality(v)],
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

const exportFrame: ProbeDef<Ctx> = {
  op: "export_frame",
  timeoutMs: 180_000,
  run: async (ctx) => {
    const cfg = needConfig(ctx);
    const { ppro } = ctx;
    const seq = await getSequence(ctx);
    const frame = await seq.getFrameSize();
    const endS = (await seq.getEndTime()).seconds;
    const dir = `${toForwardSlashes(cfg.work_dir).replace(/\/+$/, "")}/frames`;
    await ensureDir(ctx.fs, dir);
    const times = [Math.min(1, endS / 4), endS / 2].map((t) => Math.max(0, Math.round(t * 1000) / 1000));
    const steps = new Steps();
    let i = 0;
    for (const t of times) {
      i++;
      await steps.run(`frame_${i}_at_${t}s`, async () => {
        const name = `spike_frame_${ctx.stamp}_${i}.png`;
        const t0 = Date.now();
        // exportSequenceFrame(sequence, time, filename, filepath, w, h): the doc example shows filename as a full
        // path but names the folder in `filepath`; try (name, dir/) first, then (full path, dir/).
        const attempts: Array<{ form: string; filename: string; returned?: boolean; error?: string; exists: boolean; bytes: number | null }> = [];
        let winner: (typeof attempts)[number] | undefined;
        for (const [form, filename] of [["name + dir/", name], ["full path + dir/", `${dir}/${name.replace(".png", "_b.png")}`]] as const) {
          const rec: (typeof attempts)[number] = { form, filename, exists: false, bytes: null };
          try {
            rec.returned = await ppro.Exporter.exportSequenceFrame(seq, tickSeconds(ctx, t), filename, `${dir}/`, frame.width, frame.height);
          } catch (e) {
            rec.error = errText(e);
          }
          const target = form === "name + dir/" ? `${dir}/${name}` : filename;
          const st = await statOf(ctx.fs, target);
          rec.exists = st.exists;
          rec.bytes = st.bytes;
          attempts.push(rec);
          if (st.exists && (st.bytes ?? 0) > 0) {
            winner = rec;
            break;
          }
        }
        expect(winner, `no PNG appeared in ${dir}: ${JSON.stringify(attempts)}`);
        return { t_s: t, ms: Date.now() - t0, width: frame.width, height: frame.height, used: winner.form, path: winner.form === "name + dir/" ? `${dir}/${name}` : winner.filename, bytes: winner.bytes, attempts };
      });
    }
    return steps.outcome({ sequence_end_s: endS, out_dir: dir });
  },
};

const keyframes: ProbeDef<Ctx> = {
  op: "keyframes_motion_opacity_crop",
  timeoutMs: 180_000,
  run: async (ctx) => {
    const { ppro } = ctx;
    const project = await getProject(ctx);
    const steps = new Steps();
    const target = await steps.run("place_still_or_pick_clip", async () => {
      const t = await ensureTarget(ctx);
      return { source: t.source, track_index: t.trackIndex, start_s: (await t.clip.getStartTime()).seconds, end_s: (await t.clip.getEndTime()).seconds, in_point_s: (await t.clip.getInPoint()).seconds, notes: ctx.notes.slice() };
    });
    if (!target || !ctx.target) return steps.outcome();
    const clip = ctx.target.clip;
    const chain = await clip.getComponentChain();
    await steps.run("dump_component_chain", async () => await dumpChain(chain));

    const motion = await findComponent(chain, /ADBE Motion/i);
    await steps.run("motion_found", async () => {
      expect(motion, "no component matching /ADBE Motion/ in the chain");
      return { matchName: motion.matchName };
    });
    if (motion) {
      await steps.run("motion.scale 100->110", () => numericKeyframes(ctx, project, motion.comp, /^scale$/i, { t: 0, v: 100 }, { t: 1, v: 110 }));
      await steps.run("motion.rotation 0->5", () => numericKeyframes(ctx, project, motion.comp, /^rotation$/i, { t: 0, v: 0 }, { t: 1, v: 5 }));
      await steps.run("motion.position (PointF)", async () => {
        const found = findParam(motion.comp, /^position$/i);
        expect(found, "no param matching /^position$/");
        const { param } = found;
        const start = (await param.getStartValue()).value.value as PointF;
        const kA = param.createKeyframe(new ppro.PointF(start.x, start.y));
        kA.position = tickSeconds(ctx, 0);
        const kB = param.createKeyframe(new ppro.PointF(start.x + 0.05, start.y));
        kB.position = tickSeconds(ctx, 1);
        expect(tx(project, (ca) => add(ca, param.createSetTimeVaryingAction(true))), "setTimeVarying transaction returned false");
        expect(
          tx(project, (ca) => {
            add(ca, param.createAddKeyframeAction(kA));
            add(ca, param.createAddKeyframeAction(kB));
          }),
          "addKeyframe transaction returned false",
        );
        const times = param.getKeyframeListAsTickTimes().map((t) => t.seconds);
        expect(times.length >= 2, `expected >= 2 position keyframes, read back ${times.length}`);
        return { start: { x: start.x, y: start.y }, read_back_times_s: times, value_at_1s: await param.getValueAtTime(tickSeconds(ctx, 1)) };
      });
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

    let crop = await findComponent(chain, /ADBE Crop/i);
    if (!crop) {
      await steps.run("crop: add via VideoFilterFactory", async () => {
        const names = await ppro.VideoFilterFactory.getMatchNames();
        const cands = names.filter((n) => /ADBE Crop/i.test(n));
        expect(cands.length > 0, "no filter match name matching /ADBE Crop/ in VideoFilterFactory");
        const pick = cands.find((n) => /^AE\.ADBE Crop$/i.test(n)) ?? cands[0] ?? "";
        const comp = await ppro.VideoFilterFactory.createComponent(pick);
        expect(tx(project, (ca) => add(ca, chain.createAppendComponentAction(comp))), "append crop transaction returned false");
        crop = await findComponent(chain, /ADBE Crop/i);
        expect(crop, "crop not in the chain after append");
        return { candidates: cands, used: pick };
      });
    }
    if (crop) {
      const c = crop;
      await steps.run("crop.left 0->10", () => numericKeyframes(ctx, project, c.comp, /^left$/i, { t: 0, v: 0 }, { t: 1, v: 10 }));
      await steps.run("crop.top 0->5", () => numericKeyframes(ctx, project, c.comp, /^top$/i, { t: 0, v: 0 }, { t: 1, v: 5 }));
    }
    return steps.outcome();
  },
};

const FILTER_TARGETS: Array<{ key: string; display: RegExp; match: RegExp }> = [
  { key: "gaussian_blur", display: /^gaussian blur$/i, match: /gaussian blur/i },
  { key: "sharpen", display: /^sharpen$/i, match: /ADBE Sharpen/i },
  { key: "noise", display: /^noise$/i, match: /ADBE Noise$/i },
];

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
    const chain = await ctx.target.clip.getComponentChain();
    for (const f of FILTER_TARGETS) {
      await steps.run(`${f.key}: create + append + read back`, async () => {
        const byMatch = holder.matchNames.filter((n) => f.match.test(n));
        const byDisplayIdx = holder.displayNames.map((d, i) => (f.display.test(d) ? i : -1)).filter((i) => i >= 0);
        const viaDisplay = lists.parallel_arrays ? byDisplayIdx.map((i) => holder.matchNames[i] ?? "") : [];
        const candidates = [...new Set([...viaDisplay, ...byMatch])].filter(Boolean);
        expect(candidates.length > 0, `no filter matching ${f.display} / ${f.match} (of ${lists.match_names} filters)`);
        const pick = candidates[0] ?? "";
        const before = chain.getComponentCount();
        const comp = await ppro.VideoFilterFactory.createComponent(pick);
        expect(tx(project, (ca) => add(ca, chain.createAppendComponentAction(comp))), "append transaction returned false");
        const after = chain.getComponentCount();
        expect(after === before + 1, `chain had ${before} components, ${after} after append`);
        const added = chain.getComponentAtIndex(after - 1);
        const info: Record<string, unknown> = { candidates, used: pick, chain_before: before, chain_after: after, added_match_name: await added.getMatchName(), added_display_name: await added.getDisplayName() };
        const params: string[] = [];
        for (let j = 0; j < added.getParamCount(); j++) params.push(added.getParam(j).displayName);
        info.params = params;
        if (f.key === "gaussian_blur") {
          const blur = findParam(added, /blurriness/i);
          expect(blur, `no Blurriness param among ${params.join(", ")}`);
          const kf = blur.param.createKeyframe(25);
          expect(tx(project, (ca) => add(ca, blur.param.createSetValueAction(kf))), "setValue transaction returned false");
          info.blurriness_set_25_read_back = await blur.param.getValueAtTime(tickSeconds(ctx, 0));
        }
        return info;
      });
    }
    return steps.outcome({ filters_total: lists.match_names, filters_file: lists.file });
  },
};

const trackRename: ProbeDef<Ctx> = {
  op: "track_rename",
  run: async (ctx) => {
    const project = await getProject(ctx);
    const seq = await getSequence(ctx);
    const steps = new Steps();
    await steps.run("video_track_0", async () => {
      const track = await seq.getVideoTrack(0);
      const before = track.name;
      const wanted = "WNC Spike V1";
      expect(tx(project, (ca) => add(ca, track.createSetNameAction(wanted))), "rename transaction returned false");
      const after = (await seq.getVideoTrack(0)).name;
      expect(after === wanted, `video track read back "${after}", wanted "${wanted}" (was "${before}")`);
      ctx.expect.videoTrackName = after;
      return { before, after };
    });
    await steps.run("audio_track_0", async () => {
      expect((await seq.getAudioTrackCount()) > 0, "sequence has no audio tracks");
      const track = await seq.getAudioTrack(0);
      const before = track.name;
      const wanted = "WNC Spike A1";
      expect(tx(project, (ca) => add(ca, track.createSetNameAction(wanted))), "rename transaction returned false");
      const after = (await seq.getAudioTrack(0)).name;
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
    await steps.run("one_transaction_three_actions", async () => {
      const track = await seq.getVideoTrack(0);
      const aTrack = await seq.getAudioTrack(0);
      const markersObj = await ppro.Markers.getMarkers(seq);
      const beforeCount = markersObj.getMarkers().length;
      const wanted = "WNC Undo Test";
      const returned = tx(project, (ca) => {
        add(ca, track.createSetNameAction(wanted));
        add(ca, markersObj.createAddMarkerAction("WNC undo marker", ppro.Marker.MARKER_TYPE_COMMENT, tickSeconds(ctx, 4), tickSeconds(ctx, 0), "added in the same transaction"));
        add(ca, aTrack.createSetNameAction("WNC Undo Test A1"));
      }, UNDO_LABEL);
      expect(returned, "executeTransaction returned false");
      const after = (await seq.getVideoTrack(0)).name;
      const afterMarkers = (await ppro.Markers.getMarkers(seq)).getMarkers().length;
      expect(after === wanted && afterMarkers === beforeCount + 1, `track "${after}", markers ${beforeCount}->${afterMarkers}`);
      ctx.expect.videoTrackName = after;
      ctx.expect.markerCount = afterMarkers;
      return {
        undo_label: UNDO_LABEL,
        executeTransaction_returned: returned,
        manual_check: `Edit menu must now read "Undo ${UNDO_LABEL}" and ONE Ctrl+Z must revert the track name and the marker together`,
      };
    });
    return steps.outcome();
  },
};

const saveCloseOpen: ProbeDef<Ctx> = {
  op: "save_close_open",
  timeoutMs: 180_000,
  run: async (ctx) => {
    if (skipSaveCloseOpen.value) return { ok: null, detail: "skipped (Run, keep project open) so Edit > Undo can be inspected" };
    const { ppro } = ctx;
    const project = await getProject(ctx);
    const steps = new Steps();
    const path = project.path;
    await steps.run("save", async () => {
      const saved = await project.save();
      const st = await statOf(ctx.fs, toForwardSlashes(path));
      expect(saved && st.exists && (st.bytes ?? 0) > 0, `save returned ${saved}; file ${JSON.stringify(st)}`);
      return { path, bytes: st.bytes };
    });
    await steps.run("close", async () => {
      const closed = await project.close(new ppro.CloseProjectOptions().setPromptIfDirty(false).setSaveWorkspace(false).setShowCancelButton(false));
      expect(closed, "project.close returned false");
      ctx.project = undefined;
      ctx.sequence = undefined;
      ctx.target = undefined;
      return { closed };
    });
    await steps.run("open + verify persisted", async () => {
      const reopened = await ppro.Project.open(path, new ppro.OpenProjectOptions().setShowConvertProjectDialog(false).setShowLocateFileDialog(false).setShowWarningDialog(false).setAddToMRUList(false));
      expect(reopened, "Project.open returned nothing");
      ctx.project = reopened;
      const seqs = await reopened.getSequences();
      const seq = seqs.find((s) => s.name === ctx.expect.sequenceName) ?? seqs[0];
      expect(seq, "no sequences after reopen");
      ctx.sequence = seq;
      const v1 = (await seq.getVideoTrack(0)).name;
      const markerCount = (await ppro.Markers.getMarkers(seq)).getMarkers().length;
      expect(ctx.expect.videoTrackName === undefined || v1 === ctx.expect.videoTrackName, `V1 name after reopen "${v1}", expected "${ctx.expect.videoTrackName}"`);
      expect(ctx.expect.markerCount === undefined || markerCount === ctx.expect.markerCount, `markers after reopen ${markerCount}, expected ${ctx.expect.markerCount}`);
      return { sequences: seqs.length, sequence: seq.name, v1_name: v1, markers: markerCount };
    });
    return steps.outcome();
  },
};

export function buildProbes(): ProbeDef<Ctx>[] {
  return [hostInfo, wsLoopback, createProject, importXml, sequenceSettings, exportFrame, keyframes, effects, trackRename, markers, undoTransaction, saveCloseOpen];
}

// ---------------------------------------------------------------------------------------------- context

export async function loadConfig(fs: UxpFs, dir: string): Promise<{ config: SpikeConfig | null; error: string | null }> {
  try {
    const text = await readText(fs, `${dir}/config.json`);
    const parsed = JSON.parse(text) as Partial<SpikeConfig>;
    const missing = (["xml_path", "work_dir"] as const).filter((k) => typeof parsed[k] !== "string" || parsed[k] === "");
    if (missing.length) return { config: null, error: `config.json is missing: ${missing.join(", ")}` };
    return { config: parsed as SpikeConfig, error: null };
  } catch (e) {
    return { config: null, error: `cannot read ${dir}/config.json: ${errText(e)}` };
  }
}
