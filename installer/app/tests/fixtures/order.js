/* Test fixture (never part of ui/): the DRAWN order of data in a sentence (review F1). For every character the UI
   neutralises, "XQ<char>QZ" goes through each data helper inside a real sentence; once the fonts are in, a Range per
   character measures where "X" and "Z" are drawn. The data is Latin, so X must be drawn left of Z, in Arabic too.
   Written to <meta name="order" content="<code>/<helper>=intact|BROKEN …">. The probe lines do not wrap (CSSOM
   nowrap) and sit in an .i-clip box, so line breaks cannot fake a result and the overflow check skips them. */
const CODES = [0x00, 0x01, 0x08, 0x0A, 0x0B, 0x0C, 0x0D, 0x1C, 0x1D, 0x1E, 0x1F, 0x7F, 0x80, 0x85, 0x9F, 0x061C,
  0x200B, 0x200E, 0x200F, 0x2028, 0x2029, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2060, 0x2066, 0x2067, 0x2068,
  0x2069, 0xFEFF, 0xE000, 0xE001];

function where(el, ch, last) {
  const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  let hit = null;
  for (let n = walk.nextNode(); n; n = walk.nextNode()) {
    const i = last ? n.data.lastIndexOf(ch) : n.data.indexOf(ch);
    if (i >= 0) { hit = [n, i]; if (!last) break; }
  }
  if (!hit) return null;
  const r = document.createRange();
  r.setStart(hit[0], hit[1]);
  r.setEnd(hit[0], hit[1] + 1);
  return r.getBoundingClientRect();
}

export default function ({ demo, I }) {
  const view = demo.shellView({});
  const box = document.createElement("div");
  box.className = "m-col i-clip";
  view.body.append(box);
  const probes = [];
  const line = (label, ...kids) => {
    const d = document.createElement("div");
    d.className = "t-meta";
    d.style.whiteSpace = "nowrap";
    d.append(...kids);
    box.append(d);
    probes.push([label, d]);
  };
  for (const c of CODES) {
    const code = c.toString(16).toUpperCase().padStart(4, "0");
    const v = "XQ" + String.fromCharCode(c) + "QZ";
    line(code + "/ltr", I.T("i03.disk.ok", { free: I.gb(1), drive: I.ltr(v), gb: I.gb(2) }));
    line(code + "/name", I.T("i03.gpu"), " ", I.name(v), " ", I.T("i03.gpu"));
    line(code + "/var", I.T("i03.disk.ok", { free: v, drive: I.ltr("C:"), gb: I.gb(2) }));
    line(code + "/mono", I.T("i04.elapsed", { time: I.mono(v) }));
    line(code + "/app", I.T("i03.gpu"), " ", I.T("i00.version", { app: I.app(v) }));
    line(code + "/box", I.T("i04.act.ccx"), " ", I.monoBox(v));
  }
  document.fonts.ready.then(() => setTimeout(() => {
    const out = probes.map(([label, el]) => {
      const x = where(el, "X", false), z = where(el, "Z", true);
      const ok = x && z && Math.abs(x.top - z.top) < 2 && x.left < z.left;
      return label + "=" + (ok ? "intact" : "BROKEN");
    });
    const m = document.createElement("meta");
    m.name = "order";
    m.content = out.join(" ");
    document.head.append(m);
  }, 30)); /* before the self-check (fonts.ready + 50 ms), so a dump that has the check has this too */
  return view;
}
