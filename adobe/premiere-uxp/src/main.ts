// WhyNot Cut panel entry (bundled to index.js, loaded by plugin/index.html).
// The panel talks to the local engine daemon (`reel serve`) over two WebSocket sessions:
//   - DaemonSource (panel-ui) is the panel's data source, a requester: live state, intents, commands, cancel; its
//     link diagnosis is in the offline banner. Without a WebSocket / fs / home folder the panel mounts OfflineSource.
//   - the host link (src/host-link.ts) runs the Premiere ops the engine routes to this panel (src/host-adapter.ts).
// `WNC_MOCK=1` at build time swaps in the panel kit's MockSource for visual checks (no engine link at all); a normal
// build cannot contain it.
import { DaemonSource } from "../../panel-ui/src/daemon-source.ts";
import { MockSource } from "../../panel-ui/src/mock.ts";
import { startHostLink } from "./host-link.ts";
import { hostDetailOf, languageOf, OfflineSource } from "./offline-source.ts";
import type { OpEnv } from "./ops/types.ts";
import { startShell } from "./shell.ts";
import type { PanelLifecycle, ShellDoc, ShellEnv } from "./shell.ts";
import { createDaemonTransport, readEngineJson, timerOf } from "./uxp-transport.ts";
import type { FetchFn, LinkGlobals, WebSocketCtor } from "./uxp-transport.ts";
import type { UxpFs, UxpModule, UxpOs } from "./uxp-types.ts";
import { version as manifestVersion } from "../plugin/manifest.json";

declare const require: (id: string) => unknown;
/** replaced by esbuild `define` (scripts/build.mjs): true only for `WNC_MOCK=1` builds */
declare const __WNC_MOCK__: boolean;
/** replaced by esbuild `define`: "<short git hash>[+dirty] <UTC build time>" (scripts/build.mjs buildStamp) */
declare const __WNC_BUILD__: string;

// literal require() calls, exactly as the spike proved them in Premiere: only the host modules the plugin uses
function hostModule(id: string): unknown {
  if (id === "premierepro") return require("premierepro");
  if (id === "uxp") return require("uxp");
  if (id === "fs") return require("fs");
  if (id === "os") return require("os");
  throw new Error(`unknown host module ${id}`);
}
function maybe<T>(id: string): T | undefined {
  try {
    return hostModule(id) as T;
  } catch {
    return undefined;
  }
}

const g = globalThis as { WebSocket?: WebSocketCtor; fetch?: FetchFn; console?: { log?: (s: string) => void } };
const globals: LinkGlobals = {
  fs: undefined,
  os: undefined,
  WebSocket: g.WebSocket,
  fetch: typeof g.fetch === "function" ? (url, init) => (g.fetch as FetchFn)(url, init) : undefined,
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
  now: () => Date.now(),
  log: (line) => g.console?.log?.(`WhyNot Cut: ${line}`),
};
let linkReady = false;
function linkGlobals(): LinkGlobals {
  if (!linkReady && !__WNC_MOCK__) {
    linkReady = true;
    globals.fs = maybe<UxpFs>("fs");
    globals.os = maybe<UxpOs>("os");
  }
  return globals;
}

const uxpModule = () => maybe<UxpModule>("uxp");
/** the plugin's own version (uxp.versions.plugin, else the manifest it was built with), 1-64 characters */
const bundleVersion = () => (String(uxpModule()?.versions?.plugin ?? "") || String(manifestVersion) || "0.0.0").slice(0, 64);

const env: ShellEnv = {
  document: document as unknown as ShellDoc,
  // not read here: in UXP the `navigator.clipboard` getter throws without the clipboard permission
  get navigator() {
    return (globalThis as { navigator?: ShellEnv["navigator"] }).navigator;
  },
  require: (id) => {
    if (id === "premierepro" || id === "uxp") return hostModule(id);
    throw new Error(`unknown host module ${id}`);
  },
  createSource: (info) => {
    if (__WNC_MOCK__) return new MockSource({ language: languageOf(info.uiLocale) });
    const transport = createDaemonTransport(linkGlobals());
    if (!transport) return new OfflineSource(info);
    return new DaemonSource({
      transport,
      version: bundleVersion(),
      build: __WNC_BUILD__,
      language: languageOf(info.uiLocale),
      localHost: { state: "uxp", detail: hostDetailOf(info.hostVersion) },
    });
  },
  startHostLink: () => {
    if (__WNC_MOCK__) return null;
    const lg = linkGlobals();
    const WS = lg.WebSocket;
    if (typeof WS !== "function" || !lg.fs) return null;
    const opEnv: OpEnv = {
      ppro: () => hostModule("premierepro") as ReturnType<OpEnv["ppro"]>,
      fs: () => lg.fs as UxpFs,
      hostVersion: () => String(uxpModule()?.host?.version ?? ""),
      bundleVersion: bundleVersion(),
      sleep: (ms) => new Promise<void>((r) => setTimeout(r, ms)),
      now: () => Date.now(),
    };
    return startHostLink({
      readEngineJson: () => readEngineJson(lg.fs, lg.os),
      openSocket: (url) => new WS(url),
      env: opEnv,
      setTimer: timerOf(lg),
      log: (level, text) => (level === "info" ? g.console?.log?.(text) : g.console?.log?.(`[${level}] ${text}`)),
    });
  },
  build: { version: bundleVersion(), build: __WNC_BUILD__ },
  onLifecycle: (handlers: PanelLifecycle) => {
    // the manifest's one panel. show / hide are no-ops in the shell (the sessions outlive a hidden panel; Premiere's
    // events are unmeasured); destroy ends both sessions.
    const entrypoints = (uxpModule() as { entrypoints?: { setup?: (cfg: unknown) => void } } | undefined)?.entrypoints;
    entrypoints?.setup?.({
      panels: {
        whynotCut: {
          show: () => handlers.show(),
          hide: () => handlers.hide(),
          destroy: () => handlers.destroy(),
        },
      },
    });
  },
};

startShell(env);
