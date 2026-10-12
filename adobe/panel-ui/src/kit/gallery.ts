// The kit gallery: every component of src/kit in one panel-shaped page, for one language. It is the style guide's
// content (the dev harness "Kit" scenario, the spike's style-guide view) AND the corpus the kit tests check (B4 guards,
// CSS coverage, contrast and stacking guards), so it lives with the kit where the hard-coded-string scanner reads it.
// It is NOT re-exported from index.ts: the runtime kit never bundles it (it reads the mock data).
// The copy comes from the string table; the sample data (timecodes, file names, log lines) is data, as the engine
// would send it (the mock's own lines plus a raw error code, which is what the log drawer is for). Each section is
// titled with the component's function name (a technical identifier, the same in both languages) and holds at most
// one primary button (a screen's worth, Addendum B4).
import { stringsFor } from "../i18n.ts";
import { sampleState } from "../mock.ts";
import type { Language, LogLine } from "../source.ts";
import { button, buttonRow } from "./button.ts";
import { card, paragraph, section } from "./card.ts";
import { chip, chips } from "./chip.ts";
import { dialog } from "./dialog.ts";
import { emptyState } from "./empty.ts";
import { frameGrid } from "./frames.ts";
import { header } from "./header.ts";
import { join } from "./html.ts";
import type { Html } from "./html.ts";
import { logDrawer } from "./log.ts";
import { progress } from "./progress.ts";
import { footer, kitRoot } from "./root.ts";
import { stepStrip } from "./steps.ts";
import { tabs } from "./tabs.ts";
import { toast } from "./toast.ts";
import { waveformFrame } from "./waveform.ts";

/** The command the offline hint names (the same in both languages). */
const ENSURE = "reel serve --ensure";

export interface GallerySection {
  /** the component function's name, e.g. "card()" */
  name: string;
  html: Html;
}

/** The gallery's sections in order: the chrome (header + tabs), one per component, then the footer. */
export function kitGallerySections(lang: Language): readonly GallerySection[] {
  const t = stringsFor(lang);
  const rtl = lang === "ar";
  const qc = sampleState(lang, "qc");
  const frames = qc.qc.slice(0, 4);
  // the 4:5 frame of the mock set, so both aspects show
  const four5 = qc.qc.find((q) => q.w === 1080 && q.h === 1350);
  if (four5 && !frames.includes(four5)) frames[3] = four5;
  const last = qc.log.at(-1)?.ts ?? "";
  const log: LogLine[] = [...qc.log.slice(0, 3), { ts: last, level: "error", text: "EDITOR_CHANGES_PRESENT" }];
  const block = (name: string, body: Html): GallerySection => ({ name, html: section({ title: name, body }) });

  return [
    {
      name: "header()",
      html: join([
        header({ t, lang, needsYou: 3 }),
        tabs({
          t,
          active: "edit",
          items: [
            { id: "home", label: t["tab.home"] },
            { id: "edit", label: t["tab.edit"], count: 2 },
            { id: "tools", label: t["tab.tools"] },
          ],
        }),
      ]),
    },
    block(
      "card()",
      card({
        eyebrow: t["section.approval"],
        title: t["approval.summary"],
        body: join([
          paragraph(t["rebuild.warning"]),
          chips([chip({ label: t["approval.flagged.medical"], tone: "warn" }), chip({ label: "00:00:12:04", ltr: true })]),
          buttonRow([
            button({ label: t["approval.approve"], action: "approve", variant: "primary", glow: true }),
            button({ label: t["approval.preview"], action: "preview" }),
          ]),
        ]),
      }),
    ),
    block(
      "button()",
      join([
        button({ label: t["approval.approve"], action: "approve", variant: "primary", glow: true, block: true }),
        buttonRow([
          button({ label: t["approval.changes"], action: "request-changes" }),
          button({ label: t["actions.rebuild"], action: "rebuild", variant: "danger" }),
          button({ label: t["actions.export"], action: "export-frames", disabled: true }),
          button({ label: t["actions.open"], action: "open-project", icon: "chevron-end", rtl }),
        ]),
      ]),
    ),
    block(
      "chip()",
      chips([
        chip({ label: t["qc.pass"], tone: "ok" }),
        chip({ label: t["qc.media_pending"], tone: "warn" }),
        chip({ label: t["qc.fail"], tone: "error" }),
        chip({ label: t["qc.pending"], tone: "info" }),
        chip({ label: t["approval.flagged.religious"], tone: "accent" }),
        chip({ label: "C0239.mp4", ltr: true }),
      ]),
    ),
    block(
      "stepStrip()",
      join([
        stepStrip({
          t,
          rtl,
          steps: [
            { id: "transcript", state: "done" },
            { id: "plan", state: "done" },
            { id: "approve", state: "done" },
            { id: "build", state: "running" },
          ],
        }),
        stepStrip({
          t,
          rtl,
          steps: [
            { id: "transcript", state: "done" },
            { id: "plan", state: "done" },
            { id: "approve", state: "waiting" },
            { id: "build", state: "failed" },
          ],
        }),
      ]),
    ),
    block(
      "progress()",
      join([
        progress({ t, status: t["progress.building"], n: 23, of: 47, elapsedS: 65, cancel: { action: "cancel", data: { id: "req-1" } } }),
        progress({ t, status: t["status.connecting"] }),
      ]),
    ),
    block(
      "toast()",
      join([
        toast({ t, kind: "error", text: t["offline.no_engine"], how: `${t["offline.hint"]} \`${ENSURE}\``, fix: { label: t["action.retry"], action: "retry" } }),
        toast({ t, kind: "warn", text: t["offline.bad_engine_json"] }),
        toast({ t, kind: "ok", text: t["notice.approved"] }),
        toast({ t, kind: "info", text: t["qc.hint"], dismiss: false }),
      ]),
    ),
    block(
      "dialog()",
      dialog({
        t,
        id: "kit-rebuild",
        title: t["rebuild.title"],
        changes: [t["rebuild.warning"]],
        backupName: "C0239_prev_2026-10-13-1412.prproj",
        confirm: { label: t["rebuild.confirm"], action: "rebuild-confirm" },
        cancel: { label: t["rebuild.cancel"], action: "rebuild-cancel" },
      }),
    ),
    block(
      "emptyState()",
      emptyState({ title: t["empty.noclient.title"], text: t["empty.noclient.text"], action: { label: t["empty.noclient.action"], action: "choose-client" } }),
    ),
    block(
      "logDrawer()",
      join([
        logDrawer({ t, open: false, rtl, lines: [], id: "kit-log-closed" }),
        logDrawer({ t, open: true, rtl, build: { version: "3.0.0", build: "c589a67 2026-10-12T22:37Z" }, lines: log }),
      ]),
    ),
    block("frameGrid()", frameGrid({ t, frames })),
    block("waveformFrame()", waveformFrame({ t, start: "00:00:00:00", end: "00:00:42:10", slot: "hush" })),
    { name: "footer()", html: footer(t) },
  ];
}

/** The whole gallery page for one language. */
export function kitGallery(lang: Language): Html {
  return kitRoot({ lang, body: join(kitGallerySections(lang).map((s) => s.html)) });
}
