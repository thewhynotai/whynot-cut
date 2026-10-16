/* Test fixture (never part of ui/), review round 2 (N5): pins both parts of the one-self-check rule.
   main.js mounts the returned view A (with a missing key). Once A's self-check has been WRITTEN, B is mounted (another
   missing key) and right after that the number of self-check metas is read: it must be 0 (the removal at mount). Then
   C is mounted before B's check settles: B's late check must never write (the generation check). A MutationObserver
   records the state of every self-check ever written; <meta name="remount"> = "afterB=<n> writes=<s1>,<s2>,…". */
export default function ({ demo, I, mount }) {
  const writes = [];
  let afterB = -1;
  const count = () => document.querySelectorAll('meta[name="mock-check"]').length;
  const obs = new MutationObserver((recs) => {
    for (const r of recs) {
      for (const n of r.addedNodes) {
        if (n.nodeName !== "META" || n.name !== "mock-check") continue;
        const st = (n.content.match(/state=([^;]*)/) || [])[1];
        writes.push(st);
        if (st === "shell:remount-late") {
          setTimeout(() => {
            const b = demo.shellView({});
            b.state = "B";
            b.body.append(I.T("no.such.key.B"));
            mount(b);
            afterB = count();
            const c = demo.shellView({});
            c.state = "C";
            mount(c);
          }, 0);
        } else if (st === "C") {
          const m = document.createElement("meta");
          m.name = "remount";
          m.content = "afterB=" + afterB + " writes=" + writes.join(",");
          document.head.append(m);
        }
      }
    }
  });
  obs.observe(document.head, { childList: true });
  const a = demo.shellView({});
  a.body.append(I.T("no.such.key.A"));
  return a;
}
