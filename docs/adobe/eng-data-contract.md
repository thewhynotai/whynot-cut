# G-ENG-DATA: panel ↔ engine data contract for the 3.0 screens

Date: 2026-10-14. Status: contract for mocking (Adobe track) and for the engine build (executor, Phase 6 / T6.2b).
Inputs: `docs/design/screen-inventory.md` §6, `docs/design/reviews/G2-r1-designer.md` and `G2-r1-agency-owner.md`
(controller decisions), `docs/adobe/g2-reliability-speed-gaps.md`, `docs/superpowers/plans/2026-10-14-3.0-adobe-g2-hardening.md`
(H1 to H3), `whynot-cut/engine/reel/contract/` (session, engine_state, progress, protocol), `serve/engine_state.py`,
`serve/messages.py`, and the mockups' `window.MOCK_DATA` (`adobe/panel-ui/design/strings.js`, `strings/*.js`).

## 1. Purpose and scope

- This contract names the data the new 3.0 screens show and `PanelState` does not carry today. Today `PanelState` has
  `connection, client, item, language, editor_name, context, pipeline, approval, qc, log`.
- It is **additive to protocol 4**. No field is renamed, removed or retyped, and `protocol` stays `4`. Every new
  property is optional (it is not in any `required` list). New objects are closed (`additionalProperties: false`), like
  the rest of `session.schema.json`.
- It is safe for panels already in the field. `parseIncoming` in `adobe/panel-ui/src/daemon-source.ts` is hand-written
  and reads only the keys it knows, so unknown keys are ignored.
- `item` stays a **string**, and so does `approval`'s current shape. The brief's names map to wire names as follows:

| Brief name | Wire name (new, optional) | Where |
|---|---|---|
| `item.poster`, `item.duration_s`, `time_saved` | `item_meta.poster`, `item_meta.duration_s`, `item_meta.time_saved` | `panel_state` |
| `plan.edit_map`, `plan.diff` | `plan.edit_map`, `plan.diff` | `panel_state` |
| `week` | `week` | `panel_state` |
| `verbs[]` | `verbs[]` (+ `tools_last[]`, same row shape) | `panel_state` |
| `approval {by, at, …}` | `approval_record` | `panel_state` (the old `approval` card is unchanged) |
| `jobs[]` | `jobs[]` | `panel_state` |
| progress `phase` | `phase` | `progress.schema.json` and `pipeline_step.progress` |
| `claude {…}` | `claude` (detail; `connection.claude` stays the pill) | `panel_state` |
| `setup[]`, `support` | `setup[]`, `support` | `panel_state` |

**Fixed units and formats (apply to every field below):**

| Kind | Format | Example |
|---|---|---|
| Instant | RFC 3339 / ISO 8601 **with an offset**. The engine writes new values in UTC (`Z`). Older records with a local offset (`plan-approval.json` `at` comes from `common.now_iso()`) are valid as they are. The panel displays every instant in the computer's local zone. | `2026-10-14T11:32:00Z` → "Tue 14 Oct 2026, 14:32" (Cairo, UTC+3) |
| Duration | seconds, float, at most 3 decimals | `400.0`, `52.04` |
| Time on a timeline | seconds from the start of the **result sequence**, float, 3 decimals | `14.3` |
| Estimated minutes | integer minutes ≥ 0 | `45` |
| Timecode for display only | the existing `tc` strings (`00:00:14:08`); never used for maths | |

**No developer words in user-facing values.** A value the editor reads is either an `_en`/`_ar` pair written for
editors, or an i18n key the panel owns. Command names, file names of evidence, stack traces, `engine`, `reel`, `serve`,
`JSON` and English error strings never reach a user-facing value. Machine values (enums, codes, ids) are never shown
as text; the panel maps them to its own strings.

## 2. Objects

### 2.1 `item_meta`: the current item's media and time saved (P-03, P-06 done, P-07)

| Field | Type | Req | Meaning | Example |
|---|---|---|---|---|
| `duration_s` | number ≥ 0 \| null | yes | length of the raw clip (or of the episode range for a reel cut from an episode) | `400.0` |
| `poster` | object \| null | yes | one still of the item; null = none yet | see below |
| `poster.file` | string ≤ 4096 | yes | absolute local path of a JPEG/PNG inside the item folder | `D:\Clients\Sahha\output\projects\C0239\00_inputs\poster.jpg` |
| `poster.w`, `poster.h` | integer 16..4096 | yes | pixel size (the panel draws the well with `aspectPct(w, h)`) | `270`, `480` |
| `poster.data_url` | string ≤ 49152 | no | the same image as `data:image/jpeg;base64,…`, sent only when ≤ 48 KB | |
| `time_saved` | object \| null | yes | null until the item has a plan | see below |
| `time_saved.raw_s` | number ≥ 0 | yes | = `duration_s` at the time of the plan | `400.0` |
| `time_saved.result_s` | number ≥ 0 | yes | length of the planned/built sequence | `52.0` |
| `time_saved.est_manual_min` | integer ≥ 0 | yes | estimate of a manual edit of this item | `60` |
| `time_saved.est_saved_min` | integer ≥ 0 | yes | what the screens show as "saved about": `max(0, est_manual_min − basis.review_min)` | `45` |
| `time_saved.basis` | object | yes | how the estimate was made (shown on request, never hidden) | |
| `basis.method` | `"per_raw_minute"` | yes | the only method in 3.0 | |
| `basis.rate_min_per_raw_min` | number > 0 | yes | manual minutes per raw minute | `9.0` |
| `basis.review_min` | integer ≥ 0 | yes | the editor's own review time, subtracted | `15` |
| `basis.source` | `"default"` \| `"settings"` | yes | owner default or the editor's own rate (P-22) | `"default"` |

Example: `raw_s` = 400 s is 6.67 raw minutes; × 9.0 = 60 manual minutes; minus a 15-minute review = 45 minutes saved.
That matches the mock line "6:40 raw → 52 s reel · saved about 45 min".

```json
"item_meta": {
  "duration_s": 400.0,
  "poster": { "file": "D:\\Clients\\Sahha\\output\\projects\\C0239\\00_inputs\\poster.jpg", "w": 270, "h": 480 },
  "time_saved": { "raw_s": 400.0, "result_s": 52.0, "est_manual_min": 60, "est_saved_min": 45,
    "basis": { "method": "per_raw_minute", "rate_min_per_raw_min": 9.0, "review_min": 15, "source": "default" } }
}
```

**How the panel loads the poster safely:**
1. If `data_url` is present and passes `isSafeImg` (`src/media.ts`), the panel uses it. It is a raster data URL, needs
   no filesystem permission and fetches nothing.
2. Otherwise the panel builds `file:///` + the path with forward slashes, percent-encodes each segment, and draws it
   only if `isSafeImg` passes. `isSafeImg` refuses a host, UNC paths, encoded separators and look-alike slashes.
3. If both fail, or the `<img>` fires `error`, the panel draws the empty #0D0D0D well. It never draws a broken image or
   alt text. Whether `<img>` can load a `file:///` path in UXP is a css_lab item (G2-r1-designer). Until it is proven,
   the engine always sends `data_url`.

### 2.2 `plan`: the plan the editor is looking at (P-07, A-02)

| Field | Type | Req | Meaning | Example |
|---|---|---|---|---|
| `version` | integer ≥ 1 | yes | counts compiled plans with a new fingerprint, per item | `2` |
| `fingerprint` | string ≤ 256 | yes | = `approval.fingerprint` of the same plan | `"sha256:9c1e…"` |
| `sequence_name` | string ≤ 256 \| null | no | the NEW sequence the build will create (trust line `{seq}`) | `"C0239_v2"` |
| `edit_map` | object \| null | yes | below; null = no map (the panel hides the strip) | |
| `edit_map.duration_s` | number > 0 | yes | length of the result sequence | `52.0` |
| `edit_map.spans[]` | array ≤ 2000 | yes | timeline marks, sorted by `start_s` | |
| `spans[].kind` | `cut` \| `statement` \| `broll` \| `flagged` \| `caption` | yes | `cut` = a join where material was removed (a point: `end_s == start_s`); `statement` = an on-screen line; `broll`; `flagged` = an on-screen line that needs a medical/religious check (it replaces its `statement` span); `caption` = optional, the panel may ignore it | `"broll"` |
| `spans[].start_s`, `end_s` | number, 0 ≤ start ≤ end ≤ duration_s | yes | result-timeline seconds | `14.3`, `17.5` |
| `spans[].label` | string ≤ 120 | no | the line as said (for tooltips and the aria text); never a template id | `"قياس السكر الصايم…"` |
| `spans[].flag` | `medical` \| `religious` | only on `flagged` | which check | `"medical"` |
| `diff` | object \| null | yes | null on version 1, or when nothing countable changed | |
| `diff.from_version`, `to_version` | integer | yes | the previous plan shown or approved, and this one | `1`, `2` |
| `diff.changes[]` | array ≤ 12 | yes | one row per changed count | |
| `changes[].what` | `cuts` \| `statements` \| `broll` \| `captions` \| `duration_s` \| `flagged` \| `music` | yes | what changed | `"cuts"` |
| `changes[].before`, `after` | number \| null | yes | counts (or seconds for `duration_s`); null = none | `6`, `7` |
| `diff.summary_en`, `summary_ar` | string ≤ 200 | yes | one line, built from `changes` | see example |

```json
"plan": {
  "version": 2, "fingerprint": "sha256:9c1e0d", "sequence_name": "C0239_v2",
  "edit_map": { "duration_s": 52.0, "spans": [
    { "kind": "statement", "start_s": 3.0, "end_s": 7.0, "label": "قياس السكر الصبح" },
    { "kind": "cut", "start_s": 4.2, "end_s": 4.2 },
    { "kind": "cut", "start_s": 9.8, "end_s": 9.8 },
    { "kind": "flagged", "start_s": 14.3, "end_s": 17.5, "flag": "medical",
      "label": "قياس السكر الصايم الصبح بيقولك أكتر من أي قراية تانية في اليوم." },
    { "kind": "cut", "start_s": 17.9, "end_s": 17.9 },
    { "kind": "broll", "start_s": 19.5, "end_s": 24.0 },
    { "kind": "cut", "start_s": 26.0, "end_s": 26.0 },
    { "kind": "flagged", "start_s": 31.8, "end_s": 35.0, "flag": "medical" },
    { "kind": "cut", "start_s": 35.6, "end_s": 35.6 },
    { "kind": "broll", "start_s": 37.5, "end_s": 42.0 },
    { "kind": "cut", "start_s": 44.1, "end_s": 44.1 },
    { "kind": "flagged", "start_s": 47.1, "end_s": 50.5, "flag": "religious" } ] },
  "diff": { "from_version": 1, "to_version": 2,
    "changes": [ { "what": "cuts", "before": 6, "after": 7 }, { "what": "broll", "before": 2, "after": 1 } ],
    "summary_en": "7 cuts instead of 6 · 1 B-roll clip instead of 2",
    "summary_ar": "7 قطعات بدل 6 · لقطة B-roll واحدة بدل 2" }
}
```

### 2.3 `week`: time saved this week (P-03, P-04)

| Field | Type | Req | Meaning | Example |
|---|---|---|---|---|
| `since` | date-time | yes | start of the week, local midnight, sent as UTC | `2026-10-10T21:00:00Z` |
| `items` | integer ≥ 0 | yes | items handed off since `since`, all clients | `7` |
| `est_saved_min` | integer ≥ 0 | yes | sum of their `est_saved_min` | `270` |
| `by_client[]` | array ≤ 200 | no | P-04 rows: `{client (folder name ≤ 256), items, est_saved_min}` | |

```json
"week": { "since": "2026-10-10T21:00:00Z", "items": 7, "est_saved_min": 270,
  "by_client": [ { "client": "Sahha Clinic", "items": 4, "est_saved_min": 180 } ] }
```

### 2.4 `verbs[]` and `tools_last[]`: step state per verb (P-03, A-01)

| Field | Type | Req | Meaning | Example |
|---|---|---|---|---|
| `id` | `drop` \| `edit` \| `approve` (tools_last: `tidy` \| `hush` \| `kalam`) | yes | fixed order on Home | `"edit"` |
| `state` | `todo` \| `running` \| `done` \| `blocked` | yes | `blocked` = cannot start now | `"done"` |
| `reason` | `needs_claude` \| `needs_service` \| `no_plan` \| `no_footage` | only when blocked | the panel's own sentence and fix; `approve` + `no_plan` = the card is hidden (owner decision) | `"needs_claude"` |
| `result_en`, `result_ar` | string ≤ 120 | no | the done line | `"Plan ready · 52 s reel"` |
| `at` | date-time | no | when it reached this state; the panel shows "{ago}" | `2026-10-14T11:20:00Z` |
| `step` | `{n, of}` integers | no | Home hero "Step 3 of 7" | `{"n": 3, "of": 7}` |

```json
"verbs": [
  { "id": "drop", "state": "done", "result_en": "1 clip added · 6:40", "result_ar": "اتضاف كليب واحد · 6:40", "at": "2026-10-14T09:02:00Z" },
  { "id": "edit", "state": "done", "result_en": "Plan ready · 52 s reel", "result_ar": "الخطة جاهزة · ريل 52 ثانية", "at": "2026-10-14T11:20:00Z", "step": { "n": 3, "of": 7 } },
  { "id": "approve", "state": "todo" } ],
"tools_last": [ { "id": "tidy", "state": "done", "result_en": "214 files sorted", "result_ar": "اترتّب 214 ملف", "at": "2026-10-13T12:42:10Z" } ]
```

### 2.5 `approval_record`: who approved, when, and with whom (P-07, A-02, P-06)

| Field | Type | Req | Meaning | Example |
|---|---|---|---|---|
| `by` | string 1..256 | yes | the name typed at approval | `"Yunus"` |
| `at` | date-time | yes | full date and time (shown as "Tue 14 Oct 2026, 14:32") | `2026-10-14T11:32:00Z` |
| `confirmed_with` | string ≤ 256 | no | free text, for example a doctor or sheikh; absent = not given | `"د. هناء مصطفى"` |
| `flagged_checked` | boolean | yes | the "I've checked these lines" box was ticked | `true` |
| `flagged_count` | integer ≥ 0 | no | flagged lines at approval | `3` |
| `current` | boolean | yes | its fingerprint equals the current plan's; false = the plan changed since (P-07 stale) | `true` |
| `version` | integer | no | the `plan.version` approved | `2` |
| `previous_approval` | object, sent as `panel_state.previous_approval` | no | the approval that no longer counts, so the editor can see it and re-approve without redoing unchanged work (R3, P-07 older and stale): `{by` string 1..256, `at` date-time, `via` `"panel"` \| `"claude"` (where it was given), `format` string ≤ 16 (the approval-record format version it was written in, e.g. `"2.2"`), `reason` `"older_whynot_cut"` \| `"plan_changed"`, `confirmed_with?` string ≤ 256, `lines?` array ≤ 64 of `{graphic_id` string ≤ 64, `text` string ≤ 1024 (the on-screen text as approved), `checked` boolean`}}`. The panel shows who approved, when and with whom. A flagged line is prefilled as ticked, marked "From the earlier approval" / «من الموافقة اللي قبل كده», ONLY when a `lines[]` entry has the same `graphic_id` AND the same `text` as the current plan's line and `checked` is true; every other line stays empty with "The wording changed, so this line needs a fresh look." `confirmed_with` is shown, never prefilled into the field. **Absent** = nothing is prefilled: every line starts empty (today's behaviour); absent `lines` = the who/when line only, no prefill. | `{"by": "Yunus", "at": "2026-10-14T11:32:00Z", "via": "panel", "format": "2.2", "reason": "older_whynot_cut", "lines": [{"graphic_id": "g1", "text": "…", "checked": true}]}` |

```json
"approval_record": { "by": "Yunus", "at": "2026-10-14T11:32:00Z", "confirmed_with": "د. هناء مصطفى",
  "flagged_checked": true, "flagged_count": 3, "current": true, "version": 2 }
```

The **intent** changes too, additively: `approve` gains the optional `confirmed_with` (string ≤ 256) and
`flagged_checked` (boolean). With flagged lines present, the daemon refuses `flagged_checked !== true` with the reply
`ok:false` and `how` = the i18n key `approval.tick_first`. `reel approve-plan` gains `--confirmed-with` and
`--flagged-checked`.

### 2.6 `jobs[]`: the job journal, as the panel sees it (H1; P-06, P-11, A-04)

| Field | Type | Req | Meaning | Example |
|---|---|---|---|---|
| `request_id` | id (`^[A-Za-z0-9._-]{1,64}$`) | yes | the panel reattaches by it | `"r-7f3a"` |
| `action` | protocol action enum | yes | `request.schema.json#/properties/action` | `"export_frames"` |
| `state` | `received` \| `queued` \| `claimed` \| `done` \| `failed` \| `interrupted` | yes | H1 journal states | `"done"` |
| `submitted_at`, `updated_at` | date-time | yes | | |
| `item` | string ≤ 256 | no | the item the job was for | `"C0239"` |
| `result` | object | only when done/failed/interrupted | `{ok: bool, code?: session error code \| "interrupted" \| "host_lost", n?, of?}`; never the host's text | `{"ok": true}` |

The last 20 jobs, newest first. `session_kind` and `job_id` stay in the journal file and are not sent to the panel.
"Try again" sends a new `request_id` only when the job is `failed` or `interrupted` (H1).

```json
"jobs": [ { "request_id": "r-7f3a", "action": "export_frames", "state": "interrupted", "item": "C0239",
  "submitted_at": "2026-10-14T11:40:02Z", "updated_at": "2026-10-14T11:41:30Z", "result": { "ok": false, "code": "host_lost" } } ]
```

### 2.7 Progress `phase` and `elapsed_s` (H2; P-06, A-04)

The progress event (`progress.schema.json`) gains `phase`, an optional enum: `queued | claimed | running | elapsed`.
`elapsed_s` already exists. `pipeline_step` gains the same optional `phase` (null/absent: no event yet) as a sibling of
`progress`, because `queued` / `claimed` carry no `n/of` and `progress` requires them. An `elapsed` tick keeps the
step's phase from the events before it; a settled step carries none. Landed in H2: `FileQueueAdapter` sends them for CEP
commands (`serve/adapters.py` QueueTracker), the daemon source stores them, the running card renders them.

| Phase | Sent when | Panel shows |
|---|---|---|
| `queued` | at submit (FileQueueAdapter) | indeterminate bar, "Waiting for Premiere…" |
| `claimed` | the `.claimed` file appears | indeterminate bar, "Premiere started it" |
| `running` | a host sends a real progress event with `n/of` | "{n} of {of}" bar |
| `elapsed` | every 2 s until the result, while no `n/of` is known | indeterminate bar + "Elapsed {t}" |

When `phase` is set, `step` is a machine phrase (the phase name). The panel renders its own string and never shows
`step`. The first event must arrive within 2 s of the click (budget S3).

```json
{ "type": "progress", "progress": { "event": "progress", "id": "r-7f3a", "action": "export_frames",
  "step": "elapsed", "phase": "elapsed", "elapsed_s": 14.0 } }
```

### 2.8 `claude`: Claude detail behind the pill (P-01, P-02, P-03, P-07 no-claude)

| Field | Type | Req | Meaning | Example |
|---|---|---|---|---|
| `state` | `ok` \| `signed_out` \| `missing` \| `unknown` | yes | the account check only | `"signed_out"` |
| `checked_at` | date-time | yes | when the probe ran | `2026-10-14T11:30:00Z` |
| `plugin_version` | string ≤ 32 | no | the WhyNot Cut add-on version inside Claude (P-02 "older add-on") | `"3.0.0"` |
| `how_to_url` | https URL ≤ 512 | no | the page for "how to install / sign in"; allowlisted host | `"https://thewhynot.ai/help/claude"` |

`connection.claude` stays the pill and agrees with this object: `ok → ready | working | waiting`,
`signed_out → signed_out`, `missing → not_installed`, `unknown → unknown`.

**Source is read-only.** The engine finds the `claude` executable on PATH and the known install paths (`missing` if
none). It runs `claude auth status`, or the equivalent the installed CLI offers, with a 3 s timeout, and reads only the
exit status (and a signed-in boolean if the output gives one). Nothing is stored except `state` and `checked_at` in
memory, cached for 60 s. Credential files are never read, and the command's output is never logged or forwarded.

```json
"claude": { "state": "signed_out", "checked_at": "2026-10-14T11:30:00Z", "plugin_version": "3.0.0",
  "how_to_url": "https://thewhynot.ai/help/claude" }
```

### 2.9 `setup[]`: the first-run checklist (P-01; the 4-row summary of the installer's rows)

| Field | Type | Req | Meaning | Example |
|---|---|---|---|---|
| `id` | `engine` \| `premiere` \| `claude` \| `clients` | yes | fixed order | `"claude"` |
| `state` | `ok` \| `todo` \| `checking` \| `failed` | yes | `todo` = the editor has a step to take | `"todo"` |
| `detail` | i18n key ≤ 64 | no | the row's sub-line, a panel key (e.g. `claude.signed_out`) | `"claude.signed_out"` |
| `params` | object of string\|number, ≤ 4 keys | no | values for the key's `{placeholders}`; a folder NAME only | `{"name": "Clients"}` |

```json
"setup": [ { "id": "engine", "state": "ok" }, { "id": "premiere", "state": "ok" },
  { "id": "claude", "state": "todo", "detail": "claude.signed_out" }, { "id": "clients", "state": "todo", "detail": "checklist.clients.none" } ]
```

The `engine` row is always `ok` when the daemon sends it. The panel itself sets that row to `failed` when it has no
connection.

### 2.10 `support` (P-02, P-11, P-22, I-00)

| Field | Type | Req | Meaning | Example |
|---|---|---|---|---|
| `url` | https URL ≤ 512 | no | what "Contact support" opens. For 3.0 it is the WhyNot Cut support WhatsApp chat (Yunus, 2026-10-16): a `https://wa.me/<number>?text=…` link whose fixed text says it is a support request. It is live, so the engine sends it by default and the panel shows "Copy details and open WhatsApp" (one action: copy the details, then open the chat; the editor pastes them) with the D-05 reply promise "We reply within one working day (Sun–Thu, Cairo time)." Absent = the link is hidden: "Copy details for support" only copies and one plain-text line says "The support chat is coming soon." (H24; mockups: `?support=off`) | `"https://wa.me/20XXXXXXXXXX?text=WhyNot%20Cut%20support"` |
| `data_url` | https URL ≤ 512 | no | the "Cost and data" sheet (what is sent, where, retention per Claude plan; owner decision D-02); absent = the link is hidden and the D-02 line stands alone | `"https://thewhynot.ai/data"` |

```json
"support": { "url": "https://wa.me/20XXXXXXXXXX?text=WhyNot%20Cut%20support", "data_url": "https://thewhynot.ai/data" }
```

The panel opens either URL with the host's external-open call and never adds query parameters. `url` (WhatsApp) is live
and sent by default; `data_url` stays absent until Yunus publishes the page (H24): the panel never links to a page that
isn't live. Diagnostics are copied to the
clipboard by the editor (P-22 "Copy details"), never attached to the URL.

### 2.11 Speed: `stale`, `welcome.features`, pushed states and the `perf` message (H3; budgets S1, S2, S3)

Landed in H3 (`serve/app.py`, `serve/push.py`, `serve/perf.py`, `serve/perf_report.py`, `src/perf.ts`).

| Where | Field | Type | Meaning |
|---|---|---|---|
| `panel_state` | `stale` | boolean, optional | `true` when the daemon built this state from its last good engine-state read because the fresh read did not answer in time. A session's FIRST snapshot waits at most 1 s (later ones 3 s). A panel then gets the fresh state as a push as soon as that read answers. Absent = fresh. |
| `welcome` | `features` | array ≤ 8 of `"perf"` \| `"push"`, optional | `perf`: the daemon appends the panel's perf batches. `push`: it pushes a `state` (no `id`) when the engine state changes. Absent (an older daemon) = no perf batch is sent. |
| new message `perf` | `marks` | 1..50 `perf_mark` | panel → daemon, only when `features` has `perf`. Answered with nothing. |
| `perf_mark` | `mark` | `panel.boot` \| `panel.first_paint` \| `link.welcome` \| `link.first_state` \| `panel.usable` \| `ui.click` \| `ui.paint` | the panel's marks only; the daemon's own (`cmd.*`, `link.welcome_sent`) are refused |
| | `t` | number, 0..10^14 | epoch ms, the panel's clock |
| | `ms` | number, 0..3600000, optional | the duration the mark closes: since `panel.boot` for the boot marks, since its `ui.click` for `ui.paint` |
| | `rid` | `^[A-Za-z0-9][A-Za-z0-9._-]*$`, ≤ 48, optional | pairs a `ui.click` with its `ui.paint` (`c-12`). It is too short for the engine token and cannot hold a path. |

The daemon's rules:
- **Who may send `perf`.** Only a `kind: "panel"` session. From any other session it is `error{schema}` and audited.
- **Rate.** At most 1 batch/s per session, burst 5. A batch over the rate is dropped silently, audited once per session.
- **The file.** `serve/perf.py` keeps only `{t, mark, ms?, rid?}` and drops every other key. It appends to
  `<home>/logs/perf.jsonl`, which is capped at 512 KB with one rotated `perf.jsonl.1`.
- **Its own marks.** The daemon writes `cmd.received`, `cmd.queued`, `cmd.claimed`, `cmd.first_progress` and
  `cmd.result` (each with its ms since `cmd.received` and the request id), plus `link.welcome_sent` (ms since the hello).
- **The report.** `python -m serve.perf_report --since <iso>` (and `reel perf-report`) prints the p95 per budget and
  exits 1 on a miss:
  - S1 ≤ 1500 ms: `panel.boot` → `panel.usable` (or `link.first_state` when no usable mark exists);
  - S2 ≤ 100 ms: `ui.click` → `ui.paint`;
  - S3 ≤ 2000 ms: `cmd.received` → `cmd.first_progress`.

The panel sends its marks only right after the first state and then once per poll. Clicks are sampled (1 in 5), and a
click whose handler paints nothing records nothing. The panel's 2 s snapshot poll stays as the fallback for pushed
states; H6 lengthens it once push is proven live.

```json
{ "type": "perf", "marks": [ { "mark": "panel.boot", "t": 1760000000000 },
  { "mark": "panel.usable", "t": 1760000000812, "ms": 812 }, { "mark": "ui.paint", "t": 1760000001000, "ms": 6.5, "rid": "c-12" } ] }
```

## 3. Screen → fields

| Screen | Reads (new fields) |
|---|---|
| P-01 first run | `setup[]`, `claude`, `support.url`, `support.data_url` |
| P-02 status | `claude` (state, plugin_version, how_to_url), `support.url` |
| P-03 home | `item_meta.poster`, `item_meta.duration_s`, `verbs[]`, `tools_last[]`, `week`, `claude.state`, `approval_record.current` |
| P-04 picker | `week.by_client[]` (clients and clips lists are outside this contract, §6) |
| P-05 footage | `verbs[drop]`, `item_meta.duration_s`, `claude.state` |
| P-06 pipeline / done | `pipeline[].progress.phase`, `pipeline[].elapsed_s`, `jobs[]`, `item_meta.time_saved`, `plan.sequence_name` |
| P-07 approval | `plan.edit_map`, `plan.diff`, `plan.sequence_name`, `item_meta.time_saved`, `approval_record`, `claude.state` |
| P-08 QC frames | `claude.state` (Request changes), `jobs[]` (export frames) |
| P-10 needs you | `claude.state` |
| P-11 messages | `jobs[].result.code`, `support.url`, `claude` |
| P-12 AI sheet | `claude.state` (P-12's "jobs" are its three AI tasks, not `jobs[]`) |
| P-22 settings | `support.url`, `support.data_url`, `item_meta.time_saved.basis` (rate source) |
| A-01 AE home | `verbs[]`, `item_meta.poster` |
| A-02 motion approval | `plan.diff`, `plan.version`, `approval_record`, `claude.state` |
| A-04 AE render | `jobs[]`, progress `phase` / `elapsed_s` |
| I-03, I-05 installer | the same `claude.state` enum, through the installer core (not `PanelState`); I-05 shows the `data_url` link only when the installer core has it |

## 4. Where each field comes from

The daemon (`serve/engine_state.py` `panel_fields`) reads every evidence file the way it does today: capped, confined
to the item or client folder, no links, cached by mtime and inode. "NEW file" means the executor writes it.

| Field | Source today | To build |
|---|---|---|
| `item_meta.duration_s` | `lib/media.py` probe (`duration_s`); `timeline-spec.json` `time_map.source_duration_ms` once planned | NEW `00_inputs/item-meta.json {duration_s, poster{file,w,h}, at}`, written at intake/transcribe |
| `item_meta.poster` | nothing | ffmpeg still at 10 % of the clip (or the first face frame) → `00_inputs/poster.jpg`, max 270 × 480, ≤ 48 KB; recorded in `item-meta.json` |
| `item_meta.time_saved` | raw from above; result from `timeline-spec.json` `duration_ms` (motion: `motion-plan.json`) | daemon computes; rate from NEW `<plugin>/config/time-saved.json {rate_min_per_raw_min, review_min}`, override in settings |
| `plan.version`, `plan.diff` | `plan_fingerprint` (`lib/plan.py:912`); no history | NEW `01_analysis/plan-versions.json {versions:[{version, fingerprint, at, counts{cuts, statements, broll, captions, flagged, duration_s}}]}` (last 20), appended by `reel plan` / `motion-plan` on a new fingerprint; daemon diffs current vs last approved (else previous) and builds `summary_en/ar` from a fixed template table |
| `plan.edit_map` | `timeline-spec.json`: `duration_ms`, `time_map.keep_ms` (joins), `events[].template` | NEW `01_analysis/edit-map.json`, written by `reel plan` (plan.py owns which template is a statement or a B-roll); flagged spans need the sensitive-review file below |
| `flagged` spans, `approval.flagged` | none (`engine_state.py`: "no evidence file carries the flags") | NEW `01_analysis/sensitive-review.json {items:[{kind, text, start_s, end_s, event_id}]}`, written by medical-reviewer via a `reel` writer |
| `plan.sequence_name` | `ppro_build` naming | daemon derives the next `<item>_v<n>` the build will create |
| `week` | nothing | NEW `<home>/state/ledger.jsonl`, one line per handoff `{client, item, at, raw_s, result_s, est_saved_min}`, appended by the handoff writer; daemon sums from `since` |
| `verbs[]`, `tools_last[]` | `pipeline` (evidence files), `approval_state` (`plan.py:945`), `08_quality_control/project-status.json` history (timestamps) | daemon derives; tool results from the Phase 6B tool journals (none before 6B → absent) |
| `approval_record` | `01_analysis/plan-approval.json {approved, by, at, plan_fingerprint, note}` | add `confirmed_with`, `flagged_checked`, `flagged_count`, `version` to the record (cli.py `cmd_approve_plan` and the daemon's approve handler) |
| `jobs[]` | none (in memory, `router.py:62`) | H1 `serve/jobs.py` journal `<home>/serve/jobs/<rid>.json` |
| progress `phase` | none (CEP jobs emit no progress, `adapters.py:146`) | H2 FileQueueAdapter |
| `claude` | pill hard-coded `unknown` (`messages.py:110`); `active.json` `claude_pid` for working/waiting | NEW `serve/claude_probe.py` (read-only, §2.8) |
| `setup[]` | `connection`, settings clients root | daemon composes |
| `support.url`, `support.data_url`, `claude.how_to_url` | nothing | Phase 6 engine task: `config/defaults/links.json {support_url, data_url, claude_howto_url}`, all empty until Yunus publishes (H24); https and allowlisted host only, ≤ 512 chars |

## 5. Rules

1. **Absent means old behaviour.** Any new field, or any sub-field, may be absent, null or invalid. The panel then
   renders what it renders today (no poster well → the empty well; no edit map → no strip; no `time_saved` → no line;
   no `verbs` → the verbs without results; no `phase` → today's running card). It never throws, and it never prints
   `undefined`, `null`, `NaN` or an empty `{}` placeholder. Each object is checked by hand like `parseConnection`, and
   an invalid object is dropped whole.
2. **Both languages, or a key.** User-facing text comes as an `_en` + `_ar` pair (`result_*`, `summary_*`) or as an
   i18n key the panel owns (`setup[].detail`, `verbs[].reason`, `jobs[].result.code` → message). If the pair is missing
   the UI's language, that line is not shown. The panel never falls back to the other language. Arabic is professional
   Egyptian (G2 decision). Digits are Latin in both languages, as in the mocks. Text said by the speaker (`label`,
   flagged text) stays as said, in both UIs.
3. **No tokens or secrets.** No new field carries the engine token, an API key, Claude credentials, CLI output,
   environment variables or a user's account email. `perf.jsonl` (H3) is likewise free of paths and names.
4. **Paths only where needed, and confined.** The only path in this contract is `item_meta.poster.file`. It must resolve
   (realpath, no symlinks, no UNC, no `..`) inside `<client_root>/output/projects/<item>/`, be a `.jpg` or `.png` of
   at most 8 MB, or be dropped. Screen body copy uses file and folder NAMES only (Addendum G); "Show in folder" uses
   the existing `context` paths.
5. **Size.** New fields add at most 64 KB to a `state` message, plus at most 48 KB for `poster.data_url`. Lists are
   capped as stated (spans 2000, jobs 20, changes 12, by_client 200). The engine truncates; it never fails the state.
6. **Schema.** `session.schema.json` adds each object as an optional `panel_state` property. `progress.schema.json`
   and `pipeline_step` add `phase`, and `approve` adds `confirmed_with` / `flagged_checked`. `source.ts`,
   `contract.ts` and `test/session.test.ts` mirror these, and the engine's SessionContractTests keep the key parity.
   One fixture carries every example above.

## 6. Open questions for the executor

1. **Claude probe command.** Is `claude auth status` stable on the installed CLI (Windows and macOS), what does it exit
   with when signed out, and does it ever prompt or open a browser? If it can, the probe must use another read-only
   check, or report `unknown`.
2. **Poster frame.** Choose the frame rule (10 %, the first face frame, or the first statement's frame) and the step
   that writes it (intake or transcribe). For a reel cut from an episode, is it taken from the range?
3. **Time-saved rate.** The owner sets `rate_min_per_raw_min` and `review_min` (proposed 9.0 and 15). May the editor
   change them in P-22? The copy always says "about", and the basis must be honest for the $1,000 claim (G).
4. **Week start.** Sunday 00:00 local (the Egyptian work week) is proposed; ISO Monday is the alternative.
5. **Plan versions.** Should `plan-versions.json` live with `reel plan` / `motion-plan` (proposed), and does the diff
   compare against the last *approved* plan or the last *shown* one? Proposed: approved if any, else previous.
6. **Sensitive review file.** medical-reviewer reports to the lead in chat today. Who writes `sensitive-review.json`,
   with which `reel` writer, and how do its statements map to `events[]` (`event_id`)?
7. **Edit map ownership.** Proposed: `reel plan` writes `edit-map.json`, and plan.py owns the template → kind table.
   Confirm, and add the motion equivalent (scenes → statement and B-roll spans).
8. **Ledger.** Which writer appends `ledger.jsonl` at handoff? What retention (proposed 400 lines)? Does a rebuild of
   the same item replace its line?
9. **Claude add-on version.** Where does `plugin_version` come from (the installed plugin's `plugin.json` under the
   Claude plugins folder, read-only)? Is that read allowed?
10. **Links allowlist.** Which hosts are allowed for `support_url` and `claude_howto_url`
    (proposed: `thewhynot.ai`, `claude.ai`, `docs.anthropic.com`)?
11. **Tool results (`tools_last`).** These ride on the Phase 6B journals; confirm the shape now so 6B writes it.

## 7. Executor answers (2026-10-14): binding, and they replace §6 where they differ
1. **`claude`**
   - Source: `claude auth status`, run with stdin closed, a 3 s timeout and no shell. It is read-only and never opens a browser.
   - Parse `loggedIn`. A non-zero exit, a timeout or a parse failure means `unknown`, never `signed_out`.
   - Cached for 60 s.
   - The signed-out exit code is confirmed on this PC with a sandboxed `CLAUDE_CONFIG_DIR`, never by signing the owner out.
2. **Poster**
   - The engine writes `<item>/poster.jpg` at the preview step (stage 8), from the frame 0.5 s into the first kept segment.
   - Before a preview exists, intake writes a fallback frame at 10 % of the duration.
   - Episode reels get theirs at reels-select, at each reel's start + 0.5 s.
   - Owner: executor, Phase 6 engine.
3. **Time saved**
   - The formula in §2 is the default, labelled «تقدير» / "estimate".
   - The editor can change the rate in Settings (preference `time_saved_rate`). It is not an owner number.
4. **Week:** starts on Sunday.
5. **Plan versions:** they live with `reel plan` / `reel motion-plan`. `plan.diff` is always against the last APPROVED plan.
6. **Flags:** `reel review-flags` (Phase 4) writes `<item>/review-flags.json`, each line keyed by plan event id. Until then `flag` is absent.
7. **Edit map:** `reel plan` writes `edit-map.json`, and `reel motion-plan` writes the motion equivalent (Phase 6 engine).
8. **Weekly log**
   - `reel handoff` appends one line per item to `<home>/logs/time-saved.jsonl`, keyed by item id.
   - A rebuild replaces the item's line: dedupe on read, the last line wins.
   - Lines are kept for 1 year.
9. **Add-on version:** read from `~/.whynot-cut/plugin-root.json` (written by T3.4). Reading it is allowed.
10. **Link allowlist:** https only, on these hosts and nothing else (no other thewhynot.ai subdomains):
    - `thewhynot.ai`
    - `dl.thewhynot.ai`
    - `claude.ai`
    - `support.claude.com`
    - `code.claude.com`
    - `wa.me`, for `support.url` only (added 2026-10-16: Yunus chose WhatsApp as the support channel)
11. **`tools_last[]`:** the shape in §2.4 is FROZEN now. Phase 6B writes it.

The panel mocks against this contract until the G-ENG-DATA engine subtasks land (tracked in PROGRESS by the executor).
