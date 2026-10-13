# WhyNot Cut 3.0: screen inventory for the high-fidelity mockups (E-D2)

| | |
|---|---|
| Track | Design track, Addendum E §E1, step E-D2 |
| Date | 2026-10-13 |
| Status | Draft 1, written from the sources below. The mockups in `adobe/panel-ui/design/` follow this list |
| Stored mockups | `adobe/panel-ui/design/` (HTML/CSS) + `renders/` (PNG) + `manifest.csv`; installer mockups are handed to the installer track (E-T1) |
| Sources read | Addendum A (+ the three PRDs), B, C (+ `evidence/ecosystem.md` §3.4, §3.5, §3.6), D, E; the Phase 7 installer plan; `adobe/panel-ui/src/{render,source,mount,commands}.ts`, `src/kit/*`; `whynot-cut/engine/reel/contract/session.schema.json`; `i18n/{en,ar}.json`; `skills/motion/SKILL.md`; `adobe/cep-bridge/CSXS/manifest.xml`; `brand/tokens.css`; `docs/adobe/uxp-parity.md` |

Reference letters in the "Rule" cells: A = Addendum A, B = B, C = C (`C1.n` = Addendum C §C1 item n; `eco §3.n` = `evidence/ecosystem.md`), D = D, E = E (`E2.1#n` = security rule n), FR-n = a PRD requirement, `PS` = a field of `PanelState` in `source.ts`.

## 0. Count and index

**35 screens** (Premiere UXP 22, After Effects CEP 4, installer 9) **+ 9 global elements** (G1–G9). The states of each screen are listed inside its section (about 150 in all).

| ID | Screen | Host | Primary action |
|---|---|---|---|
| G1–G9 | Header and pills · language switch · Needs-you badge · tabs · notice/error card · dialog · log drawer · footer · loading skeleton | all | n/a |
| P-01 | First-run checklist | Premiere UXP | Set up my first client |
| P-02 | Status cards (engine · Premiere link · Claude · panel update) | Premiere UXP | the card's one fix button |
| P-03 | Home | Premiere UXP | the next verb (Drop files, Make my edit or Approve) |
| P-04 | Client and clip picker | Premiere UXP | Choose client folder |
| P-05 | New footage and Make my edit | Premiere UXP | Make my edit |
| P-06 | Pipeline progress (+ done) | Premiere UXP | Approve, or Open project when done |
| P-07 | Approval (+ flagged lines, request changes) | Premiere UXP | Approve |
| P-08 | QC frames grid | Premiere UXP | Re-export (a pending tile) |
| P-09 | Actions and rebuild confirm | Premiere UXP | Rebuild (in the confirm dialog) |
| P-10 | Needs you | Premiere UXP | the first item's action |
| P-11 | Error cards (catalogue) | Premiere UXP | the card's one fix button |
| P-12 | AI action sheet | Premiere UXP | Apply |
| P-13 | Tools hub | Premiere UXP | Organise → Cut → Caption |
| P-14 | Tidy: scan and plan | Premiere UXP | Clean & organise |
| P-15 | Tidy: report, undo, podcast sync | Premiere UXP | Open the pre-clean copy (undo) / Sync the podcast |
| P-16 | Hush: scan and preview | Premiere UXP | Cut |
| P-17 | Hush: result and undo | Premiere UXP | Undo |
| P-18 | Kalam: setup | Premiere UXP | Start |
| P-19 | Kalam: MOGRT gallery | Premiere UXP | Use this template |
| P-20 | Kalam: progress and results | Premiere UXP | Stop (while running) / none when done |
| P-21 | Models | Premiere UXP | Download all |
| P-22 | Settings | Premiere UXP | none (a settings page has no primary) |
| A-01 | After Effects home and motion pipeline | AE CEP | Start the build (when the plan is approved) |
| A-02 | Motion plan approval | AE CEP | Approve |
| A-03 | After Effects gates and Needs-you cards | AE CEP | the card's one fix button |
| A-04 | Motion render, frames and handoff | AE CEP | Open project |
| I-01 | Welcome | installer | Install everything |
| I-02 | Customise | installer | Install |
| I-03 | Preflight | installer | Continue |
| I-04 | Progress checklist (+ action needed) | installer | none while running (Cancel is secondary) |
| I-05 | Install Claude for me | installer | Install Claude |
| I-06 | Finish | installer | Open Claude |
| I-07 | Security and failure cards | installer | the card's one fix button |
| I-08 | Update and repair | installer | Update |
| I-09 | Uninstall | installer | Uninstall |

## 1. Rules that apply to every screen

| # | Rule | Source |
|---|---|---|
| 1 | One primary button per screen (violet). Secondary actions are glass buttons. Destructive actions show what changes and the backup name, then ask to confirm | B4.2 |
| 2 | No command on screen, ever. A problem is one sentence and one fix button (Start engine, Try again, Copy diagnostics, or a named action). Commands live only in the log drawer and in Copy diagnostics. File names and paths are fine, in `<bdi dir="ltr">` | C1.4, B4.4 |
| 3 | Empty states teach: what to do next, one button. No blank panel | B4.5 |
| 4 | Narrow first: everything works at 280–360 px docked, no sideways scroll, hit targets 32 px or more | B4.7 |
| 5 | Status always has an icon (ok, warn, error, info, pending), never colour alone. Contrast 4.5:1 text, 3:1 large text and icons | B2, B4.8 |
| 6 | Always dark. Tokens only from `brand/tokens.css`. #5400FB is a fill, never text; violet text is #9D6BFF; pink #D95C9B for eyebrows and the active tab | B2, tokens.css |
| 7 | Arabic is RTL by CSS `direction`. Tabs, steps, chevrons and the progress fill mirror. Commands, paths, timecodes and numbers sit in `<bdi dir="ltr">` with Western digits | B3 |
| 8 | Arabic copy is clear MSA, with the English UI term in parentheses on first use (e.g. «التسلسل (Sequence)») | B3 |
| 9 | Kalam, Hush and Tidy keep their PRD flows and controls. Only the look changes (same cards, buttons, chips, waveform, progress strip) | A0, B4.9, B6 |
| 10 | UXP limits that shape the mockups (measured): flexbox only, no `<button>` (a `div role="button"`), svg colour only through CSS fill, box-shadow does not paint (the CTA mark is a 1 px pink ring), `@font-face` does not load (system font stacks), physical margins for gaps, radius up to 16 px on controls (999 px on `<span>` chips only) | STATE.md, uxp-parity.md |
| 11 | Mockup widths: 300 / 360 / 480 in AR and EN (E1). Also draw 280 for the layouts that carry a row of controls (CEP minimum width is 280, default 340) | E1, B4.7, CSXS manifest |
| 12 | Every screen needs its states drawn: empty, loading, normal, error, offline, stale, success (only the ones that apply; the section says which do not) | E-D2, E-D3 |
| 13 | Motion 150–250 ms ease, progress shimmer, no layout shift | E-D6 |

Arabic word list used in the drafts below (keeps the copy consistent with `ar.json`): panel = اللوحة; engine = المحرّك (Engine); client = العميل; clip = المقطع; plan = الخطة (Plan); approve = موافقة; build = البناء (Build); frames = الإطارات; QC = الفحص (QC); handoff = التسليم (Handoff); backup = نسخة احتياطية (Backup); undo = تراجع; playhead = مؤشر التشغيل (Playhead); captions = الترجمة النصية (Captions).

## 2. Global elements

### G1. Header and the three pills

| | |
|---|---|
| Host | Premiere UXP and AE CEP (same kit) |
| Purpose | Always show whose work this is and whether the three links are alive |
| Data | `PS.client`, `PS.item` (or `status.noclient`); `PS.connection.engine` (connected / offline), `.claude` (ClaudeState), `.host.state` (uxp / cep / offline) and `.host.detail` (e.g. "Premiere Pro 26.5.2"). NEW: engine "starting" (first 10 s, eco §3.2), host name for After Effects |
| Layout | Row 1: monogram + wordmark + Needs-you badge + language switch. Row 2: client · item. Row 3: the three pills. Gradient hairline under row 1. At 280 px a pill shows icon + value only; the key word ("Engine", "Claude", "Premiere") appears from 340 px. Today `kit/header.ts` has the badge and switch but no pills, and `render.ts` has the pills but no badge or switch: the mockup merges them |
| Rule | B2 (monogram + wordmark + hairline), B4.6, C1.6, eco §3.4 (one status model, identical in panel, doctor, SessionStart) |

| Pill | State | Look | Existing key | NEW EN | NEW AR |
|---|---|---|---|---|---|
| Engine | starting | pending icon, muted | none | Starting | يبدأ التشغيل |
| Engine | connected | ok | `pill.engine.connected` | n/a | n/a |
| Engine | offline | error | `pill.engine.offline` | n/a | n/a |
| Claude | not_installed | error | none (only `active`, `idle`, `unknown` exist) | Not installed | غير مثبّت |
| Claude | signed_out | warn | none | Sign in | سجّل الدخول |
| Claude | plugin_outdated | warn | none | Update | يحتاج تحديثًا |
| Claude | ready | ok | none | Ready | جاهز |
| Claude | working | ok, animated dot | none | Working on {item} | يعمل على {item} |
| Claude | waiting | warn | none | Waiting for you | بانتظارك |
| Claude | unknown | muted | `pill.claude.unknown` | n/a | n/a |
| Host | uxp | ok | `pill.host.uxp` (shows `host.detail` when set) | n/a | n/a |
| Host | cep | warn | `pill.host.cep` | n/a | n/a |
| Host | offline | error | `pill.host.offline` | n/a | n/a |
| Host label in AE | n/a | n/a | `pill.host` = "Premiere" (hard-coded) | After Effects | After Effects |

Key names for the NEW lines: `pill.engine.starting`, `pill.claude.not_installed`, `.signed_out`, `.plugin_outdated`, `.ready`, `.working`, `.waiting`, `pill.host.ae`. The legacy `active` and `idle` map to `working` and `ready`.

### G2. Language switch

| | |
|---|---|
| Purpose | ع / EN, remembered per editor; the first-run default comes from preferences `language` |
| Data | `PS.language` |
| States | ع on, EN on. The panel re-renders mirrored with no layout jump |
| Keys | `lang.group`, `lang.ar`, `lang.en`, `lang.ar.short`, `lang.en.short` |
| Rule | B3 |

### G3. Needs-you badge

| | |
|---|---|
| Purpose | Count of things only the editor can do; opens P-10 |
| Data | NEW `needs_you` (count + items). `PanelState` has no such field today; the kit's `needsYouBadge(t, count)` already takes the count |
| States | 0 = hidden; 1–99 = number in a pink-outlined badge; 100 or more = "99+" |
| Keys | `needs.label`, `needs.aria` |
| Rule | B4.6, T4.7 |

### G4. Tabs

| | |
|---|---|
| Purpose | Home · Edit · Tools. Models and Settings open from rows at the bottom of Home (a header gear does not fit at 280 px) |
| Data | NEW optional count per tab (Edit shows 1 when an approval waits) |
| States | active (pink underline), inactive, hidden while the first-run checklist (P-01) is showing |
| Keys | `tabs.label`, `tab.home`, `tab.edit`, `tab.tools` |
| Rule | B4.7, B4.8 (tab order follows the visual order, mirrored in RTL) |

### G5. Notice and error card

| | |
|---|---|
| Purpose | The one pattern for every message: ok, info (amber note, no button) or error (red, one fix button) |
| Data | `Notice {kind, text, how?, code?, fix?, again?}` in `render.ts`; the fix is one of Start engine, Try again, Copy diagnostics |
| States | ok, info, error with each of the three fix buttons; error whose text held a command (the panel's own sentence replaces it, raw words go to the log); dismiss ✕ |
| Keys | `notice.*`, `action.retry`, `action.start_engine`, `actions.diagnostics`, `notice.send_diagnostics`, `notice.dismiss` |
| Rule | C1.4, B4.4 |

### G6. Confirm dialog

| | |
|---|---|
| Purpose | Every destructive step (rebuild, Hush cut, Tidy clean, MOGRT placement, uninstall) shows what changes and the backup name, then asks |
| Layout | Warning card: title, "what will change" list, backup line with the name in a mono chip on its own row, primary confirm + secondary "keep" |
| States | with backup; without backup (`dialog.nobackup`: cannot be undone); confirm disabled while a command runs |
| Keys | `dialog.changes`, `dialog.backup`, `dialog.nobackup`, `rebuild.*` |
| Rule | B4.2 |

### G7. Log drawer

| | |
|---|---|
| Purpose | The only place commands and raw codes may appear |
| Data | `PS.log` (last 100 lines shown), build stamp "WhyNot Cut {version} · build {build}" |
| States | collapsed (default), open, empty |
| Keys | `log.toggle`, `log.lines`, `log.empty`, `log.build`, `log.held`, `log.start_engine` |
| Note | `log.held`, `log.start_engine` and `footer.powered` have English text in `ar.json` today |
| Rule | C1.4, B4.4 |

### G8. Footer

| | |
|---|---|
| Purpose | «Powered by thewhynot.ai» (left-to-right even in Arabic). One line, muted |
| Keys | `footer.powered` |
| Rule | A6b, B2 (the master plan and C1.7 say "Powered by Claude"; see §5) |

### G9. Loading skeleton and progress

| | |
|---|---|
| Purpose | Loading state for every list and card (a skeleton, never a blank panel); the progress bar with shimmer, gradient fill, fills from the right in Arabic |
| States | skeleton, determinate bar with "{n} of {of}" and elapsed time, indeterminate shimmer |
| Keys | `status.connecting`, `pipeline.progress`, `pipeline.elapsed` |
| Rule | B4.3, E-D6 |

## 3. Premiere UXP screens

### P-01. First-run checklist

| | |
|---|---|
| Purpose | The editor opens Premiere first; the panel shows what is ready and the one thing to press |
| Data | Status model rows `engine`, `premiere`, `claude`, `clients` (`kit/checklist.ts`). From `PS.connection` + NEW `setup[] {id, state ok/warn/error/pending, detail}`; the Claude row detail is "signed in · plugin {version}" |
| Primary | The first red row's fix; when engine, link and Claude are green, "Set up my first client" on the clients row (opens Claude on the start skill; the panel never runs it). The kit throws on a second primary |
| Secondary | Per-row fixes: Start engine, Try again, Open Claude, Open guide, Update; Copy diagnostics |
| Existing keys | `checklist.label`, `.engine`, `.premiere`, `.claude`, `.clients`, `status.ok`, `.warn`, `.error`, `.pending`, `action.start_engine`, `action.retry`, `empty.noclient.*` |
| Rule | C3.6 / eco §3.6 (one checklist definition shared with the installer and the start skill), C1.4, B4.5 |

| State | What the editor sees |
|---|---|
| Loading | Four rows with the pending icon, "Starting WhyNot Cut…" for the first 10 s |
| Normal | Mixed rows, one primary |
| Error | Red row with its sentence and button (engine not running: Start engine) |
| Offline | Engine row red; the other rows pending ("waiting for the engine") |
| Stale | The P-02 update card sits above the list |
| Success | All green: toast "WhyNot Cut is ready.", the panel moves to Home |
| Empty | Not applicable (the checklist is the empty state) |

| NEW key | EN | AR |
|---|---|---|
| `firstrun.title` | Let's get WhyNot Cut ready | لنجهّز WhyNot Cut للعمل |
| `firstrun.sub` | Four quick checks. A button appears next to any check that needs you. | أربعة فحوص سريعة. يظهر زر بجانب أي فحص يحتاج إلى تدخّلك. |
| `firstrun.client` | Set up my first client | جهّز عميلي الأول |
| `firstrun.client_hint` | Claude opens and walks you through it. | يفتح Claude ويرشدك خطوة بخطوة. |
| `firstrun.starting` | Starting WhyNot Cut… | جارٍ تشغيل WhyNot Cut… |
| `firstrun.ready` | WhyNot Cut is ready. | WhyNot Cut جاهز. |
| `checklist.engine.ok` | Running | يعمل |
| `checklist.premiere.ok` | Linked to {host} | مرتبط بـ {host} |
| `checklist.claude.ok` | Signed in · plugin {version} | تم تسجيل الدخول · الإضافة {version} |
| `checklist.clients.none` | No client folder yet | لا يوجد مجلد عميل بعد |

### P-02. Status cards

| | |
|---|---|
| Purpose | One card per problem of the status model, each with one sentence and one button. Shown at the top of any screen, or by tapping a pill |
| Data | `PS.connection` (engine, claude, host), `welcome.update.panel` (ok / stale / newer / unknown; NEW `update` in the state), the Claude probe detail (plugin version, item, minutes ago), NEW pending-update flag |
| Primary | The card's one button |
| Existing keys | `offline.*` (14 link diagnoses), `action.start_engine`, `action.retry`, `notice.code.no_route`, `pill.*` |
| Rule | C1.4, C1.6, C1.8 (stale panel: "Restart Premiere" as one card), eco §3.4 (Start engine · Restart Premiere · Open Claude · Sign in to Claude · Update WhyNot Cut · Copy diagnostics) |

| Card | Trigger | Button | EN | AR |
|---|---|---|---|---|
| Engine starting | first 10 s offline | none (it connects by itself) | Starting WhyNot Cut… | جارٍ تشغيل WhyNot Cut… |
| Engine off | after 10 s | Start engine | WhyNot Cut isn't running. (`offline.no_engine`) | محرّك WhyNot Cut لا يعمل. (`offline.no_engine`) |
| Premiere not linked | host offline | Try again | `notice.code.no_route` | `notice.code.no_route` |
| Restart once | CEP installed, no heartbeat 60 s after start (eco §3.4) | Check again | Restart Premiere once to finish installing. | أعد تشغيل Premiere مرة واحدة لإكمال التثبيت. |
| Stale panel | `update.panel = stale` | Check again | WhyNot Cut was updated. Restart Premiere to load it. | تم تحديث WhyNot Cut. أعد تشغيل Premiere لتحميله. |
| Update staged | pending update, host open | none | Update ready. It installs the next time Premiere is closed. | التحديث جاهز، وسيُثبَّت عند إغلاق Premiere في المرة القادمة. |
| Engine older | `update.panel = newer` | Update | The engine is older than this panel. Update WhyNot Cut. | المحرّك أقدم من هذه اللوحة. حدّث WhyNot Cut. |
| Claude not installed | `not_installed` | Open guide | Claude isn't installed on this computer. | Claude غير مثبّت على هذا الكمبيوتر. |
| Claude signed out | `signed_out` | Open Claude | Sign in to Claude to continue. | سجّل الدخول إلى Claude لتتابع. |
| Claude plugin old | `plugin_outdated` | Update | Claude has an older WhyNot Cut ({version}). | لدى Claude إصدار أقدم من WhyNot Cut ({version}). |
| Claude working | `working` | none | Claude is working on {item} · {ago} ago. | يعمل Claude على {item} منذ {ago}. |
| Claude waiting | `waiting` | Open Needs you | Claude is waiting for you. | Claude بانتظار قرارك. |
| Claude ready | `ready` | none (no card; pill only) | n/a | n/a |

NEW keys: `status.engine.starting`, `status.host.restart_once`, `update.stale`, `update.staged`, `update.newer`, `claude.not_installed`, `claude.signed_out`, `claude.plugin_old`, `claude.working`, `claude.waiting`; buttons `action.check_again` (Check again / تحقق مرة أخرى), `action.open_guide` (Open guide / افتح الدليل), `action.open_claude` (Open Claude / افتح Claude), `action.update` (Update / تحديث), `action.open_needs` (Open Needs you / افتح «مطلوب منك»).

States: normal (the table), loading (probe pending: "Checking…" `status.pending`), success (a card turns into the ok notice for 3 s, then leaves), offline (the engine card hides the rest). Empty: not applicable.

### P-03. Home

| | |
|---|---|
| Purpose | Three big verbs and three tool cards; each shows its one-line purpose and its last result |
| Data | `PS.client`, `PS.item`, `PS.pipeline` (to choose the next verb), `PS.approval` (is one waiting), NEW `home.last {drop, edit, approve, tidy, hush, kalam}` (last result text + time), NEW `needs_you` count |
| Primary | The next verb only: Approve if an approval waits; else Make my edit if new footage exists; else Drop files. The other two are glass (B4.2 allows one primary) |
| Secondary | The other two verbs; Tidy / Hush / Kalam cards (open P-13 on that tool); rows "Models" (P-21) and "Settings" (P-22); Copy diagnostics |
| Existing keys | `tab.home`, `status.noclient`, `approval.approve`, `section.*` |
| Rule | B4.1, B4.2, B4.5, A6b (names) |

| State | What the editor sees |
|---|---|
| Empty | No client: `empty.noclient.*` and P-04 |
| Loading | Skeleton cards |
| Normal | Verb row + tool cards + "last result" lines |
| Error | A notice above the verbs; verbs disabled |
| Offline | Engine card (P-02); verbs disabled; tool cards show the last known result |
| Stale | Update card on top |
| Success | A "last result" line turns green for a new result ("Edit C0239 is ready to approve") |

| NEW key | EN | AR |
|---|---|---|
| `home.drop` | Drop files | أضف ملفاتك |
| `home.drop.sub` | Put raw footage in the client folder. | ضع الفيديو الخام في مجلد العميل. |
| `home.edit` | Make my edit | ابدأ المونتاج |
| `home.edit.sub` | Claude cuts, plans and builds the sequence. | يقصّ Claude ويخطّط ويبني التسلسل (Sequence). |
| `home.approve` | Approve | وافق |
| `home.approve.sub` | Check the plan, then say go. | راجع الخطة ثم أعطِ الموافقة. |
| `home.tool.tidy` | Tidy · Organise | تايدي · ترتيب المشروع |
| `home.tool.hush` | Hush · Cut silences | هَش · قصّ السكتات |
| `home.tool.kalam` | Kalam · Captions | كلام · الترجمة النصية (Captions) |
| `home.last` | Last: {text} · {ago} | آخر نتيجة: {text} · منذ {ago} |
| `home.last.none` | Nothing yet. | لا شيء بعد. |
| `home.models` | Models | النماذج (Models) |
| `home.settings` | Settings | الإعدادات |

### P-04. Client and clip picker

| | |
|---|---|
| Purpose | Choose or create the client folder, then the clip (item) to work on |
| Data | `PS.client`, `PS.item`; NEW `clients[] {name, path, items, last_at, ok}` and `items[] {id, status}` (the state has only the current pair) |
| Primary | Choose client folder (empty state); in a populated list, tapping a row is the action and "New client" is secondary |
| Secondary | New client (opens Claude on the new-client skill), Open folder, Back |
| Existing keys | `empty.noclient.title`, `.text`, `.action`, `status.noclient` |
| Rule | B4.5, B4.7, E1 ("client picker") |

| State | What the editor sees |
|---|---|
| Empty | `empty.noclient.*` with one button |
| Loading | Skeleton rows |
| Normal | Client rows (name, path in LTR, item count, last activity), then the clip list of the chosen client |
| Error | "This folder is not a client folder." + Choose another folder |
| Offline | Last known list, rows disabled, engine card on top |
| Success | The chosen client appears in the header and the picker closes |
| Stale | Not applicable |

| NEW key | EN | AR |
|---|---|---|
| `client.title` | Your clients | عملاؤك |
| `client.item_title` | Pick a clip | اختر المقطع |
| `client.new` | New client | عميل جديد |
| `client.items` | {n} clips | عدد المقاطع: {n} |
| `client.bad_folder` | This folder is not a client folder. It needs `assets` and `data` inside. | هذا المجلد ليس مجلد عميل. يجب أن يحتوي على المجلدين `assets` و `data`. |
| `client.pick_other` | Choose another folder | اختر مجلدًا آخر |

### P-05. New footage and Make my edit

| | |
|---|---|
| Purpose | Verbs 1 and 2: see where to put footage and what is new, then hand the edit to Claude |
| Data | NEW `intake {folder, clips[{name, duration_s, state new/in_progress/edited}], warnings[]}`; warnings are the early checks (missing logo, brand colours, fonts, episode sheet; T4.8). `PS.connection.claude` decides what Make my edit does |
| Primary | Make my edit (several new clips: "Edit the new videos") |
| Secondary | Open folder (through the engine, no Adobe consent dialog, F17), Check again, Back |
| Existing keys | `actions.reveal`, `notice.missing` |
| Rule | B4.1, C1.5 (intents are written as evidence, not typed in chat), eco §3.5b (multi-step work is not headless: the panel writes a request; a live session hears it, otherwise Open Claude), T4.8 |

| State | What the editor sees |
|---|---|
| Empty | "No new footage yet" + the folder path + Open folder |
| Loading | Skeleton rows |
| Normal | Clip rows with state chips; warnings as amber rows each with its one fix |
| Error | "That did not work." + Try again (`notice.failed`) |
| Offline | Make my edit disabled; engine card |
| Stale | Update card |
| Success, live session | "Claude got it and started." The panel moves to P-06 |
| Success, no live session | "Claude will pick this up when you open it." + Open Claude |
| Blocked | Claude not installed or signed out: Make my edit disabled and the matching P-02 card sits above it |

| NEW key | EN | AR |
|---|---|---|
| `intake.title` | Footage | الفيديو الخام |
| `intake.empty` | No new footage yet. Put your files in this folder. | لا يوجد فيديو جديد بعد. ضع ملفاتك في هذا المجلد. |
| `intake.state.new` | New | جديد |
| `intake.state.in_progress` | In progress | قيد العمل |
| `intake.state.edited` | Edited | تم مونتاجه |
| `intake.all` | Edit the new videos | مونتاج الفيديوهات الجديدة |
| `intake.sent_live` | Claude got it and started. | استلم Claude الطلب وبدأ العمل. |
| `intake.sent_later` | Claude will pick this up when you open it. | سيتابع Claude هذا الطلب عندما تفتحه. |
| `intake.warn.logo` | The client's logo is missing. | شعار العميل غير موجود. |
| `intake.warn.fonts` | The client's fonts are missing. | خطوط العميل غير موجودة. |

### P-06. Pipeline progress (+ done)

| | |
|---|---|
| Purpose | Readable progress: the step strip, the current step's bar with elapsed time and Cancel, plain-language status; the finished state with the handoff summary |
| Data | `PS.pipeline[]` (`id` transcript / plan / approve / build / frames / qc / handoff; `state` done / running / waiting / pending / failed; `progress {n, of, step}`; `elapsed_s`; `request_id`), `PS.connection.claude`, `PS.log` |
| Primary | Approve when the current step is `waiting` at `approve`; Open project when everything is done; no primary while a step runs (Cancel is secondary) |
| Secondary | Cancel (the running request), Copy diagnostics, Open log |
| Existing keys | `section.pipeline`, `step.*`, `step.state.*`, `pipeline.progress`, `pipeline.elapsed`, `pipeline.cancel`, `pipeline.idle`, `progress.building`, `step.aria` |
| Rule | B4.3, C1.6 (Claude pill working / waiting) |

| State | What the editor sees |
|---|---|
| Empty | "Nothing is running." (`pipeline.idle`) + the Make my edit button (P-05) |
| Loading | Strip skeleton |
| Normal, running | Strip with the current dot; "Building your sequence… 23 of 47" with bar, elapsed, Cancel |
| Waiting | The step "waiting for you" in amber and a link to P-07 |
| Error, failed | The failed dot, an error card with the cause in one line and Try again |
| Offline | Strip stays, Cancel disabled, engine card |
| Stale | Update card |
| Success, done | All seven dots done; the handoff card (below) |

The done card follows the lead's report format: **Verified** (what was proven), **Not verified**, **Needs you**, each as a short list with icons. It has Open project (primary), Reveal folder and Copy diagnostics (secondary). A sequence that did not pass QC never shows "done".

| NEW key | EN | AR |
|---|---|---|
| `pipeline.done.title` | Ready for the human editor | جاهز للمحرّر |
| `pipeline.done.verified` | Verified | تم التحقق |
| `pipeline.done.not_verified` | Not verified | لم يتم التحقق |
| `pipeline.done.needs_you` | Needs you | مطلوب منك |
| `pipeline.failed` | This step did not finish. | لم تكتمل هذه الخطوة. |
| `pipeline.waiting_link` | Review and approve | راجع ووافق |

### P-07. Approval (+ flagged lines, request changes)

| | |
|---|---|
| Purpose | The editor approves the plan with their name and the plan's fingerprint, or asks for changes |
| Data | `PS.approval {summary, preview_mp4, flagged[{kind medical/religious, text, tc}], fingerprint}`, `PS.editor_name`, `PS.item` |
| Primary | Approve (disabled until a name exists, while offline, while a command runs) |
| Secondary | Watch preview (opens in the Source Monitor, disabled when `preview_mp4` is null), Request changes (with a text box), flagged lines expand |
| Existing keys | `section.approval`, `approval.*` (empty, summary, preview, flagged, flagged.medical, flagged.religious, editor, editor.placeholder, approve, changes, changes.label, changes.placeholder), `notice.approved`, `notice.changes`, `notice.plan_changed`, `notice.need_name`, `notice.need_changes`, `text.held` |
| Rule | B4.2, B4.6, C1.5 (approve writes `plan-approval.json {by: editor, via: panel, fingerprint}`), T1.4 |

| State | What the editor sees |
|---|---|
| Empty | "Nothing is waiting for your approval." |
| Loading | Skeleton summary |
| Normal | Summary, preview button, flagged list, name field (only when `editor_name` is empty), Approve, change box + Request changes |
| Flagged expanded | Full list: kind chip (Medical / Religious), the statement as said, timecode in LTR |
| Error | "That did not work." + Try again (replays the same Approve while the plan is the same one) |
| Offline | Both buttons disabled; engine card |
| Stale | The plan changed after the editor opened it: "The plan changed. Review it and approve again." (info note, the card reloads) |
| Success approve, live session | "Approved. The build can start." + "Claude continues now." |
| Success approve, no live session | "Approved." + "Claude will pick this up when you open it." + Open Claude |
| Success changes | "Your changes were sent." |

| NEW key | EN | AR |
|---|---|---|
| `approval.claude_continues` | Claude continues now. | يتابع Claude العمل الآن. |
| `approval.claude_later` | Claude will pick this up when you open it. | سيتابع Claude هذه الخطوة عندما تفتحه. |
| `approval.flagged.hint` | Ask the speaker or the doctor to confirm these lines. | اطلب من المتحدث أو الطبيب تأكيد هذه العبارات. |
| `approval.fingerprint` | Plan {id} | الخطة {id} |

### P-08. QC frames grid

| | |
|---|---|
| Purpose | See the rendered frames and their verdicts; tap one to move the playhead |
| Data | `PS.qc[] {t_s, tc, file, label, verdict pass / fail / pending / media_pending, w, h, thumb}`; tile follows the frame's aspect (9:16 default, 4:5) |
| Primary | Re-export (only on a pending tile); a tap on a tile is the main gesture |
| Secondary | Export frames (P-09) |
| Existing keys | `section.qc`, `qc.*` (empty, pass, fail, pending, media_pending, reexport, hint), `frame.seek`, `notice.bad_frame` |
| Rule | B4 (all four verdicts with icon and text), B6 (no clipped text, no sideways scroll) |

| State | What the editor sees |
|---|---|
| Empty | "No frames yet. They appear after the build." |
| Loading | Skeleton tiles (2 columns at 280–360 px, 3 at 480 px) |
| Normal | Tiles with timecode, verdict icon and text, label |
| Error | A failed export: an error card + Try again |
| Offline | Tiles stay, tap-to-seek disabled |
| Stale | A tile whose file is gone: `notice.bad_frame` |
| Success | "All frames passed." (NEW) |

| NEW key | EN | AR |
|---|---|---|
| `qc.all_pass` | All frames passed. | نجحت جميع الإطارات. |
| `qc.fail_hint` | Request changes to fix a failed frame. | اطلب تعديلات لإصلاح الإطار الفاشل. |

### P-09. Actions and rebuild confirm

| | |
|---|---|
| Purpose | One-click actions on the current project; the safe rebuild |
| Data | `PS.context {project_path, sequence_name, folder, out_dir, review_mp4}` |
| Primary | Rebuild, inside the confirm dialog |
| Secondary | Open project, Export frames, Render review MP4, Reveal folder, Copy diagnostics |
| Existing keys | `section.actions`, `actions.*`, `rebuild.*`, `dialog.*`, `notice.missing`, `notice.copied`, `notice.opened` |
| Rule | B4.2 (what will change + the backup name + a confirm), master plan T6.5 item 5 |

| State | What the editor sees |
|---|---|
| Empty | Buttons disabled; "This needs a project that is not set yet." |
| Loading | A running action disables the rest (`working`) |
| Normal | Path in LTR, six buttons |
| Rebuild confirm | Warning card: "If you edited this project in Premiere since the last build, a rebuild replaces your edits", the backup name `name_prev_date-time.prproj` on its own row, Rebuild (primary) and "Keep my project" |
| Error | Notice with Try again |
| Offline | Everything except Reveal and Copy diagnostics disabled |
| Success | `notice.ok`, `notice.opened`, `notice.copied` |
| Stale | Not applicable |

### P-10. Needs you

| | |
|---|---|
| Purpose | The list of things only the editor can do; opens from the badge. Same list as `NEEDS-YOU.md` |
| Data | NEW `needs_you[] {id, kind, text, action, item}`. Kinds from T4.7 and the skills: confirm words by ear, medical or religious approval, music, fonts or logo missing, final mix or render, restart Premiere / After Effects, numbers to confirm |
| Primary | The first item's action |
| Secondary | Each item's own button (one per item), Reveal folder |
| Rule | B4.6, T4.7 ("the panel shows the same list") |

| State | What the editor sees |
|---|---|
| Empty, success | "Nothing needs you right now." with the ok icon |
| Loading | Skeleton rows |
| Normal | Rows: kind icon, one sentence, one button; grouped by client and item |
| Error | "The panel could not read the list." + Try again |
| Offline | Last list, buttons disabled |
| Stale | Not applicable |

| NEW key | EN | AR |
|---|---|---|
| `needs.title` | Needs you | مطلوب منك |
| `needs.empty` | Nothing needs you right now. | لا شيء مطلوب منك الآن. |
| `needs.kind.words` | Listen to these words and confirm them. | استمع إلى هذه الكلمات وأكّدها. |
| `needs.kind.claim` | A doctor or the speaker should approve these lines. | يجب أن يوافق الطبيب أو المتحدث على هذه العبارات. |
| `needs.kind.fonts` | Install the client's fonts. | ثبّت خطوط العميل. |
| `needs.kind.music` | Choose the music. | اختر الموسيقى. |
| `needs.kind.render` | Check the final mix and export. | راجع المزج النهائي ثم صدّر. |
| `needs.kind.restart` | Restart {app}. | أعد تشغيل {app}. |

### P-11. Error cards (catalogue)

One sheet that draws every error card once, at 300 and 360 px, in both languages. Each card is: icon, one sentence, optional "how", one button. The mockup shows the pattern; the table lists what each card says.

| Group | Triggers | Sentence (existing key) | Button | Source |
|---|---|---|---|---|
| Link: engine absent or lost | `no_engine`, `down`, `unreachable`, `bad_engine_json`, `auth`, `no_welcome`, `lost`, `stopped` | `offline.*` of the same name (+ `offline.retry` while it retries) | Start engine | `LINK_FIX` in `render.ts` |
| Link: engine refuses | `refused_host`, `refused_busy`, `refused`, `protocol`, `too_large`, `blocked` | `offline.*` | Copy diagnostics (+ `notice.send_diagnostics`) | `LINK_FIX` |
| Intent or command failed | `auth`, `origin`, `host`, `too_large`, `rate`, `schema`, `unknown_type`, `no_route`, `timeout`, `internal`, `not_yet` | `notice.code.*` | Try again (`rate`, `timeout`) or Copy diagnostics | `session.schema.json` error codes |
| Validation | plan changed, name missing, changes missing, frame gone, no project | `notice.plan_changed`, `.need_name`, `.need_changes`, `.bad_frame`, `.missing` | none (info note) | `render.ts` / `mount.ts` |
| Panel itself | render or snapshot failed | `error.render`, `error.snapshot` | Copy diagnostics | `renderError` |
| Engine text that held a command | any | `notice.failed` ("That did not work."), raw text only in the log | Copy diagnostics | `runtimeText()` |
| Claude | not installed, signed out, plugin old | NEW, see P-02 | Open guide / Open Claude / Update | C1.6 |
| Update | stale, restart once, engine older | NEW, see P-02 | Check again / Update | C1.8 |
| Tools | see P-14 to P-20 | NEW | one per card | A5 |

| NEW key | EN | AR |
|---|---|---|
| `err.title` | Something needs attention | هناك أمر يحتاج إلى انتباهك |
| `err.copy_done` | Diagnostics copied. Send them to support. | تم نسخ التشخيص. أرسله إلى الدعم. |

States: each card in normal; with and without the "how" line; the button disabled while a command runs (`working`); the dismissed card. A card with two buttons is a defect (a fix that equals the engine banner's fix is not repeated).

### P-12. AI action sheet

| | |
|---|---|
| Purpose | A closed list of one-shot text jobs the engine runs on the editor's own Claude: the panel shows the result, the editor presses Apply. The panel never runs Claude itself |
| Data | NEW `ai {backend: session / api_key / cli_optin / none, jobs[{id, state idle / running / ready / rejected / error, result_diff}]}`. Jobs named in C1.7: fix captions, suggest titles, summarise. eco §3.5b also names the Kalam correction (FR-6), title or hook suggestions and a publish-copy draft |
| Primary | Apply (when a result is ready); Run is the primary when idle |
| Secondary | Discard, Run again, Open Claude (backend 3, a deep link with the task filled in) |
| Rule | C1.7, C1.5, eco §3.8 (tool-less, applied only by an editor click), Kalam §8 (only text leaves the machine) |

| State | What the editor sees |
|---|---|
| Empty | Three job buttons, each with a one-line purpose |
| Loading | "Claude is working…" with a shimmer bar and Stop |
| Normal, ready | Before and after list, per line; Apply and Discard |
| Rejected | A line the faithfulness gate refused (Kalam FR-9): the source is kept and says so |
| Error | "That did not work." + Try again |
| Offline, blocked | `backend none`: buttons disabled, "AI buttons need Claude" + Open guide |
| Success | "Applied to {n} lines." with Undo |
| Stale | The text changed under the result: "The captions changed. Run it again." |

| NEW key | EN | AR |
|---|---|---|
| `ai.title` | Ask Claude | اسأل Claude |
| `ai.fix_captions` | Fix captions | تصحيح الترجمة النصية (Captions) |
| `ai.suggest_titles` | Suggest titles | اقتراح عناوين |
| `ai.summarise` | Summarise | تلخيص |
| `ai.privacy` | Only the text is sent to Claude. Audio and timing stay on this computer. | يُرسَل النص فقط إلى Claude. يبقى الصوت والتوقيت على هذا الكمبيوتر. |
| `ai.apply` | Apply | تطبيق |
| `ai.discard` | Discard | تجاهل |
| `ai.working` | Claude is working… | يعمل Claude الآن… |
| `ai.kept_source` | Kept your original line. | تم الإبقاء على سطرك الأصلي. |
| `ai.needs_claude` | AI buttons need Claude. | أزرار الذكاء الاصطناعي تحتاج إلى Claude. |
| `ai.applied` | Applied to {n} lines. | تم التطبيق على {n} من الأسطر. |
| `ai.stale` | The text changed. Run it again. | تغيّر النص. شغّل الأمر مرة أخرى. |

### P-13. Tools hub

| | |
|---|---|
| Purpose | The Tools tab: Tidy, Hush and Kalam as three cards, and the combined flow |
| Data | NEW `tools {sequence: name or null, tidy/hush/kalam: {last_result, last_at, ready}}`, `models` summary (is the Kalam pack ready) |
| Primary | Organise → Cut → Caption (A3.4: Tidy, then Hush, then Kalam; each step keeps its own preview, confirm, backup and undo) |
| Secondary | The three cards (open P-14, P-16, P-18), Models row |
| Existing keys | `tab.tools` |
| Rule | A3.4, A6b, B4.1, B4.9 |

| State | What the editor sees |
|---|---|
| Empty | No sequence or project open: "Open a project to use the tools." + Open project |
| Loading | Skeleton cards |
| Normal | Three cards with purpose, last result, a ready chip |
| Error | Notice + Try again |
| Offline | Cards visible, Start disabled, engine card |
| Stale | Update card |
| Success | A card's "last result" refreshes |
| Models busy | Kalam card: "Kalam pack downloading 42%" with the smaller model offered (D3) |

| NEW key | EN | AR |
|---|---|---|
| `tools.title` | Tools | الأدوات |
| `tools.flow` | Organise → Cut → Caption | رتّب ← اقطع ← ترجم |
| `tools.flow.sub` | Three steps. Each one shows its preview and asks first. | ثلاث خطوات. تعرض كل خطوة معاينتها وتسألك أولًا. |
| `tools.tidy.sub` | Clean and organise the project. Sync a podcast by sound. | نظّف المشروع ورتّبه. زامن البودكاست بالصوت. |
| `tools.hush.sub` | Cut silences and filler words. | احذف السكتات وكلمات التردد (Fillers). |
| `tools.kalam.sub` | Captions timed to the voice, as a track, a template or an SRT file. | ترجمة نصية متوافقة مع الصوت: مسار أو قالب أو ملف SRT. |
| `tools.need_sequence` | Open a project to use the tools. | افتح مشروعًا لتستخدم الأدوات. |
| `tools.model_busy` | Kalam pack downloading {pct}% | حزمة كلام قيد التنزيل {pct}% |

### P-14. Tidy: scan and plan

| | |
|---|---|
| Purpose | Scan the project, then show everything Tidy would do with a tick box on each item |
| Data (PRD) | Project card with a Reels / Podcast switch. Scan stats: items, total media size, to remove (count and size), share of the project size unused, count per type. Lists: to remove (grouped by reason, with sizes), to move (by target bin), nest names, old bins, duplicates in use, offline files. Opt-ins listed unticked: caption files; in Podcast mode camera footage, mics and any recording of 180 s or more. Options: remove ticked items, organise into bins (incl. nest names), colour by type. Fixed bins `01 Footage` … `09 Other` |
| Primary | Clean & organise (opens the confirm dialog) |
| Secondary | Scan, Reels / Podcast switch, per-section expand, Back |
| Rule | A0, B4.9, FR-1 to FR-18, B4.2 (the dialog states "saved, then copied as «(WhyNot Tidy backup YYYY-MM-DD HHMMSS)»") |

| State | What the editor sees |
|---|---|
| Empty | "Scan the project to see what Tidy can clean." + Scan |
| Loading | Scan progress (read-only) |
| Normal | Stats strip, sections with ticks and sizes |
| Error | A step failed: it is listed in "problems" and the rest continues |
| Offline | Scan disabled, engine card |
| Stale | "The project changed since the scan. Scan again." |
| Success | Moves to P-15 |

| NEW key | EN | AR |
|---|---|---|
| `tidy.title` | Tidy | تايدي |
| `tidy.mode.reels` | Reels | ريلز |
| `tidy.mode.podcast` | Podcast | بودكاست |
| `tidy.scan` | Scan the project | افحص المشروع |
| `tidy.stat.unused` | {size} unused ({pct}% of the project) | {size} غير مستخدم ({pct}% من المشروع) |
| `tidy.sec.remove` | To remove from the project | سيُحذف من المشروع |
| `tidy.sec.remove_note` | Only from the project. Your files stay on disk. | من المشروع فقط. تبقى ملفاتك على القرص. |
| `tidy.sec.move` | To move into bins | سيُنقل إلى المجلدات (Bins) |
| `tidy.sec.nests` | New nest names | أسماء التسلسلات المتداخلة (Nests) |
| `tidy.sec.offline` | Offline files (report only) | ملفات غير متصلة (للإبلاغ فقط) |
| `tidy.optin` | Not ticked by default | غير محددة افتراضيًا |
| `tidy.apply` | Clean & organise | نظّف ورتّب |
| `tidy.confirm.backup` | The project is saved, then copied as: | يُحفظ المشروع ثم يُنسخ باسم: |

### P-15. Tidy: report, undo and podcast sync

| | |
|---|---|
| Purpose | Show what Tidy did and how to go back; in Podcast mode build one synced multicam sequence |
| Data | Apply report `{moved, removed, skipped, binsRemoved, colored, renamed, problems[]}`; backup path; sync: per-clip progress, `placed`, skipped clips with their names and why (confidence below 3), new sequence "<project> - Synced" |
| Primary | Open the pre-clean copy (undo), or in Podcast mode "Sync the podcast by sound" |
| Secondary | Reveal folder, Copy diagnostics, Done |
| Rule | A0, FR-15 (undo = open the backup), FR-19 to FR-23, A3.7 (numbered second sync, temp sequences removed, the skip reason shown) |

| State | What the editor sees |
|---|---|
| Empty | Not applicable |
| Loading | Applying; or sync per-clip progress "Clip 3 of 8" with Stop |
| Normal, report | Counts, problems list, backup name |
| Error | A clip failed to export: it is left out and named; the rest continues |
| Offline | Undo stays (it opens a file); Sync disabled |
| Stale | Not applicable |
| Success | "Project organised. The old copy is kept." or "Synced sequence ready." |

| NEW key | EN | AR |
|---|---|---|
| `tidy.report.title` | Project organised | تم ترتيب المشروع |
| `tidy.report.counts` | Moved {moved} · removed {removed} · renamed {renamed} | نُقل {moved} · حُذف {removed} · أُعيدت تسمية {renamed} |
| `tidy.report.undo` | Open the pre-clean copy | افتح النسخة السابقة للتنظيف |
| `tidy.sync` | Sync the podcast by sound | زامن البودكاست بالصوت |
| `tidy.sync.progress` | Matching clip {n} of {of} | مطابقة المقطع {n} من {of} |
| `tidy.sync.skipped` | Left out: {name} (no clear match) | استُبعد: {name} (لا توجد مطابقة واضحة) |
| `tidy.sync.done` | Synced sequence ready: {name} | التسلسل المتزامن جاهز: {name} |

### P-16. Hush: scan and preview

| | |
|---|---|
| Purpose | Choose the target, scan, tune how strong the cut is, check the waveform, cut or only mark |
| Data (PRD) | Target label ("3 clips", "In/Out", "Whole sequence"); track chips (V1…, A1…; tracks with clips and not locked are ticked; a warning for tracks that will not move). Scan builds the 10 ms envelope. Simple tab: intensity 0–100 with Soft 25, Medium 50, Strong 80, and Tight on. Advanced: threshold (dB), min silence (s), pad before and after (s, linkable). Fillers: toggle, language auto / en / ar, Strong list (ticked) and Soft list (unticked), each a row with a tick and a play button; optional unclear sounds. Waveform with silence and filler cuts in two colours, hover tooltip, click moves the playhead. Summary: before, after, saved, "N silences + M fillers", the numbers in force. Mode Cut or Markers; Backup on by default; presets |
| Primary | Cut (the destructive primary, opens the confirm dialog that names the backup `(WhyNot Hush backup HH:MM:SS)`); in Markers mode the primary is "Add markers" |
| Secondary | Scan, Simple / Advanced, Cut / Markers, Save preset, Stop, Remove all markers |
| Rule | A0, B4.9, FR-1 to FR-22, PRD §8 (never cut into speech, backup before cutting, locked track aborts) |

| State | What the editor sees |
|---|---|
| Empty | "Scan a range to see the silences." + Scan; waveform placeholder `wave.placeholder` |
| Loading | Progress with stage text ("Exporting audio…", "Finding filler words…") and Stop |
| Normal | Chips, controls, waveform, summary |
| Error, locked track | "A ticked track is locked. Nothing was cut." + one fix |
| Offline | Fillers need the engine (Whisper): the filler section disables, silence cutting still works |
| Stale | "The sequence changed since the scan. Scan again." |
| Success | Moves to P-17 |

| NEW key | EN | AR |
|---|---|---|
| `hush.title` | Hush | هَش |
| `hush.target` | Target: {label} | الهدف: {label} |
| `hush.scan` | Scan | افحص |
| `hush.intensity` | Strength | القوة |
| `hush.soft` | Soft | خفيفة |
| `hush.medium` | Medium | متوسطة |
| `hush.strong` | Strong | قوية |
| `hush.tight` | Tight (no padding) | مضبوط (بلا هامش) |
| `hush.fillers` | Filler words | كلمات التردد (Fillers) |
| `hush.summary` | Before {a} · after {b} · saved {c} | قبل {a} · بعد {b} · الموفَّر {c} |
| `hush.counts` | {s} silences + {f} fillers | {s} سكتة + {f} كلمة تردد |
| `hush.mode.cut` | Cut | قصّ |
| `hush.mode.markers` | Markers only | علامات فقط |
| `hush.go` | Cut | قصّ |
| `hush.markers.go` | Add markers | أضف علامات |
| `hush.track_locked` | A ticked track is locked. Nothing was cut. | أحد المسارات المحددة مقفل. لم يُقصّ شيء. |
| `hush.not_moving` | These tracks will not move: {tracks} | هذه المسارات لن تتحرك: {tracks} |

### P-17. Hush: result and undo

| | |
|---|---|
| Purpose | Say what was cut and give the one-click way back |
| Data | `{removed, cuts, backup {id, name}, sequence, linked}` or `{added}` for markers |
| Primary | Undo (the backup sequence becomes the open one under the original name; the cut version is kept as «(WhyNot Hush cut HH:MM:SS)») |
| Secondary | Clear markers, Reveal, Done |
| Rule | FR-19 to FR-23, B4.2, A0 |

| State | What the editor sees |
|---|---|
| Normal, success | "Cut {n} pieces. Saved {time}. Your original is kept as «name»." |
| Error | Partial failure listed |
| Offline | Undo still works (a host operation, not the engine) |
| Stale, loading, empty | Not applicable |

| NEW key | EN | AR |
|---|---|---|
| `hush.result` | Cut {n} pieces. Saved {time}. | قُصَّت {n} من القطع. تم توفير {time}. |
| `hush.result.backup` | Your original is kept as: | تم الاحتفاظ بنسختك الأصلية باسم: |
| `hush.undo` | Undo | تراجع |
| `hush.markers.added` | Added {n} markers. | أُضيفت {n} من العلامات (Markers). |

### P-18. Kalam: setup

| | |
|---|---|
| Purpose | Set the language, range and output, then start |
| Data (PRD) | Mode: Arabic (default), English, Other. Range 2 × 2: In/Out, whole sequence, from the playhead, selected clips; audio chips (only ticked tracks are exported). Output: Captions track, MOGRT, SRT only; MOGRT shows the chosen template card (thumbnail, video track select, text-field select). Caption settings: max characters per line (32), max lines (2; the client uses 1), max seconds (4.5), min pause (0.22). Correction: toggle, backend, rules, glossary. Client-aware defaults (A3.5): the client's glossary and rules start filled. Model state (pack downloading, or ready) |
| Primary | Start |
| Secondary | Choose template (P-19), Correction rules, Glossary, Back |
| Rule | A0, B4.9, FR-1 to FR-16, FR-24, A3.5 |

| State | What the editor sees |
|---|---|
| Empty | No sequence open: "Open a sequence first." Range errors from FR-2: no In/Out, nothing selected, playhead at the end |
| Loading | Reading sequence info |
| Normal | Cards in the PRD order |
| Error | "No In/Out is set." / "Select a clip first." with the one fix |
| Offline | Start disabled; engine card |
| Stale | Not applicable |
| Success | Moves to P-20 |
| Model busy | "Kalam pack downloading 42%. Start with the smaller model now?" |
| Correction unavailable | Claude missing: "Captions will be made without correction." (FR-6) |

| NEW key | EN | AR |
|---|---|---|
| `kalam.title` | Kalam | كلام |
| `kalam.mode` | Language | اللغة |
| `kalam.mode.ar` | Arabic | العربية |
| `kalam.mode.en` | English | الإنجليزية |
| `kalam.mode.other` | Other | أخرى |
| `kalam.range` | Range | النطاق |
| `kalam.range.inout` | In / Out | من البداية إلى النهاية (In/Out) |
| `kalam.range.sequence` | Whole sequence | التسلسل كاملًا |
| `kalam.range.playhead` | From the playhead | من مؤشر التشغيل |
| `kalam.range.selection` | Selected clips | المقاطع المحددة |
| `kalam.audio` | Audio tracks | المسارات الصوتية |
| `kalam.output` | Output | المخرجات |
| `kalam.output.track` | Captions track | مسار ترجمة نصية |
| `kalam.output.mogrt` | MOGRT template | قالب MOGRT |
| `kalam.output.srt` | SRT file only | ملف SRT فقط |
| `kalam.settings` | Caption settings | إعدادات الترجمة النصية |
| `kalam.correct` | Correct the text with Claude | صحّح النص باستخدام Claude |
| `kalam.start` | Start | ابدأ |
| `kalam.err.no_inout` | No In/Out is set. | لم تُحدَّد نقطتا البداية والنهاية (In/Out). |
| `kalam.err.no_selection` | Select a clip first. | حدّد مقطعًا أولًا. |
| `kalam.err.playhead_end` | The playhead is at the end. | مؤشر التشغيل عند النهاية. |
| `kalam.no_correction` | Claude is not available. Captions will be made without correction. | Claude غير متاح. ستُنشأ الترجمة النصية بدون تصحيح. |

### P-19. Kalam: MOGRT gallery

| | |
|---|---|
| Purpose | Pick the caption template visually |
| Data (PRD FR-19) | Every `.mogrt` in Premiere's Local Templates folder: thumbnail, name, folder; search by name; filter by top folder; the template's own text controls; "From a file…" |
| Primary | Use this template |
| Secondary | Search, folder filter, From a file…, Back |
| Rule | FR-18, FR-19, B4.9 |

| State | What the editor sees |
|---|---|
| Empty | "No templates found." + From a file… |
| Loading | Skeleton thumbnails (thumbnails are cached by path and mtime) |
| Normal | Grid of cards |
| Error | "This template has no editable text." (all-or-nothing, FR-18) |
| Selected | Highlight ring; text-field select appears |
| Offline, stale, success | Offline: not applicable (a local read). Stale: the folder changed, refresh. Success: back to P-18 with the card filled |

| NEW key | EN | AR |
|---|---|---|
| `kalam.gallery.search` | Search templates | ابحث في القوالب |
| `kalam.gallery.all` | All folders | كل المجلدات |
| `kalam.gallery.file` | From a file… | من ملف… |
| `kalam.gallery.use` | Use this template | استخدم هذا القالب |
| `kalam.gallery.empty` | No templates found. | لم يُعثر على قوالب. |
| `kalam.gallery.no_text` | This template has no editable text. | هذا القالب لا يحتوي على نص قابل للتعديل. |

### P-20. Kalam: progress and results

| | |
|---|---|
| Purpose | Show the stages, then the caption list |
| Data (PRD) | Stages: loading, transcribing, aligning (with the device), correcting, captions, done or error; Stop. Results: every caption with its time; a click moves the playhead; Undo for MOGRT (removes the clips placed in the range); the captions track is removed by the user (Premiere has no API); SRT path (always written) |
| Primary | Stop while running; no primary when done (the list is the result) |
| Secondary | Undo (MOGRT), Reveal SRT, AI: Fix captions (P-12), Done |
| Rule | FR-17, FR-18, FR-21 to FR-23, A3.10, B4.3 |

| State | What the editor sees |
|---|---|
| Loading | Stage list with the current stage, device, elapsed time |
| Normal, results | Caption rows: time (LTR), text |
| Error | Stage that failed + Try again |
| Offline | Engine lost mid-run: "The connection was lost" + Try again |
| Success | "{n} captions placed." + SRT path |
| Empty, stale | Not applicable |

| NEW key | EN | AR |
|---|---|---|
| `kalam.stage.loading` | Loading the model | تحميل النموذج |
| `kalam.stage.transcribing` | Listening | الاستماع |
| `kalam.stage.aligning` | Timing each word ({device}) | ضبط توقيت كل كلمة ({device}) |
| `kalam.stage.correcting` | Correcting the text | تصحيح النص |
| `kalam.stage.captions` | Building captions | بناء الترجمة النصية |
| `kalam.done` | {n} captions placed. | وُضعت {n} من الترجمات النصية. |
| `kalam.srt` | SRT file saved: | تم حفظ ملف SRT: |
| `kalam.track_note` | To remove a captions track, delete it in Premiere. | لإزالة مسار الترجمة النصية، احذفه من Premiere. |

### P-21. Models

| | |
|---|---|
| Purpose | See every model and pack, its state and size, and install or remove it |
| Data | NEW `models[] {id, title, used_for, state installed / downloading / available / skipped, pct, eta_min, size_bytes}`. Packs from D3 / ID-13: core (Whisper large-v3), fast (large-v3-turbo), small (medium, small; available on demand), Kalam pack (Egyptian turbo, Parakeet, MMS-300m, torch), fonts |
| Primary | Download all (when anything is missing); no primary when all are installed |
| Secondary | Install, Remove (with a confirm), Use the smaller model now |
| Rule | D3, D-T3, D-T4, E1 ("models page") |

| State | What the editor sees |
|---|---|
| Empty | Engine offline and nothing cached: "Start the engine to see your models." + Start engine |
| Loading | Skeleton rows |
| Normal | Rows with a state chip, size, used-for |
| Downloading | Bar with "{pct}% · {eta} min left" |
| Error | "The download stopped. It resumes where it left off." + Try again |
| Offline | Last known states, buttons disabled |
| Skipped (disk) | "Skipped: not enough space. Add it later." |
| Success | "All models are ready." |
| Stale | Not applicable |

| NEW key | EN | AR |
|---|---|---|
| `models.title` | Models | النماذج (Models) |
| `models.sub` | Speech models run on this computer. | تعمل نماذج الكلام على هذا الكمبيوتر. |
| `models.state.installed` | Installed | مثبّت |
| `models.state.downloading` | Downloading {pct}% | قيد التنزيل {pct}% |
| `models.state.available` | Available | متاح |
| `models.state.skipped` | Skipped: not enough space | تم تخطيه: المساحة غير كافية |
| `models.eta` | {n} min left | متبقٍّ {n} دقيقة |
| `models.download_all` | Download all | نزّل الكل |
| `models.install` | Install | تثبيت |
| `models.remove` | Remove | إزالة |
| `models.use_smaller` | Use the smaller model now | استخدم النموذج الأصغر الآن |
| `models.core` | Speech recognition (best accuracy) | التعرّف على الكلام (أعلى دقة) |
| `models.fast` | Fast recognition | تعرّف سريع |
| `models.small` | Small models | نماذج صغيرة |
| `models.kalam` | Kalam pack (Arabic captions) | حزمة كلام (ترجمة نصية عربية) |
| `models.all_ready` | All models are ready. | جميع النماذج جاهزة. |

### P-22. Settings

| | |
|---|---|
| Purpose | The few things an editor may change; nothing technical |
| Data | NEW `settings {editor_name, language, clients_root, login_item: bool, ai_backend: session / api_key / cli_optin, version, build}` |
| Sections | Your name (for approvals, `PS.editor_name`) · Language · Clients folder (path in LTR + Change) · Engine always on (the login item, on by default, visible in Startup apps) · Claude and AI (which backend; an API-key field stored in an owner-only file and never shown again; the subscription CLI backend is opt-in and off by default, H14) · Tool defaults (link to P-14, P-16, P-18) · About (WhyNot Cut 3.0.0, Copy diagnostics, Open guide) |
| Primary | None (each control saves at once and says so) |
| Rule | B3 (language remembered per editor), C1.7 (H14), E2.1#4 (the login item can be turned off), C1.10 (one version) |

| State | What the editor sees |
|---|---|
| Loading | Skeleton rows |
| Normal | The sections above |
| Error | A control that failed shows a notice + Try again |
| Offline | Engine-backed rows disabled; language and name still work |
| Success | "Saved." per control |
| Empty, stale | Not applicable |

| NEW key | EN | AR |
|---|---|---|
| `settings.title` | Settings | الإعدادات |
| `settings.name` | Your name | اسمك |
| `settings.name_hint` | Used on your approvals. | يُستخدم في موافقاتك. |
| `settings.clients` | Clients folder | مجلد العملاء |
| `settings.change` | Change | تغيير |
| `settings.engine` | Start WhyNot Cut when I sign in to Windows | شغّل WhyNot Cut عند تسجيل الدخول إلى الجهاز |
| `settings.engine_hint` | Keeps the panel connected. You can turn it off any time. | يُبقي اللوحة متصلة. يمكنك إيقافه في أي وقت. |
| `settings.ai` | Claude and AI buttons | Claude وأزرار الذكاء الاصطناعي |
| `settings.ai.session` | Use my open Claude session | استخدم جلسة Claude المفتوحة |
| `settings.ai.key` | Use my Anthropic API key | استخدم مفتاح Anthropic الخاص بي |
| `settings.ai.cli` | Use my Claude sign-in (off by default) | استخدم تسجيل دخولي إلى Claude (متوقف افتراضيًا) |
| `settings.saved` | Saved. | تم الحفظ. |
| `settings.about` | WhyNot Cut {version} | WhyNot Cut {version} |

## 4. After Effects CEP screens

The AE panel is the CEP panel "WhyNot Cut" (After Effects only; Premiere has the UXP panel). It uses the same kit, the same header, notice, dialog, log drawer, Needs-you badge, language switch and footer, and the checklist of P-01 and the status cards of P-02 with "After Effects" as the host. Size: default 340 × 640, minimum 280 × 320 (CEP manifest). A hidden CEP daemon in both hosts is not a screen.

### A-01. After Effects home and motion pipeline

| | |
|---|---|
| Purpose | See the motion projects of the current episode and the state of the selected one |
| Data | The panel's pipeline strip keeps the seven ids (`transcript`, `plan`, `approve`, `build`, `frames`, `qc`, `handoff`); motion mode maps them: Audio (audio-clean), Script (script, plan, claims review, animatic), Approve, Build (Arabic probe + build + read-back), Render and frames, QC, Handoff. NEW `motion {projects[{id "<EP>_<ID>_MO", status}], build_status PROJECT_ASSEMBLED / BUILT_UNVERIFIED / FAILED / REFUSED / SCRIPT_ONLY, render_status RENDERED / FAILED}` |
| Primary | Start the build (when the plan is approved and the gates in A-03 are green); otherwise the card that blocks it |
| Secondary | Open project (.aep), Reveal folder, Copy diagnostics |
| Rule | C1.3 (one visible panel per app), B-T4, master plan T6.8, motion SKILL §2 |

| State | What the editor sees |
|---|---|
| Empty | "No motion video yet. Pick a part of an episode in Claude." + Open Claude |
| Loading | Skeleton strip |
| Normal | Project selector (id in LTR), the strip, the current step |
| Error | The failed step with its reason and Try again |
| Offline | Engine card; "After Effects is not linked" card |
| Stale | The panel update card (P-02) |
| Success | Strip done; A-04 |

| NEW key | EN | AR |
|---|---|---|
| `ae.step.transcript` | Audio | الصوت |
| `ae.step.plan` | Script and plan | النص والخطة |
| `ae.step.build` | Build in After Effects | البناء في After Effects |
| `ae.step.frames` | Render and frames | التصيير (Render) والإطارات |
| `ae.empty.title` | No motion video yet | لا يوجد فيديو موشن بعد |
| `ae.empty.text` | Pick a part of an episode in Claude and it appears here. | اختر جزءًا من حلقة في Claude فيظهر هنا. |
| `ae.status.assembled` | Built and checked | تم البناء والتحقق |
| `ae.status.unverified` | Built, not checked | تم البناء دون تحقق |

### A-02. Motion plan approval

| | |
|---|---|
| Purpose | Approve the motion plan only after the claims review of the current plan exists |
| Data | From `motion-plan.md`: each scene's time, beat, type and on-screen words; editorial lines marked as Claude's words (not the speaker's); the medical-reviewer's approval list; numbers to confirm; icons or illustrations with their licences; music; recipe deviations; the animatic MP4 and storyboard. Fingerprint as in P-07 |
| Primary | Approve (disabled with the reason "Waiting for the claims review" until the review of this plan exists) |
| Secondary | Watch the animatic, Request changes (text box) |
| Rule | motion SKILL §3 (approval only from the editor, never before the claims review; a new plan needs a new review; editorial lines marked), non-negotiables (numbers only as said, names only from the sheet, licensed assets only) |

| State | What the editor sees |
|---|---|
| Empty | "No plan is waiting." |
| Loading | Skeleton scenes |
| Normal | Scene list; Claude's lines in a labelled chip; numbers with an "Confirm" mark |
| Blocked | Approve disabled: the claims review is missing |
| Error | Notice + Try again |
| Offline | Buttons disabled |
| Stale | "The plan changed. Review it and approve again." |
| Success | "Approved. The build can start." |

| NEW key | EN | AR |
|---|---|---|
| `ae.plan.scenes` | Scenes | المشاهد |
| `ae.plan.claude_line` | Claude's words, not the speaker's | من كلمات Claude وليست من كلام المتحدث |
| `ae.plan.numbers` | Confirm these numbers | أكّد هذه الأرقام |
| `ae.plan.music` | Music | الموسيقى |
| `ae.plan.animatic` | Watch the animatic | شاهد النسخة التجريبية (Animatic) |
| `ae.plan.blocked` | Waiting for the claims review of this plan. | بانتظار مراجعة الادعاءات لهذه الخطة. |

### A-03. After Effects gates and Needs-you cards

| | |
|---|---|
| Purpose | The reasons a build cannot start, each as one card with one button |
| Data | `motion-build` refusals: no ok Arabic probe for this After Effects version (once per version; Claude runs and records it), brand fonts not installed, After Effects holds unsaved work, the `.aep` was edited by the editor since the last build, no bridge or After Effects (script-only: built but not verified, QC cannot pass) |
| Primary | The card's one button |
| Rule | motion SKILL §4, C1.4, B4.4 |

| Card | Button | EN | AR |
|---|---|---|---|
| Probe pending | none (Claude does it) | Checking Arabic text in After Effects {version}. This happens once per version. | جارٍ فحص النص العربي في After Effects {version}. يتم ذلك مرة واحدة لكل إصدار. |
| Fonts missing | Open fonts folder | Install the client's fonts, then restart After Effects. | ثبّت خطوط العميل ثم أعد تشغيل After Effects. |
| Unsaved work | Try again | After Effects has unsaved changes. Save or close the project first. | في After Effects تغييرات غير محفوظة. احفظ المشروع أو أغلقه أولًا. |
| Edited project | Rebuild (confirm dialog with the backup name) | You changed this project since the last build. A rebuild keeps a backup copy. | عدّلت هذا المشروع منذ آخر بناء. تحتفظ إعادة البناء بنسخة احتياطية. |
| No bridge | Check again | WhyNot Cut cannot reach After Effects. Restart it once. | لا يستطيع WhyNot Cut الوصول إلى After Effects. أعد تشغيله مرة واحدة. |
| Script only | Open Claude | Built without a check. It cannot pass QC. | تم البناء دون تحقق، ولا يمكنه اجتياز الفحص (QC). |

NEW keys: `ae.gate.probe`, `ae.gate.fonts`, `ae.gate.unsaved`, `ae.gate.edited`, `ae.gate.no_bridge`, `ae.gate.script_only`. States: each card normal; success (the card turns green and leaves); offline (the engine card replaces all). Empty, loading, stale: not applicable.

### A-04. Motion render, frames and handoff

| | |
|---|---|
| Purpose | Render, view the frames and finish |
| Data | `render_status` (RENDERED / FAILED), pieces, the MP4 path, the cover, the frames sheet (the same grid as P-08), the QC result, the verdict recorded by Claude, the handoff package, Needs you (final look and export, music, numbers) |
| Primary | Open project |
| Secondary | Render, Re-render scenes, Reveal folder, Copy diagnostics |
| Rule | motion SKILL §2, §5 (never "done" unless QC passed in the same report; Verified / Not verified / Needs you) |

| State | What the editor sees |
|---|---|
| Empty | "Nothing rendered yet." |
| Loading | Render progress with Cancel |
| Normal | MP4 path, frames grid, verdicts |
| Error | The render reasons in one line + Try again |
| Offline | Buttons disabled |
| Stale | "The project changed after the render. Render again." |
| Success | Done card as in P-06 |

NEW keys: `ae.render.empty`, `ae.render.progress`, `ae.render.stale`, `ae.render.done` (EN "Rendered. Check the frames." / AR «تم التصيير. راجع الإطارات.»).

## 5. Installer screens

One Tauri 2 app, "WhyNot Cut Setup", the same on Windows (per user, NSIS) and macOS (`.app` in a `.dmg`). The UI is HTML/CSS from the panel-ui tokens and components, AR/EN with RTL, no remote content. The core runs as a child process; the screens show its progress JSON `{step, index, total, status, percent, message_en, message_ar, done, exit_code}`. Proposed window: 760 × 540, minimum 640 × 480 (the sources give no size). Mockups at 760 and 640 in AR and EN, on both OS chromes only where copy differs (Smart App Control on Windows; folder access on macOS). A build that is not signed shows an "Internal build" label in the header (E2.1#8).

### I-01. Welcome

| | |
|---|---|
| Purpose | One screen, one decision: install everything |
| Data | Size N GB for this machine (from the pack selection), free disk, language, version "WhyNot Cut 3.0.0", signed or internal, existing install found (2.2.1), offline bundle found |
| Primary | Install everything |
| Secondary | Customise, language switch ع / EN |
| Rule | D1 (no questions by default), D-T1, E2, E2.1#1 (no admin), E2.1#4 (no telemetry) |

| State | What the editor sees |
|---|---|
| Normal | Title, one line, size, buttons, "No administrator rights needed." |
| Offline bundle | "No internet needed. Everything is in this download." |
| Upgrade | "WhyNot Cut 2.2.1 is installed. This will update it." |
| Internal build | An "Internal build" label |
| Error | The core did not start: I-07 |
| Empty, loading, stale, offline, success | Loading: the core is read once on open (a skeleton for the size line). Others not applicable |

| NEW key | EN | AR |
|---|---|---|
| `inst.welcome.title` | Install WhyNot Cut | تثبيت WhyNot Cut |
| `inst.welcome.text` | Everything WhyNot Cut needs, in one go (about {gb} GB). | كل ما يحتاجه WhyNot Cut دفعة واحدة (حوالي {gb} جيجابايت). |
| `inst.welcome.install` | Install everything | ثبّت كل شيء |
| `inst.welcome.customise` | Customise | تخصيص |
| `inst.welcome.no_admin` | No administrator rights needed. Nothing is sent from your computer. | لا حاجة إلى صلاحيات المسؤول. لا يُرسَل أي شيء من جهازك. |
| `inst.welcome.offline` | No internet needed. Everything is in this download. | لا حاجة إلى الإنترنت. كل شيء موجود في هذا التنزيل. |
| `inst.welcome.upgrade` | WhyNot Cut {version} is installed. This updates it. | WhyNot Cut {version} مثبّت. سيتم تحديثه. |
| `inst.internal` | Internal build | نسخة داخلية |

### I-02. Customise

| | |
|---|---|
| Purpose | The optional questions, every one preselected |
| Data | Engine location (default under the user home; a path with non-ASCII or spaces suggests `C:\WhyNotCut`), model packs with sizes (core, fast, small, Kalam pack, fonts; all ticked except small), language, clients folder (default `D:\WhyNot Clients` if D: exists, else Documents), "Run WhyNot Cut's engine without asking each time" (default yes), "Start WhyNot Cut when I sign in" (default on) |
| Primary | Install |
| Secondary | Back |
| Rule | D1, D3, ID-11, ID-13, ID-14, E2.1#4 |

States: normal; a pack that does not fit the disk is marked "Skipped, add later" (D3); non-ASCII path warning (amber); error "This folder cannot be used" (Choose another). Empty, loading, offline, stale, success: not applicable.

| NEW key | EN | AR |
|---|---|---|
| `inst.custom.title` | Customise | تخصيص |
| `inst.custom.location` | Where to install the engine | مكان تثبيت المحرّك |
| `inst.custom.packs` | Speech models | نماذج الكلام |
| `inst.custom.clients` | Clients folder | مجلد العملاء |
| `inst.custom.permission` | Let WhyNot Cut run its engine without asking each time | اسمح لـ WhyNot Cut بتشغيل محرّكه دون سؤال في كل مرة |
| `inst.custom.login` | Start WhyNot Cut when I sign in | شغّل WhyNot Cut عند تسجيل الدخول |
| `inst.custom.non_ascii` | This path has special characters. We suggest {path}. | يحتوي هذا المسار على رموز خاصة. نقترح {path}. |
| `inst.custom.install` | Install | تثبيت |
| `inst.back` | Back | رجوع |

### I-03. Preflight

| | |
|---|---|
| Purpose | Tell the truth about this computer before downloading anything |
| Data (`ctx.facts`) | os, arch, free_gb, home_ascii and home_space, OneDrive or iCloud Documents, Claude found, Adobe hosts (app, version, running), NVIDIA, existing engine or legacy install, Smart App Control (Windows) |
| Primary | Continue (disabled on a red row) |
| Secondary | Check again, Back |
| Rule | D0, D4, T7.1 step 1 (free space under 6 GB is red and stops, under 9 GB is amber), E2.1#2 |

| Row | Result | EN | AR |
|---|---|---|---|
| Disk | red under 6 GB | There is not enough space. Free {gb} GB and check again. | المساحة غير كافية. حرّر {gb} جيجابايت ثم افحص مرة أخرى. |
| Disk | amber under 9 GB | Space is tight. Some optional models will be skipped. | المساحة محدودة. ستُتخطى بعض النماذج الاختيارية. |
| Adobe | info | Premiere Pro or After Effects must already be installed with your own licence. | يجب أن يكون Premiere Pro أو After Effects مثبّتًا بترخيصك الخاص. |
| Adobe running | amber | Close Premiere Pro before the Adobe step. | أغلق Premiere Pro قبل خطوة Adobe. |
| Path | amber | Your user folder has special characters. We handle it. | يحتوي مجلد المستخدم على رموز خاصة. سنتعامل معها. |
| Cloud folders | amber | Documents is synced by OneDrive. Clients go in another folder. | مجلد المستندات متزامن مع OneDrive. سنضع العملاء في مجلد آخر. |
| Windows protection | amber | Smart App Control may show a warning for an unsigned build. | قد تعرض حماية التطبيقات الذكية (Smart App Control) تحذيرًا لنسخة غير موقّعة. |
| Claude | info | Claude is not installed. We can install it for you. | Claude غير مثبّت. يمكننا تثبيته لك. |

NEW keys `inst.pre.*`. States: loading (rows "Checking" one by one); normal (green, amber, info); error (a red row stops the flow; the fix is "Check again"); success (all ok: Continue enabled). Offline: a note "No internet: only the offline bundle can install" when the bundle is absent. Empty, stale: not applicable.

### I-04. Progress checklist (+ action needed)

| | |
|---|---|
| Purpose | Show every step as a row; the same definition as the panel checklist and the start skill (eco §3.6.4) |
| Data | One row per user-facing step, from the core's steps: Check this computer · Engine (runtime, ffmpeg, GPU) · Claude plugin · Git Bash for the safety hooks (Windows) · Adobe panels · Fonts · Engine always on (launcher, login item, link scheme) · Speech models · Your first client folder · Final check · Open Claude. Each row: status icon (ok, amber, red, pending, running), name, one line from `message_ar` or `message_en`, a bar with percent and size while downloading |
| Primary | None while running (Cancel is secondary) |
| Secondary | Cancel (confirm: stops and keeps what is done), Show details (log drawer, path of `install-*.log`), Hide window (downloads continue) |
| Rule | D2, ID-12, T7.1, B-T5 (rows green / amber / red with icons), E2.1#4 (every action shown and logged), D3 ("editing can start while large packs keep downloading") |

| State | What the editor sees |
|---|---|
| Loading, normal | Rows turn green one by one; the current row has a bar and elapsed time |
| Action needed | An interstitial card, one button: "Close Premiere Pro" (then Continue); "Sign in to Creative Cloud" (it is started for you if closed); the UPIA fallback "Double-click the panel file" with the file name in LTR |
| Error, amber | A row with one sentence and one fix; the rest continue |
| Error, red | Stops; I-07 |
| Offline | Rows that need the network turn amber; "The model downloads continue when you are online." |
| Resume | Re-running repairs: finished rows show green at once |
| Success | All rows done; moves to I-06 |
| Cancelled | "Stopped. Run it again to continue." |
| Empty, stale | Not applicable |

| NEW key | EN | AR |
|---|---|---|
| `inst.step.preflight` | Check this computer | فحص هذا الكمبيوتر |
| `inst.step.engine` | WhyNot Cut engine | محرّك WhyNot Cut |
| `inst.step.claude` | WhyNot Cut inside Claude | WhyNot Cut داخل Claude |
| `inst.step.gitbash` | Safety tools for Claude | أدوات الحماية لـ Claude |
| `inst.step.adobe` | Premiere and After Effects panels | لوحات Premiere وAfter Effects |
| `inst.step.fonts` | Fonts | الخطوط |
| `inst.step.always_on` | Keep the engine ready | إبقاء المحرّك جاهزًا |
| `inst.step.models` | Speech models | نماذج الكلام |
| `inst.step.client` | Your first client folder | مجلد عميلك الأول |
| `inst.step.doctor` | Final check | الفحص النهائي |
| `inst.step.launch` | Open Claude | فتح Claude |
| `inst.cancel` | Cancel | إلغاء |
| `inst.cancel.confirm` | Stop installing? What is done stays. | إيقاف التثبيت؟ ما تم يبقى كما هو. |
| `inst.cancelled` | Stopped. Run it again to continue. | تم الإيقاف. شغّل المثبّت مرة أخرى لتتابع. |
| `inst.hide` | Keep going in the background | تابع في الخلفية |
| `inst.details` | Show details | عرض التفاصيل |
| `inst.action.close_host` | Close {app}, then continue. | أغلق {app} ثم تابع. |
| `inst.action.cc` | Open Creative Cloud and sign in. | افتح Creative Cloud وسجّل الدخول. |
| `inst.action.ccx` | Double-click this file to finish: {file} | انقر نقرًا مزدوجًا على هذا الملف لتكمل: {file} |
| `inst.continue` | Continue | متابعة |

### I-05. Install Claude for me

| | |
|---|---|
| Purpose | Install Anthropic's official app when it is missing, then wait for the editor to sign in |
| Data | detect → download from claude.ai/download over HTTPS → check the publisher (Windows: Authenticode publisher; macOS: `codesign` Team ID) → launch → wait for sign-in (timeout) |
| Primary | Install Claude |
| Secondary | I already have Claude, Skip for now |
| Rule | D7, E-T4, E2.1#3 (HTTPS from the allowlist only, signature checked), D0.1 (the sign-in stays the editor's) |

| State | What the editor sees |
|---|---|
| Normal | A short explanation and the button |
| Loading | Downloading with a bar; "Checking it is really from Anthropic." |
| Waiting | "Sign in to Claude in the window that opened. We continue by ourselves." with a spinner and "I have signed in" |
| Error | Publisher not Anthropic: "The file did not pass the safety check, so we did not run it." + Copy diagnostics (never run) |
| Offline | "No internet. Install Claude later from claude.ai." |
| Timeout | "We did not see a sign-in yet." + Wait more / Continue without it |
| Success | "Claude is ready." |
| Empty, stale | Not applicable |

| NEW key | EN | AR |
|---|---|---|
| `inst.claude.title` | Claude is not installed | Claude غير مثبّت |
| `inst.claude.text` | WhyNot Cut works inside Claude. We can install Anthropic's official app for you. | يعمل WhyNot Cut داخل Claude. يمكننا تثبيت تطبيق Anthropic الرسمي لك. |
| `inst.claude.install` | Install Claude | ثبّت Claude |
| `inst.claude.checking` | Checking that it is really from Anthropic… | نتأكد أنه من Anthropic فعلًا… |
| `inst.claude.signin` | Sign in to Claude in the window that opened. We continue by ourselves. | سجّل الدخول إلى Claude في النافذة التي فُتحت. سنتابع تلقائيًا. |
| `inst.claude.signed` | I have signed in | سجّلت الدخول |
| `inst.claude.refused` | The file did not pass the safety check, so we did not run it. | لم ينجح الملف في فحص الأمان، لذلك لم نشغّله. |
| `inst.claude.ready` | Claude is ready. | Claude جاهز. |

### I-06. Finish

| | |
|---|---|
| Purpose | Say what is ready, what is left, and open Claude on the first run |
| Data | Final `doctor` rows (green or amber with a one-click fix), the first client folder path, a deep link result (launched or not registered) |
| Primary | Open Claude (opens a new session on the start skill; the new session is what picks up the new plugin) |
| Secondary | Show my clients folder, Close; fallback box "Paste this in Claude" with a Copy button when the deep link is not available |
| Rule | eco §3.6.1, D2.8 and D2.9, F14, ID-15, D4 (macOS folder access is explained before the prompt appears) |

| State | What the editor sees |
|---|---|
| Success | Green summary; "Next: open Premiere, then Window ▸ UXP Plugins ▸ WhyNot Cut." |
| Normal, amber | A row with its one-click fix (e.g. "Restart Premiere once") |
| Fallback | The copy box (the text is the start command, in a mono chip, LTR) |
| macOS | A note: "macOS will ask once to allow access to your clients folder. Choose Allow." |
| Error | A red row: I-07 |
| Empty, loading, offline, stale | Loading: the final check runs for about 2 s. Others not applicable |

| NEW key | EN | AR |
|---|---|---|
| `inst.done.title` | WhyNot Cut is ready | WhyNot Cut جاهز |
| `inst.done.next` | Next: open Premiere, then Window ▸ UXP Plugins ▸ WhyNot Cut. | التالي: افتح Premiere ثم Window ▸ UXP Plugins ▸ WhyNot Cut. |
| `inst.done.open_claude` | Open Claude | افتح Claude |
| `inst.done.clients` | Show my clients folder | أظهر مجلد العملاء |
| `inst.done.paste` | Paste this in Claude to begin: | الصق هذا في Claude لتبدأ: |
| `inst.done.copy` | Copy | نسخ |
| `inst.done.mac_access` | macOS will ask once to allow access to your clients folder. Choose Allow. | سيطلب macOS مرة واحدة السماح بالوصول إلى مجلد العملاء. اختر «سماح». |
| `inst.close` | Close | إغلاق |

### I-07. Security and failure cards

| | |
|---|---|
| Purpose | Every installer failure as one sentence and one button, never a stack trace |
| Data | Core status `red` or `amber` with the step and the log path |
| Primary | The card's one button |
| Rule | E2.1#3, E2.1#4, E-T7 (tampered download and manifest rejected, offline mode), F7 (UPIA silent failure), B4.4 |

| Card | Button | EN | AR |
|---|---|---|---|
| Download changed | Try again | A download did not match its checksum, so we did not use it. | لم يطابق أحد التنزيلات بصمته (Checksum)، لذلك لم نستخدمه. |
| Manifest not trusted | Copy diagnostics | The install list is not signed by The Why Not. Nothing was installed. | قائمة التثبيت غير موقّعة من The Why Not. لم يُثبَّت شيء. |
| Address not allowed | Copy diagnostics | We stopped a download from an address that is not on our list. | أوقفنا تنزيلًا من عنوان غير مدرج في قائمتنا. |
| No internet | Try again | No internet. Connect and try again, or use the offline download. | لا يوجد إنترنت. اتصل ثم حاول مرة أخرى، أو استخدم التنزيل الكامل دون إنترنت. |
| Disk full | Check again | The disk is full. Free some space and continue. | القرص ممتلئ. حرّر بعض المساحة وتابع. |
| Adobe panel not loaded | Show me | Adobe did not install the panel. Double-click the panel file to finish. | لم تثبّت Adobe اللوحة. انقر نقرًا مزدوجًا على ملف اللوحة لتكمل. |
| Hosts still open | Check again | Premiere Pro is still open. Close it, then continue. | ما زال Premiere Pro مفتوحًا. أغلقه ثم تابع. |

States: each card normal; with the log path shown under it. Empty, loading, offline (the no-internet card), stale, success: not applicable (a card is shown only on failure).

### I-08. Update and repair

| | |
|---|---|
| Purpose | A new version is ready, or a damaged install is repaired by running the same steps again |
| Data | Installed and available version (one number, "WhyNot Cut 3.0.1"), release notes in one line, signed-update check |
| Primary | Update |
| Secondary | Later, Repair |
| Rule | E2 (Tauri's signed updater), C1.10, D1 ("running either door again repairs or updates") |

States: normal (update ready), loading (downloading and checking the signature), success ("WhyNot Cut is up to date"), error (signature check failed: "We did not install the update because it is not signed correctly." + Copy diagnostics), offline ("Could not check for updates."), repair (progress as I-04). Empty, stale: not applicable.

| NEW key | EN | AR |
|---|---|---|
| `inst.update.title` | WhyNot Cut {version} is ready | WhyNot Cut {version} جاهز |
| `inst.update.now` | Update | تحديث |
| `inst.update.later` | Later | لاحقًا |
| `inst.update.repair` | Repair | إصلاح |
| `inst.update.current` | WhyNot Cut is up to date. | WhyNot Cut محدَّث. |
| `inst.update.bad_sig` | We did not install the update because it is not signed correctly. | لم نثبّت التحديث لأنه غير موقّع توقيعًا صحيحًا. |

### I-09. Uninstall

| | |
|---|---|
| Purpose | Remove everything WhyNot Cut added, and nothing else |
| Data | The list of what goes (the Claude plugin and marketplace entry, the Adobe panels, fonts, the login item, the link scheme, the engine) and a tick box "Also delete speech models ({gb} GB)" unticked; the client folders named as untouched; the settings backup |
| Primary | Uninstall (a destructive confirm) |
| Secondary | Cancel |
| Rule | E2.1#5 (clean uninstall; models only if ticked; client folders never touched; a before and after diff equals our files only), D1 |

| State | What the editor sees |
|---|---|
| Normal | The list, the models tick box, "Your client folders are not touched: {path}" |
| Loading | Progress rows (plugin, panels, fonts, login item, engine) |
| Error | A row that could not be removed is listed with its path |
| Success | "WhyNot Cut was removed. Your client folders were not touched." |
| Empty, offline, stale | Not applicable |

| NEW key | EN | AR |
|---|---|---|
| `inst.un.title` | Remove WhyNot Cut | إزالة WhyNot Cut |
| `inst.un.list` | This removes the plugin, the panels, the fonts, the startup entry and the engine. | ستُزال الإضافة واللوحات والخطوط وإدخال بدء التشغيل والمحرّك. |
| `inst.un.models` | Also delete the speech models ({gb} GB) | احذف نماذج الكلام أيضًا ({gb} جيجابايت) |
| `inst.un.clients` | Your client folders are not touched: {path} | لن يُمسّ مجلد عملائك: {path} |
| `inst.un.go` | Uninstall | إزالة |
| `inst.un.done` | WhyNot Cut was removed. Your client folders were not touched. | أُزيل WhyNot Cut. لم يُمسّ مجلد عملائك. |

## 6. Data the screens need that `PanelState` does not carry today

`PanelState` today has: `connection`, `client`, `item`, `language`, `editor_name`, `context`, `pipeline`, `approval`, `qc`, `log`. The schema is closed (`additionalProperties: false`), so every addition below is a contract change for the engine side (T6.2b).

| Needed by | NEW field | Note |
|---|---|---|
| G3, P-10 | `needs_you[]` | The kit badge already takes a count |
| P-02, P-01 | `update {panel: ok / stale / newer / unknown, pending: bool}` | Today only in `welcome.update`, not in the state |
| P-01 | `setup[] {id, state, detail}` | Rows engine, premiere, claude, clients |
| P-02, G1 | `connection.claude` detail: plugin version, item, minutes ago | The enum has the six states but no detail |
| G1, AE | `connection.engine` starting; host name (Premiere or After Effects) | The pill key is hard-coded "Premiere" |
| P-03 | `home.last{}` | Last result per verb and tool |
| P-04 | `clients[]`, `items[]` | Only the current pair exists |
| P-05 | `intake {folder, clips[], warnings[]}` | |
| P-12 | `ai {backend, jobs[]}` | |
| P-13 to P-20 | `tools {…}` | The 20 reserved host actions are named in `protocol.json` and not routed yet |
| P-21 | `models[]` | |
| P-22 | `settings {…}` | |
| A-01 to A-04 | `motion {…}` and host-specific step labels | The pipeline step ids are a fixed enum of seven |

## 7. Where the sources disagree or are silent

| # | Topic | What the sources say | Decision in this inventory |
|---|---|---|---|
| 1 | Reference numbers | The brief cites "B3 screens", "C3.6" and "C3.4". Addendum B §B3 is Arabic and English (the screens are in B1, B4.1 and E1). In Addendum C, §C3 is "Plan changes"; the first-run checklist and the status model are `evidence/ecosystem.md` §3.6 and §3.4 | Cited by their real location |
| 2 | Tabs | `i18n` has Home, Edit and Tools. Addendum A and B speak of "tabs" for Kalam, Hush and Tidy. `render.ts` has no tabs at all (one scroll) | Three tabs; the three tools live in Tools (P-13) |
| 3 | Where Models and Settings open | E1 lists a models page and settings; no source says how to reach them | Two rows at the bottom of Home |
| 4 | What Settings contains | No source defines it | Proposed in P-22 |
| 5 | Home: "three big actions" vs "one primary per screen" | B4.1 and B4.2 | The next step in the flow is the primary; the other two are glass |
| 6 | What "Drop files" does in a UXP panel | B4.1 names it; UXP cannot take an OS drop | Shows the folder and Open folder, then watches for new files (P-05) |
| 7 | Footer text | A6b, B2 and the i18n key: «Powered by thewhynot.ai». The master plan and C1.7 say "Powered by Claude" | Kept «Powered by thewhynot.ai» as the brief says; the AR value is English today |
| 8 | Mockup widths | E1: 300, 360, 480. B-T6 and the UXP evidence: 280, 340, 480. CEP minimum width is 280 | 300 / 360 / 480 plus 280 where a row of controls is at risk |
| 9 | Icons | E-D6: one set, Lucide. The kit's `icons.ts` has its own 16 px inline set (status, chevrons, close) | Open: keep the kit set for status and use Lucide only if it paints in UXP |
| 10 | AI backends | C1.7: open session first, then the API key, then a deep link; the subscription CLI is opt-in and off by default (H14). eco §3.5b lists the local CLI first. Kalam PRD FR-6 and A3.10 make the subscription CLI the default | C1.7 wins (latest and binding); P-22 shows the CLI as off by default |
| 11 | AI button list | C1.7: fix captions, suggest titles, summarise. eco §3.5b: Kalam correction, caption fix, title or hook suggestions, publish copy draft | P-12 draws the C1.7 three; the rest are the same pattern |
| 12 | Checklist rows | The panel and kit have 4 rows (engine, premiere, claude, clients); the installer has 14 steps; D2 has 9 items. eco §3.6.4 wants one shared definition | Installer shows 11 user-facing rows (I-04); the panel shows the 4-row summary |
| 13 | Stale-panel card button | C1.8 says "Restart Premiere" as one card; the panel cannot quit Premiere (no API measured, spike 0.1.6) and C1.4 wants a button | Button "Check again"; whether Claude may restart Premiere (standing permission) is not shown on the card |
| 14 | Installer front end | D7 says Inno Setup (Windows) and SwiftUI (macOS); E2 replaces both with one Tauri app. ID-11 describes a 10 second "press C" countdown in the console; D1 describes a button | E wins; GUI uses the Customise button |
| 15 | Installer screens | E1 lists "the installer screens (E2)" but E2 names none | Nine derived from D, E2.1 and the core's steps (§5) |
| 16 | Installer window size and OS chrome | Not stated | Proposed 760 × 540 |
| 17 | Commands in the installer | C1.4 (no commands on screen) is a panel-ui rule; eco F14 asks for a big copy box of the start command when the deep link fails | Copy box kept in I-06, in a mono chip |
| 18 | Motion pipeline | The panel's seven step ids are a fixed enum; the motion skill has about eleven stages (audio, script, claims, animatic, approve, probe, build, render, QC, verdict, handoff) | Mapped onto the seven (A-01); needs host-specific labels |
| 19 | AE panel scope | T6.8 says "same UI: motion pipeline, approvals, QC frames, render"; no source lists the AE panel's data fields or states | A-01 to A-04 derived from the motion skill and `motion_build.py` statuses |
| 20 | Motion approval from the panel | The motion skill speaks of the lead and the editor approving in chat; C1.5 says a panel approve writes the same evidence | Drawn as in P-07 (the editor's own click is the approval) |
| 21 | Tool flows on the panel | The PRDs describe CEP panels; A2 says tabs in the UXP panel; the host actions are reserved and not routed | Drawn from the PRDs as placeholders; no screen shows a routing error |
| 22 | Where "Organise → Cut → Caption" lives | A3.4 describes the flow, not its place | Primary button of the Tools hub |
| 23 | QC fail tile | The verdicts exist; no source says what the editor does with a failed frame | A hint "Request changes" (P-08) |
| 24 | Done / handoff screen | The `handoff` step exists; no source designs its screen | Drawn as the done state of P-06 using the Verified / Not verified / Needs you report format |
| 25 | Arabic strings still in English | `ar.json`: `log.held`, `log.start_engine`, `footer.powered`. B3 says a test fails on any untranslated key | Flagged for the string table owner |
| 26 | Needs-you scope | B4.6 says "opens `NEEDS-YOU.md` in the panel"; T4.7 writes one file per client | One list for the current client, grouped by item |
| 27 | Claude pill vs card | C1.6 gives states; eco §3.5c gives pill texts with buttons | Pill = short value; card = sentence + one button (P-02) |
| 28 | Door 2 (install from inside Claude) | D1 describes a chat card and chat progress, not a screen | Not mocked; its copy would reuse the `inst.*` keys |
