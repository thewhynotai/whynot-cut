// Buttons: primary (violet #5400FB fill, white text; ONE per screen), secondary (glass), danger (destructive confirm).
// Every button is type="button", at least 32 px (kit.css), carries the focus-ring class and a data-action the shell
// reads by event delegation. The main CTA may get the gradient border glow.
import { dataAttrs, esc, join, trusted } from "./html.ts";
import type { Act, Html } from "./html.ts";
import { icon } from "./icons.ts";
import type { IconName } from "./icons.ts";

export type ButtonVariant = "primary" | "secondary" | "danger";
const VARIANTS: readonly ButtonVariant[] = ["primary", "secondary", "danger"];

export interface ButtonOpts extends Act {
  /** default secondary */
  variant?: ButtonVariant;
  /** full width */
  block?: boolean;
  /** the screen's main CTA: a gradient border glow (primary only) */
  glow?: boolean;
  icon?: IconName;
  /** mirrors a directional icon */
  rtl?: boolean;
  /** required when the label is empty (an icon-only button) */
  ariaLabel?: string;
}

export function button(o: ButtonOpts): Html {
  const variant: ButtonVariant = o.variant && VARIANTS.includes(o.variant) ? o.variant : "secondary";
  const aria = o.ariaLabel ? ` aria-label="${esc(o.ariaLabel)}"` : "";
  const ic = o.icon ? icon(o.icon, { rtl: o.rtl === true }) : "";
  const label = o.label !== "" ? `<span class="kit-btn-label">${esc(o.label)}</span>` : "";
  const btn = `<button type="button" class="kit-btn kit-btn-${variant} kit-focus${o.block ? " kit-btn-block" : ""}" data-action="${esc(o.action)}"${dataAttrs(o.data)}${aria}${o.disabled ? " disabled" : ""}>${ic}${label}</button>`;
  if (o.glow && variant === "primary") return trusted(`<span class="kit-glow${o.block ? " kit-glow-block" : ""}">${btn}</span>`);
  return trusted(btn);
}

/** Buttons side by side, wrapping on a narrow panel. */
export const buttonRow = (buttons: readonly Html[]): Html => trusted(`<div class="kit-btn-row">${join(buttons)}</div>`);
