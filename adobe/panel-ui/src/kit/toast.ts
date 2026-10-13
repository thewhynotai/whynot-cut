// Toasts: the "status line + one fix button" pattern (Addendum C1.4, ecosystem §3.4). A status message with its colour
// AND icon, one plain sentence, and at most ONE fix button: Start engine, Try again or Copy diagnostics. Never a
// command: commands live only in the log drawer and the Copy diagnostics payload. A text that holds one anyway is never
// cut up (src/commands.ts runtimeText, C2.2 review round 2): "Claude Code" reads "Claude", and a text that still holds
// a command is replaced whole by "That did not work." (the shell logs the raw words). An error always says what
// to do: its one button is the fix, or Copy diagnostics when there is no other fix (Addendum B4.4), and then the toast
// says what to do with the copy. (The log drawer has its own Copy diagnostics button, but only while it is open.) A
// toast never adds a primary button (one primary per screen).
import type { Strings } from "../i18n.ts";
import { runtimeText } from "../commands.ts";
import { button, buttonRow } from "./button.ts";
import { esc, trusted, withCommands } from "./html.ts";
import type { Act, Html } from "./html.ts";
import { icon, isStatus, statusIcon } from "./icons.ts";
import type { StatusKind } from "./icons.ts";

/** The fix buttons a problem may carry, wired by the shell's event delegation (data-action). */
export type FixKind = "start-engine" | "retry" | "copy-diagnostics";
const FIX_KINDS: readonly FixKind[] = ["start-engine", "retry", "copy-diagnostics"];

/** The translated button for a fix: Start engine / Try again / Copy diagnostics. */
export function fixAction(t: Strings, kind: FixKind): Act {
  const k: FixKind = FIX_KINDS.includes(kind) ? kind : "copy-diagnostics";
  const label = k === "start-engine" ? t["action.start_engine"] : k === "retry" ? t["action.retry"] : t["actions.diagnostics"];
  return { label, action: k };
}

export interface ToastOpts {
  t: Strings;
  kind: StatusKind;
  /** the one plain sentence; `file names` stay left-to-right */
  text: string;
  /** the one fix button (always secondary). An error without one gets Copy diagnostics. */
  fix?: Act | null;
  /** the close button; default true */
  dismiss?: boolean;
}

export function toast(o: ToastOpts): Html {
  const kind: StatusKind = isStatus(o.kind) ? o.kind : "info";
  const fix: Act | null = o.fix ?? (kind === "error" ? fixAction(o.t, "copy-diagnostics") : null);
  const close =
    o.dismiss === false
      ? ""
      : `<button type="button" class="kit-x kit-focus" data-action="dismiss-toast" aria-label="${esc(o.t["notice.dismiss"])}" title="${esc(o.t["notice.dismiss"])}">${icon("close")}</button>`;
  const alert = kind === "error";
  return trusted(
    `<div class="kit-toast kit-toast-${kind}" role="${alert ? "alert" : "status"}" aria-live="${alert ? "assertive" : "polite"}">` +
      `<span class="kit-toast-icon">${statusIcon(kind, o.t)}</span>` +
      `<div class="kit-toast-body"><div class="kit-toast-text">${withCommands(runtimeText(o.text) ?? o.t["notice.failed"])}</div>` +
      (fix?.action === "copy-diagnostics" ? `<div class="kit-toast-text">${esc(o.t["notice.send_diagnostics"])}</div>` : "") +
      (fix ? buttonRow([button({ ...fix, variant: "secondary" })]) : "") +
      `</div>${close}</div>`,
  );
}
