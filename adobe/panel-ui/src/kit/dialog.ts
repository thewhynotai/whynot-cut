// The confirm dialog (Addendum B4.2): a destructive action always shows what will change and the backup name, and asks
// for a confirm. The backup name is a left-to-right chip; with no backup the dialog says so. The confirm is a danger
// button (primary when the action is not destructive), the cancel a secondary one. Rendered in place (no overlay), so it
// works the same in UXP and CEP.
import type { Strings } from "../i18n.ts";
import { button, buttonRow } from "./button.ts";
import { cmdRow, esc, safeId, trusted, withCommands } from "./html.ts";
import type { Act, Html } from "./html.ts";
import { icon } from "./icons.ts";

export interface DialogOpts {
  t: Strings;
  /** element id (aria-labelledby / describedby are derived from it); default "kit-dialog" */
  id?: string;
  title: string;
  /** what will change, one line each (at least one); `commands` stay left-to-right */
  changes: readonly [string, ...string[]];
  /** the backup the action keeps first; absent = "No backup copy is made" */
  backupName?: string | null;
  confirm: Act;
  cancel: Act;
  /** default true: the confirm is a danger button */
  destructive?: boolean;
}

export function dialog(o: DialogOpts): Html {
  const id = safeId(o.id ?? "kit-dialog");
  const changes = o.changes.map((c) => `<li class="kit-dialog-change">${withCommands(c)}</li>`).join("");
  const backup = o.backupName
    ? `<div class="kit-label">${esc(o.t["dialog.backup"])}</div>${cmdRow(o.backupName)}`
    : `<p class="kit-dialog-nobackup">${esc(o.t["dialog.nobackup"])}</p>`;
  const destructive = o.destructive !== false;
  return trusted(
    `<div class="kit-dialog" id="${id}" role="alertdialog" aria-modal="true" aria-labelledby="${id}-title" aria-describedby="${id}-changes">` +
      `<div class="kit-dialog-head"><span class="kit-dialog-icon">${icon("warn")}</span><h3 class="kit-dialog-title" id="${id}-title">${esc(o.title)}</h3></div>` +
      `<div class="kit-label">${esc(o.t["dialog.changes"])}</div><ul class="kit-dialog-changes" id="${id}-changes">${changes}</ul>` +
      backup +
      buttonRow([button({ ...o.confirm, variant: destructive ? "danger" : "primary" }), button({ ...o.cancel, variant: "secondary" })]) +
      `</div>`,
  );
}
