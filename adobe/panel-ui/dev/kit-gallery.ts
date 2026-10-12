// The dev harness "Kit" scenario: every component of src/kit in one panel-shaped page, for one language. The copy comes
// from the string table; the sample data (timecodes, file names, log lines) is data, as the engine would send it.
// Each block is titled with the component's function name (a technical identifier, the same in both languages).
import { stringsFor } from "../src/i18n.ts";
import {
  button,
  buttonRow,
  card,
  chip,
  chips,
  dialog,
  emptyState,
  footer,
  frameGrid,
  header,
  join,
  kitRoot,
  logDrawer,
  paragraph,
  progress,
  section,
  stepStrip,
  tabs,
  toast,
  waveformFrame,
} from "../src/kit/index.ts";
import type { Html } from "../src/kit/index.ts";
import { sampleState } from "../src/mock.ts";
import type { Language } from "../src/source.ts";

export function kitGallery(lang: Language): Html {
  const t = stringsFor(lang);
  const rtl = lang === "ar";
  const frames = sampleState(lang, "qc").qc.slice(0, 4);
  // the 4:5 frame of the mock set, so both aspects show
  const four5 = sampleState(lang, "qc").qc.find((q) => q.w === 1080 && q.h === 1350);
  if (four5 && !frames.includes(four5)) frames[3] = four5;
  const block = (name: string, body: Html) => section({ title: name, body });

  return kitRoot({
    lang,
    body: join([
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
          toast({ t, kind: "error", text: t["offline.no_engine"], how: `${t["offline.hint"]} \`reel serve --ensure\``, fix: { label: t["action.retry"], action: "retry" } }),
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
        emptyState({ title: t["empty.noclient.title"], text: t["empty.noclient.text"], action: { label: t["empty.noclient.action"], action: "choose-client" }, primary: false }),
      ),
      block(
        "logDrawer()",
        join([
          logDrawer({ t, open: false, rtl, lines: [], id: "kit-log-closed" }),
          logDrawer({
            t,
            open: true,
            rtl,
            build: { version: "3.0.0", build: "c589a67 2026-10-12T22:37Z" },
            lines: [
              { ts: "14:12:03", level: "info", text: "reel ppro-build --video-id C0239" },
              { ts: "14:12:09", level: "warn", text: "font fallback: Syne 600 -> Syne Bold" },
              { ts: "14:12:11", level: "error", text: "EDITOR_CHANGES_PRESENT C0239_v2.prproj" },
            ],
          }),
        ]),
      ),
      block("frameGrid()", frameGrid({ t, frames })),
      block("waveformFrame()", waveformFrame({ t, start: "00:00:00:00", end: "00:00:42:10", slot: "hush" })),
      footer(t),
    ]),
  });
}
