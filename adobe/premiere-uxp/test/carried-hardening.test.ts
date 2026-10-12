// Hardening carried into Task 4 from the round-3 reviews of the host adapter (Task 3):
//   - export_frames refuses a relative out_dir and never reports an old PNG as a fresh frame (the target is deleted
//     before the export; when it cannot be, the new file must differ in size or mtime);
//   - open_project checks that the project Premiere made active is the one asked for;
//   - nativePath turns a forward-slash UNC share (//server/share) into \\server\share;
//   - ping / status use the guarded host version (a throwing uxp.host.version is "", not a failed command);
//   - open_project / set_player_position check for a cancel before they answer ok.
import { test } from "node:test";
import assert from "node:assert/strict";
import { startHostAdapter } from "../src/host-adapter.ts";
import { OPS } from "../src/ops/index.ts";
import { OpError } from "../src/ops/types.ts";
import { validateReadback } from "../src/ops/validate.ts";
import { nativePath } from "../src/uxp-host.ts";
import { FakeSocket, SEQ, WIN_OTHER, WIN_PROJECT, makeEnv, opCtx, request, settle } from "./host-adapter.fakes.ts";

const OUT = "D:\\0 Work\\Clients\\EP02TEST_R02\\08_quality_control\\premiere_frames\\run-20261012-101010";
const OUT_FWD = OUT.replace(/\\/g, "/");
const fwd = (p: string) => p.replace(/\\/g, "/");

function setup() {
  const e = makeEnv();
  e.pp.addOpen(WIN_PROJECT, [{ name: SEQ, width: 1080, height: 1920 }]);
  e.fs.dirs.add(OUT_FWD);
  return e;
}

// ---- export_frames ------------------------------------------------------------------------------------------------

test("export_frames: a relative out_dir is refused before Premiere is touched", async () => {
  for (const out of ["frames", "./frames", "..\\frames", "run/frames", "C:frames"]) {
    const { env, pp, fs } = setup();
    await assert.rejects(
      () => OPS.export_frames.run({ sequence_name: SEQ, times: [1], out_dir: out }, opCtx(env).ctx),
      (e: unknown) => e instanceof OpError && /not an absolute folder path/.test(e.message) && e.message.includes(out),
      out,
    );
    assert.deepEqual(pp.calls, [], out);
    assert.ok(!fs.calls.some((c) => c.startsWith("mkdir")), out);
  }
  for (const out of [OUT, OUT_FWD, "\\\\srv\\share\\frames", "//srv/share/frames", "/Users/ed/frames", `\\\\?\\${OUT}`]) {
    const { env } = setup();
    const rb = await OPS.export_frames.run({ sequence_name: SEQ, times: [1], out_dir: out }, opCtx(env).ctx);
    assert.equal(rb.frames.length, 1, out);
  }
});

test("export_frames: an old PNG at the target is deleted first, so a failed export is never reported as a fresh frame", async () => {
  const { env, pp, fs } = setup();
  const target = `${OUT_FWD}/frame_001000.png`;
  fs.write(target, [1_610_035]); // yesterday's frame
  pp.exportWritesNothing = true; // Premiere says true, writes nothing
  const rb = await OPS.export_frames.run({ sequence_name: SEQ, times: [1], out_dir: OUT }, opCtx(env).ctx);
  assert.ok(fs.calls.includes(`unlink ${target}`));
  assert.ok(!fs.files.has(target), "the old frame is gone");
  assert.equal(rb.frames.length, 1);
  assert.match((rb.frames[0] as { error?: string }).error ?? "", /no file appeared/);
  assert.equal(validateReadback("export_frames", rb), null);
});

test("export_frames: the old PNG cannot be deleted -> the new one must differ in mtime or size; an unchanged file is an error", async () => {
  // could not delete, Premiere wrote nothing: same size, same mtime -> stale
  const stale = setup();
  const target = `${OUT_FWD}/frame_001000.png`;
  stale.fs.write(target, [1_610_035], 1_600_000_000_000);
  stale.fs.unlinkThrows = true;
  stale.pp.exportWritesNothing = true;
  const rb = await OPS.export_frames.run({ sequence_name: SEQ, times: [1], out_dir: OUT }, opCtx(stale.env).ctx);
  assert.match((rb.frames[0] as { error?: string }).error ?? "", /older frame_001000\.png .* was not replaced/);
  assert.equal(validateReadback("export_frames", rb), null);

  // could not delete, Premiere rewrote it (same size, newer mtime) -> fresh
  const rewritten = setup();
  rewritten.fs.write(target, [1_610_035], 1_600_000_000_000);
  rewritten.fs.unlinkThrows = true;
  rewritten.pp.frameGrowth = [1_610_035];
  const ok = await OPS.export_frames.run({ sequence_name: SEQ, times: [1], out_dir: OUT }, opCtx(rewritten.env).ctx);
  assert.deepEqual(ok.frames, [{ t: 1, file: `${OUT}\\frame_001000.png`, called: true }]);

  // no unlink and no mtime in this fs: only a size change proves a new file
  const blind = setup();
  blind.fs.hasUnlink = false;
  blind.fs.reportsMtime = false;
  blind.fs.write(target, [1_610_035]);
  blind.pp.frameGrowth = [1_610_035];
  const same = await OPS.export_frames.run({ sequence_name: SEQ, times: [1], out_dir: OUT }, opCtx(blind.env).ctx);
  assert.match((same.frames[0] as { error?: string }).error ?? "", /was not replaced/);
  blind.pp.frameGrowth = [0, 2_000_000];
  const grown = await OPS.export_frames.run({ sequence_name: SEQ, times: [1], out_dir: OUT }, opCtx(blind.env).ctx);
  assert.equal((grown.frames[0] as { called?: boolean }).called, true);
});

test("export_frames: no old file -> no unlink call; the normal path is unchanged", async () => {
  const { env, fs } = setup();
  const rb = await OPS.export_frames.run({ sequence_name: SEQ, times: [2.5], out_dir: OUT }, opCtx(env).ctx);
  assert.deepEqual(rb.frames, [{ t: 2.5, file: `${OUT}\\frame_002500.png`, called: true }]);
  assert.ok(!fs.calls.some((c) => c.startsWith("unlink")));
});

// ---- open_project -------------------------------------------------------------------------------------------------

test("open_project: Premiere activating a different project than the one asked for is an OpError, not ok", async () => {
  const { env, pp } = makeEnv();
  pp.addOpen(WIN_OTHER, [{ name: "A" }]);
  pp.disk.set(WIN_PROJECT, [{ name: SEQ }]);
  const other = pp.projects[0]!;
  (pp.api.Project as { open: unknown }).open = async (path: string) => {
    pp.calls.push(`Project.open ${path}`);
    return other; // e.g. a dialog was dismissed and the old project stayed active
  };
  await assert.rejects(() => OPS.open_project.run({ path: WIN_PROJECT }, opCtx(env).ctx), (e: unknown) => {
    assert.ok(e instanceof OpError);
    assert.ok(e.message.includes(WIN_PROJECT), e.message);
    assert.ok(e.message.includes(WIN_OTHER), e.message);
    assert.match(e.message, /instead of/);
    return true;
  });
  // export_frames' project_path goes through the same check
  const ex = makeEnv();
  ex.pp.addOpen(WIN_OTHER, [{ name: SEQ }]);
  const o = ex.pp.projects[0]!;
  (ex.pp.api.Project as { open: unknown }).open = async () => o;
  await assert.rejects(
    () => OPS.export_frames.run({ sequence_name: SEQ, times: [1], out_dir: OUT, project_path: fwd(WIN_PROJECT) }, opCtx(ex.env).ctx),
    /instead of/,
  );
});

test("open_project and set_player_position: a cancel that lands while Premiere works is answered as cancelled, not ok", async () => {
  const a = makeEnv();
  a.pp.disk.set(WIN_PROJECT, [{ name: SEQ }]);
  const { ctx: openCtx } = opCtx(a.env, { cancelAfterProgress: 1 }); // cancelled right after the "Opening" step
  await assert.rejects(() => OPS.open_project.run({ path: WIN_PROJECT }, openCtx), /cancel/i);

  const b = makeEnv();
  const p = b.pp.addOpen(WIN_PROJECT, [{ name: SEQ }]);
  const c = opCtx(b.env);
  const seq = p.sequences[0]!;
  const original = seq.setPlayerPosition.bind(seq);
  seq.setPlayerPosition = async (t: { seconds: number }) => {
    c.cancel();
    return original(t);
  };
  await assert.rejects(() => OPS.set_player_position.run({ sequence_name: SEQ, t_s: 4 }, c.ctx), /cancel/i);
});

// ---- nativePath ---------------------------------------------------------------------------------------------------

test("nativePath: a forward-slash UNC share becomes \\\\server\\share; other forms unchanged", () => {
  assert.equal(nativePath("//srv/share/clients/a.prproj"), "\\\\srv\\share\\clients\\a.prproj");
  assert.equal(nativePath("//srv/share"), "\\\\srv\\share");
  assert.equal(nativePath("\\\\srv\\share\\a"), "\\\\srv\\share\\a");
  assert.equal(nativePath("//?/UNC/srv/share/a"), "\\\\srv\\share\\a");
  assert.equal(nativePath("//?/D:/w/a"), "D:\\w\\a");
  assert.equal(nativePath("/Users/x/a"), "/Users/x/a");
});

// ---- guarded host version -----------------------------------------------------------------------------------------

test("ping / status: a throwing uxp.host.version gives '' (the hello's guard), not a failed command", async () => {
  const { env } = makeEnv();
  env.hostVersion = () => {
    throw new Error("host.version is not readable");
  };
  const ping = await OPS.ping.run({}, opCtx(env).ctx);
  assert.equal(ping.version, "");
  assert.equal(validateReadback("ping", ping), null);
  const status = await OPS.status.run({}, opCtx(env).ctx);
  assert.equal(status.hostVersion, "");
  assert.equal(validateReadback("status", status), null);
  // through the adapter: the hello leaves hostVersion out, ping still answers ok
  const sock = new FakeSocket();
  startHostAdapter({ socket: sock, token: "a".repeat(64), env });
  const hello = sock.sent[0] as { client: Record<string, unknown> };
  assert.ok(!("hostVersion" in hello.client));
  sock.deliver(request("ping", {}, "p-1"));
  await settle(() => sock.of("result").length > 0);
  const res = sock.of<{ result: { ok: boolean } }>("result")[0]!;
  assert.equal(res.result.ok, true);
});

test("ping / status: a very long host version is cut to 64 characters like the hello's", async () => {
  const { env } = makeEnv({ hostVersion: "9".repeat(100) });
  assert.equal((await OPS.ping.run({}, opCtx(env).ctx)).version, "9".repeat(64));
  assert.equal((await OPS.status.run({}, opCtx(env).ctx)).hostVersion, "9".repeat(64));
});
