// Keyboard activation for the kit's controls. A kit control is a <div role="button"> (or role="tab") with
// tabindex="0" (html.ts control(): UXP paints every <button> as Premiere's native grey control, spike 0.1.7), so the
// browser gives it no keyboard behaviour of its own: Enter and Space must do what a click does, the way a native button
// does it. Enter activates on keydown; Space activates on keyup, and only when the Space press started on the same
// control (its keydown only stops the panel from scrolling). A held key's auto-repeat never activates again (one press,
// one action: a held Enter must not approve twice). kitKeyHandler() turns those keys on a focused control into the
// shell's own click handler (the same event delegation on data-action); kitDisabled() lets that handler ignore a
// disabled control (aria-disabled="true"), which a <div> cannot refuse to click by itself; kitPointerGuard() stops a
// mouse press on a disabled control from moving the focus to it. kitControlSelector() names a control by its
// data-action and key attributes, so the shell can find it again after a repaint (mount.ts keeps the focus on it).
// mount.ts wires them: one keydown + keyup listener, one mousedown listener and one check in its click handler.

/** The slice of an element this module reads (a real element and the mount tests' fake both satisfy it). */
export interface KitElement {
  getAttribute(name: string): string | null;
  closest(selector: string): KitElement | null;
}

/** A keydown / keyup event as far as this module reads it. */
export interface KitKeyEvent {
  target: KitElement | null;
  key?: string;
  /** "keydown" (also when absent) or "keyup" */
  type?: string;
  /** true on a held key's auto-repeated keydown */
  repeat?: boolean;
  preventDefault?(): void;
}

/** A mousedown event as far as this module reads it. */
export interface KitPointerEvent {
  target: KitElement | null;
  preventDefault?(): void;
}

/** The roles of a kit control (html.ts control()). */
const ROLES = new Set(["button", "tab"]);

/** The attributes that tell two controls with the same data-action apart (a frame's time, a request id, a tab...). */
export const CONTROL_KEY_ATTRS = ["data-t", "data-id", "data-fingerprint", "data-tab", "data-lang"] as const;

/** A control the editor cannot use now: aria-disabled="true" (the kit's disabled state). */
export const kitDisabled = (el: KitElement | null | undefined): boolean => el?.getAttribute("aria-disabled") === "true";

const isSpace = (key: string | undefined): boolean => key === " " || key === "Spacebar";

/** A CSS attribute value in double quotes. */
const quoted = (v: string): string => `"${v.replace(/["\\]/g, "\\$&").replace(/[\r\n\f]/g, (c) => `\\${c.charCodeAt(0).toString(16)} `)}"`;

/**
 * The selector that finds this control again after a repaint: its data-action plus whichever key attributes it carries
 * (`[data-action="seek"][data-t="12.5"]`). null for an element with no data-action.
 */
export function kitControlSelector(el: KitElement | null | undefined): string | null {
  const action = el?.getAttribute("data-action");
  if (!el || !action) return null;
  let sel = `[data-action=${quoted(action)}]`;
  for (const k of CONTROL_KEY_ATTRS) {
    const v = el.getAttribute(k);
    if (v !== null) sel += `[${k}=${quoted(v)}]`;
  }
  return sel;
}

/** The enabled kit control (role button / tab, with a data-action) an event landed on, or null. */
function controlOf(target: KitElement | null): KitElement | null {
  const el = target?.closest("[data-action]") ?? null;
  if (!el || !ROLES.has(el.getAttribute("role") ?? "") || kitDisabled(el)) return null;
  return el;
}

/**
 * One listener for keydown AND keyup: on a kit control (role button / tab, with a data-action, not disabled), Enter's
 * keydown, or Space's keyup after a Space keydown on the same control, calls `activate` with that control as the
 * target, exactly as a click on it would. Space's keydown stops its default (it would scroll the panel). An
 * auto-repeated keydown never activates. Any other key or element is left alone (typing in a text box is never touched).
 */
export function kitKeyHandler<E extends { target: KitElement | null }>(activate: (e: E) => void): (e: KitKeyEvent) => void {
  /** the control a Space press went down on (its selector: a repaint in between replaces the element itself) */
  let spaceDown: string | null = null;
  return (e) => {
    const up = e.type === "keyup";
    if (e.key === "Enter") {
      if (up) return;
      const el = controlOf(e.target);
      if (!el) return;
      e.preventDefault?.();
      if (!e.repeat) activate({ target: el } as E);
      return;
    }
    if (!isSpace(e.key)) return;
    const el = controlOf(e.target);
    if (!up) {
      if (!el) return void (spaceDown = null);
      e.preventDefault?.();
      if (!e.repeat) spaceDown = kitControlSelector(el);
      return;
    }
    const started = spaceDown;
    spaceDown = null;
    if (!el) return;
    e.preventDefault?.();
    if (started !== null && started === kitControlSelector(el)) activate({ target: el } as E);
  };
}

/** A mousedown listener: a press on a disabled control does not move the focus to it (preventDefault). */
export function kitPointerGuard(e: KitPointerEvent): void {
  const el = e.target?.closest("[data-action]") ?? null;
  if (el && kitDisabled(el)) e.preventDefault?.();
}
