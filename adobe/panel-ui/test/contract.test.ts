import { test } from "node:test";
import assert from "node:assert/strict";
import protocol from "../../../whynot-cut/engine/reel/contract/protocol.json" with { type: "json" };
import { readdirSync, readFileSync } from "node:fs";
import { ACTION_NAMES, ACTIVE_ACTION_NAMES, PROTOCOL, RESERVED_ACTION_NAMES } from "../src/contract.ts";
import type { ExportedFrame, PingPremiereReadback, ResultEnvelope } from "../src/contract.ts";

test("PROTOCOL comes from protocol.json (one source)", () => {
  assert.equal(PROTOCOL, protocol.protocol);
  assert.equal(PROTOCOL, 4);
});

test("the panel's action list equals protocol.json's, in order", () => {
  assert.deepEqual([...ACTION_NAMES], Object.keys(protocol.actions));
});

test("round 4: the active and reserved lists equal protocol.json's status, and the panel exposes no reserved action", () => {
  const entries = Object.entries(protocol.actions as Record<string, { status: string }>);
  assert.deepEqual([...ACTIVE_ACTION_NAMES], entries.filter(([, e]) => e.status === "active").map(([a]) => a));
  assert.deepEqual([...RESERVED_ACTION_NAMES], entries.filter(([, e]) => e.status === "reserved").map(([a]) => a));
  assert.equal(RESERVED_ACTION_NAMES.length, 20);
  assert.equal(ACTIVE_ACTION_NAMES.length + RESERVED_ACTION_NAMES.length, ACTION_NAMES.length);
  const src = new URL("../src/", import.meta.url);
  for (const f of readdirSync(src).filter((n) => n.endsWith(".ts") && n !== "contract.ts")) {
    const text = readFileSync(new URL(f, src), "utf8");
    for (const a of RESERVED_ACTION_NAMES) assert.ok(!text.includes(`"${a}"`), `${f} must not expose ${a} (Phase 6B)`);
  }
});

// The TypeScript mirror of the schemas is checked by the compiler (npm run check): these literals must keep type-checking.
test("the TS types mirror the schema relaxations: a frame without tc, a ping without build, one envelope shape per outcome", () => {
  const frames: ExportedFrame[] = [{ t: 1, file: "D:\f.png", called: true }, { t: 1, tc: "00:00:01:00", file: "f", called: true }, { t: 2, error: "x" }];
  const ping: PingPremiereReadback = { version: "26.5.2", project: "", projects_open: 1 };
  const ok: ResultEnvelope = { ok: true, action: "ping", readback: ping };
  const failed: ResultEnvelope = { ok: false, action: "ping", error: "x", how: "y", readback: { reason: "z" } };
  // @ts-expect-error ok:true carries no error
  const badOk: ResultEnvelope = { ok: true, action: "ping", readback: {}, error: "x" };
  // @ts-expect-error ok:false needs an error
  const badFail: ResultEnvelope = { ok: false, action: "ping" };
  assert.equal(frames.length + (ok.ok ? 1 : 0) + (failed.ok ? 0 : 1) + (badOk ? 0 : 1) + (badFail ? 0 : 1), 5);
});
