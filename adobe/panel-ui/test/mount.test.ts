import { test } from "node:test";
import assert from "node:assert/strict";
import { mount } from "../src/mount.ts";
import type { MountRoot, PanelElement } from "../src/mount.ts";
import type { PanelHost } from "../src/host.ts";
import type { PanelDataSource, PanelState, Result } from "../src/source.ts";
import { MockSource } from "../src/mock.ts";
import type { ActionName } from "../src/contract.ts";

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

interface Calls { approve: unknown[]; requestChanges: unknown[]; run: { action: ActionName; data: object }[]; cancel: string[] }
class RecSource implements PanelDataSource {
  calls: Calls = { approve: [], requestChanges: [], run: [], cancel: [] };
  cbs: ((s: PanelState) => void)[] = [];
  inner = new MockSource({ language: "en", scenario: "approval" });
  nextResult: Result = { ok: true };
  snapshot() { return this.inner.snapshot(); }
  subscribe(cb: (s: PanelState) => void) { this.cbs.push(cb); return () => { this.cbs = this.cbs.filter((c) => c !== cb); }; }
  async approve(i: { item: string; editor_name: string; fingerprint: string }) { this.calls.approve.push(i); return this.nextResult; }
  async requestChanges(i: { item: string; editor_name: string; text: string }) { this.calls.requestChanges.push(i); return this.nextResult; }
  async run(action: ActionName, data: object) { this.calls.run.push({ action, data }); return this.nextResult; }
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

test("Rebuild asks in-panel first; only the confirm runs build_project", async () => {
  const { root, source } = await setup();
  root.click({ "data-action": "rebuild" });
  await tick();
  assert.equal(source.calls.run.length, 0);
  assert.ok(root.innerHTML.includes('data-action="rebuild-confirm"'));
  root.click({ "data-action": "rebuild-cancel" });
  assert.ok(!root.innerHTML.includes('data-action="rebuild-confirm"'));
  assert.equal(source.calls.run.length, 0);
  root.click({ "data-action": "rebuild" });
  root.click({ "data-action": "rebuild-confirm" });
  await tick();
  assert.equal(source.calls.run.length, 1);
  assert.equal(source.calls.run[0]!.action, "build_project");
  assert.equal((source.calls.run[0]!.data as { overwrite_existing: boolean }).overwrite_existing, true);
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
