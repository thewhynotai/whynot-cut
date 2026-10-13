// The "no command text on the editor's screen" scanner (Addendum C1.4, C2.2), not a test file itself: test/
// no-commands.test.ts runs it over the string table, the panel sources, the Premiere plugin's sources and its
// index.html / manifest.json. Commands live only in the log drawer (src/kit/log.ts and the log lines it shows) and in
// the Copy diagnostics payload (src/diagnostics.ts). What counts as a command is src/commands.ts's BROAD detector
// (commandIn / looksLikeCommand: high recall, for our own strings; the panel's runtime uses the precise one).
//
// String literals come from the TypeScript compiler's own parser (typescript/unstable/sync: the tsgo API that ships with
// the typescript devDependency), so a regular expression after `=>` or `)`, a nested template or an escape can never
// desynchronise a hand-written lexer. The parser also decodes escapes ("reel\x20serve", " "). On top of single
// literals the scan folds what builds one text at runtime: a `+` chain, parentheses included (("reel" + " ") +
// "serve"), "reel".concat(" serve"), an array joined with a literal separator (["reel", "serve"].join(" "), also after
// .concat), `x += " serve"` on a variable declared with a literal, and a template literal, where ${"literal"} reads as
// its text and any other ${...} as a space. A non-literal part of a chain, a concat or a joined array reads as a space.
// The broad detector applies NFKC before matching, so full-width text is caught too.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { API } from "typescript/unstable/sync";
import { createVirtualFileSystem } from "typescript/unstable/fs";
import { SyntaxKind } from "typescript/unstable/ast";
import type { Node } from "typescript/unstable/ast";
import { commandIn } from "../src/commands.ts";

export { commandIn };

/** panel-ui sources that may hold commands: the log drawer and the diagnostics payload. */
export const COMMAND_FILES: readonly string[] = ["kit/log.ts", "diagnostics.ts"];

/** The only file with an exempt log-lines array (the mock's sample log: a `log` array of [level, text] tuples). */
export const LOG_TUPLE_FILE = "mock.ts";

/** Parses TS sources with the compiler (one tsgo process for the batch). Keys are names, values the source text. */
export function parseSources(files: Readonly<Record<string, string>>): Map<string, Node> {
  const names = Object.keys(files);
  const vfs: Record<string, string> = {
    "/scan/tsconfig.json": JSON.stringify({ compilerOptions: { noLib: true, noResolve: true, types: [] }, files: names.map((_, i) => `f${i}.ts`) }),
  };
  names.forEach((n, i) => (vfs[`/scan/f${i}.ts`] = files[n]!));
  const api = new API({ fs: createVirtualFileSystem(vfs), cwd: "/scan" });
  try {
    const project = api.updateSnapshot({ openProjects: ["/scan/tsconfig.json"] }).getProject("/scan/tsconfig.json");
    if (!project) throw new Error("no-commands-scan: the compiler did not open the scan project");
    const out = new Map<string, Node>();
    names.forEach((n, i) => {
      const sf = project.program.getSourceFile(`/scan/f${i}.ts`);
      if (!sf) throw new Error(`no-commands-scan: the compiler did not parse ${n}`);
      out.set(n, sf);
    });
    return out;
  } finally {
    api.close();
  }
}

type AnyNode = Node & Record<string, unknown>;
const kindOf = (n: Node) => n.kind;
const prop = (n: Node, k: string) => (n as AnyNode)[k] as AnyNode;
const isStr = (n: Node) => kindOf(n) === SyntaxKind.StringLiteral || kindOf(n) === SyntaxKind.NoSubstitutionTemplateLiteral;
const LEVELS = new Set(["info", "warn", "error"]);

const isPlus = (n: Node) => kindOf(n) === SyntaxKind.BinaryExpression && kindOf(prop(n, "operatorToken")) === SyntaxKind.PlusToken;
const unparen = (n: Node): Node => (kindOf(n) === SyntaxKind.ParenthesizedExpression ? unparen(prop(n, "expression")) : n);
/** The method name of a call like x.concat(...) / x.join(...), or "". */
const methodOf = (n: Node): string => {
  if (kindOf(n) !== SyntaxKind.CallExpression) return "";
  const callee = prop(n, "expression");
  return kindOf(callee) === SyntaxKind.PropertyAccessExpression ? String(prop(callee, "name")["text"]) : "";
};
const argsOf = (n: Node) => (prop(n, "arguments") as unknown as readonly Node[]) ?? [];
const targetOf = (n: Node) => unparen(prop(prop(n, "expression"), "expression"));

/** The operands of a + chain, left to right, through parentheses. */
function plusOperands(n: Node, out: Node[] = []): Node[] {
  for (const side of [prop(n, "left"), prop(n, "right")]) {
    const s = unparen(side);
    if (isPlus(s)) plusOperands(s, out);
    else out.push(s);
  }
  return out;
}

/** The parts of an array an expression builds: an array literal, or one with .concat(...) after it; null otherwise. */
function arrayParts(n0: Node): Node[] | null {
  const n = unparen(n0);
  if (kindOf(n) === SyntaxKind.ArrayLiteralExpression) return [...(prop(n, "elements") as unknown as readonly Node[])];
  if (methodOf(n) === "concat") {
    const head = arrayParts(targetOf(n));
    if (!head) return null;
    for (const a of argsOf(n)) head.push(...(arrayParts(a) ?? [a]));
    return head;
  }
  return null;
}

/** The static text an expression builds, or null when it builds none; a non-literal part reads as a space. */
function fold(n0: Node): string | null {
  const n = unparen(n0);
  if (isStr(n)) return String((n as AnyNode)["text"]);
  if (kindOf(n) === SyntaxKind.TemplateExpression) {
    const spans = prop(n, "templateSpans") as unknown as readonly Node[];
    return String(prop(n, "head")["text"]) + spans.map((s) => (fold(prop(s, "expression")) ?? " ") + String(prop(s, "literal")["text"])).join("");
  }
  if (isPlus(n)) {
    const parts = plusOperands(n).map((p) => fold(p));
    return parts.some((p) => p !== null) ? parts.map((p) => p ?? " ").join("") : null;
  }
  const method = methodOf(n);
  if (method === "concat") {
    const head = fold(targetOf(n));
    if (head !== null) return head + argsOf(n).map((a) => fold(a) ?? " ").join("");
  }
  if (method === "join") {
    const parts = arrayParts(targetOf(n));
    const args = argsOf(n);
    const sepText = args.length ? fold(args[0]!) : ",";
    if (parts && sepText !== null) {
      const texts = parts.map((p) => fold(p));
      if (texts.some((p) => p !== null)) return texts.map((p) => p ?? " ").join(sepText);
    }
  }
  return null;
}

/** The name a node is bound to when it is a declaration's initializer or a property's value ("" otherwise). */
function boundName(n: Node): string {
  const p = n.parent;
  if (!p) return "";
  if ((kindOf(p) === SyntaxKind.PropertyAssignment || kindOf(p) === SyntaxKind.VariableDeclaration) && prop(p, "name")) {
    return String(prop(p, "name")["text"] ?? "");
  }
  return "";
}

/** A [level, text] tuple of the mock's log-lines array (a `log` array): log drawer data. */
function isLogTuple(n: Node): boolean {
  if (kindOf(n) !== SyntaxKind.ArrayLiteralExpression) return false;
  const els = prop(n, "elements") as unknown as readonly Node[];
  if (els.length !== 2 || !isStr(els[0]!) || !LEVELS.has(String((els[0] as AnyNode)["text"]))) return false;
  const list = n.parent;
  return !!list && kindOf(list) === SyntaxKind.ArrayLiteralExpression && boundName(list) === "log";
}

/** Every text a source builds: each literal, each template, each + chain, concat and joined array, folded, and each
 *  `+=` on a variable declared with a literal. In LOG_TUPLE_FILE the tuples of its `log` array are skipped. */
export function textsOf(sf: Node, file: string): string[] {
  const out: string[] = [];
  const vars = new Map<string, string>();
  const visit = (n: Node): void => {
    if (file === LOG_TUPLE_FILE && isLogTuple(n)) return;
    const k = kindOf(n);
    if (k !== SyntaxKind.ParenthesizedExpression) {
      const own = fold(n);
      if (own !== null) out.push(own);
    }
    if (k === SyntaxKind.VariableDeclaration && prop(n, "initializer")) {
      const init = fold(prop(n, "initializer"));
      if (init !== null) vars.set(String(prop(n, "name")["text"] ?? ""), init);
    }
    if (k === SyntaxKind.BinaryExpression && kindOf(prop(n, "operatorToken")) === SyntaxKind.PlusEqualsToken) {
      const left = unparen(prop(n, "left"));
      const name = kindOf(left) === SyntaxKind.Identifier ? String((left as AnyNode)["text"]) : "";
      if (vars.has(name)) {
        const acc = vars.get(name)! + (fold(prop(n, "right")) ?? " ");
        vars.set(name, acc);
        out.push(acc);
      }
    }
    n.forEachChild(visit);
  };
  visit(sf);
  return out;
}

/** Every text a TS source builds that holds a command, as "rule: text". */
export function commandTexts(sf: Node, file: string): string[] {
  const found: string[] = [];
  for (const text of new Set(textsOf(sf, file))) {
    const rule = commandIn(text);
    if (rule) found.push(`${rule}: ${text}`);
  }
  return found;
}

/** Parses one source and returns its command texts (for the guard's own regression cases). */
export function commandLiterals(src: string, file = "sample.ts"): string[] {
  return commandTexts(parseSources({ [file]: src }).get(file)!, file);
}

/** The .ts files under dir (recursive), as paths relative to it with forward slashes. */
export function tsFiles(dir: string): string[] {
  const out: string[] = [];
  const walk = (d: string) => {
    for (const name of readdirSync(d)) {
      const p = join(d, name);
      if (statSync(p).isDirectory()) walk(p);
      else if (name.endsWith(".ts") && !name.endsWith(".d.ts")) out.push(relative(dir, p).split(sep).join("/"));
    }
  };
  walk(dir);
  return out.sort();
}

/** The attributes a person reads or hears. */
const SCREEN_ATTRS = /\s(?:title|aria-label|aria-description|placeholder|alt|aria-valuetext|value)=(?:"([^"]*)"|'([^']*)')/g;

/** What a rendered panel (or a plugin page) puts in front of the editor, outside the log drawer: the text between tags
 *  and the values of the attributes a person reads or hears (title, aria-label, aria-description, placeholder, alt,
 *  aria-valuetext, value; double- or single-quoted), entities decoded. Script and style bodies are not screen text. */
export function screenText(html: string): string {
  const visible = html
    .replace(/<script\b[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[\s\S]*?<\/style>/gi, " ")
    .replace(/<section class="sec sec-log">[\s\S]*?<\/section>/g, " ")
    .replace(/<ul class="kit-log-lines"[\s\S]*?<\/ul>/g, " ");
  const attrs = [...visible.matchAll(SCREEN_ATTRS)].map((m) => m[1] ?? m[2] ?? "");
  const decode = (s: string) =>
    s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&");
  return decode([visible.replace(/<[^>]*>/g, " "), ...attrs].join(" \n "));
}

/** The texts of a Premiere plugin file the editor can see: every string value of manifest.json (labels, names), or the
 *  screen text of index.html. */
export function pluginTexts(content: string, name: string): string[] {
  if (name.endsWith(".json")) {
    const out: string[] = [];
    const walk = (v: unknown): void => {
      if (typeof v === "string") out.push(v);
      else if (Array.isArray(v)) v.forEach(walk);
      else if (v && typeof v === "object") Object.values(v).forEach(walk);
    };
    walk(JSON.parse(content));
    return out;
  }
  return [screenText(content)];
}

/** The Premiere plugin's own page and manifest (premiere-uxp/plugin/). */
export function scannedPluginFiles(panelUi: string): string[] {
  const dir = join(panelUi, "..", "premiere-uxp", "plugin");
  return [join(dir, "index.html"), join(dir, "manifest.json")];
}

/** Every command the panel can show: panel-ui/src/** except COMMAND_FILES, every i18n value, the Premiere plugin's
 *  sources (premiere-uxp/src/**: its offline source, shell and host adapter hand texts to the panel) and its
 *  index.html / manifest.json. As "where: rule: text". */
export function commandsOnScreen(panelUi: string): string[] {
  const found: string[] = [];
  const sources: Record<string, string> = {};
  const src = join(panelUi, "src");
  for (const f of tsFiles(src)) if (!COMMAND_FILES.includes(f)) sources[`panel-ui/src/${f}`] = readFileSync(join(src, f), "utf8");
  const uxp = join(panelUi, "..", "premiere-uxp", "src");
  for (const f of tsFiles(uxp)) sources[`premiere-uxp/src/${f}`] = readFileSync(join(uxp, f), "utf8");
  for (const [name, sf] of parseSources(sources)) {
    const file = name.startsWith("panel-ui/src/") ? name.slice("panel-ui/src/".length) : name;
    for (const hit of commandTexts(sf, file)) found.push(`${name}: ${hit}`);
  }
  for (const lang of ["en", "ar"]) {
    const table = JSON.parse(readFileSync(join(panelUi, "i18n", `${lang}.json`), "utf8")) as Record<string, string>;
    for (const [k, v] of Object.entries(table)) {
      const rule = commandIn(String(v));
      if (rule) found.push(`i18n/${lang}.json ${k}: ${rule}: ${v}`);
    }
  }
  for (const f of scannedPluginFiles(panelUi)) {
    for (const text of pluginTexts(readFileSync(f, "utf8"), f)) {
      const rule = commandIn(text);
      if (rule) found.push(`premiere-uxp/plugin/${f.split(/[\\/]/).pop()}: ${rule}: ${text}`);
    }
  }
  return found;
}
