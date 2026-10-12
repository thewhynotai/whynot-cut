// The header: TWN monogram + "WhyNot Cut", the Needs-you badge (things only the editor can do; opens NEEDS-YOU.md)
// and the ع / EN language switch, over the pink-to-violet gradient hairline. The shell remembers the chosen language
// per editor (data-action="set-language", data-lang); the kit only shows which one is on.
import { fmt } from "../i18n.ts";
import type { Strings } from "../i18n.ts";
import { MONOGRAM_DATA_URI } from "../monogram.ts";
import type { Language } from "../source.ts";
import { esc, ltr, trusted } from "./html.ts";
import type { Html } from "./html.ts";

export interface HeaderOpts {
  t: Strings;
  lang: Language;
  /** how many things need the editor; 0 (or not a positive number) hides the badge */
  needsYou?: number;
}

const SHORT = { ar: "lang.ar.short", en: "lang.en.short" } as const;

export function langSwitch(t: Strings, lang: Language): Html {
  const one = (l: Language) =>
    `<button type="button" class="kit-lang-btn kit-lang-${l} kit-focus${l === lang ? " kit-lang-on" : ""}" data-action="set-language" data-lang="${l}" lang="${l}" aria-pressed="${l === lang ? "true" : "false"}" aria-label="${esc(t[`lang.${l}`])}">${esc(t[SHORT[l]])}</button>`;
  return trusted(`<div class="kit-lang" role="group" aria-label="${esc(t["lang.group"])}">${one("ar")}${one("en")}</div>`);
}

export function needsYouBadge(t: Strings, count: unknown): Html | "" {
  const n = typeof count === "number" && Number.isFinite(count) ? Math.floor(count) : 0;
  if (n <= 0) return "";
  return trusted(
    `<button type="button" class="kit-badge kit-focus" data-action="open-needs-you" aria-label="${esc(fmt(t["needs.aria"], { n }))}">` +
      `<span class="kit-badge-label">${esc(t["needs.label"])}</span><span class="kit-badge-count">${ltr(n)}</span></button>`,
  );
}

export function header(o: HeaderOpts): Html {
  return trusted(
    `<header class="kit-hdr"><div class="kit-hdr-row">` +
      `<img class="kit-mono" src="${MONOGRAM_DATA_URI}" alt="" width="24" height="24">` +
      `<span class="kit-wordmark">${ltr(o.t["product.name"])}</span>` +
      `<span class="kit-hdr-spacer"></span>` +
      `<div class="kit-hdr-end">${needsYouBadge(o.t, o.needsYou)}${langSwitch(o.t, o.lang)}</div>` +
      `</div><div class="kit-hairline" aria-hidden="true"></div></header>`,
  );
}
