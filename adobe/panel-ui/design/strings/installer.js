/* Installer copy (I-01 to I-09), EN and AR, merged into window.MOCK_STRINGS. Origins, marked per block:
   I18N = verbatim from adobe/panel-ui/i18n (none of the installer copy exists there yet; shared keys come from
          ../strings.js);
   NEW  = a NEW key of docs/design/screen-inventory.md §5 kept in meaning (its inventory key in the comment); the
          inventory's MSA Arabic is replaced by the Egyptian register below;
   MOCK = written for these mockups;
   MOCK-VERIFY = a product fact the executor must confirm before shipping (agency-owner review, G2-r1 (c)); none is left for
          the owner decisions D-01 to D-05, which are applied verbatim (see below).
   Rules applied:
   - E-D3 r1: one Arabic verb per action, no tatweel, no English gloss, U+00A0 inside unit and time phrases, every
     failure names what failed and the next step, never "Claude Code";
   - G2-r1 agency owner: professional EGYPTIAN Arabic everywhere (not MSA); the background program is
     "WhyNot Cut service" / «خدمة WhyNot Cut» (never engine / app / المحرّك); trust copy says exactly what Setup adds
     and where; every failure card offers Contact support + Save a report for support;
   - Addendum G (G2/G10/G11): no developer words (checksum, signature, JSON, engine, ffmpeg, PATH ...): security facts
     are said plainly ("Checked: the genuine file from WhyNot Cut"); every fault says what happened, why, and one fix;
     macOS is the primary platform (its copy is the default; Windows-only copy is marked win).
   - R2 pass (installer group): titles follow the state, no raw paths or file names in primary text, one Close look, no
     developer words (Homebrew, Xcode, Gatekeeper); the owner decisions are applied verbatim: Claude plan and cost D-01
     (shared key claude.cost in ../strings.js, with a "See plans" link), data handling D-02 (claude.data), privacy line D-03,
     signing D-04 = BETA ONLY, support D-05 (support.copy / support.copy_open / support.soon / support.promise).
   - H24: the support and "Cost and data" pages are linked only when live (mockup.js M.live): not live = "Copy details for
     support" copies only and a plain-text "Support page coming soon" sits beside it.
     R3 (D-05 update 2026-10-16): the support chat is WhatsApp and live, so every failure card shows "Copy details and
     open WhatsApp" + the reply promise by default; the copy-only state is the ?support=off alternate.
   Every MOCK line needs the string-table owner; every Arabic line needs a native writer (direction §11 draft). */
(function () {
  var NB = "\u00A0";
  window.I_GB = function (n, ar) { return n + NB + (ar ? "جيجا" : "GB"); };
  window.I_MB = function (n, ar) { return n + NB + (ar ? "ميجا" : "MB"); };
  var en = {
    /* shell */
    "i00.setup": "Setup",
    "i00.wintitle": "WhyNot Cut Setup",
    "i00.internal": "Internal build", /* NEW inst.internal */
    "i00.version": "{app}",
    "i00.signed": "Genuine Setup from The" + NB + "Why" + NB + "Not",
    "i00.unsigned": "Beta test build. For testing only.", /* BETA ONLY (owner decision D-04): the paid edition ships signed; this line is never shown to a customer */
    "i00.stage.welcome": "Welcome", "i00.stage.custom": "Your choices", "i00.stage.check": "Check this computer",
    "i00.stage.claude": "Claude", "i00.stage.install": "Install", "i00.stage.finish": "Finish",
    "i00.stage.update": "Update", "i00.stage.choose": "What goes", "i00.stage.remove": "Remove", "i00.stage.done": "Done",
    "i00.back": "Back", /* NEW inst.back */
    "i00.continue": "Continue", /* NEW inst.continue */
    "i00.close": "Close", /* NEW inst.close */
    "i00.cancel": "Cancel", /* NEW inst.cancel */
    "i00.next": "Next",
    "i00.retry": "Try again",
    "i00.check_again": "Check again",
    "i00.offline_get": "Get the offline installer",
    "i00.save_report": "Save a report for support",
    "i00.report_note": "The report is saved on this computer without personal details. Nothing is sent unless you send it.",
    "i00.min": "{n}" + NB + "min",
    "i00.service": "WhyNot Cut service",
    /* I-01 Welcome */
    "i01.eyebrow": "Version {version}",
    "i01.title": "Install WhyNot Cut", /* NEW inst.welcome.title */
    "i01.text": "Everything WhyNot Cut needs, in one go (about {gb}).", /* NEW inst.welcome.text */
    "i01.fact.disk": "{free} free on {drive}",
    "i01.fact.user": "Just for you. No admin password and no developer tools.", /* R2 E-P2-17 */
    "i01.fact.user.win": "For you only. No administrator rights needed.", /* MOCK from inst.welcome.no_admin */
    "i01.fact.private": "Setup sends nothing from your computer.", /* R2 G-F-14: scoped to Setup; what Claude reads is said on I-05 */
    "i01.fact.visible": "Every step is shown here and written to a log.",
    "i01.adds": "Setup adds 6 things, all inside your user folder. Uninstall removes all of them and never touches your client folders.",
    "i01.adds.show": "See what goes where",
    "i01.adds.hide": "Hide the list",
    "i01.install": "Install everything", /* NEW inst.welcome.install */
    "i01.customise": "Customise", /* NEW inst.welcome.customise */
    "i01.offline": "Installs without internet. Claude and signing in need it later.", /* R2 D-P1-12 */
    "i01.upgrade": "{app} is installed. This updates it, and your clients and settings stay.", /* NEW inst.welcome.upgrade */
    "i01.internal": "This beta test build hasn't been checked by Apple or Microsoft. Use it for testing only; never send it to clients.", /* BETA ONLY (D-04) */
    "i01.noclaude": "Claude isn't on this computer yet. Setup installs it for you after the check.",
    "i01.error": "Setup couldn't start its checks, so nothing was installed.",
    "i01.error.why": "This usually means another Setup window is still open. Close it, then try again.",
    /* what Setup adds, and where (G2-r1 (d), E2.1#1/#5) */
    "add.service": "WhyNot Cut service", "add.service.sub": "Does the heavy work on this computer, in your user folder",
    "add.panels": "Premiere and After Effects panels", "add.panels.sub": "In Adobe's own plugin folders, for you only",
    "add.fonts": "Brand fonts", "add.fonts.sub": "In your fonts. Fonts you already had stay",
    "add.login": "Startup entry", "add.login.sub": "Login Items. Turn it off there any time",
    "add.login.sub.win": "Startup apps. Turn it off there any time",
    "add.model": "Speech model", "add.model.sub": "Inside the WhyNot Cut service folder",
    "add.claude": "WhyNot Cut inside Claude", "add.claude.sub": "Added to your Claude; your Claude settings are backed up first",
    /* I-02 Customise */
    "i02.title": "Your choices", /* MOCK from inst.custom.title */
    "i02.sub": "Every choice is already set to the best option. Change only what you need.",
    "i02.lang": "The language you pick at the top is saved for WhyNot Cut too.",
    "i02.model": "Speech model", /* MOCK from inst.custom.packs */
    "i02.model.sub": "Turns speech into text. The biggest is the most accurate.",
    "i02.model.large": "Most accurate", "i02.model.turbo": "Faster, a little less accurate",
    "i02.model.medium": "Smaller, less accurate", "i02.model.small": "Smallest, least accurate",
    "i02.recommended": "Recommended",
    "i02.skipped": "Skipped, add later",
    "i02.tight": "There isn't space for the most accurate model now. It's skipped, and you can add it later in Settings.",
    "i02.folders": "Folders",
    "i02.location": "WhyNot Cut service", /* MOCK from inst.custom.location */
    "i02.location.sub": "Needs about {gb}. {free} free on {drive}.",
    "i02.location.other": "On drive {drive} because drive {sys} has less than 30" + NB + "GB free.",
    "i02.clients": "Clients folder", /* NEW inst.custom.clients */
    "i02.clients.sub": "Your raw footage goes here. WhyNot Cut never moves or deletes it.",
    "i02.change": "Change",
    "i02.arabic": "Arabic letters and spaces in this path are fine. WhyNot Cut handles them.", /* MOCK from inst.custom.non_ascii (G11) */
    "i02.external": "This folder is on an external drive. Keep the drive connected while you edit.",
    "i02.bad": "WhyNot Cut can't save files in this folder, because it's protected by the system.",
    "i02.bad.btn": "Choose another folder",
    "i02.options": "Options",
    "i02.login": "Start WhyNot Cut when I sign in", /* NEW inst.custom.login */
    "i02.login.mac": "It shows in System Settings, Login Items, where you can turn it off.",
    "i02.login.win": "It shows in Windows Startup apps, where you can turn it off.",
    "i02.permission": "Don't ask me each time Claude uses WhyNot Cut", /* MOCK from inst.custom.permission */
    "i02.permission.sub": "Claude won't stop to ask permission before every editing step. Anything outside WhyNot Cut still asks.", /* R2 E-P2-17; the box is UNTICKED by default */
    "i02.gpu": "Use the NVIDIA graphics card for speed ({gb})",
    "i02.gpu.sub": "Found: {gpu}",
    "i02.adds": "What Setup adds, and where",
    "i02.total": "Total: about {gb}",
    "i02.install": "Install", /* NEW inst.custom.install */
    /* I-03 Preflight */
    "i03.title": "Checking this computer",
    "i03.sub": "This check changes nothing on your computer.",
    "i03.sum.ok": "Ready: {n}", "i03.sum.note": "Good to know: {n}", "i03.sum.block": "Blocking the install: {n}",
    "i03.checking": "Checking…",
    "i03.disk": "Free space",
    "i03.disk.ok": "{free} free on {drive}. WhyNot Cut needs about {gb}.",
    "i03.disk.red": "There isn't enough space: {free} is free and WhyNot Cut needs {need}. Free {gb}, then check again.", /* MOCK from inst.pre disk red */
    "i03.disk.amber": "Space is tight. Some optional models will be skipped.", /* NEW inst.pre disk amber */
    "i03.system": "This computer",
    "i03.adobe": "Adobe apps",
    "i03.adobe.info": "{apps} found. Your own Adobe licence is used.", /* MOCK from inst.pre adobe info */
    "i03.adobe.running": "Premiere Pro is open. Save your work and close it before the panels step; we'll remind you.", /* MOCK from inst.pre adobe running */
    "i03.claude": "Claude",
    "i03.claude.missing": "Claude isn't installed. We can install it for you.", /* NEW inst.pre claude */
    "i03.claude.signedout": "Claude is installed, but you're not signed in. You'll sign in after the install.",
    "i03.claude.ok": "Claude is installed and you're signed in.",
    "i03.gpu": "Graphics",
    "i03.gpu.ok": "{gpu}. Transcription will be fast.",
    "i03.gpu.none": "No NVIDIA card. Transcription uses the processor and takes longer.",
    "i03.path": "Your user folder",
    "i03.path.ok": "Your user folder has Arabic letters or spaces. That's fine; WhyNot Cut handles it.", /* MOCK from inst.pre path (G11) */
    "i03.cloud": "Documents folder",
    "i03.cloud.icloud": "Documents is in iCloud Drive. Your clients go in a folder that isn't synced.",
    "i03.cloud.onedrive": "Documents is synced by OneDrive. Your clients go in a folder that isn't synced.", /* MOCK from inst.pre cloud */
    "i03.existing": "Earlier install",
    "i03.existing.info": "{app} is installed. It will be updated, and your clients and settings stay.",
    "i03.access": "Files and folders",
    "i03.access.info": "During the install, macOS asks once to let WhyNot Cut use your clients folder. Choose Allow.",
    "i03.auto": "Control of Adobe apps",
    "i03.auto.info": "macOS also asks once to let WhyNot Cut control Premiere Pro and After Effects. Choose OK.",
    "i03.gk": "macOS protection",
    "i03.gk.ok": "macOS protection is still on. Setup never asks you to turn it off.", /* R2 E-P2-17 */
    "i03.sac": "Windows protection",
    "i03.sac.amber": "Smart App Control may warn about this test build. We never turn it off.", /* MOCK from inst.pre sac */
    "i03.net": "Internet",
    "i03.net.ok": "Connected",
    "i03.net.off": "No internet. Only the full offline download can install. Nothing on your computer was changed.", /* MOCK from inst.pre offline note */
    "i03.blocked": "Continue stays off until the red line is fixed.",
    "i03.again": "Check again",
    /* I-04 Progress checklist */
    "i04.title": "Installing WhyNot Cut",
    "i04.title.done": "Everything is installed",
    "i04.title.stopped": "Installing stopped",
    "i04.position": "Step {n} of {of} · about {min} left",
    "i04.count": "{n} of {of} steps done",
    "i04.step.preflight": "Check this computer", /* NEW inst.step.preflight */
    "i04.step.engine": "WhyNot Cut service", /* MOCK from inst.step.engine */
    "i04.step.claude": "WhyNot Cut inside Claude", /* NEW inst.step.claude */
    "i04.step.gitbash": "Safety tools for Claude", /* NEW inst.step.gitbash (Windows only) */
    "i04.step.adobe": "Premiere and After Effects panels", /* NEW inst.step.adobe */
    "i04.step.fonts": "Brand fonts", /* MOCK from inst.step.fonts */
    "i04.step.always_on": "Keep WhyNot Cut ready", /* MOCK from inst.step.always_on */
    "i04.step.models": "Speech model", /* MOCK from inst.step.models */
    "i04.step.client": "Your first client folder", /* NEW inst.step.client */
    "i04.step.doctor": "Final check", /* NEW inst.step.doctor */
    "i04.step.launch": "Open Claude", /* NEW inst.step.launch */
    "i04.end.done": "Done", "i04.end.wait": "Waiting", "i04.end.already": "Already done",
    "i04.end.you": "Needs you", "i04.end.bg": "In the background", "i04.end.offline": "Waiting for internet",
    "i04.run.engine": "Downloading the video tools · {done} of {total}",
    "i04.run.models": "Downloading · {done} of {total}. You can start editing while it finishes.",
    "i04.msg.always_on": "Starts when you sign in. You'll see it in Login Items.",
    "i04.msg.always_on.win": "Starts when you sign in. You'll see it in Startup apps.",
    "i04.trust": "Every download is checked: only genuine files from WhyNot Cut are used.",
    "i04.hide": "Keep going in the background", /* NEW inst.hide */
    "i04.details": "Show details", /* NEW inst.details */
    "i04.details.hide": "Hide details",
    "i04.act.host.title": "Close Premiere Pro to continue",
    "i04.act.host": "Save your work in Premiere Pro, then close it. The panels can't be installed while it's open.", /* MOCK from inst.action.close_host */
    "i04.act.cc.title": "Sign in to Creative Cloud",
    "i04.act.cc": "We opened Creative Cloud for you. Sign in there, then come back here.", /* MOCK from inst.action.cc */
    "i04.act.cc.btn": "I've signed in",
    "i04.act.ccx.title": "One step for you: finish the panel",
    "i04.act.ccx": "Adobe didn't finish installing the panel. Double-click this file to finish:", /* NEW inst.action.ccx */
    "i04.act.ccx.btn": "Show the file",
    "i04.act.ccx.hint": "We continue by ourselves when it's done.",
    "i04.prompt.title": "macOS will ask you next",
    "i04.prompt.text": "WhyNot Cut needs your clients folder. When macOS asks, choose Allow. It only uses the folders you chose.",
    "i04.prompt.dialog": "\u201CWhyNot Cut\u201D would like to access files in the \u201C{folder}\u201D folder.", /* R2 D-P2-8: names the clients folder, not Documents */
    "i04.prompt.deny": "Don\u2019t Allow", "i04.prompt.allow": "Allow",
    "i04.amber.fonts": "2 fonts are in use by another app, so they'll be added after you restart the computer.",
    "i04.offline": "No internet. The model download continues by itself when you're online; everything else is installed.", /* MOCK from NEW offline */
    "i04.cancel.title": "Stop installing?",
    "i04.cancel.text": "What's done stays. Run Setup again to continue.", /* MOCK from inst.cancel.confirm */
    "i04.cancel.stop": "Stop installing", "i04.cancel.keep": "Keep installing",
    "i04.cancelled": "Stopped. Run Setup again to continue.", /* MOCK from inst.cancelled */
    "i04.resume": "Picking up where it stopped. Finished steps aren't done again.",
    "i04.continue": "Continue installing",
    "i04.success": "Everything is installed. The speech model keeps downloading in the background.",
    "i04.log.title": "Log",
    "i04.log.saved": "Saved to {path}",
    "i04.log.open": "Open log folder",
    "i04.red": "The disk is full. Free {gb} and continue.",
    /* I-05 Install Claude for me */
    "i05.title": "Claude isn't installed", /* NEW inst.claude.title */
    "i05.title.installing": "Installing Claude…", "i05.title.signin": "Sign in to Claude", "i05.title.ready": "Claude is ready",
    "i05.open": "Open claude.ai/download",
    "i05.text": "WhyNot Cut works inside Claude, the AI assistant that does the editing. We can install Anthropic's official app for you.", /* MOCK from inst.claude.text */
    "i05.how": "What happens",
    "i05.how.download": "Downloaded from claude.ai over a secure connection",
    "i05.how.check": "Checked that it's really from Anthropic",
    "i05.how.signin": "You sign in yourself. We never see your password.",
    "i05.know": "Good to know",
    "i05.know.footage": "Video and audio files are never uploaded. Claude reads text (the transcript and the plan) and a few still images: some timeline frames for checking, and brand photos.", /* APPROVED (executor, exact line); the cost line D-01 and the data line D-02 are the shared keys claude.cost / claude.data */
    "i05.know.private": "No telemetry, and WhyNot Cut trains on nothing.", /* APPROVED (executor) */
    "i05.install": "Install Claude", /* NEW inst.claude.install */
    "i05.have": "I already have Claude",
    "i05.skip": "Skip for now",
    "i05.downloading": "Downloading Claude · {done} of {total}",
    "i05.checking": "Checking that it's really from Anthropic…", /* NEW inst.claude.checking */
    "i05.publisher": "Checked: genuine app from {name}",
    "i05.signin": "Sign in to Claude in the window that opened. We continue by ourselves.", /* NEW inst.claude.signin */
    "i05.signed": "I've signed in", /* MOCK from inst.claude.signed */
    "i05.timeout": "We haven't seen a sign-in yet.",
    "i05.timeout.sub": "Sign in to Claude, or continue now and sign in later.",
    "i05.wait": "Wait more", "i05.without": "Continue without it",
    "i05.refused": "The downloaded file wasn't the genuine Claude app, so we didn't open it.", /* MOCK from inst.claude.refused */
    "i05.refused.sub": "It was deleted. Open {url}, install Claude there, then press Check again.", /* R2 D-P1-6: the install path comes first */
    "i05.offline": "No internet, so Claude can't be downloaded now. Install it later from {url}; the rest of Setup doesn't need it.",
    /* I-06 Finish */
    "i06.title": "WhyNot Cut is ready", /* NEW inst.done.title */
    "i06.title.error": "One step needs you", "i06.title.almost": "Almost ready",
    "i06.sub": "Two steps to start.",
    "i06.step1": "Open Premiere, then go to:{path}",
    "i06.step2": "In the panel, press \u201C{btn}\u201D.", /* {btn} = firstrun.client in strings.js */
    "i06.checking": "Running the final check…",
    "i06.r.app": "WhyNot Cut service", "i06.r.app.ok": "Installed in your user folder.",
    "i06.r.panels": "Premiere and After Effects panels", "i06.r.panels.ok": "Installed",
    "i06.r.panels.amber": "Close and open Premiere once to load the panel.",
    "i06.r.claude": "WhyNot Cut inside Claude", "i06.r.claude.ok": "Added to Claude",
    "i06.r.model": "Speech model", "i06.r.model.bg": "Still downloading · {done} of {total}. You can start now.",
    "i06.r.login": "Starts when you sign in", "i06.r.login.mac": "Turn it off any time in Login Items.",
    "i06.r.login.win": "Turn it off any time in Startup apps.",
    "i06.r.clients": "Clients folder",
    "i06.open": "Open Claude", /* NEW inst.done.open_claude */
    "i06.clients": "Show my clients folder", /* NEW inst.done.clients */
    "i06.nolink": "Claude didn't open by itself.",
    "i06.paste": "Paste this in Claude to begin:", /* NEW inst.done.paste */
    "i06.copy": "Copy", /* NEW inst.done.copy */
    "i06.mac_access": "macOS will ask once to allow access to your clients folder. Choose Allow.", /* NEW inst.done.mac_access */
    "i06.red": "The final check found a problem: the Premiere panel isn't installed.",
    "i06.nosignin": "Claude is installed, but you're not signed in yet.",
    "i06.nosignin.sub": "Open Claude and sign in. WhyNot Cut starts as soon as you do.",
    /* I-07 Failure cards */
    "i07.title": "Setup stopped",
    "i07.done": "{n} of {of} steps are done and stay installed.",
    "i07.safety": "Safety check",
    "i07.checksum": "A download wasn't the genuine file from WhyNot Cut, so we didn't use it.", /* MOCK from I-07 Download changed */
    "i07.checksum.sub": "It was the video tools download. It was deleted before it ran. Nothing on your computer changed.", /* R2 D-P1-10: no file names here */
    "i07.manifest": "We couldn't confirm the list of files to install is the genuine one from The" + NB + "Why" + NB + "Not. Nothing was installed.", /* MOCK from I-07 Manifest not trusted */
    "i07.manifest.sub": "Get WhyNot Cut again from the official download page:", /* R2 D-P1-6: never a script address */
    "i07.manifest.btn": "Open download page", /* MOCK-VERIFY: the page address */
    "i07.address": "We stopped a download from an address that isn't on our list.", /* NEW I-07 Address not allowed */
    "i07.address.sub": "Address: {host}. Nothing from it was used.",
    "i07.dlfail": "The download of the video tools stopped halfway.",
    "i07.dlfail.sub": "The connection dropped. Try again: it continues where it stopped.",
    "i07.nointernet": "No internet. Connect and try again, or use the full offline installer.", /* MOCK from I-07 No internet */
    "i07.nointernet.sub": "What's done stays installed. Nothing else needs the internet until the next download.",
    "i07.diskfull": "The disk is full. Free {gb} and continue.", /* MOCK from I-07 Disk full */
    "i07.diskfull.sub": "{free} free on {drive}. The speech model needs the space.",
    "i07.panel": "Adobe didn't install the panel. Double-click the panel file to finish.", /* NEW I-07 Adobe panel not loaded */
    "i07.panel.btn": "Show me",
    "i07.hostopen": "Premiere Pro is still open. Close it, then continue.", /* NEW I-07 Hosts still open */
    "i07.hostopen.sub": "Save your work first. Nothing in your projects was changed.",
    /* I-08 Update and repair */
    "i08.eyebrow": "Update",
    "i08.title": "{app} is ready", /* NEW inst.update.title */
    "i08.title.error": "Update not installed",
    "i08.have": "You have {version}.",
    "i08.notes": "Faster captions, and Arabic titles fixed in After Effects.",
    "i08.signed": "Checked: this update is the genuine one from WhyNot Cut. It's checked again before anything is installed.",
    "i08.now": "Update", /* NEW inst.update.now */
    "i08.later": "Later", /* NEW inst.update.later */
    "i08.repair": "Repair", /* NEW inst.update.repair */
    "i08.repair.title": "Something not working?",
    "i08.repair.text": "Repair runs every step again and fixes what's broken. Your clients and settings stay.",
    "i08.prev": "Go back to {version}", /* backlog B-04: keeps the last good version on disk */
    "i08.prev.text": "Or go back to the last version that worked. Your clients and settings stay.",
    "i08.loading": "Downloading the update · {done} of {total}",
    "i08.checking": "Checking it's the genuine update…",
    "i08.current": "WhyNot Cut is up to date.", /* NEW inst.update.current */
    "i08.current.sub": "Version {version} · checked at {time}",
    "i08.bad_sig": "We didn't install the update because we couldn't confirm it's the genuine one.", /* MOCK from inst.update.bad_sig */
    "i08.bad_sig.sub": "Your current version keeps working. Nothing was changed.",
    "i08.offline": "No internet, so we couldn't check for updates. Your current version keeps working.",
    "i08.repair.run": "Repairing WhyNot Cut",
    /* I-09 Uninstall */
    "i09.title": "Remove WhyNot Cut", /* NEW inst.un.title */
    "i09.sub": "This removes only what WhyNot Cut added:", /* MOCK from inst.un.list */
    "i09.r.link": "The WhyNot Cut link in your browser",
    "i09.models": "Also delete the speech models ({gb})", /* NEW inst.un.models */
    "i09.models.sub": "Keep them if you might install again.",
    "i09.clients": "Your client folders are not touched: {path}", /* NEW inst.un.clients */
    "i09.backup": "Claude's settings are backed up first.", /* R2 D-P1-10: no file name */
    "i09.backup.done": "Claude settings backed up today at {time}.",
    "i09.confirm.title": "Remove WhyNot Cut from this computer?",
    "i09.confirm.text": "The list below goes. Your client folders stay.",
    "i09.confirm.go": "Remove WhyNot Cut", "i09.confirm.keep": "Keep it",
    "i09.removing": "Removing WhyNot Cut",
    "i09.end.removed": "Removed", "i09.end.kept": "Kept",
    "i09.error": "The panels couldn't be removed because Premiere Pro is using them.",
    "i09.error.row": "Premiere Pro is using it.",
    "i09.error.sub": "Close Premiere Pro, then press Try again. Everything else is removed.",
    "i09.done": "WhyNot Cut was removed. Your client folders were not touched.", /* NEW inst.un.done */
    "i09.done.sub": "{gb} freed. The speech models stay on this computer, so installing again is quick.",
    "i09.empty.title": "WhyNot Cut isn't on this computer",
    "i09.empty.text": "There's nothing to remove. Your client folders are where you left them."
  };
  var ar = {
    /* shell */
    "i00.setup": "التسطيب",
    "i00.wintitle": "تسطيب WhyNot Cut",
    "i00.internal": "نسخة داخلية",
    "i00.version": "{app}",
    "i00.signed": "نسخة أصلية من The" + NB + "Why" + NB + "Not",
    "i00.unsigned": "نسخة بيتا للتجربة بس.",
    "i00.stage.welcome": "البداية", "i00.stage.custom": "اختياراتك", "i00.stage.check": "فحص الجهاز",
    "i00.stage.claude": "Claude", "i00.stage.install": "التسطيب", "i00.stage.finish": "النهاية",
    "i00.stage.update": "التحديث", "i00.stage.choose": "اللي هيتشال", "i00.stage.remove": "الإزالة", "i00.stage.done": "خلاص",
    "i00.back": "رجوع",
    "i00.continue": "كمّل",
    "i00.close": "اقفل",
    "i00.cancel": "إلغاء",
    "i00.next": "التالي",
    "i00.retry": "جرّب تاني",
    "i00.check_again": "افحص تاني",
    "i00.offline_get": "حمّل نسخة التسطيب اللي من غير نت",
    "i00.save_report": "احفظ تقرير للدعم",
    "i00.report_note": "التقرير بيتحفظ على جهازك من غير بيانات شخصية، ومش بيتبعت لحد إلا لو إنت بعته.",
    "i00.min": "{n}" + NB + "دقيقة",
    "i00.service": "خدمة WhyNot Cut",
    /* I-01 Welcome */
    "i01.eyebrow": "الإصدار {version}",
    "i01.title": "سطّب WhyNot Cut",
    "i01.text": "كل اللي WhyNot Cut محتاجه، مرة واحدة (حوالي {gb}).",
    "i01.fact.disk": "فاضي {free} على {drive}",
    "i01.fact.user": "ليك إنت بس. من غير باسورد الأدمن ولا أدوات مطوّرين.",
    "i01.fact.user.win": "ليك إنت بس. مش محتاج صلاحيات الأدمن.",
    "i01.fact.private": "التسطيب مش بيبعت أي حاجة من جهازك.",
    "i01.fact.visible": "كل خطوة بتظهر هنا وبتتكتب في سجل.",
    "i01.adds": "التسطيب بيضيف 6 حاجات، كلها جوه فولدر المستخدم بتاعك. الإزالة بتشيلهم كلهم ومش بتلمس فولدرات العملاء أبدًا.",
    "i01.adds.show": "شوف إيه بيتحط فين",
    "i01.adds.hide": "خبّي القائمة",
    "i01.install": "سطّب كل حاجة",
    "i01.customise": "اختار بنفسك",
    "i01.offline": "بيتسطّب من غير نت. Claude وتسجيل الدخول هيحتاجوا نت بعد كده.",
    "i01.upgrade": "{app} متسطّب. هيتحدّث، وعملاءك وإعداداتك هيفضلوا زي ما هم.",
    "i01.internal": "نسخة البيتا دي لسه Apple و Microsoft ما فحصوهاش. استخدمها للتجربة بس، وما تبعتهاش للعملاء.",
    "i01.noclaude": "Claude لسه مش موجود على الجهاز. التسطيب هيسطّبه لك بعد الفحص.",
    "i01.error": "التسطيب ما قدرش يبدأ الفحص، فما اتسطّبش حاجة.",
    "i01.error.why": "ده غالبًا معناه إن فيه شباك تسطيب تاني مفتوح. اقفله وجرّب تاني.",
    /* what Setup adds, and where */
    "add.service": "خدمة WhyNot Cut", "add.service.sub": "بتعمل الشغل التقيل على الجهاز ده، جوه فولدر المستخدم بتاعك",
    "add.panels": "بانلز Premiere و After Effects", "add.panels.sub": "في فولدرات Adobe نفسها، ليك إنت بس",
    "add.fonts": "خطوط البراند", "add.fonts.sub": "في خطوطك. الخطوط اللي كانت عندك بتفضل زي ما هي",
    "add.login": "التشغيل مع الدخول", "add.login.sub": "في عناصر تسجيل الدخول. تقدر تقفله من هناك في أي وقت",
    "add.login.sub.win": "في تطبيقات بدء التشغيل. تقدر تقفله من هناك في أي وقت",
    "add.model": "نموذج الكلام", "add.model.sub": "جوه فولدر خدمة WhyNot Cut",
    "add.claude": "WhyNot Cut جوه Claude", "add.claude.sub": "بيتضاف جوه Claude بتاعك، وبناخد نسخة من إعدادات Claude الأول",
    /* I-02 Customise */
    "i02.title": "اختياراتك",
    "i02.sub": "كل اختيار متظبط على الأحسن. غيّر بس اللي محتاجه.",
    "i02.lang": "اللغة اللي هتختارها فوق بتتحفظ في WhyNot Cut كمان.",
    "i02.model": "نموذج الكلام",
    "i02.model.sub": "بيحوّل الكلام لنص. الأكبر هو الأدق.",
    "i02.model.large": "الأدق", "i02.model.turbo": "أسرع، وأقل دقة شوية",
    "i02.model.medium": "أصغر، وأقل دقة", "i02.model.small": "الأصغر، والأقل دقة",
    "i02.recommended": "ننصح بيه",
    "i02.skipped": "هيتأجل، ضيفه بعدين",
    "i02.tight": "مفيش مساحة للنموذج الأدق دلوقتي. هيتأجل، وتقدر تضيفه بعدين من الإعدادات.",
    "i02.folders": "الفولدرات",
    "i02.location": "خدمة WhyNot Cut",
    "i02.location.sub": "محتاجة حوالي {gb}. الفاضي {free} على {drive}.",
    "i02.location.other": "على درايف {drive} لأن درايف {sys} فاضي فيه أقل من 30" + NB + "جيجا.",
    "i02.clients": "فولدر العملاء",
    "i02.clients.sub": "هنا هتحط الفيديوهات الخام. WhyNot Cut عمره ما بينقلها ولا بيمسحها.",
    "i02.change": "غيّر",
    "i02.arabic": "الحروف العربي والمسافات في المسار ده مفيهاش مشكلة. WhyNot Cut بيتعامل معاها.",
    "i02.external": "الفولدر ده على هارد خارجي. خلّي الهارد متوصّل وإنت بتعمل مونتاج.",
    "i02.bad": "WhyNot Cut مش قادر يحفظ ملفات في الفولدر ده، لأن النظام قافله.",
    "i02.bad.btn": "اختار فولدر تاني",
    "i02.options": "خيارات",
    "i02.login": "شغّل WhyNot Cut أول ما أدخل على الجهاز",
    "i02.login.mac": "هتلاقيه في إعدادات النظام، عناصر تسجيل الدخول، وتقدر تقفله من هناك.",
    "i02.login.win": "هتلاقيه في تطبيقات بدء التشغيل في Windows، وتقدر تقفله من هناك.",
    "i02.permission": "ما تسألنيش كل مرة Claude يستخدم WhyNot Cut",
    "i02.permission.sub": "Claude مش هيوقّف الشغل عشان يسألك إذن قبل كل خطوة مونتاج. أي حاجة برّه WhyNot Cut هتفضل تسألك.",
    "i02.gpu": "استخدم كارت NVIDIA عشان السرعة ({gb})",
    "i02.gpu.sub": "لقينا: {gpu}",
    "i02.adds": "التسطيب بيضيف إيه، وفين",
    "i02.total": "الإجمالي: حوالي {gb}",
    "i02.install": "سطّب",
    /* I-03 Preflight */
    "i03.title": "بنفحص الجهاز",
    "i03.sub": "الفحص ده مش بيغيّر أي حاجة في جهازك.",
    "i03.sum.ok": "جاهز: {n}", "i03.sum.note": "حاجات تعرفها: {n}", "i03.sum.block": "واقف عليه التسطيب: {n}",
    "i03.checking": "بنفحص…",
    "i03.disk": "المساحة الفاضية",
    "i03.disk.ok": "فاضي {free} على {drive}. WhyNot Cut محتاج حوالي {gb}.",
    "i03.disk.red": "المساحة مش كفاية: الفاضي {free} و WhyNot Cut محتاج {need}. فضّي {gb} وافحص تاني.",
    "i03.disk.amber": "المساحة على القد. شوية نماذج اختيارية هتتأجل.",
    "i03.system": "الجهاز ده",
    "i03.adobe": "برامج Adobe",
    "i03.adobe.info": "لقينا {apps}. بنستخدم رخصة Adobe بتاعتك.",
    "i03.adobe.running": "Premiere Pro مفتوح. احفظ شغلك واقفله قبل خطوة البانلز، وهنفكّرك.",
    "i03.claude": "Claude",
    "i03.claude.missing": "Claude مش متسطّب. نقدر نسطّبه لك.",
    "i03.claude.signedout": "Claude متسطّب، بس إنت مش مسجّل دخول. هتسجّل بعد التسطيب.",
    "i03.claude.ok": "Claude متسطّب وإنت مسجّل دخول.",
    "i03.gpu": "كارت الشاشة",
    "i03.gpu.ok": "{gpu}. التفريغ هيبقى سريع.",
    "i03.gpu.none": "مفيش كارت NVIDIA. التفريغ هيشتغل على البروسيسور وهياخد وقت أطول.",
    "i03.path": "فولدر المستخدم",
    "i03.path.ok": "فولدر المستخدم فيه حروف عربي أو مسافات. مفيش مشكلة، WhyNot Cut بيتعامل معاها.",
    "i03.cloud": "فولدر المستندات",
    "i03.cloud.icloud": "المستندات على iCloud Drive. هنحط العملاء في فولدر مش متزامن.",
    "i03.cloud.onedrive": "المستندات متزامنة مع OneDrive. هنحط العملاء في فولدر مش متزامن.",
    "i03.existing": "تسطيب قديم",
    "i03.existing.info": "{app} متسطّب. هيتحدّث، وعملاءك وإعداداتك هيفضلوا زي ما هم.",
    "i03.access": "الملفات والفولدرات",
    "i03.access.info": "وقت التسطيب، macOS هيسألك مرة واحدة تسمح إن WhyNot Cut يستخدم فولدر العملاء. اختار «سماح».",
    "i03.auto": "التحكم في برامج Adobe",
    "i03.auto.info": "macOS هيسألك كمان مرة تسمح إن WhyNot Cut يتحكم في Premiere Pro و After Effects. اختار «موافق».",
    "i03.gk": "حماية macOS",
    "i03.gk.ok": "حماية macOS فاضلة شغّالة. التسطيب عمره ما هيطلب منك تقفلها.",
    "i03.sac": "حماية Windows",
    "i03.sac.amber": "حماية التطبيقات الذكية ممكن تطلع تحذير لنسخة التجربة دي. إحنا عمرنا ما بنقفلها.",
    "i03.net": "النت",
    "i03.net.ok": "متوصّل",
    "i03.net.off": "لسه مفيش نت. التسطيب ينفع بس من التحميل الكامل اللي من غير نت. ما اتغيّرش حاجة في جهازك.",
    "i03.blocked": "زرار «كمّل» هيفضل مقفول لحد ما السطر الأحمر يتحل.",
    "i03.again": "افحص تاني",
    /* I-04 Progress checklist */
    "i04.title": "بنسطّب WhyNot Cut",
    "i04.title.done": "كل حاجة اتسطّبت",
    "i04.title.stopped": "التسطيب وقف",
    "i04.position": "خطوة {n} من {of} · فاضل حوالي {min}",
    "i04.count": "خلصنا {n} من {of} خطوة",
    "i04.step.preflight": "فحص الجهاز",
    "i04.step.engine": "خدمة WhyNot Cut",
    "i04.step.claude": "WhyNot Cut جوه Claude",
    "i04.step.gitbash": "أدوات أمان Claude",
    "i04.step.adobe": "بانلز Premiere و After Effects",
    "i04.step.fonts": "خطوط البراند",
    "i04.step.always_on": "خلّي WhyNot Cut جاهز",
    "i04.step.models": "نموذج الكلام",
    "i04.step.client": "فولدر أول عميل",
    "i04.step.doctor": "الفحص الأخير",
    "i04.step.launch": "افتح Claude",
    "i04.end.done": "خلص", "i04.end.wait": "مستني", "i04.end.already": "خلص قبل كده",
    "i04.end.you": "محتاجينك", "i04.end.bg": "في الخلفية", "i04.end.offline": "مستني النت",
    "i04.run.engine": "بننزّل أدوات الفيديو · {done} من {total}",
    "i04.run.models": "بينزل · {done} من {total}. تقدر تبدأ مونتاج قبل ما يخلص.",
    "i04.msg.always_on": "بيشتغل أول ما تدخل على الجهاز. هتلاقيه في عناصر تسجيل الدخول.",
    "i04.msg.always_on.win": "بيشتغل أول ما تدخل على الجهاز. هتلاقيه في تطبيقات بدء التشغيل.",
    "i04.trust": "كل تحميل بيتفحص: مش بنستخدم غير الملفات الأصلية من WhyNot Cut.",
    "i04.hide": "كمّل في الخلفية",
    "i04.details": "اعرض التفاصيل",
    "i04.details.hide": "خبّي التفاصيل",
    "i04.act.host.title": "اقفل Premiere Pro الأول",
    "i04.act.host": "احفظ شغلك في Premiere Pro واقفله. مينفعش نسطّب البانلز وهو مفتوح.",
    "i04.act.cc.title": "سجّل دخول في Creative Cloud",
    "i04.act.cc": "فتحنالك Creative Cloud. سجّل دخول فيه وارجع هنا.",
    "i04.act.cc.btn": "سجّلت دخول",
    "i04.act.ccx.title": "خطوة واحدة منك: كمّل تسطيب البانل",
    "i04.act.ccx": "Adobe ما كمّلتش تسطيب البانل. دوس مرتين على الملف ده عشان تكمّل:",
    "i04.act.ccx.btn": "وريني الملف",
    "i04.act.ccx.hint": "هنكمّل لوحدنا أول ما يخلص.",
    "i04.prompt.title": "macOS هيسألك دلوقتي",
    "i04.prompt.text": "WhyNot Cut محتاج فولدر العملاء. لما macOS يسألك اختار «سماح». مش هيستخدم غير الفولدرات اللي اخترتها.",
    "i04.prompt.dialog": "يرغب \u201DWhyNot Cut\u201C في الوصول إلى الملفات الموجودة في المجلد \u201D{folder}\u201C.",
    "i04.prompt.deny": "عدم السماح", "i04.prompt.allow": "سماح",
    "i04.amber.fonts": "خطين مستخدمين في برنامج تاني، فهيتضافوا بعد ما تعمل ريستارت للجهاز.",
    "i04.offline": "لسه مفيش نت. تحميل النموذج هيكمّل لوحده لما النت يرجع، وباقي الحاجات اتسطّبت.",
    "i04.cancel.title": "توقّف التسطيب؟",
    "i04.cancel.text": "اللي خلص هيفضل زي ما هو. شغّل التسطيب تاني عشان تكمّل.",
    "i04.cancel.stop": "وقّف التسطيب", "i04.cancel.keep": "كمّل التسطيب",
    "i04.cancelled": "وقفنا. شغّل التسطيب تاني عشان تكمّل.",
    "i04.resume": "بنكمّل من مكان ما وقفنا. الخطوات اللي خلصت مش هتتعاد.",
    "i04.continue": "كمّل التسطيب",
    "i04.success": "كل حاجة اتسطّبت. نموذج الكلام بيكمّل تحميل في الخلفية.",
    "i04.log.title": "السجل",
    "i04.log.saved": "محفوظ في {path}",
    "i04.log.open": "افتح فولدر السجل",
    "i04.red": "الهارد مليان. فضّي {gb} وكمّل.",
    /* I-05 Install Claude for me */
    "i05.title": "Claude مش متسطّب",
    "i05.title.installing": "بنسطّب Claude…", "i05.title.signin": "سجّل دخول في Claude", "i05.title.ready": "Claude جاهز",
    "i05.open": "افتح claude.ai/download",
    "i05.text": "WhyNot Cut بيشتغل جوه Claude، المساعد الذكي اللي بيعمل المونتاج. نقدر نسطّبلك تطبيق Anthropic الرسمي.",
    "i05.how": "اللي هيحصل",
    "i05.how.download": "بينزل من claude.ai على اتصال آمن",
    "i05.how.check": "بنتأكد إنه من Anthropic فعلًا",
    "i05.how.signin": "إنت اللي بتسجّل دخول. إحنا عمرنا ما بنشوف الباسورد.",
    "i05.know": "حاجات تعرفها",
    "i05.know.footage": "ملفات الفيديو والصوت عمرها ما بتترفع. Claude بيقرا نصوص بس (التفريغ والخطة) وشوية صور ثابتة: لقطات قليلة من التايملاين عشان المراجعة، وصور البراند.", /* D-03, the approved Egyptian line, verbatim */
    "i05.know.private": "مفيش أي تتبّع، و WhyNot Cut مش بيدرّب أي حاجة على شغلك.",
    "i05.install": "سطّب Claude",
    "i05.have": "Claude عندي",
    "i05.skip": "بعدين",
    "i05.downloading": "بننزّل Claude · {done} من {total}",
    "i05.checking": "بنتأكد إنه من Anthropic فعلًا…",
    "i05.publisher": "اتفحص: تطبيق أصلي من {name}",
    "i05.signin": "سجّل دخول في Claude من الشباك اللي اتفتح. هنكمّل لوحدنا.",
    "i05.signed": "سجّلت دخول",
    "i05.timeout": "لسه ما شفناش تسجيل دخول.",
    "i05.timeout.sub": "سجّل دخول في Claude، أو كمّل دلوقتي وسجّل بعدين.",
    "i05.wait": "استنى شوية", "i05.without": "كمّل من غيره",
    "i05.refused": "الملف اللي نزل ما كانش تطبيق Claude الأصلي، فما فتحناهوش.",
    "i05.refused.sub": "اتمسح. افتح {url} وسطّب Claude من هناك، وبعدين دوس «افحص تاني».",
    "i05.offline": "لسه مفيش نت، فمش هنقدر ننزّل Claude دلوقتي. سطّبه بعدين من {url}؛ باقي التسطيب مش محتاجه.",
    /* I-06 Finish */
    "i06.title": "WhyNot Cut جاهز",
    "i06.title.error": "فيه خطوة محتاجاك", "i06.title.almost": "قربنا نخلّص",
    "i06.sub": "خطوتين وتبدأ.",
    "i06.step1": "افتح Premiere، وبعدين روح على:{path}",
    "i06.step2": "من البانل دوس «{btn}».",
    "i06.checking": "بنعمل الفحص الأخير…",
    "i06.r.app": "خدمة WhyNot Cut", "i06.r.app.ok": "متسطّبة في فولدر المستخدم بتاعك.",
    "i06.r.panels": "بانلز Premiere و After Effects", "i06.r.panels.ok": "متسطّبين",
    "i06.r.panels.amber": "اقفل Premiere وافتحه مرة واحدة عشان البانل يظهر.",
    "i06.r.claude": "WhyNot Cut جوه Claude", "i06.r.claude.ok": "اتضاف جوه Claude",
    "i06.r.model": "نموذج الكلام", "i06.r.model.bg": "لسه بينزل · {done} من {total}. تقدر تبدأ دلوقتي.",
    "i06.r.login": "بيشتغل مع الدخول", "i06.r.login.mac": "تقدر تقفله في أي وقت من عناصر تسجيل الدخول.",
    "i06.r.login.win": "تقدر تقفله في أي وقت من تطبيقات بدء التشغيل.",
    "i06.r.clients": "فولدر العملاء",
    "i06.open": "افتح Claude",
    "i06.clients": "وريني فولدر العملاء",
    "i06.nolink": "Claude ما اتفتحش لوحده.",
    "i06.paste": "الصق ده في Claude عشان تبدأ:",
    "i06.copy": "انسخ",
    "i06.mac_access": "macOS هيسألك مرة واحدة تسمح بالوصول لفولدر العملاء. اختار «سماح».",
    "i06.red": "الفحص الأخير لقى مشكلة: بانل Premiere مش متسطّب.",
    "i06.nosignin": "Claude متسطّب، بس لسه ما سجّلتش دخول.",
    "i06.nosignin.sub": "افتح Claude وسجّل دخول. WhyNot Cut هيبدأ أول ما تسجّل.",
    /* I-07 Failure cards */
    "i07.title": "التسطيب وقف",
    "i07.done": "خلصنا {n} من {of} خطوة، وهيفضلوا متسطّبين.",
    "i07.safety": "فحص الأمان",
    "i07.checksum": "ملف من اللي نزلوا ما كانش الملف الأصلي من WhyNot Cut، فما استخدمناهوش.",
    "i07.checksum.sub": "ده كان تحميل أدوات الفيديو. اتمسح قبل ما يشتغل. ما اتغيّرش حاجة في جهازك.",
    "i07.manifest": "ما قدرناش نتأكد إن قائمة الملفات أصلية من The" + NB + "Why" + NB + "Not. ما اتسطّبش حاجة.",
    "i07.manifest.sub": "نزّل WhyNot Cut تاني من صفحة التحميل الرسمية:",
    "i07.manifest.btn": "افتح صفحة التحميل",
    "i07.address": "وقّفنا تحميل من عنوان مش موجود في قائمتنا.",
    "i07.address.sub": "العنوان: {host}. ما استخدمناش منه حاجة.",
    "i07.dlfail": "تحميل أدوات الفيديو وقف في النص.",
    "i07.dlfail.sub": "النت فصل. جرّب تاني: التحميل هيكمّل من مكان ما وقف.",
    "i07.nointernet": "لسه مفيش نت. اتوصّل وجرّب تاني، أو استخدم نسخة التسطيب الكاملة اللي من غير نت.",
    "i07.nointernet.sub": "اللي خلص هيفضل متسطّب. مفيش حاجة تانية محتاجة نت لحد التحميل الجاي.",
    "i07.diskfull": "الهارد مليان. فضّي {gb} وكمّل.",
    "i07.diskfull.sub": "الفاضي {free} على {drive}. نموذج الكلام محتاج المساحة دي.",
    "i07.panel": "Adobe ما سطّبتش البانل. دوس مرتين على ملف البانل عشان تكمّل.",
    "i07.panel.btn": "وريني",
    "i07.hostopen": "Premiere Pro لسه مفتوح. اقفله الأول وبعدين كمّل.",
    "i07.hostopen.sub": "احفظ شغلك الأول. ما اتغيّرش حاجة في مشاريعك.",
    /* I-08 Update and repair */
    "i08.eyebrow": "تحديث",
    "i08.title": "{app} جاهز",
    "i08.title.error": "التحديث ما اتسطّبش",
    "i08.have": "عندك الإصدار {version}.",
    "i08.notes": "كابشن أسرع، وتصليح العناوين العربي في After Effects.",
    "i08.signed": "اتفحص: التحديث ده أصلي من WhyNot Cut، وهيتفحص تاني قبل ما يتسطّب أي حاجة.",
    "i08.now": "حدّث",
    "i08.later": "بعدين",
    "i08.repair": "صلّح",
    "i08.repair.title": "فيه حاجة مش شغّالة؟",
    "i08.repair.text": "التصليح بيعيد كل الخطوات ويصلّح اللي بايظ. عملاءك وإعداداتك هيفضلوا زي ما هم.",
    "i08.prev": "ارجع للإصدار {version}",
    "i08.prev.text": "أو ارجع لآخر إصدار كان شغّال. عملاءك وإعداداتك هيفضلوا زي ما هم.",
    "i08.loading": "بننزّل التحديث · {done} من {total}",
    "i08.checking": "بنتأكد إن التحديث أصلي…",
    "i08.current": "WhyNot Cut على آخر إصدار.",
    "i08.current.sub": "الإصدار {version} · آخر فحص {time}",
    "i08.bad_sig": "ما سطّبناش التحديث لأننا ما قدرناش نتأكد إنه أصلي.",
    "i08.bad_sig.sub": "الإصدار اللي عندك شغّال زي ما هو. ما اتغيّرش حاجة.",
    "i08.offline": "لسه مفيش نت، فما قدرناش ندوّر على تحديثات. الإصدار اللي عندك شغّال عادي.",
    "i08.repair.run": "بنصلّح WhyNot Cut",
    /* I-09 Uninstall */
    "i09.title": "شيل WhyNot Cut",
    "i09.sub": "هيتشال بس اللي WhyNot Cut ضافه:",
    "i09.r.link": "رابط WhyNot Cut في المتصفح",
    "i09.models": "امسح نماذج الكلام كمان ({gb})",
    "i09.models.sub": "سيبها لو ممكن تسطّب تاني.",
    "i09.clients": "فولدرات عملاءك مش هتتلمس: {path}",
    "i09.backup": "بناخد نسخة من إعدادات Claude الأول.",
    "i09.backup.done": "اتاخدت نسخة من إعدادات Claude النهارده الساعة {time}.",
    "i09.confirm.title": "تشيل WhyNot Cut من الجهاز ده؟",
    "i09.confirm.text": "القائمة اللي تحت هتتشال. فولدرات عملاءك هتفضل.",
    "i09.confirm.go": "شيل WhyNot Cut", "i09.confirm.keep": "خليه",
    "i09.removing": "بنشيل WhyNot Cut",
    "i09.end.removed": "اتشال", "i09.end.kept": "فاضل",
    "i09.error": "البانلز ما اتشالتش لأن Premiere Pro بيستخدمها.",
    "i09.error.row": "Premiere Pro بيستخدمها.",
    "i09.error.sub": "اقفل Premiere Pro ودوس «جرّب تاني». كل الباقي اتشال.",
    "i09.done": "WhyNot Cut اتشال. فولدرات عملاءك ما اتلمستش.",
    "i09.done.sub": "فضّينا {gb}. نماذج الكلام فاضلة على جهازك، فالتسطيب تاني هيبقى أسرع.",
    "i09.empty.title": "WhyNot Cut مش موجود على الجهاز ده",
    "i09.empty.text": "مفيش حاجة تتشال. فولدرات عملاءك في مكانها زي ما سبتها."
  };
  Object.assign(window.MOCK_STRINGS.en, en);
  Object.assign(window.MOCK_STRINGS.ar, ar);
})();

/* MOCK data shown in the installer screens (not UI copy). macOS is the primary platform (G11): I.D takes the "mac" set
   unless the state is the Windows variant ("win"). "long" = the long-text values: Arabic letters, spaces, an external
   drive, iCloud (G11). */
window.I_DATA = {
  version: "3.0.0", old: "2.2.1", next: "3.0.1", badHost: "files.example-mirror.net", apps: "Premiere Pro 25.5 · After Effects 25.5",
  downloadPage: "thewhynot.ai/download", /* MOCK-VERIFY: the page address */
  /* the support and "Cost and data" addresses are in ../strings.js (MOCK_DATA.support) and are shown only when live (H24) */
  mac: {
    total: 3.6, free: 212, drive: "Macintosh HD", gpu: "Apple M2 Pro", os: "macOS 15 · Apple silicon",
    home: "/Users/sara/.whynot-cut", clients: "/Users/sara/WhyNot Clients",
    fonts: "/Users/sara/Library/Fonts", login: "/Users/sara/Library/LaunchAgents/ai.thewhynot.cut.plist",
    log: "/Users/sara/.whynot-cut/logs/install-20261014-103200.log", ccx: "WhyNotCut-3.0.0.ccx",
        backup: "settings.json.bak-20261014-103200",
    cep: "/Users/sara/Library/Application Support/Adobe/CEP/extensions/ai.thewhynot.cut",
    long: {
      home: "/Users/محمد عبد الرحمن/.whynot-cut",
      clients: "/Volumes/Samsung T7 Shield/عملاء 2026/Al-Mustaqbal Family Medicine and Diabetes Care Center/Raw footage",
      fonts: "/Users/محمد عبد الرحمن/Library/Fonts",
      log: "/Users/محمد عبد الرحمن/.whynot-cut/logs/install-20261014-103200.log",
      ccx: "WhyNotCut-Premiere-and-AfterEffects-Panels-3.0.0.ccx",
      apps: "Premiere Pro 25.5 · After Effects 25.5 · Premiere Pro 26.0 (Beta)", total: 12.4, free: 1024.5, external: true
    }
  },
  win: {
    total: 5.0, free: 212, drive: "C:", gpu: "NVIDIA GeForce RTX 4060", gpuGb: 1.0, os: "Windows 11 · 64-bit",
    home: "C:\\Users\\Sara\\.whynot-cut", clients: "D:\\WhyNot Clients",
    fonts: "C:\\Users\\Sara\\AppData\\Local\\Microsoft\\Windows\\Fonts", login: "Startup apps",
    log: "C:\\Users\\Sara\\.whynot-cut\\logs\\install-20261014-103200.log", ccx: "WhyNotCut-3.0.0.ccx",
        backup: "settings.json.bak-20261014-103200",
    cep: "C:\\Users\\Sara\\AppData\\Roaming\\Adobe\\CEP\\extensions\\ai.thewhynot.cut",
    long: {
      home: "C:\\Users\\Mohamed Abdel-Rahman El-Sayed\\.whynot-cut",
      clients: "D:\\Clients 2026\\Al-Mustaqbal Family Medicine and Diabetes Care Center\\Raw footage",
      log: "C:\\Users\\Mohamed Abdel-Rahman El-Sayed\\.whynot-cut\\logs\\install-20261014-103200.log",
      ccx: "WhyNotCut-Premiere-and-AfterEffects-Panels-3.0.0.ccx", gpu: "NVIDIA GeForce RTX 4090 Laptop GPU (16 GB)",
      apps: "Premiere Pro 25.5 · After Effects 25.5 · Premiere Pro 26.0 (Beta)", total: 12.4, free: 1024.5
    }
  }
};
