// WhyNot Cut panel entry (bundled to index.js, loaded by plugin/index.html).
// Until the engine daemon exists (reel serve, T6.2) the panel shows "Engine: not running" (OfflineSource).
// `WNC_MOCK=1` at build time swaps in the panel kit's MockSource for visual checks; a normal build cannot contain it.
import { MockSource } from "../../panel-ui/src/mock.ts";
import { languageOf, OfflineSource } from "./offline-source.ts";
import { startShell } from "./shell.ts";
import type { ShellDoc, ShellEnv } from "./shell.ts";

declare const require: (id: string) => unknown;
/** replaced by esbuild `define` (scripts/build.mjs): true only for `WNC_MOCK=1` builds */
declare const __WNC_MOCK__: boolean;

const env: ShellEnv = {
  document: document as unknown as ShellDoc,
  // not read here: in UXP the `navigator.clipboard` getter throws without the clipboard permission
  get navigator() {
    return (globalThis as { navigator?: ShellEnv["navigator"] }).navigator;
  },
  // literal require() calls, exactly as the spike proved them in Premiere: only the two host modules the shell uses
  require: (id) => {
    if (id === "premierepro") return require("premierepro");
    if (id === "uxp") return require("uxp");
    throw new Error(`unknown host module ${id}`);
  },
  createSource: (info) => (__WNC_MOCK__ ? new MockSource({ language: languageOf(info.uiLocale) }) : new OfflineSource(info)),
};

startShell(env);
