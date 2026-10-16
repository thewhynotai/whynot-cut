/* Test fixture (never part of ui/): an HTML sink the static scanner cannot see (a computed property name). With
   require-trusted-types-for 'script' the browser must throw (TypeError) and report a violation. */
export default function ({ demo }) {
  const view = demo.shellView({});
  const box = document.createElement("div");
  let res = "allowed";
  try {
    box["inner" + "HTML"] = '<img src="x">';
  } catch (e) {
    res = e instanceof TypeError ? "blocked" : "error:" + e.name;
  }
  view.body.append(box);
  const m = document.createElement("meta");
  m.name = "tt";
  m.content = res;
  document.head.append(m);
  return view;
}
