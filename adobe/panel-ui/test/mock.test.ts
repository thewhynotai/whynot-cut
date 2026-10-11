import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { MockSource, sampleState } from "../src/mock.ts";
import { exportFramesAction, openProjectAction, renderReviewAction, rebuildInput } from "../src/actions.ts";
import type { PanelState } from "../src/source.ts";

const CONTRACT = new URL("../../../whynot-cut/engine/reel/contract/", import.meta.url);
const ajv = new Ajv2020({ strict: false, allErrors: true });
(addFormats as unknown as (a: unknown) => void)(ajv);
const load = (name: string) => {
  const schema = JSON.parse(readFileSync(new URL(`${name}.schema.json`, CONTRACT), "utf8"));
  ajv.addSchema(schema);
  return schema as { $id: string; $defs: Record<string, { properties?: Record<string, unknown> }> };
};
const schemas: Record<string, ReturnType<typeof load>> = {};
for (const a of ["open_project", "export_frames", "render_review", "set_player_position", "build_project", "status", "result"]) schemas[a] = load(a);
const validator = (action: string, def: "data" | "readback") => ajv.getSchema(`${schemas[action]!.$id}#/$defs/${def}`)!;
const check = (action: string, def: "data" | "readback", value: unknown) => {
  const v = validator(action, def);
  assert.ok(v(value), `${action}.${def}: ${JSON.stringify(v.errors)}`);
};

test("sampleState: realistic PODCAST-TEST content for EN and an Arabic variant", () => {
  const en = sampleState("en", "showcase");
  const ar = sampleState("ar", "showcase");
  assert.equal(en.language, "en");
  assert.equal(ar.language, "ar");
  assert.notEqual(en.client, ar.client);
  assert.match(ar.client, /[؀-ۿ]/);
  assert.match(ar.context.project_path ?? "", /[؀-ۿ]/);
  assert.equal(en.approval!.flagged.length, 2);
  assert.deepEqual(new Set(en.qc.map((q) => q.verdict)), new Set(["pass", "fail", "pending", "media_pending"]));
  assert.equal(en.pipeline.length, 7);
});

test("every scenario is internally consistent (one current step, ids in order)", () => {
  for (const sc of ["showcase", "approval", "building", "qc", "idle"] as const) {
    const s = sampleState("en", sc);
    assert.deepEqual(s.pipeline.map((p) => p.id), ["transcript", "plan", "approve", "build", "frames", "qc", "handoff"]);
  }
  const b = sampleState("en", "building");
  assert.equal(b.pipeline.find((p) => p.id === "build")!.state, "running");
});

test("MockSource: snapshot, subscribe/unsubscribe, setLanguage notifies", async () => {
  const m = new MockSource({ language: "en", scenario: "approval" });
  const seen: PanelState[] = [];
  const off = m.subscribe((s) => seen.push(s));
  assert.equal((await m.snapshot()).language, "en");
  m.setLanguage("ar");
  assert.equal(seen.at(-1)!.language, "ar");
  off();
  m.setLanguage("en");
  assert.equal(seen.length, 1);
});

test("MockSource: approve with the right fingerprint clears the approval and advances the pipeline; a wrong one is refused", async () => {
  const m = new MockSource({ language: "en", scenario: "approval" });
  const s = await m.snapshot();
  const bad = await m.approve({ item: s.item, editor_name: "Layla", fingerprint: "stale" });
  assert.equal(bad.ok, false);
  assert.ok(bad.error && bad.how);
  const ok = await m.approve({ item: s.item, editor_name: "Layla", fingerprint: s.approval!.fingerprint });
  assert.equal(ok.ok, true);
  const after = await m.snapshot();
  assert.equal(after.approval, null);
  assert.equal(after.pipeline.find((p) => p.id === "approve")!.state, "done");
});

test("MockSource: requestChanges records the request and keeps the plan blocked", async () => {
  const m = new MockSource({ language: "en", scenario: "approval" });
  const s = await m.snapshot();
  const r = await m.requestChanges({ item: s.item, editor_name: "Layla", text: "Shorter intro" });
  assert.equal(r.ok, true);
  const after = await m.snapshot();
  assert.ok(after.log.some((l) => l.text.includes("Shorter intro")));
});

test("MockSource.advance moves the build step forward and finishes it", async () => {
  const m = new MockSource({ language: "en", scenario: "building" });
  let last = (await m.snapshot()).pipeline.find((p) => p.id === "build")!;
  const n0 = last.progress!.n;
  m.advance();
  last = (await m.snapshot()).pipeline.find((p) => p.id === "build")!;
  assert.ok(last.progress!.n > n0);
  for (let i = 0; i < 100; i++) m.advance();
  assert.equal((await m.snapshot()).pipeline.find((p) => p.id === "build")!.state, "done");
});

test("requests the panel builds are valid against the v4 action schemas", () => {
  const s = sampleState("en", "qc");
  const open = openProjectAction(s)!;
  assert.equal(open.action, "open_project");
  check("open_project", "data", open.data);
  const ex = exportFramesAction(s)!;
  assert.equal(ex.action, "export_frames");
  check("export_frames", "data", ex.data);
  const one = exportFramesAction(s, [s.qc[0]!.t_s])!;
  check("export_frames", "data", one.data);
  const rv = renderReviewAction(s)!;
  assert.equal(rv.action, "render_review");
  check("render_review", "data", rv.data);
});

test("rebuild is a panel intent, not a build_project request: item + project_path + replace_edited", () => {
  const rb = rebuildInput(sampleState("en", "qc"))!;
  assert.deepEqual(Object.keys(rb).sort(), ["item", "project_path", "replace_edited"]);
  assert.equal(rb.replace_edited, true, "only built after the in-panel confirm");
  assert.equal(rb.item, "EP01_R03");
});

test("BuildProjectData mirrors the schema: required keys and every property name", () => {
  const src = readFileSync(new URL("../src/contract.ts", import.meta.url), "utf8");
  const body = /export interface BuildProjectData \{([\s\S]*?)\n\}/.exec(src)![1]!;
  const declared = [...body.matchAll(/^\s{2}(\w+)(\??):/gm)].map((m) => ({ k: m[1]!, optional: m[2] === "?" }));
  const def = schemas["build_project"]!.$defs["data"] as unknown as { properties: Record<string, unknown>; required: string[] };
  assert.deepEqual(declared.map((d) => d.k).sort(), Object.keys(def.properties).sort());
  assert.deepEqual(declared.filter((d) => !d.optional).map((d) => d.k).sort(), [...def.required].sort());
});

test("actions return null when the context is missing", () => {
  const s = sampleState("en", "idle");
  s.context = { project_path: null, sequence_name: null, folder: null, out_dir: null, review_mp4: null };
  assert.equal(openProjectAction(s), null);
  assert.equal(exportFramesAction(s), null);
  assert.equal(renderReviewAction(s), null);
  assert.equal(rebuildInput(s), null);
});

test("MockSource.run answers with readbacks that satisfy the contract", async () => {
  const m = new MockSource({ language: "en", scenario: "qc" });
  const s = await m.snapshot();
  for (const [build, name] of [[openProjectAction, "open_project"], [exportFramesAction, "export_frames"], [renderReviewAction, "render_review"]] as const) {
    const a = build(s)!;
    const r = await m.run(a.action, a.data);
    assert.equal(r.ok, true, name);
    check(name, "readback", r.readback);
  }
  const st = await m.run("status", {});
  check("status", "readback", st.readback);
  const bad = await m.run("ae_render", {});
  assert.equal(bad.ok, false);
});

test("every v4 result the mock produces validates against result.schema.json and its action's readback", async () => {
  const m = new MockSource({ language: "en", scenario: "qc" });
  const s = await m.snapshot();
  const resultV = ajv.getSchema(`${schemas["result"]!.$id}`)!;
  const results = [
    await m.run("status", {}),
    await m.run("open_project", openProjectAction(s)!.data),
    await m.run("export_frames", exportFramesAction(s)!.data),
    await m.run("render_review", renderReviewAction(s)!.data),
    await m.run("set_player_position", { sequence_name: "x", t_s: 1.5 }),
    await m.run("build_project", { project_path: "p" }),
    await m.run("ae_render", {}),
    await m.rebuild(rebuildInput(s)!),
  ];
  for (const r of results) {
    assert.ok(resultV(r), `${r.action}: ${JSON.stringify(resultV.errors)}`);
    if (r.ok) check(r.action!, "readback", r.readback);
  }
});

test("MockSource.rebuild starts the Build step and returns a schema-valid build_project result", async () => {
  const m = new MockSource({ language: "en", scenario: "qc" });
  const s = await m.snapshot();
  const r = await m.rebuild(rebuildInput(s)!);
  assert.equal(r.ok, true);
  assert.equal(r.action, "build_project");
  assert.equal((r.readback as { project: string }).project, s.context.project_path);
  const after = await m.snapshot();
  assert.equal(after.pipeline.find((p) => p.id === "build")!.state, "running");
  assert.ok(after.log.some((l) => /rebuild/i.test(l.text)));
});

test("MockSource.run refuses a hand-built partial build_project with a plain error", async () => {
  const m = new MockSource({ language: "en", scenario: "qc" });
  const r = await m.run("build_project", { project_path: "p", overwrite_existing: true });
  assert.equal(r.ok, false);
  assert.ok(r.error && r.how);
});
