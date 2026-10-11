// Safety + time-basis tests for the spike probes, against hand-made fakes of Premiere.
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildProbes, type Ctx, type SpikeConfig } from "../spike/src/probes.ts";
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

/** probes before / around the project: create_project itself, and the read-only or opt-in ones */
const LEAD = new Set(["host_info", "ws_loopback", "create_project"]);
const NOT_MUTATING = new Set(["project_views", "save_as", "encoder_export"]);

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
  for (const o of ops.filter((x) => !LEAD.has(x.op) && !NOT_MUTATING.has(x.op))) {
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
  for (const o of ops.filter((x) => !LEAD.has(x.op) && !NOT_MUTATING.has(x.op))) assert.equal(o.ok, false, `${o.op} -> ${o.ok}`);
  assert.deepEqual(calls, []);
});

test("a project outside work_dir is refused by every mutating probe even if it is somehow in ctx.project", async () => {
  const calls: string[] = [];
  const ctx = baseCtx({});
  ctx.project = userProject(calls) as unknown as Ctx["project"];
  for (const op of ["scratch_disk", "sequence_settings", "keyframes_motion_opacity_crop", "keyframe_time_basis", "effects_by_match_name", "clip_edits_transitions_tracks", "track_rename", "markers", "undo_transaction", "save_close_open", "save_as", "export_frame"]) {
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
