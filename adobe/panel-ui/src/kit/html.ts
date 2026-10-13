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

const ARABIC = /[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]/;
/** In ESCAPED text: an entity, a `backticked` run (withCommands makes it a code run), a (parenthesised term), or a
 *  Latin word run ("WhyNot Cut", "Premiere"), in that order of precedence. */
const LATIN_RUN = /(&#?[a-z0-9]+;)|(`[^`]*`)|(\([^()]*\))|([A-Za-z][A-Za-z0-9]*(?:[ .-][A-Za-z0-9]+)*)/g;
/** Latin words inside an Arabic sentence become left-to-right <bdi dir="ltr"> runs: UXP shapes a run that mixes
 *  Arabic and a Latin word badly (spike 0.1.7 lab, font rows). A term in parentheses (the English UI term on first use,
 *  "(Rebuild)") stays as it is, and so does a sentence with no Arabic. Takes and returns ESCAPED text. */
export function isolateLatin(escaped: string): string {
  if (!ARABIC.test(escaped)) return escaped;
  return escaped.replace(LATIN_RUN, (m, entity?: string, code?: string, paren?: string, latin?: string) =>
    latin ? `<bdi dir="ltr">${latin}</bdi>` : (entity ?? code ?? paren ?? m),
  );
}
/** Copy (a translated sentence or title): escaped, with any Latin word inside Arabic as a left-to-right run. */
export const prose = (text: unknown): Html => trusted(isolateLatin(esc(text)));
/** Text of unknown direction (a client name, a statement): isolated, direction from its own first letter (a Latin word
 *  inside Arabic is its own left-to-right run, as in prose()). */
export const auto = (text: unknown): Html => trusted(`<bdi>${isolateLatin(esc(text))}</bdi>`);
/** A sentence that may hold paths or file names in `backticks`: EVERY backticked run (not only the last) becomes a
 *  left-to-right `kit-code` run (the backticks are markup); none becomes a chip. (The name is historical: a backticked
 *  command in copy is a bug the no-commands guard catches.) The run is set in the mono face on a code background (kit.css .kit-code, display inline), so
 *  inside Arabic it reads as one token: without the box an RTL reader meets a path's edge punctuation first and reads
 *  "assets/" as "/assets". */
export const withCommands = (text: unknown): Html =>
  trusted(isolateLatin(esc(text)).replace(/`([^`]+)`/g, (_m, cmd: string) => `<bdi dir="ltr" class="kit-code">${cmd}</bdi>`));

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

/** The kit's one control element. UXP (Premiere 26.5.2, spike 0.1.7 CSS lab) paints EVERY <button> as Premiere's own
 *  grey control whatever its display, radius, background or appearance, so the kit never emits <button>: a control is a
 *  <div role="button" tabindex="0"> (role="tab" for a tab) with flex layout, which paints exactly as kit.css says.
 *  Disabled = aria-disabled="true", the kit-btn-disabled class and tabindex="-1" (it leaves the tab order; the shell's
 *  click and keyboard dispatch ignore it, src/kit/activate.ts). Enter and Space activate it (activate.ts). `cls` is the
 *  class list (one class per entry, falsy entries dropped); `attrs` are attributes by name (values escaped here; a
 *  null / undefined / false value is left out), then `data` (data-*, dataAttrs()); `body` is kit markup. */
export function control(o: {
  cls: readonly (string | false | null | undefined)[];
  role?: "button" | "tab";
  disabled?: boolean;
  attrs?: Readonly<Record<string, string | number | false | null | undefined>>;
  data?: DataAttrs;
  body: string;
}): Html {
  const off = o.disabled === true;
  const cls = [...o.cls, off && "kit-btn-disabled"].filter((c): c is string => typeof c === "string" && c !== "").join(" ");
  let attrs = "";
  for (const [k, v] of Object.entries(o.attrs ?? {})) {
    if (!/^[a-z][a-z0-9-]*$/.test(k)) throw new Error(`kit.attribute=${JSON.stringify(k)}`);
    if (v !== null && v !== undefined && v !== false) attrs += ` ${k}="${esc(v)}"`;
  }
  return trusted(
    `<div class="${cls}" role="${o.role ?? "button"}" tabindex="${off ? "-1" : "0"}"${attrs}${dataAttrs(o.data)}${off ? ` aria-disabled="true"` : ""}>${o.body}</div>`,
  );
}

/** A button the caller wires: its label (already translated), the data-action and data-* the shell reads. */
export interface Act {
  label: string;
  action: string;
  data?: DataAttrs;
  disabled?: boolean;
}
