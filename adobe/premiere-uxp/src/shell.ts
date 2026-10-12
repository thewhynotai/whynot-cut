// The plugin shell: wires the shared panel (panel-ui mount) to Premiere. main.ts calls startShell once with the real
// page; the tests call it with fakes. This file never imports MockSource: main.ts picks the data source at build time
// (the WNC_MOCK build flag), so a normal build cannot carry mock data.
import { asMountRoot, mount } from "../../panel-ui/src/mount.ts";
import type { MountHandle } from "../../panel-ui/src/mount.ts";
import type { Language, PanelDataSource } from "../../panel-ui/src/source.ts";
import type { UxpModule } from "./uxp-types.ts";
import { showCopyText } from "./copy-fallback.ts";
import type { FallbackDoc, FallbackEl } from "./copy-fallback.ts";
import { languageOf } from "./offline-source.ts";
import type { OfflineInfo } from "./offline-source.ts";
import { applyHostTheme } from "./theme.ts";
import type { ThemeDoc } from "./theme.ts";
import { createUxpHost } from "./uxp-host.ts";
import type { UxpShell } from "./uxp-host.ts";
import type { premierepro as Ppro } from "@adobe/premierepro";

export interface ShellDoc extends FallbackDoc, ThemeDoc {}

export interface ShellEnv {
  document: ShellDoc;
  /** `navigator`, read lazily: with no clipboard permission, touching navigator.clipboard throws in UXP */
  navigator: { clipboard?: { writeText?: (text: string) => Promise<void> } } | undefined;
  /** UXP's `require` (host modules: "premierepro", "uxp") */
  require: (id: string) => unknown;
  createSource: (info: OfflineInfo) => PanelDataSource;
}

export interface Shell {
  ready: Promise<void>;
  unmount(): void;
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

export function startShell(env: ShellEnv): Shell {
  const doc = env.document;
  const rootEl: FallbackEl | null = doc.getElementById("root");
  if (!rootEl) {
    say(doc, "WhyNot Cut could not start: the page has no #root element.");
    return { ready: Promise.resolve(), unmount() {} };
  }
  try {
    const uxp = tryRequire<UxpModule & { shell?: UxpShell }>(env, "uxp");
    applyHostTheme(doc, uxp?.host);
    const info: OfflineInfo = { hostVersion: uxp?.host?.version, uiLocale: uxp?.host?.uiLocale };
    const source = env.createSource(info);

    // The adapter reports errors in the panel's language; the source decides it, the locale is the first guess.
    let language: Language = languageOf(info.uiLocale);
    source.subscribe((s) => void (language = s.language));
    void source.snapshot().then((s) => void (language = s.language), () => {});

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

    const handle: MountHandle = mount(asMountRoot(rootEl), source, host);
    return { ready: handle.ready, unmount: () => handle.unmount() };
  } catch (e) {
    say(doc, `WhyNot Cut could not start: ${e instanceof Error ? e.message : String(e)}`);
    return { ready: Promise.resolve(), unmount() {} };
  }
}
