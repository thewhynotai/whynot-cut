/* Mockup copy for the "tools + After Effects" screen group (P-13 to P-20, A-01 to A-04), EN and AR.
   Loaded after ../strings.js; merges into window.MOCK_STRINGS.{en,ar}. Every key carries its screen id (p13. … a04.);
   keys used by several screens of the group carry the first screen that uses them (p13. for the tools, a01. for After
   Effects). This group uses its own keys even where strings.js has a similar line, so the register and the names below
   stay consistent on these screens (the string owner may merge them later).
   Origins:
   NEW  = a NEW key of docs/design/screen-inventory.md, reworded to the rules below (key renamed to the screen id);
   MOCK = written for these mockups. Every line needs the string-table owner; every Arabic line needs a native writer.
   Tool wording follows the upstream tools (adobe/tools/{tidy,hush,kalam}/_upstream/js/i18n.js).
   Rules applied (E-D3 r1, Addendum G, G2-r1 agency-owner decisions 2026-10-14):
   - Arabic is professional EGYPTIAN (السيكوينس، قطعات، الكليب، التراك، عايز، لسه، مفيش، عشان), no tatweel, Western digits,
     U+00A0 inside time and unit phrases, no English glosses; brand sub-names Tidy, Hush, Kalam stay in Latin script.
   - The background program is "the WhyNot Cut service" / «خدمة WhyNot Cut»; the panel is just "WhyNot Cut".
   - Plain-language tool names first (رتّب المشروع / شيل السكتات / كابشن); «الترجمة النصية» is never used.
   - No developer words: no "MOGRT" alone (a "caption template"), no "read-back", "recipe", "engine", no paths in body
     copy (file names only, with a Show-in-folder button). Errors: what happened, why, one fix; "Contact support".
   - Trust lines: what each tool creates or changes, that the originals stay untouched, and the undo or backup name.
   - Value: results show the time saved (mock values; an engine data request). */
(function () {
  var NB = " ";
  Object.assign(window.MOCK_STRINGS.en, {
    /* group-wide (P-13) */
    "p13.title": "Tools",                                                          /* NEW */
    "p13.flow": "Organise → Cut → Caption",                                         /* NEW */
    "p13.flow.sub": "Three steps, one after another. Each one shows its preview and asks you first.", /* NEW */
    "p13.need_project": "Open a project in Premiere to use the tools.",             /* NEW */
    "p13.model_busy": "Captions pack downloading · {pct}%",                         /* NEW */
    "p13.flow.eyebrow": "All three in order",
    "p13.sequence": "Sequence: {name}",
    "p13.tidy.sub": "Cleans the project and sorts it into bins. Syncs a podcast by sound.",
    "p13.hush.sub": "Cuts silences and filler words.",
    "p13.kalam.sub": "Captions timed to the voice: a track, a template or an SRT file.",
    "p13.need_project.title": "No project open",
    "p13.open_project": "Open project",
    "p13.chip.downloading": "Downloading",
    "p13.model_offer": "The captions pack is still downloading. You can start now with the smaller model: it's faster but less exact.",
    "p13.use_small": "Use the smaller model",
    "p13.error": "Couldn't read the open project from Premiere.",
    "p13.error.hint": "Try again. If it fails again, save the project, close Premiere and open it again.",
    "p13.success": "Captions done: {n} captions placed in {seq}.",
    "p13.last": "Last: {text} · {ago}",
    "p13.last.now": "Last: {text} · just now",
    "p13.none": "Nothing yet.",
    "p13.last.tidy": "214 files sorted", "p13.ago.tidy": "1" + NB + "d ago",
    "p13.last.hush": "24 pieces cut", "p13.ago.hush": "2" + NB + "h ago",
    "p13.kalam.last": "64 captions placed",
    "p13.week": "This week the tools saved about 1 h 10 min · estimate.",
    "p13.back": "Tools",
    "p13.elapsed": "Elapsed {t}",
    "p13.stop": "Stop",
    "p13.done": "Done",





    "p13.dialog.changes": "What will change",
    "p13.dialog.keep": "Keep my project",
    "p16.show_words": "Show the {n} words",




    "p13.no_claude": "Claude isn't signed in. The tools still work; captions are made without correction until you sign in.",
    "p13.no_claude.solo": "Claude isn't signed in. You don't need it here: this tool works on its own.",

    /* P-14 Tidy scan and plan */
    "p14.mode.reels": "Reels", "p14.mode.podcast": "Podcast",                       /* NEW */
    "p14.scan": "Scan the project",                                                 /* NEW */
    "p14.sec.remove": "To remove from the project",                                 /* NEW */
    "p14.sec.remove_note": "Only from the project. Your files stay on disk.",        /* NEW */
    "p14.sec.move": "To move into bins",                                            /* NEW */
    "p14.sec.nests": "New nest names",                                              /* NEW */
    "p14.sec.offline": "Missing files (for your information)",
    "p14.optin": "Not ticked by default",                                           /* NEW */
    "p14.apply": "Clean & organise",                                                /* NEW */
    "p14.dialog.backup": "The project is saved, then copied as:",                   /* NEW */
    "p14.project": "Project",
    "p14.mode.hint.reels": "Reels: one bin per type of file.",
    "p14.mode.hint.podcast": "Podcast: one bin per camera (Cam 1, Cam 2 …) and the mics apart.",
    "p14.rescan": "Scan again",
    "p14.empty.title": "Not scanned yet",
    "p14.empty": "Scan the project to see what Tidy can clean. Nothing changes until you confirm.",
    "p14.scanning": "Reading the project · {n} of {of} items",
    "p14.stat.items": "items in the project", "p14.stat.size": "media size",
    "p14.stat.remove": "to remove ({size})", "p14.stat.unused": "of the project size is unused",
    "p14.r.unused": "Not used in any sequence", "p14.r.duplicate": "Unused duplicate copy",
    "p14.r.backup": "Old Hush or Kalam backup", "p14.r.captions": "Caption files",
    "p14.r.captions_note": "Not ticked: Premiere doesn't say which ones are in use.",
    "p14.r.cameras": "Camera footage", "p14.r.mics": "Mic recordings", "p14.r.long": "Recordings of 3" + NB + "min or longer",
    "p14.show_all": "Show all {n}",
    "p14.nests.note": "Named from what each nest holds. Untick one to keep its old name.",
    "p14.sec.bins": "Old bins to remove",
    "p14.sec.dup": "Duplicates in use (for your information)",
    "p14.offline.note": "Missing from their folder on disk. Tidy doesn't change them.",
    "p14.sec.problems": "Problems",
    "p14.problem.1": "Interview_B-cam.mxf: the file is damaged and can't be opened.",
    "p14.problem.2": "Nested Sequence 04: Premiere didn't say what it holds.",
    "p14.sec.options": "What Tidy does",
    "p14.opt.remove": "Remove the ticked items", "p14.opt.organise": "Organise into bins, with nest names",
    "p14.opt.colours": "Give each type a fixed colour",
    "p14.bar.summary": "{r} to remove · {m} to move · {n} renamed",
    "p14.bar.hint": "Files on disk are never touched, and you can put everything back.",
    "p14.dialog.title": "Clean and organise {name}?",
    "p14.dialog.c1": "{r} items leave the project. The files stay on disk.",
    "p14.dialog.c2": "{m} items move into {b} bins.",
    "p14.dialog.c3": "{e} empty bins are removed and {n} nests renamed.",
    "p14.dialog.c4": "Each type gets its fixed colour.",
    "p14.unsaved": "This project has never been saved, so no backup can be made.",
    "p14.unsaved.hint": "Save it once in Premiere (File > Save), then press Check again.",
    "p14.error": "Tidy couldn't read 2 items, so they're left out of the plan.",
    "p14.error.hint": "They're listed under Problems. The rest of the plan is complete.",
    "p14.stale": "The project changed since the scan. Scan again before cleaning.",

    /* P-15 Tidy report, put back, podcast sync */
    "p15.done": "Project organised. The old copy is kept.",                         /* NEW */

    "p15.sync": "Sync the podcast by sound",                                       /* NEW */
    "p15.sync.progress": "Matching clip {n} of {of} · {name}",                     /* NEW */
    "p15.sync.skipped": "Left out: {name} (no clear sound match)",                 /* NEW */
    "p15.sync.done": "Synced sequence ready: {name}",                              /* NEW */
    "p15.applying": "Cleaning the project · {n} of {of}",
    "p15.value": "About 25 min of sorting saved · estimate.",
    "p15.counts": "What Tidy did",
    "p15.moved": "Moved into bins", "p15.removed": "Removed from the project", "p15.renamed": "Nests renamed",
    "p15.bins": "Empty bins removed",
    "p15.skipped": "{s} of the {r} planned items were kept because they turned out to be in use.",
    "p15.where": "Where things went",

    "p13.sec": "{n}" + NB + "s",
    "p15.backup.title": "Put everything back",
    "p15.undo.hint": "Opens the copy saved before cleaning, as it was. The organised project stays too.",
    "p15.reveal": "Show in folder",
    "p15.sync.title": "Podcast sync",
    "p15.sync.sub": "Lines up every camera and mic by sound and builds one new multicam sequence. Your clips stay as they are.",
    "p15.sync.found": "Found {c} cameras and {m} mics.",
    "p15.sync.placed": "{n} of {of} clips placed.",
    "p15.sync.skip_hint": "Place it by hand, or record a clap at the start next time.",
    "p15.open_seq": "Open the synced sequence",
    "p15.error": "1 clip couldn't be exported, so it was left out: {name}",
    "p15.error.hint": "The other 6 were synced. The file may be open in another app: close it, then try again.",
    "p15.retry_clip": "Try this clip again",


    /* P-16 Hush scan and preview */
    "p16.target": "Target: {label}",                                               /* NEW */
    "p16.scan": "Scan",                                                             /* NEW */
    "p16.soft": "Soft", "p16.medium": "Medium", "p16.strong": "Strong",             /* NEW */
    "p16.strength": "Strength",                                                     /* NEW */
    "p16.fillers": "Filler words",                                                  /* NEW */
    "p16.counts": "{s} pauses + {f} filler words",                                  /* NEW */
    "p16.mode.cut": "Cut", "p16.mode.markers": "Markers only",                      /* NEW */
    "p16.go": "Cut", "p16.markers.go": "Add markers",                               /* NEW */
    "p16.track_locked": "A ticked track is locked: {track}. Nothing was cut.",      /* NEW */
    "p16.not_moving": "These tracks will not move: {tracks}",                       /* NEW */
    "p16.target.whole": "Whole sequence",
    "p16.target.hint": "Select clips or set In/Out in Premiere to narrow it.",
    "p16.tracks": "Tracks",
    "p16.rescan": "Scan again",
    "p16.empty": "Scan the range to see the pauses.",
    "p16.strength.title": "How much to cut",
    "p16.simple": "Simple", "p16.advanced": "Advanced",
    "p16.tight": "Tight cut (no margin around speech)",
    "p16.threshold": "Silence below", "p16.min": "Shortest pause",
    "p16.pad_before": "Keep before speech", "p16.pad_after": "Keep after speech",
    "p16.link_pads": "Same margin before and after",
    "p16.fillers.on": "Cut filler words",
    "p16.lang": "Speech", "p16.lang.auto": "Auto", "p16.lang.en": "English", "p16.lang.ar": "Arabic",
    "p16.list.strong": "Cut by default", "p16.list.soft": "Ask first (often real words)",
    "p16.sounds": "Unclear sounds (breaths, clicks)",
    "p16.off": "Off",
    "p16.fillers.off": "Filler words need the WhyNot Cut service. Pauses can still be cut.",
    "p16.wave": "Preview",
    "p16.legend.sil": "{n} pauses", "p16.legend.fil": "{n} filler words",
    "p16.wave.hint": "Click the waveform to move the playhead there.",
    "p16.summary.title": "Result",
    "p16.before": "Before", "p16.after": "After", "p16.saved": "Shorter by",
    "p16.in_force": "Settings in use: {v}",
    "p16.options": "How to cut",
    "p16.ripple": "Close the gaps after cutting",
    "p16.link": "Keep audio linked to video",

    "p16.presets": "Preset: Sahha talking head",
    "p16.save_preset": "Save preset",
    "p16.bar": "Cuts {n} pieces · {t} shorter",
    "p16.bar.trust": "A backup copy of your sequence is always saved first.",
    "p16.bar.markers": "Adds {n} markers. Nothing is cut.",
    "p16.dialog.title": "Cut {n} pieces from {seq}?",
    "p16.dialog.c1": "{s} pauses and {f} filler words are removed.",
    "p16.dialog.c2": "The gaps close, so everything after a cut moves earlier.",
    "p16.dialog.c3": "Tracks that move: {tracks}",
    "p16.dialog.backup": "Your sequence is copied first, as:",
    "p16.dialog.keep": "Keep my sequence",
    "p16.dialog.nobackup": "The backup copy couldn't be made this time. Without it, only Edit > Undo in Premiere can bring the sequence back.",
    "p16.stage.export": "Exporting audio from Premiere",
    "p16.stage.silence": "Finding pauses",
    "p16.stage.fillers": "Finding filler words",
    "p16.scanning": "{stage} · step {n} of {of}",
    "p16.locked.hint": "Untick it here, or unlock it in Premiere and scan again.",
    "p16.untick": "Untick {track}",
    "p16.stale": "The sequence changed since the scan. Scan again.",

    /* P-17 Hush result and undo */
    "p17.result": "Cut {n} pieces. The sequence is {time} shorter.",               /* NEW */
    "p17.value": "{n} pieces cut · about {m} min of editing saved · estimate",
    "p17.backup": "Your original is kept, untouched, as:",                         /* NEW */

    "p17.markers": "Added {n} markers. Nothing was cut.",                          /* NEW */
    "p17.undo.hint": "Brings the original back under its own name. The cut version is kept as:",
    "p17.reveal": "Show in project",
    "p17.clear": "Remove all Hush markers",
    "p17.markers.hint": "Each marker sits on a pause or a filler word, so you can cut by hand.",
    "p17.partial": "Cut {n} of {of} pieces. {k} were skipped.",
    "p17.partial.hint": "They sit on V2, where a clip is locked. Unlock it in Premiere, then cut the rest.",
    "p17.cut_rest": "Cut the skipped pieces",
    "p17.undone": "Restored {name}. The cut version is kept as:",


    /* P-18 Kalam setup */
    "p18.lang": "Language", "p18.lang.ar": "Arabic", "p18.lang.en": "English", "p18.lang.other": "Other", /* NEW */
    "p18.range": "Range", "p18.range.sequence": "Whole sequence", "p18.range.playhead": "From the playhead", /* NEW */
    "p18.range.selection": "Selected clips", "p18.audio": "Audio tracks",           /* NEW */
    "p18.output.srt": "SRT file only",                                             /* NEW */
    "p18.correct": "Correct the text with Claude",                                  /* NEW */
    "p18.start": "Start",                                                           /* NEW */
    "p18.model.ar": "Tuned for Egyptian Arabic, with each word timed",
    "p18.range.inout": "In / Out",
    "p18.range.inout.sub": "{a} to {b}",
    "p18.audio.hint": "Only ticked tracks are listened to.",
    "p18.output": "Captions as",
    "p18.output.track": "Captions track",
    "p18.output.mogrt": "Caption template",
    "p18.output.mogrt.sub": "A Premiere motion graphics template (.mogrt)",
    "p18.srt_always": "An SRT caption file is always saved next to the project.",
    "p18.change": "Change",
    "p18.vtrack": "Video track", "p18.textfield": "Text field",
    "p18.settings": "Caption settings",
    "p18.max_chars": "Characters per line", "p18.max_lines": "Lines per caption",
    "p18.max_secs": "Longest caption", "p18.min_pause": "Pause that splits a phrase",
    "p18.from_client": "From {client}'s profile",
    "p18.correct.sub": "Uses {client}'s glossary ({n} terms) and rules.",
    "p18.rules": "Correction rules", "p18.glossary": "Glossary",
    "p18.bar": "Works on: {range}",
    "p18.trust": "Adds a new captions track. Your clips and audio stay untouched.",
    "p18.undo_hint": "You can take it back in one step: Edit > Undo in Premiere.",
    "p18.err.no_inout": "No In/Out is set on {seq}.",
    "p18.err.no_inout.hint": "Set In and Out in Premiere, or caption the whole sequence.",
    "p18.err.no_selection": "No clip is selected in the timeline.",
    "p18.err.no_selection.hint": "Select a clip in Premiere, or caption the whole sequence.",
    "p18.use_whole": "Use the whole sequence",
    "p18.empty.title": "No sequence open",
    "p18.empty": "Open a sequence in Premiere, then check again.",
    "p18.model_busy": "The captions pack is downloading · {pct}%",
    "p18.model_busy.sub": "Start waits for it. The smaller model works now: it's faster but less exact.",
    "p18.wait_pack": "Start turns on when the pack has downloaded.",
    "p18.no_claude": "Claude isn't signed in, so captions will be made without correction.",

    /* P-19 Kalam caption template gallery */
    "p19.search": "Search templates", "p19.all": "All folders", "p19.file": "From a file…", /* NEW */
    "p19.use": "Use this template",                                                 /* NEW */
    "p19.empty.title": "No templates found",                                       /* NEW */
    "p19.title": "Choose a caption template",
    "p19.count": "{n} templates",
    "p19.pick_first": "Pick a template first.",
    "p19.selected": "Selected",
    "p19.empty": "Add caption templates (.mogrt files) to Premiere's Local Templates folder, or pick one from a file.",
    "p19.no_text": "{name} has no editable text, so it can't hold captions.",
    "p19.no_text.hint": "Pick another template, or one from a file.",
    "p19.stale": "The templates folder changed since it was read.",
    "p19.refresh": "Refresh",

    /* P-20 Kalam progress and results */
    "p20.stage.loading": "Loading the model", "p20.stage.listening": "Listening",  /* NEW */
    "p20.stage.aligning": "Timing each word", "p20.stage.correcting": "Correcting the text", /* NEW */
    "p20.stage.captions": "Building captions",                                      /* NEW */
    "p20.srt": "SRT caption file, saved next to the project:",
    "p20.track_note": "To take it back, use Edit > Undo once in Premiere. Your clips and audio were not changed.",
    "p20.title": "Making captions",
    "p20.stage.export": "Exporting audio",
    "p20.stage.placing": "Placing captions in Premiere",
    "p20.device.gpu": "On the graphics card",
    "p20.running": "Timing each word · stage {n} of {of}",
    "p20.done": "{n} captions placed in {seq}.",
    "p20.value": "About 40 min of typing saved · estimate.",
    "p20.corrected": "Corrected with {client}'s rules and glossary.",
    "p20.reveal": "Show SRT file",
    "p20.fix": "Fix captions with Claude",
    "p20.list": "Captions",
    "p20.show_all": "Show all {n}",
    "p20.undo": "Remove the placed captions",
    "p20.undo.hint": "Removes the {n} template clips placed in the range. Nothing else changes.",
    "p20.error": "Timing each word failed: the graphics card ran out of memory.",
    "p20.error.hint": "Try again runs it on the processor. It's slower, about 2" + NB + "min.",
    "p20.lost": "The connection to the WhyNot Cut service was lost while listening.",
    "p20.lost.hint": "Start it, then press Try again. Nothing was placed in your sequence.",
    "p20.no_claude": "Claude isn't signed in, so Fix captions is off. Your captions are placed and saved.",

    /* A-01 After Effects home and motion pipeline */
    "a01.pill.host": "After Effects",                                               /* NEW */
    "a01.step.transcript": "Audio", "a01.step.plan": "Script and plan",            /* NEW */
    "a01.step.build": "Build in After Effects", "a01.step.frames": "Render and frames", /* NEW */
    "a01.empty.title": "No motion video yet",                                      /* NEW */
    "a01.empty": "Pick a part of an episode in Claude and it appears here.",       /* NEW */
    "a01.status.assembled": "Built and checked", "a01.status.unverified": "Built, not checked", /* NEW */
    "a01.current": "Motion video",
    "a01.other": "{n} more in this episode",
    "a01.status.approved": "Plan approved",
    "a01.next.title": "Next: build in After Effects",
    "a01.next.sub": "The plan is approved and every check below passed. WhyNot Cut builds the project, then checks it against the plan.",
    "a01.undo": "It makes a new After Effects project. Your footage and the Premiere project stay untouched.",
    "a01.start": "Start the build",
    "a01.checks": "Before the build",
    "a01.chk.approved": "Plan approved by {name}",
    "a01.chk.probe": "Arabic text checked in After Effects {v}",
    "a01.chk.fonts": "Client fonts installed",
    "a01.chk.saved": "No unsaved work in After Effects",
    "a01.open_aep": "Open project", "a01.reveal": "Show folder",
    "a01.empty.hint": "Claude opens in its own window, outside After Effects.",
    "a01.building": "Building in After Effects · scene {n} of {of}",
    "a01.cancel": "Cancel",
    "a01.error": "After the build, the project didn't match the plan: scene 5 has no title.",
    "a01.error.hint": "Try again builds it once more. If it fails again, contact support.",

    "a01.done": "Built and checked. Render the video next.",
    "a01.go_render": "Go to render",
    "a01.blocked": "The build can't start yet: 1 check needs you.",
    "a01.no_claude": "Claude isn't signed in, so the build can't start: Claude runs the checks and the build.",
    "a01.stale": "WhyNot Cut was updated. Close After Effects and open it again, then press Check again.",

    /* A-02 Motion plan approval */
    "a02.scenes": "Scenes",                                                         /* NEW */
    "a02.claude_line": "Claude's words, not the speaker's",                        /* NEW */
    "a02.numbers": "Confirm these numbers",                                        /* NEW */
    "a02.animatic": "Watch the animatic",                                          /* NEW */
    "a02.blocked": "Waiting for the claims review of this plan. Claude runs it, then Approve turns on.", /* NEW */
    "a02.title": "Check the motion plan",
    "a02.animatic.sub": "Storyboard and a rough animated cut, {d}.",
    "a02.type.title": "Title", "a02.type.number": "Number", "a02.type.quote": "Quote", "a02.type.list": "Icon list", "a02.type.end": "Ending",
    "a02.review": "Claims review",
    "a02.review.ok": "Reviewed for this plan: {n} lines approved.",
    "a02.review.note": "Scene 4 softened to “may help” instead of “treats”.",
    "a02.numbers.hint": "Numbers appear only as the speaker said them.",
    "a02.assets": "Icons, music and style",
    "a02.icons": "6 free icons, we may use them",
    "a02.music": "Music: Calm Pulse. Credit the artist in the post (it's in the publish pack).",
    "a02.recipe": "1 change from the usual style: no ending card.",
    "a02.pending": "Waiting",
    "a02.as": "Approving as {name}",
    "a02.approve": "Approve",
    "a02.tick": "Confirm both numbers to turn on Approve.",
    "a02.trust": "Approving changes nothing yet. The build later makes a new project; nothing you have is replaced.",
    "a02.changes.label": "What should change?",
    "a02.changes.placeholder": "Describe the changes you want",
    "a02.changes": "Request changes",
    "a02.failed": "Your approval wasn't saved.",
    "a02.failed.hint": "Try again. If it fails again, contact support.",
    "a02.plan_changed": "The plan changed. Review it and approve again.",
    "a02.empty": "No plan is waiting.",
    "a02.empty.text": "When Claude finishes a motion plan, it shows up here.",
    "a02.diff": "Scene 3 title shortened · music changed",
    "a02.done": "Approved. Start the build from Home.",
    "a02.done_by": "Approved by {name} · {time}",
    "a02.go_home": "Go to Home",
    "a02.no_claude": "Claude isn't signed in, so the claims review can't run and Approve stays off.",

    /* A-03 After Effects gates and Needs-you cards */
    "a03.probe": "Checking Arabic text in After Effects {version}. This happens once per version.", /* NEW */
    "a03.fonts": "Install the client's fonts, then restart After Effects.",       /* NEW */
    "a03.unsaved": "After Effects has unsaved changes. Save or close the project first.", /* NEW */
    "a03.edited": "You changed this project since the last build. A rebuild keeps a backup copy.", /* NEW */
    "a03.no_bridge": "WhyNot Cut can't reach After Effects. Restart it once, then press Check again.", /* NEW */
    "a03.script_only": "Built without a check, so it can't pass the quality check.", /* NEW */
    "a03.title": "Before the build",
    "a03.blocked": "The build starts once the cards above are sorted out.",
    "a03.sub": "Each card is one thing to sort out. The build can start when none is left.",
    "a03.probe.t": "Checking Arabic text", "a03.probe.meta": "Claude does this. Nothing to do.",
    "a03.fonts.t": "Fonts missing", "a03.fonts.list": "Missing: {fonts}", "a03.fonts.btn": "Open fonts folder",
    "a03.unsaved.t": "Unsaved work",
    "a03.edited.t": "You edited this project", "a03.rebuild": "Rebuild",
    "a03.no_bridge.t": "After Effects not reachable",
    "a03.script_only.t": "Built without a check",
    "a03.script_only.hint": "In Claude, ask for a checked build once After Effects is linked.",
    "a03.dialog.title": "Rebuild {item}?",
    "a03.dialog.c1": "The project is built again from the approved plan.",
    "a03.dialog.c2": "Your own changes in After Effects are not carried over.",
    "a03.dialog.backup": "Your edited project is kept as:",
    "a03.ok": "Arabic text checked in After Effects {version}. The build can start.",
    "a03.needs.title": "Needs you · {item}",
    "a03.need.music": "Choose the music: 3 tracks fit the mood.",
    "a03.need.numbers": "Confirm 2 numbers in the plan.",
    "a03.need.look": "The final look and the export are yours: colour, loudness and export settings.",
    "a03.need.music.btn": "Hear the tracks", "a03.need.numbers.btn": "Open the plan", "a03.need.look.btn": "Open project",
    "a03.no_claude": "Claude isn't signed in, so the Arabic text check can't run.",

    /* A-04 Motion render, frames and handoff */
    "a04.empty.title": "Nothing rendered yet",                                     /* NEW */
    "a04.progress": "Rendering · piece {n} of {of}",                               /* NEW */
    "a04.stale": "The project changed after the render. Render again.",            /* NEW */
    "a04.rendered": "Rendered. Check the frames.",                                 /* NEW */
    "a04.title": "Render and frames",
    "a04.empty": "Render the built project to an MP4, then check its frames.",
    "a04.render": "Render", "a04.render_again": "Render again",
    "a04.mp4": "Video file, in the motion project's folder:",
    "a04.cover": "Cover",
    "a04.frames": "Frames",
    "a04.frames.sub": "{n} frames from the render. Claude checks each one.",
    "a04.not_done": "It isn't done until the quality check passes.",
    "a04.v.verified": "Verified", "a04.v.not": "Not verified", "a04.v.needs": "Needs you",
    "a04.v.verified.t": "The built project matches the plan · a test render passed",
    "a04.v.not.t": "The quality check is still on 2 frames.",
    "a04.v.needs.t": "Final look and export, music choice.",
    "a04.v.not.fail": "Scene 5: the title touches the safe edge. Claude is fixing it.",
    "a04.rerender": "Re-render scenes",
    "a04.f.pass": "Pass", "a04.f.fix": "Claude is fixing", "a04.f.pending": "Claude is checking",
    "a04.error": "The render failed at piece 3: the D: drive is full.",
    "a04.error.hint": "Free up about 4" + NB + "GB on D:, then try again.",
    "a04.done": "Quality check passed. {item} is done.",
    "a04.value": "About 3 h of motion work saved · estimate.",
    "a04.handoff": "Handoff written: the editor notes and the publish package.",
    "a04.verdict": "Report",
    "a04.no_claude": "Claude isn't signed in, so the quality check can't look at the frames.",
    "p15.offline.hint": "Podcast sync is off. Undo still works.",
    "p17.offline.hint": "Undo still works: it only needs Premiere.",
    "p20.retry_wait": "Try again turns on once the service is running.",
    "a02.num.twice": "(twice in a row)",
    "a02.retry_first": "Try again first.",
    "a04.f.editor": "Needs your editor",
    "a04.f.stale": "Out of date",
    "a04.open_anyway": "Open anyway",
    "a04.wait_qc": "Wait for QC",
    "a04.wait_qc.hint": "Open project turns on when the quality check passes.",
    "p19.no_text.reason": "No editable text"
  });

  Object.assign(window.MOCK_STRINGS.ar, {
    /* group-wide (P-13) */
    "p13.title": "الأدوات",
    "p13.flow": "رتّب ← قطّع ← كابشن",
    "p13.flow.sub": "تلات خطوات ورا بعض. كل خطوة بتوريك المعاينة وبتسألك الأول.",
    "p13.need_project": "افتح مشروع في Premiere عشان تستخدم الأدوات.",
    "p13.model_busy": "حزمة الكابشن بتنزل · {pct}%",
    "p13.flow.eyebrow": "التلاتة بالترتيب",
    "p13.sequence": "السيكوينس: {name}",
    "p13.tidy.sub": "بينضّف المشروع ويرتّبه في فولدرات. وبيزامن البودكاست بالصوت.",
    "p13.hush.sub": "بيشيل السكتات وكلمات التردد.",
    "p13.kalam.sub": "كابشن مظبوط على الصوت: تراك أو قالب أو ملف SRT.",
    "p13.need_project.title": "مفيش مشروع مفتوح",
    "p13.open_project": "افتح مشروع",
    "p13.chip.downloading": "بتنزل",
    "p13.model_offer": "حزمة الكابشن لسه بتنزل. تقدر تبدأ دلوقتي بالنموذج الأصغر: أسرع بس أقل دقة.",
    "p13.use_small": "استخدم النموذج الأصغر",
    "p13.error": "مقدرناش نقرا المشروع المفتوح من Premiere.",
    "p13.error.hint": "جرّب تاني. لو فشلت تاني، احفظ المشروع واقفل Premiere وافتحه من جديد.",
    "p13.success": "الكابشن خلص: اتحط {n} كابشن في {seq}.",
    "p13.last": "آخر نتيجة: {text} · من {ago}",
    "p13.last.now": "آخر نتيجة: {text} · دلوقتي",
    "p13.none": "لسه مفيش.",
    "p13.last.tidy": "اترتّب 214 ملف", "p13.ago.tidy": "يوم",
    "p13.last.hush": "اتقطّع 24 قطعة", "p13.ago.hush": "ساعتين",
    "p13.kalam.last": "اتحط 64 كابشن",
    "p13.week": "الأسبوع ده الأدوات وفّرت حوالي ساعة و10 دقايق · تقدير.",
    "p13.back": "الأدوات",
    "p13.elapsed": "عدّى {t}",
    "p13.stop": "وقّف",
    "p13.done": "تمام",





    "p13.dialog.changes": "اللي هيتغيّر",
    "p13.dialog.keep": "خلّي مشروعي زي ما هو",
    "p16.show_words": "اعرض الكلمات ({n})",




    "p13.no_claude": "Claude مش مسجّل دخول. الأدوات شغالة، بس الكابشن هيتعمل من غير تصحيح لحد ما تسجّل دخول.",
    "p13.no_claude.solo": "Claude مش مسجّل دخول. مش محتاجه هنا: الأداة دي شغالة لوحدها.",

    /* P-14 */
    "p14.mode.reels": "ريلز", "p14.mode.podcast": "بودكاست",
    "p14.scan": "افحص المشروع",
    "p14.sec.remove": "هيتشال من المشروع",
    "p14.sec.remove_note": "من المشروع بس. ملفاتك فاضلة على الهارد.",
    "p14.sec.move": "هيتنقل للفولدرات",
    "p14.sec.nests": "أسامي جديدة للنستات",
    "p14.sec.offline": "ملفات مش موجودة (للعلم بس)",
    "p14.optin": "مش متعلّم عليها من الأول",
    "p14.apply": "نضّف ورتّب",
    "p14.dialog.backup": "المشروع هيتحفظ، وبعدين يتعمل منه نسخة باسم:",
    "p14.project": "المشروع",
    "p14.mode.hint.reels": "ريلز: فولدر لكل نوع ملفات.",
    "p14.mode.hint.podcast": "بودكاست: فولدر لكل كاميرا (Cam 1، Cam 2 …) والمايكات لوحدها.",
    "p14.rescan": "افحص تاني",
    "p14.empty.title": "لسه متفحصش",
    "p14.empty": "افحص المشروع عشان تشوف إيه اللي هيتنضّف. مفيش حاجة هتتغيّر قبل ما توافق.",
    "p14.scanning": "بنقرا المشروع · {n} من {of} عنصر",
    "p14.stat.items": "عنصر في المشروع", "p14.stat.size": "حجم الميديا",
    "p14.stat.remove": "هيتشال ({size})", "p14.stat.unused": "من حجم المشروع مش مستخدم",
    "p14.r.unused": "مش مستخدم في أي سيكوينس", "p14.r.duplicate": "نسخة مكررة مش مستخدمة",
    "p14.r.backup": "نسخة احتياطية قديمة من شيل السكتات أو الكابشن", "p14.r.captions": "ملفات كابشن",
    "p14.r.captions_note": "مش متعلّم عليها: Premiere مبيقولش أنهي واحد مستخدم.",
    "p14.r.cameras": "لقطات الكاميرات", "p14.r.mics": "تسجيلات المايكات", "p14.r.long": "تسجيلات 3" + NB + "دقايق أو أكتر",
    "p14.show_all": "اعرض الكل ({n})",
    "p14.nests.note": "الاسم من اللي جوه كل نست. شيل العلامة عشان يفضل الاسم القديم.",
    "p14.sec.bins": "فولدرات قديمة هتتشال",
    "p14.sec.dup": "ملفات مكررة ومستخدمة (للعلم بس)",
    "p14.offline.note": "مش موجودة في الفولدر بتاعها على الهارد. الترتيب مش هيلمسها.",
    "p14.sec.problems": "مشاكل",
    "p14.problem.1": "Interview_B-cam.mxf: الملف بايظ ومش بيفتح.",
    "p14.problem.2": "Nested Sequence 04: Premiere مقالش جواه إيه.",
    "p14.sec.options": "اللي هيحصل في المشروع",
    "p14.opt.remove": "شيل الحاجات المتعلّم عليها", "p14.opt.organise": "رتّب في فولدرات مع أسامي النستات",
    "p14.opt.colours": "لوّن كل نوع بلون ثابت",
    "p14.bar.summary": "{r} هيتشال · {m} هيتنقل · {n} اسم جديد",
    "p14.bar.hint": "ملفاتك على الهارد مش هتتلمس، وتقدر ترجّع كل حاجة زي ما كانت.",
    "p14.dialog.title": "تنضّف وترتّب {name}؟",
    "p14.dialog.c1": "{r} عنصر هيخرجوا من المشروع. الملفات فاضلة على الهارد.",
    "p14.dialog.c2": "{m} عنصر هيتنقلوا في {b} فولدرات.",
    "p14.dialog.c3": "{e} فولدرات فاضية هتتشال، و{n} نست هياخدوا أسامي جديدة.",
    "p14.dialog.c4": "كل نوع هياخد لونه الثابت.",
    "p14.unsaved": "المشروع ده عمره ما اتحفظ، فمش هنقدر نعمل له نسخة احتياطية.",
    "p14.unsaved.hint": "احفظه مرة في Premiere ‏(⁦File > Save⁩)، وبعدين دوس «افحص تاني».",
    "p14.error": "الترتيب ماقدرش يقرا عنصرين، فاتشالوا من الخطة.",
    "p14.error.hint": "هتلاقيهم تحت «مشاكل». باقي الخطة كامل.",
    "p14.stale": "المشروع اتغيّر من بعد الفحص. افحصه تاني قبل التنضيف.",

    /* P-15 */
    "p15.done": "المشروع اترتّب. النسخة القديمة محفوظة.",

    "p15.sync": "زامن البودكاست بالصوت",
    "p15.sync.progress": "بنطابق الكليب {n} من {of} · {name}",
    "p15.sync.skipped": "اتساب برّه: {name} (مفيش تطابق واضح في الصوت)",
    "p15.sync.done": "السيكوينس المتزامن جاهز: {name}",
    "p15.applying": "بننضّف المشروع · {n} من {of}",
    "p15.value": "وفّرت حوالي 25 دقيقة ترتيب · تقدير.",
    "p15.counts": "اللي حصل في المشروع",
    "p15.moved": "اتنقل للفولدرات", "p15.removed": "اتشال من المشروع", "p15.renamed": "نستات اتغيّر اسمها",
    "p15.bins": "فولدرات فاضية اتشالت",
    "p15.skipped": "{s} من {r} عنصر فضلوا لأنهم طلعوا مستخدمين.",
    "p15.where": "الحاجات راحت فين",

    "p13.sec": "{n}" + NB + "ثانية",
    "p15.backup.title": "رجّع كل حاجة",
    "p15.undo.hint": "بيفتح النسخة اللي اتحفظت قبل التنضيف، زي ما كانت بالظبط. والمشروع المترتّب بيفضل موجود.",
    "p15.reveal": "اعرضها في الفولدر",
    "p15.sync.title": "مزامنة البودكاست",
    "p15.sync.sub": "بيظبط كل كاميرا ومايك على الصوت ويعمل سيكوينس مالتي كام جديد. الكليبات بتاعتك بتفضل زي ما هي.",
    "p15.sync.found": "لقينا {c} كاميرات و{m} مايكات.",
    "p15.sync.placed": "اتحط {n} من {of} كليبات.",
    "p15.sync.skip_hint": "حطّه بإيدك، أو سجّل تصفيقة في الأول المرة الجاية.",
    "p15.open_seq": "افتح السيكوينس المتزامن",
    "p15.error": "كليب واحد مقدرناش نصدّره، فاتساب برّه: {name}",
    "p15.error.hint": "الستة التانيين اتزامنوا. ممكن الملف يكون مفتوح في برنامج تاني: اقفله وجرّب تاني.",
    "p15.retry_clip": "جرّب الكليب ده تاني",


    /* P-16 */
    "p16.target": "الهدف: {label}",
    "p16.scan": "افحص",
    "p16.soft": "خفيف", "p16.medium": "متوسط", "p16.strong": "قوي",
    "p16.strength": "القوة",
    "p16.fillers": "كلمات التردد",
    "p16.counts": "{s} سكتة + {f} كلمة تردد",
    "p16.mode.cut": "قطّع", "p16.mode.markers": "ماركرز بس",
    "p16.go": "قطّع", "p16.markers.go": "حط ماركرز",
    "p16.track_locked": "فيه تراك متعلّم عليه ومقفول: {track}. متقطّعش حاجة.",
    "p16.not_moving": "التراكات دي مش هتتحرك: {tracks}",
    "p16.target.whole": "السيكوينس كله",
    "p16.target.hint": "حدّد كليبات أو حط ⁦In/Out⁩ في Premiere عشان تضيّقه.",
    "p16.tracks": "التراكات",
    "p16.rescan": "افحص تاني",
    "p16.empty": "افحص النطاق عشان تشوف السكتات.",
    "p16.strength.title": "هنقطّع قد إيه",
    "p16.simple": "بسيط", "p16.advanced": "متقدم",
    "p16.tight": "قطع مظبوط (من غير هامش حوالين الكلام)",
    "p16.threshold": "الصمت أقل من", "p16.min": "أقصر سكتة",
    "p16.pad_before": "هامش قبل الكلام", "p16.pad_after": "هامش بعد الكلام",
    "p16.link_pads": "نفس الهامش قبل وبعد",
    "p16.fillers.on": "شيل كلمات التردد",
    "p16.lang": "لغة الكلام", "p16.lang.auto": "تلقائي", "p16.lang.en": "إنجليزي", "p16.lang.ar": "عربي",
    "p16.list.strong": "بتتشال على طول", "p16.list.soft": "اسألني الأول (غالبًا كلام حقيقي)",
    "p16.sounds": "أصوات مش واضحة (نَفَس وطقطقة)",
    "p16.off": "واقفة",
    "p16.fillers.off": "كلمات التردد محتاجة خدمة WhyNot Cut. السكتات تقدر تتشال من غيرها.",
    "p16.wave": "المعاينة",
    "p16.legend.sil": "{n} سكتة", "p16.legend.fil": "{n} كلمة تردد",
    "p16.wave.hint": "دوس على الموجة عشان تحرّك البلاي هيد هناك.",
    "p16.summary.title": "النتيجة",
    "p16.before": "قبل", "p16.after": "بعد", "p16.saved": "الفرق",
    "p16.in_force": "الإعدادات: {v}",
    "p16.options": "طريقة القطع",
    "p16.ripple": "اقفل الفراغات بعد القطع",
    "p16.link": "خلّي الصوت مربوط بالصورة",

    "p16.presets": "الإعداد المحفوظ: Sahha talking head",
    "p16.save_preset": "احفظ الإعداد",
    "p16.bar": "هيقطّع {n} قطعة · أقصر {t}",
    "p16.bar.trust": "بنحفظ نسخة احتياطية من السيكوينس الأول دايمًا.",
    "p16.bar.markers": "هيحط {n} ماركر. مفيش حاجة هتتقطّع.",
    "p16.dialog.title": "تقطّع {n} قطعة من {seq}؟",
    "p16.dialog.c1": "هيتشال {s} سكتة و{f} كلمة تردد.",
    "p16.dialog.c2": "الفراغات هتتقفل، فكل اللي بعد القطع هيقدّم.",
    "p16.dialog.c3": "التراكات اللي هتتحرك: {tracks}",
    "p16.dialog.backup": "السيكوينس هيتنسخ الأول باسم:",
    "p16.dialog.keep": "خلّي السيكوينس زي ما هو",
    "p16.dialog.nobackup": "النسخة الاحتياطية ماتعملتش المرة دي. من غيرها، الرجوع الوحيد هو ⁦Edit > Undo⁩ في Premiere.",
    "p16.stage.export": "بنصدّر الصوت من Premiere",
    "p16.stage.silence": "بندوّر على السكتات",
    "p16.stage.fillers": "بندوّر على كلمات التردد",
    "p16.scanning": "{stage} · خطوة {n} من {of}",
    "p16.locked.hint": "شيل العلامة من هنا، أو افتح القفل في Premiere وافحص تاني.",
    "p16.untick": "شيل علامة {track}",
    "p16.stale": "السيكوينس اتغيّر من بعد الفحص. افحص تاني.",

    /* P-17 */
    "p17.result": "اتقطّع {n} قطعة. السيكوينس بقى أقصر {time}.",
    "p17.value": "اتقطّع {n} قطعة · وفّرت حوالي {m} دقايق مونتاج · تقدير",
    "p17.backup": "نسختك الأصلية محفوظة زي ما هي باسم:",

    "p17.markers": "اتحط {n} ماركر. متقطّعش حاجة.",
    "p17.undo.hint": "بيرجّع الأصل باسمه، والنسخة المتقطّعة بتتحفظ باسم:",
    "p17.reveal": "اعرضه في المشروع",
    "p17.clear": "امسح ماركرز شيل السكتات",
    "p17.markers.hint": "كل ماركر على سكتة أو كلمة تردد، عشان تقطّع بإيدك.",
    "p17.partial": "اتقطّع {n} من {of} قطعة. {k} اتسابوا.",
    "p17.partial.hint": "موجودين على V2 وفيه كليب مقفول. افتح القفل في Premiere وقطّع الباقي.",
    "p17.cut_rest": "قطّع اللي اتساب",
    "p17.undone": "رجع {name}. النسخة المتقطّعة محفوظة باسم:",


    /* P-18 */
    "p18.lang": "اللغة", "p18.lang.ar": "عربي", "p18.lang.en": "إنجليزي", "p18.lang.other": "لغة تانية",
    "p18.range": "النطاق", "p18.range.sequence": "السيكوينس كله", "p18.range.playhead": "من البلاي هيد",
    "p18.range.selection": "الكليبات المحدّدة", "p18.audio": "تراكات الصوت",
    "p18.output.srt": "ملف SRT بس",
    "p18.correct": "صحّح الكلام مع Claude",
    "p18.start": "ابدأ",
    "p18.model.ar": "مظبوط على العامية المصرية، وكل كلمة متوقّتة",
    "p18.range.inout": "من In لحد Out",
    "p18.range.inout.sub": "من {a} لحد {b}",
    "p18.audio.hint": "هنسمع التراكات المتعلّم عليها بس.",
    "p18.output": "الكابشن يطلع على شكل",
    "p18.output.track": "تراك كابشن",
    "p18.output.mogrt": "قالب كابشن",
    "p18.output.mogrt.sub": "قالب موشن جرافيك من Premiere (ملف mogrt)",
    "p18.srt_always": "ملف كابشن SRT بيتحفظ دايمًا جنب المشروع.",
    "p18.change": "غيّر",
    "p18.vtrack": "تراك الفيديو", "p18.textfield": "خانة الكلام",
    "p18.settings": "إعدادات الكابشن",
    "p18.max_chars": "عدد الحروف في السطر", "p18.max_lines": "عدد السطور",
    "p18.max_secs": "أطول كابشن", "p18.min_pause": "الوقفة اللي بتفصل الجملة",
    "p18.from_client": "من ملف {client}",
    "p18.correct.sub": "بيستخدم قاموس {client} ‏({n} كلمة) وقواعده.",
    "p18.rules": "قواعد التصحيح", "p18.glossary": "القاموس",
    "p18.bar": "هيشتغل على: {range}",
    "p18.trust": "هيضيف تراك كابشن جديد. الكليبات والصوت بتوعك مش هيتلمسوا.",
    "p18.undo_hint": "تقدر ترجع بخطوة واحدة: ⁦Edit > Undo⁩ في Premiere.",
    "p18.err.no_inout": "مفيش In وOut على {seq}.",
    "p18.err.no_inout.hint": "حط In وOut في Premiere، أو اعمل كابشن للسيكوينس كله.",
    "p18.err.no_selection": "مفيش كليب محدّد في التايم لاين.",
    "p18.err.no_selection.hint": "حدّد كليب في Premiere، أو اعمل كابشن للسيكوينس كله.",
    "p18.use_whole": "استخدم السيكوينس كله",
    "p18.empty.title": "مفيش سيكوينس مفتوح",
    "p18.empty": "افتح سيكوينس في Premiere، وبعدين افحص تاني.",
    "p18.model_busy": "حزمة الكابشن بتنزل · {pct}%",
    "p18.model_busy.sub": "«ابدأ» مستني الحزمة. النموذج الأصغر شغال دلوقتي: أسرع بس أقل دقة.",
    "p18.wait_pack": "«ابدأ» هيشتغل أول ما الحزمة تخلص.",
    "p18.no_claude": "Claude مش مسجّل دخول، فالكابشن هيتعمل من غير تصحيح.",

    /* P-19 */
    "p19.search": "دوّر في القوالب", "p19.all": "كل الفولدرات", "p19.file": "من ملف…",
    "p19.use": "استخدم القالب ده",
    "p19.empty.title": "ملقيناش قوالب",
    "p19.title": "اختار قالب الكابشن",
    "p19.count": "{n} قالب",
    "p19.pick_first": "اختار قالب الأول.",
    "p19.selected": "متختار",
    "p19.empty": "حط قوالب كابشن (ملفات mogrt) في فولدر Local Templates في Premiere، أو اختار واحد من ملف.",
    "p19.no_text": "القالب {name} مفيهوش كلام يتعدّل، فمينفعش للكابشن.",
    "p19.no_text.hint": "اختار قالب تاني، أو واحد من ملف.",
    "p19.stale": "فولدر القوالب اتغيّر من ساعة ما اتقرا.",
    "p19.refresh": "حدّث القايمة",

    /* P-20 */
    "p20.stage.loading": "تحميل النموذج", "p20.stage.listening": "بنسمع",
    "p20.stage.aligning": "توقيت كل كلمة", "p20.stage.correcting": "تصحيح الكلام",
    "p20.stage.captions": "تقسيم الكابشن",
    "p20.srt": "ملف كابشن SRT، محفوظ جنب المشروع:",
    "p20.track_note": "عشان ترجع، استخدم ⁦Edit > Undo⁩ مرة واحدة في Premiere. الكليبات والصوت متغيّروش.",
    "p20.title": "بنعمل الكابشن",
    "p20.stage.export": "تصدير الصوت",
    "p20.stage.placing": "حط الكابشن في Premiere",
    "p20.device.gpu": "على كارت الشاشة",
    "p20.running": "توقيت كل كلمة · مرحلة {n} من {of}",
    "p20.done": "اتحط {n} كابشن في {seq}.",
    "p20.value": "وفّرت حوالي 40 دقيقة كتابة · تقدير.",
    "p20.corrected": "اتصحّح بقواعد {client} وقاموسه.",
    "p20.reveal": "اعرض ملف SRT",
    "p20.fix": "صلّح الكابشن مع Claude",
    "p20.list": "الكابشن",
    "p20.show_all": "اعرض الكل ({n})",
    "p20.undo": "امسح الكابشن اللي اتحط",
    "p20.undo.hint": "بيمسح {n} كليب قالب اتحطوا في النطاق. ومفيش حاجة تانية بتتغيّر.",
    "p20.error": "توقيت الكلمات فشل: ذاكرة كارت الشاشة خلصت.",
    "p20.error.hint": "«جرّب تاني» هيشغّله على البروسيسور. أبطأ، حوالي 2" + NB + "دقيقة.",
    "p20.lost": "الاتصال بخدمة WhyNot Cut اتقطع وإحنا بنسمع.",
    "p20.lost.hint": "شغّلها ودوس «جرّب تاني». مفيش حاجة اتحطت في السيكوينس.",
    "p20.no_claude": "Claude مش مسجّل دخول، عشان كده «صلّح الكابشن» واقف. الكابشن اتحط واتحفظ.",

    /* A-01 */
    "a01.pill.host": "After Effects",
    "a01.step.transcript": "الصوت", "a01.step.plan": "السكريبت والخطة",
    "a01.step.build": "البناء في After Effects", "a01.step.frames": "الريندر ومراجعة الصور",
    "a01.empty.title": "لسه مفيش فيديو موشن",
    "a01.empty": "اختار جزء من حلقة في Claude وهيظهر هنا.",
    "a01.status.assembled": "اتبنى واتراجع", "a01.status.unverified": "اتبنى من غير مراجعة",
    "a01.current": "فيديو الموشن",
    "a01.other": "{n} كمان في الحلقة دي",
    "a01.status.approved": "الخطة متوافق عليها",
    "a01.next.title": "اللي جاي: البناء في After Effects",
    "a01.next.sub": "الخطة متوافق عليها وكل الفحوصات تحت عدّت. WhyNot Cut هيبني المشروع ويطابقه مع الخطة.",
    "a01.undo": "هيعمل مشروع After Effects جديد. الفوتيج ومشروع Premiere مش هيتلمسوا.",
    "a01.start": "ابدأ البناء",
    "a01.checks": "قبل البناء",
    "a01.chk.approved": "{name} وافق على الخطة",
    "a01.chk.probe": "الكلام العربي اتراجع في After Effects {v}",
    "a01.chk.fonts": "خطوط العميل متسطّبة",
    "a01.chk.saved": "مفيش شغل مش محفوظ في After Effects",
    "a01.open_aep": "افتح المشروع", "a01.reveal": "افتح الفولدر",
    "a01.empty.hint": "Claude بيفتح في شباك لوحده برّه After Effects.",
    "a01.building": "بنبني في After Effects · مشهد {n} من {of}",
    "a01.cancel": "إلغاء",
    "a01.error": "بعد البناء، المشروع مطابقش الخطة: مشهد 5 من غير عنوان.",
    "a01.error.hint": "«جرّب تاني» هيبنيه مرة كمان. لو فشل تاني، كلّم الدعم.",

    "a01.done": "اتبنى واتراجع. اللي جاي: الريندر.",
    "a01.go_render": "روح للريندر",
    "a01.blocked": "البناء مش هيبدأ لسه: فيه فحص واحد محتاجك.",
    "a01.no_claude": "Claude مش مسجّل دخول، فالبناء مش هيبدأ: Claude هو اللي بيعمل الفحوصات والبناء.",
    "a01.stale": "WhyNot Cut اتحدّث. اقفل After Effects وافتحه تاني، وبعدين دوس «افحص تاني».",

    /* A-02 */
    "a02.scenes": "المشاهد",
    "a02.claude_line": "كلام Claude مش كلام المتكلم",
    "a02.numbers": "أكّد الأرقام دي",
    "a02.animatic": "اتفرّج على النسخة التجريبية",
    "a02.blocked": "مستنيين مراجعة الجمل الطبية للخطة دي. Claude بيعملها، وبعدها «وافق» هيشتغل.",
    "a02.title": "راجع خطة الموشن",
    "a02.animatic.sub": "ستوري بورد ونسخة متحركة أولية، {d}.",
    "a02.type.title": "عنوان", "a02.type.number": "رقم", "a02.type.quote": "اقتباس", "a02.type.list": "لستة بأيقونات", "a02.type.end": "خاتمة",
    "a02.review": "مراجعة الجمل الطبية",
    "a02.review.ok": "اتراجعت للخطة دي: {n} سطور متوافق عليها.",
    "a02.review.note": "مشهد 4 اتخفّف وبقى «ممكن يساعد» بدل «بيعالج».",
    "a02.numbers.hint": "الأرقام بتظهر زي ما المتكلم قالها بالظبط.",
    "a02.assets": "الأيقونات والموسيقى والستايل",
    "a02.icons": "6 أيقونات مجانية، مسموح نستخدمها",
    "a02.music": "الموسيقى: Calm Pulse. لازم تكتب اسم الفنان في البوست (مكتوب في حزمة النشر).",
    "a02.recipe": "تغيير واحد عن الستايل المعتاد: من غير كارت ختام.",
    "a02.pending": "مستني",
    "a02.as": "هتوافق باسم {name}",
    "a02.approve": "وافق",
    "a02.tick": "أكّد الرقمين عشان «وافق» يشتغل.",
    "a02.trust": "الموافقة مش بتغيّر حاجة دلوقتي. البناء بعدين بيعمل مشروع جديد، ومفيش حاجة عندك بتتبدّل.",
    "a02.changes.label": "عايز تغيّر إيه؟",
    "a02.changes.placeholder": "اكتب التعديلات اللي عايزها",
    "a02.changes": "اطلب تعديلات",
    "a02.failed": "موافقتك متسجلتش.",
    "a02.failed.hint": "جرّب تاني. لو فشلت تاني، كلّم الدعم.",
    "a02.plan_changed": "الخطة اتغيّرت. راجعها ووافق تاني.",
    "a02.empty": "مفيش خطة مستنياك.",
    "a02.empty.text": "لما Claude يخلّص خطة موشن، هتظهر هنا.",
    "a02.diff": "عنوان مشهد 3 اتقصّر · الموسيقى اتغيّرت",
    "a02.done": "اتوافق. ابدأ البناء من الرئيسية.",
    "a02.done_by": "وافق {name} · {time}",
    "a02.go_home": "روح للرئيسية",
    "a02.no_claude": "Claude مش مسجّل دخول، فمراجعة الجمل الطبية مش هتتعمل و«وافق» هيفضل واقف.",

    /* A-03 */
    "a03.probe": "بنراجع الكلام العربي في After Effects {version}. ده بيحصل مرة واحدة لكل نسخة.",
    "a03.fonts": "سطّب خطوط العميل، وبعدين اقفل After Effects وافتحه تاني.",
    "a03.unsaved": "في After Effects تعديلات مش محفوظة. احفظ المشروع أو اقفله الأول.",
    "a03.edited": "إنت عدّلت المشروع ده من آخر بناء. إعادة البناء بتحتفظ بنسخة احتياطية.",
    "a03.no_bridge": "WhyNot Cut مش قادر يكلّم After Effects. اقفله وافتحه مرة، وبعدين دوس «افحص تاني».",
    "a03.script_only": "اتبنى من غير مراجعة، فمش هيعدّي فحص الجودة.",
    "a03.title": "قبل البناء",
    "a03.blocked": "البناء هيبدأ أول ما الكروت اللي فوق تتحل.",
    "a03.sub": "كل كارت حاجة واحدة محتاجة تتحل. البناء يقدر يبدأ لما ميفضلش ولا واحد.",
    "a03.probe.t": "مراجعة الكلام العربي", "a03.probe.meta": "Claude بيعمل ده. مفيش حاجة مطلوبة منك.",
    "a03.fonts.t": "خطوط ناقصة", "a03.fonts.list": "الناقص: {fonts}", "a03.fonts.btn": "افتح فولدر الخطوط",
    "a03.unsaved.t": "شغل مش محفوظ",
    "a03.edited.t": "إنت عدّلت المشروع ده", "a03.rebuild": "ابنيه تاني",
    "a03.no_bridge.t": "After Effects مش متوصّل",
    "a03.script_only.t": "اتبنى من غير مراجعة",
    "a03.script_only.hint": "في Claude، اطلب بناء بمراجعة بعد ما After Effects يتوصّل.",
    "a03.dialog.title": "تبني {item} تاني؟",
    "a03.dialog.c1": "المشروع هيتبني من جديد من الخطة المتوافق عليها.",
    "a03.dialog.c2": "تعديلاتك في After Effects مش هتتنقل.",
    "a03.dialog.backup": "مشروعك المتعدّل هيتحفظ باسم:",
    "a03.ok": "الكلام العربي اتراجع في After Effects {version}. البناء يقدر يبدأ.",
    "a03.needs.title": "مطلوب منك · {item}",
    "a03.need.music": "اختار الموسيقى: فيه 3 تراكات تناسب الجو.",
    "a03.need.numbers": "أكّد رقمين في الخطة.",
    "a03.need.look": "الشكل النهائي والتصدير عليك: الألوان وعلو الصوت وإعدادات التصدير.",
    "a03.need.music.btn": "اسمع التراكات", "a03.need.numbers.btn": "افتح الخطة", "a03.need.look.btn": "افتح المشروع",
    "a03.no_claude": "Claude مش مسجّل دخول، فمراجعة الكلام العربي مش هتتعمل.",

    /* A-04 */
    "a04.empty.title": "لسه متعملش ريندر",
    "a04.progress": "ريندر · جزء {n} من {of}",
    "a04.stale": "المشروع اتغيّر بعد الريندر. اعمل ريندر تاني.",
    "a04.rendered": "الريندر خلص. راجع الصور.",
    "a04.title": "الريندر ومراجعة الصور",
    "a04.empty": "اعمل ريندر MP4 للمشروع المبني، وبعدين راجع صوره.",
    "a04.render": "اعمل ريندر", "a04.render_again": "ريندر تاني",
    "a04.mp4": "ملف الفيديو، في فولدر مشروع الموشن:",
    "a04.cover": "الغلاف",
    "a04.frames": "الصور",
    "a04.frames.sub": "{n} صور من الريندر. Claude بيراجع كل واحدة.",
    "a04.not_done": "الشغل مش خالص غير لما فحص الجودة يعدّي.",
    "a04.v.verified": "اتراجع", "a04.v.not": "لسه متراجعش", "a04.v.needs": "مطلوب منك",
    "a04.v.verified.t": "المشروع المبني مطابق للخطة · ريندر تجريبي عدّى",
    "a04.v.not.t": "فحص الجودة لسه على صورتين.",
    "a04.v.needs.t": "الشكل النهائي والتصدير، واختيار الموسيقى.",
    "a04.v.not.fail": "مشهد 5: العنوان لامس حافة الأمان. Claude بيصلّحه.",
    "a04.rerender": "ريندر لمشاهد",
    "a04.f.pass": "سليمة", "a04.f.fix": "Claude بيصلّحها", "a04.f.pending": "Claude بيراجعها",
    "a04.error": "الريندر فشل عند الجزء 3: هارد D: مليان.",
    "a04.error.hint": "فضّي حوالي 4" + NB + "GB على D:، وجرّب تاني.",
    "a04.done": "فحص الجودة عدّى. {item} خلص.",
    "a04.value": "وفّرت حوالي 3 ساعات شغل موشن · تقدير.",
    "a04.handoff": "التسليم اتكتب: ملاحظات المونتير وحزمة النشر.",
    "a04.verdict": "التقرير",
    "a04.no_claude": "Claude مش مسجّل دخول، ففحص الجودة مش هيقدر يراجع الصور.",
    "p15.offline.hint": "مزامنة البودكاست واقفة. «تراجع» لسه شغال.",
    "p17.offline.hint": "الرجوع لسه شغال: محتاج Premiere بس.",
    "p20.retry_wait": "«جرّب تاني» هيشتغل أول ما الخدمة تشتغل.",
    "a02.num.twice": "(مرتين ورا بعض)",
    "a02.retry_first": "جرّب تاني الأول.",
    "a04.f.editor": "محتاجة المونتير",
    "a04.f.stale": "قديمة",
    "a04.open_anyway": "افتح المشروع برضه",
    "a04.wait_qc": "استنى فحص الجودة",
    "a04.wait_qc.hint": "«افتح المشروع» هيشتغل أول ما فحص الجودة يعدّي.",
    "p19.no_text.reason": "مفيهوش كلام يتعدّل"
  });

  /* Data shown in this group's screens (not UI copy). Arabic lines are as said (Arabic in both UIs). File names only:
     no paths in body copy (Addendum G); the folder opens with Show in folder. */
  window.MOCK_DATA.ta = {
    seq: "C0239_main", project: "Sahha_C0239.prproj", projectName: "Sahha_C0239",
    tidyBackup: "Sahha_C0239 (WhyNot Tidy backup 2026-10-13 154210).prproj",
    hushBackup: "C0239_main (WhyNot Hush backup 15:42:10)", hushCut: "C0239_main (WhyNot Hush cut 15:42:10)",
    srt: "C0239_main.srt",
    motion: "EP12_03_MO", aeVersion: "25.4", aep: "EP12_03_MO.aep",
    aeBackup: "EP12_03_MO (WhyNot backup 2026-10-13 1542).aep",
    mp4: "EP12_03_MO.mp4",
    approvedAt: "13 Oct 2026 · 14:32",
    long: {
      seq: "C0239_interview_final_v2_master_sequence_for_reels",
      project: "Al-Mustaqbal_Family_Medicine_C0239_interview_final_v2.prproj",
      projectName: "Al-Mustaqbal_Family_Medicine_C0239_interview_final_v2",
      tidyBackup: "Al-Mustaqbal_Family_Medicine_C0239_interview_final_v2 (WhyNot Tidy backup 2026-10-13 154210).prproj",
      hushBackup: "C0239_interview_final_v2_master_sequence_for_reels (WhyNot Hush backup 15:42:10)",
      hushCut: "C0239_interview_final_v2_master_sequence_for_reels (WhyNot Hush cut 15:42:10)",
      srt: "C0239_interview_final_v2_master_sequence_for_reels.srt",
      motion: "EP127_014_Al-Mustaqbal_MO", aep: "EP127_014_Al-Mustaqbal_MO.aep",
      aeBackup: "EP127_014_Al-Mustaqbal_MO (WhyNot backup 2026-10-13 1542).aep",
      mp4: "EP127_014_Al-Mustaqbal_MO.mp4"
    },
    bins: [["01 Footage", 96], ["03 Audio/Music", 24], ["04 Images/PNG", 61], ["06 Sequences", 33]],
    captions: [
      ["00:12.40", "قياس السكر الصايم الصبح"],
      ["00:14.10", "بيقولك أكتر من أي قراية تانية في اليوم"],
      ["00:17.02", "عشان كده بنقيسه قبل الفطار"],
      ["00:19.60", "ومن غير ما تشرب أي حاجة غير مية"],
      ["00:22.35", "لو القراية فوق 126 مرتين ورا بعض"],
      ["00:25.10", "لازم تكشف عند الدكتور على طول"]
    ],
    longCaption: "والكلام ده مش معناه إنك توقف العلاج من نفسك، لكن معناه إنك تسأل دكتورك وتراجع الجرعة معاه كل شهر لحد ما القراية تستقر",
    scenes: [
      { tc: "00:00–00:04", type: "title", text: "قياس السكر الصبح", claude: true },
      { tc: "00:04–00:11", type: "quote", text: "قياس السكر الصايم الصبح بيقولك أكتر من أي قراية تانية في اليوم." },
      { tc: "00:11–00:19", type: "number", text: "فوق 126 مرتين ورا بعض" },
      { tc: "00:19–00:28", type: "list", text: "قبل الفطار · مية بس · نفس الميعاد كل يوم", claude: true },
      { tc: "00:28–00:34", type: "end", text: "اسأل دكتورك قبل ما تغيّر علاجك" }
    ],
    numbers: [["126", "mg/dL", "00:11", ""], ["2", "", "00:14", "a02.num.twice"]]
  };
})();
