// The daemon-link session messages (whynot-cut/engine/reel/contract/session.schema.json) and their TypeScript mirror
// (src/session.ts): typed samples must validate with ajv (strict), the panel states MockSource produces must validate as
// `panel_state`, and bad messages must not. Python's twin is test_contract.py SessionContractTests.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { PROTOCOL } from "../src/contract.ts";
import { SESSION_ERROR_CODES, SESSION_MESSAGE_TYPES } from "../src/session.ts";
import type { SessionMessage } from "../src/session.ts";
import { SCENARIOS, sampleState } from "../src/mock.ts";

const CONTRACT = new URL("../../../whynot-cut/engine/reel/contract/", import.meta.url);
const ajv = new Ajv2020({ strictSchema: true, strictTypes: false, strictRequired: false, strictTuples: false, allErrors: true });
(addFormats as unknown as (a: unknown) => void)(ajv);
type Schema = { $id: string; $defs?: Record<string, { oneOf?: { $ref: string }[]; properties?: Record<string, { enum?: string[] }> }> };
const load = (name: string) => {
  const schema = JSON.parse(readFileSync(new URL(`${name}.schema.json`, CONTRACT), "utf8")) as Schema;
  ajv.addSchema(schema);
  return schema;
};
for (const name of ["request", "result", "progress"]) load(name);
const session = load("session");
const message = ajv.getSchema(session.$id)!;
const def = (name: string) => ajv.getSchema(`${session.$id}#/$defs/${name}`)!;

const request = { protocol: PROTOCOL, id: "r-1", action: "ping", data: {}, expires_at: "2026-10-12T10:00:00Z" } as const;
const SAMPLES: SessionMessage[] = [
  { type: "hello", token: "ab".repeat(32), client: { kind: "uxp", version: "3.0.0", host: "premiere", hostVersion: "26.5.2", protocol: 4, capabilities: ["ping", "status"] } },
  { type: "hello", token: "ab".repeat(32), client: { kind: "cli", version: "3.0.0", protocol: 4, capabilities: [] } },
  { type: "welcome", session_id: "s-1", protocol: 4, daemon_version: "3.0.0" },
  { type: "command", request, context: { root: "D:/c", profile: "nour" } },
  { type: "command", request },
  { type: "result", result: { ok: true, action: "ping", readback: { version: "26.5.2", project: null, projects_open: 1 }, id: "r-1" } },
  { type: "result", result: { ok: false, action: "ping", error: "x", how: "y" } },
  { type: "progress", progress: { event: "progress", id: "r-1", action: "build_project", step: "tracks", n: 1, of: 4 } },
  { type: "state", state: sampleState("en", "showcase"), id: "p-1" },
  { type: "approve", id: "p-2", item: "C0239", editor_name: "Yunus", fingerprint: "abc" },
  { type: "request_changes", id: "p-3", item: "C0239", editor_name: "Yunus", text: "shorter" },
  { type: "rebuild", id: "p-4", item: "C0239", project_path: "D:/p.prproj", replace_edited: false },
  { type: "snapshot" },
  { type: "snapshot", id: "p-5" },
  { type: "cancel", id: "r-1" },
  { type: "reply", id: "p-2", intent: "approve", ok: true, readback: { approved: true } },
  { type: "reply", id: "p-3", intent: "rebuild", ok: false, error: "x", how: "y" },
  { type: "error", code: "schema", message: "bad", id: "r-9" },
  { type: "error", code: "auth", message: "no" },
];

test("session.schema.json compiles under ajv strict, and its message oneOf lists every type the TS mirror knows, in order", () => {
  assert.equal(typeof message, "function");
  const refs = session.$defs!.message!.oneOf!.map((b) => b.$ref.replace("#/$defs/", ""));
  assert.deepEqual(refs, [...SESSION_MESSAGE_TYPES]);
  for (const t of SESSION_MESSAGE_TYPES) assert.ok(def(t), t);
  assert.deepEqual(session.$defs!.error!.properties!.code!.enum, [...SESSION_ERROR_CODES]);
});

test("every typed sample validates (as the message and as its own def), and every type has a sample", () => {
  for (const m of SAMPLES) {
    assert.ok(message(m), `${m.type}: ${JSON.stringify(message.errors)}`);
    assert.ok(def(m.type)(m), `${m.type}: ${JSON.stringify(def(m.type).errors)}`);
  }
  assert.deepEqual([...new Set(SAMPLES.map((m) => m.type))].sort(), [...SESSION_MESSAGE_TYPES].sort());
});

test("every panel state MockSource can produce (all scenarios, EN and AR) validates as panel_state", () => {
  const v = def("panel_state");
  for (const language of ["en", "ar"] as const) {
    for (const scenario of SCENARIOS) assert.ok(v(sampleState(language, scenario)), `${language}/${scenario}: ${JSON.stringify(v.errors)}`);
  }
});

test("bad messages are rejected: wrong protocol or missing token in hello, unknown type, extra keys, a bad embedded request", () => {
  const hello = SAMPLES[0] as Extract<SessionMessage, { type: "hello" }>;
  const bad: unknown[] = [
    { ...hello, client: { ...hello.client, protocol: 3 } },
    { ...hello, client: { ...hello.client, protocol: 5 } },
    { type: "hello", client: hello.client },
    { ...hello, token: "" },
    { ...hello, extra: 1 },
    { type: "run_script", code: "1+1" },
    { type: "command", request: { ...request, action: "run_script" } },
    { type: "command", request: { ...request, protocol: 3 } },
    { type: "result", result: { ok: true, action: "ping" } },
    { type: "progress", progress: { event: "progress", id: "r", action: "ping" } },
    { type: "error", code: "oops", message: "m" },
    { type: "cancel" },
    { type: "approve", id: "p", item: "x", editor_name: "y" },
    { type: "reply", id: "p", intent: "run", ok: true },
    { type: "reply", id: "p", intent: "approve", ok: true, error: "x" },
    {},
    [],
    "hello",
  ];
  for (const b of bad) assert.equal(message(b), false, JSON.stringify(b));
});

// The compiler checks the mirror: these must NOT type-check (npm run check).
test("the TS mirror is closed: a hello without a token, a state without a PanelState, a wrong error code do not compile", () => {
  // @ts-expect-error token is required
  const noToken: SessionMessage = { type: "hello", client: { kind: "cli", version: "3", protocol: 4, capabilities: [] } };
  // @ts-expect-error protocol is the literal 4
  const oldProto: SessionMessage = { type: "welcome", session_id: "s", protocol: 3, daemon_version: "3" };
  // @ts-expect-error unknown error code
  const badCode: SessionMessage = { type: "error", code: "oops", message: "m" };
  // @ts-expect-error reply ok:true carries no error
  const badReply: SessionMessage = { type: "reply", id: "p", intent: "approve", ok: true, error: "x" };
  assert.equal([noToken, oldProto, badCode, badReply].length, 4);
});
