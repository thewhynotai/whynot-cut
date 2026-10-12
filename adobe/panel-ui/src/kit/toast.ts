// Toasts: a status message with its colour AND icon. Errors say what to do (Addendum B4.4): the cause in one line, an
// optional how-line whose trailing `command` becomes a copyable chip row, a fix button and "Copy diagnostics" (on by
// default for errors). An error toast needs a fix action or a how-line (required by the type, checked at run time).
// A toast never adds a primary button (one primary per screen).
import type { Strings } from "../i18n.ts";
import { button, buttonRow } from "./button.ts";
import { cmdRow, esc, sentenceWithCommand, trusted, withCommands } from "./html.ts";
import type { Act, Html } from "./html.ts";
import { icon, isStatus, statusIcon } from "./icons.ts";
import type { StatusKind } from "./icons.ts";

interface ToastBase {
  t: Strings;
  /** the cause / message in one line; `commands` stay left-to-right */
  text: string;
  /** "Copy diagnostics"; default: errors only */
  diagnostics?: boolean;
  /** the close button; default true */
  dismiss?: boolean;
}

/** how: what to do (a trailing `command` becomes a chip row); fix: the fix action (secondary). An error says what to
 *  do: it has a fix action, a how-line or both. */
type ToastKind =
  | { kind: Exclude<StatusKind, "error">; how?: string; fix?: Act | null }
  | { kind: "error"; how: string; fix?: Act | null }
  | { kind: "error"; how?: string; fix: Act };

export type ToastOpts = ToastBase & ToastKind;

export function toast(o: ToastOpts): Html {
  const kind: StatusKind = isStatus(o.kind) ? o.kind : "info";
  const howText = typeof o.how === "string" && o.how.trim() !== "" ? o.how : null;
  if (kind === "error" && !o.fix && !howText) throw new Error("kit.toast.error-needs-fix-or-how");
  const how = howText ? sentenceWithCommand(howText) : null;
  const acts: Html[] = [];
  if (o.fix) acts.push(button({ ...o.fix, variant: "secondary" }));
  if (o.diagnostics ?? kind === "error") acts.push(button({ label: o.t["actions.diagnostics"], action: "copy-diagnostics", variant: "secondary" }));
  const close =
    o.dismiss === false
      ? ""
      : `<button type="button" class="kit-x kit-focus" data-action="dismiss-toast" aria-label="${esc(o.t["notice.dismiss"])}" title="${esc(o.t["notice.dismiss"])}">${icon("close")}</button>`;
  const alert = kind === "error";
  return trusted(
    `<div class="kit-toast kit-toast-${kind}" role="${alert ? "alert" : "status"}" aria-live="${alert ? "assertive" : "polite"}">` +
      `<span class="kit-toast-icon">${statusIcon(kind, o.t)}</span>` +
      `<div class="kit-toast-body"><div class="kit-toast-text">${withCommands(o.text)}</div>` +
      (how ? `<div class="kit-toast-how">${how.line}</div>${how.cmd ? cmdRow(how.cmd) : ""}` : "") +
      (acts.length ? buttonRow(acts) : "") +
      `</div>${close}</div>`,
  );
}
