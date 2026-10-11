import { test } from "node:test";
import assert from "node:assert/strict";
import { isUnder, normPath, scratchPathProblem } from "../spike/src/safety.ts";
import { loadConfig } from "../spike/src/probes.ts";

const WT = "D:/0 Work/0 Pegasus IMC Agency/00 TWN/0 TWN AI/Editing Plugin/whynot-test";

test("normPath: forward slashes, lower case, no trailing slash", () => {
  assert.equal(normPath("D:\\Work\\Foo\\\\Bar\\"), "d:/work/foo/bar");
});

test("isUnder is segment-wise, not a string prefix", () => {
  assert.equal(isUnder("C:/a/b/c", "c:/A/B"), true);
  assert.equal(isUnder("C:/a/b", "C:/a/b"), true);
  assert.equal(isUnder("C:/a/bc", "C:/a/b"), false);
});

test("scratchPathProblem accepts only absolute paths under .../Editing Plugin/whynot-test/", () => {
  assert.equal(scratchPathProblem(`${WT}/_uxp-spike`), null);
  assert.equal(scratchPathProblem(`${WT.replace(/\//g, "\\")}\\PODCAST-TEST\\x.xml`), null);
  assert.equal(scratchPathProblem(WT.toUpperCase()), null);
  assert.equal(scratchPathProblem("/Users/x/Editing Plugin/whynot-test/a"), null);
});

test("scratchPathProblem rejects client folders, other folders, look-alikes, relative and '..' paths", () => {
  assert.match(scratchPathProblem("D:/WhyNot Clients/Dr X/assets") ?? "", /WhyNot Clients/);
  assert.match(scratchPathProblem("d:\\whynot clients") ?? "", /WhyNot Clients/);
  assert.match(scratchPathProblem(`${WT}/../WhyNot Clients/x`) ?? "", /'\.\.'/);
  assert.match(scratchPathProblem("D:/WhyNot Clients/Editing Plugin/whynot-test/x") ?? "", /WhyNot Clients/);
  assert.match(scratchPathProblem("C:/Users/yunus/Documents") ?? "", /not under/);
  assert.match(scratchPathProblem(`${WT}-evil/x`) ?? "", /not under/);
  assert.match(scratchPathProblem("D:/0 Work/0 Pegasus IMC Agency/00 TWN/0 TWN AI/Editing Plugin/WhyNotCut/dist") ?? "", /not under/);
  assert.match(scratchPathProblem("whynot-test/x") ?? "", /absolute/);
  assert.match(scratchPathProblem("") ?? "", /empty/);
});

function fsWith(json: unknown) {
  return { readFile: async () => (typeof json === "string" ? json : JSON.stringify(json)) };
}

test("loadConfig accepts a config entirely under whynot-test", async () => {
  const r = await loadConfig(fsWith({ xml_path: `${WT}/a.xml`, work_dir: `${WT}/_uxp-spike`, still_png: `${WT}/s.png`, ws_url: null }), "C:/h");
  assert.equal(r.error, null);
  assert.equal(r.config?.work_dir, `${WT}/_uxp-spike`);
});

test("loadConfig rejects work_dir / xml_path / still_png outside whynot-test or inside WhyNot Clients (config treated as missing)", async () => {
  for (const bad of [
    { work_dir: "D:/WhyNot Clients/x" },
    { work_dir: "C:/Users/yunus/Desktop/spike" },
    { xml_path: "D:/WhyNot Clients/Dr X/a.xml" },
    { xml_path: "C:/other/a.xml" },
    { still_png: "D:/WhyNot Clients/Dr X/s.png" },
  ]) {
    const r = await loadConfig(fsWith({ xml_path: `${WT}/a.xml`, work_dir: `${WT}/_uxp-spike`, ...bad }), "C:/h");
    assert.equal(r.config, null, JSON.stringify(bad));
    assert.match(r.error ?? "", /config\.json rejected/);
  }
});

test("loadConfig: missing keys, unreadable file and a non-loopback ws_url are all 'no config'", async () => {
  assert.match((await loadConfig(fsWith({ work_dir: `${WT}/w` }), "C:/h")).error ?? "", /missing: xml_path/);
  assert.match((await loadConfig({}, "C:/h")).error ?? "", /cannot read/);
  const r = await loadConfig(fsWith({ xml_path: `${WT}/a.xml`, work_dir: `${WT}/w`, ws_url: "ws://evil.example.com/x" }), "C:/h");
  assert.equal(r.config, null);
  assert.match(r.error ?? "", /ws_url/);
});
