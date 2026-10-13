// Tabs: a tablist of equal-width controls (<div role="tab" tabindex="0">, html.ts control(): UXP paints a <button>
// as its native grey control); the active one has the pink underline. Enter and Space activate a tab (activate.ts).
// A count after the label carries kit-gap-s (flex drops the whitespace between them). The DOM order is the reading order in
// both languages: CSS direction lays the row out right-to-left in Arabic, so the tab order follows the visual order.
// A label that does not fit is cut with an ellipsis (kit.css .kit-tab-label): its title attribute holds the full label.
import type { Strings } from "../i18n.ts";
import { control, esc, ltr, trusted } from "./html.ts";
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
      const count = typeof i.count === "number" && Number.isFinite(i.count) ? `<span class="kit-tab-count kit-gap-s">${ltr(i.count)}</span>` : "";
      return control({
        cls: ["kit-tab", "kit-focus", on && "kit-tab-on"],
        role: "tab",
        attrs: { "data-action": "tab", "data-tab": i.id, "aria-selected": String(on) },
        body: `<span class="kit-tab-label" title="${esc(i.label)}">${esc(i.label)}</span>${count}`,
      });
    })
    .join("");
  return trusted(`<div class="kit-tabs" role="tablist" aria-label="${esc(o.label ?? o.t["tabs.label"])}">${items}</div>`);
}
