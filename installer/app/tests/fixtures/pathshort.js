/* Test fixture (never part of ui/): I.pathShort on the cases of tests/pathshort.json (copied here as a literal; the test
   checks both lists are the same) at both budgets, and one path field with a long path (its shown text depends on the
   window width: 46 characters at 760, 38 below). Results go to <meta name="pathshort"> as encodeURIComponent pieces. */
const CASES = ["/Users/sara/Documents/Clients/2026/Acme Corp/Raw footage", "D:\\WhyNot Cut\\clients\\2026\\October\\Acme\\Raw", "/Volumes/Samsung T7 Shield/Clients/2026/Acme/Raw footage", "/Users/editor/WhyNot Clients", "/a/b", "/Users/a-very-long-account-name-here/Clients/x/y/Final", "C:\\Users\\editor\\AppData\\Local\\a-very-very-long-folder-name-that-is-longer-than-the-budget", "/Library/Application Support/WhyNot Cut/models/whisper/large-v3", "/Users/sara/Clients/", "~/Movies/WhyNot Clients/Acme Productions International/Raw footage", "D:\\Clients\\Acme\\", "\\\\server\\share\\Clients\\2026\\October\\Acme Productions\\Raw"];
const LONG = "/Users/sara/Documents/Clients/2026/Acme Corp/Raw footage";

export default function ({ demo, I }) {
  const view = demo.shellView({ path: LONG });
  const out = [];
  for (const b of [46, 38]) CASES.forEach((c, i) => out.push(b + ":" + i + ":" + encodeURIComponent(I.pathShort(c, b))));
  CASES.forEach((c, i) => out.push("case:" + i + ":" + encodeURIComponent(c)));
  const m = document.createElement("meta");
  m.name = "pathshort";
  m.content = out.join(" ");
  document.head.append(m);
  return view;
}
