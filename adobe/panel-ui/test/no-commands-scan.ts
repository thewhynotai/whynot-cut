// The "no command text on the editor's screen" scanner (Addendum C1.4, C2.2), not a test file itself: test/
// no-commands.test.ts runs it over the string table, the panel sources and the Premiere plugin's sources. Commands live
// only in the log drawer (src/kit/log.ts and the log lines it shows) and in the Copy diagnostics payload
// (src/diagnostics.ts). What counts as a command is src/commands.ts: the SAME detector the panel uses at runtime.
//
// String literals come from the TypeScript compiler's own parser (typescript/unstable/sync: the tsgo API that ships with
// the typescript devDependency), so a regular expression after `=>` or `)`, a nested template or an escape can never
// desynchronise a hand-written lexer. The parser also decodes escapes ("reel\x20serve", " "). On top of single
// literals the scan folds what builds one text at runtime: a `+` chain ("reel" + " serve"), an array joined with a
// literal separator (["reel", "serve"].join(" ")) and a template literal, where each ${...} reads as a space
// (`reel${" "}doctor`). A non-literal part of a `+` chain or a joined array reads as a space too.
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

/** The only file whose [level, text] tuples are log drawer data (the mock's sample log). */
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
const isStr = (n: Node) => kindOf(n) === SyntaxKind.StringLiteral || kindOf(n) === SyntaxKind.NoSubstitutionTemplateLiteral;
const LEVELS = new Set(["info", "warn", "error"]);

/** The static text of an expression, or null when it is not a text literal; ${...} reads as a space. */
function staticText(n: Node): string | null {
  const a = n as AnyNode;
  if (isStr(n)) return String(a["text"]);
  if (kindOf(n) === SyntaxKind.TemplateExpression) {
    const head = a["head"] as AnyNode;
    const spans = a["templateSpans"] as readonly AnyNode[];
    return String(head["text"]) + spans.map((s) => " " + String((s["literal"] as AnyNode)["text"])).join("");
  }
  if (kindOf(n) === SyntaxKind.ParenthesizedExpression) return staticText(a["expression"] as Node);
  return null;
}

const isPlus = (n: Node) =>
  kindOf(n) === SyntaxKind.BinaryExpression && kindOf((n as AnyNode)["operatorToken"] as Node) === SyntaxKind.PlusToken;

/** The operands of a + chain, left to right. */
function plusOperands(n: Node, out: Node[] = []): Node[] {
  const a = n as AnyNode;
  for (const side of [a["left"] as Node, a["right"] as Node]) {
    if (isPlus(side)) plusOperands(side, out);
    else out.push(side);
  }
  return out;
}

/** Every text a source builds: each literal, each template (expressions as spaces), each + chain and each joined
 *  array literal, folded. In LOG_TUPLE_FILE the text of a [level, text] tuple is skipped (log drawer data). */
export function textsOf(sf: Node, file: string): string[] {
  const out: string[] = [];
  const visit = (n: Node): void => {
    const a = n as AnyNode;
    if (file === LOG_TUPLE_FILE && kindOf(n) === SyntaxKind.ArrayLiteralExpression) {
      const els = a["elements"] as readonly Node[];
      if (els.length === 2 && isStr(els[0]!) && LEVELS.has(String((els[0] as AnyNode)["text"]))) return;
    }
    const own = staticText(n);
    if (own !== null && kindOf(n) !== SyntaxKind.ParenthesizedExpression) out.push(own);
    if (isPlus(n) && !(n.parent && isPlus(n.parent))) {
      const parts = plusOperands(n).map((p) => staticText(p));
      if (parts.filter((p) => p !== null).length >= 2) out.push(parts.map((p) => p ?? " ").join(""));
    }
    if (kindOf(n) === SyntaxKind.CallExpression) {
      const callee = a["expression"] as AnyNode;
      if (kindOf(callee as Node) === SyntaxKind.PropertyAccessExpression && String((callee["name"] as AnyNode)["text"]) === "join") {
        const target = callee["expression"] as AnyNode;
        if (kindOf(target as Node) === SyntaxKind.ArrayLiteralExpression) {
          const args = a["arguments"] as readonly Node[];
          const sepText = args.length ? staticText(args[0]!) : ",";
          const parts = (target["elements"] as readonly Node[]).map((e) => staticText(e));
          if (sepText !== null && parts.some((p) => p !== null)) out.push(parts.map((p) => p ?? " ").join(sepText));
        }
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
  for (const text of textsOf(sf, file)) {
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

/** What a rendered panel puts in front of the editor, outside the log drawer: the text between tags and the values of
 *  the attributes a person reads or hears (title, aria-label, placeholder, alt, aria-valuetext), entities decoded. */
export function screenText(html: string): string {
  const visible = html
    .replace(/<section class="sec sec-log">[\s\S]*?<\/section>/g, " ")
    .replace(/<ul class="kit-log-lines"[\s\S]*?<\/ul>/g, " ");
  const attrs = [...visible.matchAll(/\s(?:title|aria-label|placeholder|alt|aria-valuetext)="([^"]*)"/g)].map((m) => m[1]!);
  const decode = (s: string) =>
    s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&");
  return decode([visible.replace(/<[^>]*>/g, " "), ...attrs].join(" \n "));
}

/** Every command the panel can show: panel-ui/src/** except COMMAND_FILES, every i18n value, and the Premiere plugin's
 *  sources (premiere-uxp/src/**: its offline source, shell and host adapter hand texts to the panel). As
 *  "where: rule: text". */
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
  return found;
}
