/* The panel components the installer reuses (the mockups' mockup.js M.ico, M.status, M.btn, M.kbd, M.chip, M.card,
   M.progress, M.supportParts, M.soonLine), as DOM builders. Labels and texts are Nodes (from T()) or plain strings
   (shown as text). Behaviour and classes are the mockup's, so the screens and the visual-parity check (ET1-15) line up. */
import { C } from "./ctx.js";
import ICONS from "./icons.gen.js";
import { h, svg, T } from "./text.js";

/* an icon: an inline SVG path coloured by an .ink-* class; a missing icon is recorded (missing=icon:<name>@<size>) */
export function ico(name, size, ink, extra) {
  size = size || 16;
  const set = ICONS[name], d = set && set[String(size)];
  if (!d) C.missing.push("icon:" + name + "@" + size);
  const el = svg("svg", { class: ["m-ico", "m-ico-" + size, ink || "ink-text", extra || ""].join(" ").trim(),
    viewBox: "0 0 24 24", "aria-hidden": "true" });
  el.append(svg("path", { "fill-rule": "evenodd", d: d || "" }));
  return el;
}

/* ONE status model (R2 designer P1-3): one kind, one icon, one colour. waiting = waiting FOR THE PERSON (pink dot). */
const STATUS = {
  ok: ["circle-check", "ink-ok"], warn: ["triangle-alert", "ink-warn"], error: ["circle-x", "ink-error"],
  info: ["info", "ink-info"], pending: ["circle-dashed", "ink-muted"], busy: ["loader-circle", "ink-info"],
  waiting: ["circle-dot", "ink-accent"], paused: ["circle-pause", "ink-warn"]
};
export function status(kind, size) {
  const s = STATUS[kind] || STATUS.info;
  return ico(s[0], size || 16, s[1], kind === "busy" ? "m-spin" : "");
}

export function kbd(k, cls) { return h("span", { class: ("m-kbd " + (cls || "")).trim(), "aria-hidden": "true" }, k); }

/* a button: <div role="button"> with a 2 px rest border. A danger or destructive action never carries a keycap
   (R2 designer P0-3); a disabled one leaves the tab order (its keycap, if asked for, is drawn greyed). o = {kind, icon, disabled, focus, block,
   start, flush, destructive, kbd, cls} */
export function btn(label, o) {
  o = o || {};
  const refuse = o.kind === "danger" || !!o.destructive;
  const key = refuse ? null : o.kbd;
  const kind = o.disabled ? "m-btn-disabled" : "m-btn-" + (o.kind || "secondary");
  const mainOff = o.disabled && (o.kind === "primary" || !!o.kbd) ? "m-main-off" : "";
  const cls = ["m-btn", kind, mainOff, o.destructive ? "m-btn-destructive" : "", o.block ? "m-btn-block" : "",
    o.start ? "m-btn-start" : "", o.flush ? "m-btn-flush" : "", o.focus ? "m-btn-focus" : "", o.cls || ""]
    .filter(Boolean).join(" ");
  const el = h("div", { class: cls, role: "button", tabindex: o.disabled ? "-1" : "0", "aria-disabled": o.disabled ? "true" : null });
  if (o.icon) el.append(o.icon === "busy" ? status("busy") : ico(o.icon, 16, "ink-text"));
  el.append(h("span", { class: "m-block" }, label));
  if (key) el.append(kbd(key));
  return el;
}

export function chip(tone, label, icon) {
  const ink = { ok: "ink-ok", warn: "ink-warn", error: "ink-error", info: "ink-info", neutral: "ink-muted" }[tone] || "ink-muted";
  return h("span", { class: "m-chip m-chip-" + tone }, icon ? ico(icon, 12, ink) : null, h("span", { class: "m-block" }, label));
}

export function card(inner, cls) { return h("section", { class: ("m-card " + (cls || "")).trim() }, inner); }

/* a progress bar; the width is set through the CSSOM (style-src 'self' allows it; a style="" attribute would not) */
export function progress(pct, o) {
  const fill = h("span", { class: "m-fill" + (o && o.paused ? " m-fill-paused" : "") });
  fill.style.width = Math.max(0, Math.min(100, Number(pct) || 0)) + "%";
  return h("div", { class: "m-track" }, fill);
}

/* H24 / D-05: the ONE "coming soon" line, always under the button row: a 12 px info icon and meta text */
export function soonLine(key, cls) {
  return h("div", { class: "m-row-top m-soonline " + (cls || "mt-2") },
    h("div", { class: "m-last-ico" }, ico("info", 12, "ink-muted")),
    h("div", { class: "t-meta tx-muted ms-1 m-grow" }, T(key)));
}

/* D-05 support (WhatsApp, live): "Copy details and open WhatsApp" + the reply promise under it; with support off:
   "Copy details for support" (copies only) + the ONE "coming soon" line. Returns {btn, under, live}. */
export function supportParts(o) {
  o = o || {};
  const live = C.cfg.supportLive;
  const b = btn(T(live ? "support.copy_open" : "support.copy"), { kind: o.kind || "ghost", icon: live ? "message-square" : "copy",
    cls: "m-btn-wrap" + (o.cls ? " " + o.cls : ""), flush: !!o.flush });
  const under = live ? h("div", { class: "t-meta tx-muted mt-2 m-support-promise" }, T("support.promise")) : soonLine("support.soon");
  return { btn: b, under, live };
}
