// The visible "copy this" box: the fallback when the clipboard write is refused (navigator.clipboard throws without the
// manifest permission, or the user denies it) or a folder cannot be opened. The text is shown in a read-only,
// pre-selected box the editor can copy from with Ctrl/Cmd+C. It lives outside the panel root, so a re-render never wipes it.

export interface FallbackEl {
  className: string;
  textContent: string | null;
  value?: string;
  readOnly?: boolean;
  appendChild(child: FallbackEl): unknown;
  setAttribute(name: string, value: string): void;
  addEventListener(type: string, fn: () => void): void;
  select?(): void;
  focus?(): void;
  remove?(): void;
  scrollIntoView?(): void;
}

export interface FallbackDoc {
  body: FallbackEl;
  createElement(tag: string): FallbackEl;
  getElementById(id: string): FallbackEl | null;
  execCommand?(command: string): boolean;
}

const BOX_ID = "wnc-copy";

export function showCopyText(doc: FallbackDoc, text: string, title: string, closeLabel: string): void {
  doc.getElementById(BOX_ID)?.remove?.();
  const box = doc.createElement("div");
  box.setAttribute("id", BOX_ID);
  box.className = "wnc-copy";

  const heading = doc.createElement("p");
  heading.className = "wnc-copy-title";
  heading.textContent = title;
  box.appendChild(heading);

  const area = doc.createElement("textarea");
  area.className = "wnc-copy-text";
  area.setAttribute("rows", "8");
  area.setAttribute("spellcheck", "false");
  area.readOnly = true;
  area.value = text;
  box.appendChild(area);

  const close = doc.createElement("button");
  close.className = "wnc-copy-close";
  close.textContent = closeLabel;
  close.addEventListener("click", () => box.remove?.());
  box.appendChild(close);

  doc.body.appendChild(box);
  try {
    area.focus?.();
    area.select?.();
    // Selected text copies with Ctrl/Cmd+C; execCommand is a bonus where the runtime allows it.
    doc.execCommand?.("copy");
  } catch {
    // selecting is enough: the editor copies by hand
  }
  try {
    box.scrollIntoView?.();
  } catch {
    // not available
  }
}
