// Buttons: primary (violet #5400FB fill, white text; ONE per screen, see primaryCount), secondary (glass), danger
// (destructive confirm; it carries the warn icon by default, so the status colour is never alone). Every button is
// type="button", at least 32 px (kit.css), carries the focus-ring class and a data-action the shell reads by event
// delegation. The main CTA may get the gradient border glow. A directional icon (chevron-start / chevron-end) needs
// the panel's direction (rtl), required by the type and checked at run time, so a chevron never points the wrong way.
import { dataAttrs, esc, join, trusted } from "./html.ts";
import type { Act, Html } from "./html.ts";
import { icon, isDirectional } from "./icons.ts";
import type { DirectionalIcon, IconName } from "./icons.ts";

export type ButtonVariant = "primary" | "secondary" | "danger";
const VARIANTS: readonly ButtonVariant[] = ["primary", "secondary", "danger"];

interface ButtonBase extends Act {
  /** default secondary */
  variant?: ButtonVariant;
  /** full width */
  block?: boolean;
  /** the screen's main CTA: a gradient border glow (primary only) */
  glow?: boolean;
  /** required when the label is empty (an icon-only button) */
  ariaLabel?: string;
}

/** A non-directional icon (default: none; warn for a danger button); a directional one comes with the direction. */
type ButtonIcon = { icon?: Exclude<IconName, DirectionalIcon>; rtl?: boolean } | { icon: DirectionalIcon; rtl: boolean };

export type ButtonOpts = ButtonBase & ButtonIcon;

export function button(o: ButtonOpts): Html {
  const variant: ButtonVariant = o.variant && VARIANTS.includes(o.variant) ? o.variant : "secondary";
  if (isDirectional(o.icon) && typeof o.rtl !== "boolean") throw new Error(`kit.button.rtl-required=${o.icon}`);
  const name: IconName | undefined = o.icon ?? (variant === "danger" ? "warn" : undefined);
  const aria = o.ariaLabel ? ` aria-label="${esc(o.ariaLabel)}"` : "";
  const ic = name ? icon(name, { rtl: o.rtl === true }) : "";
  const label = o.label !== "" ? `<span class="kit-btn-label">${esc(o.label)}</span>` : "";
  const btn = `<button type="button" class="kit-btn kit-btn-${variant} kit-focus${o.block ? " kit-btn-block" : ""}" data-action="${esc(o.action)}"${dataAttrs(o.data)}${aria}${o.disabled ? " disabled" : ""}>${ic}${label}</button>`;
  if (o.glow && variant === "primary") return trusted(`<span class="kit-glow${o.block ? " kit-glow-block" : ""}">${btn}</span>`);
  return trusted(btn);
}

/** Buttons side by side, wrapping on a narrow panel. */
export const buttonRow = (buttons: readonly Html[]): Html => trusted(`<div class="kit-btn-row">${join(buttons)}</div>`);

/** How many primary buttons a piece of kit markup holds (Addendum B4: at most ONE per screen). */
export function primaryCount(html: string): number {
  let n = 0;
  for (const m of html.matchAll(/<button\b[^>]*\bclass="([^"]*)"/g)) if (m[1]!.split(/\s+/).includes("kit-btn-primary")) n++;
  return n;
}
