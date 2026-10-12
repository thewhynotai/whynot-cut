// export_frames, encoding the measured Q1 facts: Exporter.exportSequenceFrame(seq, TickTime, "<bare name>.png",
// "<native backslash folder>\\", w, h); `false` is not a throw (-> the {t, error} form); the PNG appears before it is
// complete, so the op waits until its size stops changing; `called` = the call returned true; no `tc` (TickTime).
import { test } from "node:test";
import assert from "node:assert/strict";
import { OPS } from "../src/ops/index.ts";
import { OpError } from "../src/ops/types.ts";
import { validateReadback } from "../src/ops/validate.ts";
import { SEQ, WIN_OTHER, WIN_PROJECT, makeEnv, opCtx } from "./host-adapter.fakes.ts";

const OUT = "D:\\0 Work\\Clients\\EP02TEST_R02\\08_quality_control\\premiere_frames\\run-20261012-101010";
const OUT_FWD = OUT.replace(/\\/g, "/");

function setup() {
  const e = makeEnv();
  e.pp.addOpen(WIN_PROJECT, [{ name: "Other" }, { name: SEQ, width: 1080, height: 1920 }]);
  e.fs.dirs.add(OUT_FWD);
  return e;
}

test("export_frames: bare file name + backslash folder with a trailing backslash, one entry per time in order", async () => {
  const { env, pp } = setup();
  const { ctx, progressed } = opCtx(env);
  const rb = await OPS.export_frames.run({ sequence_name: SEQ, times: [1.188, 2.5, 30], out_dir: OUT }, ctx);
  assert.deepEqual(rb, {
    frames: [
      { t: 1.188, file: `${OUT}\\frame_001188.png`, called: true },
      { t: 2.5, file: `${OUT}\\frame_002500.png`, called: true },
      { t: 30, file: `${OUT}\\frame_030000.png`, called: true },
    ],
  });
  const exports = pp.calls.filter((c) => c.startsWith("export "));
  assert.deepEqual(exports, [
    `export ${SEQ} 1.188 frame_001188.png ${OUT}\\ 1080x1920`,
    `export ${SEQ} 2.5 frame_002500.png ${OUT}\\ 1080x1920`,
    `export ${SEQ} 30 frame_030000.png ${OUT}\\ 1080x1920`,
  ]);
  assert.ok(pp.calls.indexOf(`setActiveSequence ${SEQ}`) < pp.calls.indexOf(exports[0]!), "the sequence is made active first");
  assert.deepEqual(progressed.map((p) => [p.n, p.of]), [[0, 3], [1, 3], [2, 3]]);
  assert.equal(validateReadback("export_frames", rb), null);
});

test("export_frames: waits until the PNG stops growing (it shows up before it is fully written)", async () => {
  const { env, fs, pp } = setup();
  pp.frameGrowth = [0, 114_967, 900_000, 1_610_035];
  await OPS.export_frames.run({ sequence_name: SEQ, times: [1], out_dir: OUT }, opCtx(env).ctx);
  const path = `${OUT_FWD}/frame_001000.png`;
  const reads = fs.calls.filter((c) => c === `lstat ${path}`).length;
  // 0 (not there yet), 114 967, 900 000, 1 610 035, then 1 610 035 again = stable
  // (+1: the target is looked up once before the export, to delete an older frame of the same name)
  assert.ok(reads >= 6, `polled ${reads} times`);
  assert.equal(fs.files.get(path)?.reads, reads - 1);
});

test("export_frames: forward slashes, a trailing separator and the \\\\?\\ prefix in out_dir all give the same native folder", async () => {
  for (const out of [OUT_FWD, `${OUT}\\`, `${OUT_FWD}/`, `\\\\?\\${OUT}`]) {
    const { env, pp } = setup();
    const rb = await OPS.export_frames.run({ sequence_name: SEQ, times: [2], out_dir: out }, opCtx(env).ctx);
    assert.deepEqual(rb.frames, [{ t: 2, file: `${OUT}\\frame_002000.png`, called: true }], out);
    assert.ok(pp.calls.includes(`export ${SEQ} 2 frame_002000.png ${OUT}\\ 1080x1920`), out);
  }
});

test("export_frames: false, a throw and a file that never appears are per-frame errors; the other frames still export", async () => {
  const { env, pp } = setup();
  pp.exportReturns = (t) => t !== 2;
  const rb = await OPS.export_frames.run({ sequence_name: SEQ, times: [1, 2], out_dir: OUT }, opCtx(env).ctx);
  assert.deepEqual(rb.frames[0], { t: 1, file: `${OUT}\\frame_001000.png`, called: true });
  assert.equal(rb.frames[1]!.t, 2);
  assert.match((rb.frames[1] as { error: string }).error, /returned false/);

  const thrown = setup();
  (thrown.pp.api.Exporter as { exportSequenceFrame: unknown }).exportSequenceFrame = async () => {
    throw new Error("Illegal Parameter type");
  };
  const rb2 = await OPS.export_frames.run({ sequence_name: SEQ, times: [3], out_dir: OUT }, opCtx(thrown.env).ctx);
  assert.deepEqual(rb2.frames, [{ t: 3, error: "exportSequenceFrame failed: Illegal Parameter type" }]);

  const ghost = setup();
  ghost.pp.exportWritesNothing = true;
  const rb3 = await OPS.export_frames.run({ sequence_name: SEQ, times: [4], out_dir: OUT }, opCtx(ghost.env).ctx);
  assert.equal(rb3.frames.length, 1);
  assert.match((rb3.frames[0] as { error: string }).error, /no file appeared/);
  assert.ok(ghost.now() - 1_000_000 < 60_000, "gives up after the appear timeout, not forever");
  for (const r of [rb, rb2, rb3]) assert.equal(validateReadback("export_frames", r), null);
});

test("export_frames: project_path makes that project active first (Project.open with the native path)", async () => {
  const { env, pp } = setup();
  pp.addOpen(WIN_OTHER, [{ name: "A" }]);
  assert.equal(pp.active?.native, WIN_OTHER);
  const rb = await OPS.export_frames.run({ sequence_name: SEQ, times: [1], out_dir: OUT, project_path: WIN_PROJECT.replace(/\\/g, "/") }, opCtx(env).ctx);
  assert.equal(pp.calls[0], `Project.open ${WIN_PROJECT}`);
  assert.equal(pp.active?.native, WIN_PROJECT);
  assert.equal((rb.frames[0] as { called?: boolean }).called, true);
});

test("export_frames: a missing out_dir is created; an unknown sequence or no project is an OpError", async () => {
  const { env, fs } = setup();
  fs.dirs.clear();
  fs.dirs.add("D:/0 Work/Clients/EP02TEST_R02/08_quality_control");
  await OPS.export_frames.run({ sequence_name: SEQ, times: [1], out_dir: OUT }, opCtx(env).ctx);
  assert.ok(fs.calls.includes(`mkdir D:/0 Work/Clients/EP02TEST_R02/08_quality_control/premiere_frames`));
  assert.ok(fs.calls.includes(`mkdir ${OUT_FWD}`));
  await assert.rejects(() => OPS.export_frames.run({ sequence_name: "Nope", times: [1], out_dir: OUT }, opCtx(env).ctx), (e: unknown) => e instanceof OpError && /no sequence named "Nope"/.test(e.message));
  const none = makeEnv();
  await assert.rejects(() => OPS.export_frames.run({ sequence_name: SEQ, times: [1], out_dir: OUT }, opCtx(none.env).ctx), /open a project/i);
});

test("export_frames: a cancel between frames stops the export (the cancelled error, not a partial ok)", async () => {
  const { env, pp } = setup();
  const { ctx } = opCtx(env, { cancelAfterProgress: 2 });
  await assert.rejects(() => OPS.export_frames.run({ sequence_name: SEQ, times: [1, 2, 3, 4], out_dir: OUT }, ctx), /cancel/i);
  assert.ok(pp.calls.filter((c) => c.startsWith("export ")).length <= 2);
});
