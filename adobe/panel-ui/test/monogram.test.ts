import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { MONOGRAM_DATA_URI } from "../src/monogram.ts";

test("the inline header monogram is exactly the premiere-uxp dark 48 px icon (no drift)", () => {
  const png = readFileSync(new URL("../../premiere-uxp/icons/dark/icon-48.png", import.meta.url));
  assert.equal(MONOGRAM_DATA_URI, `data:image/png;base64,${png.toString("base64")}`);
});
