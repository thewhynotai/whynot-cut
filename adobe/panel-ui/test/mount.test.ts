import { test } from "node:test";
import assert from "node:assert/strict";
import { logEpoch, mount } from "../src/mount.ts";
import type { MountRoot, PanelElement } from "../src/mount.ts";
import type { PanelHost } from "../src/host.ts";
import type { LogLine, PanelDataSource, PanelState, Result } from "../src/source.ts";
import { MockSource } from "../src/mock.ts";
import type { ActionName } from "../src/contract.ts";
import { AR, EN } from "../src/i18n.ts";
import { PerfRecorder } from "../src/perf.ts";

// A tiny fake DOM: enough for event delegation, innerHTML and querySelector of data attributes.
type Listener = (e: { target: PanelElement | null }) => void;
class FakeEl implements PanelElement {
  value = "";
  disabled = false;
  attrs: Record<string, string>;
  constructor(attrs: Record<string, string>) { this.attrs = attrs; }
  getAttribute(n: string) { return this.attrs[n] ?? null; }
  closest(sel: string): PanelElement | null {
    const m = /^\[([\w-]+)\]$/.exec(sel);
    return m && m[1]! in this.attrs ? this : null;
  }
}
class FakeRoot implements MountRoot {
  innerHTML = "";
  listeners: Record<string, Listener[]> = {};
  renders = 0;
  addEventListener(t: string, fn: Listener) { (this.listeners[t] ??= []).push(fn); }
  removeEventListener(t: string, fn: Listener) { this.listeners[t] = (this.listeners[t] ?? []).filter((f) => f !== fn); }
  fire(type: string, target: FakeEl) { for (const fn of this.listeners[type] ?? []) fn({ target }); }
  click(attrs: Record<string, string>) { this.fire("click", new FakeEl(attrs)); }
  input(field: string, value: string) { const el = new FakeEl({ "data-field": field }); el.value = value; this.fire("input", el); }
  querySelector(): null { return null; }
}

interface Calls { approve: unknown[]; requestChanges: unknown[]; run: { action: ActionName; data: object }[]; rebuild: { item: string; project_path: string; replace_edited: boolean }[]; cancel: string[] }
class RecSource implements PanelDataSource {
  calls: Calls = { approve: [], requestChanges: [], run: [], rebuild: [], cancel: [] };
  cbs: ((s: PanelState) => void)[] = [];
  inner = new MockSource({ language: "en", scenario: "approval" });
  nextResult: Result = { ok: true };
  snapshot() { return this.inner.snapshot(); }
  subscribe(cb: (s: PanelState) => void) { this.cbs.push(cb); return () => { this.cbs = this.cbs.filter((c) => c !== cb); }; }
  async approve(i: { item: string; editor_name: string; fingerprint: string }) { this.calls.approve.push(i); return this.nextResult; }
  async requestChanges(i: { item: string; editor_name: string; text: string }) { this.calls.requestChanges.push(i); return this.nextResult; }
  async run(action: ActionName, data: object) { this.calls.run.push({ action, data }); return this.nextResult; }
  async rebuild(i: { item: string; project_path: string; replace_edited: boolean }) { this.calls.rebuild.push(i); return this.nextResult; }
  async cancel(id: string) { this.calls.cancel.push(id); }
}
function hostRec() {
  const calls = { seek: [] as number[], preview: [] as string[], reveal: [] as string[], copy: [] as string[] };
  const host: PanelHost = {
    setPlayerPosition: (t) => { calls.seek.push(t); },
    openInSourceMonitor: (p) => { calls.preview.push(p); },
    revealPath: (p) => { calls.reveal.push(p); },
    copyText: (t) => { calls.copy.push(t); },
  };
  return { host, calls };
}
const tick = () => new Promise((r) => setTimeout(r, 0));

async function setup() {
  const root = new FakeRoot();
  const source = new RecSource();
  const { host, calls } = hostRec();
  const handle = mount(root, source, host);
  await handle.ready;
  return { root, source, calls, handle, state: await source.snapshot() };
}

test("mount renders the snapshot and re-renders on subscribe", async () => {
  const { root, source, state } = await setup();
  assert.ok(root.innerHTML.includes("WhyNot Cut"));
  assert.ok(root.innerHTML.includes(state.client));
  const next: PanelState = { ...state, client: "Another Client" };
  for (const cb of source.cbs) cb(next);
  assert.ok(root.innerHTML.includes("Another Client"));
});

test("a state pushed while the snapshot is still pending is not lost", async () => {
  const root = new FakeRoot();
  const source = new RecSource();
  const s = await source.snapshot();
  let release!: (v: PanelState) => void;
  source.snapshot = () => new Promise<PanelState>((r) => { release = r; });
  const { host } = hostRec();
  const h = mount(root, source, host);
  for (const cb of source.cbs) cb({ ...s, client: "Pushed Client" });
  release(s);
  await h.ready;
  assert.ok(root.innerHTML.includes("Pushed Client"));
});

test("language follows state: AR state renders dir=rtl", async () => {
  const { root, source, state } = await setup();
  for (const cb of source.cbs) cb({ ...state, language: "ar" });
  assert.match(root.innerHTML, /dir="rtl" lang="ar"/);
});

test("Approve sends item, editor_name and the fingerprint that was on screen", async () => {
  const { root, source, state } = await setup();
  root.click({ "data-action": "approve", "data-fingerprint": state.approval!.fingerprint });
  await tick();
  assert.deepEqual(source.calls.approve, [{ item: state.item, editor_name: state.editor_name, fingerprint: state.approval!.fingerprint }]);
});

test("Approve without an editor name is refused in the handler, and typing a name enables it", async () => {
  const root = new FakeRoot();
  const source = new RecSource();
  const s = await source.snapshot();
  source.snapshot = async () => ({ ...s, editor_name: "" });
  const { host } = hostRec();
  const h = mount(root, source, host);
  await h.ready;
  root.click({ "data-action": "approve", "data-fingerprint": s.approval!.fingerprint });
  await tick();
  assert.equal(source.calls.approve.length, 0);
  root.input("editor_name", "Layla");
  root.click({ "data-action": "approve", "data-fingerprint": s.approval!.fingerprint });
  await tick();
  assert.equal((source.calls.approve[0] as { editor_name: string }).editor_name, "Layla");
});

test("Request changes needs non-empty text", async () => {
  const { root, source, state } = await setup();
  root.click({ "data-action": "request-changes" });
  await tick();
  assert.equal(source.calls.requestChanges.length, 0);
  root.input("changes", "   ");
  root.click({ "data-action": "request-changes" });
  await tick();
  assert.equal(source.calls.requestChanges.length, 0);
  root.input("changes", " Cut the first 5 seconds ");
  root.click({ "data-action": "request-changes" });
  await tick();
  assert.deepEqual(source.calls.requestChanges, [{ item: state.item, editor_name: state.editor_name, text: "Cut the first 5 seconds" }]);
});

test("the typed change text survives a re-render", async () => {
  const { root, source, state } = await setup();
  root.input("changes", "keep me");
  for (const cb of source.cbs) cb({ ...state });
  assert.ok(root.innerHTML.includes("keep me"));
});

test("a QC tile click moves the playhead; Re-export runs export_frames for that one time", async () => {
  const { root, source, calls, state } = await setup();
  root.click({ "data-action": "seek", "data-t": "12.5" });
  assert.deepEqual(calls.seek, [12.5]);
  for (const cb of source.cbs) cb({ ...state, qc: [{ t_s: 12.5, tc: "00:00:12:12", file: "f.png", label: "x", verdict: "media_pending" }] });
  root.click({ "data-action": "reexport", "data-t": "12.5" });
  await tick();
  const run = source.calls.run[0]!;
  assert.equal(run.action, "export_frames");
  assert.deepEqual((run.data as { times: number[] }).times, [12.5]);
});

test("Rebuild asks in-panel first; only the confirm calls source.rebuild (never run build_project)", async () => {
  const { root, source, state } = await setup();
  root.click({ "data-action": "rebuild" });
  await tick();
  assert.equal(source.calls.rebuild.length, 0);
  assert.ok(root.innerHTML.includes('data-action="rebuild-confirm"'));
  root.click({ "data-action": "rebuild-cancel" });
  assert.ok(!root.innerHTML.includes('data-action="rebuild-confirm"'));
  assert.equal(source.calls.rebuild.length, 0);
  root.click({ "data-action": "rebuild" });
  root.click({ "data-action": "rebuild-confirm" });
  await tick();
  assert.deepEqual(source.calls.rebuild, [{ item: state.item, project_path: state.context.project_path, replace_edited: true }]);
  assert.equal(source.calls.run.length, 0, "the panel must not send a partial build_project");
  assert.ok(!root.innerHTML.includes('data-action="rebuild-confirm"'));
});

test("host adapter actions: preview, reveal folder, copy diagnostics", async () => {
  const { root, calls, state } = await setup();
  root.click({ "data-action": "preview" });
  assert.deepEqual(calls.preview, [state.approval!.preview_mp4]);
  root.click({ "data-action": "reveal" });
  assert.deepEqual(calls.reveal, [state.context.folder]);
  root.click({ "data-action": "copy-diagnostics" });
  assert.equal(calls.copy.length, 1);
  assert.ok(calls.copy[0]!.includes(state.client));
  assert.ok(!/claude\s*code/i.test(calls.copy[0]!));
});

test("Cancel forwards the request id; the log drawer toggles", async () => {
  const { root, source } = await setup();
  root.click({ "data-action": "cancel", "data-id": "req-9" });
  await tick();
  assert.deepEqual(source.calls.cancel, ["req-9"]);
  assert.ok(!root.innerHTML.includes('class="log-lines"'));
  root.click({ "data-action": "toggle-log" });
  assert.ok(root.innerHTML.includes('class="log-lines"'));
  root.click({ "data-action": "toggle-log" });
  assert.ok(!root.innerHTML.includes('class="log-lines"'));
});

test("a failed result shows its error and how, escaped", async () => {
  const { root, source } = await setup();
  source.nextResult = { ok: false, error: "Premiere is <busy>", how: "Wait and retry." };
  root.click({ "data-action": "open-project" });
  await tick();
  assert.ok(root.innerHTML.includes("Premiere is &lt;busy&gt;"));
  assert.ok(root.innerHTML.includes("Wait and retry."));
});

test("a throwing host adapter becomes a notice, not an unhandled rejection", async () => {
  const root = new FakeRoot();
  const source = new RecSource();
  const host: PanelHost = {
    setPlayerPosition: () => { throw new Error("no sequence"); },
    openInSourceMonitor: async () => { throw new Error("nope"); },
    revealPath: () => {},
    copyText: () => {},
  };
  const h = mount(root, source, host);
  await h.ready;
  root.click({ "data-action": "seek", "data-t": "1" });
  root.click({ "data-action": "preview" });
  await tick();
  assert.ok(root.innerHTML.includes("nope"));
});

test("unmount stops listening and unsubscribes", async () => {
  const { root, source, handle } = await setup();
  handle.unmount();
  assert.equal(source.cbs.length, 0);
  assert.equal((root.listeners["click"] ?? []).length, 0);
});

// ---- render errors are shown, never swallowed ----

const sloppy = (s: PanelState): PanelState => ({ ...s, pipeline: null, context: undefined } as unknown as PanelState);

test("a slightly-off snapshot (pipeline: null, no context) shows the error view instead of a blank panel", async () => {
  const root = new FakeRoot();
  const source = new RecSource();
  const good = await source.snapshot();
  source.snapshot = async () => sloppy(good);
  const { host } = hostRec();
  const h = mount(root, source, host);
  await h.ready;
  assert.ok(root.innerHTML.length > 0, "blank panel");
  assert.ok(root.innerHTML.includes('class="banner banner-error"'));
  assert.ok(root.innerHTML.includes(EN["error.render"]));
  assert.match(root.innerHTML, /Cannot read|undefined|null/i, "the message is shown");
  assert.ok(root.innerHTML.includes("Powered by thewhynot.ai") || root.innerHTML.includes("WhyNot Cut"));
});

test("the error view follows the state's language when it is known (AR)", async () => {
  const root = new FakeRoot();
  const source = new RecSource();
  const good = await source.snapshot();
  source.snapshot = async () => ({ ...sloppy(good), language: "ar" } as PanelState);
  const { host } = hostRec();
  const h = mount(root, source, host);
  await h.ready;
  assert.ok(root.innerHTML.includes(AR["error.render"]));
  assert.match(root.innerHTML, /dir="rtl" lang="ar"/);
});

test("a throwing render in the subscribe path does not reach the source's emit loop, and a good state recovers", async () => {
  const { root, source, state } = await setup();
  assert.doesNotThrow(() => { for (const cb of source.cbs) cb(sloppy(state)); });
  assert.ok(root.innerHTML.includes(EN["error.render"]));
  for (const cb of source.cbs) cb({ ...state, client: "Recovered Client" });
  assert.ok(root.innerHTML.includes("Recovered Client"));
  assert.ok(!root.innerHTML.includes(EN["error.render"]));
});

test("a click handler that throws becomes a notice, not an exception in the event loop", async () => {
  const { root, source, state } = await setup();
  // diagnostics reads state.log; make the next state sloppy only in a field the click path uses
  for (const cb of source.cbs) cb({ ...state, log: null, pipeline: state.pipeline } as unknown as PanelState);
  // render of that state throws -> error view; clicking must still not throw
  assert.doesNotThrow(() => root.click({ "data-action": "copy-diagnostics" }));
  await tick();
});

test("a snapshot that rejects shows an error view; a later pushed state replaces it", async () => {
  const root = new FakeRoot();
  const source = new RecSource();
  const good = await source.snapshot();
  source.snapshot = async () => { throw new Error("daemon unreachable"); };
  const { host } = hostRec();
  const h = mount(root, source, host);
  await h.ready;
  assert.ok(root.innerHTML.includes("daemon unreachable"));
  for (const cb of source.cbs) cb(good);
  assert.ok(root.innerHTML.includes(good.client));
});

test("Reveal folder / Copy diagnostics: a host that did it ('done') gets a short ok notice (EN + AR); a host that showed the box ('shown') or returns nothing gets no banner; a rejection is still an error", async () => {
  for (const [lang, table, opened, copied] of [["en", EN, "Opened.", "Copied."], ["ar", AR, "تم الفتح.", "تم النسخ."]] as const) {
    const source = new RecSource();
    source.inner = new MockSource({ language: lang, scenario: "approval" });
    const host: PanelHost = { ...hostRec().host, revealPath: async () => "done" as const, copyText: async () => "done" as const };
    const root = new FakeRoot();
    await mount(root, source, host).ready;
    assert.equal(table["notice.opened"], opened);
    assert.equal(table["notice.copied"], copied);
    root.click({ "data-action": "reveal" });
    await tick();
    assert.ok(root.innerHTML.includes("banner-ok") && root.innerHTML.includes(opened), `${lang} opened notice`);
    root.click({ "data-action": "copy-diagnostics" });
    await tick();
    assert.ok(root.innerHTML.includes("banner-ok") && root.innerHTML.includes(copied), `${lang} copied notice`);
    assert.ok(!root.innerHTML.includes("banner-error"));
  }
  // the box was shown (or an older host returns nothing): no banner at all, never a red one
  for (const out of ["shown", undefined] as const) {
    const source = new RecSource();
    const host: PanelHost = { ...hostRec().host, revealPath: async () => out as never, copyText: async () => out as never };
    const root = new FakeRoot();
    await mount(root, source, host).ready;
    root.click({ "data-action": "reveal" });
    root.click({ "data-action": "copy-diagnostics" });
    await tick();
    assert.ok(!root.innerHTML.includes("banner-error") && !root.innerHTML.includes("banner-ok"), String(out));
  }
  const source = new RecSource();
  const host: PanelHost = { ...hostRec().host, revealPath: () => { throw new Error("host broke"); } };
  const r2 = new FakeRoot();
  await mount(r2, source, host).ready;
  r2.click({ "data-action": "reveal" });
  await tick();
  assert.ok(r2.innerHTML.includes("banner-error") && r2.innerHTML.includes("host broke"));
});

test("M8: Copy diagnostics carries ui.build (the plugin version and build stamp the shell set)", async () => {
  const { root, calls, handle } = await setup();
  handle.ui.build = { version: "3.0.0", build: "61b12aa 2026-10-12T18:40Z" };
  root.click({ "data-action": "copy-diagnostics" });
  const d = JSON.parse(calls.copy[0]!) as Record<string, unknown>;
  assert.deepEqual(d["plugin"], { version: "3.0.0", build: "61b12aa 2026-10-12T18:40Z" });
});

// ---------------------------------------------------------------------------- C2.2: one sentence + one fix button

test("C2.2 Start engine: a log line (English, in both languages) that names what will run, and the log drawer opens; no throw, no engine call, no notice", async () => {
  const { root, source, handle } = await setup();
  const before = (await source.snapshot()).log.length;
  assert.doesNotThrow(() => root.click({ "data-action": "start-engine" }));
  await tick();
  assert.deepEqual(source.calls, { approve: [], requestChanges: [], run: [], rebuild: [], cancel: [] });
  assert.equal(handle.ui.notice, null);
  assert.equal(handle.ui.logOpen, true, "the press visibly does something: the log drawer opens");
  const lines = [...root.innerHTML.matchAll(/<li class="log-line[^"]*">([\s\S]*?)<\/li>/g)].map((m) => m[1]!);
  assert.equal(lines.length, before + 1, "one more log line");
  const expected = EN["log.start_engine"].replace("{command}", "reel serve --ensure");
  assert.ok(lines.some((l) => l.includes(expected.replace(/'/g, "&#39;"))), "the line names the command (log drawer only)");
  // the panel's own lines go into Copy diagnostics too
  const { calls, root: r2 } = await (async () => {
    const h = hostRec();
    const r = new FakeRoot();
    await mount(r, new RecSource(), h.host).ready;
    return { calls: h.calls, root: r };
  })();
  r2.click({ "data-action": "start-engine" });
  r2.click({ "data-action": "copy-diagnostics" });
  const d = JSON.parse(calls.copy[0]!) as { log: { text: string }[] };
  assert.ok(d.log.some((l) => l.text.includes("reel serve --ensure")));
});

test("C2.2 Try again: a failed engine action's notice carries ONE fix button, Try again, which runs the same action again", async () => {
  const { root, source } = await setup();
  source.nextResult = { ok: false, error: "Premiere is busy.", how: "Wait and retry." };
  root.click({ "data-action": "open-project" });
  await tick();
  const fixes = [...root.innerHTML.matchAll(/class="btn-row banner-fix"><button class="btn btn-secondary" data-action="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(fixes, ["retry"]);
  source.nextResult = { ok: true };
  root.click({ "data-action": "retry" });
  await tick();
  assert.equal(source.calls.run.length, 2);
  assert.deepEqual(source.calls.run[1], source.calls.run[0], "the same request again");
  assert.ok(root.innerHTML.includes("banner-ok"));
  // Try again with nothing to repeat only clears the notice
  const fresh = await setup();
  assert.doesNotThrow(() => fresh.root.click({ "data-action": "retry" }));
});

test("C2.2 Try again after a failed rebuild shows the confirm card again (a rebuild is never re-run unasked)", async () => {
  const { root, source } = await setup();
  source.nextResult = { ok: false, error: "The engine did not answer in time." };
  root.click({ "data-action": "rebuild" });
  root.click({ "data-action": "rebuild-confirm" });
  await tick();
  assert.equal(source.calls.rebuild.length, 1);
  assert.ok(root.innerHTML.includes('data-action="retry"'));
  root.click({ "data-action": "retry" });
  await tick();
  assert.equal(source.calls.rebuild.length, 1, "not sent again");
  assert.ok(root.innerHTML.includes('data-action="rebuild-confirm"'), "the confirm card is back");
});

test("C2.2 the fix button follows the problem: engine offline -> Start engine; a host-only failure -> Try again, never Start engine", async () => {
  const { root, source, state, handle: h0 } = await setup();
  for (const cb of source.cbs) cb({ ...state, connection: { ...state.connection, engine: "offline" } });
  source.nextResult = { ok: false, error: "The WhyNot Cut engine is not connected." };
  root.click({ "data-action": "open-project" });
  await tick();
  assert.equal(h0.ui.notice?.fix, "start-engine");
  // the offline banner already carries Start engine: the notice does not repeat it (one Start engine on the screen)
  assert.equal((root.innerHTML.match(/data-action="start-engine"/g) ?? []).length, 1);
  assert.match(root.innerHTML, /role="alert"[\s\S]*?data-action="start-engine"/);
  assert.doesNotMatch(/<div class="banner banner-error" role="status"[\s\S]*?data-action="dismiss-notice"/.exec(root.innerHTML)![0], /start-engine/);
  const host: PanelHost = { ...hostRec().host, revealPath: () => { throw new Error("host broke"); } };
  const r2 = new FakeRoot();
  const s2 = new RecSource();
  await mount(r2, s2, host).ready;
  for (const cb of s2.cbs) cb({ ...state, connection: { ...state.connection, engine: "offline" } });
  r2.click({ "data-action": "reveal" });
  await tick();
  const notice = /<div class="banner banner-error" role="status"[\s\S]*?data-action="dismiss-notice"/.exec(r2.innerHTML)![0];
  assert.match(notice, /data-action="retry"/);
  assert.doesNotMatch(notice, /start-engine/);
});

test("C2.2 an engine text or how that names a command is not shown: the notice is plain, the full text goes to the log drawer", async () => {
  const { root, source } = await setup();
  source.nextResult = { ok: false, error: "Bridge not ready.", how: "In your Claude session run `reel doctor`." };
  root.click({ "data-action": "open-project" });
  await tick();
  const screen = root.innerHTML;
  assert.ok(screen.includes("Bridge not ready."));
  assert.ok(!screen.includes("reel doctor"), "no command on screen");
  root.click({ "data-action": "toggle-log" });
  assert.ok(root.innerHTML.includes("Bridge not ready. In your Claude session run `reel doctor`."), "kept in the log drawer");
});

test("C2.2 Copy diagnostics names the link diagnosis and the command that fixes it (diagnostics.ts), never on screen", async () => {
  const { root, calls, handle } = await setup();
  handle.ui.link = { code: "no_engine", retry_in_s: 2 };
  root.click({ "data-action": "copy-diagnostics" });
  const d = JSON.parse(calls.copy[0]!) as Record<string, unknown>;
  assert.deepEqual(d["link"], { code: "no_engine", fix: "reel serve --ensure" });
});

// ------------------------------------------------- C2.2 review round 1: Try again belongs to the notice it is on

test("C2.2 r1: a seek during an in-flight rebuild, then Try again on the rebuild's notice, opens the confirm card again (never the seek, never a rebuild)", async () => {
  const { root, source, calls, handle } = await setup();
  let finish!: (r: Result) => void;
  source.rebuild = async (i) => {
    source.calls.rebuild.push(i);
    return new Promise<Result>((r) => { finish = r; });
  };
  root.click({ "data-action": "rebuild" });
  root.click({ "data-action": "rebuild-confirm" });
  await tick();
  root.click({ "data-action": "seek", "data-t": "3" });
  await tick();
  assert.deepEqual(calls.seek, [3]);
  finish({ ok: false, error: "The engine did not answer in time." });
  await tick();
  assert.equal(handle.ui.notice?.fix, "retry");
  assert.deepEqual(handle.ui.notice?.again, { action: "rebuild-confirm", attrs: {} });
  root.click({ "data-action": "retry" });
  await tick();
  assert.deepEqual(calls.seek, [3], "the seek is not run again");
  assert.equal(source.calls.rebuild.length, 1, "no rebuild without the confirm");
  assert.ok(root.innerHTML.includes('data-action="rebuild-confirm"'), "the confirm card is back");
});

test("C2.2 r1: Try again on a failed Request changes sends the text in the box NOW, and its success follow-up runs (the box empties)", async () => {
  const { root, source, state, handle } = await setup();
  root.input("changes", "shorter hook");
  source.nextResult = { ok: false, error: "The engine did not answer in time." };
  root.click({ "data-action": "request-changes" });
  await tick();
  assert.ok(root.innerHTML.includes('data-action="retry"'));
  root.input("changes", "shorter hook, and keep the last line");
  source.nextResult = { ok: true };
  root.click({ "data-action": "retry" });
  await tick();
  assert.deepEqual(source.calls.requestChanges.map((c) => (c as { text: string }).text), ["shorter hook", "shorter hook, and keep the last line"]);
  assert.equal((source.calls.requestChanges[1] as { editor_name: string }).editor_name, state.editor_name);
  assert.equal(handle.ui.changeText, "", "the normal success path ran");
  assert.equal(handle.ui.notice?.kind, "ok");
});

test("C2.2 r2: Try again on a failed Approve replays only while the plan on screen is the one approved; a changed plan is never approved unread", async () => {
  // unchanged: the same approval again
  const a = await setup();
  a.source.nextResult = { ok: false, error: "The engine did not answer in time." };
  a.root.click({ "data-action": "approve", "data-fingerprint": a.state.approval!.fingerprint });
  await tick();
  a.source.nextResult = { ok: true };
  a.root.click({ "data-action": "retry" });
  await tick();
  assert.deepEqual(a.source.calls.approve.map((x) => (x as { fingerprint: string }).fingerprint), [a.state.approval!.fingerprint, a.state.approval!.fingerprint]);
  // changed, or gone: no approval; a short notice says to review it
  for (const next of [{ ...a.state.approval!, fingerprint: "sha256:new-plan" }, null]) {
    const { root, source, state, handle } = await setup();
    source.nextResult = { ok: false, error: "The engine did not answer in time." };
    root.click({ "data-action": "approve", "data-fingerprint": state.approval!.fingerprint });
    await tick();
    for (const cb of source.cbs) cb({ ...state, approval: next });
    source.nextResult = { ok: true };
    root.click({ "data-action": "retry" });
    await tick();
    assert.equal(source.calls.approve.length, 1, "not approved again");
    assert.equal(handle.ui.notice?.kind, "info");
    assert.equal(handle.ui.notice?.text, EN["notice.plan_changed"]);
    assert.ok(root.innerHTML.includes(EN["notice.plan_changed"]), "repainted with the notice");
  }
});

test("C2.2 r1: Try again only runs the notice on screen: after a seek cleared the failed notice, it runs nothing", async () => {
  const { root, source, calls } = await setup();
  source.nextResult = { ok: false, error: "Premiere is busy." };
  root.click({ "data-action": "open-project" });
  await tick();
  root.click({ "data-action": "seek", "data-t": "1" });
  await tick();
  root.click({ "data-action": "retry" });
  await tick();
  assert.deepEqual(calls.seek, [1], "the seek is not run again");
  assert.equal(source.calls.run.length, 1, "open-project is not run again");
});

test("C2.2 r1: an answer that is the same every time (NOT_YET: not available from the panel yet) offers Copy diagnostics, never Try again", async () => {
  for (const r of [
    { ok: false, action: "approve", error: "Approving is not available from the panel yet.", how: "Do this step in your Claude session for now — it will work from the panel after the next update." },
    { ok: false, action: "approve", error: "The engine refused this.", code: "NOT_YET" },
  ] as Result[]) {
    const { root, source, state, handle } = await setup();
    source.nextResult = r;
    root.click({ "data-action": "approve", "data-fingerprint": state.approval!.fingerprint });
    await tick();
    assert.equal(handle.ui.notice?.fix, "copy-diagnostics", String(r.error));
    assert.equal(handle.ui.notice?.again, undefined);
    assert.ok(!root.innerHTML.includes('data-action="retry"'), String(r.error));
    assert.ok(root.innerHTML.includes('class="btn-row banner-fix"><button class="btn btn-secondary" data-action="copy-diagnostics"'), String(r.error));
  }
});

test("C2.2 r2: a how that holds a command is not shown (never cut up); the raw words go to the log, token-scrubbed", async () => {
  const { root, source } = await setup();
  const token = "ab12".repeat(16);
  source.nextResult = { ok: false, error: "Engine refused the key.", how: `Start it with reel serve --ensure --key ${token}, then press Try again.` };
  root.click({ "data-action": "open-project" });
  await tick();
  assert.ok(root.innerHTML.includes('<div class="banner-line">Engine refused the key.</div>'), "the text stays, the how is held back whole");
  assert.ok(!root.innerHTML.includes("Start it, then"), "no cut-up sentence");
  assert.ok(!root.innerHTML.includes("reel serve"));
  root.click({ "data-action": "toggle-log" });
  assert.ok(root.innerHTML.includes("Engine refused the key. Start it with reel serve --ensure --key [token], then press Try again."), "the full words, in the log drawer");
  assert.ok(!root.innerHTML.includes(token), "no token anywhere");
});

test("C2.2 r1: the panel's own log lines scrub a token-looking 64-hex run (as DaemonSource's do), also in Copy diagnostics", async () => {
  const { root, source, calls } = await setup();
  const token = "0123456789abcdef".repeat(4);
  source.nextResult = { ok: false, error: "Bridge not ready.", how: `Run \`reel doctor --token ${token}\` in your session.` };
  root.click({ "data-action": "open-project" });
  await tick();
  root.click({ "data-action": "copy-diagnostics" });
  const d = JSON.parse(calls.copy[0]!) as { log: { text: string }[] };
  const line = d.log.find((l) => l.text.includes("Bridge not ready."));
  assert.ok(line, "the raw words are in the log");
  assert.ok(line!.text.includes("[token]") && !line!.text.includes(token), line!.text);
  assert.ok(!calls.copy[0]!.includes(token));
});

test("C2.2 r1: log merge order is by the full time (epoch ms), not the HH:MM:SS text: a line from before midnight sorts before one after it", () => {
  const now = Date.UTC(2026, 9, 13, 0, 0, 5); // 00:00:05 UTC
  const before = logEpoch({ ts: "23:59:59", level: "info", text: "a" }, now);
  const after = logEpoch({ ts: "00:00:02", level: "info", text: "b" }, now);
  assert.equal(before, Date.UTC(2026, 9, 12, 23, 59, 59), "yesterday, not later today");
  assert.equal(after, Date.UTC(2026, 9, 13, 0, 0, 2));
  assert.ok(before < after && after < now);
  assert.equal(logEpoch({ ts: "x", level: "info", text: "c", at: 42 } as LogLine, now), 42, "a line's own epoch wins");
  assert.equal(logEpoch({ ts: "garbage", level: "info", text: "d" }, now), now);
});

test("C2.2 r1: the panel's own lines sort after older source lines and before newer ones", async () => {
  const { root, source, state } = await setup();
  const earlier = new Date(Date.now() - 30_000).toISOString().slice(11, 19);
  const later = new Date(Date.now() + 30_000).toISOString().slice(11, 19);
  root.click({ "data-action": "start-engine" });
  for (const cb of source.cbs) cb({ ...state, log: [{ ts: later, level: "info", text: "new source line" }, { ts: earlier, level: "info", text: "old source line" }].reverse() as LogLine[] });
  const texts = [...root.innerHTML.matchAll(/<li class="log-line[^"]*"><span class="log-ts">[^<]*<\/span><bdi dir="ltr">([^<]*)<\/bdi><\/li>/g)].map((m) => m[1]!);
  const iOld = texts.indexOf("old source line");
  const iOwn = texts.findIndex((t) => t.startsWith("Start engine pressed."));
  const iNew = texts.indexOf("new source line");
  assert.ok(iOld >= 0 && iOwn > iOld && iNew > iOwn, JSON.stringify(texts));
});

test("C2.2 r1: the Start engine log line is English in the Arabic panel too", async () => {
  const source = new RecSource();
  source.inner = new MockSource({ language: "ar", scenario: "approval" });
  const root = new FakeRoot();
  await mount(root, source, hostRec().host).ready;
  root.click({ "data-action": "start-engine" });
  assert.ok(root.innerHTML.includes("Start engine pressed."));
  assert.equal(AR["log.start_engine"], EN["log.start_engine"], "log lines are English in both tables");
});

// ------------------------------------------------- C2.2 review round 2

test("C2.2 r2: an engine text that holds a command shows the localized sentence for its code; the raw text goes to the log", async () => {
  const { root, source, handle } = await setup();
  source.nextResult = { ok: false, error: "Premiere is not responding. Run reel doctor and press Try again.", code: "no_route" };
  root.click({ "data-action": "open-project" });
  await tick();
  assert.ok(root.innerHTML.includes(EN["notice.code.no_route"]));
  assert.ok(!root.innerHTML.includes("Premiere is not responding."), "never a cut-up sentence");
  assert.equal(handle.ui.notice?.fix, "retry", "the fix button stays");
  root.click({ "data-action": "toggle-log" });
  assert.ok(root.innerHTML.includes("Premiere is not responding. Run reel doctor and press Try again."), "the raw words, in the log drawer");
});

test("C2.2 r2: every plain failure gets a log line too (Copy diagnostics carries it)", async () => {
  const { root, source, calls } = await setup();
  source.nextResult = { ok: false, error: "Premiere is busy.", how: "Wait and retry." };
  root.click({ "data-action": "open-project" });
  await tick();
  root.click({ "data-action": "copy-diagnostics" });
  const d = JSON.parse(calls.copy[0]!) as { log: { text: string; level: string }[] };
  assert.ok(d.log.some((l) => l.text === "Premiere is busy. Wait and retry." && l.level === "error"), JSON.stringify(d.log));
});

test("C2.2 r2: an engine or host text held back from the state (summary, label, step, host detail) is logged once", async () => {
  const { root, source, state } = await setup();
  const raw = "Plan summary: run reel previews --video-id C0239 first.";
  const next: PanelState = { ...state, approval: { ...state.approval!, summary: raw } };
  for (const cb of source.cbs) cb(next);
  for (const cb of source.cbs) cb({ ...next });
  root.click({ "data-action": "toggle-log" });
  const html = root.innerHTML;
  assert.equal(html.split(raw).length - 1, 1, "logged once, in the log drawer only");
  assert.ok(html.includes(EN["text.held"]), "the summary reads the panel's own sentence");
});

test("C2.2 r2: a replay that cannot run says so: missing name, empty box, bad frame time are the normal validation notices, never a silent disappearance", async () => {
  // missing name
  {
    const root = new FakeRoot();
    const source = new RecSource();
    const s = await source.snapshot();
    source.snapshot = async () => ({ ...s, editor_name: "" });
    const h = mount(root, source, hostRec().host);
    await h.ready;
    root.input("editor_name", "Layla");
    source.nextResult = { ok: false, error: "The engine did not answer in time." };
    root.click({ "data-action": "approve", "data-fingerprint": s.approval!.fingerprint });
    await tick();
    root.input("editor_name", "  ");
    root.click({ "data-action": "retry" });
    await tick();
    assert.equal(source.calls.approve.length, 1);
    assert.equal(h.ui.notice?.text, EN["notice.need_name"]);
    assert.ok(root.innerHTML.includes(EN["notice.need_name"]));
  }
  // empty box
  {
    const { root, source, handle } = await setup();
    root.input("changes", "shorter hook");
    source.nextResult = { ok: false, error: "The engine did not answer in time." };
    root.click({ "data-action": "request-changes" });
    await tick();
    root.input("changes", "");
    root.click({ "data-action": "retry" });
    await tick();
    assert.equal(source.calls.requestChanges.length, 1);
    assert.equal(handle.ui.notice?.text, EN["notice.need_changes"]);
  }
  // bad data-t, on a click and on a replay
  {
    const { root, calls, handle } = await setup();
    root.click({ "data-action": "seek", "data-t": "abc" });
    await tick();
    assert.deepEqual(calls.seek, []);
    assert.equal(handle.ui.notice?.text, EN["notice.bad_frame"]);
    handle.ui.notice = { kind: "error", text: "x", fix: "retry", again: { action: "reexport", attrs: { "data-t": "NaN" } } };
    root.click({ "data-action": "retry" });
    await tick();
    assert.equal(handle.ui.notice?.text, EN["notice.bad_frame"]);
  }
});

test("C2.2 r2: a Start engine notice clears itself once the engine connects", async () => {
  const { root, source, state, handle } = await setup();
  const off = { ...state, connection: { ...state.connection, engine: "offline" as const } };
  for (const cb of source.cbs) cb(off);
  source.nextResult = { ok: false, error: "The WhyNot Cut engine is not connected.", code: "no_engine" };
  root.click({ "data-action": "open-project" });
  await tick();
  assert.equal(handle.ui.notice?.fix, "start-engine");
  for (const cb of source.cbs) cb({ ...off, connection: { ...off.connection, engine: "connected" } });
  assert.equal(handle.ui.notice, null);
  assert.ok(!root.innerHTML.includes('role="status"'), "repainted without it");
  // another notice stays
  source.nextResult = { ok: false, error: "Premiere is busy." };
  root.click({ "data-action": "open-project" });
  await tick();
  for (const cb of source.cbs) cb({ ...off, connection: { ...off.connection, engine: "connected" } });
  assert.equal((handle.ui.notice as { text: string } | null)?.text, "Premiere is busy.");
});

// ---------------------------------------------------------------------------------------------------- perf (H3)
test("H3 perf: mount marks the first paint and times a sampled click to the paint it causes", async () => {
  const clock = { t: 1_760_000_000_000 };
  const perf = new PerfRecorder({ now: () => clock.t, random: () => 0 });
  const root = new FakeRoot();
  const source = Object.assign(new RecSource(), { perf });
  const { host } = hostRec();
  clock.t += 30;
  const h = mount(root, source, host);
  await h.ready;
  const s = await source.snapshot();
  clock.t += 5;
  root.input("changes", "shorter hook");
  root.click({ "data-action": "request-changes" });
  await tick();
  root.click({ "data-action": "no-such-action" }); // paints nothing: no sample
  const marks = perf.take();
  assert.deepEqual(marks.map((m) => m.mark), ["panel.boot", "panel.first_paint", "ui.click", "ui.paint"]);
  assert.equal(marks[1]!.ms, 30);
  assert.equal(marks[2]!.rid, marks[3]!.rid);
  assert.equal(typeof marks[3]!.ms, "number");
  assert.equal(source.calls.requestChanges.length, 1);
  assert.ok(s.client);
  h.unmount();
});

test("H3 perf: a source without a recorder (the mock) mounts and clicks as before", async () => {
  const { root, source } = await setup();
  root.click({ "data-action": "no-such-action" });
  assert.ok(root.innerHTML.includes("WhyNot Cut"));
  assert.equal((source as unknown as { perf?: unknown }).perf, undefined);
});
