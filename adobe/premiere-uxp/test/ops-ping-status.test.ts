// ping and status: read-only identity of the host. Version from uxp.host.version (Application.version is undefined on
// 26.5.2, parity P2); paths without the \\?\ prefix (fact 1); no `build` (UXP has none).
import { test } from "node:test";
import assert from "node:assert/strict";
import { OPS } from "../src/ops/index.ts";
import { validateReadback } from "../src/ops/validate.ts";
import { SEQ, WIN_OTHER, WIN_PROJECT, makeEnv, opCtx } from "./host-adapter.fakes.ts";

test("ping: version, the active project's clean path and how many projects are open; no build", async () => {
  const { env, pp } = makeEnv();
  pp.addOpen(WIN_OTHER, [{ name: "A" }]);
  pp.addOpen(WIN_PROJECT, [{ name: SEQ }]);
  const rb = await OPS.ping.run({}, opCtx(env).ctx);
  assert.deepEqual(rb, { version: "26.5.2", project: WIN_PROJECT, projects_open: 2 });
  assert.equal(validateReadback("ping", rb), null);
});

test("ping: no project open -> project '' and 0; a project list Premiere cannot give -> null (not a guess)", async () => {
  const { env, pp } = makeEnv();
  assert.deepEqual(await OPS.ping.run({}, opCtx(env).ctx), { version: "26.5.2", project: "", projects_open: 0 });
  pp.addOpen(WIN_PROJECT, [{ name: SEQ }]);
  pp.viewIdsThrow = true;
  const rb = await OPS.ping.run({}, opCtx(env).ctx);
  assert.deepEqual(rb, { version: "26.5.2", project: WIN_PROJECT, projects_open: null });
  assert.equal(validateReadback("ping", rb), null);
});

test("ping: getActiveProject throwing means no project, not a failed ping", async () => {
  const { env } = makeEnv({
    ppro: {
      Project: { getActiveProject: async () => { throw new Error("no project"); } },
      ProjectUtils: { getProjectViewIds: async () => [] },
    },
  });
  assert.deepEqual(await OPS.ping.run({}, opCtx(env).ctx), { version: "26.5.2", project: "", projects_open: 0 });
});

test("status: host premiere, versions, protocol 4, busy from the adapter, project path or null", async () => {
  const { env, pp } = makeEnv();
  const idle = await OPS.status.run({}, opCtx(env).ctx);
  assert.deepEqual(idle, { host: "premiere", hostVersion: "26.5.2", bundle: "3.0.0", protocol: 4, busy: false, project: null });
  pp.addOpen(WIN_PROJECT, [{ name: SEQ }]);
  const busy = await OPS.status.run({}, opCtx(env, { busy: true }).ctx);
  assert.deepEqual(busy, { host: "premiere", hostVersion: "26.5.2", bundle: "3.0.0", protocol: 4, busy: true, project: WIN_PROJECT });
  assert.equal(validateReadback("status", busy), null);
});

test("ping and status are not exclusive (they answer while a Premiere op runs); the Premiere ops are", () => {
  assert.equal(OPS.ping.exclusive, false);
  assert.equal(OPS.status.exclusive, false);
  for (const a of ["open_project", "set_player_position", "export_frames", "close_project_path", "clip_components"] as const) {
    assert.equal(OPS[a].exclusive, true, a);
    assert.equal(OPS[a].action, a);
  }
});
