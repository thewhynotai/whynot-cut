# H6 live checklist: host_busy and the idle footprint (next Premiere / After Effects session)

What H6 changed (G2 hardening, Addendum G13), and what only a live session can confirm. Use a `whynot-test`
project with nothing unsaved. Read everything from files: the heartbeat
(`<engine home>/ppro-queue/bridge.heartbeat`, `<engine home>/ae-queue/bridge.heartbeat`) and the daemon's log (the
hidden daemon page's `#log`, reachable through the CEP debug port if one is set up). Nothing here needs code.

A one-line watcher for the heartbeat, run from Claude's shell (PowerShell, read only; it prints the time, the age of
the beat and host_busy every second):

```powershell
$q = "$env:USERPROFILE\.whynot-cut\ppro-queue\bridge.heartbeat"   # engine_home from ~/.whynot-cut/bridge/config.json; ae-queue for AE
while ($true) { try { $b = Get-Content $q -Raw | ConvertFrom-Json; $age = ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() - $b.at) / 1000; "{0:HH:mm:ss}  age {1,5:N1}s  busy={2}  host_busy={3}  action={4}" -f (Get-Date), $age, $b.busy, $b.host_busy, $b.action } catch { "unreadable" }; Start-Sleep 1 }
```

## 1. The bridge loads and idles (both apps)

1. Install the bundle built from this commit; start Premiere.
2. Run the watcher. **Log:** idle, the age stays under 3 s for 2 minutes (2 s beats; the engine counts a beat dead at
   5 s); while a job runs or waits, under 2 s (1 s beats). `host_busy` = `unknown`, `host_busy_reason` =
   `encoder_events_off` (the encoder events are off by default).
3. Press the panel's status check (or run any `reel` command that pings Premiere). **Log:** it answers within a second (the job arrived
   through `fs.watch`, not the 10 s safety tick). Repeat 5 times; note the slowest.
4. In the daemon log: no `queue watch …` line. If you see `queue watch unavailable`, `error` or `deaf`, copy it: the
   1 s fallback is running, which works but wakes more. (The watch is created with `persistent: false` so a plain node
   run can end; confirm here that CEP still delivers its events: step 3 answering within a second shows it.)
5. Task Manager → Details → the `CEPHtmlEngine.exe` of the WhyNot Cut daemon: **log** CPU % and memory over 10 idle
   minutes (expect ~0 % CPU).
6. Same for After Effects with `ae-queue`.

## 2. Premiere: the encoder events (app.encoder) — OFF by default

0. First check step 7 below with the events OFF (they are off unless `~/.whynot-cut/bridge/config.json` has
   `"encoder_events": true`). Then add that key, restart Premiere, and do steps 1–8. Turn it on for customers only
   if step 7 says the bind does not replace another extension's handler.
1. After step 1.3 (one job has run) the daemon log says `encoder events: bound` or `encoder events: unavailable`.
   **Log which.** `unavailable` means `app.encoder.bind` or `PlugPlugExternalObject` failed: host_busy stays `unknown`.
2. Queue a sequence to Adobe Media Encoder: File → Export → Media → **Send to Media Encoder**, start the queue in AME.
   **Log** the watcher lines from the click to the end: expect `exporting` within 2 s of the job being queued, and
   `idle` within 2 s of AME finishing (that first full cycle is what makes `idle` possible at all).
3. Queue two jobs; cancel one in AME; let the other finish. **Log:** `exporting` until the second ends, then `idle`.
4. Queue one job and make it fail (e.g. output to a read-only folder). **Log:** `idle` after the error.
5. **Export in Premiere itself** (Export mode → Export, no AME). **Log** host_busy during it. Expected: no encoder
   event fires, so it stays `idle` / `unknown`. If it shows `idle` during an in-app export, write it down: then
   Premiere's own exports need another signal (the UXP EncoderManager events, see 4).
6. Does an AME job that was **queued by hand inside AME** (not from Premiere) fire the events? **Log** yes / no.
7. Another extension that binds encoder events (if one is installed): after WhyNot Cut binds, does that extension
   still get its events? `app.encoder.bind` may replace a handler rather than add one. **Log** yes / no. If it
   replaces, turn the bind off before release (it is one call in `hostTouch`, `js/bridge.js`).
8. Restart only the daemon (close and reopen Premiere is fine): the log says `bound` again and step 2 still works
   once (the `$.global.__wncEncoderBound` guard: no double counting). **Log** whether a single export now counts
   twice (watch for `exporting` staying on after AME finished: that means two handlers).

## 2b. Premiere: Media Encoder's process and probe.request

1. With Adobe Media Encoder open, create `<engine home>\ppro-queue\probe.request` (an empty file). **Log:** the file
   disappears within a second; the heartbeat says `host_busy` `unknown`, `host_busy_reason` `media_encoder_running`,
   and `host_probe.answered_at` moves. Quit AME, wait 15 s, request again: the reason goes back.
2. **Log** the process name tasklist sees (`tasklist /FI "IMAGENAME eq Adobe Media Encoder.exe"`); on macOS, what
   `pgrep -f "Adobe Media Encoder"` prints. If the name differs, the check never finds it.
3. Start a long in-app export (Export mode → Export) and create `probe.request` during it. **Log:** does the no-op probe
   answer during the export? If not, after 3 s the reason is `script_engine_busy` (value `unknown`).

## 3. After Effects: renderQueue.rendering

1. Add a comp to the render queue; press Render.
2. While it renders, press the panel's status check (a job). **Log:** how long the status job takes to answer (does
   AE run our evalScript during a render at all, or only after it?), and the watcher's host_busy: `rendering`,
   `idle` (probe ran after the render) or `unknown`.
3. During the render, **log** whether the heartbeat age stays under 3 s (does the CEP daemon keep beating while AE
   renders?). If it stops, `serve.host_busy` reports that lane `unknown` while the beat is under 120 s old.
4. After the render: host_busy goes `unknown` 15 s after the last job (the probe's lifetime). Expected.
5. **The probe.request heuristic (unproven):** start a render that takes over a minute, then create
   `<engine home>\ae-queue\probe.request`. **Log:** after about 3 s the watcher shows `rendering` with reason
   `script_engine_busy` (the probe is out, the heartbeat keeps beating), and when the render ends the probe answers and
   it goes to `idle`. If AE answers the probe DURING the render, log the answer: then `renderQueue.rendering` itself is
   the signal and the heuristic never fires. If the heartbeat stops during the render, the heuristic cannot fire
   either (the lane goes stale: "proceed").
6. Repeat 5 with a modal dialog open in AE instead of a render: does the heuristic call that "rendering" too? **Log**
   it: a false "rendering" only delays a GPU job, but it should be known.

## 4. For the next step (not built in H6)

- Premiere UXP has `ppro.EncoderManager` events (`EVENT_RENDER_QUEUE / _COMPLETE / _ERROR / _CANCEL / _PROGRESS`,
  added with `EventManager.addEventListener`, which adds rather than replaces). **Log** whether they fire for
  Send to Media Encoder and for an in-app export, in a UXP probe: that is the better source once the UXP host
  reports host_busy to serve.
- Media Encoder as a process: with AME open, **log** its process name and whether it is running while idle.
