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
  "undo_transaction",
  "sequence_settings",
  "export_frame",
  "keyframes_motion_opacity_crop",
  "keyframe_time_basis",
  "effects_by_match_name",
  "clip_edits_transitions_tracks",
  "track_rename",
  "markers",
  "project_views",
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
  assert.equal(ops.find((o) => o.op === "ws_loopback")?.detail, "pending reel serve (T6.2)");
});

// ---- a tiny fake Premiere: enough to exercise tx(), Steps and the transaction label -------------------------------

interface FakeAction {
  apply: () => void;
}

function fakePremiere() {
  const labels: string[] = [];
  const marks: Array<{ name: string; start: number; dur: number; comments: string; color: number }> = [];
  const trackNames = { v: ["V1 original"], a: ["A1 original"] };
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
    getAudioTrackCount: async () => 1,
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

test("track_rename renames V1 and A1 inside labelled transactions and reads the names back", async () => {
  const f = fakePremiere();
  const ctx = scratchCtx(f);
  const r = await runProbe(probe("track_rename"), ctx);
  assert.equal(r.ok, true, JSON.stringify(r));
  assert.deepEqual(f.trackNames, { v: ["WNC Spike V1"], a: ["WNC Spike A1"] });
  assert.deepEqual(f.labels, [UNDO_LABEL, UNDO_LABEL]);
  assert.equal(ctx.expect.videoTrackName, "WNC Spike V1");
});

test("markers adds two markers and recolours one", async () => {
  const f = fakePremiere();
  const ctx = scratchCtx(f);
  const r = await runProbe(probe("markers"), ctx);
  assert.equal(r.ok, true, JSON.stringify(r));
  assert.equal(f.marks.length, 2);
  assert.equal(f.marks[1]?.color, 1);
  assert.equal(ctx.expect.markerCount, 2);
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

// ---- ws_loopback against a fake WebSocket -----------------------------------------------------------------------

type G = { WebSocket?: unknown };

function withFakeWebSocket<T>(factory: (url: string) => Record<string, unknown>, fn: () => Promise<T>): Promise<T> {
  const g = globalThis as G;
  const saved = g.WebSocket;
  g.WebSocket = function (this: unknown, url: string) {
    const ws = factory(url);
    queueMicrotask(() => (ws.__start as () => void)());
    return ws;
  };
  return fn().finally(() => {
    g.WebSocket = saved;
  });
}

test("ws_loopback: connects to ws_url, sends a protocol-4 ping, ok on a reply", async () => {
  const sent: string[] = [];
  const ctx = baseCtx({});
  ctx.config = { xml_path: "x", work_dir: "w", ws_url: "ws://127.0.0.1:9999/panel" };
  const r = await withFakeWebSocket(
    () => {
      const ws: Record<string, unknown> = {
        send: (m: string) => {
          sent.push(m);
          queueMicrotask(() => (ws.onmessage as (e: unknown) => void)({ data: '{"ok":true}' }));
        },
        close: () => {},
        __start: () => (ws.onopen as () => void)(),
      };
      return ws;
    },
    () => runProbe(probe("ws_loopback"), ctx),
  );
  assert.equal(r.ok, true, JSON.stringify(r));
  assert.equal(JSON.parse(sent[0] ?? "{}").protocol, 4);
  assert.equal((r.detail as { reply: string }).reply, '{"ok":true}');
});

test("ws_loopback: a socket error is ok:false", async () => {
  const ctx = baseCtx({});
  ctx.config = { xml_path: "x", work_dir: "w", ws_url: "ws://127.0.0.1:1/none" };
  const r = await withFakeWebSocket(
    () => {
      const ws: Record<string, unknown> = { send: () => {}, close: () => {}, __start: () => (ws.onerror as (e: unknown) => void)({ message: "ECONNREFUSED" }) };
      return ws;
    },
    () => runProbe(probe("ws_loopback"), ctx),
  );
  assert.equal(r.ok, false);
});
