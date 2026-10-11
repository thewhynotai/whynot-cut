// Host theme: Premiere's panel background -> the --twn-bg CSS variable. The live spike (Premiere 26.5.2, UXP 9.3.0)
// found getBackgroundColor() is a function but returned {}, so every value is validated and the stylesheet's brand
// dark stays when the host gives nothing usable. A light host colour is also ignored: the panel's text is white.

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

const channel = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 255 ? Math.round(v) : null);

export function parseColor(value: unknown): Rgb | null {
  if (typeof value === "string") {
    const s = value.trim();
    const hex = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(s);
    if (hex) {
      const h = hex[1]!.length === 3 ? hex[1]!.replace(/./g, (c) => c + c) : hex[1]!;
      return { r: parseInt(h.slice(0, 2), 16), g: parseInt(h.slice(2, 4), 16), b: parseInt(h.slice(4, 6), 16) };
    }
    const fn = /^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*[\d.]+\s*)?\)$/i.exec(s);
    if (fn) return parseColor({ r: Number(fn[1]), g: Number(fn[2]), b: Number(fn[3]) });
    return null;
  }
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const o = value as Record<string, unknown>;
    const r = channel(o["r"] ?? o["red"]);
    const g = channel(o["g"] ?? o["green"]);
    const b = channel(o["b"] ?? o["blue"]);
    return r !== null && g !== null && b !== null ? { r, g, b } : null;
  }
  return null;
}

function luminance({ r, g, b }: Rgb): number {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** "#rrggbb" for --twn-bg, or null to keep the stylesheet default (nothing usable, or too light for white text). */
export function backgroundVar(value: unknown): string | null {
  const c = parseColor(value);
  if (!c || luminance(c) >= 0.2) return null;
  const hex = (n: number) => n.toString(16).padStart(2, "0");
  return `#${hex(c.r)}${hex(c.g)}${hex(c.b)}`;
}

export interface ThemeDoc {
  documentElement: { style: { setProperty(name: string, value: string): void } };
}

/** Applies the host background to the page. Never throws. Returns what it set, or null. */
export function applyHostTheme(doc: ThemeDoc, host: { getBackgroundColor?: () => unknown } | undefined): string | null {
  try {
    const css = backgroundVar(host?.getBackgroundColor?.());
    if (!css) return null;
    doc.documentElement.style.setProperty("--twn-bg", css);
    return css;
  } catch {
    return null;
  }
}
