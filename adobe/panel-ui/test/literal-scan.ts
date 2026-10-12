// A small literal scanner for the "no hard-coded user-visible strings" tests (not a test file itself).

export interface Literal {
  /** static text; each template expression becomes "§" */
  text: string;
  /** the function the literal is the first argument of, e.g. "cmdRow" in cmdRow("reel doctor"); "" otherwise */
  callee: string;
  /** the object key the literal is the value of, e.g. "how" in { how: "..." }; "" otherwise */
  key: string;
}

/** Every string and template literal in a TS source. Comments and regular expressions are skipped; literals inside
 *  template expressions are found too. Small on purpose: enough for the panel's own sources. */
export function literals(src: string): Literal[] {
  const out: Literal[] = [];
  let i = 0;
  let prev = "";
  let prevAt = -1;
  const n = src.length;
  /** what precedes the literal that starts at i: a call's "(" or an object key's ":" */
  function context(): { callee: string; key: string } {
    const before = src.slice(0, prevAt + 1);
    if (prev === "(") return { callee: /([A-Za-z_$][\w$]*)\s*\($/.exec(before)?.[1] ?? "", key: "" };
    if (prev === ":") return { callee: "", key: /([A-Za-z_$][\w$]*)\s*:$/.exec(before)?.[1] ?? "" };
    if (prev === "=") return { callee: "", key: /(?:const|let)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]*)?=$/.exec(before)?.[1] ?? "" };
    return { callee: "", key: "" };
  }
  function template(): string {
    let text = "";
    i++;
    while (i < n && src[i] !== "`") {
      if (src[i] === "\\") {
        text += src.slice(i, i + 2);
        i += 2;
      } else if (src[i] === "$" && src[i + 1] === "{") {
        i += 2;
        prev = "{";
        prevAt = i - 1;
        code(true);
        text += "§";
      } else text += src[i++];
    }
    i++;
    return text;
  }
  function quoted(q: string): string {
    let text = "";
    i++;
    while (i < n && src[i] !== q) {
      if (src[i] === "\\") {
        text += src.slice(i, i + 2);
        i += 2;
      } else text += src[i++];
    }
    i++;
    return text;
  }
  /** Code until the end (or, inside a template expression, until its closing brace). */
  function code(inExpr: boolean): void {
    let depth = 0;
    while (i < n) {
      const c = src[i]!;
      if (c === "/" && src[i + 1] === "/") {
        i = src.indexOf("\n", i);
        if (i < 0) i = n;
      } else if (c === "/" && src[i + 1] === "*") {
        i = src.indexOf("*/", i) + 2;
      } else if (c === "/" && (prev === "" || "(,=:[!&|?{};+".includes(prev) || /\breturn$/.test(src.slice(0, i).trimEnd()))) {
        // a regular expression literal
        i++;
        let cls = false;
        while (i < n && (cls || src[i] !== "/")) {
          if (src[i] === "\\") i++;
          else if (src[i] === "[") cls = true;
          else if (src[i] === "]") cls = false;
          i++;
        }
        i++;
        prev = "/";
        prevAt = i - 1;
      } else if (c === "`" || c === '"' || c === "'") {
        const ctx = context();
        const text = c === "`" ? template() : quoted(c);
        out.push({ text, ...ctx });
        prev = c;
        prevAt = i - 1;
      } else {
        if (c === "{") depth++;
        else if (c === "}") {
          if (inExpr && depth === 0) {
            i++;
            prev = "}";
            prevAt = i - 1;
            return;
          }
          depth--;
        }
        if (!/\s/.test(c)) {
          prev = c;
          prevAt = i;
        }
        i++;
      }
    }
  }
  code(false);
  return out;
}

const LETTERS = /[A-Za-z؀-ۿ]/;
/** Text that reads as words to a person: any Arabic, or two or more space-separated words with letters (a class name,
 *  a string-table key or a data value is one token). */
export const isWords = (s: string): boolean =>
  /[؀-ۿ]/.test(s) || s.replace(/§/g, " ").split(/\s+/).filter((w) => /[A-Za-z]{2,}/.test(w)).length >= 2;
/** The panel's own helpers that put their argument on screen as text. */
const TEXT_HELPERS = new Set(["esc", "ltr", "auto", "cmdRow", "withCommands", "sentenceWithCommand"]);
/** Commands are the same in every language and stay left-to-right: allowed as literals. */
export const IS_COMMAND = /^reel( [a-z][a-z-]*| --[a-z-]+)+$/;

const isMarkup = (s: string) => /<[a-z/][^>]*>/i.test(s) || /^[^<]*>/.test(s);

/** Hard-coded user-visible words in render code:
 *  - in markup literals: text between tags, and literal words in title / aria-label / placeholder / alt;
 *  - in any other literal: words (two or more, or any Arabic), unless the literal is a command;
 *  - any literal with letters handed straight to a text helper (esc, ltr, cmdRow, ...), unless it is a command. */
export function hardCoded(src: string): string[] {
  const found: string[] = [];
  for (const { text: lit, callee } of literals(src)) {
    if (isMarkup(lit)) {
      for (const m of lit.matchAll(/\b(title|aria-label|placeholder|alt|aria-valuetext)="([^"]*)"/g)) {
        if (LETTERS.test(m[2]!.replace(/§/g, ""))) found.push(`${m[1]}="${m[2]}"`);
      }
      const text = lit.replace(/<[^>]*>/g, " ").replace(/^[^<]*>/, " ").replace(/<[^>]*$/, " ").replace(/§/g, " ");
      if (LETTERS.test(text)) found.push(text.trim());
      continue;
    }
    if (IS_COMMAND.test(lit)) continue;
    if (isWords(lit) || (TEXT_HELPERS.has(callee) && LETTERS.test(lit))) found.push(lit);
  }
  return found;
}

/** The literals of a source a person would read: capitalised text (a sentence, a label like "Approving", a log
 *  prefix), e.g. the error / how / text strings DaemonSource sets. Markup and commands are left out. */
export function sentences(src: string): string[] {
  return literals(src)
    .map((l) => l.text)
    .filter((t) => !isMarkup(t) && !IS_COMMAND.test(t) && /^[A-Z§]/.test(t) && /[A-Za-z]{2,}/.test(t));
}
