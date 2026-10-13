// Buttons: primary (violet #5400FB fill, white text; ONE per screen, see primaryCount), secondary (glass), danger
// (destructive confirm; it carries the warn icon by default, so the status colour is never alone). Every button is a
// <div role="button" tabindex="0"> (html.ts control(): UXP paints a <button> as Premiere's native grey control), at
// least 32 px with a 16 px (half-height) radius, never 999 (kit.css), carries the focus-ring class and a data-action
// the shell reads by event delegation; Enter and Space activate it (activate.ts). Disabled is aria-disabled + the
// kit-btn-disabled class + tabindex -1. The main CTA may get the glow: a box-shadow (--twn-cta-glow), because UXP
// cannot clip a gradient ring to a radius (spike 0.1.7). A directional icon (chevron-start / chevron-end) needs the
// panel's direction (rtl), required by the type and checked at run time, so a chevron never points the wrong way. An
// icon next to a label: the label carries kit-gap-s (UXP and flexbox drop the whitespace between flex children).
import { control, esc, join, trusted } from "./html.ts";
import type { Act, Html } from "./html.ts";
import { icon, isDirectional } from "./icons.ts";
import type { DirectionalIcon, IconInk, IconName } from "./icons.ts";

export type ButtonVariant = "primary" | "secondary" | "danger";
const VARIANTS: readonly ButtonVariant[] = ["primary", "secondary", "danger"];

interface ButtonBase extends Act {
  /** default secondary */
  variant?: ButtonVariant;
  /** full width */
  block?: boolean;
  /** the screen's main CTA: the shadow glow (primary only) */
  glow?: boolean;
  /** required when the label is empty (an icon-only button) */
  ariaLabel?: string;
}

/** A non-directional icon (default: none; warn for a danger button); a directional one comes with the direction. */
type ButtonIcon = { icon?: Exclude<IconName, DirectionalIcon>; rtl?: boolean } | { icon: DirectionalIcon; rtl: boolean };

export type ButtonOpts = ButtonBase & ButtonIcon;

/** The icon's fill on each variant's background (a disabled button's icon is muted, like its text). */
const INK: Readonly<Record<ButtonVariant, IconInk>> = { primary: "on-primary", secondary: "text", danger: "on-error" };

export function button(o: ButtonOpts): Html {
  const variant: ButtonVariant = o.variant && VARIANTS.includes(o.variant) ? o.variant : "secondary";
  if (isDirectional(o.icon) && typeof o.rtl !== "boolean") throw new Error(`kit.button.rtl-required=${o.icon}`);
  const name: IconName | undefined = o.icon ?? (variant === "danger" ? "warn" : undefined);
  const off = o.disabled === true;
  const ic = name ? icon(name, { rtl: o.rtl === true, ink: off ? "muted" : INK[variant] }) : "";
  const label = o.label !== "" ? `<span class="kit-btn-label${ic ? " kit-gap-s" : ""}">${esc(o.label)}</span>` : "";
  return control({
    cls: ["kit-btn", `kit-btn-${variant}`, "kit-focus", o.block && "kit-btn-block", o.glow && variant === "primary" && !off && "kit-btn-glow"],
    disabled: off,
    attrs: { "data-action": o.action, "aria-label": o.ariaLabel || undefined },
    data: o.data,
    body: `${ic}${label}`,
  });
}

/** Buttons side by side, wrapping on a narrow panel. */
export const buttonRow = (buttons: readonly Html[]): Html => trusted(`<div class="kit-btn-row">${join(buttons)}</div>`);

/** How many primary buttons a piece of kit markup holds (Addendum B4: at most ONE per screen): every element whose
 *  class list names kit-btn-primary (the kit's <div role="button">, or a <button> should one ever appear). */
export function primaryCount(html: string): number {
  let n = 0;
  for (const m of html.matchAll(/<[a-z][a-z0-9]*\b[^>]*?\sclass="([^"]*)"/g)) if (m[1]!.split(/\s+/).includes("kit-btn-primary")) n++;
  return n;
}
