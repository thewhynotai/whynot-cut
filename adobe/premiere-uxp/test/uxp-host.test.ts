import { test } from "node:test";
import assert from "node:assert/strict";
import { cleanPath, createUxpHost } from "../src/uxp-host.ts";
import type { UxpHostDeps } from "../src/uxp-host.ts";
import { showCopyText } from "../src/copy-fallback.ts";

interface Shown {
  text: string;
  title: string;
}

function makeDeps(over: Partial<{
  ppro: unknown;
  shell: unknown;
  clip: ((t: string) => Promise<void>) | undefined;
  lang: "en" | "ar";
}> = {}) {
  const shown: Shown[] = [];
  const calls: string[] = [];
  const seq = {
    setPlayerPosition: async (t: { seconds: number }) => {
      calls.push(`seek ${t.seconds}`);
      return true;
    },
  };
  const ppro = over.ppro ?? {
    Project: { getActiveProject: async () => ({ getActiveSequence: async () => seq }) },
    TickTime: { createWithSeconds: (seconds: number) => ({ seconds }) },
    SourceMonitor: { openFilePath: async (p: string) => (calls.push(`open ${p}`), true) },
  };
  const deps: UxpHostDeps = {
    getPpro: () => ppro as never,
    getShell: () => over.shell as never,
    clipboardWriteText: "clip" in over ? over.clip : async (t) => void calls.push(`clip ${t}`),
    showText: (text, title) => void shown.push({ text, title }),
    language: () => over.lang ?? "en",
  };
  return { deps, shown, calls, seq };
}

test("setPlayerPosition: moves the active sequence's playhead to t_s seconds (TickTime.createWithSeconds)", async () => {
  const { deps, calls } = makeDeps();
  await createUxpHost(deps).setPlayerPosition(21.4);
  assert.deepEqual(calls, ["seek 21.4"]);
});

test("setPlayerPosition: refuses a bad time, no project, no sequence and a false return with a plain sentence", async () => {
  const host = (ppro: unknown) => createUxpHost(makeDeps({ ppro }).deps);
  await assert.rejects(() => host(undefined).setPlayerPosition(Number.NaN), /time/i);
  await assert.rejects(() => host(undefined).setPlayerPosition(-1), /time/i);
  const noProject = { Project: { getActiveProject: async () => { throw new Error("no project"); } }, TickTime: {} };
  await assert.rejects(() => host(noProject).setPlayerPosition(1), /open a project/i);
  const noSeq = { Project: { getActiveProject: async () => ({ getActiveSequence: async () => undefined }) }, TickTime: {} };
  await assert.rejects(() => host(noSeq).setPlayerPosition(1), /sequence/i);
  const refused = {
    Project: { getActiveProject: async () => ({ getActiveSequence: async () => ({ setPlayerPosition: async () => false }) }) },
    TickTime: { createWithSeconds: (s: number) => ({ s }) },
  };
  await assert.rejects(() => host(refused).setPlayerPosition(1), /did not move/i);
});

test("openInSourceMonitor: SourceMonitor.openFilePath(path); a false return is an error", async () => {
  const { deps, calls } = makeDeps();
  await createUxpHost(deps).openInSourceMonitor("E:/x/preview.mp4");
  assert.deepEqual(calls, ["open E:/x/preview.mp4"]);
  const bad = makeDeps({ ppro: { SourceMonitor: { openFilePath: async () => false } } });
  await assert.rejects(() => createUxpHost(bad.deps).openInSourceMonitor("E:/x/preview.mp4"), /source monitor/i);
});

test("copyText: uses the clipboard when the plugin may", async () => {
  const { deps, calls, shown } = makeDeps();
  await createUxpHost(deps).copyText("hello");
  assert.deepEqual(calls, ["clip hello"]);
  assert.deepEqual(shown, []);
});

test("copyText: no clipboard permission (the call throws) -> the text is shown to copy by hand, and the panel is told", async () => {
  for (const clip of [
    async () => { throw new Error("clipboard permission is not granted"); },
    undefined,
  ]) {
    const { deps, shown } = makeDeps({ clip });
    await assert.rejects(() => createUxpHost(deps).copyText("diagnostics text"), /copy/i);
    assert.equal(shown.length, 1);
    assert.equal(shown[0]!.text, "diagnostics text");
  }
});

test("copyText: Arabic panel gets the Arabic explanation", async () => {
  const { deps, shown } = makeDeps({ clip: undefined, lang: "ar" });
  await assert.rejects(() => createUxpHost(deps).copyText("t"), /[؀-ۿ]/);
  assert.match(shown[0]!.title, /[؀-ۿ]/);
});

test("revealPath: shell.openPath on the folder; an empty answer is success", async () => {
  const opened: string[] = [];
  const { deps, shown } = makeDeps({ shell: { openPath: async (p: string) => (opened.push(p), "") } });
  await createUxpHost(deps).revealPath("E:\\Clients\\X");
  assert.deepEqual(opened, ["E:\\Clients\\X"]);
  assert.deepEqual(shown, []);
});

test("revealPath: openPath that throws, answers with an error string or is missing -> the path is shown", async () => {
  for (const shell of [
    { openPath: async () => { throw new Error("denied"); } },
    { openPath: async () => "Permission denied" },
    {},
    undefined,
  ]) {
    const { deps, shown } = makeDeps({ shell });
    await assert.rejects(() => createUxpHost(deps).revealPath("\\\\?\\E:\\Clients\\X"), /path/i);
    assert.equal(shown[0]!.text, "E:\\Clients\\X","the long-path prefix is not shown to the editor");
  }
});

test("cleanPath strips the Windows long-path prefixes Premiere returns", () => {
  assert.equal(cleanPath("\\\\?\\D:/work/a.prproj"), "D:/work/a.prproj");
  assert.equal(cleanPath("//?/D:/work"), "D:/work");
  assert.equal(cleanPath("\\\\?\\UNC\\srv\\share\\a"), "\\\\srv\\share\\a");
  assert.equal(cleanPath("/Users/x/a"), "/Users/x/a");
});

// ---- the visible "copy this" box -------------------------------------------------------------------------------

class FakeEl {
  children: FakeEl[] = [];
  attrs: Record<string, string> = {};
  listeners: Record<string, () => void> = {};
  className = "";
  textContent = "";
  value = "";
  readOnly = false;
  selected = false;
  removed = false;
  tag: string;
  doc: FakeDoc;
  constructor(tag: string, doc: FakeDoc) {
    this.tag = tag;
    this.doc = doc;
  }
  appendChild(c: FakeEl) { this.children.push(c); return c; }
  setAttribute(k: string, v: string) { this.attrs[k] = v; }
  addEventListener(t: string, fn: () => void) { this.listeners[t] = fn; }
  select() { this.selected = true; }
  focus() {}
  remove() { this.removed = true; this.doc.byId.delete(this.attrs["id"] ?? ""); this.doc.body.children = this.doc.body.children.filter((c) => c !== this); }
}
class FakeDoc {
  byId = new Map<string, FakeEl>();
  body = new FakeEl("body", this);
  execCalls: string[] = [];
  createElement(tag: string) { return new FakeEl(tag, this); }
  getElementById(id: string) { return this.byId.get(id) ?? null; }
  execCommand(c: string) { this.execCalls.push(c); return false; }
  register(el: FakeEl) { this.byId.set(el.attrs["id"] ?? "", el); }
}

test("showCopyText: a readonly selected textarea with the text, a title and a Close button, appended to the page", () => {
  const doc = new FakeDoc();
  const origAppend = doc.body.appendChild.bind(doc.body);
  doc.body.appendChild = (c: FakeEl) => (doc.register(c), origAppend(c));
  showCopyText(doc as never, "the text", "Copy this", "Close");
  const box = doc.body.children[0]!;
  assert.equal(box.attrs["id"], "wnc-copy");
  const area = box.children.find((c) => c.tag === "textarea")!;
  assert.equal(area.value, "the text");
  assert.equal(area.readOnly, true);
  assert.equal(area.selected, true);
  assert.ok(box.children.some((c) => c.tag === "p" && c.textContent === "Copy this"));
  const close = box.children.find((c) => c.tag === "button")!;
  assert.equal(close.textContent, "Close");
  close.listeners["click"]!();
  assert.equal(box.removed, true);
  // showing again replaces, never stacks
  showCopyText(doc as never, "one", "t", "c");
  showCopyText(doc as never, "two", "t", "c");
  assert.equal(doc.body.children.length, 1);
});
