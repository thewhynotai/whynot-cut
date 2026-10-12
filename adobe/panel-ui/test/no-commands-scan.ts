// The "no command text on the editor's screen" scanner (Addendum C1.4, C2.2), not a test file itself: test/
// no-commands.test.ts runs it over the string table and the panel sources. Commands live only in the log drawer
// (src/kit/log.ts and the log lines it shows) and in the Copy diagnostics payload (src/diagnostics.ts).
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { literals } from "./literal-scan.ts";

/** Sources that may hold commands: the log drawer and the diagnostics payload. */
export const COMMAND_FILES: readonly string[] = ["kit/log.ts", "diagnostics.ts"];

const RULES: ReadonlyArray<[string, RegExp]> = [
  // a CLI invocation: the word, then a space (lowercase, as typed; "Claude" the product name is fine)
  ["reel/claude/npm/python command", /(?:^|[^\w-])(?:reel|claude|npm|python) /],
  // a backticked run with a space in it: a verb and its arguments (`assets`, `engine.json` are single tokens: allowed)
  ["backticked command", /`[^`\s]+ [^`]*`/],
  ["Claude Code", /claude\s*code/i],
  // a sentence that leads into a command ("In your Claude session run:", «شغّل الأمر»)
  ["command lead-in", /\b(?:run|type|paste)\s*:|شغّل الأمر|نفّذ الأمر/i],
];

/** The rule a text breaks, or null. */
export function commandIn(text: string): string | null {
  for (const [name, re] of RULES) if (re.test(text)) return name;
  return null;
}

/** A log line in data ([level, text], as mock.ts writes its sample log): log drawer content, where commands belong. */
const LOG_TUPLE = /\[\s*"(?:info|warn|error)"\s*,\s*(?:"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`)\s*\]/g;

/** Every string / template literal of a TS source that holds a command (log-line tuples excepted). */
export function commandLiterals(src: string): string[] {
  const found: string[] = [];
  for (const { text } of literals(src.replace(LOG_TUPLE, "[]"))) {
    const plain = text.replace(/\\`/g, "`");
    const rule = commandIn(plain);
    if (rule) found.push(`${rule}: ${plain}`);
  }
  return found;
}

/** The .ts files under dir (recursive), as paths relative to it with forward slashes. */
export function tsFiles(dir: string): string[] {
  const out: string[] = [];
  const walk = (d: string) => {
    for (const name of readdirSync(d)) {
      const p = join(d, name);
      if (statSync(p).isDirectory()) walk(p);
      else if (name.endsWith(".ts")) out.push(relative(dir, p).split(sep).join("/"));
    }
  };
  walk(dir);
  return out.sort();
}

/** Every command a panel-ui tree shows (src/** except COMMAND_FILES, and every i18n value), as "where: rule: text". */
export function commandsOnScreen(panelUi: string): string[] {
  const found: string[] = [];
  const src = join(panelUi, "src");
  for (const f of tsFiles(src)) {
    if (COMMAND_FILES.includes(f)) continue;
    for (const hit of commandLiterals(readFileSync(join(src, f), "utf8"))) found.push(`src/${f}: ${hit}`);
  }
  for (const lang of ["en", "ar"]) {
    const table = JSON.parse(readFileSync(join(panelUi, "i18n", `${lang}.json`), "utf8")) as Record<string, string>;
    for (const [k, v] of Object.entries(table)) {
      const rule = commandIn(String(v));
      if (rule) found.push(`i18n/${lang}.json ${k}: ${rule}: ${v}`);
    }
  }
  return found;
}
