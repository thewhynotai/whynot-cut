/* Test fixture: staged at <stage>/fixtures/ by tests/_harness.py, never part of ui/.
   Hostile data in the places a real install shows data: a folder named like HTML (a legal macOS name), bidi controls
   (RLO, RLI/PDI) and every other character the UI must neutralise (C0 but TAB, DEL, C1, ALM, ZWSP, LRM, RLM, LS, PS,
   LRE..RLO, WJ, LRI..PDI, BOM, the two placeholder code points). All of it must render as inert text: shown as
   [U+XXXX], never applied. ZWJ (U+200D) is left alone. */
const HTML = "<img src=x onerror=alert(1)>";
const RLO = "\u202E", RLI = "\u2067", PDI = "\u2069";
const ALL = "\u0000\u0001\u0008\u000A\u000B\u000C\u000D\u001C\u001D\u001E\u001F\u007F\u0080\u0085\u009F\u061C" +
  "\u200B\u200E\u200F\u2028\u2029\u202A\u202B\u202C\u202D\u202E\u2060\u2066\u2067\u2068\u2069\uFEFF\uE000\uE001";

export default function ({ demo, I }) {
  const view = demo.shellView({
    path: "/Users/editor/" + HTML + "/Clients/" + RLO + "4pm.exe" + ALL,
    name: HTML + " " + RLO + "evil" + ALL,
    mono: "/Users/editor/" + HTML + "/" + RLI + "x" + PDI + RLO + "gpj.ccx" + ALL
  });
  // a data STRING var beside a Node var: the string tries to forge the Node's placeholder (\uE000 0 \uE001)
  const line = document.createElement("div");
  line.className = "t-meta probe-var";
  line.append(I.T("i03.disk.ok", { free: "\uE0000\uE001" + ALL, drive: I.ltr("NODEVAR"), gb: I.gb(2) }));
  view.body.append(line);
  // every data helper, fed every character (ZWJ included, which must stay)
  const v = "d" + ALL + "\u200D" + "e";
  const helpers = document.createElement("div");
  helpers.className = "t-meta probe-helper";
  helpers.append(I.ltr(v), " ", I.name(v), " ", I.mono(v), " ", I.app(v), " ", I.ver(v), " ", I.path(v), " ",
    I.path(v, true), " ", I.monoBox(v), " ", I.data(v));
  view.body.append(helpers);
  return view;
}
