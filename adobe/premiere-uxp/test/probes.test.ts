import { test } from "node:test";
import assert from "node:assert/strict";
import { buildProbes, UNDO_LABEL, skipSaveCloseOpen, type Ctx } from "../spike/src/probes.ts";
import { runAll, runProbe } from "../spike/src/runner.ts";

function baseCtx(ppro: unknown): Ctx {
  return {
    ppro: ppro as Ctx["ppro"],
    fs: {},
    uxp: {},
    os: undefined,
    home: "C:/Users/test",
    homeVia: "os.homedir",
    stamp: "20260101-000000",
    config: null,
    configError: "test: no config",
    expect: {},
    notes: [],
  };
}

const OPS = [
  "host_info",
  "ws_loopback",
  "create_project",
  "scratch_disk",
  "import_fcp7_xml",
  "sequence_settings",
  "export_frame",
  "keyframes_motion_opacity_crop",
  "keyframe_time_basis",
  "effects_by_match_name",
  "clip_edits_transitions_tracks",
  "track_rename",
  "markers",
  "project_views",
  "host_calls",
  "undo_transaction",
  "save_close_open",
  "save_as",
  "encoder_export",
];

test("without a config only the read-only probes run; every other probe is skipped with ok:null 'no config'", async () => {
  const ops = await runAll(buildProbes(), baseCtx({}));
  assert.deepEqual(
    ops.map((o) => o.op),
    OPS,
  );
  for (const o of ops.slice(2)) {
    assert.equal(o.ok, null, `${o.op} -> ${o.ok}`);
    assert.match(String(o.detail), /^no config/);
  }
  // 0.1.3: the link probe is real. It needs no config, so with no engine.json (no `reel serve`) it fails on its first step
  // and opens no socket (spike-013.test.ts covers the live-link behaviour against a fake daemon).
  const ws = ops.find((o) => o.op === "ws_loopback");
  assert.equal(ws?.ok, false);
  assert.match(JSON.stringify(ws?.detail), /engine\.json/);
});

// ---- a tiny fake Premiere: enough to exercise tx(), Steps and the transaction label -------------------------------

interface FakeAction {
  apply: () => void;
}

function fakePremiere() {
  const labels: string[] = [];
  const marks: Array<{ name: string; start: number; dur: number; comments: string; color: number }> = [];
  const trackNames = { v: ["V1 original", "V2 original"], a: ["A1 original", "A2 original"] };
  const track = (kind: "v" | "a", i: number) => ({
    get name() {
      return trackNames[kind][i] as string;
    },
    createSetNameAction: (n: string): FakeAction => ({ apply: () => void (trackNames[kind][i] = n) }),
  });
  const markersObj = {
    createAddMarkerAction: (name: string, _t: string, start: { seconds: number }, dur: { seconds: number }, comments: string): FakeAction => ({
      apply: () => void marks.push({ name, start: start.seconds, dur: dur.seconds, comments, color: 0 }),
    }),
    getMarkers: () =>
      marks.map((m) => ({
        getName: () => m.name,
        getType: () => "Comment",
        getStart: () => ({ seconds: m.start }),
        getDuration: () => ({ seconds: m.dur }),
        getComments: () => m.comments,
        getColorIndex: () => m.color,
        createSetColorByIndexAction: (c: number): FakeAction => ({ apply: () => void (m.color = c) }),
      })),
  };
  const sequence = {
    name: "SEQ",
    getVideoTrack: async (i: number) => track("v", i),
    getAudioTrack: async (i: number) => track("a", i),
    getVideoTrackCount: async () => 2,
    getAudioTrackCount: async () => 2,
  };
  const project = {
    path: `${WHYNOT_TEST}/_uxp-spike/spike-1.prproj`,
    lockedAccess: (cb: () => void) => cb(),
    executeTransaction: (cb: (ca: { addAction: (a: FakeAction) => boolean }) => void, label?: string) => {
      labels.push(label ?? "");
      cb({
        addAction: (a) => {
          a.apply();
          return true;
        },
      });
      return true;
    },
  };
  const ppro = {
    Markers: { getMarkers: async () => markersObj },
    Marker: { MARKER_TYPE_COMMENT: "Comment" },
    TickTime: { createWithSeconds: (seconds: number) => ({ seconds }) },
    Constants: { MarkerColor: { RED: 1 } },
  };
  return { ppro, project, sequence, labels, marks, trackNames };
}

const WHYNOT_TEST = "D:/0 Work/0 Pegasus IMC Agency/00 TWN/0 TWN AI/Editing Plugin/whynot-test";

/** A context as it looks after create_project + import_fcp7_xml succeeded against the fake. */
function scratchCtx(f: ReturnType<typeof fakePremiere>): Ctx {
  const ctx = baseCtx(f.ppro);
  ctx.config = { xml_path: `${WHYNOT_TEST}/a.xml`, work_dir: `${WHYNOT_TEST}/_uxp-spike` };
  ctx.project = f.project as unknown as Ctx["project"];
  ctx.sequence = f.sequence as unknown as Ctx["sequence"];
  return ctx;
}

function probe(op: string) {
  const p = buildProbes().find((d) => d.op === op);
  assert.ok(p, `no probe ${op}`);
  return p;
}

test("track_rename renames V2 and A2 only (V1/A1 belong to undo_transaction) inside transactions labelled with the probe", async () => {
  const f = fakePremiere();
  const ctx = scratchCtx(f);
  const r = await runProbe(probe("track_rename"), ctx);
  assert.equal(r.ok, true, JSON.stringify(r));
  assert.deepEqual(f.trackNames, { v: ["V1 original", "WNC Spike V2"], a: ["A1 original", "WNC Spike A2"] });
  assert.deepEqual(f.labels, ["WNC spike: track_rename", "WNC spike: track_rename"]);
  assert.equal(ctx.expect.renamedVideoTrackName, "WNC Spike V2");
  assert.equal(ctx.expect.videoTrackName, undefined, "V1's expected name is set only by undo_transaction");
});

test("markers adds two markers and recolours one", async () => {
  const f = fakePremiere();
  const ctx = scratchCtx(f);
  const r = await runProbe(probe("markers"), ctx);
  assert.equal(r.ok, true, JSON.stringify(r));
  assert.equal(f.marks.length, 2);
  assert.equal(f.marks[1]?.color, 1);
  assert.equal(ctx.expect.markerCount, 2);
  assert.ok(f.marks.every((m) => m.name !== "WNC undo marker"), "markers never uses the undo probe's marker");
  assert.ok(f.labels.every((l) => l === "WNC spike: markers"));
});

test("undo_transaction does three changes in ONE transaction labelled 'WhyNot Cut build'", async () => {
  const f = fakePremiere();
  const ctx = scratchCtx(f);
  const r = await runProbe(probe("undo_transaction"), ctx);
  assert.equal(r.ok, true, JSON.stringify(r));
  assert.deepEqual(f.labels, ["WhyNot Cut build"]);
  assert.equal(f.trackNames.v[0], "WNC Undo Test");
  assert.equal(f.trackNames.a[0], "WNC Undo Test A1");
  assert.equal(f.marks.length, 1);
});

test("save_close_open is n/a (not a failure) when 'keep project open' is selected", async () => {
  skipSaveCloseOpen.value = true;
  try {
    const f = fakePremiere();
    const ctx = scratchCtx(f);
    const r = await runProbe(probe("save_close_open"), ctx);
    assert.equal(r.ok, null);
  } finally {
    skipSaveCloseOpen.value = false;
  }
});

// ws_loopback (the real link: engine.json, hello/welcome, snapshot, idle keepalive) is tested in spike-013.test.ts.
