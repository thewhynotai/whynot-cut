// What the panel needs from the app that hosts it. The Premiere UXP plugin and the After Effects CEP
// panel each implement this small adapter; the panel itself never touches a host API.
/** "done" = the host really opened the folder / wrote the clipboard; "shown" = it put the text in the visible box instead. */
export type HostOutcome = "done" | "shown";

export interface PanelHost {
  /** Move the playhead of the item's sequence (QC tile click). */
  setPlayerPosition(t_s: number): void | Promise<void>;
  /** Open a media file (the plan preview MP4) in the Source Monitor. */
  openInSourceMonitor(path: string): void | Promise<void>;
  /** Open a folder (or file) in Explorer / Finder when the host may ("done"), else show its path in a visible, selected text box ("shown"). Never an error; a host that returns nothing is treated as "shown". */
  revealPath(path: string): void | HostOutcome | Promise<void | HostOutcome>;
  /** Put text on the clipboard when the host may ("done"), else show it in a visible, selected text box ("shown"). Never an error; a host that returns nothing is treated as "shown". */
  copyText(text: string): void | HostOutcome | Promise<void | HostOutcome>;
}
