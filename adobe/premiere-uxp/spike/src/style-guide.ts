// Spike 0.1.6: the "Style guide" view. It renders every panel-kit component (adobe/panel-ui/src/kit/gallery.ts, the
// same page as the dev harness's ?scenario=kit) inside Premiere, in English or Arabic, in a 280 / 340 / 480 px column, so
// the live UXP rendering can be screenshotted and compared with Chromium (docs/adobe/evidence/ui-kit/). The bundle
// carries fonts.css + fonts/, brand/tokens.css and kit.css (scripts/build.mjs); the string table is bundled into index.js.
// A run-request with mode "style_guide" opens it (and its lang / width) and it stays open until Back is pressed.
import { kitGallery } from "../../../panel-ui/src/kit/gallery.ts";
import { DEFAULT_VIEW, GUIDE_WIDTHS, type GuideLang, type GuideView, type GuideWidth } from "./autorun.ts";
import { SPIKE_VERSION } from "./version.ts";

export interface GuideDom {
  main: HTMLElement;
  guide: HTMLElement;
  frame: HTMLElement;
  host: HTMLElement;
  caption: HTMLElement;
  buttons: { lang: Record<GuideLang, HTMLElement>; width: Record<GuideWidth, HTMLElement>; back: HTMLElement };
}

/** The caption above the column: what a screenshot shows. */
export const guideCaption = (v: GuideView) => `Style guide - ${v.lang === "ar" ? "AR" : "EN"} - ${v.width} px - spike ${SPIKE_VERSION}`;

/** The gallery markup for one view (kit-root carries dir/lang; the kit's own scroll region scrolls it). */
export const guideHtml = (v: GuideView): string => kitGallery(v.lang);

export interface StyleGuide {
  show(view?: Partial<GuideView>): GuideView;
  hide(): void;
  view(): GuideView;
  isOpen(): boolean;
}

export function createStyleGuide(dom: GuideDom, onChange?: (v: GuideView, open: boolean) => void): StyleGuide {
  let current: GuideView = { ...DEFAULT_VIEW };
  let open = false;

  const mark = (el: HTMLElement, on: boolean) => {
    el.className = on ? "seg on" : "seg";
  };

  function render(): void {
    dom.frame.style.width = `${current.width}px`;
    dom.host.innerHTML = guideHtml(current);
    dom.caption.textContent = guideCaption(current);
    for (const l of ["en", "ar"] as const) mark(dom.buttons.lang[l], current.lang === l);
    for (const w of GUIDE_WIDTHS) mark(dom.buttons.width[w], current.width === w);
  }

  const api: StyleGuide = {
    show(view = {}) {
      current = { lang: view.lang ?? current.lang, width: view.width ?? current.width };
      open = true;
      dom.main.style.display = "none";
      dom.guide.style.display = "flex";
      render();
      onChange?.(current, open);
      return current;
    },
    hide() {
      open = false;
      dom.guide.style.display = "none";
      dom.main.style.display = "flex";
      onChange?.(current, open);
    },
    view: () => current,
    isOpen: () => open,
  };

  for (const l of ["en", "ar"] as const) dom.buttons.lang[l].addEventListener("click", () => void api.show({ lang: l }));
  for (const w of GUIDE_WIDTHS) dom.buttons.width[w].addEventListener("click", () => void api.show({ width: w }));
  dom.buttons.back.addEventListener("click", () => api.hide());
  return api;
}
