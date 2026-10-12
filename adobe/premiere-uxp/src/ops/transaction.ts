// The one way the UXP adapter changes a project (parity U1 / U2, measured live): every Action goes into ONE
// project.executeTransaction inside project.lockedAccess, labelled "WhyNot Cut build", so the editor sees one named
// History step and one Ctrl+Z undoes it. Reads and the playhead stay outside. None of this round's seven ops creates
// an Action (open / close / save / playhead / frame export are not undoable edits); build_project uses this.
import type { Action, Project } from "@adobe/premierepro";
import { OpError } from "./types.ts";

export const UNDO_LABEL = "WhyNot Cut build";

/** Run `build(add)` as one undoable transaction; an action Premiere refuses or a rejected transaction is an OpError. */
export function transact(project: Project, build: (add: (action: Action) => void) => void, label: string = UNDO_LABEL): void {
  let applied = false;
  let failure: unknown;
  project.lockedAccess(() => {
    try {
      applied = project.executeTransaction((ca) => {
        build((action) => {
          if (!ca.addAction(action)) throw new OpError("Premiere refused one of the changes.", "Run the command again; if it repeats, send the WhyNot Cut log.");
        });
      }, label);
    } catch (e) {
      failure = e;
    }
  });
  if (failure !== undefined) throw failure;
  if (!applied) throw new OpError("Premiere did not apply the changes.", "Look for a dialog in Premiere, dismiss it, then run the command again.");
}
