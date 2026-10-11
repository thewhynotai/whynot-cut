// What the panel needs from the app that hosts it. The Premiere UXP plugin and the After Effects CEP
// panel each implement this small adapter; the panel itself never touches a host API.
export interface PanelHost {
  /** Move the playhead of the item's sequence (QC tile click). */
  setPlayerPosition(t_s: number): void | Promise<void>;
  /** Open a media file (the plan preview MP4) in the Source Monitor. */
  openInSourceMonitor(path: string): void | Promise<void>;
  /** Show a file or folder in Explorer / Finder. */
  revealPath(path: string): void | Promise<void>;
  /** Put text on the clipboard. */
  copyText(text: string): void | Promise<void>;
}
