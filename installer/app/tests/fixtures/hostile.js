/* Test fixture: staged at <stage>/fixtures/ by tests/_harness.py, never part of ui/.
   Hostile data in the places a real install shows data: a folder named like HTML (a legal macOS name) and bidi
   controls (RLO, RLI/PDI) that would reorder a path or a file name on screen. All of it must render as inert text. */
const HTML = "<img src=x onerror=alert(1)>";
const RLO = "\u202E", RLI = "\u2067", PDI = "\u2069";

export default function ({ demo }) {
  return demo.shellView({
    path: "/Users/editor/" + HTML + "/Clients/" + RLO + "4pm.exe",
    name: HTML + " " + RLO + "evil",
    mono: "/Users/editor/" + HTML + "/" + RLI + "x" + PDI + RLO + "gpj.ccx"
  });
}
