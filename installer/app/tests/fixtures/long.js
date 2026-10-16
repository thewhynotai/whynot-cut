/* Test fixture (never part of ui/), review round 2 (N3): 200 000 characters of hostile data (paragraph separators
   between letters, then a long Latin run) through every data place: the path field, a step name (I.name), a mono box,
   a T() string var, I.ltr, I.mono and I.path. The page must still render quickly; what is shown is capped (with an
   ellipsis) and the full value, also neutralised and capped, is the title. */
const BIG = "a\u2029".repeat(50000) + "W".repeat(100000);

export default function ({ demo, I }) {
  const view = demo.shellView({ path: BIG, name: BIG, mono: BIG });
  const d = document.createElement("div");
  d.className = "t-meta probe-long i-clip";
  d.append(I.T("i03.disk.ok", { free: BIG, drive: I.ltr(BIG), gb: I.gb(2) }), " ", I.mono(BIG), " ", I.path(BIG));
  view.body.append(d);
  return view;
}
