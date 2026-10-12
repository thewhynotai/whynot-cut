// set_player_position (moves the playhead of the named sequence; readback = where Premiere says it is) and
// clip_components (read-only: components by match name, params by display name, values unwrapped from UXP's
// {value} wrapper; arrays in the CEP "x,y" form; objects stringified; unreadable ones '?').
import { test } from "node:test";
import assert from "node:assert/strict";
import { OPS } from "../src/ops/index.ts";
import { OpError } from "../src/ops/types.ts";
import { validateReadback } from "../src/ops/validate.ts";
import { SEQ, WIN_PROJECT, editClip, makeEnv, opCtx } from "./host-adapter.fakes.ts";

test("set_player_position: activates the named sequence when another is active, seeks, reads the position back", async () => {
  const { env, pp } = makeEnv();
  pp.addOpen(WIN_PROJECT, [{ name: "Other" }, { name: SEQ }]);
  const rb = await OPS.set_player_position.run({ sequence_name: SEQ, t_s: 12.5 }, opCtx(env).ctx);
  assert.deepEqual(rb, { position_s: 12.5 });
  assert.deepEqual(pp.calls, [`setActiveSequence ${SEQ}`, `setPlayerPosition ${SEQ} 12.5`]);
  assert.equal(validateReadback("set_player_position", rb), null);
  pp.calls.length = 0;
  await OPS.set_player_position.run({ sequence_name: SEQ, t_s: 3 }, opCtx(env).ctx);
  assert.deepEqual(pp.calls, [`setPlayerPosition ${SEQ} 3`], "already active: no re-activation");
});

test("set_player_position: no project, an unknown sequence and a refused move are plain-sentence OpErrors", async () => {
  const none = makeEnv();
  await assert.rejects(() => OPS.set_player_position.run({ sequence_name: SEQ, t_s: 1 }, opCtx(none.env).ctx), /open a project/i);
  const { env, pp } = makeEnv();
  const p = pp.addOpen(WIN_PROJECT, [{ name: SEQ }]);
  await assert.rejects(() => OPS.set_player_position.run({ sequence_name: "Nope", t_s: 1 }, opCtx(env).ctx), (e: unknown) => {
    assert.ok(e instanceof OpError);
    assert.match(e.message, /no sequence named "Nope"/);
    return true;
  });
  p.sequences[0]!.setPlayerPositionReturns = false;
  await assert.rejects(() => OPS.set_player_position.run({ sequence_name: SEQ, t_s: 1 }, opCtx(env).ctx), /did not move the playhead/i);
});

test("clip_components: the clip's name and every component with its match name and param values", async () => {
  const { env, pp } = makeEnv();
  pp.addOpen(WIN_PROJECT, [{ name: SEQ, video: [[editClip()]] }]);
  const rb = await OPS.clip_components.run({ sequence_name: SEQ }, opCtx(env).ctx);
  assert.deepEqual(rb, {
    clip: "EP02TEST.mp4 [hold]",
    components: [
      { name: "Opacity", match: "AE.ADBE Opacity", props: [{ name: "Opacity", value: 100 }, { name: "Blend Mode", value: 18 }] },
      {
        name: "Motion",
        match: "AE.ADBE Motion",
        props: [
          { name: "Position", value: "0.427413,0.5" },
          { name: "Scale", value: 177.77799987793 },
          { name: " ", value: true },
          { name: "Crop Left", value: 0 },
        ],
      },
      { name: "Lumetri Color", match: "AE.ADBE Lumetri", props: [{ name: "Look", value: '{"r":1,"g":0,"b":0,"a":1}' }, { name: "Broken", value: "?" }] },
    ],
  });
  assert.equal(validateReadback("clip_components", rb), null);
});

test("clip_components: track, clip and audio pick the clip; out of range is an OpError, not a crash", async () => {
  const { env, pp } = makeEnv();
  const second = { name: "second", components: [] };
  const audio = { name: "voice.wav", components: [{ match: "AE.ADBE Volume", display: "Volume", params: [{ displayName: "Level", start: 0 }] }] };
  pp.addOpen(WIN_PROJECT, [{ name: SEQ, video: [[editClip()], [editClip(), second]], audio: [[audio]] }]);
  assert.equal((await OPS.clip_components.run({ sequence_name: SEQ, track: 1, clip: 1 }, opCtx(env).ctx)).clip, "second");
  const a = await OPS.clip_components.run({ sequence_name: SEQ, audio: true }, opCtx(env).ctx);
  assert.deepEqual(a, { clip: "voice.wav", components: [{ name: "Volume", match: "AE.ADBE Volume", props: [{ name: "Level", value: 0 }] }] });
  await assert.rejects(() => OPS.clip_components.run({ sequence_name: SEQ, track: 5 }, opCtx(env).ctx), /no video track 6/i);
  await assert.rejects(() => OPS.clip_components.run({ sequence_name: SEQ, track: 1, clip: 7 }, opCtx(env).ctx), /no clip 8/i);
  await assert.rejects(() => OPS.clip_components.run({ sequence_name: "X" }, opCtx(env).ctx), /no sequence named "X"/);
});
