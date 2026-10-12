// Cards and sections. A card is glass rgba(255,255,255,.08) over the black background, with the 14% border and the
// 16 px radius (the card ruling in brand/tokens.css); it is never put on a #121212 surface. A section is a titled block
// on the background (pink uppercase eyebrow). A paragraph keeps `commands` left-to-right.
import { auto, esc, trusted, withCommands } from "./html.ts";
import type { Html } from "./html.ts";

export type CardTone = "neutral" | "ok" | "warn" | "error";
const TONES: readonly CardTone[] = ["ok", "warn", "error"];

export interface CardOpts {
  body: Html;
  /** small pink uppercase label above the title */
  eyebrow?: string;
  title?: string;
  /** a status border (with an icon in the body, never colour alone) */
  tone?: CardTone;
}

/** Titles are isolated runs (<bdi>): a title that starts with a Latin word keeps its order inside Arabic and vice versa. */
export const eyebrow = (text: string): Html => trusted(`<div class="kit-eyebrow">${auto(text)}</div>`);

export const paragraph = (text: string): Html => trusted(`<p class="kit-text">${withCommands(text)}</p>`);

export function card(o: CardOpts): Html {
  const tone = o.tone && TONES.includes(o.tone) ? ` kit-card-${o.tone}` : "";
  const name = o.title ?? o.eyebrow;
  return trusted(
    `<section class="kit-card${tone}"${name ? ` aria-label="${esc(name)}"` : ""}>` +
      (o.eyebrow ? eyebrow(o.eyebrow) : "") +
      (o.title ? `<h3 class="kit-card-title">${auto(o.title)}</h3>` : "") +
      `<div class="kit-card-body">${o.body}</div></section>`,
  );
}

export function section(o: { title: string; body: Html }): Html {
  return trusted(`<section class="kit-section" aria-label="${esc(o.title)}"><h2 class="kit-eyebrow">${auto(o.title)}</h2>${o.body}</section>`);
}
