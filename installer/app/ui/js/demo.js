/* The demo entry (index.html?demo=shell[&fixture=<name>]): the window shell with a placeholder body that uses every
   shared component once, for the UI tests and for a person looking at the shell. It is not a screen: the real screens
   (ET1-10..12) replace it, and the host interface (ET1-09) decides what is shown. The values below are mock data, as in
   the mockups (I_DATA); the copy comes from the string table only.
   &fixture=<name> loads <bundle>/fixtures/<name>.js, which exists only in a test staging (tests/fixtures/); its default
   export gets {demo, I, mount} and returns a view. A name is letters, digits and hyphens only. */
import { C } from "./ctx.js";
import { I, T, frag, h, mount } from "./shell.js";

export const VERSION = "3.0.0";
const DEFAULTS = { path: "/Users/editor/WhyNot Clients", name: null, mono: "WhyNotCut-Premiere-3.0.0.ccx" };

export function shellView(d) {
  d = Object.assign({}, DEFAULTS, d || {});
  const drive = C.os === "win" ? "C:" : "Macintosh HD";
  const rows = [
    I.step("ok", T("i03.disk"), { detail: T("i03.disk.ok", { free: I.gb(118.4), drive: I.ltr(drive), gb: I.gb(3.6) }) }),
    I.step("busy", T("i03.system"), { prog: { pct: 42, time: "0:42",
      meta: T("i04.run.engine", { what: T("i04.what.video"), done: I.mb(126), total: I.mb(300) }) } }),
    I.step("warn", d.name ? I.name(d.name) : T("i03.gpu"), { detail: I.plural("i04.amber.fonts", 2) }),
    I.step("pending", T("i03.gpu"))
  ];
  const body = frag(
    I.title(T("i03.title")),
    I.list(rows, "mt-4"),
    h("div", { class: "i-sec" },
      h("div", { class: "t-label" }, T("i02.model")),
      h("div", { class: "t-meta tx-muted mt-1" }, T("i02.model.sub")),
      h("div", { class: "m-col mt-2", role: "radiogroup" },
        I.radio(T("i02.model.large"), { on: true, size: I.gb(2.9) }),
        I.radio(T("i02.model.turbo"), { size: I.gb(1.6) }))),
    h("div", { class: "i-sec" }, I.pathField(T("i02.clients"), d.path, { sub: T("i02.clients.sub") })),
    /* a danger and a destructive button, both ASKED for the Return keycap: btn() must refuse it (the self-check's
       dangerkbd must stay 0 with something to count) */
    h("div", { class: "i-sec" }, I.act("waiting", T("i04.act.ccx.title"), T("i04.act.ccx"), { mono: d.mono,
      btns: [I.btn(T("i04.act.ccx.btn"), { icon: "file-search" }),
        h("span", { class: "ms-2" }), I.btn(T("i00.cancel"), { kind: "danger", key: "enter" }),
        h("span", { class: "ms-2" }), I.btn(T("i00.close"), { destructive: true, key: "enter" })],
      hint: T("i04.act.ccx.hint") })),
    h("div", { class: "i-sec" }, I.fail(T("i07.checksum"), { sub: T("i07.checksum.sub"), safety: true,
      btn: I.btn(T("i00.retry"), { icon: "refresh-cw" }) })));
  return {
    state: "shell",
    version: VERSION,
    rail: { flow: "install", at: "check", custom: true, claude: true },
    body,
    bar: { start: [I.btn(T("i00.back"), { key: "esc" })], end: [I.btn(T("i00.continue"), { kind: "primary", key: "enter" })] }
  };
}

export async function fixtureView(name) {
  if (!/^[a-z0-9-]{1,40}$/.test(name)) throw new Error("bad fixture name");
  const mod = await import("../fixtures/" + name + ".js");
  const view = mod.default({ demo: { shellView }, I, mount });
  view.state = "shell:" + name;
  return view;
}
