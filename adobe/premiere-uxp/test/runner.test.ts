import { test } from "node:test";
import assert from "node:assert/strict";
import { jsonSafe, runAll, runProbe, type ProbeDef } from "../spike/src/runner.ts";

const ctx = {};

test("runProbe records ok, ms and detail", async () => {
  let t = 1000;
  const def: ProbeDef<object> = { op: "fine", run: async () => ({ ok: true, detail: { a: 1 } }) };
  const r = await runProbe(def, ctx, () => (t += 7));
  assert.equal(r.op, "fine");
  assert.equal(r.ok, true);
  assert.equal(r.ms, 7);
  assert.deepEqual(r.detail, { a: 1 });
  assert.equal(r.error, null);
});

test("runProbe never throws: a throwing probe is ok:false with message and stack", async () => {
  const def: ProbeDef<object> = {
    op: "boom",
    run: async () => {
      throw new Error("kaput");
    },
  };
  const r = await runProbe(def, ctx);
  assert.equal(r.ok, false);
  assert.equal(r.error, "kaput");
  assert.match(r.stack ?? "", /kaput/);
});

test("runProbe survives a synchronous throw and a non-Error rejection", async () => {
  const sync: ProbeDef<object> = {
    op: "sync",
    run: () => {
      throw new TypeError("sync bad");
    },
  };
  assert.equal((await runProbe(sync, ctx)).error, "sync bad");
  const odd: ProbeDef<object> = { op: "odd", run: () => Promise.reject("plain string") };
  const r = await runProbe(odd, ctx);
  assert.equal(r.ok, false);
  assert.equal(r.error, "plain string");
});

test("runProbe times out a probe that never settles", async () => {
  const def: ProbeDef<object> = { op: "hang", timeoutMs: 30, run: () => new Promise(() => {}) };
  const r = await runProbe(def, ctx);
  assert.equal(r.ok, false);
  assert.match(r.error ?? "", /timed out after 30 ms/);
});

test("ok:null (pending/skipped) is kept as null", async () => {
  const def: ProbeDef<object> = { op: "pending", run: async () => ({ ok: null, detail: "pending reel serve (T6.2)" }) };
  const r = await runProbe(def, ctx);
  assert.equal(r.ok, null);
  assert.equal(r.detail, "pending reel serve (T6.2)");
});

test("runAll runs probes in order, keeps going after a failure, reports progress", async () => {
  const seen: string[] = [];
  const defs: ProbeDef<object>[] = [
    { op: "a", run: async () => ({ ok: true, detail: 1 }) },
    {
      op: "b",
      run: async () => {
        throw new Error("b failed");
      },
    },
    { op: "c", run: async () => ({ ok: true, detail: 3 }) },
  ];
  const ops = await runAll(defs, ctx, (done) => {
    seen.push(done.op);
  });
  assert.deepEqual(
    ops.map((o) => [o.op, o.ok]),
    [
      ["a", true],
      ["b", false],
      ["c", true],
    ],
  );
  assert.deepEqual(seen, ["a", "b", "c"]);
});

test("a throwing progress callback does not abort the run", async () => {
  const defs: ProbeDef<object>[] = [
    { op: "a", run: async () => ({ ok: true, detail: null }) },
    { op: "b", run: async () => ({ ok: true, detail: null }) },
  ];
  const ops = await runAll(defs, ctx, () => {
    throw new Error("disk full");
  });
  assert.equal(ops.length, 2);
});

test("jsonSafe makes cyclic / exotic details serialisable", () => {
  const cyc: Record<string, unknown> = { n: 1 };
  cyc.self = cyc;
  const out = jsonSafe({ cyc, big: 10n, fn: () => 1, undef: undefined });
  assert.doesNotThrow(() => JSON.stringify(out));
  assert.equal((out as { big: string }).big, "10");
});
