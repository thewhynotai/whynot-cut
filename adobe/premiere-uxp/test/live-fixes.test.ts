// Defects found in the first live run (Premiere 26.5.2, Windows): long-path prefix on project.path, and a
// clipboard getter that throws inside host_info.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { buildProbes, type Ctx, type SpikeConfig } from "../spike/src/probes.ts";
import { cleanPath, isUnder, normPath, scratchPathProblem } from "../spike/src/safety.ts";
import { DEFAULT_TIMEOUT_MS, runProbe } from "../spike/src/runner.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const WT = "D:/0 Work/0 Pegasus IMC Agency/00 TWN/0 TWN AI/Editing Plugin/whynot-test";
const CONFIG: SpikeConfig = { xml_path: `${WT}/a.xml`, work_dir: `${WT}/_uxp-spike`, still_png: `${WT}/s.png` };

// exactly what Premiere returned live as project.path (the string value, backslashes unescaped)
const LIVE_PATH = "\\\\?\\D:/0 Work/0 Pegasus IMC Agency/00 TWN/0 TWN AI/Editing Plugin/whynot-test/_uxp-spike/spike-20261012-002655.prproj";

function probe(op: string) {
  const p = buildProbes().find((d) => d.op === op);
  assert.ok(p, `no probe ${op}`);
  return p;
}

function ctxWith(ppro: unknown, extra: Partial<Ctx> = {}): Ctx {
  return {
    ppro: ppro as Ctx["ppro"],
    fs: { lstat: async () => ({ size: 5, isDirectory: () => true }), mkdir: async () => {} },
    uxp: { host: { name: "premierepro", version: "26.5.2" }, versions: { uxp: "uxp-9.3.0-local" } },
    os: undefined,
    home: "C:/Users/LOQ",
    homeVia: "os.homedir",
    stamp: "20261012-002655",
    config: CONFIG,
    configError: null,
    expect: {},
    notes: [],
    ...extra,
  };
}

// ---- long-path prefixes ----------------------------------------------------------------------------------------

test("cleanPath strips \\\\?\\, //?/ and \\\\?\\UNC\\ and keeps the case", () => {
  assert.equal(cleanPath(LIVE_PATH), "D:/0 Work/0 Pegasus IMC Agency/00 TWN/0 TWN AI/Editing Plugin/whynot-test/_uxp-spike/spike-20261012-002655.prproj");
  assert.equal(cleanPath("//?/D:/x/y"), "D:/x/y");
  assert.equal(cleanPath("\\\\?\\D:\\x\\y\\"), "D:/x/y");
  assert.equal(cleanPath("\\\\?\\UNC\\srv\\share\\x"), "//srv/share/x");
  assert.equal(cleanPath("//?/UNC/srv/share/x"), "//srv/share/x");
  assert.equal(cleanPath("D:/plain/path"), "D:/plain/path");
});

test("the exact live project.path is under work_dir and acceptable as a scratch path", () => {
  assert.equal(isUnder(LIVE_PATH, CONFIG.work_dir), true);
  assert.equal(scratchPathProblem(LIVE_PATH), null);
  assert.equal(normPath(LIVE_PATH).startsWith("d:/0 work/"), true);
});

test("strictness is kept with prefixes: other folders, clients, look-alikes and '..' are still refused", () => {
  assert.equal(isUnder("\\\\?\\C:/Users/yunus/Documents/Client Reel.prproj", CONFIG.work_dir), false);
  assert.equal(isUnder("\\\\?\\D:/WhyNot Clients/Dr X/a.prproj", CONFIG.work_dir), false);
  assert.equal(isUnder(`\\\\?\\${WT}/_uxp-spike-evil/a.prproj`, CONFIG.work_dir), false);
  assert.match(scratchPathProblem("\\\\?\\D:/WhyNot Clients/Dr X/a.prproj") ?? "", /WhyNot Clients/);
  assert.match(scratchPathProblem("\\\\?\\C:/Users/yunus/a.prproj") ?? "", /not under/);
  assert.match(scratchPathProblem(`\\\\?\\${WT}/../x`) ?? "", /'\.\.'/);
  assert.match(scratchPathProblem("\\\\?\\UNC\\srv\\share\\x") ?? "", /not under/);
});

test("create_project accepts the live \\\\?\\ path, adopts the project and records the raw path", async () => {
  const project = { name: "spike-20261012-002655", path: LIVE_PATH };
  const ppro = { Project: { createProject: async () => project, getActiveProject: async () => project } };
  const ctx = ctxWith(ppro);
  const r = await runProbe(probe("create_project"), ctx);
  assert.equal(r.ok, true, JSON.stringify(r));
  assert.equal(ctx.project, project as unknown);
  assert.equal(ctx.projectPath?.startsWith("D:/0 Work/"), true, "projectPath must be the clean path");
  const d = r.detail as { path: string; path_raw_json: string; path_normalised: string; is_active: boolean };
  assert.equal(d.path, LIVE_PATH);
  assert.equal(d.path_raw_json, JSON.stringify(LIVE_PATH));
  assert.match(d.path_raw_json, /^"\\\\\\\\\?\\\\D:/);
  assert.equal(d.path_normalised.startsWith("d:/0 work/"), true);
  assert.equal(d.is_active, true);
});

test("a later mutating probe passes the guard with the long-path project (and still refuses a foreign one)", async () => {
  const names = { v: "V1" };
  const project = {
    name: "x",
    path: LIVE_PATH,
    lockedAccess: (cb: () => void) => cb(),
    executeTransaction: (cb: (ca: { addAction: (a: { apply: () => void }) => boolean }) => void) => {
      cb({ addAction: (a) => (a.apply(), true) });
      return true;
    },
  };
  const seq = {
    getVideoTrack: async () => ({
      get name() {
        return names.v;
      },
      createSetNameAction: (n: string) => ({ apply: () => void (names.v = n) }),
    }),
    getVideoTrackCount: async () => 2,
    getAudioTrackCount: async () => 0,
  };
  const ctx = ctxWith({}, { project: project as unknown as Ctx["project"], sequence: seq as unknown as Ctx["sequence"] });
  const r = await runProbe(probe("track_rename"), ctx);
  assert.doesNotMatch(r.error ?? "", /refusing/);
  assert.equal(names.v, "WNC Spike V2");
  const foreign = ctxWith({}, { project: { path: "\\\\?\\C:/Users/yunus/Documents/x.prproj" } as unknown as Ctx["project"] });
  assert.match((await runProbe(probe("track_rename"), foreign)).error ?? "", /refusing to touch a project outside work_dir/);
});

test("no probe timeout is shorter than 90 s for create_project and import_fcp7_xml (createProject took ~33 s live)", () => {
  for (const op of ["create_project", "import_fcp7_xml"]) {
    const t = probe(op).timeoutMs ?? DEFAULT_TIMEOUT_MS;
    assert.ok(t >= 90_000, `${op} timeout ${t}`);
  }
  assert.ok(DEFAULT_TIMEOUT_MS >= 90_000);
});

// ---- clipboard -------------------------------------------------------------------------------------------------

function withThrowingClipboard<T>(fn: (accessed: () => number) => Promise<T>): Promise<T> {
  const g = globalThis as { navigator?: unknown };
  const saved = Object.getOwnPropertyDescriptor(g, "navigator");
  let hits = 0;
  Object.defineProperty(g, "navigator", {
    configurable: true,
    value: {
      get clipboard() {
        hits++;
        throw new Error("Clipboard access not supported for 3P plugins with manifest version upto 4.");
      },
    },
  });
  return fn(() => hits).finally(() => {
    if (saved) Object.defineProperty(g, "navigator", saved);
    else delete g.navigator;
  });
}

test("host_info never touches navigator.clipboard (its getter throws without the permission)", async () => {
  await withThrowingClipboard(async (hits) => {
    const ppro = { Application: { version: Promise.resolve("26.5.2") }, Project: { getActiveProject: async () => null } };
    const r = await runProbe(probe("host_info"), ctxWith(ppro));
    assert.equal(r.ok, true, JSON.stringify(r));
    assert.equal(hits(), 0, "host_info read navigator.clipboard");
  });
});

test("host_info steps are independent: failing getBackgroundColor, version and active project keep the rest", async () => {
  const ppro = {
    Application: { version: Promise.reject(new Error("no version")) },
    Project: {
      getActiveProject: async () => {
        throw new Error("no active project");
      },
    },
  };
  const ctx = ctxWith(ppro);
  ctx.uxp = {
    host: {
      name: "premierepro",
      version: "26.5.2",
      getBackgroundColor: () => {
        throw new Error("bg boom");
      },
    },
    versions: { uxp: "uxp-9.3.0-local" },
  };
  const r = await runProbe(probe("host_info"), ctx);
  assert.equal(r.ok, true, "core host info was readable, so host_info itself is ok");
  const steps = (r.detail as { steps: Array<{ step: string; ok: boolean; error?: string }> }).steps;
  const by = Object.fromEntries(steps.map((s) => [s.step, s]));
  assert.equal(by["premiere_version (informational)"]?.ok, true, "premiere_version is informational: it never fails the step list");
  assert.equal(by.background_color?.ok, false);
  assert.match(by.background_color?.error ?? "", /bg boom/);
  assert.equal(by["active_project (read-only)"]?.ok, false);
  for (const name of ["uxp_host", "theme", "os", "home_and_config", "fs_members", "globals", "ppro_members"]) assert.equal(by[name]?.ok, true, name);
});

test("host_info is ok:false only when the UXP host info itself is unreadable", async () => {
  const ctx = ctxWith({ Application: { version: Promise.resolve("26.5.2") }, Project: { getActiveProject: async () => null } });
  ctx.uxp = {};
  const r = await runProbe(probe("host_info"), ctx);
  assert.equal(r.ok, false);
});

test("spike sources never read navigator.clipboard outside the Copy results handler", () => {
  const probes = readFileSync(join(root, "spike", "src", "probes.ts"), "utf8");
  assert.doesNotMatch(probes.replace(/\/\/.*$/gm, "").replace(/"[^"\n]*"/g, '""').replace(/`[^`]*`/g, "``"), /clipboard/);
  const spike = readFileSync(join(root, "spike", "src", "spike.ts"), "utf8");
  const outside = spike.slice(0, spike.indexOf("async function copyResults")) + spike.slice(spike.indexOf("async function runSpike"));
  assert.doesNotMatch(outside.replace(/\/\/.*$/gm, ""), /navigator|clipboard/);
});

test("spike manifest asks for clipboard readAndWrite and the version is the current one (0.1.8) everywhere", () => {
  const manifest = JSON.parse(readFileSync(join(root, "spike", "manifest.json"), "utf8"));
  assert.equal(manifest.requiredPermissions.clipboard, "readAndWrite");
  assert.equal(manifest.requiredPermissions.localFileSystem, "fullAccess");
  assert.equal(manifest.version, "0.1.8");
  assert.match(readFileSync(join(root, "spike", "src", "version.ts"), "utf8"), /SPIKE_VERSION = "0.1.8"/);
});
