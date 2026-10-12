// Tabs: a tablist of equal-width buttons; the active one has the pink underline. The DOM order is the reading order in
// both languages: CSS direction lays the row out right-to-left in Arabic, so the tab order follows the visual order.
// A label that does not fit is cut with an ellipsis (kit.css .kit-tab-label): its title attribute holds the full label.
import type { Strings } from "../i18n.ts";
import { esc, ltr, trusted } from "./html.ts";
import type { Html } from "./html.ts";

export interface TabItem {
  id: string;
  /** translated label */
  label: string;
  /** an optional count shown next to the label */
  count?: number;
}

export interface TabsOpts {
  t: Strings;
  items: readonly TabItem[];
  /** the active tab's id; an unknown id selects the first tab */
  active: string;
  /** the tablist's label; default "Sections" */
  label?: string;
}

export function tabs(o: TabsOpts): Html {
  const active = o.items.some((i) => i.id === o.active) ? o.active : o.items[0]?.id;
  const items = o.items
    .map((i) => {
      const on = i.id === active;
      const count = typeof i.count === "number" && Number.isFinite(i.count) ? `<span class="kit-tab-count">${ltr(i.count)}</span>` : "";
      return (
        `<button type="button" role="tab" class="kit-tab kit-focus${on ? " kit-tab-on" : ""}" data-action="tab" data-tab="${esc(i.id)}" aria-selected="${on ? "true" : "false"}">` +
        `<span class="kit-tab-label" title="${esc(i.label)}">${esc(i.label)}</span>${count}</button>`
      );
    })
    .join("");
  return trusted(`<div class="kit-tabs" role="tablist" aria-label="${esc(o.label ?? o.t["tabs.label"])}">${items}</div>`);
}
