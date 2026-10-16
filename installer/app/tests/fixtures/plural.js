/* Test fixture (never part of ui/): which string form I.plural picks for 0, 1, 2, 3, 10, 11, 100 and the STRING "2"
   (host JSON), written to <meta name="plural" content="<n>=<key> …">; each form is drawn too. */
const NS = [["0", 0], ["1", 1], ["2", 2], ["3", 3], ["10", 10], ["11", 11], ["100", 100], ["s2", "2"]];

export default function ({ demo, I }) {
  const view = demo.shellView({});
  const out = [];
  for (const [label, n] of NS) {
    out.push(label + "=" + I.pluralKey("i04.amber.fonts", n));
    const d = document.createElement("div");
    d.className = "t-meta";
    d.append(I.plural("i04.amber.fonts", n));
    view.body.append(d);
  }
  const m = document.createElement("meta");
  m.name = "plural";
  m.content = out.join(" ");
  document.head.append(m);
  return view;
}
