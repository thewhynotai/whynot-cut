// export_frames (export_frames.schema.json): Premiere renders PNG frames of its own timeline into out_dir as
// frame_<ms>.png, the engine's QC evidence. Measured (parity Q1, facts 1 and 13):
//   - Exporter.exportSequenceFrame(seq, TickTime, "<bare file name>.png", "<native backslash folder>\", w, h); every
//     forward-slash folder form returned false, so the winning form is used directly (no fallbacks to try);
//   - `false` is not a throw: it is the {t, error} frame form; `called` means the call returned true;
//   - the PNG appears before it is fully written, so each frame waits until its size stops changing;
//   - UXP takes a TickTime, so the frame entries have no `tc`.
// project_path (when given) is made the active project first; the sequence is made the active sequence.
import type { ExportFramesData, ExportFramesReadback, ExportedFrame } from "../../../panel-ui/src/contract.ts";
import {
  activateProject,
  activateSequence,
  ensureDir,
  findSequence,
  fsPath,
  getPpro,
  isWindowsPath,
  nativePath,
  requireActiveProject,
  statOf,
} from "./premiere.ts";
import { DEFAULT_TIMING, OpError } from "./types.ts";
import type { FrameTiming, Op, OpContext } from "./types.ts";

/** frame_<milliseconds, at least 6 digits>.png, the CEP bridge's names (the engine globs *.png). */
export function frameName(t: number): string {
  return `frame_${String(Math.round(t * 1000)).padStart(6, "0")}.png`;
}

/** The folder in the form exportSequenceFrame takes: native separators and a trailing separator. */
export function exportFolder(outDir: string): string {
  const native = nativePath(outDir).replace(/[\\/]+$/, "");
  return native + (isWindowsPath(outDir) ? "\\" : "/");
}

type Settled = { ok: true } | { ok: false; why: string };

/** Wait until the file exists and two reads `pollMs` apart give the same non-zero size. */
async function waitForStableFile(ctx: OpContext, path: string, timing: FrameTiming): Promise<Settled> {
  const { env } = ctx;
  const fs = env.fs();
  const t0 = env.now();
  let last = -1;
  let seen = false;
  for (;;) {
    ctx.throwIfCancelled();
    const st = await statOf(fs, path);
    const size = typeof st?.size === "number" ? st.size : st ? 0 : -1;
    if (size > 0) {
      if (size === last) return { ok: true };
      seen = true;
    }
    last = size;
    const waited = env.now() - t0;
    if (!seen && waited >= timing.appearMs) return { ok: false, why: `no file appeared at ${path} within ${Math.round(timing.appearMs / 1000)} s` };
    if (waited >= timing.settleMs) return { ok: false, why: `${path} was still being written after ${Math.round(timing.settleMs / 1000)} s` };
    await env.sleep(timing.pollMs);
  }
}

export const exportFrames: Op<ExportFramesData, ExportFramesReadback> = {
  action: "export_frames",
  exclusive: true,
  async run(data, ctx) {
    const timing: FrameTiming = { ...DEFAULT_TIMING, ...ctx.env.timing };
    const ppro = getPpro(ctx.env);
    const project = data.project_path ? await activateProject(ctx.env, ppro, data.project_path) : await requireActiveProject(ppro);
    const seq = await findSequence(project, data.sequence_name);
    await activateSequence(project, seq);
    const size = await seq.getFrameSize();
    const width = Math.round(Number(size?.width));
    const height = Math.round(Number(size?.height));
    if (!(width > 0 && height > 0)) throw new OpError(`Premiere reported no frame size for "${seq.name}".`, "Open the sequence in the Timeline, then run the command again.");

    const folder = exportFolder(data.out_dir);
    try {
      await ensureDir(ctx.env.fs(), data.out_dir);
    } catch {
      throw new OpError(`The frames folder ${folder} could not be created.`, "Check that the drive is connected and writable, then run the command again.");
    }

    const frames: ExportedFrame[] = [];
    const n = data.times.length;
    for (let i = 0; i < n; i++) {
      ctx.throwIfCancelled();
      const t = data.times[i] as number;
      ctx.progress(`Frame ${i + 1} of ${n}`, i, n);
      const name = frameName(t);
      let returned: unknown;
      try {
        returned = await ppro.Exporter.exportSequenceFrame(seq, ppro.TickTime.createWithSeconds(t), name, folder, width, height);
      } catch (e) {
        frames.push({ t, error: `exportSequenceFrame failed: ${e instanceof Error ? e.message : String(e)}` });
        continue;
      }
      if (returned !== true) {
        frames.push({ t, error: `Premiere did not export the frame (exportSequenceFrame returned ${String(returned)}).` });
        continue;
      }
      const settled = await waitForStableFile(ctx, `${fsPath(folder)}${name}`, timing);
      frames.push(settled.ok ? { t, file: `${folder}${name}`, called: true } : { t, error: `Premiere reported the frame exported, but ${settled.why}.` });
    }
    return { frames };
  },
};
