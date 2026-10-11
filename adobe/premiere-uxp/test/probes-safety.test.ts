// Safety + time-basis tests for the spike probes, against hand-made fakes of Premiere.
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildProbes, type Ctx, type SpikeConfig, type TargetClip } from "../spike/src/probes.ts";
import { runAll, runProbe } from "../spike/src/runner.ts";

const WT = "D:/0 Work/0 Pegasus IMC Agency/00 TWN/0 TWN AI/Editing Plugin/whynot-test";
const GOOD_CONFIG: SpikeConfig = { xml_path: `${WT}/PODCAST-TEST/x.xml`, work_dir: `${WT}/_uxp-spike`, still_png: `${WT}/PODCAST-TEST/s.png` };

function baseCtx(ppro: unknown, config: SpikeConfig | null = GOOD_CONFIG, fs: Ctx["fs"] = {}): Ctx {
  return {
    ppro: ppro as Ctx["ppro"],
    fs,
    uxp: {},
    os: undefined,
    home: "C:/Users/test",
    homeVia: "os.homedir",
    stamp: "20260101-000000",
    config,
    configError: config ? null : "test: no config",
    expect: {},
    notes: [],
  };
}

function probe(op: string) {
  const p = buildProbes().find((d) => d.op === op);
  assert.ok(p, `no probe ${op}`);
  return p;
}

/** A stand-in for the editor's open project: any method call on it is recorded in `calls`. */
function userProject(calls: string[]) {
  const base: Record<string, unknown> = { name: "Client Reel", path: "C:/Users/yunus/Documents/Client Reel.prproj" };
  return new Proxy(base, {
    get: (t, k) => {
      if (typeof k === "symbol" || k === "then" || k === "toJSON") return undefined;
      if (k in t) return t[k];
      return (...args: unknown[]) => {
        calls.push(`${String(k)}(${args.length})`);
        return Promise.resolve(undefined);
      };
    },
  });
}

const okFs = { lstat: async () => ({ size: 1, isDirectory: () => true }), mkdir: async () => {} };

test("no config: nothing is called on the user's open project (no actions, save or close)", async () => {
  const calls: string[] = [];
  const user = userProject(calls);
  const ppro = { Project: { getActiveProject: async () => user, createProject: async () => assert.fail("createProject must not run") } };
  const ops = await runAll(buildProbes(), baseCtx(ppro, null));
  assert.deepEqual(calls, []);
  assert.ok(ops.slice(2).every((o) => o.ok === null));
});

test("create_project fails: every later probe fails without touching the user's open project", async () => {
  const calls: string[] = [];
  const user = userProject(calls);
  const ppro = {
    Project: {
      getActiveProject: async () => user,
      createProject: async () => {
        throw new Error("disk full");
      },
      open: async () => assert.fail("Project.open must not run"),
    },
  };
  const ops = await runAll(buildProbes(), baseCtx(ppro, GOOD_CONFIG, okFs));
  assert.equal(ops.find((o) => o.op === "create_project")?.ok, false);
  for (const o of ops.slice(3)) {
    assert.equal(o.ok, false, `${o.op} should fail, got ${o.ok}`);
    assert.match(o.error ?? "", /no scratch project|refusing/);
  }
  assert.deepEqual(calls, []);
});

test("createProject that lands outside work_dir is refused and never used", async () => {
  const calls: string[] = [];
  const user = userProject(calls);
  const ppro = { Project: { getActiveProject: async () => user, createProject: async () => user } };
  const ops = await runAll(buildProbes(), baseCtx(ppro, GOOD_CONFIG, okFs));
  const create = ops.find((o) => o.op === "create_project");
  assert.equal(create?.ok, false);
  assert.match(create?.error ?? "", /refusing to touch a project outside work_dir/);
  for (const o of ops.slice(3)) assert.equal(o.ok, false, `${o.op} -> ${o.ok}`);
  assert.deepEqual(calls, []);
});

test("a project outside work_dir is refused by every mutating probe even if it is somehow in ctx.project", async () => {
  const calls: string[] = [];
  const ctx = baseCtx({});
  ctx.project = userProject(calls) as unknown as Ctx["project"];
  for (const op of ["sequence_settings", "keyframes_motion_opacity_crop", "effects_by_match_name", "track_rename", "markers", "undo_transaction", "save_close_open", "export_frame"]) {
    const r = await runProbe(probe(op), ctx);
    assert.equal(r.ok, false, op);
    assert.match(r.error ?? "", /refusing to touch a project outside work_dir/, op);
  }
  assert.deepEqual(calls, []);
});

test("a scratch project without a sequence from import_fcp7_xml: later probes fail and never ask for the active sequence", async () => {
  const calls: string[] = [];
  const project = {
    path: `${GOOD_CONFIG.work_dir}/spike-1.prproj`,
    lockedAccess: () => calls.push("lockedAccess"),
    getActiveSequence: async () => void calls.push("getActiveSequence"),
  };
  const ctx = baseCtx({});
  ctx.project = project as unknown as Ctx["project"];
  for (const op of ["track_rename", "markers", "undo_transaction", "sequence_settings", "export_frame"]) {
    const r = await runProbe(probe(op), ctx);
    assert.equal(r.ok, false, op);
    assert.match(r.error ?? "", /no scratch sequence/);
  }
  assert.deepEqual(calls, []);
});

test("import_fcp7_xml refuses an xml_path outside whynot-test even if ctx.config was built by hand", async () => {
  const ctx = baseCtx({}, { ...GOOD_CONFIG, xml_path: "D:/WhyNot Clients/Dr X/a.xml" });
  ctx.project = { path: `${GOOD_CONFIG.work_dir}/spike-1.prproj`, getSequences: async () => assert.fail("must not list sequences") } as unknown as Ctx["project"];
  const r = await runProbe(probe("import_fcp7_xml"), ctx);
  assert.equal(r.ok, false);
  assert.match(r.error ?? "", /xml_path rejected/);
});

// ---- keyframe time basis ---------------------------------------------------------------------------------------

interface FakeAction {
  apply: () => void;
}

test("keyframes: time basis is keyed three ways on a clip with non-zero in-point and start, and classified", async () => {
  type Kf = { position: { seconds: number }; value: number };
  const fakeParam = (name: string) => {
    const kfs: Kf[] = [];
    return {
      displayName: name,
      areKeyframesSupported: async () => true,
      isTimeVarying: () => kfs.length > 0,
      createSetTimeVaryingAction: (): FakeAction => ({ apply: () => {} }),
      createKeyframe: (value: number): Kf => ({ value, position: { seconds: 0 } }),
      createAddKeyframeAction: (k: Kf): FakeAction => ({ apply: () => void kfs.push(k) }),
      getKeyframeListAsTickTimes: () => kfs.map((k) => k.position),
      getValueAtTime: async (t: { seconds: number }) => kfs.find((k) => k.position.seconds === t.seconds)?.value ?? null,
    };
  };
  const comp = (match: string, names: string[]) => {
    const params = names.map(fakeParam);
    return { getMatchName: async () => match, getDisplayName: async () => match, getParamCount: () => params.length, getParam: (i: number) => params[i] };
  };
  const comps = [comp("AE.ADBE Motion", ["Scale", "Rotation"]), comp("AE.ADBE Opacity", ["Opacity"])];
  const chain = { getComponentCount: () => comps.length, getComponentAtIndex: (i: number) => comps[i], createAppendComponentAction: (): FakeAction => ({ apply: () => {} }) };
  const clip = {
    getStartTime: async () => ({ seconds: 30 }),
    getInPoint: async () => ({ seconds: 20 }),
    getEndTime: async () => ({ seconds: 33 }),
    getComponentChain: async () => chain,
  };
  // the placed still is a different clip with its own (untouched) chain, as in a real run
  const stillComps = [comp("AE.ADBE Motion", ["Scale"])];
  const stillChain = { getComponentCount: () => 1, getComponentAtIndex: (i: number) => stillComps[i], createAppendComponentAction: (): FakeAction => ({ apply: () => {} }) };
  const placedStill = { ...clip, getStartTime: async () => ({ seconds: 40 }), getInPoint: async () => ({ seconds: 0 }), getEndTime: async () => ({ seconds: 45 }), getComponentChain: async () => stillChain };
  const project = {
    path: `${GOOD_CONFIG.work_dir}/spike-1.prproj`,
    lockedAccess: (cb: () => void) => cb(),
    executeTransaction: (cb: (ca: { addAction: (a: FakeAction) => boolean }) => void) => {
      cb({ addAction: (a) => (a.apply(), true) });
      return true;
    },
  };
  const ppro = {
    TickTime: { createWithSeconds: (seconds: number) => ({ seconds }) },
    Constants: { TrackItemType: { CLIP: 1 } },
    VideoFilterFactory: { getMatchNames: async () => [] },
    PointF: function () {},
    Keyframe: { INTERPOLATION_MODE_BEZIER: 2 },
  };
  const ctx = baseCtx(ppro);
  ctx.project = project as unknown as Ctx["project"];
  ctx.sequence = {
    name: "SEQ",
    getVideoTrackCount: async () => 1,
    getVideoTrack: async () => ({ getTrackItems: () => [clip] }),
  } as unknown as Ctx["sequence"];
  ctx.target = { clip: placedStill as unknown as TargetClip["clip"], trackIndex: 0, source: "placed still" };
  const r = await runProbe(probe("keyframes_motion_opacity_crop"), ctx);
  const steps = (r.detail as { steps: Array<{ step: string; ok: boolean; info?: Record<string, unknown>; error?: string }> }).steps;
  const basis = steps.filter((s) => s.step.startsWith("time_basis "));
  assert.equal(basis.length, 3, JSON.stringify(steps.map((s) => [s.step, s.ok, s.error])));
  assert.ok(basis.every((s) => s.ok), JSON.stringify(basis));
  type Info = { read_back_times_s: number[]; inside_local_window: boolean[]; inside_media_window: boolean[]; inside_sequence_window: boolean[]; clip: unknown };
  const [a, b, c] = basis.map((s) => s.info as Info);
  assert.deepEqual(a?.read_back_times_s, [0, 1]);
  assert.deepEqual(a?.inside_local_window, [true, true]);
  assert.deepEqual(a?.inside_media_window, [false, false]);
  assert.deepEqual(b?.read_back_times_s, [20, 21]);
  assert.deepEqual(b?.inside_media_window, [true, true]);
  assert.deepEqual(b?.inside_local_window, [false, false]);
  assert.deepEqual(c?.read_back_times_s, [30, 31]);
  assert.deepEqual(c?.inside_sequence_window, [true, true]);
  assert.deepEqual(a?.clip, { start_s: 30, in_s: 20, end_s: 33, duration_s: 3 });
});

test("keyframes: with no suitable clip the basis step fails clearly instead of keying the wrong clip", async () => {
  const still = { getStartTime: async () => ({ seconds: 40 }), getInPoint: async () => ({ seconds: 0 }), getEndTime: async () => ({ seconds: 45 }) };
  const ctx = baseCtx({ Constants: { TrackItemType: { CLIP: 1 } } });
  ctx.project = { path: `${GOOD_CONFIG.work_dir}/spike-1.prproj` } as unknown as Ctx["project"];
  ctx.sequence = { getVideoTrackCount: async () => 1, getVideoTrack: async () => ({ getTrackItems: () => [still] }) } as unknown as Ctx["sequence"];
  const r = await runProbe(probe("keyframes_motion_opacity_crop"), ctx);
  const steps = (r.detail as { steps: Array<{ step: string; ok: boolean; error?: string }> }).steps;
  const find = steps.find((s) => s.step.startsWith("time_basis: find clip"));
  assert.equal(find?.ok, false);
  assert.match(find?.error ?? "", /no clip with in-point/);
});
