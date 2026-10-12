// The v4 command contract, checked from the TypeScript side with ajv (JSON Schema 2020-12 + formats): every schema the engine
// ships compiles, every golden fixture validates, and everything the panel kit's MockSource says and sends validates too.
// Python's stdlib validator (engine/reel/contract/validator.py) is the engine's own check; this is the plugin's.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import type { ValidateFunction } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { ACTION_NAMES, PROTOCOL } from "../../panel-ui/src/contract.ts";
import { exportFramesAction, openProjectAction, rebuildInput, renderReviewAction } from "../../panel-ui/src/actions.ts";
import { MockSource, SCENARIOS } from "../../panel-ui/src/mock.ts";
import type { Result } from "../../panel-ui/src/source.ts";

const CONTRACT_DIR = fileURLToPath(new URL("../../../whynot-cut/engine/reel/contract/", import.meta.url));
const FIXTURE_DIR = fileURLToPath(new URL("../../../whynot-cut/tests/fixtures/contract/", import.meta.url));
const ID_BASE = "https://thewhynot.ai/whynot-cut/contract/4/";

type Schema = { $schema?: string; $id: string; $defs?: Record<string, unknown> };

function loadContract(dir: string) {
  const files = readdirSync(dir).filter((f) => f.endsWith(".schema.json")).sort();
  // strictSchema stays on: an unknown keyword or a typo in a schema must fail loudly. The type-shape rules (union types,
  // "required" of a property declared in a sibling branch) are off: the schemas use both on purpose.
  const ajv = new Ajv2020({ strictSchema: true, strictTypes: false, strictRequired: false, strictTuples: false, allErrors: true });
  (addFormats as unknown as (a: unknown) => void)(ajv);
  const schemas = new Map<string, Schema>();
  for (const f of files) {
    const schema = JSON.parse(readFileSync(join(dir, f), "utf8")) as Schema;
    schemas.set(f.replace(/\.schema\.json$/, ""), schema);
    ajv.addSchema(schema);
  }
  return { ajv, schemas, files };
}

const { ajv, schemas, files } = loadContract(CONTRACT_DIR);
const protocol = JSON.parse(readFileSync(join(CONTRACT_DIR, "protocol.json"), "utf8")) as { protocol: number; actions: Record<string, unknown> };

function getDef(name: string, def?: string): ValidateFunction | undefined {
  const schema = schemas.get(name);
  if (!schema) return undefined;
  return ajv.getSchema(def ? `${schema.$id}#/$defs/${def}` : schema.$id);
}

/** Request envelope + the action's $defs/data (errors under /data), like validator.validate_request. */
function validateRequest(req: unknown): string[] {
  const out: string[] = [];
  const env = getDef("request")!;
  if (!env(req)) out.push(...(env.errors ?? []).map((e) => `${e.instancePath || "/"}: ${e.message}`));
  const r = req as { action?: unknown; data?: unknown } | null;
  if (r && typeof r.action === "string" && (ACTION_NAMES as readonly string[]).includes(r.action) && r.data && typeof r.data === "object") {
    const data = getDef(r.action, "data");
    if (!data) out.push(`/data: ${r.action} has no $defs/data`);
    else if (!data(r.data)) out.push(...(data.errors ?? []).map((e) => `/data${e.instancePath}: ${e.message}`));
  }
  return out;
}

/** Result envelope + $defs/readback (ok) or $defs/readback_failure (not ok, when the action has one). */
function validateResult(res: unknown): string[] {
  const out: string[] = [];
  const env = getDef("result")!;
  if (!env(res)) out.push(...(env.errors ?? []).map((e) => `${e.instancePath || "/"}: ${e.message}`));
  const r = res as { action?: unknown; ok?: unknown; readback?: unknown } | null;
  if (r && typeof r.action === "string" && (ACTION_NAMES as readonly string[]).includes(r.action) && r.readback && typeof r.readback === "object") {
    const def = getDef(r.action, r.ok === true ? "readback" : "readback_failure");
    if (def && !def(r.readback)) out.push(...(def.errors ?? []).map((e) => `/readback${e.instancePath}: ${e.message}`));
  }
  return out;
}

// ---- the schemas ----------------------------------------------------------------------------------------------

test("every contract schema file is draft 2020-12 with the v4 $id, and ajv compiles all of them (with every $ref across files)", () => {
  assert.ok(files.length >= 18, `expected the action + envelope schemas, found ${files.length}`);
  for (const [name, schema] of schemas) {
    assert.equal(schema.$schema, "https://json-schema.org/draft/2020-12/schema", name);
    assert.equal(schema.$id, `${ID_BASE}${name}.schema.json`, name);
    const compiled = ajv.getSchema(schema.$id);
    assert.ok(compiled, `${name}: ajv has no compiled schema for ${schema.$id}`);
    assert.equal(typeof compiled, "function");
    for (const def of Object.keys(schema.$defs ?? {})) {
      assert.ok(ajv.getSchema(`${schema.$id}#/$defs/${def}`), `${name}#/$defs/${def} does not compile`);
    }
  }
});

test("protocol.json: protocol 4, and every action has a schema with $defs/data and $defs/readback", () => {
  assert.equal(protocol.protocol, 4);
  assert.equal(PROTOCOL, 4);
  for (const name of ["request", "result", "progress"]) assert.ok(schemas.has(name), `missing ${name}.schema.json`);
  for (const action of Object.keys(protocol.actions)) {
    const schema = schemas.get(action);
    assert.ok(schema, `no schema for action ${action}`);
    assert.ok(schema.$defs && "data" in schema.$defs && "readback" in schema.$defs, `${action}: needs $defs/data and $defs/readback`);
  }
});

test("the request envelope: protocol must be 4, the action must exist, the id and expiry are checked", () => {
  const req = { protocol: 4, id: "r-1", action: "ping", data: {}, expires_at: "2026-10-12T10:00:00Z" };
  const v = getDef("request")!;
  assert.ok(v(req), JSON.stringify(v.errors));
  for (const bad of [
    { ...req, protocol: 3 },
    { ...req, action: "nope" },
    { ...req, id: "has space" },
    { ...req, id: "" },
    { ...req, expires_at: "tomorrow" },
    { ...req, extra: 1 },
    { protocol: 4, id: "r", action: "ping", data: {} },
  ]) assert.equal(v(bad), false, JSON.stringify(bad));
});

test("the result envelope: ok:true needs a readback, ok:false needs none, an unknown action is rejected", () => {
  const v = getDef("result")!;
  assert.ok(v({ ok: false, action: "ping", error: "x", how: "y" }));
  assert.ok(v({ ok: true, action: "ping", readback: { pong: true } }));
  assert.equal(v({ ok: true, action: "ping" }), false);
  assert.equal(v({ ok: true, action: "nope", readback: {} }), false);
  assert.equal(v({ ok: "yes", action: "ping" }), false);
});

test("C6: ok:true forbids error, ok:false requires it (also with a readback or a how)", () => {
  const v = getDef("result")!;
  assert.equal(v({ ok: true, action: "ping", readback: {}, error: "x" }), false);
  assert.equal(v({ ok: true, action: "ping", readback: {}, error: "" }), false);
  assert.equal(v({ ok: false, action: "ping" }), false);
  assert.equal(v({ ok: false, action: "ping", how: "y" }), false);
  assert.equal(v({ ok: false, action: "ping", readback: { frames: [] } }), false);
  assert.ok(v({ ok: false, action: "ping", error: "x", readback: { reason: "dirty" } }));
  assert.ok(v({ ok: true, action: "ping", readback: { pong: 1 }, how: "fine to carry a how" }));
});

test("C4/C5/C8: a UXP frame has no timecode, a UXP ping has no build, aerender can be refused", () => {
  const frames = getDef("export_frames", "readback")!;
  assert.ok(frames({ frames: [{ t: 1, file: "D:\f.png", called: true }, { t: 2, error: "exportSequenceFrame returned false" }] }), JSON.stringify(frames.errors));
  assert.ok(frames({ frames: [{ t: 1, tc: "00:00:01:00", file: "D:/f.png", called: true }] }), "the CEP form still validates");
  assert.equal(frames({ frames: [{ t: 1, tc: 7, file: "f.png", called: true }] }), false);
  const ping = getDef("ping", "readback")!;
  assert.ok(ping({ version: "26.5.2", project: "", projects_open: 1 }), JSON.stringify(ping.errors));
  assert.equal(ping({ version: "26.5.2", build: 5, project: "", projects_open: 1 }), false);
  const render = getDef("ae_render", "readback")!;
  const base = { status: "REFUSED", returncode: null, output: "x.mov", elapsed_s: 0, log: null, msg: "sandbox" };
  assert.ok(render(base), JSON.stringify(render.errors));
  assert.equal(render({ ...base, status: "DENIED" }), false);
});

test("C1/C3: the schemas say who owns the codec table and that paths are native (no \\?\ prefix)", () => {
  const text = readFileSync(join(CONTRACT_DIR, "build_project.schema.json"), "utf8");
  assert.match(text, /UXP adapter owns a FourCC <-> display-name table/);
  assert.match(text, /Apple ProRes 422 LT/);
  for (const f of ["open_project", "status", "probe", "ping", "build_project"]) {
    assert.match(JSON.parse(readFileSync(join(CONTRACT_DIR, `${f}.schema.json`), "utf8")) && readFileSync(join(CONTRACT_DIR, `${f}.schema.json`), "utf8"), /native OS path/, f);
  }
  assert.match(String((JSON.parse(readFileSync(join(CONTRACT_DIR, "protocol.json"), "utf8")) as { description: string }).description), /planned/);
});

test("the offline source's results validate as ok:false envelopes (error present, no readback)", async () => {
  const { OfflineSource } = await import("../src/offline-source.ts");
  const src = new OfflineSource({ uiLocale: "ar" });
  for (const a of ACTION_NAMES) assert.deepEqual(validateResult(await src.run(a)), [], a);
});

// ---- golden fixtures ------------------------------------------------------------------------------------------

interface FixtureReport {
  present: boolean;
  /** every .json file found, relative to the fixture folder */
  files: string[];
  /** request/result files that were validated */
  validated: string[];
  problems: string[];
}

function walkJson(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir).sort()) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...walkJson(full));
    else if (name.toLowerCase().endsWith(".json")) out.push(full);
  }
  return out;
}

/**
 * Parses every JSON file under `dir`; a file called request.json (or *.request.json) is a v4 request, result.json (or
 * *.result.json) a v4 result; those are validated, the rest (index.json, cep-data.json, ...) only have to parse.
 * A folder that does not exist yet is reported as absent, not as a failure.
 */
function checkFixtures(dir: string): FixtureReport {
  if (!existsSync(dir)) return { present: false, files: [], validated: [], problems: [] };
  const report: FixtureReport = { present: true, files: [], validated: [], problems: [] };
  for (const file of walkJson(dir)) {
    const rel = relative(dir, file).split("\\").join("/");
    report.files.push(rel);
    let doc: unknown;
    try {
      doc = JSON.parse(readFileSync(file, "utf8"));
    } catch (e) {
      report.problems.push(`${rel}: not valid JSON (${e instanceof Error ? e.message : String(e)})`);
      continue;
    }
    const base = rel.split("/").pop()!.toLowerCase();
    const errs = /(^|\.)request\.json$/.test(base) ? validateRequest(doc) : /(^|\.)result\.json$/.test(base) ? validateResult(doc) : null;
    if (errs === null) continue;
    report.validated.push(rel);
    for (const e of errs) report.problems.push(`${rel}: ${e}`);
  }
  return report;
}

test("fixture check: a folder that does not exist (yet) is reported as absent, with nothing to validate and no problems", () => {
  const missing = join(tmpdir(), `wnc-no-such-fixture-folder-${process.pid}-${Date.now()}`);
  assert.equal(existsSync(missing), false);
  assert.deepEqual(checkFixtures(missing), { present: false, files: [], validated: [], problems: [] });
});

test("fixture check: valid request/result pairs pass, broken ones are reported by file, other JSON only has to parse", () => {
  const dir = mkdtempSync(join(tmpdir(), "wnc-fixtures-"));
  try {
    const put = (rel: string, body: unknown) => {
      const full = join(dir, rel);
      mkdirSync(join(full, ".."), { recursive: true });
      writeFileSync(full, typeof body === "string" ? body : JSON.stringify(body));
    };
    const stamp = "2026-10-12T10:00:00Z";
    put("ping/request.json", { protocol: 4, id: "p1", action: "ping", data: {}, expires_at: stamp });
    put("status/result.json", { ok: true, action: "status", readback: { host: "premiere", hostVersion: "26.5.2", bundle: "3.1.0", protocol: 4, busy: false, project: null } });
    put("open_project/request.json", { protocol: 4, id: "o1", action: "open_project", data: { path: "E:/x/a.prproj" }, expires_at: stamp });
    put("index.json", { open_project: { recorded: false } });
    put("ping/cep-result.json", { anything: "goes" });
    let r = checkFixtures(dir);
    assert.equal(r.present, true);
    assert.deepEqual(r.problems, []);
    assert.deepEqual(r.validated, ["open_project/request.json", "ping/request.json", "status/result.json"]);
    assert.equal(r.files.length, 5);

    put("open_project/request.json", { protocol: 4, id: "o1", action: "open_project", data: { path: 7 }, expires_at: stamp });
    put("status/result.json", { ok: true, action: "status", readback: { host: "premiere", hostVersion: "26.5.2" } });
    put("broken/x.json", "{nope");
    r = checkFixtures(dir);
    assert.ok(r.problems.some((p) => p.startsWith("open_project/request.json: /data")), r.problems.join("\n"));
    assert.ok(r.problems.some((p) => p.startsWith("status/result.json: /readback")), r.problems.join("\n"));
    assert.ok(r.problems.some((p) => p.startsWith("broken/x.json: not valid JSON")), r.problems.join("\n"));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("every fixture under whynot-cut/tests/fixtures/contract/ validates (zero fixtures is fine until that folder exists)", () => {
  const r = checkFixtures(FIXTURE_DIR);
  assert.deepEqual(r.problems, []);
  if (!r.present) {
    assert.deepEqual(r.files, []);
    return;
  }
  // the folder is there: it must hold golden pairs, not just notes
  assert.ok(r.validated.length > 0, "fixtures/contract exists but holds no request.json / result.json");
});

// ---- the panel kit: what MockSource says and what the panel's buttons send ------------------------------------

test("every request the panel's buttons build validates as a v4 request (envelope + the action's data schema)", async () => {
  const expires_at = new Date(Date.now() + 60_000).toISOString();
  for (const scenario of SCENARIOS) {
    const s = await new MockSource({ language: "en", scenario }).snapshot();
    const built = [openProjectAction(s), exportFramesAction(s), renderReviewAction(s), exportFramesAction(s, [1.5])];
    for (const b of built) {
      if (!b) continue; // "idle" has no project yet: the panel shows "missing context" instead of sending
      const errs = validateRequest({ protocol: PROTOCOL, id: "panel-1", action: b.action, data: b.data, expires_at });
      assert.deepEqual(errs, [], `${scenario} ${b.action}`);
    }
  }
  const ar = await new MockSource({ language: "ar", scenario: "qc" }).snapshot();
  const open = openProjectAction(ar)!;
  assert.deepEqual(validateRequest({ protocol: PROTOCOL, id: "panel-2", action: open.action, data: open.data, expires_at }), [], "Arabic client path");
});

test("every v4 result MockSource produces validates (envelope + readback / readback_failure), failures included", async () => {
  const m = new MockSource({ language: "en", scenario: "qc" });
  const s = await m.snapshot();
  const results: Result[] = [
    await m.run("status", {}),
    await m.run("open_project", openProjectAction(s)!.data),
    await m.run("export_frames", exportFramesAction(s)!.data),
    await m.run("render_review", renderReviewAction(s)!.data),
    await m.run("set_player_position", { sequence_name: "EP01_R03_main", t_s: 1.5 }),
    await m.run("build_project", {}),
    await m.run("ae_render", {}),
    await m.rebuild(rebuildInput(s)!),
  ];
  assert.ok(results.some((r) => r.ok) && results.some((r) => !r.ok), "both outcomes are exercised");
  for (const r of results) assert.deepEqual(validateResult(r), [], `${r.action}: ${JSON.stringify(r)}`);
});

test("a result with a readback the schema forbids is caught (the check can fail)", async () => {
  const m = new MockSource({ language: "en", scenario: "qc" });
  const good = await m.run("set_player_position", { sequence_name: "x", t_s: 1 });
  assert.deepEqual(validateResult(good), []);
  assert.notDeepEqual(validateResult({ ...good, readback: { position_s: "soon" } }), []);
  assert.notDeepEqual(validateResult({ ok: true, action: "set_player_position" }), []);
});
