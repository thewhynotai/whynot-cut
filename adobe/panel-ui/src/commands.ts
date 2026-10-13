// The ONE command detector (Addendum C1.4, C2.2): what counts as command text, used by the panel at runtime (render.ts /
// mount.ts neutralise an engine or host text before it is shown) and by the guard test (test/no-commands-scan.ts scans
// the string table and every source literal with it). Commands live only in the log drawer and the Copy diagnostics
// payload; the editor's screen shows plain sentences and one fix button.
//
// What is a command (case-insensitive; any whitespace, NBSP and tab included; Arabic diacritics / tashkeel, tatweel and
// zero-width characters are ignored, and the alef forms أ إ آ ٱ read as ا):
//   - a program followed by an argument: reel, claude, npm, npx, node, python, python3, py, pip, git, powershell, pwsh,
//     winget, brew. For reel the first argument must look like one (a flag, a known subcommand, a hyphenated name or a
//     path) and for claude too (a flag, a known subcommand or a quoted prompt), so "a 58 s reel" and "your Claude
//     session" stay plain words; for the others any word that is not a common English word counts ("npx x");
//   - a `backticked` span with whitespace in it (a single `token`, a folder or file name, is not a command);
//   - a whynotcut:// link;
//   - the product name with "Code" after it (the panel says "Claude");
//   - a lead-in: "run:", "type:", "paste:", "enter:", and the Arabic family «شغّل / نفّذ / اكتب / الصق الأمر».
// Nothing here is shown on screen: the lists below are single words, and the patterns are regular expressions.

export type CommandRule = "command" | "backticked-command" | "launcher-link" | "claude-code" | "lead-in";

export interface CommandSpan {
  rule: CommandRule;
  /** the span in the ORIGINAL text, [start, end) */
  start: number;
  end: number;
}

/** reel's subcommands (whynot-cut/engine/reel/cli.py COMMANDS, plus the podcast / motion / panel ones). */
const REEL_SUBCOMMANDS: ReadonlySet<string> = new Set([
  "doctor", "setup", "py", "scaffold", "inbox", "settings", "bench", "profile", "discover", "preflight", "range",
  "transcribe", "plan", "validate", "previews", "sfx", "serve", "premiere", "verify", "qc", "handoff", "status", "next",
  "lock", "update", "watch", "build", "approve", "rebuild", "install", "edit", "revise", "preview",
]);
/** claude's subcommands. */
const CLAUDE_SUBCOMMANDS: ReadonlySet<string> = new Set([
  "auth", "login", "logout", "mcp", "plugin", "plugins", "update", "doctor", "config", "install", "migrate-installer",
  "setup-token", "agents", "resume", "continue",
]);
/** Common English words: a program name followed by one of these is a sentence ("python is required"), not a command. */
const STOP_WORDS: ReadonlySet<string> = new Set([
  "a", "an", "the", "and", "or", "but", "then", "to", "in", "on", "at", "of", "for", "from", "with", "by", "is", "are",
  "was", "were", "be", "been", "it", "its", "this", "that", "these", "those", "your", "you", "my", "our", "we", "they",
  "if", "when", "once", "first", "now", "again", "before", "after", "until", "while", "as", "so", "not", "no", "can",
  "could", "will", "would", "should", "may", "might", "must", "do", "does", "did", "has", "have", "had", "here", "there",
  "which", "who", "what", "where", "why", "how", "all", "any", "each", "more", "only", "than", "too", "very", "just",
  "also", "still", "yet", "into", "over", "up", "out", "about", "session", "sessions", "version", "versions",
]);

/** Ignored when matching: Arabic diacritics (tashkeel), the superscript alef, tatweel, zero-width characters. */
const IGNORED = /[ً-ٰٟـ​-‏⁠﻿]/;
const ALEF_FORMS = /[أإآٱ]/;

interface Normalised {
  /** whitespace as " ", ignored characters dropped, alef forms as ا: the same length as map minus one */
  text: string;
  /** map[i] = the original index of text[i]; map[text.length] = the original length */
  map: number[];
}

function normalise(src: string): Normalised {
  let text = "";
  const map: number[] = [];
  for (let i = 0; i < src.length; i++) {
    const c = src[i]!;
    if (IGNORED.test(c)) continue;
    text += /\s/.test(c) ? " " : ALEF_FORMS.test(c) ? "ا" : c;
    map.push(i);
  }
  map.push(src.length);
  return { text, map };
}

const PROGRAM = /(?<![\p{L}\p{N}_.\/\\-])(reel|claude|npm|npx|node|python3?|py|pip3?|git|powershell|pwsh|winget|brew)(?:\.exe)?(?= +[^ ])/giu;
const FLAG = /^--?[a-z0-9]/i;
const PATHISH = /[\/\\=]|^[.~]|\.[a-z0-9]{1,5}$/i;
const QUOTED = /^["'“«]/;
const ARG_WORD = /^[a-z0-9@][\w@.:~-]*$/i;
/** punctuation that may end a token without being part of it (it also ends the invocation) */
const TRAILING = /[.,;:!?)\]}»"'”`،؛؟]+$/;
const ENDS_CLAUSE = /[.;!?،؛؟]/;
/** a plain lowercase word after the first argument ("claude auth login", "brew install ffmpeg") */
const PLAIN_WORD = /^[a-z]+$/;

type Program = "reel" | "claude" | "other";

function firstArgOk(program: Program, tok: string): boolean {
  const low = tok.toLowerCase();
  if (FLAG.test(tok)) return true;
  if (program === "reel") return REEL_SUBCOMMANDS.has(low) || /^[a-z]+(?:-[a-z0-9]+)+$/i.test(tok) || PATHISH.test(tok);
  if (program === "claude") return CLAUDE_SUBCOMMANDS.has(low) || QUOTED.test(tok);
  return QUOTED.test(tok) || PATHISH.test(tok) || (ARG_WORD.test(tok) && !STOP_WORDS.has(low));
}

const nextArgOk = (tok: string): boolean =>
  FLAG.test(tok) || QUOTED.test(tok) || PATHISH.test(tok) || (/^[a-z0-9@][\w@.:~-]*$/.test(tok) && !STOP_WORDS.has(tok));

/** The end (in normalised text) of the program invocation whose name ends at `at`, or -1 when no argument follows.
 *  After the first argument come flags, paths, quoted strings and identifiers (dev:build, C0239), plus at most one
 *  plain word (none for reel: its subcommands have no subcommands), so "part of reel serve ships" stops at "serve". */
function invocationEnd(text: string, at: number, program: Program): number {
  let end = -1;
  let p = at;
  let plain = program === "reel" ? 0 : 1;
  for (let first = true; ; first = false) {
    while (text[p] === " ") p++;
    if (p >= text.length) break;
    let tokEnd: number;
    if (QUOTED.test(text[p]!)) {
      const close = { '"': '"', "'": "'", "“": "”", "«": "»" }[text[p]!]!;
      const q = text.indexOf(close, p + 1);
      tokEnd = q < 0 ? text.length : q + 1;
    } else {
      const sp = text.indexOf(" ", p);
      tokEnd = sp < 0 ? text.length : sp;
    }
    const raw = text.slice(p, tokEnd);
    const trail = QUOTED.test(raw) ? "" : (TRAILING.exec(raw)?.[0] ?? "");
    const tok = raw.slice(0, raw.length - trail.length);
    if (!tok || !(first ? firstArgOk(program, tok) : nextArgOk(tok))) break;
    if (!first && PLAIN_WORD.test(tok) && plain-- <= 0) break;
    end = p + tok.length;
    if (trail) break;
    p = tokEnd;
  }
  return end;
}

/** The end of the clause that starts at `from`: the next . ; ! ? (or Arabic ، ؛ ؟) followed by a space, or the end. */
function clauseEnd(text: string, from: number): number {
  for (let i = from; i < text.length; i++) {
    if (ENDS_CLAUSE.test(text[i]!) && (i + 1 === text.length || text[i + 1] === " ")) return i;
  }
  return text.length;
}

/** A verb that leads into the command right after it ("run reel doctor", «شغّل الأمر reel doctor»). */
const DANGLING_LEAD = /(?:(?<![\p{L}])(?:run|type|paste|enter|execute|use|using|via|with)(?: +(?:the|this))?(?: +commands?)?|(?:شغل|نفذ|اكتب|الصق|استخدم)(?: +(?:ال)?(?:امر|اوامر))?) *:? *$/iu;
const LEAD_IN_EN = /(?<![\p{L}])(?:run|type|paste|enter|execute)(?: +(?:this|the|following|these|commands?|it))* *:/giu;
const LEAD_IN_AR = /(?:شغل|نفذ|اكتب|الصق)(?: +(?:هذا|هذه))? +(?:ال)?(?:امر|اوامر)(?: +(?:ال)?تالي[هة]?)?/gu;

/** Every command span in the normalised text, unsorted. */
function rawSpans(text: string): Array<{ rule: CommandRule; start: number; end: number }> {
  const out: Array<{ rule: CommandRule; start: number; end: number }> = [];
  for (const m of text.matchAll(/`([^`]*)`/g)) {
    if (/ /.test(m[1]!)) out.push({ rule: "backticked-command", start: m.index!, end: m.index! + m[0].length });
  }
  for (const m of text.matchAll(PROGRAM)) {
    const name = m[1]!.toLowerCase();
    const end = invocationEnd(text, m.index! + m[0].length, name === "reel" ? "reel" : name === "claude" ? "claude" : "other");
    if (end > 0) out.push({ rule: "command", start: m.index!, end });
  }
  for (const m of text.matchAll(/whynotcut:\/\/[^ ]*/gi)) {
    const tok = m[0].replace(TRAILING, "");
    out.push({ rule: "launcher-link", start: m.index!, end: m.index! + tok.length });
  }
  for (const m of text.matchAll(/(?<![\p{L}\p{N}])claude *code(?![\p{L}\p{N}])/giu)) {
    out.push({ rule: "claude-code", start: m.index!, end: m.index! + m[0].length });
  }
  // a lead-in reaches over the command right after it, or to the end of its clause
  const commandAt = (i: number) => out.find((s) => s.start === i && (s.rule === "command" || s.rule === "backticked-command"));
  for (const re of [LEAD_IN_EN, LEAD_IN_AR]) {
    for (const m of text.matchAll(re)) {
      let p = m.index! + m[0].length;
      while (text[p] === " " || text[p] === ":") p++;
      const cmd = commandAt(p);
      out.push({ rule: "lead-in", start: m.index!, end: cmd ? cmd.end : clauseEnd(text, p) });
    }
  }
  // the verb that leads into a command belongs to it ("run reel doctor" -> one span)
  for (const s of out) {
    if (s.rule !== "command" && s.rule !== "backticked-command") continue;
    const lead = DANGLING_LEAD.exec(text.slice(0, s.start));
    if (lead) s.start = lead.index;
  }
  return out;
}

/** Every command span of a text, in the original text's indices, sorted by start. */
export function commandSpans(text: unknown): CommandSpan[] {
  if (typeof text !== "string" || text === "") return [];
  const n = normalise(text);
  return rawSpans(n.text)
    .map((s) => ({ rule: s.rule, start: n.map[s.start]!, end: s.end >= n.text.length ? text.length : n.map[s.end]! }))
    .sort((a, b) => a.start - b.start || b.end - a.end);
}

/** The rule the first command in a text breaks, or null when it holds none. */
export function commandIn(text: unknown): CommandRule | null {
  return commandSpans(text)[0]?.rule ?? null;
}

export const hasCommand = (text: unknown): boolean => commandIn(text) !== null;

/** Two or more words (Latin letters or Arabic): enough to tell the editor something. */
function meaningful(text: string): boolean {
  return text.split(/\s+/).filter((w) => /[A-Za-z]{2,}|[؀-ۿ]/.test(w)).length >= 2;
}

function tidy(text: string, sentence: boolean): string {
  let s = text
    .replace(/\(\s*(?:e\.g\.|i\.e\.|see|via|or|with|use)?[\s\/,;:|&+-]*\)|\[\s*\]|«\s*»|"\s*"|“\s*”|`\s*`/gi, " ")
    .replace(/\s+/g, " ")
    .replace(/\s+([.,;:!?)\]،؛؟])/g, "$1")
    .replace(/[,;:،؛]+\s*([.!?؟])/g, "$1")
    .replace(/([.!?؟])(?:\s*[,;:.،؛])+/g, "$1")
    .replace(/(?:\s+(?:and|or|then|و|ثم|أو))+\s*([.!?؟]?)$/i, "$1")
    .replace(/\s*[,;:،؛—–-]+\s*$/, "")
    .replace(/^[\s,;:.،؛)\]]+/, "")
    .replace(/^(?:and|or|then|ثم)\s+/i, "")
    .trim();
  if (sentence && s && !/[.!?؟]$/.test(s)) s += ".";
  return s.replace(/^[a-z]/, (c) => c.toUpperCase());
}

/**
 * The text with its command spans neutralised, for the editor's screen: the product name with "Code" after it becomes "Claude", every other
 * command span is removed together with the verb that leads into it, and what is left is tidied (empty brackets, stray
 * punctuation, a dangling "and"). The cause and the remedy stay whenever they survive. Returns the text unchanged when
 * it holds no command, and null when nothing meaningful is left (the caller shows its own generic sentence).
 */
export function neutralise(text: unknown): string | null {
  if (typeof text !== "string") return null;
  const spans = commandSpans(text);
  if (!spans.length) return text;
  let out = "";
  let at = 0;
  for (let i = 0; i < spans.length; ) {
    // merge overlapping spans; a group is replaced by "Claude" only when it is nothing but that product name
    let end = spans[i]!.end;
    let onlyName = spans[i]!.rule === "claude-code";
    const start = spans[i]!.start;
    let j = i + 1;
    for (; j < spans.length && spans[j]!.start < end; j++) {
      end = Math.max(end, spans[j]!.end);
      onlyName &&= spans[j]!.rule === "claude-code";
    }
    if (start >= at) out += text.slice(at, start);
    out += onlyName ? "Claude" : " ";
    at = Math.max(at, end);
    i = j;
  }
  out += text.slice(at);
  const clean = tidy(out, /[.!?؟]\s*$/.test(text));
  if (!meaningful(clean) || hasCommand(clean)) return null;
  return clean;
}
