import { test } from "node:test";
import assert from "node:assert/strict";
import { diagnosticsText } from "../src/diagnostics.ts";
import { sampleState } from "../src/mock.ts";

test("U4: diagnostics copy only named, non-secret fields of connection and context; a port, token or ws URL never gets in", () => {
  const s = sampleState("en", "qc");
  const secretConnection = {
    ...s.connection,
    token: "SECRET-TOKEN-1",
    ws_url: "ws://127.0.0.1:58231/secret",
    port: 58231,
    host: { ...s.connection.host, token: "SECRET-TOKEN-2", url: "ws://127.0.0.1:58231" },
  };
  const secretContext = { ...s.context, token: "SECRET-TOKEN-3", ws_url: "ws://127.0.0.1:1", port: 9 };
  const text = diagnosticsText({ ...s, connection: secretConnection, context: secretContext } as never);
  for (const leak of ["SECRET-TOKEN", "ws://", "58231", '"ws_url"', '"port"', '"token"', '"url"']) assert.ok(!text.includes(leak), `leaked: ${leak}`);
  const d = JSON.parse(text) as { connection: Record<string, unknown>; context: Record<string, unknown> };
  assert.deepEqual(Object.keys(d.connection).sort(), ["claude", "engine", "host"]);
  assert.deepEqual(Object.keys(d.connection.host as object).sort(), ["detail", "state"]);
  assert.deepEqual(Object.keys(d.context).sort(), ["folder", "out_dir", "project_path", "review_mp4", "sequence_name"]);
  assert.equal(d.connection.engine, s.connection.engine);
  assert.equal(d.context.project_path, s.context.project_path);
});

test("U4: a state with no connection or context still gives text, not an exception", () => {
  const s = sampleState("en", "idle");
  assert.doesNotThrow(() => diagnosticsText({ ...s, connection: null, context: undefined } as never));
});

test("M8: diagnostics name the plugin version and its build stamp (a same-version rebuild is told apart); without them nothing changes", () => {
  const s = sampleState("en", "idle");
  const d = JSON.parse(diagnosticsText(s, { version: "3.0.0", build: "61b12aa 2026-10-12T18:40Z" })) as Record<string, unknown>;
  assert.deepEqual(d["plugin"], { version: "3.0.0", build: "61b12aa 2026-10-12T18:40Z" });
  const plain = JSON.parse(diagnosticsText(s)) as Record<string, unknown>;
  assert.ok(!("plugin" in plain));
});
