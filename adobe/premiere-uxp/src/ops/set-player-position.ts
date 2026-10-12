// set_player_position (set_player_position.schema.json): move the playhead of the named sequence in the active
// project (made the active sequence first when another one is), then read back where Premiere says it is. Not a
// project edit, so no transaction. Sequence.setPlayerPosition is from the types; live measurement is spike 0.1.3 (h).
import type { SetPlayerPositionData, SetPlayerPositionReadback } from "../../../panel-ui/src/contract.ts";
import { activateSequence, findSequence, getPpro, requireActiveProject } from "./premiere.ts";
import { OpError } from "./types.ts";
import type { Op } from "./types.ts";

export const setPlayerPosition: Op<SetPlayerPositionData, SetPlayerPositionReadback> = {
  action: "set_player_position",
  exclusive: true,
  async run(data, ctx) {
    const ppro = getPpro(ctx.env);
    const project = await requireActiveProject(ppro);
    const seq = await findSequence(project, data.sequence_name);
    await activateSequence(project, seq);
    const moved = await seq.setPlayerPosition(ppro.TickTime.createWithSeconds(data.t_s));
    if (moved === false) throw new OpError("Premiere did not move the playhead.", "Click in the Timeline once, then run the command again.");
    const at = await seq.getPlayerPosition();
    ctx.throwIfCancelled();
    return { position_s: typeof at?.seconds === "number" ? at.seconds : data.t_s };
  },
};
