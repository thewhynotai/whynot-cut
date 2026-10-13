// open_project and close_project_path. Project.open takes only a native backslash path (parity O2; the fake refuses
// forward slashes and the raw \\?\ form like Premiere did); paths are compared after stripping \\?\ and normalising
// slashes and drive-letter case; readbacks carry the clean native path.
import { test } from "node:test";
import assert from "node:assert/strict";
import { OPS } from "../src/ops/index.ts";
import { OpError } from "../src/ops/types.ts";
import { validateData, validateReadback } from "../src/ops/validate.ts";
import { SEQ, WIN_OTHER, WIN_PROJECT, makeEnv, opCtx } from "./host-adapter.fakes.ts";

const fwd = (p: string) => p.replace(/\\/g, "/");

test("open_project: a project that is not open is opened with the native backslash path and no options", async () => {
  for (const given of [WIN_PROJECT, fwd(WIN_PROJECT), `\\\\?\\${fwd(WIN_PROJECT)}`]) {
    const { env, pp } = makeEnv();
    pp.disk.set(WIN_PROJECT, [{ name: SEQ }]);
    const { ctx, progressed } = opCtx(env);
    const rb = await OPS.open_project.run({ path: given }, ctx);
    assert.deepEqual(rb, { opened: true, project: WIN_PROJECT }, given);
    assert.deepEqual(pp.calls, [`Project.open ${WIN_PROJECT}`], given);
    assert.equal(validateReadback("open_project", rb), null);
    assert.ok(progressed.length >= 1, "a progress step for a call that can take seconds");
  }
});

test("open_project: already open and active -> no Project.open; open but not active -> activated through Project.open", async () => {
  const { env, pp } = makeEnv();
  pp.addOpen(WIN_PROJECT, [{ name: SEQ }]);
  pp.addOpen(WIN_OTHER, [{ name: "A" }]);
  assert.equal(pp.active?.native, WIN_OTHER);
  const rb = await OPS.open_project.run({ path: WIN_OTHER.replace("D:", "d:") }, opCtx(env).ctx);
  assert.deepEqual(rb, { opened: true, project: WIN_OTHER });
  assert.deepEqual(pp.calls, []);
  const rb2 = await OPS.open_project.run({ path: fwd(WIN_PROJECT) }, opCtx(env).ctx);
  assert.deepEqual(rb2, { opened: true, project: WIN_PROJECT });
  assert.deepEqual(pp.calls, [`Project.open ${WIN_PROJECT}`]);
  assert.equal(pp.active?.native, WIN_PROJECT);
});

test("open_project: Premiere refusing -> OpError naming the path; a missing file says so", async () => {
  const { env, pp, fs } = makeEnv();
  // the file exists but Premiere refuses (a dialog, a newer project version)
  fs.write(fwd(WIN_PROJECT), [5000]);
  await assert.rejects(() => OPS.open_project.run({ path: WIN_PROJECT }, opCtx(env).ctx), (e: unknown) => {
    assert.ok(e instanceof OpError);
    assert.match(e.message, /could not open/i);
    assert.ok(e.message.includes(WIN_PROJECT));
    assert.match(e.how ?? "", /dialog/i);
    return true;
  });
  await assert.rejects(() => OPS.open_project.run({ path: WIN_OTHER }, opCtx(env).ctx), (e: unknown) => {
    assert.ok(e instanceof OpError);
    assert.match(e.message, /no project file/i);
    return true;
  });
  assert.equal(pp.projects.length, 0);
});

test("close_project_path: not open -> closed false, reason 'not open', nothing saved", async () => {
  const { env, pp } = makeEnv();
  pp.addOpen(WIN_OTHER, [{ name: "A" }]);
  const rb = await OPS.close_project_path.run({ path: WIN_PROJECT }, opCtx(env).ctx);
  assert.deepEqual(rb, { closed: false, reason: "not open" });
  assert.deepEqual(pp.calls, []);
  assert.equal(validateReadback("close_project_path", rb), null);
});

test("close_project_path: saves, then closes without prompts; any path form matches; readback has the clean path", async () => {
  const { env, pp } = makeEnv();
  const p = pp.addOpen(WIN_PROJECT, [{ name: SEQ }]);
  pp.addOpen(WIN_OTHER, [{ name: "A" }]);
  const rb = await OPS.close_project_path.run({ path: `\\\\?\\${fwd(WIN_PROJECT).replace("D:", "d:")}` }, opCtx(env).ctx);
  assert.deepEqual(rb, { closed: true, path: WIN_PROJECT, dirty: null, saved: true, dirty_api: null });
  assert.deepEqual(pp.calls, [`save ${p.name}`, `close ${p.name}`]);
  assert.deepEqual((p.closeOptions as { opts: unknown }).opts, { promptIfDirty: false, saveWorkspace: false, showCancelButton: false });
  assert.equal(pp.projects.length, 1);
  assert.equal(validateReadback("close_project_path", rb), null);
});

test("close_project_path: save 'if_clean' is accepted; with no dirty flag in UXP it saves, closes and says dirty null", async () => {
  for (const save of ["if_clean", "always"] as const) {
    const { env, pp } = makeEnv();
    const p = pp.addOpen(WIN_PROJECT, [{ name: SEQ }]);
    const data = { path: WIN_PROJECT, save };
    assert.equal(validateData("close_project_path", data), null, save);
    const rb = await OPS.close_project_path.run(data, opCtx(env).ctx);
    assert.deepEqual(rb, { closed: true, path: WIN_PROJECT, dirty: null, saved: true, dirty_api: null }, save);
    assert.deepEqual(pp.calls, [`save ${p.name}`, `close ${p.name}`], save);
    assert.equal(validateReadback("close_project_path", rb), null, save);
  }
  assert.notEqual(validateData("close_project_path", { path: WIN_PROJECT, save: "never" }), null);
});

test("close_project_path: a failed save leaves the project open (nothing is lost); a refused close is reported", async () => {
  const { env, pp } = makeEnv();
  const p = pp.addOpen(WIN_PROJECT, [{ name: SEQ }]);
  p.saveReturns = false;
  await assert.rejects(() => OPS.close_project_path.run({ path: WIN_PROJECT }, opCtx(env).ctx), (e: unknown) => {
    assert.ok(e instanceof OpError);
    assert.match(e.message, /could not save/i);
    return true;
  });
  assert.deepEqual(pp.calls, [`save ${p.name}`]);
  p.saveReturns = true;
  p.closeReturns = false;
  const rb = await OPS.close_project_path.run({ path: WIN_PROJECT }, opCtx(env).ctx);
  assert.equal(rb.closed, false);
  assert.equal(rb.path, WIN_PROJECT);
  assert.match(String(rb.reason), /did not close/i);
  assert.equal(validateReadback("close_project_path", rb), null);
});
