import { test } from "node:test";
import assert from "node:assert/strict";
import { resolveHome, spikeDir, toForwardSlashes } from "../spike/src/home.ts";

test("resolveHome prefers os.homedir()", () => {
  const r = resolveHome({ osHomedir: () => "C:\\Users\\LOQ", env: { USERPROFILE: "C:\\other" } });
  assert.deepEqual(r, { home: "C:/Users/LOQ", via: "os.homedir" });
});

test("resolveHome falls back to USERPROFILE, then HOME, then HOMEDRIVE+HOMEPATH", () => {
  assert.deepEqual(resolveHome({ env: { USERPROFILE: "C:\\Users\\A" } }), { home: "C:/Users/A", via: "env.USERPROFILE" });
  assert.deepEqual(resolveHome({ env: { HOME: "/Users/a" } }), { home: "/Users/a", via: "env.HOME" });
  assert.deepEqual(resolveHome({ env: { HOMEDRIVE: "C:", HOMEPATH: "\\Users\\B" } }), {
    home: "C:/Users/B",
    via: "env.HOMEDRIVE+HOMEPATH",
  });
});

test("resolveHome skips a throwing or empty os.homedir()", () => {
  const throwing = () => {
    throw new Error("no os");
  };
  assert.equal(resolveHome({ osHomedir: throwing, env: { USERPROFILE: "D:\\u" } }).via, "env.USERPROFILE");
  assert.equal(resolveHome({ osHomedir: () => "", env: { HOME: "/h" } }).via, "env.HOME");
});

test("resolveHome returns null home when nothing works", () => {
  assert.deepEqual(resolveHome({ env: {} }), { home: null, via: "none" });
});

test("spikeDir and toForwardSlashes", () => {
  assert.equal(toForwardSlashes("C:\\a\\b/c"), "C:/a/b/c");
  assert.equal(spikeDir("C:/Users/LOQ/"), "C:/Users/LOQ/.whynot-cut/uxp-spike");
});
