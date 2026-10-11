import { test } from "node:test";
import assert from "node:assert/strict";
import protocol from "../../../whynot-cut/engine/reel/contract/protocol.json" with { type: "json" };
import { ACTION_NAMES, PROTOCOL } from "../src/contract.ts";

test("PROTOCOL comes from protocol.json (one source)", () => {
  assert.equal(PROTOCOL, protocol.protocol);
  assert.equal(PROTOCOL, 4);
});

test("the panel's action list equals protocol.json's, in order", () => {
  assert.deepEqual([...ACTION_NAMES], Object.keys(protocol.actions));
});
