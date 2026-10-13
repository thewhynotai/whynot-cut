// Spike 0.1.5: hands-free auto-run. A run-request.json in ~/.whynot-cut/uxp-spike starts the spike when the panel
// is open; Claude then reads run-done-<id>.json + the results file. Fake fs (the measured UXP surface: sync calls
// only, optionally without rename/unlink) and a fake clock - nothing here touches a real disk or timer.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createAutoRunner, POLL_MS, STALE_MS, type AutoRunDeps, type RunMode, type RunSummary } from "../spike/src/autorun.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const DIR = "C:/Users/LOQ/.whynot-cut/uxp-spike";
const T0 = Date.parse("2026-10-12T12:00:00.000Z");
const iso = (ms: number) => new Date(ms).toISOString();

/** UXP-shaped fs: only the *Sync twins (the measured surface). rename / unlink can be taken away. */
function memFs(opts: { rename?: boolean; unlink?: boolean; initial?: Record<string, string> } = {}) {
  const files = new Map<string, string>(Object.entries(opts.initial ?? {}));
  const fs: Record<string, unknown> = {
    files,
    readFileSync: (p: string) => {
      const v = files.get(p);
      if (v === undefined) throw new Error(`ENOENT: ${p}`);
      return v;
    },
    writeFileSync: (p: string, data: string) => void files.set(p, data),
    lstatSync: (p: string) => {
      const v = files.get(p);
      if (v === undefined) throw new Error(`ENOENT: ${p}`);
      return { size: v.length, isDirectory: () => false };
    },
  };
  if (opts.rename !== false) {
    fs.renameSync = (from: string, to: string) => {
      const v = files.get(from);
      if (v === undefined) throw new Error(`ENOENT: ${from}`);
      files.delete(from);
      files.set(to, v);
    };
  }
  if (opts.unlink !== false) {
    fs.unlinkSync = (p: string) => {
      if (!files.delete(p)) throw new Error(`ENOENT: ${p}`);
    };
  }
  return fs as Record<string, unknown> & { files: Map<string, string> };
}

const REQ = `${DIR}/run-request.json`;
const request = (id: string, mode: RunMode | string = "full", requestedAt = iso(T0 - 1000)) => JSON.stringify({ id, mode, requested_at: requestedAt });

function harness(fsOpts: Parameters<typeof memFs>[0] = {}, over: Partial<AutoRunDeps> = {}) {
  const fs = memFs(fsOpts);
  const clock = { t: T0 };
  const runs: Array<{ id: string; mode: RunMode }> = [];
  const statuses: string[] = [];
  const lock = { held: false, taken: 0, heldDuringRun: [] as boolean[] };
  const summary: RunSummary = { results_file: `${DIR}/results-20261012-120000.json`, ok: true, pass: 20, fail: 2, na: 3 };
  const deps: AutoRunDeps = {
    fs: fs as AutoRunDeps["fs"],
    dir: DIR,
    now: () => clock.t,
    isBusy: () => false,
    tryLock: () => {
      if (lock.held) return false;
      lock.held = true;
      lock.taken++;
      return true;
    },
    unlock: () => void (lock.held = false),
    run: async (mode, id) => {
      lock.heldDuringRun.push(lock.held);
      runs.push({ id, mode });
      clock.t += 4000; // the run takes 4 s
      return summary;
    },
    setStatus: (t) => void statuses.push(t),
    schedule: () => () => {},
    ...over,
  };
  return { fs, clock, runs, statuses, deps, lock, runner: createAutoRunner(deps), summary };
}

const names = (fs: { files: Map<string, string> }) => [...fs.files.keys()].map((k) => k.slice(DIR.length + 1)).sort();

// ---- nothing to do -----------------------------------------------------------------------------------------------

test("no request file: nothing runs, nothing is written, the status line is left alone", async () => {
  const h = harness();
  assert.deepEqual(await h.runner.poll(), { kind: "none" });
  assert.equal(h.runs.length, 0);
  assert.deepEqual(names(h.fs), []);
  assert.deepEqual(h.statuses, []);
});

// ---- claim once --------------------------------------------------------------------------------------------------

test("a request is claimed by renaming it, run once in the requested mode, and a done file is written", async () => {
  const h = harness({ initial: { [REQ]: request("job-1", "full") } });
  const out = await h.runner.poll();
  assert.equal(out.kind, "ran");
  assert.deepEqual(h.runs, [{ id: "job-1", mode: "full" }]);
  assert.equal(h.fs.files.has(REQ), false, "the request is gone");
  assert.equal(h.fs.files.has(`${DIR}/run-request.job-1.claimed`), true);
  // a second poll with nothing new does nothing
  assert.deepEqual(await h.runner.poll(), { kind: "none" });
  assert.equal(h.runs.length, 1);
});

test("keep_open mode is passed through", async () => {
  const h = harness({ initial: { [REQ]: request("k1", "keep_open") } });
  await h.runner.poll();
  assert.deepEqual(h.runs, [{ id: "k1", mode: "keep_open" }]);
});

test("the same id is never run twice: a request file that comes back (same id) is moved aside, not run", async () => {
  const h = harness({ initial: { [REQ]: request("same") } });
  await h.runner.poll();
  h.fs.files.set(REQ, request("same"));
  const again = await h.runner.poll();
  assert.equal(again.kind, "duplicate");
  assert.equal(h.runs.length, 1);
  assert.equal(h.fs.files.has(REQ), false);
  assert.equal(h.fs.files.has(`${DIR}/run-request.same.duplicate`), true);
});

test("the same id is not run again after a panel reload: the claim / done files on disk are the memory", async () => {
  const h = harness({ initial: { [REQ]: request("reload"), [`${DIR}/run-done-reload.json`]: "{}" } });
  assert.equal((await h.runner.poll()).kind, "duplicate");
  assert.equal(h.runs.length, 0);
  const h2 = harness({ initial: { [REQ]: request("reload2"), [`${DIR}/run-request.reload2.claimed`]: "{}" } });
  assert.equal((await h2.runner.poll()).kind, "duplicate");
  assert.equal(h2.runs.length, 0);
  const h3 = harness({ initial: { [REQ]: request("reload3"), [`${DIR}/run-claimed-reload3.json`]: "{}" } });
  assert.equal((await h3.runner.poll()).kind, "duplicate");
  assert.equal(h3.runs.length, 0);
});

test("two requests with different ids both run, one after the other", async () => {
  const h = harness({ initial: { [REQ]: request("a1", "full") } });
  await h.runner.poll();
  h.fs.files.set(REQ, request("b2", "keep_open", iso(h.clock.t - 500)));
  const second = await h.runner.poll();
  assert.equal(second.kind, "ran");
  assert.deepEqual(h.runs, [
    { id: "a1", mode: "full" },
    { id: "b2", mode: "keep_open" },
  ]);
  assert.equal(h.fs.files.has(`${DIR}/run-done-a1.json`), true);
  assert.equal(h.fs.files.has(`${DIR}/run-done-b2.json`), true);
  assert.equal(h.fs.files.has(`${DIR}/run-request.a1.claimed`), true);
  assert.equal(h.fs.files.has(`${DIR}/run-request.b2.claimed`), true);
});

test("no rename in this UXP build: the claim is run-claimed-<id>.json and the request is deleted", async () => {
  const h = harness({ rename: false, initial: { [REQ]: request("w1") } });
  await h.runner.poll();
  assert.equal(h.runs.length, 1);
  assert.equal(h.fs.files.has(REQ), false);
  const claim = JSON.parse(h.fs.files.get(`${DIR}/run-claimed-w1.json`) ?? "null");
  assert.equal(claim.id, "w1");
  assert.deepEqual(await h.runner.poll(), { kind: "none" });
});

test("neither rename nor delete: the claim file still stops a re-run, quietly, on every later poll", async () => {
  const h = harness({ rename: false, unlink: false, initial: { [REQ]: request("stuck") } });
  await h.runner.poll();
  assert.equal(h.runs.length, 1);
  assert.equal(h.fs.files.has(REQ), true, "the request cannot be removed here");
  for (let i = 0; i < 3; i++) assert.equal((await h.runner.poll()).kind, "duplicate");
  assert.equal(h.runs.length, 1);
  // and a NEW id written over it still runs
  h.fs.files.set(REQ, request("fresh", "full", iso(h.clock.t)));
  assert.equal((await h.runner.poll()).kind, "ran");
  assert.equal(h.runs.length, 2);
});

test("a claim that cannot be recorded at all means the spike does not run (never a risk of a loop)", async () => {
  const h = harness({ rename: false, initial: { [REQ]: request("noclaim") } });
  h.fs.writeFileSync = () => {
    throw new Error("disk full");
  };
  const out = await h.runner.poll();
  assert.equal(out.kind, "claim_failed");
  assert.equal(h.runs.length, 0);
  assert.match(h.statuses.at(-1) ?? "", /Auto-run noclaim .*could not claim/);
  assert.equal((await h.runner.poll()).kind, "claim_failed"); // still not run
  assert.equal(h.runs.length, 0);
});

// ---- stale -------------------------------------------------------------------------------------------------------

test("a request older than 30 minutes is not run and is moved to run-request.<id>.stale", async () => {
  const h = harness({ initial: { [REQ]: request("old", "full", iso(T0 - STALE_MS - 1)) } });
  const out = await h.runner.poll();
  assert.deepEqual(out, { kind: "stale", id: "old" });
  assert.equal(h.runs.length, 0);
  assert.equal(h.fs.files.has(REQ), false);
  assert.equal(h.fs.files.has(`${DIR}/run-request.old.stale`), true);
  assert.match(h.statuses.at(-1) ?? "", /Auto-run old .*stale/);
});

test("exactly 30 minutes old still runs; a request dated in the future (clock skew) runs too", async () => {
  const h = harness({ initial: { [REQ]: request("edge", "full", iso(T0 - STALE_MS)) } });
  assert.equal((await h.runner.poll()).kind, "ran");
  const h2 = harness({ initial: { [REQ]: request("future", "full", iso(T0 + 60_000)) } });
  assert.equal((await h2.runner.poll()).kind, "ran");
});

// ---- malformed ---------------------------------------------------------------------------------------------------

test("valid JSON with a bad shape (no id / bad mode / bad date / unsafe id) is moved aside at once with an error file, no run, no throw", async () => {
  const bad = [
    JSON.stringify({ mode: "full", requested_at: iso(T0) }),
    JSON.stringify({ id: "x1", mode: "everything", requested_at: iso(T0) }),
    JSON.stringify({ id: "x2", mode: "full", requested_at: "yesterday-ish" }),
    JSON.stringify({ id: "../evil", mode: "full", requested_at: iso(T0) }),
    JSON.stringify({ id: 7, mode: "full", requested_at: iso(T0) }),
    "[]",
    "null",
    '"text"',
  ];
  for (const text of bad) {
    const h = harness({ initial: { [REQ]: text } });
    const out = await h.runner.poll();
    assert.equal(out.kind, "malformed", text);
    assert.equal(h.runs.length, 0);
    assert.equal(h.fs.files.has(REQ), false, `${text} not moved aside`);
    const listing = names(h.fs);
    const errFile = listing.find((n) => n.startsWith("run-error-"));
    assert.ok(errFile, `no error file for ${text}`);
    const err = JSON.parse(h.fs.files.get(`${DIR}/${errFile}`) ?? "null");
    assert.equal(typeof err.error, "string");
    assert.ok(listing.some((n) => n.startsWith("run-request.bad-")), "the bad request is kept for inspection");
    assert.match(h.statuses.at(-1) ?? "", /Auto-run .*malformed/);
  }
});

test("not JSON at all (maybe a half-written file): left alone on the first poll, moved aside when the same text is still there on the next", async () => {
  const h = harness({ initial: { [REQ]: '{"id": "half", "mo' } });
  assert.deepEqual(await h.runner.poll(), { kind: "waiting" });
  assert.equal(h.fs.files.has(REQ), true);
  assert.equal(h.runs.length, 0);
  // the writer finishes: it is now valid and runs
  h.fs.files.set(REQ, request("half"));
  assert.equal((await h.runner.poll()).kind, "ran");

  const h2 = harness({ initial: { [REQ]: "not json {" } });
  await h2.runner.poll();
  const out = await h2.runner.poll();
  assert.equal(out.kind, "malformed");
  assert.equal(h2.fs.files.has(REQ), false);
  assert.ok(names(h2.fs).some((n) => n.startsWith("run-error-")));
  assert.equal(h2.runs.length, 0);
});

test("a malformed request that cannot be moved is reported once, not on every poll, and never crashes", async () => {
  const h = harness({ rename: false, unlink: false, initial: { [REQ]: '{"id":1}' } });
  assert.equal((await h.runner.poll()).kind, "malformed");
  const writes = h.fs.files.size;
  for (let i = 0; i < 3; i++) assert.equal((await h.runner.poll()).kind, "none");
  assert.equal(h.fs.files.size, writes);
});

test("a throwing fs never escapes poll()", async () => {
  const h = harness({ initial: { [REQ]: request("e1") } });
  h.fs.lstatSync = () => {
    throw new Error("EIO");
  };
  assert.deepEqual(await h.runner.poll(), { kind: "none" });
  h.fs.lstatSync = (p: string) => ({ size: 1, isDirectory: () => false, p });
  h.fs.readFileSync = () => {
    throw new Error("EACCES");
  };
  const out = await h.runner.poll();
  assert.ok(out.kind === "none" || out.kind === "error");
  assert.equal(h.runs.length, 0);
});

// ---- the run + the done file -------------------------------------------------------------------------------------

test("run-done-<id>.json holds id, mode (0.1.6), results_file, ok, pass, fail, na, started_at, finished_at (the run's own clock)", async () => {
  const h = harness({ initial: { [REQ]: request("done1") } });
  await h.runner.poll();
  const done = JSON.parse(h.fs.files.get(`${DIR}/run-done-done1.json`) ?? "null");
  assert.deepEqual(done, {
    id: "done1",
    mode: "full",
    results_file: `${DIR}/results-20261012-120000.json`,
    ok: true,
    pass: 20,
    fail: 2,
    na: 3,
    started_at: iso(T0),
    finished_at: iso(T0 + 4000),
  });
  assert.equal(h.fs.files.has(`${DIR}/run-done-done1.json.tmp`), false, "no temp file left behind");
});

test("a spike that could not start still gets a done file: ok false, results_file null, the error", async () => {
  const h = harness(
    { initial: { [REQ]: request("dead") } },
    { run: async () => ({ results_file: null, ok: false, pass: 0, fail: 0, na: 0, error: "Spike could not start: no premierepro" }) },
  );
  await h.runner.poll();
  const done = JSON.parse(h.fs.files.get(`${DIR}/run-done-dead.json`) ?? "null");
  assert.equal(done.ok, false);
  assert.equal(done.results_file, null);
  assert.equal(done.error, "Spike could not start: no premierepro");
});

test("a run() that throws is caught: done file with ok false and the message; poll() resolves", async () => {
  const h = harness(
    { initial: { [REQ]: request("boom") } },
    {
      run: async () => {
        throw new Error("kaput");
      },
    },
  );
  const out = await h.runner.poll();
  assert.equal(out.kind, "ran");
  const done = JSON.parse(h.fs.files.get(`${DIR}/run-done-boom.json`) ?? "null");
  assert.equal(done.ok, false);
  assert.match(done.error, /kaput/);
});

test("a done file written without rename (direct write) is still complete JSON", async () => {
  const h = harness({ rename: false, initial: { [REQ]: request("nor") } });
  await h.runner.poll();
  assert.equal(JSON.parse(h.fs.files.get(`${DIR}/run-done-nor.json`) ?? "null").id, "nor");
});

test("while a manual run is in progress nothing is read or claimed; the request waits for the next poll", async () => {
  let busy = true;
  const h = harness({ initial: { [REQ]: request("wait") } }, { isBusy: () => busy });
  assert.deepEqual(await h.runner.poll(), { kind: "busy" });
  assert.equal(h.fs.files.has(REQ), true);
  busy = false;
  assert.equal((await h.runner.poll()).kind, "ran");
});

test("two polls at once cannot run the same request twice (re-entrancy guard)", async () => {
  const h = harness({ initial: { [REQ]: request("par") } });
  const [a, b] = await Promise.all([h.runner.poll(), h.runner.poll()]);
  assert.equal(h.runs.length, 1);
  assert.deepEqual([a.kind, b.kind].sort(), ["busy", "ran"]);
});

test("the status line says Auto-run <id> ... while it claims, runs and when it ends", async () => {
  const h = harness({ initial: { [REQ]: request("st1") } });
  await h.runner.poll();
  assert.match(h.statuses[0] ?? "", /^Auto-run st1 /);
  assert.ok(h.statuses.every((s) => s.startsWith("Auto-run st1")), h.statuses.join(" | "));
  assert.match(h.statuses.at(-1) ?? "", /done: 20 pass, 2 fail, 3 n\/a/);
});

// ---- BOM (Windows PowerShell 5.1 writes UTF-8 with a BOM) -------------------------------------------------------

test("a request file that starts with a UTF-8 BOM (PowerShell 5.1) parses and runs", async () => {
  const h = harness({ initial: { [REQ]: "﻿" + request("bom1", "keep_open") } });
  const out = await h.runner.poll();
  assert.equal(out.kind, "ran");
  assert.deepEqual(h.runs, [{ id: "bom1", mode: "keep_open" }]);
});

test("a BOM does not hide a real problem: BOM + bad shape is malformed, BOM + half a file waits then is malformed", async () => {
  const h = harness({ initial: { [REQ]: "﻿" + JSON.stringify({ id: "b2", mode: "nope", requested_at: iso(T0) }) } });
  assert.equal((await h.runner.poll()).kind, "malformed");
  const h2 = harness({ initial: { [REQ]: "﻿{\"id\": " } });
  assert.equal((await h2.runner.poll()).kind, "waiting");
  assert.equal((await h2.runner.poll()).kind, "malformed");
  assert.equal(h2.runs.length, 0);
});

// ---- the manual-click race ---------------------------------------------------------------------------------------

test("the run lock is taken BEFORE the claim and held through the run and the done file, then released", async () => {
  const h = harness({ initial: { [REQ]: request("lock1") } });
  const heldAt: Record<string, boolean> = {};
  const rename = h.fs.renameSync as (a: string, b: string) => void;
  h.fs.renameSync = (a: string, b: string) => {
    heldAt[b.slice(b.lastIndexOf("/") + 1)] = h.lock.held;
    rename(a, b);
  };
  await h.runner.poll();
  assert.equal(heldAt["run-request.lock1.claimed"], true, "locked while claiming");
  assert.equal(heldAt["run-done-lock1.json"], true, "locked while writing the done file");
  assert.deepEqual(h.lock.heldDuringRun, [true]);
  assert.equal(h.lock.held, false, "released afterwards");
});

test("a manual run that holds the lock at claim time: the request is left untouched and runs on a later poll (never consumed as a failure)", async () => {
  const h = harness({ initial: { [REQ]: request("race1") } });
  h.lock.held = true; // the button was pressed between the early busy check and the claim
  assert.deepEqual(await h.runner.poll(), { kind: "busy" });
  assert.equal(h.fs.files.has(REQ), true);
  assert.equal(h.runs.length, 0);
  assert.deepEqual(names(h.fs).filter((n) => n.includes("race1")), []);
  h.lock.held = false;
  assert.equal((await h.runner.poll()).kind, "ran");
});

test("the lock is released on every exit: claim failure, a run() that throws", async () => {
  const h = harness({ rename: false, initial: { [REQ]: request("rel1") } });
  h.fs.writeFileSync = () => {
    throw new Error("disk full");
  };
  assert.equal((await h.runner.poll()).kind, "claim_failed");
  assert.equal(h.lock.held, false);
  const h2 = harness({ initial: { [REQ]: request("rel2") } }, {
    run: async () => {
      throw new Error("kaput");
    },
  });
  await h2.runner.poll();
  assert.equal(h2.lock.held, false);
});

// ---- the loop ----------------------------------------------------------------------------------------------------

test("start() polls at once (panel load) and again every 5 s; stop() ends it", async () => {
  const scheduled: Array<{ fn: () => void; ms: number; cancelled: boolean }> = [];
  const h = harness({}, {
    schedule: (fn, ms) => {
      const entry = { fn, ms, cancelled: false };
      scheduled.push(entry);
      return () => void (entry.cancelled = true);
    },
  });
  h.fs.files.set(REQ, request("loop1"));
  await h.runner.start();
  assert.equal(h.runs.length, 1, "the first poll is immediate");
  assert.equal(scheduled.length, 1);
  assert.equal(scheduled[0]?.ms, POLL_MS);
  assert.equal(POLL_MS, 5000);

  h.fs.files.set(REQ, request("loop2", "full", iso(h.clock.t)));
  scheduled[0]?.fn();
  await h.runner.idle();
  assert.equal(h.runs.length, 2);
  assert.equal(scheduled.length, 2, "re-armed after each poll");

  h.runner.stop();
  assert.equal(scheduled[1]?.cancelled, true);
  scheduled[1]?.fn();
  await h.runner.idle();
  assert.equal(scheduled.length, 2, "stopped: no more polls");
});

test("a scheduler that throws cannot reject start() or leave an unhandled rejection", async () => {
  const h = harness({}, {
    schedule: () => {
      throw new Error("no timers");
    },
  });
  await assert.doesNotReject(h.runner.start());
  await assert.doesNotReject(h.runner.idle());
});

// ---- wiring + 0.1.5 ----------------------------------------------------------------------------------------------

test("spike.ts wires the auto-runner on boot and keeps the three buttons", () => {
  const spike = readFileSync(join(root, "spike", "src", "spike.ts"), "utf8");
  assert.match(spike, /import \{ createAutoRunner[^}]*\} from "\.\/autorun\.ts"/);
  assert.match(spike, /createAutoRunner\(/);
  assert.match(spike, /tryLock:[\s\S]*unlock:/, "the auto-run lock is wired to the same flag the buttons use");
  for (const id of ["run", "run-keep", "copy"]) assert.match(spike, new RegExp(`\\$\\("${id}"\\)\\.addEventListener\\("click"`));
});

test("spike 0.1.9: manifest version, SPIKE_VERSION and the safety guards are unchanged", () => {
  const manifest = JSON.parse(readFileSync(join(root, "spike", "manifest.json"), "utf8"));
  assert.equal(manifest.version, "0.1.9");
  assert.match(readFileSync(join(root, "spike", "src", "version.ts"), "utf8"), /SPIKE_VERSION = "0.1.9"/);
  const autorun = readFileSync(join(root, "spike", "src", "autorun.ts"), "utf8");
  assert.doesNotMatch(autorun, /scratchPathProblem|whynot-test/, "auto-run must not touch the safety rules");
});
