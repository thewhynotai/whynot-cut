# Live risks for Gate 4 and Gate 6 (Adobe track)

These are risks that only a live Adobe run can show. Unit tests cannot catch them. Check each item on the live runs
for Gate 4 (build and read-back) and Gate 6 (install on a clean machine). When an item is closed, record how in this
file.

## R-L1. After Effects "crash in your last session" modal (open)

- **What.** At launch, After Effects can show a modal (window class `#32770`) that reads "We detected a crash in your
  last session … Safe Mode".
  - Seen on 2026-10-17, run 12 of the self-close investigation: an explorer launch, right after a clean quit. The
    Sentry session status for the previous run was `ok`.
  - The cause is not known.
- **Impact.** The modal blocks CEP, so the bridge sends no heartbeat. An unattended AE build waits until someone
  answers the modal, and the run then times out.
- **The right answer for a person.** Choose the button that starts After Effects normally.
  - Not Safe Mode: it starts AE without extensions, so the bridge does not load.
  - Not any Reset Preferences button: it wipes the editor's preferences.
- **If Reset Preferences was chosen.** This happened on 2026-10-17. The checks afterwards found nothing the bridge
  needs:
  - The disk cache stays in `%TEMP%`, which is on D on this PC.
  - The media cache is the shared default, the same location Premiere uses.
  - The bridge starts through its `StartOn` events, not through a preference or a workspace.
  - On the next launch the first heartbeat came at +50 s.
  - No AE preference is needed by WhyNot Cut. In particular, "Allow Scripts to Write Files and Access Network" is not
    needed (see `lib/ae_bridge.py`).
  - What the reset does lose is the user's own layout and choices. Without a backup these cannot be restored.
- **What the engine must do.** It must never answer the modal itself. When a launch gets no heartbeat, the engine
  reports "After Effects is waiting for an answer on screen". It must not report a bridge failure.
- **Gate 4/6 check.** Launch AE 3 times through explorer and 3 times through the engine launcher, each after a clean
  quit, and count the modals. Confirm that the no-heartbeat message names the on-screen dialog.

## R-L2. After Effects quits on its own soon after launch (open, not reproduced)

- **What.** Twice, on 10-15 and 10-17, AE made a clean, ordinary quit about 7 s after the first heartbeat.
  - On a clean quit AE writes its workspace and preferences at the moment of quitting, and the CEP heartbeat runs
    until the end.
  - It is not a crash: there is no dump, no WER report and no event log entry.
  - It is not a kill: TerminateProcess never writes the preferences.
- **Not reproduced.** 10 of 10 cold harness relaunches stayed up, 12 of 12 in total. The bridge has no code path that
  quits AE.
- **Remaining leads, most likely first.**
  1. A keypress (Alt+F4 or Ctrl+Q) reached AE as it took the foreground.
  2. The first truly cold launch after a day or more. This cannot be tested without a reboot.
  3. RAM at 85% or more. This is not tested, because the machine rule forbids heavy work at that level.
- **Next time it happens.**
  1. Run `aemon.ps1` next to the launch.
  2. Before AE is relaunched, copy the `__sentry-event` file from
     `%TEMP%\Adobe\After Effects\26.0\SentryIO-db\*.run\`.
  3. Ask the person what was on screen and which key they pressed.
- **Gate 6 check.** Do a first launch after a reboot on the clean machine, and run `aemon.ps1` next to it.
- Full log: `AE-SELFCLOSE.md` in the plan session's notes folder.

## R-L3. `AfterFX.exe -r` with a space in the path (fix in review)

- **What.** `AfterFX.exe -r <jsx>` does nothing, and reports nothing, when the script path contains a space.
  - `docs/adobe/photoshop-route.md` records this.
  - The fix stages the script under a path without spaces. When it cannot, the run returns `SCRIPT_STAGE_FAILED`.
- **Gate 4 check.** Do one live AE build for a client whose folder path contains spaces.

## R-L4. Premiere QE components may lack `remove()` (open)

- **What.** The cleanup of a wrong effect in the legacy blur path needs `remove()` on Premiere QE components.
- **Gate 6 check.** Confirm on the installed Premiere version whether `remove()` exists.

## R-L5. After Effects music ducking keys (open, T4.6)

- **What.** T4.6 writes Audio Levels keys on the MUSIC layer with a floor of −60 dB. The old fade used −48 dB. The keys
  are meant to use linear interpolation.
- **Unknown until a live run.**
  - Does After Effects accept −60 dB, or does it clamp the value?
  - Does it keep the keys linear?

  If it clamps, the read-back reports a mismatch.
- **Gate 4 check.** Do one live motion build with a licensed track. Read the MUSIC layer's keys back on both channels,
  then listen to the render at a dip.
