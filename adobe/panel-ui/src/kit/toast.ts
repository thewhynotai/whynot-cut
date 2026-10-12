// Toasts: a status message with its colour AND icon. Errors say what to do (Addendum B4.4): the cause in one line, an
// optional how-line whose trailing `command` becomes a copyable chip row, a fix button and "Copy diagnostics" (on by
// default for errors). A toast never adds a primary button (one primary per screen).
import type { Strings } from "../i18n.ts";
import { button, buttonRow } from "./button.ts";
import { cmdRow, esc, sentenceWithCommand, trusted, withCommands } from "./html.ts";
import type { Act, Html } from "./html.ts";
import { icon, isStatus, statusIcon } from "./icons.ts";
import type { StatusKind } from "./icons.ts";

export interface ToastOpts {
  t: Strings;
  kind: StatusKind;
  /** the cause / message in one line; `commands` stay left-to-right */
  text: string;
  /** what to do; a trailing `command` becomes a chip row */
  how?: string;
  /** the fix action (secondary) */
  fix?: Act | null;
  /** "Copy diagnostics"; default: errors only */
  diagnostics?: boolean;
  /** the close button; default true */
  dismiss?: boolean;
}

export function toast(o: ToastOpts): Html {
  const kind: StatusKind = isStatus(o.kind) ? o.kind : "info";
  const how = o.how ? sentenceWithCommand(o.how) : null;
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
