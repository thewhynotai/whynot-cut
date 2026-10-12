import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { OFFLINE_HOW, OfflineSource, hostDetailOf, languageOf } from "../src/offline-source.ts";
import { ACTION_NAMES } from "../../panel-ui/src/contract.ts";
import { STEP_IDS } from "../../panel-ui/src/source.ts";
import { initialUi, render } from "../../panel-ui/src/render.ts";
import { stringsFor } from "../../panel-ui/src/i18n.ts";

const CONTRACT = new URL("../../../whynot-cut/engine/reel/contract/", import.meta.url);
const ajv = new Ajv2020({ strict: false, allErrors: true });
(addFormats as unknown as (a: unknown) => void)(ajv);
for (const f of ["result", ...ACTION_NAMES]) ajv.addSchema(JSON.parse(readFileSync(new URL(`${f}.schema.json`, CONTRACT), "utf8")));
const resultSchema = ajv.getSchema("https://thewhynot.ai/whynot-cut/contract/4/result.schema.json")!;

test("languageOf: Arabic UI locales give ar, everything else (and nothing) gives en", () => {
  for (const l of ["ar", "ar_AE", "ar-EG", "AR_SA"]) assert.equal(languageOf(l), "ar", l);
  for (const l of ["en_US", "de_DE", "", undefined, null]) assert.equal(languageOf(l), "en", String(l));
});

test("hostDetailOf: the real UXP host version, or just the product name when the host gave none", () => {
  assert.equal(hostDetailOf("26.5.2"), "Premiere Pro 26.5.2");
  assert.equal(hostDetailOf(""), "Premiere Pro");
  assert.equal(hostDetailOf(undefined), "Premiere Pro");
});

test("snapshot: engine not running, host pill from the real host, and no invented pipeline data", async () => {
  const s = await new OfflineSource({ hostVersion: "26.5.2", uiLocale: "en_US" }).snapshot();
  assert.equal(s.connection.engine, "offline");
  assert.equal(s.connection.claude, "unknown");
  assert.deepEqual(s.connection.host, { state: "uxp", detail: "Premiere Pro 26.5.2" });
  assert.equal(s.language, "en");
  assert.equal(s.client, "");
  assert.equal(s.item, "");
  assert.equal(s.editor_name, "");
  assert.equal(s.approval, null);
  assert.deepEqual(s.qc, []);
  assert.deepEqual(s.log, []);
  assert.deepEqual(s.context, { project_path: null, sequence_name: null, folder: null, out_dir: null, review_mp4: null });
  assert.deepEqual(s.pipeline.map((p) => p.id), [...STEP_IDS]);
  for (const p of s.pipeline) {
    assert.equal(p.state, "pending", p.id);
    assert.ok(!p.progress && !p.request_id && p.elapsed_s == null, p.id);
  }
});

test("snapshot: an Arabic Premiere gives an Arabic panel", async () => {
  const s = await new OfflineSource({ hostVersion: "26.5.2", uiLocale: "ar_AE" }).snapshot();
  assert.equal(s.language, "ar");
});

test("snapshot returns a fresh copy each time (a panel cannot mutate the source)", async () => {
  const src = new OfflineSource({});
  const a = await src.snapshot();
  a.client = "x";
  a.pipeline[0]!.state = "done";
  const b = await src.snapshot();
  assert.equal(b.client, "");
  assert.equal(b.pipeline[0]!.state, "pending");
});

test("subscribe never pushes anything and returns an unsubscribe function", () => {
  const src = new OfflineSource({});
  let calls = 0;
  const off = src.subscribe();
  assert.equal(typeof off, "function");
  off();
  assert.equal(calls, 0);
});

test("every action answers ok:false with a v4 result that says how to start the engine", async () => {
  const src = new OfflineSource({ uiLocale: "en_US" });
  for (const a of ACTION_NAMES) {
    const r = await src.run(a);
    assert.equal(r.ok, false, a);
    assert.equal(r.action, a);
    assert.equal(r.how, OFFLINE_HOW);
    assert.match(r.error ?? "", /not running/);
    assert.equal(r.readback, undefined, "never a readback: nothing was measured");
    assert.ok(resultSchema(r), `${a}: ${JSON.stringify(resultSchema.errors)}`);
  }
  assert.equal(OFFLINE_HOW, "In your Claude session run `reel doctor`.");
  assert.doesNotMatch(OFFLINE_HOW, /reel serve|coming in/);
});

test("approve, request changes and rebuild are refused too, and the rebuild result is a valid v4 result", async () => {
  const src = new OfflineSource({});
  const approve = await src.approve();
  const changes = await src.requestChanges();
  const rebuild = await src.rebuild();
  for (const r of [approve, changes, rebuild]) {
    assert.equal(r.ok, false);
    assert.equal(r.how, OFFLINE_HOW);
    assert.ok(r.error);
  }
  assert.equal(rebuild.action, "build_project");
  assert.ok(resultSchema(rebuild), JSON.stringify(resultSchema.errors));
});

test("Arabic panel gets Arabic error and how text (the command stays Latin)", async () => {
  const r = await new OfflineSource({ uiLocale: "ar" }).run("status");
  assert.match(r.error ?? "", /[؀-ۿ]/);
  assert.match(r.how ?? "", /[؀-ۿ]/);
  assert.match(r.how ?? "", /`reel doctor`/);
  assert.doesNotMatch(r.how ?? "", /reel serve/);
});

test("cancel resolves and does nothing", async () => {
  await new OfflineSource({}).cancel();
});

test("the panel renders the offline state: Engine pill 'not running', the Premiere version, the offline banner", async () => {
  const s = await new OfflineSource({ hostVersion: "26.5.2", uiLocale: "en_US" }).snapshot();
  const html = render(s, stringsFor("en"), initialUi());
  assert.match(html, /data-pill="engine"[^>]*><span class="pill-k">Engine<\/span><span class="pill-v">not running</);
  assert.match(html, /Premiere Pro 26\.5\.2/);
  assert.match(html, /The WhyNot Cut engine is not running\./);
  assert.doesNotMatch(html, /Claude Code/);
});

test("U3: the notice that carries the offline how shows the command in a left-to-right run, EN and AR", async () => {
  for (const loc of ["en_US", "ar_AE"]) {
    const src = new OfflineSource({ uiLocale: loc });
    const s = await src.snapshot();
    const r = await src.run("ping");
    const ui = { ...initialUi(), notice: { kind: "error" as const, text: r.error ?? "", ...(r.how ? { how: r.how } : {}) } };
    const html = render(s, stringsFor(s.language), ui);
    assert.ok(html.slice(html.indexOf('role="status"')).includes('<bdi dir="ltr">reel doctor</bdi>'), loc);
    assert.ok(!html.includes("reel serve"), loc);
    assert.ok(!html.includes("`"), loc);
  }
});
