// The kit's root and footer. The root carries dir/lang and the direction class (RTL is CSS direction on the container,
// never sp-theme dir) and holds ONE scroll region (UXP needs the explicit height chain in kit.css). The footer is
// «Powered by thewhynot.ai» in both languages, as a left-to-right run.
import type { Strings } from "../i18n.ts";
import type { Language } from "../source.ts";
import { ltr, trusted } from "./html.ts";
import type { Html } from "./html.ts";

export function kitRoot(o: { lang: Language; body: Html }): Html {
  const rtl = o.lang === "ar";
  return trusted(`<div class="kit-root ${rtl ? "kit-rtl" : "kit-ltr"}" dir="${rtl ? "rtl" : "ltr"}" lang="${rtl ? "ar" : "en"}"><div class="kit-scroll">${o.body}</div></div>`);
}

export const footer = (t: Strings): Html => trusted(`<footer class="kit-foot">${ltr(t["footer.powered"])}</footer>`);
