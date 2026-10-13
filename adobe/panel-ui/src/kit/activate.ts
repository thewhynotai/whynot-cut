// Keyboard activation for the kit's controls. A kit control is a <div role="button"> (or role="tab") with
// tabindex="0" (html.ts control(): UXP paints every <button> as Premiere's native grey control, spike 0.1.7), so the
// browser gives it no keyboard behaviour of its own: Enter and Space must do what a click does. kitKeyHandler() turns
// those keys on a focused control into the shell's own click handler (the same event delegation on data-action), and
// kitDisabled() lets that handler ignore a disabled control (aria-disabled="true"), which a <div> cannot refuse to
// click by itself. mount.ts wires both: one keydown listener and one check in its click handler.

/** The slice of an element this module reads (a real element and the mount tests' fake both satisfy it). */
export interface KitElement {
  getAttribute(name: string): string | null;
  closest(selector: string): KitElement | null;
}

/** A keydown event as far as this module reads it. */
export interface KitKeyEvent {
  target: KitElement | null;
  key?: string;
  preventDefault?(): void;
}

/** The roles of a kit control (html.ts control()). */
const ROLES = new Set(["button", "tab"]);

/** A control the editor cannot use now: aria-disabled="true" (the kit's disabled state). */
export const kitDisabled = (el: KitElement | null | undefined): boolean => el?.getAttribute("aria-disabled") === "true";

/** Enter, or Space ("Spacebar" in older hosts). */
const isActivationKey = (key: string | undefined): boolean => key === "Enter" || key === " " || key === "Spacebar";

/**
 * A keydown listener: Enter or Space on a kit control (role button / tab, with a data-action, not disabled) calls
 * `activate` with that control as the target, exactly as a click on it would, and stops the key's default (Space
 * would scroll the panel). Any other key or element is left alone (typing in a text box is never touched).
 */
export function kitKeyHandler<E extends { target: KitElement | null }>(activate: (e: E) => void): (e: KitKeyEvent) => void {
  return (e) => {
    if (!isActivationKey(e.key)) return;
    const el = e.target?.closest("[data-action]") ?? null;
    if (!el || !ROLES.has(el.getAttribute("role") ?? "") || kitDisabled(el)) return;
    e.preventDefault?.();
    activate({ target: el } as E);
  };
}
