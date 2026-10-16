// The panel's perf marks (src/perf.ts, Addendum G2 hardening H3; budgets S1 first usable state, S2 click -> paint):
// a bounded buffer of {mark, t, ms?, rid?} from a fixed list, once-only boot marks timed from panel.boot, and sampled
// click -> paint pairs. DaemonSource sends the buffer to `reel serve` as `perf` batches (test/daemon-source.test.ts);
// here the recorder alone, on a fake clock.
import { test } from "node:test";
import assert from "node:assert/strict";
import { NO_PERF, PERF_BATCH_MAX, PERF_BUFFER_MAX, PERF_MARKS, PerfRecorder, perfOf } from "../src/perf.ts";

function rec(random = () => 0, t0 = 1_760_000_000_000) {
  const clock = { t: t0 };
  const perf = new PerfRecorder({ now: () => clock.t, random });
  return { clock, perf };
}

test("the marks are a fixed list (the schema's perf_mark enum, checked by the engine's contract tests)", () => {
  assert.deepEqual([...PERF_MARKS], ["panel.boot", "panel.first_paint", "link.welcome", "link.first_state", "panel.usable", "ui.click", "ui.paint"]);
  assert.equal(PERF_BATCH_MAX, 50);
});

test("panel.boot is marked at construction; the other boot marks once, timed from it", () => {
  const { clock, perf } = rec();
  clock.t += 120;
  perf.mark("panel.first_paint");
  clock.t += 500;
  perf.mark("link.welcome");
  perf.mark("link.welcome"); // a reconnect: still the first one only
  clock.t += 80.06;
  perf.mark("link.first_state");
  perf.mark("panel.usable");
  assert.deepEqual(perf.take(), [
    { mark: "panel.boot", t: 1_760_000_000_000 },
    { mark: "panel.first_paint", t: 1_760_000_000_120, ms: 120 },
    { mark: "link.welcome", t: 1_760_000_000_620, ms: 620 },
    { mark: "link.first_state", t: 1_760_000_000_700, ms: 700.1 },
    { mark: "panel.usable", t: 1_760_000_000_700, ms: 700.1 },
  ]);
  assert.equal(perf.size, 0);
  assert.ok(perf.has("panel.usable"));
});

test("a sampled click is timed to the first paint after it: ui.click and ui.paint share a rid", () => {
  const { clock, perf } = rec(() => 0.1);
  perf.take();
  perf.click();
  clock.t += 6.5;
  perf.painted();
  perf.painted(); // only the first paint after the click
  const [click, paint] = perf.take();
  assert.equal(click!.mark, "ui.click");
  assert.equal(paint!.mark, "ui.paint");
  assert.equal(paint!.ms, 6.5);
  assert.equal(click!.rid, paint!.rid);
  assert.match(click!.rid!, /^c-\d+$/);
  assert.equal(perf.size, 0);
});

test("clicks are sampled; a click that paints nothing records nothing", () => {
  let r = 0.5;
  const { perf } = rec(() => r);
  perf.take();
  perf.click(); // 0.5 >= the sample rate: not timed
  perf.painted();
  assert.equal(perf.size, 0);
  r = 0;
  perf.click();
  perf.clickDone(); // the handler painted nothing
  perf.painted(); // a later paint (a poll) is not this click's
  assert.equal(perf.size, 0);
});

test("the buffer is bounded and take() hands out at most a batch", () => {
  const { perf } = rec();
  for (let i = 0; i < PERF_BUFFER_MAX + 30; i++) perf.mark("ui.click", { rid: `c-${i}` });
  assert.equal(perf.size, PERF_BUFFER_MAX);
  assert.equal(perf.dropped, 31); // panel.boot took one place
  assert.equal(perf.take().length, PERF_BATCH_MAX);
  assert.equal(perf.size, PERF_BUFFER_MAX - PERF_BATCH_MAX);
});

test("a bad rid or ms is left out, never sent", () => {
  const { perf } = rec();
  perf.take();
  perf.mark("ui.paint", { rid: "C:/clients/x", ms: -3 });
  perf.mark("ui.paint", { rid: "a".repeat(49), ms: Number.NaN });
  assert.deepEqual(perf.take().map((m) => Object.keys(m).sort()), [["mark", "t"], ["mark", "t"]]);
});

test("NO_PERF and perfOf: a source without a recorder (the mock, tests) gets the no-op", () => {
  NO_PERF.mark("panel.boot");
  NO_PERF.click();
  NO_PERF.painted();
  NO_PERF.clickDone();
  assert.equal(perfOf({}), NO_PERF);
  assert.equal(perfOf(null), NO_PERF);
  const { perf } = rec();
  assert.equal(perfOf({ perf }), perf);
});

test("H3 review P2-8: durations come from the monotonic clock, t from the wall clock", () => {
  const wall = { t: 1_760_000_000_000 };
  const mono = { t: 50 };
  const perf = new PerfRecorder({ now: () => wall.t, mono: () => mono.t, random: () => 0 });
  wall.t += 3_600_000; // the wall clock steps an hour (NTP, a time-zone fix)
  mono.t += 120;
  perf.mark("panel.first_paint");
  perf.click();
  wall.t -= 10_000; // and back
  mono.t += 7;
  perf.painted();
  const [, first, click, paint] = perf.take();
  assert.equal(first!.ms, 120);
  assert.equal(first!.t, 1_760_003_600_000);
  assert.equal(paint!.ms, 7);
  assert.equal(click!.t, 1_760_003_600_000);
});
