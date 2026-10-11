// WhyNot Cut Spike - panel entry. "Run spike" runs every probe (probes.ts), writes
// ~/.whynot-cut/uxp-spike/results-<ts>.json after each probe (so a hang keeps the partial results), and shows them.
import type { premierepro as Ppro } from "@adobe/premierepro";
import { ensureDir, writeText } from "./fsutil.ts";
import { resolveHome, spikeDir } from "./home.ts";
import { buildProbes, errText, loadConfig, skipSaveCloseOpen, type Ctx } from "./probes.ts";
import { jsonSafe, runAll, type OpResult } from "./runner.ts";
import type { UxpFs, UxpModule, UxpOs } from "./uxp-types.ts";

declare const require: (id: string) => unknown;

const SPIKE_VERSION = "0.1.2";

function $(id: string): HTMLElement {
  const el = document.getElementById(id);
  if (!el) throw new Error(`panel is missing #${id}`);
  return el;
}

function stamp(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function tryRequire<T>(id: string): T | undefined {
  try {
    return require(id) as T;
  } catch {
    return undefined;
  }
}

function badge(ok: boolean | null): string {
  return ok === true ? "PASS" : ok === false ? "FAIL" : "N/A";
}

function renderOps(ops: OpResult[], planned: number): void {
  const list = $("ops");
  list.textContent = "";
  for (const o of ops) {
    const row = document.createElement("div");
    row.className = `op ${o.ok === true ? "pass" : o.ok === false ? "fail" : "na"}`;
    const head = document.createElement("div");
    head.className = "op-head";
    head.textContent = `${badge(o.ok)}  ${o.op}  (${o.ms} ms)`;
    row.appendChild(head);
    if (o.error) {
      const err = document.createElement("div");
      err.className = "op-err";
      err.textContent = o.error;
      row.appendChild(err);
    }
    list.appendChild(row);
  }
  $("progress").textContent = `${ops.length} / ${planned} probes`;
}

let lastJson = "";

async function copyResults(): Promise<void> {
  const status = $("status");
  if (!lastJson) {
    status.textContent = "Nothing to copy yet - run the spike first.";
    return;
  }
  const failures: string[] = [];
  // 1. async clipboard API (needs the manifest's clipboard permission; the getter itself throws without it)
  try {
    const nav = (globalThis as { navigator?: { clipboard?: { writeText?: (t: string) => Promise<void> } } }).navigator;
    const clip = nav?.clipboard;
    if (typeof clip?.writeText !== "function") throw new Error("navigator.clipboard.writeText is not available");
    await clip.writeText(lastJson);
    status.textContent = "Results copied to the clipboard.";
    return;
  } catch (e) {
    failures.push(`clipboard API: ${errText(e)}`);
  }
  // 2. fall back to selecting the textarea and execCommand("copy")
  try {
    const area = $("out") as HTMLTextAreaElement;
    area.focus();
    area.select();
    const ok = (document as unknown as { execCommand?: (c: string) => boolean }).execCommand?.("copy");
    if (!ok) throw new Error("execCommand copy returned false");
    status.textContent = "Results copied to the clipboard.";
    return;
  } catch (e) {
    failures.push(`execCommand: ${errText(e)}`);
  }
  status.textContent = `Copy failed (${failures.join("; ")}) - select the text below and copy it, or read the results file.`;
}

async function runSpike(keepOpen: boolean): Promise<void> {
  const status = $("status");
  const buttons = ["run", "run-keep"].map((id) => $(id) as HTMLButtonElement);
  buttons.forEach((b) => (b.disabled = true));
  skipSaveCloseOpen.value = keepOpen;
  try {
    const ppro = require("premierepro") as Ppro;
    const uxp = (tryRequire<UxpModule>("uxp") ?? {}) as UxpModule;
    const fs = (tryRequire<UxpFs>("fs") ?? {}) as UxpFs;
    const os = tryRequire<UxpOs>("os");
    const proc = tryRequire<{ env?: Record<string, string | undefined> }>("process") ?? (globalThis as { process?: { env?: Record<string, string | undefined> } }).process;
    const { home, via } = resolveHome({ ...(os?.homedir ? { osHomedir: () => os.homedir?.() ?? "" } : {}), env: proc?.env ?? {} });
    if (!home) throw new Error("cannot resolve the home folder (os.homedir() and USERPROFILE/HOME all unavailable)");
    const dir = spikeDir(home);
    await ensureDir(fs, dir);
    const { config, error } = await loadConfig(fs, dir);
    const ts = stamp();
    const ctx: Ctx = { ppro, fs, uxp, os, home, homeVia: via, stamp: ts, config, configError: error, expect: {}, notes: [] };
    const probes = buildProbes({ keepOpen });
    status.textContent = config ? `Running ${probes.length} probes (config: ${dir}/config.json)` : `Running without config - ${error}`;
    let premiere = "unknown";
    try {
      // Application.version resolves empty on 26.5.2; uxp.host.version is the reliable source
      premiere = uxp.host?.version || (await ppro.Application.version) || "unknown";
    } catch {
      premiere = uxp.host?.version || "unknown";
    }
    const resultsPath = `${dir}/results-${ts}.json`;
    const doc = (ops: OpResult[]) => ({
      spike: SPIKE_VERSION,
      premiere,
      uxp: uxp.versions?.uxp ?? null,
      at: new Date().toISOString(),
      home,
      home_via: via,
      results_file: resultsPath,
      config: config ?? null,
      config_error: error,
      kept_project_open: keepOpen,
      notes: ctx.notes,
      ops,
    });
    let writeError: string | null = null;
    const write = async (ops: OpResult[]) => {
      lastJson = JSON.stringify(jsonSafe(doc(ops)), null, 2);
      ($("out") as HTMLTextAreaElement).value = lastJson;
      renderOps(ops, probes.length);
      try {
        await writeText(fs, resultsPath, lastJson);
        writeError = null;
      } catch (e) {
        writeError = errText(e);
      }
    };
    renderOps([], probes.length);
    const ops = await runAll(probes, ctx, (_done, all) => write(all));
    await write(ops);
    const pass = ops.filter((o) => o.ok === true).length;
    const fail = ops.filter((o) => o.ok === false).length;
    const counts = `${pass} pass, ${fail} fail, ${ops.length - pass - fail} n/a`;
    status.textContent = writeError
      ? `Done: ${counts}. COULD NOT WRITE ${resultsPath}: ${writeError} - use Copy results or select the text below.`
      : `Done: ${counts}. Results: ${resultsPath}`;
  } catch (e) {
    status.textContent = `Spike could not start: ${errText(e)}`;
  } finally {
    buttons.forEach((b) => (b.disabled = false));
  }
}

function applyTheme(): void {
  try {
    const uxp = tryRequire<UxpModule>("uxp");
    const bg = uxp?.host?.getBackgroundColor?.();
    if (typeof bg === "string") document.documentElement.style.setProperty("--twn-bg", bg);
  } catch {
    // keep the stylesheet default
  }
}

function boot(): void {
  applyTheme();
  $("version").textContent = `v${SPIKE_VERSION}`;
  $("run").addEventListener("click", () => void runSpike(false));
  $("run-keep").addEventListener("click", () => void runSpike(true));
  $("copy").addEventListener("click", () => void copyResults());
}

boot();
