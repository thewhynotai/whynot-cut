// Spike 0.1.2: the re-measurements (frame export forms, codec, Position, crop, time basis, effects by exact match
// name, scratch disks, save/close/open attribution, undo text, extra probes) against hand-made fakes of Premiere.
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildProbes, windowsDisjoint, classifyTimes, type Ctx, type SpikeConfig, type TargetClip } from "../spike/src/probes.ts";
import { runProbe } from "../spike/src/runner.ts";

const WT = "D:/0 Work/0 Pegasus IMC Agency/00 TWN/0 TWN AI/Editing Plugin/whynot-test";
const WORK = `${WT}/_uxp-spike`;
const CONFIG: SpikeConfig = { xml_path: `${WT}/a.xml`, work_dir: WORK, still_png: `${WT}/s.png` };

interface Act {
  apply: () => void;
}

function probe(op: string) {
  const p = buildProbes().find((d) => d.op === op);
  assert.ok(p, `no probe ${op}`);
  return p;
}

type Step = { step: string; ok: boolean; at: string; ms: number; info?: Record<string, unknown>; error?: string };
const stepsOf = (r: { detail: unknown }) => (r.detail as { steps: Step[] }).steps;
const stepNamed = (r: { detail: unknown }, prefix: string) => {
  const s = stepsOf(r).find((x) => x.step.startsWith(prefix));
  assert.ok(s, `no step starting with "${prefix}" in ${stepsOf(r).map((x) => x.step).join(" | ")}`);
  return s;
};

function fakeProject(extra: Record<string, unknown> = {}) {
  const labels: string[] = [];
  const project = {
    name: "spike.prproj",
    path: `\\\\?\\${WORK}/spike-1.prproj`,
    lockedAccess: (cb: () => void) => cb(),
    executeTransaction: (cb: (ca: { addAction: (a: Act) => boolean }) => void, label?: string) => {
      labels.push(label ?? "");
      cb({ addAction: (a) => (a.apply(), true) });
      return true;
    },
    ...extra,
  };
  return { project, labels };
}

function baseCtx(ppro: unknown, extra: Partial<Ctx> = {}): Ctx {
  return {
    ppro: ppro as Ctx["ppro"],
    fs: {},
    uxp: { host: { name: "premierepro", version: "26.5.2" }, versions: { uxp: "uxp-9.3.0-local" } },
    os: undefined,
    home: "C:/Users/LOQ",
    homeVia: "os.homedir",
    stamp: "20261012-120000",
    config: CONFIG,
    configError: null,
    expect: {},
    notes: [],
    ...extra,
  };
}

// ---- a fake ComponentParam with keyframes / static value -------------------------------------------------------

type Kf = { value: { value: unknown }; position: { seconds: number } };

function fakeParam(name: string, opts: { createKeyframe?: (v: unknown) => Kf; start?: unknown; staticValue?: unknown } = {}) {
  const kfs: Kf[] = [];
  let timeVarying = false;
  let staticValue: unknown = opts.staticValue ?? null;
  return {
    displayName: name,
    kfs,
    areKeyframesSupported: async () => true,
    isTimeVarying: () => timeVarying,
    createSetTimeVaryingAction: (b: boolean): Act => ({ apply: () => void (timeVarying = b) }),
    createKeyframe: opts.createKeyframe ?? ((value: unknown): Kf => ({ value: { value }, position: { seconds: 0 } })),
    createAddKeyframeAction: (k: Kf): Act => ({ apply: () => void kfs.push(k) }),
    createRemoveKeyframeAction: (t: { seconds: number }): Act => ({
      apply: () => {
        const i = kfs.findIndex((k) => k.position.seconds === t.seconds);
        if (i >= 0) kfs.splice(i, 1);
      },
    }),
    createSetValueAction: (k: Kf): Act => ({ apply: () => void (staticValue = k.value.value) }),
    createSetInterpolationAtKeyframeAction: (): Act => ({ apply: () => {} }),
    getKeyframeListAsTickTimes: () => kfs.map((k) => k.position),
    getKeyframePtr: () => ({ getTemporalInterpolationMode: async () => 5 }),
    getStartValue: async () => ({ value: { value: opts.start ?? staticValue } }),
    getValueAtTime: async (t: { seconds: number }) => {
      if (kfs.length === 0) return staticValue;
      return kfs.find((k) => k.position.seconds === t.seconds)?.value.value ?? kfs[0]?.value.value ?? null;
    },
  };
}

type FakeParam = ReturnType<typeof fakeParam>;

function fakeComp(match: string, params: FakeParam[]) {
  return { getMatchName: async () => match, getDisplayName: async () => match, getParamCount: () => params.length, getParam: (i: number) => params[i] as FakeParam, params };
}

function fakeChain(comps: Array<ReturnType<typeof fakeComp>>) {
  return {
    comps,
    getComponentCount: () => comps.length,
    getComponentAtIndex: (i: number) => comps[i],
    createAppendComponentAction: (c: ReturnType<typeof fakeComp>): Act => ({ apply: () => void comps.push(c) }),
  };
}

class FakePointF {
  x: number;
  y: number;
  constructor(x = 0, y = 0) {
    this.x = x;
    this.y = y;
  }
}

function fakeClip(w: { start: number; inP: number; end: number }, chain: ReturnType<typeof fakeChain>) {
  const st = { ...w };
  return {
    st,
    getStartTime: async () => ({ seconds: st.start }),
    getInPoint: async () => ({ seconds: st.inP }),
    getEndTime: async () => ({ seconds: st.end }),
    getOutPoint: async () => ({ seconds: st.inP + (st.end - st.start) }),
    getName: async () => "clip",
    isDisabled: async () => false,
    getComponentChain: async () => chain,
    createMoveAction: (t: { seconds: number }): Act => ({
      apply: () => {
        st.start += t.seconds;
        st.end += t.seconds;
      },
    }),
  };
}

const T = { createWithSeconds: (seconds: number) => ({ seconds }) };

// ---- host_info -------------------------------------------------------------------------------------------------

test("host_info: Application.version is informational (empty -> uxp.host.version) and uxp.versions is read explicitly", async () => {
  const versions = Object.defineProperty({}, "uxp", { value: "uxp-9.3.0-local", enumerable: false });
  const ctx = baseCtx({ Application: { version: Promise.resolve("") }, Project: { getActiveProject: async () => null } });
  ctx.uxp = { host: { name: "premierepro", version: "26.5.2" }, versions: versions as never };
  const r = await runProbe(probe("host_info"), ctx);
  assert.equal(r.ok, true);
  const pv = stepNamed(r, "premiere_version");
  assert.equal(pv.ok, true);
  assert.equal(pv.info?.value, "26.5.2");
  assert.equal(pv.info?.source, "uxp.host.version");
  const host = stepNamed(r, "uxp_host");
  assert.equal(host.info?.uxp_version, "uxp-9.3.0-local");
  assert.ok(stepsOf(r).every((s) => s.ok || s.step.startsWith("active_project")), "host_info ends clean");
  const ctx2 = baseCtx({ Application: { version: Promise.resolve("26.5.2") }, Project: { getActiveProject: async () => null } });
  assert.equal(stepNamed(await runProbe(probe("host_info"), ctx2), "premiere_version").info?.source, "Application.version");
});

test("every step record carries an ISO start time and a duration", async () => {
  const r = await runProbe(probe("host_info"), baseCtx({ Application: { version: Promise.resolve("x") } }));
  for (const s of stepsOf(r)) {
    assert.match(s.at, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/);
    assert.equal(typeof s.ms, "number");
  }
});

// ---- preview codec ---------------------------------------------------------------------------------------------

function fakeSequenceWithSettings(accepts: string[], orig = "Animation") {
  const state = { codec: orig, format: "QuickTime" };
  const returned: Array<{ what: string; value: string; accepted: boolean }> = [];
  const settings = () => {
    const pending = { ...state };
    return {
      pending,
      getPreviewCodec: async () => state.codec,
      getPreviewFileFormat: async () => state.format,
      setPreviewCodec: async (v: string) => {
        const accepted = v === orig || accepts.includes(v);
        returned.push({ what: "codec", value: v, accepted });
        if (accepted) pending.codec = v;
        return accepted;
      },
      setPreviewFileFormat: async (v: string) => {
        pending.format = v;
        return true;
      },
      getCompositeInLinearColor: async () => true,
      getMaximumBitDepth: async () => false,
      getMaxRenderQuality: async () => false,
      getEditingMode: async () => "Custom",
      getVideoFrameRect: async () => ({ width: 1080, height: 1920 }),
      getPreviewFrameRect: async () => ({ width: 1080, height: 1920 }),
      getVideoPixelAspectRatio: async () => "1:1",
      getVideoFieldType: async () => 0,
      getVideoFrameRate: () => ({ value: 24 }),
      getAudioChannelType: async () => 1,
      getAudioChannelCount: async () => 2,
      setCompositeInLinearColor: async () => true,
      setMaximumBitDepth: async () => true,
      setMaxRenderQuality: async () => true,
      setPreviewFrameRect: async () => true,
    };
  };
  const sequence = {
    name: "SEQ",
    getSettings: async () => settings(),
    createSetSettingsAction: (s: { pending: typeof state }): Act => ({ apply: () => Object.assign(state, s.pending) }),
  };
  return { sequence, state, returned };
}

test("preview codec: the round trip of the API's own value proves the setter, then display names are tried and the winner is kept", async () => {
  const f = fakeSequenceWithSettings(["Apple ProRes 422 LT"]);
  const { project, labels } = fakeProject();
  const ctx = baseCtx({ SequenceSettings: { PAR_SQUARE: "x" }, Constants: {}, RectF: function () {} }, { project: project as never, sequence: f.sequence as never });
  const r = await runProbe(probe("sequence_settings"), ctx);
  const step = stepNamed(r, "preview_codec");
  assert.equal(step.ok, true, JSON.stringify(step));
  const info = step.info as { round_trip_works: boolean; accepted_candidate: string; attempts: Array<Record<string, unknown>>; discovery: Record<string, unknown> };
  assert.equal(info.round_trip_works, true);
  assert.equal(info.accepted_candidate, "Apple ProRes 422 LT");
  assert.ok(info.attempts.every((a) => "setter_returned" in a || "error" in a), "every attempt keeps the setter return value");
  assert.equal(info.discovery.orig_codec, "Animation");
  assert.equal(f.state.codec, "Animation", "the original codec is restored after the winner was found");
  assert.ok(labels.every((l) => l === "WhyNot Cut build"));
  assert.ok(!f.returned.some((x) => x.value === "apcs"), "the FourCC is not tried before the display names");
});

test("preview codec: when no value takes, the step fails but keeps every setter return value", async () => {
  const f = fakeSequenceWithSettings([]);
  const { project } = fakeProject();
  const ctx = baseCtx({ SequenceSettings: {}, Constants: {}, RectF: function () {} }, { project: project as never, sequence: f.sequence as never });
  const r = await runProbe(probe("sequence_settings"), ctx);
  const step = stepNamed(r, "preview_codec");
  assert.equal(step.ok, false);
  assert.match(step.error ?? "", /no candidate value took/);
  const attempts = (step.info as { attempts: Array<{ setter_returned?: unknown; wanted?: string }> }).attempts;
  assert.ok(attempts.filter((a) => a.wanted).length >= 5);
  assert.ok(attempts.every((a) => a.setter_returned !== undefined));
});

// ---- export_frame ----------------------------------------------------------------------------------------------

function fakeFs() {
  const files = new Map<string, number>();
  const norm = (p: string) => p.replace(/\\/g, "/").toLowerCase();
  return {
    files,
    fs: {
      lstat: async (p: string) => {
        const key = norm(p);
        if (files.has(key)) return { size: files.get(key), isDirectory: () => false };
        if (!/\.(png|jpg|tif|bmp)$/.test(key)) return { size: 0, isDirectory: () => true };
        throw new Error("ENOENT");
      },
      mkdir: async () => {},
    },
    write: (p: string, bytes = 1234) => void files.set(norm(p), bytes),
  };
}

function exportRig(worksFor: (filename: string, filepath: string) => boolean) {
  const calls: Array<{ filename: string; filepath: string; returned: boolean }> = [];
  const vfs = fakeFs();
  const track = { getTrackItems: () => [{ getStartTime: async () => ({ seconds: 0.1667 }) }] };
  const { project } = fakeProject({ openSequence: async () => true, setActiveSequence: async () => true, getRootItem: async () => ({ getItems: async () => [] }) });
  const ppro = {
    TickTime: T,
    Constants: { TrackItemType: { CLIP: 1 } },
    ClipProjectItem: { cast: () => ({ isOffline: async () => false }) },
    Exporter: {
      exportSequenceFrame: async (_s: unknown, _t: unknown, filename: string, filepath: string) => {
        const ok = worksFor(filename, filepath);
        if (ok) {
          const full = /^[A-Za-z]:[\\/]/.test(filename) ? filename : `${filepath.replace(/[\\/]+$/, "")}/${filename}`;
          vfs.write(full);
        }
        calls.push({ filename, filepath, returned: ok });
        return ok;
      },
    },
  };
  const sequence = {
    name: "SEQ",
    getFrameSize: async () => ({ width: 1080, height: 1920 }),
    getEndTime: async () => ({ seconds: 30 }),
    getVideoTrack: async () => track,
    isDoneAnalyzingForVideoEffects: async () => true,
    setPlayerPosition: async () => true,
  };
  const ctx = baseCtx(ppro, { fs: vfs.fs, project: project as never, sequence: sequence as never, timing: { shortPollMs: 20, longPollMs: 40 } });
  ctx.uxp = { host: { name: "premierepro" }, storage: { localFileSystem: { getTemporaryFolder: async () => ({ nativePath: "C:\\Users\\LOQ\\AppData\\Local\\Temp\\uxp" }) } } };
  return { ctx, calls };
}

test("export_frame tries the d.ts example form, backslash forms, a no-space temp folder and finds the working one", async () => {
  const { ctx, calls } = exportRig((filename, filepath) => filepath.endsWith("\\") && !/^[A-Za-z]:/.test(filename));
  const r = await runProbe(probe("export_frame"), ctx);
  assert.equal(r.ok, true, JSON.stringify(r).slice(0, 600));
  const f1 = stepNamed(r, "frame 1");
  const info = f1.info as { winner: string; attempts: Array<{ form: string; returned: boolean; call_ms: number; found: boolean; filepath: string }> };
  assert.match(info.winner, /name \+ dir\\/);
  assert.ok(info.attempts.length >= 4);
  assert.ok(info.attempts.some((a) => a.form.includes("d.ts example form")), "the d.ts example form was tried");
  assert.ok(info.attempts.some((a) => a.filepath.endsWith("/") && a.returned === false), "forward-slash forms are logged with their false return value");
  assert.ok(info.attempts.every((a) => typeof a.call_ms === "number"));
  assert.equal(stepNamed(r, "frame 2").ok, true);
  assert.ok(typeof ctx.exportFrameTo === "function", "a working form is exposed for the time-basis probe");
  assert.ok(calls.length >= 5);
  const tmp = stepNamed(r, "temp folder");
  assert.equal((tmp.info as { has_spaces: boolean }).has_spaces, false);
});

test("export_frame: when no form works the step fails with every attempt and return value recorded, and nothing throws", async () => {
  const { ctx } = exportRig(() => false);
  const r = await runProbe(probe("export_frame"), ctx);
  assert.equal(r.ok, false);
  const f1 = stepNamed(r, "frame 1");
  assert.equal(f1.ok, false);
  assert.match(f1.error ?? "", /no export form produced a file/);
  const attempts = (f1.info as { attempts: Array<{ form: string; returned: boolean; filename: string; filepath: string }> }).attempts;
  assert.ok(attempts.length >= 17, `expected the full matrix, got ${attempts.length}`);
  assert.ok(attempts.every((a) => a.returned === false));
  const forms = attempts.map((a) => a.form).join(" ");
  for (const needle of ["work:", "temp:", ":jpg", ":tif", "backslashes", "d.ts example form"]) assert.ok(forms.includes(needle), needle);
  assert.equal(ctx.exportFrameTo, undefined);
});

// ---- Position, crop ---------------------------------------------------------------------------------------------

function keyframeRig(positionParam: FakeParam) {
  const motion = fakeComp("AE.ADBE Motion", [positionParam, fakeParam("Scale"), fakeParam("Rotation"), fakeParam("Crop Left"), fakeParam("Crop Top"), fakeParam("Crop Right"), fakeParam("Crop Bottom")]);
  const opacity = fakeComp("AE.ADBE Opacity", [fakeParam("Opacity")]);
  const chain = fakeChain([opacity, motion]);
  const clip = fakeClip({ start: 30, inP: 3599.96, end: 35 }, chain);
  const { project, labels } = fakeProject();
  const aeCrop = () => fakeComp("AE.ADBE AECrop", [fakeParam("Left"), fakeParam("Right"), fakeParam("Top"), fakeParam("Bottom")]);
  const ppro = {
    TickTime: T,
    PointF: FakePointF,
    Keyframe: { INTERPOLATION_MODE_BEZIER: 5 },
    Constants: { TrackItemType: { CLIP: 1 } },
    VideoFilterFactory: { getMatchNames: async () => ["AE.ADBE Opacity", "AE.ADBE AECrop"], createComponent: async () => aeCrop() },
  };
  const ctx = baseCtx(ppro, { project: project as never });
  ctx.sequence = { getFrameSize: async () => ({ width: 1080, height: 1920 }), getVideoTrackCount: async () => 1 } as never;
  ctx.target = { clip: clip as never, trackIndex: 0, source: "placed still" };
  return { ctx, chain, labels };
}

test("Position: createKeyframe is tried per value form, the PointF form is found, and the failing forms are named", async () => {
  const strict = fakeParam("Position", {
    start: { x: 0.5, y: 0.5 },
    createKeyframe: (v: unknown): Kf => {
      if (!(v instanceof FakePointF)) throw new Error("Illegal Parameter type");
      return { value: { value: v }, position: { seconds: 0 } };
    },
  });
  const { ctx } = keyframeRig(strict);
  const r = await runProbe(probe("keyframes_motion_opacity_crop"), ctx);
  const forms = stepNamed(r, "position: createKeyframe with each value form");
  assert.equal(forms.ok, true);
  const res = (forms.info as { results: Array<{ form: string; ok: boolean; error?: string }>; accepted_forms: string[] }).results;
  assert.ok(res.find((x) => x.form === "plain {x, y}" && x.ok === false)?.error?.includes("Illegal Parameter type"));
  assert.ok(res.find((x) => x.form === "new PointF(x, y)")?.ok);
  assert.equal(stepNamed(r, "position: createSetTimeVaryingAction").ok, true);
  const add = stepNamed(r, "position: addKeyframe x2");
  assert.equal(add.ok, true);
  assert.deepEqual((add.info as { read_back_times_s: number[] }).read_back_times_s, [0, 1]);
  const inspect = stepNamed(r, "position: inspect start value");
  assert.equal((inspect.info as { units: string }).units, "normalised 0-1");
  assert.equal(((inspect.info as { start_value_inner: { x: number } }).start_value_inner).x, 0.5);
});

test("Position: when every value form is rejected the step fails and keeps each error (the failing call is isolated)", async () => {
  const none = fakeParam("Position", {
    start: { x: 640, y: 960 },
    createKeyframe: () => {
      throw new Error("Illegal Parameter type");
    },
  });
  const { ctx } = keyframeRig(none);
  const r = await runProbe(probe("keyframes_motion_opacity_crop"), ctx);
  const forms = stepNamed(r, "position: createKeyframe with each value form");
  assert.equal(forms.ok, false);
  assert.equal((forms.info as { results: unknown[] }).results.length, 7);
  assert.equal((stepNamed(r, "position: inspect start value").info as { units: string }).units, "pixels");
  assert.ok(!stepsOf(r).some((s) => s.step.startsWith("position: addKeyframe")), "nothing is added when no keyframe could be created");
});

test("Crop: Motion's built-in Crop Left/Right are keyed by name and the effect AE.ADBE AECrop is created", async () => {
  const { ctx, chain } = keyframeRig(fakeParam("Position", { start: { x: 0.5, y: 0.5 } }));
  const r = await runProbe(probe("keyframes_motion_opacity_crop"), ctx);
  assert.equal(stepNamed(r, "crop: Motion built-in Crop params").ok, true);
  const left = stepNamed(r, "crop: Motion Crop Left 0->100");
  assert.equal(left.ok, true);
  assert.deepEqual((left.info as { set: unknown[] }).set, [
    { t: 0, v: 0 },
    { t: 1, v: 100 },
  ]);
  assert.equal(stepNamed(r, "crop: Motion Crop Right 0->10").ok, true);
  const eff = stepNamed(r, "crop effect AE.ADBE AECrop");
  assert.equal(eff.ok, true, JSON.stringify(eff));
  assert.equal((eff.info as { used: string }).used, "AE.ADBE AECrop");
  assert.equal(chain.comps.length, 3);
});

// ---- time basis ------------------------------------------------------------------------------------------------

test("windowsDisjoint / classifyTimes", () => {
  assert.equal(windowsDisjoint({ start_s: 0.1667, in_s: 23.83, end_s: 3.9167, duration_s: 3.75 }), false);
  assert.equal(windowsDisjoint({ start_s: 36.1, in_s: 23.83, end_s: 39.85, duration_s: 3.75 }), true);
  assert.deepEqual(classifyTimes([0, 24, 37], { start_s: 36.1, in_s: 23.83, end_s: 39.85, duration_s: 3.75 }).inside_media_window, [false, true, false]);
});

function basisRig() {
  const xmlChain = fakeChain([fakeComp("AE.ADBE Opacity", [fakeParam("Opacity")])]);
  const stillChain = fakeChain([fakeComp("AE.ADBE Opacity", [fakeParam("Opacity")])]);
  const xml = fakeClip({ start: 0.1667, inP: 23.8333, end: 3.9167 }, xmlChain);
  const still = fakeClip({ start: 30.0833, inP: 3599.9583, end: 35.0833 }, stillChain);
  const { project } = fakeProject();
  const ppro = { TickTime: T, Constants: { TrackItemType: { CLIP: 1 } } };
  const ctx = baseCtx(ppro, { project: project as never });
  ctx.sequence = {
    getVideoTrackCount: async () => 1,
    getVideoTrack: async () => ({ getTrackItems: () => [xml] }),
    getEndTime: async () => ({ seconds: 35.0833 }),
  } as never;
  ctx.target = { clip: still as never, trackIndex: 8, source: "placed still" } satisfies TargetClip;
  const exported: Array<{ t: number; base: string }> = [];
  ctx.exportFrameTo = async (t, base) => {
    exported.push({ t, base });
    return { path: `${WORK}/frames/${base}.png`, found: true, bytes: 100, returned: true };
  };
  return { ctx, xml, still, exported };
}

test("time basis: the XML clip is moved so clip-local, media and sequence windows are disjoint; each basis is keyed alone and frames are exported", async () => {
  const { ctx, xml, exported } = basisRig();
  const r = await runProbe(probe("keyframe_time_basis"), ctx);
  assert.equal(r.ok, true, JSON.stringify(stepsOf(r).filter((s) => !s.ok)));
  const pick = stepNamed(r, "xml clip: pick one");
  const pi = pick.info as { before: { start_s: number }; after: { start_s: number; end_s: number; in_s: number }; disjoint_windows: boolean };
  assert.ok(pi.before.start_s < 1);
  assert.ok(pi.after.start_s >= 36, `moved beyond the sequence end, start ${pi.after.start_s}`);
  assert.equal(pi.disjoint_windows, true);
  assert.ok(xml.st.start > 36);
  for (const label of ["xml_clip", "placed_still"]) {
    const bases = stepsOf(r).filter((s) => s.step.startsWith(`${label}: basis`));
    assert.equal(bases.length, 3, label);
    assert.ok(bases.every((s) => s.ok));
    const [a, b, c] = bases.map((s) => s.info as { requested_times_s: number[]; read_back_times_s: number[]; inside_local_window: boolean[]; inside_media_window: boolean[]; inside_sequence_window: boolean[]; keys_left_after_clear: number; frames: unknown[]; disjoint_windows: boolean });
    assert.equal(a?.disjoint_windows, true);
    assert.deepEqual(a?.inside_local_window, [true, true]);
    assert.deepEqual(a?.inside_local_window.concat(a?.inside_media_window ?? []).slice(2), [false, false]);
    assert.deepEqual(b?.inside_media_window, [true, true]);
    assert.deepEqual(c?.inside_sequence_window, [true, true]);
    for (const x of [a, b, c]) {
      assert.equal(x?.keys_left_after_clear, 0, "keys are removed between bases");
      assert.equal(x?.frames.length, 3);
    }
  }
  // baseline + A + B + C, 3 frames each, for both clips; frames at known sequence times (start + 0.25/0.5/0.75)
  assert.equal(exported.length, 24);
  assert.ok(exported.every((e) => /^tb_(xml_clip|placed_still)_(baseline|A|B|C)_0\.(25|5|75)$/.test(e.base)));
  assert.ok(Math.abs((exported[0]?.t ?? 0) - (xml.st.start + 0.25)) < 1e-9);
});

test("time basis: without a working export form the read-back still runs and says frames are unavailable; no suitable clip fails clearly", async () => {
  const { ctx } = basisRig();
  ctx.exportFrameTo = undefined;
  const r = await runProbe(probe("keyframe_time_basis"), ctx);
  const a = stepNamed(r, "xml_clip: basis A");
  assert.match(String((a.info as { frames: unknown }).frames), /export unavailable/);
  const { ctx: ctx2 } = basisRig();
  ctx2.sequence = { getVideoTrackCount: async () => 1, getVideoTrack: async () => ({ getTrackItems: () => [] }), getEndTime: async () => ({ seconds: 10 }) } as never;
  const r2 = await runProbe(probe("keyframe_time_basis"), ctx2);
  const pick = stepNamed(r2, "xml clip: pick one");
  assert.equal(pick.ok, false);
  assert.match(pick.error ?? "", /no clip with in-point/);
});

// ---- effects ---------------------------------------------------------------------------------------------------

test("effects: exact match names (Gaussian Blur 2, Sharpen, Noise, Lumetri), static values read back, Impact_Blur params recorded apart", async () => {
  const chain = fakeChain([fakeComp("AE.ADBE Opacity", [fakeParam("Opacity")]), fakeComp("AE.ADBE Motion", [fakeParam("Scale")])]);
  const clip = fakeClip({ start: 30, inP: 0, end: 35 }, chain);
  const specs: Record<string, string[]> = {
    "AE.ADBE Gaussian Blur 2": ["Blurriness", "Blur Dimensions", "Repeat Edge Pixels"],
    "AE.ADBE Sharpen": ["Sharpen Amount"],
    "AE.ADBE_Noise_FX": ["Seed", "Intensity"],
    "AE.ADBE Lumetri": ["Basic"],
    "AE.Impact_Blur_FX": ["Angle", "Amount", "Thickness"],
  };
  const created: string[] = [];
  const { project } = fakeProject();
  const ppro = {
    TickTime: T,
    VideoFilterFactory: {
      getMatchNames: async () => Object.keys(specs),
      getDisplayNames: async () => ["Gaussian Blur (Legacy)", "Sharpen", "Noise", "Lumetri Color", "Gaussian Blur"],
      createComponent: async (m: string) => {
        created.push(m);
        return fakeComp(m, (specs[m] ?? []).map((n) => fakeParam(n)));
      },
    },
  };
  const ctx = baseCtx(ppro, { project: project as never });
  ctx.sequence = {} as never;
  ctx.target = { clip: clip as never, trackIndex: 0, source: "placed still" };
  const r = await runProbe(probe("effects_by_match_name"), ctx);
  assert.deepEqual(created, ["AE.ADBE Gaussian Blur 2", "AE.ADBE Sharpen", "AE.ADBE_Noise_FX", "AE.ADBE Lumetri", "AE.Impact_Blur_FX"]);
  const blur = stepNamed(r, "gaussian_blur_legacy");
  assert.equal(blur.ok, true, JSON.stringify(blur));
  const set = (blur.info as { set: Array<{ param_name: string; matches: boolean }> }).set;
  assert.deepEqual(set.map((s) => [s.param_name, s.matches]), [["Blurriness", true], ["Repeat Edge Pixels", true]]);
  assert.equal(stepNamed(r, "sharpen").ok, true);
  assert.equal(stepNamed(r, "noise").ok, true);
  assert.equal(stepNamed(r, "lumetri").ok, true);
  const impact = stepNamed(r, "AE.Impact_Blur_FX");
  assert.deepEqual((impact.info as { params: Array<{ name: string }> }).params.map((p) => p.name), ["Angle", "Amount", "Thickness"]);
});

test("effects: a missing parameter fails that effect only and keeps what was measured", async () => {
  const chain = fakeChain([]);
  const clip = fakeClip({ start: 0, inP: 0, end: 1 }, chain);
  const { project } = fakeProject();
  const ppro = {
    TickTime: T,
    VideoFilterFactory: {
      getMatchNames: async () => ["AE.ADBE Gaussian Blur 2", "AE.ADBE Sharpen"],
      getDisplayNames: async () => ["a", "b"],
      createComponent: async (m: string) => fakeComp(m, m.includes("Sharpen") ? [fakeParam("Sharpen Amount")] : [fakeParam("Angle")]),
    },
  };
  const ctx = baseCtx(ppro, { project: project as never });
  ctx.sequence = {} as never;
  ctx.target = { clip: clip as never, trackIndex: 0, source: "placed still" };
  const r = await runProbe(probe("effects_by_match_name"), ctx);
  const blur = stepNamed(r, "gaussian_blur_legacy");
  assert.equal(blur.ok, false);
  assert.match(JSON.stringify(blur.info), /no param matching/);
  assert.equal(stepNamed(r, "sharpen").ok, true);
});

// ---- scratch disks -----------------------------------------------------------------------------------------------

test("scratch_disk: reads the project's scratch settings, sets every folder type to same-as-project in a labelled transaction and reads back", async () => {
  const paths: Record<number, string> = { 0: "C:/Users/LOQ/Documents/Adobe", 1: "C:/x", 2: "C:/x", 3: "C:/x", 4: "C:/x", 5: "C:/x" };
  const makeSettings = () => ({
    pending: { ...paths },
    getScratchDiskPath: (t: number) => paths[t] ?? "",
    setScratchDiskPath(t: number, v: number) {
      this.pending[t] = v === 0 ? "Same as project" : "other";
      return true;
    },
  });
  const { project, labels } = fakeProject();
  const ppro = {
    Constants: { ScratchDiskFolderType: { CAPTURE: 0, AUDIO_PREVIEW: 1, VIDEO_PREVIEW: 2, AUTO_SAVE: 3, CCL_LIBRARIES: 4, CAPSULE_MEDIA: 5 }, ScratchDiskFolder: { SAME_AS_PROJECT: 0, MY_DOCUMENTS: 1 } },
    ScratchDiskSettings: { FOLDER_SAME_AS_PROJECT: "same" },
    ProjectSettings: {
      getScratchDiskSettings: async () => makeSettings(),
      createSetScratchDiskSettingsAction: (_p: unknown, s: { pending: Record<number, string> }): Act => ({ apply: () => Object.assign(paths, s.pending) }),
    },
  };
  const r = await runProbe(probe("scratch_disk"), baseCtx(ppro, { project: project as never }));
  assert.equal(r.ok, true, JSON.stringify(r).slice(0, 500));
  const set = stepNamed(r, "set every type");
  assert.equal(((set.info as { paths_after: Record<string, string> }).paths_after).CAPTURE, "Same as project");
  assert.deepEqual(labels, ["WhyNot Cut build"]);
  assert.ok(stepsOf(r).every((s) => typeof s.at === "string" && typeof s.ms === "number"));
});

// ---- save / close / open attribution ---------------------------------------------------------------------------

function saveRig(openFails: (variant: number, path: string, hasOptions: boolean) => boolean) {
  const vfs = fakeFs();
  const rawPath = `\\\\?\\${WORK}/spike-1.prproj`;
  vfs.write(`${WORK}/spike-1.prproj`, 31106);
  const opens: Array<{ path: string; hasOptions: boolean }> = [];
  const reopened = {
    path: rawPath,
    getSequences: async () => [{ name: "SEQ", getVideoTrack: async () => ({ name: "V1" }) }],
  };
  const { project } = fakeProject({ save: async () => true, close: async () => true });
  const chainable = () => {
    const o: Record<string, unknown> = {};
    for (const k of ["setPromptIfDirty", "setSaveWorkspace", "setShowCancelButton", "setShowConvertProjectDialog", "setShowLocateFileDialog", "setShowWarningDialog", "setAddToMRUList"]) o[k] = () => o;
    return o;
  };
  const ppro = {
    CloseProjectOptions: function () {
      return chainable();
    },
    OpenProjectOptions: function () {
      return chainable();
    },
    Project: {
      isProject: () => true,
      open: async (path: string, options?: unknown) => {
        opens.push({ path, hasOptions: options !== undefined });
        if (openFails(opens.length, path, options !== undefined)) throw new Error("Failed to open the project");
        return reopened;
      },
    },
    Markers: { getMarkers: async () => ({ getMarkers: () => [] }) },
  };
  project.path = rawPath;
  const ctx = baseCtx(ppro, { fs: vfs.fs, project: project as never });
  ctx.expect = { sequenceName: "SEQ", videoTrackName: "V1", markerCount: 0 };
  return { ctx, opens };
}

test("save_close_open: every sub-step is timestamped and Project.open variants are tried until one works; the failures keep their detail", async () => {
  const { ctx, opens } = saveRig((n) => n < 4);
  const r = await runProbe(probe("save_close_open"), ctx);
  assert.equal(opens.length, 4);
  assert.deepEqual(opens.map((o) => o.hasOptions), [false, false, true, false]);
  assert.match(opens[1]?.path ?? "", /^\\\\\?\\/, "attempt 2 uses the raw \\\\?\\ path");
  assert.ok(opens[3]?.path.includes("\\"), "attempt 4 uses backslashes");
  const names = stepsOf(r).map((s) => s.step);
  assert.deepEqual(names.slice(0, 3), ["save (explicit)", "Project.isProject(path) before closing", "close (setPromptIfDirty(false) after the explicit save)"]);
  const failed = stepsOf(r).filter((s) => s.step.startsWith("open attempt") && !s.ok);
  assert.equal(failed.length, 3);
  for (const f of failed) {
    assert.match(f.error ?? "", /Failed to open the project/);
    const info = f.info as { error: { message: string; stack?: string }; note: string; path_used_json: string };
    assert.equal(info.error.message, "Failed to open the project");
    assert.match(info.note, /Scratch Disk Error/);
    assert.ok(info.path_used_json.startsWith('"'));
  }
  assert.equal(stepsOf(r).find((s) => s.step.startsWith("open attempt 4"))?.ok, true);
  assert.equal(stepNamed(r, "verify persisted").ok, true);
  for (const s of stepsOf(r)) assert.match(s.at, /^\d{4}-/);
  assert.equal(r.ok, false, "three failed attempts still make the probe red so the dialogs are not missed");
});

test("save_close_open: when no open variant works the probe is red and nothing is verified", async () => {
  const { ctx, opens } = saveRig(() => true);
  const r = await runProbe(probe("save_close_open"), ctx);
  assert.equal(opens.length, 4);
  assert.equal(r.ok, false);
  assert.ok(!stepsOf(r).some((s) => s.step.startsWith("verify")));
});

test("save_as: n/a without an open scratch project, and refuses when the copy would leave work_dir", async () => {
  const r0 = await runProbe(probe("save_as"), baseCtx({}));
  assert.equal(r0.ok, null);
  const vfs = fakeFs();
  const { project } = fakeProject({
    saveAs: async function (this: { path: string }, p: string) {
      this.path = p;
      vfs.write(p);
      return true;
    },
  });
  const r1 = await runProbe(probe("save_as"), baseCtx({}, { fs: vfs.fs, project: project as never }));
  assert.equal(r1.ok, true, JSON.stringify(r1));
  const r2 = await runProbe(
    probe("save_as"),
    baseCtx({}, {
      fs: vfs.fs,
      project: fakeProject({
        saveAs: async function (this: { path: string }) {
          this.path = "C:/Users/yunus/Documents/elsewhere.prproj";
          return true;
        },
      }).project as never,
    }),
  );
  assert.equal(r2.ok, false);
  assert.match(r2.error ?? JSON.stringify(r2.detail), /refusing to touch a project outside work_dir/);
});

// ---- undo, clip edits, project views, encoder ------------------------------------------------------------------

test("undo_transaction: History-panel instructions, before/after state, history API discovery; it runs right after the import", async () => {
  const names = { v: "Video 1", a: "Audio 1" };
  const marks: string[] = ["GFX_001"];
  const { project, labels } = fakeProject();
  const sequence = {
    getVideoTrack: async () => ({ get name() { return names.v; }, createSetNameAction: (n: string): Act => ({ apply: () => void (names.v = n) }) }),
    getAudioTrack: async () => ({ get name() { return names.a; }, createSetNameAction: (n: string): Act => ({ apply: () => void (names.a = n) }) }),
  };
  const ppro = {
    TickTime: T,
    Marker: { MARKER_TYPE_COMMENT: "Comment" },
    Markers: {
      getMarkers: async () => ({
        createAddMarkerAction: (n: string): Act => ({ apply: () => void marks.push(n) }),
        getMarkers: () => marks.map((n) => ({ getName: () => n })),
      }),
    },
  };
  const r = await runProbe(probe("undo_transaction"), baseCtx(ppro, { project: project as never, sequence: sequence as never }));
  assert.equal(r.ok, true, JSON.stringify(r));
  assert.deepEqual(labels, ["WhyNot Cut build"]);
  const disc = stepNamed(r, "history API discovery");
  assert.equal((disc.info as { history_step_count: string }).history_step_count, "not exposed by the API");
  const t = stepNamed(r, "one_transaction_three_actions");
  const info = t.info as { manual_check: string; state_before: { v1: string; markers: string[] }; state_after: { v1: string; a1: string; markers: string[] } };
  assert.match(info.manual_check, /Window > History/);
  assert.doesNotMatch(info.manual_check, /Edit menu must/);
  assert.match(info.manual_check, /ALL THREE/);
  assert.equal(info.state_before.v1, "Video 1");
  assert.deepEqual([info.state_after.v1, info.state_after.a1], ["WNC Undo Test", "WNC Undo Test A1"]);
  const order = buildProbes().map((p) => p.op);
  assert.equal(order.indexOf("undo_transaction"), order.indexOf("import_fcp7_xml") + 1);
  assert.equal(order.indexOf("scratch_disk"), order.indexOf("create_project") + 1);
});

test("clip_edits: refuses to edit anything but the placed still, and edits/transitions/new track/remove run on the still", async () => {
  const chain = fakeChain([]);
  const xmlClip = fakeClip({ start: 0, inP: 5, end: 4 }, chain);
  const calls: string[] = [];
  (xmlClip as unknown as Record<string, unknown>).createSetEndAction = () => (calls.push("setEnd"), { apply: () => {} });
  const { project } = fakeProject();
  const ctx = baseCtx({ TickTime: T }, { project: project as never });
  ctx.sequence = {} as never;
  ctx.target = { clip: xmlClip as never, trackIndex: 0, source: "existing clip" };
  const r = await runProbe(probe("clip_edits_transitions_tracks"), ctx);
  assert.equal(r.ok, false);
  assert.match(stepNamed(r, "target").error ?? "", /never an XML clip/);
  assert.deepEqual(calls, []);

  // placed still: full path
  const st = { start: 30, inP: 3599.96, end: 35, out: 3604.96, name: "still", disabled: false };
  const still = {
    getStartTime: async () => ({ seconds: st.start }),
    getEndTime: async () => ({ seconds: st.end }),
    getInPoint: async () => ({ seconds: st.inP }),
    getOutPoint: async () => ({ seconds: st.out }),
    getName: async () => st.name,
    isDisabled: async () => st.disabled,
    getProjectItem: async () => ({}),
    createSetEndAction: (t: { seconds: number }): Act => ({ apply: () => void (st.end = t.seconds) }),
    createSetStartAction: (t: { seconds: number }): Act => ({ apply: () => void (st.start = t.seconds) }),
    createMoveAction: (t: { seconds: number }): Act => ({ apply: () => void ((st.start += t.seconds), (st.end += t.seconds)) }),
    createSetInPointAction: (t: { seconds: number }): Act => ({ apply: () => void (st.inP = t.seconds) }),
    createSetOutPointAction: (t: { seconds: number }): Act => ({ apply: () => void (st.out = t.seconds) }),
    createSetNameAction: (n: string): Act => ({ apply: () => void (st.name = n) }),
    createSetDisabledAction: (d: boolean): Act => ({ apply: () => void (st.disabled = d) }),
    createAddVideoTransitionAction: (): Act => ({ apply: () => void transitions.push(1) }),
  };
  const transitions: number[] = [];
  const tracks: unknown[][] = [[still]];
  const ppro = {
    TickTime: T,
    Constants: { TrackItemType: { CLIP: 1, TRANSITION: 2 }, MediaType: { VIDEO: 2 } },
    AddTransitionOptions: function () {
      const o: Record<string, unknown> = {};
      o.setDuration = () => o;
      o.setApplyToStart = () => o;
      return o;
    },
    TransitionFactory: { getVideoTransitionMatchNames: async () => ["PR.ADBE Cross Dissolve", "PR.ADBE Dip"], createVideoTransition: (n: string) => ({ n }) },
    SequenceEditor: {
      getEditor: () => ({
        createOverwriteItemAction: (_i: unknown, _t: unknown, v: number): Act => ({ apply: () => void (tracks[v] = [{}]) }),
        createRemoveItemsAction: (sel: { items: unknown[] }): Act => ({ apply: () => void (tracks[tracks.length - 1] = tracks[tracks.length - 1]?.filter((x) => !sel.items.includes(x)) ?? []) }),
      }),
    },
    TrackItemSelection: { createEmptySelection: (cb: (s: { items: unknown[]; addItem: (x: unknown) => boolean }) => void) => cb({ items: [], addItem(this: { items: unknown[] }, x: unknown) { this.items.push(x); return true; } } as never) },
  };
  const { project: project2 } = fakeProject();
  const ctx2 = baseCtx(ppro, { project: project2 as never });
  ctx2.sequence = {
    getVideoTrack: async (i: number) => ({ getTrackItems: (type: number) => (type === 2 ? transitions : tracks[i] ?? []) }),
    getVideoTrackCount: async () => tracks.length,
    getEndTime: async () => ({ seconds: st.end }),
  } as never;
  ctx2.target = { clip: still as never, trackIndex: 0, source: "placed still" };
  const r2 = await runProbe(probe("clip_edits_transitions_tracks"), ctx2);
  const bad = stepsOf(r2).filter((s) => !s.ok);
  assert.deepEqual(bad.map((s) => s.error), [], "all clip-edit steps ok");
  assert.equal(st.name, "WNC placed still");
  const track = stepNamed(r2, "add a video track");
  assert.equal((track.info as { track_added: boolean }).track_added, true);
  const tr = stepNamed(r2, "video transition");
  assert.equal((tr.info as { used: string }).used, "PR.ADBE Cross Dissolve");
  assert.equal((tr.info as { transition_items_after: number }).transition_items_after, 1);
});

test("project_views lists views read-only; encoder_export is off unless config asks for it", async () => {
  const ppro = {
    ProjectUtils: {
      getProjectViewIds: async () => [{ toString: () => "guid-1" }],
      getProjectFromViewId: async () => ({ name: "spike.prproj", path: `\\\\?\\${WORK}/spike.prproj` }),
    },
  };
  const r = await runProbe(probe("project_views"), baseCtx(ppro));
  assert.equal(r.ok, true);
  assert.equal(((stepsOf(r)[0]?.info as { projects: Array<{ name: string }> }).projects[0])?.name, "spike.prproj");
  const e = await runProbe(probe("encoder_export"), baseCtx({}));
  assert.equal(e.ok, null);
  assert.match(String(e.detail), /encoder_export/);
});
