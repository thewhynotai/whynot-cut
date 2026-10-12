// The first-run checklist (Addendum C1.9, ecosystem §3.4/§3.6): one row per thing the editor's machine needs (Engine ·
// Premiere link · Claude · Clients folder). Each row is a status icon (colour AND shape, labelled for screen readers:
// never colour alone), the row's label from the string table, and at most ONE fix button (Start engine, Try again, Copy
// diagnostics, Choose client folder...). Row buttons are secondary; at most one row may carry the screen's primary
// action (B4: one primary per screen), and the function throws on a second. A component only: B-T2 places it.
// RTL through CSS direction (the DOM order is the same in both languages).
import type { Strings } from "../i18n.ts";
import { button } from "./button.ts";
import { auto, esc, trusted } from "./html.ts";
import type { Act, Html } from "./html.ts";
import { icon } from "./icons.ts";

export type ChecklistState = "ok" | "warn" | "error" | "pending";
export const CHECKLIST_STATES: readonly ChecklistState[] = ["ok", "warn", "error", "pending"];

/** The setup rows, in order: what the engine-computed status model reports (ecosystem §3.4). */
export type ChecklistId = "engine" | "premiere" | "claude" | "clients";
export const CHECKLIST_ROWS: readonly ChecklistId[] = ["engine", "premiere", "claude", "clients"];

export interface ChecklistItem {
  /** the row's id (data-check, for the shell); one of CHECKLIST_ROWS for the setup checklist */
  id: string;
  /** an unknown state reads as pending */
  state: ChecklistState;
  /** translated label (checklistItem() takes it from the string table) */
  label: string;
  /** the row's one fix button */
  action?: Act | null;
  /** this row's action is the screen's primary button (at most one row) */
  primary?: boolean;
}

const LABEL_KEY = {
  engine: "checklist.engine",
  premiere: "checklist.premiere",
  claude: "checklist.claude",
  clients: "checklist.clients",
} as const satisfies Record<ChecklistId, keyof Strings>;

const STATE_KEY = {
  ok: "status.ok",
  warn: "status.warn",
  error: "status.error",
  pending: "status.pending",
} as const satisfies Record<ChecklistState, keyof Strings>;

/** A setup row with its label from the string table. */
export function checklistItem(t: Strings, id: ChecklistId, state: ChecklistState, action?: Act | null, primary?: boolean): ChecklistItem {
  return { id, state, label: t[LABEL_KEY[id]], ...(action ? { action } : {}), ...(primary ? { primary } : {}) };
}

export function checklist(items: readonly ChecklistItem[], t: Strings): Html {
  if (items.filter((i) => i.primary && i.action).length > 1) throw new Error("kit.checklist.one-primary");
  const rows = items
    .map((i) => {
      const state: ChecklistState = CHECKLIST_STATES.includes(i.state) ? i.state : "pending";
      const act = i.action ? `<span class="kit-check-act">${button({ ...i.action, variant: i.primary ? "primary" : "secondary" })}</span>` : "";
      return (
        `<li class="kit-check-row kit-check-${state}" data-check="${esc(i.id)}">` +
        `<span class="kit-check-icon">${icon(state, { label: t[STATE_KEY[state]] })}</span>` +
        `<span class="kit-check-label">${auto(i.label)}</span>${act}</li>`
      );
    })
    .join("");
  return trusted(`<ul class="kit-check" aria-label="${esc(t["checklist.label"])}">${rows}</ul>`);
}
