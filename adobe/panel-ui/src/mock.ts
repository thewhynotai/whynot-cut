// MockSource: a believable engine for the dev harness and the tests. Content is the fictional PODCAST-TEST
// client (EN) and an Arabic client-name / path variant. No real client appears here.
import { PROTOCOL } from "./contract.ts";
import type { ActionName, BuildProjectReadback } from "./contract.ts";
import { STEP_IDS } from "./source.ts";
import type {
  Language, LogLine, PanelDataSource, PanelState, PipelineStep, QcFrame, Result, StepId, StepStatus,
} from "./source.ts";

export type Scenario = "showcase" | "approval" | "building" | "qc" | "idle";
export const SCENARIOS: readonly Scenario[] = ["showcase", "approval", "building", "qc", "idle"];

const BUILD_TOTAL = 47;

interface Flavor {
  client: string;
  item: string;
  editor: string;
  folder: string;
  summary: string;
  flagged: [string, string, string, string];
  qc: [string, string][];
  log: [string, string][];
}

const EN_FLAVOR: Flavor = {
  client: "PODCAST-TEST",
  item: "EP01_R03",
  editor: "Yara",
  folder: "E:\\Clients\\PODCAST-TEST\\output\\episodes\\EP01\\EP01_R03",
  summary:
    "58 s vertical reel from Episode 1, 31:10 to 32:08. Hook: the first coffee myth. 14 statement bars, 6 checklist cards, captions in English, 2 punch-ins, music bed at -24 LUFS.",
  flagged: [
    "Caffeine after 2 pm always ruins sleep.",
    "00:00:21:10",
    "The speaker quotes a saying about patience.",
    "00:00:44:03",
  ],
  qc: [
    ["Statement bar: coffee myth", "pass"],
    ["Caption line 3", "pass"],
    ["Checklist card 1", "pass"],
    ["Checklist card 2", "fail"],
    ["Caption line 9", "pending"],
    ["B-roll: espresso pour", "media_pending"],
    ["Statement bar: sleep", "pass"],
    ["Outro card", "media_pending"],
  ],
  log: [
    ["info", "reel plan --root E:\\Clients\\PODCAST-TEST --video-id EP01_R03"],
    ["info", "transcript: 214 words, 0 low-confidence"],
    ["warn", "2 statements flagged for review"],
    ["info", "ppro-build: importing XML"],
  ],
};

const AR_FLAVOR: Flavor = {
  client: "عيادة النور",
  item: "EP02_R05",
  editor: "ليلى",
  folder: "E:\\Clients\\عيادة النور\\output\\episodes\\EP02\\EP02_R05",
  summary:
    "ريل عمودي مدته 58 ثانية من الحلقة الثانية. الافتتاحية: خرافة القهوة الأولى. 14 شريط عبارات و6 بطاقات قوائم وترجمة عربية ولقطتا تقريب وموسيقى خلفية.",
  flagged: [
    "الكافيين بعد الثانية ظهرًا يفسد النوم دائمًا.",
    "00:00:21:10",
    "يذكر المتحدث قولًا مأثورًا عن الصبر.",
    "00:00:44:03",
  ],
  qc: [
    ["شريط عبارة: خرافة القهوة", "pass"],
    ["سطر الترجمة 3", "pass"],
    ["بطاقة القائمة 1", "pass"],
    ["بطاقة القائمة 2", "fail"],
    ["سطر الترجمة 9", "pending"],
    ["لقطة إضافية: صبّ القهوة", "media_pending"],
    ["شريط عبارة: النوم", "pass"],
    ["بطاقة الختام", "media_pending"],
  ],
  log: [
    ["info", "reel plan --root E:\\Clients\\عيادة النور --video-id EP02_R05"],
    ["info", "transcript: 231 words, 1 low-confidence"],
    ["warn", "2 statements flagged for review"],
    ["info", "ppro-build: importing XML"],
  ],
};

const STEP_ORDER = STEP_IDS as readonly StepId[];

function pipeline(states: Partial<Record<StepId, StepStatus>>, extra: Partial<Record<StepId, Partial<PipelineStep>>> = {}): PipelineStep[] {
  return STEP_ORDER.map((id) => ({ id, state: states[id] ?? "pending", progress: null, elapsed_s: null, request_id: null, ...extra[id] }));
}

function tcOf(t: number): string {
  const f = Math.round((t % 1) * 25);
  const s = Math.floor(t);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}:${p(f)}`;
}

/** A small neutral frame as an SVG data URI so tiles look like tiles without any media on disk. */
function thumbFor(i: number, w = 108, h = 192): string {
  const hues = ["#121212", "#390796", "#1E1E1E", "#000000"];
  const bg = hues[i % hues.length]!;
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">` +
    `<rect width="${w}" height="${h}" fill="${bg}"/><rect x="10" y="${h - 60}" width="88" height="14" rx="3" fill="#5400FB" opacity=".85"/>` +
    `<rect x="10" y="${h - 40}" width="60" height="8" rx="3" fill="#FFFFFF" opacity=".6"/>` +
    `<circle cx="54" cy="${Math.round(h / 3)}" r="22" fill="#FFFFFF" opacity=".18"/></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export function sampleState(language: Language, scenario: Scenario): PanelState {
  const f = language === "ar" ? AR_FLAVOR : EN_FLAVOR;
  const projectsDir = `${f.folder.replace(/\\episodes\\.*$/, "")}\\projects\\${f.item}`;
  const full = scenario !== "idle";
  const context = full
    ? {
        project_path: `${projectsDir}\\${f.item}.prproj`,
        sequence_name: `${f.item}_main`,
        folder: f.folder,
        out_dir: `${f.folder}\\qc`,
        review_mp4: `${f.folder}\\${f.item}_review.mp4`,
      }
    : { project_path: null, sequence_name: null, folder: f.folder, out_dir: null, review_mp4: null };

  const times = [3.2, 9.6, 14, 21.4, 27.8, 33.1, 41.5, 55.9];
  const qcAll: QcFrame[] = f.qc.map(([label, verdict], i) => ({
    t_s: times[i]!,
    tc: tcOf(times[i]!),
    file: `${f.folder}\\qc\\frame_${Math.round(times[i]! * 1000)}.png`,
    label,
    verdict: verdict as QcFrame["verdict"],
    thumb: verdict === "media_pending" ? null : thumbFor(i),
  }));
  // One feed-format (4:5) frame among the 9:16 ones, so the harness shows tiles following their own aspect.
  const four5 = qcAll[6];
  if (four5) Object.assign(four5, { w: 1080, h: 1350, thumb: thumbFor(6, 108, 135) });

  const approval = {
    summary: f.summary,
    preview_mp4: `${f.folder}\\${f.item}_preview.mp4`,
    flagged: [
      { kind: "medical" as const, text: f.flagged[0], tc: f.flagged[1] },
      { kind: "religious" as const, text: f.flagged[2], tc: f.flagged[3] },
    ],
    fingerprint: `sha256:${language === "ar" ? "9c41e7a0b2d8" : "4b7a1f03c6e9"}`,
  };

  const log: LogLine[] = f.log.map(([level, text], i) => ({ ts: `10:${String(12 + i).padStart(2, "0")}:07`, level: level as LogLine["level"], text }));

  const base = { client: f.client, item: f.item, language, editor_name: f.editor, context, log };
  const conn = (claude: "active" | "idle") => ({ engine: "connected" as const, claude, host: { state: "uxp" as const, detail: "Premiere Pro 26.5.2" } });

  switch (scenario) {
    case "idle":
      return { ...base, connection: conn("idle"), pipeline: pipeline({ transcript: "done", plan: "running" }), approval: null, qc: [], log: log.slice(0, 2) };
    case "approval":
      return { ...base, connection: conn("idle"), pipeline: pipeline({ transcript: "done", plan: "done", approve: "waiting" }), approval, qc: [], log: log.slice(0, 3) };
    case "building":
      return {
        ...base,
        connection: conn("active"),
        pipeline: pipeline(
          { transcript: "done", plan: "done", approve: "done", build: "running" },
          { build: { progress: { n: 31, of: BUILD_TOTAL, step: "graphics placed" }, elapsed_s: 74, request_id: "req-build-1" } },
        ),
        approval: null,
        qc: [],
        log,
      };
    case "qc":
      return {
        ...base,
        connection: conn("idle"),
        pipeline: pipeline({ transcript: "done", plan: "done", approve: "done", build: "done", frames: "done", qc: "waiting" }),
        approval: null,
        qc: qcAll,
        log,
      };
    case "showcase":
    default:
      return {
        ...base,
        connection: conn("active"),
        pipeline: pipeline(
          { transcript: "done", plan: "done", approve: "waiting", build: "running" },
          { build: { progress: { n: 31, of: BUILD_TOTAL, step: "graphics placed" }, elapsed_s: 74, request_id: "req-build-1" } },
        ),
        approval,
        qc: qcAll,
        log,
      };
  }
}

export interface MockOptions {
  language?: Language;
  scenario?: Scenario;
}

export class MockSource implements PanelDataSource {
  private state: PanelState;
  private subs = new Set<(s: PanelState) => void>();
  private lang: Language;
  private scenario: Scenario;
  private engine: "connected" | "offline" = "connected";

  constructor(opts: MockOptions = {}) {
    this.lang = opts.language ?? "en";
    this.scenario = opts.scenario ?? "showcase";
    this.state = sampleState(this.lang, this.scenario);
  }

  async snapshot(): Promise<PanelState> {
    return structuredClone(this.state);
  }

  subscribe(cb: (s: PanelState) => void): () => void {
    this.subs.add(cb);
    return () => {
      this.subs.delete(cb);
    };
  }

  // ---- dev controls (not part of PanelDataSource) ----

  /** Re-derives the current scenario in the other language (dev only: progress made by actions is reset). */
  setLanguage(lang: Language): void {
    this.lang = lang;
    this.state = this.fresh();
    this.emit();
  }

  setScenario(scenario: Scenario): void {
    this.scenario = scenario;
    this.state = this.fresh();
    this.emit();
  }

  setEngine(engine: "connected" | "offline"): void {
    this.engine = engine;
    this.state = { ...this.state, connection: { ...this.state.connection, engine } };
    this.emit();
  }

  /** Moves the running Build step forward by 4 graphics; finishes it at the end. Called by a timer in the dev page. */
  advance(): void {
    const build = this.state.pipeline.find((p) => p.id === "build");
    if (!build || build.state !== "running" || !build.progress) return;
    const n = Math.min(build.progress.of, build.progress.n + 4);
    const done = n >= build.progress.of;
    const elapsed = (build.elapsed_s ?? 0) + 3;
    this.state = {
      ...this.state,
      pipeline: this.state.pipeline.map((p) => {
        if (p.id === "build") return done ? { ...p, state: "done", progress: { ...p.progress!, n }, elapsed_s: elapsed, request_id: null } : { ...p, progress: { ...build.progress!, n }, elapsed_s: elapsed };
        if (p.id === "frames" && done) return { ...p, state: "running" };
        return p;
      }),
      connection: done ? { ...this.state.connection, claude: "idle" } : this.state.connection,
    };
    this.emit();
  }

  // ---- PanelDataSource ----

  async approve(input: { item: string; editor_name: string; fingerprint: string }): Promise<Result> {
    const a = this.state.approval;
    if (!a) return { ok: false, error: "There is nothing waiting for approval.", how: "Wait for the next plan." };
    if (a.fingerprint !== input.fingerprint) {
      return { ok: false, error: "The plan changed after you opened it.", how: "Read the new summary, then approve again." };
    }
    this.state = {
      ...this.state,
      approval: null,
      pipeline: this.state.pipeline.map((p) =>
        p.id === "approve" ? { ...p, state: "done" } : p.id === "build" ? { ...p, state: "running", progress: { n: 0, of: BUILD_TOTAL, step: "starting" }, elapsed_s: 0, request_id: "req-build-1" } : p,
      ),
      log: [...this.state.log, this.line("info", `plan approved by ${input.editor_name} (${input.fingerprint})`)],
    };
    this.emit();
    return { ok: true, action: "approve" };
  }

  async requestChanges(input: { item: string; editor_name: string; text: string }): Promise<Result> {
    this.state = {
      ...this.state,
      approval: null,
      pipeline: this.state.pipeline.map((p) => (p.id === "approve" ? { ...p, state: "pending" } : p.id === "plan" ? { ...p, state: "running" } : p)),
      log: [...this.state.log, this.line("info", `changes requested by ${input.editor_name}: ${input.text}`)],
    };
    this.emit();
    return { ok: true, action: "request_changes" };
  }

  async run(action: ActionName, data: object): Promise<Result> {
    const d = data as Record<string, unknown>;
    switch (action) {
      case "status":
        return { ok: true, action, readback: { host: "premiere", hostVersion: "26.5.2", bundle: "0.0.0", protocol: PROTOCOL, busy: false, project: this.state.context.project_path } };
      case "open_project":
        return { ok: true, action, readback: { opened: true, project: String(d["path"] ?? "") } };
      case "set_player_position":
        return { ok: true, action, readback: { position_s: Number(d["t_s"] ?? 0) } };
      case "export_frames": {
        const times = (d["times"] as number[]) ?? [];
        const out = String(d["out_dir"] ?? "");
        this.state = { ...this.state, qc: this.state.qc.map((q) => (times.includes(q.t_s) && (q.verdict === "pending" || q.verdict === "media_pending") ? { ...q, verdict: "pass", thumb: q.thumb ?? thumbFor(1) } : q)) };
        this.emit();
        return { ok: true, action, readback: { frames: times.map((t) => ({ t, tc: tcOf(t), file: `${out}\\frame_${Math.round(t * 1000)}`, called: true })) } };
      }
      case "render_review":
        return { ok: true, action, readback: { started: true, out_path: String(d["out_path"] ?? ""), mode: "encoder" } };
      case "build_project":
        // A complete build_project comes from the engine, never from the panel; the mock does not run one by hand.
        return { ok: false, action, error: "The mock engine builds through rebuild(), not a hand-made build_project.", how: "Use the Rebuild button." };
      default:
        return { ok: false, action, error: `The mock engine does not run "${action}".`, how: "Use the real engine for this action." };
    }
  }

  async rebuild(input: { item: string; project_path: string; replace_edited: boolean }): Promise<Result> {
    this.state = {
      ...this.state,
      pipeline: this.state.pipeline.map((p) => (p.id === "build" ? { ...p, state: "running", progress: { n: 0, of: BUILD_TOTAL, step: "starting" }, elapsed_s: 0, request_id: "req-build-2" } : p)),
      log: [...this.state.log, this.line("info", `rebuild ${input.item}${input.replace_edited ? " (replace edited)" : ""}: ${input.project_path}`)],
    };
    this.emit();
    // A schema-valid build_project readback (what the host reports when the rebuild finishes).
    const readback: BuildProjectReadback = {
      project: input.project_path,
      saved: true,
      settings_after: {
        previewCodec: "apcs", previewFrameWidth: 1080, previewFrameHeight: 1920, videoFrameWidth: 1080, videoFrameHeight: 1920,
        videoFrameRate: { seconds: 0.04, ticks: "10160640000" }, compositeLinearColor: true, maximumBitDepth: false, maximumRenderQuality: false,
      },
      placed: [],
      sharpened: [],
      tracks: { video: [{ i: 1, name: "V1", clips: 1 }], audio: [{ i: 1, name: "A1", clips: 1 }, { i: 2, name: "A2", clips: 1 }] },
    };
    return { ok: true, action: "build_project", readback };
  }

  async cancel(id: string): Promise<void> {
    this.state = {
      ...this.state,
      pipeline: this.state.pipeline.map((p) => (p.request_id === id ? { ...p, state: "failed", request_id: null } : p)),
      log: [...this.state.log, this.line("warn", `cancelled ${id}`)],
    };
    this.emit();
  }

  // ---- internals ----

  /** The current scenario in the current language, keeping the engine toggle the dev page set. */
  private fresh(): PanelState {
    const s = sampleState(this.lang, this.scenario);
    return { ...s, connection: { ...s.connection, engine: this.engine } };
  }

  private line(level: LogLine["level"], text: string): LogLine {
    return { ts: new Date().toISOString().slice(11, 19), level, text };
  }

  private emit(): void {
    for (const cb of [...this.subs]) cb(structuredClone(this.state));
  }
}
