// Spike 0.1.7: the real DOM / runtime behind the CSS lab (css-lab.ts measures through LabDom / LabEnv; the tests use
// fakes). Everything here is best effort and never throws: what is missing in this UXP build is recorded, not fatal.
import { readBytes } from "./fsutil.ts";
import type { LabDom, LabEnv, Rect, StepResult, StyleLike } from "./css-lab.ts";
import type { UxpFs, UxpModule } from "../../src/uxp-types.ts";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const FONT_LOAD_TIMEOUT_MS = 5000;

/** The lab view's host element: queries, computed styles, boxes. */
export function realLabDom(host: HTMLElement): LabDom {
  return {
    query: (selector) => host.querySelector(selector),
    style: (el) => getComputedStyle(el as Element) as unknown as StyleLike,
    rect(el): Rect {
      const e = el as Element & { offsetLeft?: number; offsetTop?: number; offsetWidth?: number; offsetHeight?: number };
      try {
        const r = e.getBoundingClientRect() as DOMRect & { left?: number; top?: number };
        if (r && (r.width || r.height)) return { x: r.left ?? r.x ?? 0, y: r.top ?? r.y ?? 0, width: r.width, height: r.height };
      } catch {
        // fall through to offset*
      }
      return { x: e.offsetLeft ?? 0, y: e.offsetTop ?? 0, width: e.offsetWidth ?? 0, height: e.offsetHeight ?? 0 };
    },
    prop(el, name) {
      try {
        return (el as Record<string, unknown>)[name];
      } catch {
        return undefined;
      }
    },
    hostWidth() {
      try {
        const w = host.getBoundingClientRect().width || host.offsetWidth;
        return w > 0 ? Math.round(w * 100) / 100 : null;
      } catch {
        return null;
      }
    },
    wait: (ms) => new Promise((r) => setTimeout(r, ms)),
  };
}

interface FontFaceLike {
  load(): Promise<unknown>;
  status?: string;
}
type FontFaceCtor = new (family: string, source: string | ArrayBuffer, descriptors?: Record<string, string>) => FontFaceLike;
interface DocFonts {
  add?: (f: unknown) => unknown;
  check?: (font: string) => boolean;
  size?: number;
  status?: string;
}

/** Runtime font paths (a <style>, FontFace, the plugin folder's bytes) and the environment facts. */
export function realLabEnv(doc: Document, fs: UxpFs, uxp: UxpModule): LabEnv {
  const g = globalThis as { FontFace?: FontFaceCtor; customElements?: { get?: (n: string) => unknown }; btoa?: unknown };
  const fonts = () => (doc as unknown as { fonts?: DocFonts }).fonts;
  return {
    injectStyle(css): StepResult {
      try {
        const el = doc.createElement("style");
        el.textContent = css;
        (doc.head ?? doc.body).appendChild(el);
        const sheets = (doc as unknown as { styleSheets?: { length?: number } }).styleSheets;
        return { ok: true, in_dom: el.parentNode !== null, sheet_present: Boolean((el as unknown as { sheet?: unknown }).sheet), style_sheets: sheets?.length ?? null };
      } catch (e) {
        return { ok: false, error: errText(e) };
      }
    },
    async loadFontFace(family, source, descriptors): Promise<StepResult> {
      const FF = g.FontFace;
      if (typeof FF !== "function") return { ok: false, error: `FontFace is ${typeof FF}` };
      let face: FontFaceLike;
      try {
        face = new FF(family, source, descriptors);
      } catch (e) {
        return { ok: false, step: "new FontFace", error: errText(e) };
      }
      try {
        let timer: ReturnType<typeof setTimeout> | undefined;
        await Promise.race([
          face.load(),
          new Promise((_r, reject) => {
            timer = setTimeout(() => reject(new Error(`load() did not settle in ${FONT_LOAD_TIMEOUT_MS} ms`)), FONT_LOAD_TIMEOUT_MS);
          }),
        ]).finally(() => clearTimeout(timer));
      } catch (e) {
        return { ok: false, step: "load()", status: face.status ?? null, error: errText(e) };
      }
      const f = fonts();
      if (typeof f?.add !== "function") return { ok: false, step: "document.fonts.add", status: face.status ?? null, error: "document.fonts.add is not available" };
      try {
        f.add(face);
        return { ok: true, status: face.status ?? null, added_to_document_fonts: true };
      } catch (e) {
        return { ok: false, step: "document.fonts.add", status: face.status ?? null, error: errText(e) };
      }
    },
    async readPluginBytes(rel) {
      const errors: string[] = [];
      try {
        return { bytes: await readBytes(fs, `plugin:/${rel}`), via: "fs.readFile plugin:/" };
      } catch (e) {
        errors.push(`fs plugin:/: ${errText(e)}`);
      }
      try {
        const storage = uxp.storage as { localFileSystem?: { getPluginFolder?: () => Promise<unknown> }; formats?: { binary?: unknown } } | undefined;
        const folder = (await storage?.localFileSystem?.getPluginFolder?.()) as { getEntry?: (p: string) => Promise<unknown> } | undefined;
        if (typeof folder?.getEntry !== "function") throw new Error("getPluginFolder().getEntry is not available");
        const entry = (await folder.getEntry(rel)) as { read?: (o: unknown) => Promise<unknown> };
        if (typeof entry?.read !== "function") throw new Error("the entry has no read()");
        const data = await entry.read({ format: storage?.formats?.binary });
        if (data instanceof ArrayBuffer) return { bytes: data, via: "storage getPluginFolder().getEntry().read(binary)" };
        errors.push(`storage: read returned ${typeof data}`);
      } catch (e) {
        errors.push(`storage: ${errText(e)}`);
      }
      return { error: errors.join("; ") };
    },
    facts() {
      const f = fonts();
      const ce = g.customElements;
      let spDefined: boolean | string | null = null;
      try {
        spDefined = typeof ce?.get === "function" ? ce.get("sp-button") !== undefined : null;
      } catch (e) {
        spDefined = `threw: ${errText(e)}`;
      }
      const sp = doc.getElementById("lab-btn-F-primary") as (HTMLElement & { shadowRoot?: unknown }) | null;
      return {
        typeof_FontFace: typeof g.FontFace,
        document_fonts: f !== undefined && f !== null,
        document_fonts_add: typeof f?.add,
        document_fonts_check: typeof f?.check,
        document_fonts_size: typeof f?.size === "number" ? f.size : null,
        document_fonts_status: typeof f?.status === "string" ? f.status : null,
        typeof_btoa: typeof g.btoa,
        typeof_customElements: typeof ce,
        sp_button_defined: spDefined,
        sp_button_in_dom: sp !== null,
        sp_button_constructor: sp ? (sp.constructor?.name ?? null) : null,
        sp_button_shadow_root: sp ? Boolean(sp.shadowRoot) : null,
        uxp_versions: uxp.versions ?? null,
      };
    },
  };
}
