// The one mutation pattern (parity U1/U2): project.lockedAccess(() => project.executeTransaction(build, "WhyNot Cut
// build")), so a build is one named undo step. None of this round's seven ops creates an Action (open, close, save, the
// playhead and frame export are not undoable edits); build_project (next round) uses this helper.
import { test } from "node:test";
import assert from "node:assert/strict";
import { UNDO_LABEL, transact } from "../src/ops/transaction.ts";
import { OpError } from "../src/ops/types.ts";
import { WIN_PROJECT, makeEnv } from "./host-adapter.fakes.ts";

test("transact: lockedAccess wraps one executeTransaction labelled 'WhyNot Cut build' holding every action", () => {
  const { pp } = makeEnv();
  const p = pp.addOpen(WIN_PROJECT, []);
  assert.equal(UNDO_LABEL, "WhyNot Cut build");
  transact(p as never, (add) => {
    add({ a: 1 } as never);
    add({ a: 2 } as never);
  });
  assert.deepEqual(pp.calls, ["lockedAccess", "executeTransaction WhyNot Cut build"]);
  assert.deepEqual(pp.transactions, [{ label: "WhyNot Cut build", actions: [{ a: 1 }, { a: 2 }] }]);
});

test("transact: a transaction Premiere rejects is an OpError, and so is an action it refuses to add", () => {
  const { pp } = makeEnv();
  const p = pp.addOpen(WIN_PROJECT, []);
  pp.transactionReturns = false;
  assert.throws(() => transact(p as never, (add) => add({} as never)), (e: unknown) => e instanceof OpError && /did not apply/i.test(e.message));
  const refusing = {
    lockedAccess: (cb: () => void) => cb(),
    executeTransaction: (build: (ca: { addAction: () => boolean }) => void) => (build({ addAction: () => false }), true),
  };
  assert.throws(() => transact(refusing as never, (add) => add({} as never)), (e: unknown) => e instanceof OpError && /refused/i.test(e.message));
});
