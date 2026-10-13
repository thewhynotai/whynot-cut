// The plugin shell: wires the shared panel (panel-ui mount) to Premiere. main.ts calls startShell once with the real
// page; the tests call it with fakes. This file never imports MockSource: main.ts picks the data source at build time
// (the WNC_MOCK build flag), so a normal build cannot carry mock data.
//
// Two engine sessions, both chosen by main.ts:
//   - the panel's data source (createSource): DaemonSource, a requester of `reel serve` (state, intents, commands,
//     cancel), or OfflineSource when the runtime cannot reach the engine at all. A source with a link diagnosis
//     (DaemonSource) puts it into the panel's offline banner (ui.link).
//   - the host link (startHostLink): the Premiere ops the engine routes here.
// Both are started once and live until the panel is destroyed (unmount). Hiding the panel changes nothing: stopping
// the panel's session would make the daemon cancel every command it started, and Premiere's show / hide events are
// unmeasured (in Photoshop UXP `show` fires only once, so a panel stopped on hide could never come back).
import { asMountRoot, mount } from "../../panel-ui/src/mount.ts";
import type { MountHandle } from "../../panel-ui/src/mount.ts";
import type { BuildInfo } from "../../panel-ui/src/diagnostics.ts";
import type { LinkInfo } from "../../panel-ui/src/render.ts";
import type { Language, PanelDataSource } from "../../panel-ui/src/source.ts";
import type { UxpModule } from "./uxp-types.ts";
import { showCopyText } from "./copy-fallback.ts";
import type { FallbackDoc, FallbackEl } from "./copy-fallback.ts";
import { languageOf } from "./offline-source.ts";
import type { OfflineInfo } from "./offline-source.ts";
import { createUxpHost } from "./uxp-host.ts";
import type { UxpShell } from "./uxp-host.ts";
import type { premierepro as Ppro } from "@adobe/premierepro";

/** The page the shell writes into. The background is never the host's: Addendum B is always #000 (brand/tokens.css
 *  --twn-bg), so the shell reads no host theme and sets no colour variable. */
export interface ShellDoc extends FallbackDoc {}

/** The panel's show / hide / destroy, as UXP's entrypoints.setup reports them. */
export interface PanelLifecycle {
  show(): void;
  hide(): void;
  destroy(): void;
}

export interface ShellEnv {
  document: ShellDoc;
  /** `navigator`, read lazily: without the manifest clipboard permission, touching navigator.clipboard throws in UXP */
  navigator: { clipboard?: { writeText?: (text: string) => Promise<void> } } | undefined;
  /** UXP's `require` (host modules: "premierepro", "uxp") */
  require: (id: string) => unknown;
  /** a NEW data source each call (the shell calls it again after a hide / show) */
  createSource: (info: OfflineInfo) => PanelDataSource;
  /** starts the Premiere host session to the engine; returns its stop (or null when there is no engine link here) */
  startHostLink?: () => { stop(): void } | null;
  /** hands the shell's show / hide / destroy to the host (UXP entrypoints.setup) */
  onLifecycle?: (handlers: PanelLifecycle) => void;
  /** the plugin version and build stamp: shown in the log drawer and copied with the diagnostics */
  build?: BuildInfo;
}

export interface Shell {
  ready: Promise<void>;
  /** the panel is gone: stops the data source and the host link */
  unmount(): void;
  /** the panel became visible: nothing to do (the sessions never stop while the panel exists) */
  show(): void;
  /** the panel was hidden: nothing to do (see the file comment) */
  hide(): void;
}

/** A source that knows why its engine link is down (DaemonSource) and can be stopped. */
interface LinkedSource extends PanelDataSource {
  readonly diagnosis: { code: string; retry_in_s?: number };
  stop(): void;
}

function isLinked(s: PanelDataSource): s is LinkedSource {
  return typeof (s as Partial<LinkedSource>).stop === "function" && "diagnosis" in s;
}

function linkOf(s: LinkedSource): LinkInfo | null {
  const d = s.diagnosis;
  if (!d || d.code === "connected") return null;
  return typeof d.retry_in_s === "number" ? { code: d.code, retry_in_s: d.retry_in_s } : { code: d.code };
}

function tryRequire<T>(env: ShellEnv, id: string): T | undefined {
  try {
    return env.require(id) as T;
  } catch {
    return undefined;
  }
}

function say(doc: ShellDoc, text: string): void {
  try {
    doc.body.textContent = text;
  } catch {
    // nothing else can be done
  }
}

const NOOP_SHELL: Shell = { ready: Promise.resolve(), unmount() {}, show() {}, hide() {} };

export function startShell(env: ShellEnv): Shell {
  const doc = env.document;
  const rootEl: FallbackEl | null = doc.getElementById("root");
  if (!rootEl) {
    say(doc, "WhyNot Cut could not start: the page has no #root element.");
    return NOOP_SHELL;
  }
  try {
    const uxp = tryRequire<UxpModule & { shell?: UxpShell }>(env, "uxp");
    const info: OfflineInfo = { hostVersion: uxp?.host?.version, uiLocale: uxp?.host?.uiLocale };

    // The adapter reports errors in the panel's language; the source decides it, the locale is the first guess.
    let language: Language = languageOf(info.uiLocale);
    const host = createUxpHost({
      getPpro: () => env.require("premierepro") as Ppro,
      getShell: () => uxp?.shell,
      clipboardWriteText: async (text) => {
        const write = env.navigator?.clipboard?.writeText;
        if (typeof write !== "function") throw new Error("navigator.clipboard.writeText is not available");
        await write.call(env.navigator?.clipboard, text);
      },
      showText: (text, title, closeLabel) => showCopyText(doc, text, title, closeLabel),
      language: () => language,
    });

    let hostLink: { stop(): void } | null = null;
    try {
      hostLink = env.startHostLink?.() ?? null;
    } catch {
      hostLink = null; // the panel still shows; the engine sees no Premiere host until the next start
    }

    let current: { source: PanelDataSource; handle: MountHandle; offs: Array<() => void> } | null = null;
    let destroyed = false;

    const mountSource = (): Promise<void> => {
      const source = env.createSource(info);
      const offs: Array<() => void> = [];
      let handle: MountHandle | null = null;
      offs.push(source.subscribe((s) => void (language = s.language)));
      if (isLinked(source)) {
        // subscribed before mount: the link is set before mount repaints for the same change
        offs.push(source.subscribe(() => {
          if (handle) handle.ui.link = linkOf(source);
        }));
      }
      void source.snapshot().then((s) => void (language = s.language), () => {});
      handle = mount(asMountRoot(rootEl), source, host);
      if (isLinked(source)) handle.ui.link = linkOf(source);
      if (env.build) handle.ui.build = { version: String(env.build.version), build: String(env.build.build) };
      current = { source, handle, offs };
      return handle.ready;
    };

    const teardown = () => {
      const c = current;
      if (!c) return;
      current = null;
      for (const off of c.offs) off();
      c.handle.unmount();
      if (isLinked(c.source)) c.source.stop();
    };
    // hide / show: deliberately nothing (I1). The panel's session and its running commands outlive a hidden panel.
    const hide = () => {};
    const show = () => {};
    const unmount = () => {
      if (destroyed) return;
      destroyed = true;
      teardown();
      try {
        hostLink?.stop();
      } catch {
        // already stopped
      }
      hostLink = null;
    };

    const ready = mountSource();
    try {
      env.onLifecycle?.({ show, hide, destroy: unmount });
    } catch {
      // without lifecycle events the panel simply stays mounted
    }
    return { ready, unmount, show, hide };
  } catch (e) {
    say(doc, `WhyNot Cut could not start: ${e instanceof Error ? e.message : String(e)}`);
    return NOOP_SHELL;
  }
}
