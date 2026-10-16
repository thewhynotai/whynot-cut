/* Entry module. Reads the page's own query (the app host passes none; ET1-09's host interface takes over from here):
   lang=ar|en (default en), os=mac|win (default mac, G11), chrome=none (no drawn title bar), support=off (the D-05
   alternate: support.url absent), demo=shell[&fixture=<name>] (the demo body, demo.js). Without demo= the shell is
   mounted empty ("idle"), waiting for the host. */
import { C } from "./ctx.js";
import STRINGS from "./strings.js";
import { mount } from "./shell.js";
import { fixtureView, shellView } from "./demo.js";

const q = new URLSearchParams(location.search);
C.lang = q.get("lang") === "ar" ? "ar" : "en";
C.rtl = C.lang === "ar";
C.os = q.get("os") === "win" ? "win" : "mac";
C.chrome = q.get("chrome") !== "none";
C.S = STRINGS[C.lang];
C.cfg.supportLive = q.get("support") !== "off";

let view = { state: "idle" };
if (q.get("demo") === "shell") {
  const fx = q.get("fixture");
  view = fx ? await fixtureView(fx) : shellView();
}
mount(view);
