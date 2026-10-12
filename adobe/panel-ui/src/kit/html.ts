// The kit's markup helpers. Every kit component is a pure function returning an escaped HTML string, like render.ts:
// every dynamic value goes through esc(); paths, file names, timecodes and numbers are <bdi dir="ltr"> runs so they stay
// left-to-right inside Arabic text. Commands are never on screen (Addendum C1.4): only the log drawer shows them. Kit output is typed Html (a branded string), so a component that takes markup
// (a card body, a button row) only accepts what another kit function produced, never a raw string.

/** Markup produced by a kit function (escaped). */
export type Html = string & { readonly __kitHtml: true };

/** Marks a string the kit built itself (from escaped parts) as Html. */
export const trusted = (s: string): Html => s as Html;

export function esc(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/** A left-to-right run (path, file name, timecode, number, a log line). */
export const ltr = (text: unknown): Html => trusted(`<bdi dir="ltr">${esc(text)}</bdi>`);
/** Text of unknown direction (a client name, a statement): isolated, direction from its own first letter. */
export const auto = (text: unknown): Html => trusted(`<bdi>${esc(text)}</bdi>`);
/** A sentence that may hold paths or file names in `backticks`: EVERY backticked run (not only the last) becomes a
 *  left-to-right `kit-code` run (the backticks are markup); none becomes a chip. (The name is historical: a backticked
 *  command in copy is a bug the no-commands guard catches.) The run is set in the mono face on a code background (kit.css .kit-code, display inline), so
 *  inside Arabic it reads as one token: without the box an RTL reader meets a path's edge punctuation first and reads
 *  "assets/" as "/assets". */
export const withCommands = (text: unknown): Html =>
  trusted(esc(text).replace(/`([^`]+)`/g, (_m, cmd: string) => `<bdi dir="ltr" class="kit-code">${cmd}</bdi>`));

/** A file-name chip (a backup name) on its own flex row, a monospace left-to-right run (UXP draws an inline-flex chip
 *  over running text, so never inside a sentence). Never a command: commands are not shown on screen. */
export const cmdRow = (text: string): Html => trusted(`<div class="kit-cmd-row"><span class="kit-cmd">${ltr(text)}</span></div>`);

/** Kit markup joined. */
export const join = (parts: readonly (Html | "")[]): Html => trusted(parts.join(""));

/** Fills {name} placeholders of a translated template with kit markup (the template itself is escaped). */
export function fmtHtml(template: string, vars: Readonly<Record<string, Html>>): Html {
  return trusted(esc(template).replace(/\{(\w+)\}/g, (m, k: string) => (Object.prototype.hasOwnProperty.call(vars, k) ? vars[k]! : m)));
}

export type DataAttrs = Readonly<Record<string, string | number>>;

/** data-* attributes for the shell's event delegation. Keys are fixed by the caller's code: a bad key is a bug (it throws;
 *  the message is a technical token, never shown copy). */
export function dataAttrs(data?: DataAttrs): string {
  if (!data) return "";
  let out = "";
  for (const [k, v] of Object.entries(data)) {
    if (!/^[a-z][a-z0-9-]*$/.test(k)) throw new Error(`kit.data-attribute=${JSON.stringify(k)}`);
    out += ` data-${k}="${esc(v)}"`;
  }
  return out;
}

/** An element id reduced to safe characters. */
export const safeId = (id: string): string => id.replace(/[^A-Za-z0-9_-]/g, "-") || "kit";

/** Seconds as m:ss (Western digits). */
export function clockOf(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** A button the caller wires: its label (already translated), the data-action and data-* the shell reads. */
export interface Act {
  label: string;
  action: string;
  data?: DataAttrs;
  disabled?: boolean;
}
