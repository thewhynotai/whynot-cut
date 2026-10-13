// What counts as command text (Addendum C1.4, C2.2). Commands live only in the log drawer and the Copy diagnostics
// payload; the editor's screen shows plain sentences and one fix button. TWO detectors, two jobs (C2.2 review round 2:
// no sentence surgery):
//
// looksLikeCommand / commandIn / commandSpans: HIGH RECALL, for the guard test on OUR OWN strings (test/
// no-commands-scan.ts: the string table, every source literal, the rendered panel). A false alarm there only means a
// sentence of ours gets reworded. It flags:
//   - a program with an argument: reel, claude, npm, npx, node, python, python3, py, pip, git, powershell, pwsh, winget,
//     brew, bash, sh, curl, irm, iex, cd, chmod, taskkill, setx, echo; path-qualified too (~/x/reel, ./reel,
//     C:\x\reel.exe, /usr/local/bin/reel, also with no argument). For reel the first argument must look like one (a
//     flag, a known subcommand, a hyphenated name or a path) and for claude too (a flag, a known subcommand or a quoted
//     prompt), so "a 58 s reel" and "your Claude session" stay plain words; for the others any word that is not a
//     common English word counts ("npx x"). Arguments are read case-insensitively ("reel previews C0239") and a "("
//     right after a word opens its arguments ("reel previews(C0239)"); reel-<subcommand> counts too ("reel-doctor");
//   - a `backticked` span with whitespace in it (a single `token`, a folder or file name, is not a command);
//   - a whynotcut:// link; the product name with "Code" after it (the panel says "Claude");
//   - a lead-in: "run:", "type:", "paste:", "enter:", and the Arabic family «شغّل / نفّذ / اكتب / الصق الأمر».
//
// containsRuntimeCommand: HIGH PRECISION, for engine and host texts at runtime (render.ts, mount.ts, kit/toast.ts via
// runtimeText). A text it flags is never cut up: the panel shows its own localized sentence instead, and the raw text
// goes to the log, token-scrubbed. So it must not flag a normal sentence ("The reel plan is ready", "Python 3.9 is
// required", "Claude login expired"). It matches only:
//   - a backtick span with a space in it, or one that starts with a program name (`reel`, `~/bin/reel.exe`);
//   - a program name, path-qualified or not, followed by a flag (-x / --x);
//   - reel or claude (or reel-<subcommand>) followed by a known subcommand (claude's own may follow: "claude auth
//     login") and then an id (C0239), a path, a flag, a quoted string or the end of the clause (. , ; ! ? ) or the end);
//     never after a determiner ("the reel plan C0239"), never at a clause end after a preposition ("waiting for reel
//     build."), and a plain word after it ("is", "are", "failed", "ready", "log", "and") means a sentence, unless a
//     lead-in verb comes right before the program ("Run reel doctor and press Try again", «شغّل الأمر: reel doctor ثم»);
//   - a tool that is never an English word (npm, npx, pip, git, winget, brew, irm, iex, chmod, taskkill, setx) followed
//     by an argument that is not a stop word or a bare number; an interpreter or shell word (python, py, node, bash,
//     sh, curl, powershell, pwsh, echo, cd) followed by a path, a URL or a variable;
//   - "Claude Code" (runtimeText first swaps it for "Claude" in place, so this only catches a form the swap missed);
//   - a whynotcut:// link (it can only be a launcher link).
//
// Both detectors read a normalised copy: NFKC per character (full-width letters and spaces), any whitespace (NBSP,
// tab) as a space, Arabic diacritics (tashkeel), tatweel and zero-width characters dropped, and the alef forms أ إ آ ٱ
// as ا. Nothing here is shown on screen: the lists below are single words, and the patterns are regular expressions.

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
/** reel-<name> is a command (reel-doctor); not the names that are also files or nouns (reel-profile, reel-plan). */
const REEL_HYPHEN: ReadonlySet<string> = new Set([
  "doctor", "setup", "serve", "previews", "transcribe", "preflight", "scaffold", "validate", "verify", "handoff",
  "rebuild", "approve", "build", "install", "update", "bench", "discover", "sfx", "qc", "watch", "lock", "inbox",
]);
/** claude's subcommands. */
const CLAUDE_SUBCOMMANDS: ReadonlySet<string> = new Set([
  "auth", "login", "logout", "mcp", "plugin", "plugins", "update", "doctor", "config", "install", "migrate-installer",
  "setup-token", "agents", "resume", "continue",
]);
/** what may follow a claude subcommand (claude auth login, claude mcp add, claude plugin install). */
const CLAUDE_SUB2: ReadonlySet<string> = new Set([
  "login", "logout", "status", "add", "remove", "list", "get", "install", "uninstall", "update", "enable", "disable",
  "marketplace",
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

/** Programs that are never an English word: an argument after one makes a command (runtime). */
const TOOLS: ReadonlySet<string> = new Set(["npm", "npx", "pip", "pip3", "git", "winget", "brew", "irm", "iex", "chmod", "taskkill", "setx"]);
const PROGRAM_NAMES = "reel|claude|npm|npx|node|python3?|py|pip3?|git|powershell|pwsh|winget|brew|bash|sh|curl|irm|iex|cd|chmod|taskkill|setx|echo";

/** Ignored when matching: Arabic diacritics (tashkeel), the superscript alef, tatweel, zero-width characters. */
const IGNORED = /[\u064b-\u0670\u065f\u0640\u200b-\u200f\u2060\ufeff]/;
const ALEF_FORMS = /[أإآٱ]/;

/** The cap on an engine or host text before the runtime detector reads it (and before it is shown). */
export const RUNTIME_MAX = 4000;

interface Normalised {
  /** whitespace as " ", ignored characters dropped, alef forms as ا, NFKC per character */
  text: string;
  /** map[i] = the original index of text[i]; map[text.length] = the original length */
  map: number[];
}

function normalise(src: string): Normalised {
  let text = "";
  const map: number[] = [];
  for (let i = 0; i < src.length; ) {
    const cp = src.codePointAt(i)!;
    const width = cp > 0xffff ? 2 : 1;
    for (const c of String.fromCodePoint(cp).normalize("NFKC")) {
      if (IGNORED.test(c)) continue;
      const out = /\s/.test(c) ? " " : ALEF_FORMS.test(c) ? "ا" : c;
      for (const u of out) {
        // a character NFKC turned into two UTF-16 units maps both to its source index
        for (let k = 0; k < u.length; k++) {
          text += u[k];
          map.push(i);
        }
      }
    }
    i += width;
  }
  map.push(src.length);
  return { text, map };
}

const PROGRAM = new RegExp(`(?:(?<=[\\/\\\\])|(?<![\\p{L}\\p{N}_.\\/\\\\-]))(${PROGRAM_NAMES})(?:\\.exe)?(?![\\p{L}\\p{N}_])`, "giu");
const STARTS_WITH_PROGRAM = new RegExp(`^(?:\\S*[\\/\\\\])?(?:${PROGRAM_NAMES})(?:\\.exe)?(?![\\p{L}\\p{N}_.\\/\\\\-])`, "iu");
/** what makes "~/x/" or "C:\x\" a path in front of a program name */
const PATH_PREFIX = /^(?:~|\.{1,2}|[a-z]:|%\w+%|\$\w+)?(?:[\/\\][^\/\\ ]*)*[\/\\]$/i;
const FLAG = /^--?[a-z0-9]/i;
const PATHISH = /[\/\\=]|^[.~$%]|\.[a-z0-9]{1,5}$/i;
const QUOTED = /^["'“«]/;
const ARG_WORD = /^[a-z0-9@][\w@.:~-]*$/i;
/** punctuation that may end a token without being part of it (it also ends the invocation) */
const TRAILING = /[.,;:!?)\]}»"'”`،؛؟]+$/;
const ENDS_CLAUSE = /[.;!?،؛؟]/;
/** a plain word after the first argument ("claude auth login", "brew install ffmpeg") */
const PLAIN_WORD = /^[a-z]+$/i;
const CLAUDE_CODE = /(?<![\p{L}\p{N}])claude *code(?![\p{L}\p{N}])/iu;

type Program = "reel" | "claude" | "other";

interface Tok {
  start: number;
  /** the token without trailing punctuation (a quoted token keeps its quotes) */
  tok: string;
  /** the trailing punctuation cut off ("" when none) */
  trail: string;
  /** where the next token is looked for */
  next: number;
  quoted: boolean;
}

/** The token at p (after spaces): words end at a space or at "(" ("previews(C0239)" -> "previews", then "C0239"). */
function tokenAt(text: string, p: number): Tok | null {
  while (text[p] === " ") p++;
  if (p >= text.length) return null;
  if (QUOTED.test(text[p]!)) {
    const close = { '"': '"', "'": "'", "“": "”", "«": "»" }[text[p]!]!;
    const q = text.indexOf(close, p + 1);
    const end = q < 0 ? text.length : q + 1;
    return { start: p, tok: text.slice(p, end), trail: "", next: end, quoted: true };
  }
  let end = p;
  while (end < text.length && text[end] !== " " && (text[end] !== "(" || end === p)) end++;
  const raw = text.slice(p, end);
  const trail = TRAILING.exec(raw)?.[0] ?? "";
  return { start: p, tok: raw.slice(0, raw.length - trail.length), trail, next: text[end] === "(" ? end + 1 : end, quoted: false };
}

/** Where the program name at idx really starts: the start of a path in front of it, or idx. */
function programStart(text: string, idx: number): { start: number; pathQualified: boolean } {
  if (idx === 0 || !/[\/\\]/.test(text[idx - 1]!)) return { start: idx, pathQualified: false };
  let s = idx;
  while (s > 0 && !/[ "'“«`(\[]/.test(text[s - 1]!)) s--;
  return PATH_PREFIX.test(text.slice(s, idx)) ? { start: s, pathQualified: true } : { start: idx, pathQualified: false };
}

// ------------------------------------------------------------------------------------------- broad (the guard)

function firstArgOk(program: Program, tok: string): boolean {
  const low = tok.toLowerCase();
  if (FLAG.test(tok)) return true;
  if (program === "reel") return REEL_SUBCOMMANDS.has(low) || /^[a-z]+(?:-[a-z0-9]+)+$/i.test(tok) || PATHISH.test(tok);
  if (program === "claude") return CLAUDE_SUBCOMMANDS.has(low) || QUOTED.test(tok);
  return QUOTED.test(tok) || PATHISH.test(tok) || /^\+[a-z]/i.test(tok) || (ARG_WORD.test(tok) && !STOP_WORDS.has(low));
}

const nextArgOk = (tok: string): boolean =>
  FLAG.test(tok) || QUOTED.test(tok) || PATHISH.test(tok) || (ARG_WORD.test(tok) && !STOP_WORDS.has(tok.toLowerCase()));

/** The end (in normalised text) of the program invocation whose name ends at `at`, or -1 when no argument follows.
 *  After the first argument come flags, paths, quoted strings and identifiers (dev:build, C0239), plus at most one
 *  plain word (none for reel: its subcommands have no subcommands), so "part of reel serve ships" stops at "serve". */
function invocationEnd(text: string, at: number, program: Program): number {
  let end = -1;
  let p = at;
  let plain = program === "reel" ? 0 : 1;
  for (let first = true; ; first = false) {
    const t = tokenAt(text, p);
    if (!t || !t.tok || !(first ? firstArgOk(program, t.tok) : nextArgOk(t.tok))) break;
    if (!first && !t.quoted && PLAIN_WORD.test(t.tok) && plain-- <= 0) break;
    end = t.start + t.tok.length;
    if (t.trail) break;
    p = t.next;
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
    const { start, pathQualified } = programStart(text, m.index!);
    const after = m.index! + m[0].length;
    if (name === "reel" && text[after] === "-") {
      // reel-doctor: one word, the hyphen in place of the space
      const w = /^-([a-z]+)(?![\p{L}\p{N}_-])/iu.exec(text.slice(after));
      if (w && REEL_HYPHEN.has(w[1]!.toLowerCase())) out.push({ rule: "command", start, end: after + w[0].length });
      continue;
    }
    const end = text[after] === " " || text[after] === "(" ? invocationEnd(text, after, name === "reel" ? "reel" : name === "claude" ? "claude" : "other") : -1;
    if (end > 0) out.push({ rule: "command", start, end });
    else if (pathQualified && (after >= text.length || /[ ,;:!?)\]"'`]/.test(text[after]!))) out.push({ rule: "command", start, end: after });
  }
  for (const m of text.matchAll(/whynotcut:\/\/[^ ]*/gi)) {
    const tok = m[0].replace(TRAILING, "");
    out.push({ rule: "launcher-link", start: m.index!, end: m.index! + tok.length });
  }
  for (const m of text.matchAll(new RegExp(CLAUDE_CODE.source, "giu"))) {
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

/** Every command span of a text (the broad detector), in the original text's indices, sorted by start. */
export function commandSpans(text: unknown): CommandSpan[] {
  if (typeof text !== "string" || text === "") return [];
  const n = normalise(text);
  return rawSpans(n.text)
    .map((s) => ({ rule: s.rule, start: n.map[s.start]!, end: s.end >= n.text.length ? text.length : n.map[s.end]! }))
    .sort((a, b) => a.start - b.start || b.end - a.end);
}

/** The rule the first command in a text breaks (the broad detector), or null when it holds none. */
export function commandIn(text: unknown): CommandRule | null {
  return commandSpans(text)[0]?.rule ?? null;
}

/** High recall: anything that may read as a command. The guard test runs it over the panel's own strings. */
export const looksLikeCommand = (text: unknown): boolean => commandIn(text) !== null;

// ------------------------------------------------------------------------------------------- precise (runtime)

/** A word in front of the program that makes it a noun: "the reel plan", "your Claude login". */
const DETERMINER_BEFORE = /(?<![\p{L}\p{N}])(?:the|a|an|your|my|our|their|his|her|its|this|that|these|those|each|every|any|no|new|same|current|last|next)[^\p{L}\p{N}]*$/iu;
/** A preposition in front of the program: at a clause end it is a noun ("waiting for reel build."). */
const PREP_BEFORE = /(?<![\p{L}\p{N}])(?:for|of|in|on|at|by|from|after|before|during|with|to|until|about)[^\p{L}\p{N}]*$/iu;
/** A verb that leads into the command right after it: "Run reel doctor and ...", «شغّل الأمر: reel doctor ثم». */
const LEAD_BEFORE = /(?:(?<![\p{L}])(?:run|type|paste|enter|execute)(?: +(?:the|this) +commands?| +commands?)?|(?:شغل|نفذ|اكتب|الصق)(?: +(?:ال)?(?:امر|اوامر))?) *:? *["'“«`(]?$/iu;
const NUMBER = /^\d+(?:[.,]\d+)*$/;
/** an id: letters and digits together (C0239, EP01_R03, v2) */
const isId = (tok: string) => /^(?=\S*\d)(?=\S*[a-z])[a-z0-9][\w.:@-]*$/i.test(tok);
/** a path, a URL, a file name with an extension, or a variable ($HOME, %PATH%) */
const isPath = (tok: string) =>
  /[\/\\]/.test(tok) ||
  /^[~$%]/.test(tok) ||
  /^\.\.?$/.test(tok) ||
  (/^[\w-]*[a-z][\w-]*(?:\.[\w-]+)*\.[a-z][a-z0-9]{0,4}$/i.test(tok) && !/^(?:e\.g|i\.e)$/i.test(tok));

/** Is the program name matched at idx (length len) the start of a command, by the runtime rules? */
function runtimeInvocation(text: string, idx: number, len: number, name: string): boolean {
  const after = idx + len;
  const { start, pathQualified } = programStart(text, idx);
  const before = text.slice(0, start);
  const lead = LEAD_BEFORE.test(before);
  const noun = !pathQualified && DETERMINER_BEFORE.test(before);
  let cur: Tok | null;
  if (name === "reel" && text[after] === "-") {
    const w = /^-([a-z]+)(?![\p{L}\p{N}_-])/iu.exec(text.slice(after));
    if (!w || !REEL_HYPHEN.has(w[1]!.toLowerCase())) return false;
    cur = tokenAt(text, after + 1);
  } else {
    if (text[after] !== " " && text[after] !== "(") return false;
    cur = tokenAt(text, after);
    if (!cur || !cur.tok) return false;
    if (FLAG.test(cur.tok)) return true; // a program followed by a flag
    if (noun) return false;
    if (TOOLS.has(name)) return !NUMBER.test(cur.tok) && !STOP_WORDS.has(cur.tok.toLowerCase());
    if (name !== "reel" && name !== "claude") return !cur.quoted && isPath(cur.tok); // python x.py, cd ~/x, curl https://...
    const subs = name === "reel" ? REEL_SUBCOMMANDS : CLAUDE_SUBCOMMANDS;
    if (cur.quoted || !subs.has(cur.tok.toLowerCase())) return false;
  }
  if (!cur || noun) return false;
  // claude's own subcommands may follow its subcommand: claude auth login
  while (name === "claude" && !cur.trail) {
    const nx = tokenAt(text, cur.next);
    if (!nx || nx.quoted || !CLAUDE_SUB2.has(nx.tok.toLowerCase())) break;
    cur = nx;
  }
  const clauseEndOk = !PREP_BEFORE.test(before) || lead;
  if (cur.trail) return (/^[.,;!?)\]}»”`،؛؟]/.test(cur.trail) && clauseEndOk) || lead;
  const nx = tokenAt(text, cur.next);
  if (!nx || !nx.tok) return clauseEndOk;
  if (FLAG.test(nx.tok) || nx.quoted || isPath(nx.tok) || isId(nx.tok)) return true;
  return lead;
}

/** High precision: does an engine or host text hold a command? (the runtime rules above) */
export function containsRuntimeCommand(text: unknown): boolean {
  if (typeof text !== "string" || text === "") return false;
  const n = normalise(text.slice(0, RUNTIME_MAX)).text;
  for (const m of n.matchAll(/`([^`]*)`/g)) {
    const inner = m[1]!.trim();
    if (/ /.test(inner) || STARTS_WITH_PROGRAM.test(inner)) return true;
  }
  if (/whynotcut:\/\//i.test(n) || CLAUDE_CODE.test(n)) return true;
  for (const m of n.matchAll(PROGRAM)) {
    if (runtimeInvocation(n, m.index!, m[0].length, m[1]!.toLowerCase())) return true;
  }
  return false;
}

/**
 * An engine or host text as the editor may see it: capped at RUNTIME_MAX, the product name with "Code" after it
 * swapped for "Claude" in place (a safe single-token swap), and null when it still holds a command: the caller then
 * shows its own localized sentence (and puts the raw text in the log). Never cut up. A non-string reads as "".
 */
export function runtimeText(text: unknown): string | null {
  if (typeof text !== "string") return "";
  const swapped = text.slice(0, RUNTIME_MAX).replace(/(?<![\p{L}\p{N}])claude[\s\u00a0]*code(?![\p{L}\p{N}])/giu, "Claude");
  return containsRuntimeCommand(swapped) ? null : swapped;
}
