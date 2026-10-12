// The ops the Premiere UXP host adapter implements this round, one file each. CAPABILITIES is what the plugin declares
// in its hello (the daemon routes exactly these actions to it). Not this round: build_project (createProject is
// partial, parity O1, so it stays on the CEP bridge), render_review (encoder export pending, X1), probe and the After
// Effects actions. scripts/gen-validators.mjs compiles the contract checks for exactly this list (a test keeps them equal).
import type { ActionName } from "../../../panel-ui/src/contract.ts";
import { clipComponents } from "./clip-components.ts";
import { closeProjectPath } from "./close-project-path.ts";
import { exportFrames } from "./export-frames.ts";
import { openProject } from "./open-project.ts";
import { ping } from "./ping.ts";
import { setPlayerPosition } from "./set-player-position.ts";
import { status } from "./status.ts";

export const OPS = {
  ping,
  status,
  open_project: openProject,
  set_player_position: setPlayerPosition,
  export_frames: exportFrames,
  close_project_path: closeProjectPath,
  clip_components: clipComponents,
} as const;

export const CAPABILITIES: readonly ActionName[] = Object.keys(OPS) as ActionName[];
