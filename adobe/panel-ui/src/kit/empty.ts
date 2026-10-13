// Empty states teach (Addendum B4.5): no client, no clip, no engine -> what to do next, with exactly ONE button.
import { button } from "./button.ts";
import { prose, trusted, withCommands } from "./html.ts";
import type { Act, Html } from "./html.ts";
import { icon } from "./icons.ts";
import type { IconName } from "./icons.ts";

export interface EmptyOpts {
  title: string;
  /** what to do next, in plain words (never a command: those live in the log drawer and Copy diagnostics, C1.4);
   *  a `path` or a backticked `name` stays left-to-right */
  text: string;
  action: Act;
  /** default true: the one action is the screen's primary button */
  primary?: boolean;
  /** default info */
  icon?: IconName;
}

export function emptyState(o: EmptyOpts): Html {
  return trusted(
    `<div class="kit-empty" role="status"><span class="kit-empty-icon">${icon(o.icon ?? "info")}</span>` +
      `<h3 class="kit-empty-title">${prose(o.title)}</h3><p class="kit-empty-text">${withCommands(o.text)}</p>` +
      button({ ...o.action, variant: o.primary === false ? "secondary" : "primary" }) +
      `</div>`,
  );
}
