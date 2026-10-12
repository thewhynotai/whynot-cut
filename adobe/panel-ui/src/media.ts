// Media helpers shared by the panel (render.ts) and the component kit (kit/frames.ts): ONE local-thumbnail check and
// ONE frame-aspect function, so the two can never drift apart.

/** A thumbnail URL the panel may draw: data:image, file:/// with an empty host, plugin: and local paths only, so a
 *  thumbnail never makes the panel fetch from the network. Refused: any other scheme (http(s):, javascript:, a drive
 *  letter "C:" reads as a scheme), file: with a host or a UNC share (file://host/..., file:////host/...), and paths
 *  that browsers resolve to a remote host ("//host", "\\host", "/\host", "\/host"). The first character may not be a
 *  space or a control character (URL parsers strip those, so " //host" would become "//host") and no tab, CR or LF
 *  may appear anywhere (URL parsers delete them, so "/\t/host" would become "//host"). Outside data:image (a data URL
 *  names no host, and percent-encoded SVG holds "%2F" in every closing tag), a percent-encoded separator (%2f / %5c, any
 *  case) or a look-alike slash (U+2044, U+2215, U+29F5, U+FE68, U+FF0F, U+FF3C) anywhere refuses the URL too: a decoder
 *  or a Unicode normalizer could turn either into "/" or "\" ("file:///%5Chost", "∕∕host"). */
export const SAFE_IMG =
  /^(?:data:image\/|(?![^]*(?:%2f|%5c|[⁄∕⧵﹨／＼]))(?:file:\/\/\/(?![\\/])|plugin:|(?![a-z][a-z0-9+.-]*:|\\|\/[\\/])))[^\u0000- \u007f][^\t\n\r\u0000-\u001f\u007f]*$/i;

export const isSafeImg = (src: unknown): src is string => typeof src === "string" && SAFE_IMG.test(src);

/** The frame box's height as a percentage of its width (padding-top). 9:16 when w/h are absent or invalid; clamped to
 *  40..300 so a bad size never makes a huge or flat tile. */
export function aspectPct(w: unknown, h: unknown): number {
  const ok = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n) && n > 0;
  const pct = ok(w) && ok(h) ? (h / w) * 100 : (1920 / 1080) * 100;
  return Math.round(Math.max(40, Math.min(300, pct)) * 100) / 100;
}
