---
title: Troubleshooting
slug: 17-troubleshooting
order: 17
lang: en
dir: ltr
---

# Troubleshooting {#ch17-title}

Most problems have a known cause and a short fix. Always start with the check, then look for your situation in the sections below. Each problem is written in three parts: “What happened”, “Why”, and “Do this”, which is a single step.

## The first step for any problem {#ch17-first}

1. Write to Claude: “افحص الجهاز” (“Check the computer”). It runs the check itself, a check that changes nothing on your computer, and shows the list of fixes and who does each one: Claude or you ([Chapter 2](02-install.md#ch02-check)).
2. To fix the engine or the Premiere panel, close Premiere, then type the following command in the Claude app and press Enter. It fixes everything to do with WhyNot Cut, and it is safe to repeat:

   ```
   /whynot-cut:setup
   ```
3. Do the fixes marked as yours, such as installing fonts or a command Claude gives you (how to run it is in [Chapter 2](02-install.md#ch02-run-command)), then ask for the check again.

![The check result: each fix is listed with who does it.](shots/17-troubleshooting-1.png)

*The check result: each fix is listed with who does it.*

> **Tip:** Claude doesn't try random fixes: if a fix fails twice it calls in a helper that specialises in checking the computer, and after three failed attempts at the same problem it stops and explains to you what it tried and what it found out.

## Installing and starting WhyNot Cut {#ch17-setup}

**What happened:** Claude says the `reel` command isn't known on the computer.\
**Why:** The chat started before WhyNot Cut was installed, so it doesn't know where the engine's tool is yet. Claude carries on with the current work another way.\
**Do this:** Once the current work is finished, quit the Claude app completely ([Chapter 2](02-install.md#ch02-claude-first)) and open it, then open a new chat.

**What happened:** The same message about `reel` appeared in a new chat after reopening Claude.\
**Why:** The WhyNot Cut plugin isn't turned on in the Claude app.\
**Do this:** Type `/plugin` in the message box, and turn on WhyNot Cut in the list of plugins.

**What happened:** Claude mentions an old WhyNot Cut version number after the update, or an error appears about `reel-editor` (the old name of the WhyNot Cut engine).\
**Why:** The chat started before the install or update, so it's still using the old version.\
**Do this:** Quit the Claude app completely and open it, then open a new chat.

**What happened:** A message saying “engine not installed”.\
**Why:** This is a new computer, or its first setup wasn't completed, so the engine isn't on your computer yet.\
**Do this:** Type `/whynot-cut:setup`, and agree when Claude asks you about installing the engine (about 400 MB).

## In Premiere and in After Effects {#ch17-premiere}

**What happened:** The WhyNot Cut Bridge panel doesn't appear in Window › Extensions after installing.\
**Why:** Premiere was open during the install, and it only looks for panels when it opens.\
**Do this:** Quit Premiere and open it.

**What happened:** The WhyNot Cut Bridge panel still doesn't appear after reopening Premiere.\
**Why:** The `PlayerDebugMode` setting, which lets Premiere open panels not signed by Adobe, isn't turned on. Claude never changes it, because it's a setting on your computer.\
**Do this:** Run the command that “افحص الجهاز” (“Check the computer”) gives you in Terminal on a Mac or in PowerShell on Windows ([Chapter 2](02-install.md#ch02-run-command)), then reopen Premiere.

**What happened:** You turned on `PlayerDebugMode` but the panel doesn't work.\
**Why:** The command was run while you were signed in to another user account on the computer, or it was pasted into the wrong window, so the setting didn't reach your account.\
**Do this:** While signed in to your usual account on the computer, run the command again in Terminal on a Mac, or in PowerShell on Windows without “Run as administrator”, then reopen Premiere.

**What happened:** Claude says Premiere isn't responding.\
**Why:** Premiere is closed, or the WhyNot Cut Bridge panel is closed, or a dialog box is open in Premiere, so the build request doesn't reach it. Claude doesn't open or close Premiere itself.\
**Do this:** In Premiere, open Window › Extensions › WhyNot Cut Bridge after closing any dialog box open in it.

**What happened:** Premiere was closed during the project build.\
**Why:** The build happens inside Premiere itself, so it stops when Premiere closes, and after a set time Claude tells you it didn't finish. The editing steps completed before it are saved.\
**Do this:** Open Premiere, then write to Claude “كمّل المونتاج” (“Continue the edit”), and it rebuilds from the approved plan.

**What happened:** Premiere asks you to link files (Link Media) when you open the project.\
**Why:** A file the project depends on was moved or deleted, such as a graphic image or a sound effect.\
**Do this:** Write to Claude “Premiere بيطلب Link Media في C0001” (“Premiere is asking for Link Media in C0001”), and it recreates the missing files then rebuilds, keeping your previous project as a backup copy ([Chapter 10](10-revisions.md#ch10-title)).

## Files and fonts {#ch17-files}

**What happened:** Transcription fails for files in iCloud, OneDrive or Dropbox.\
**Why:** The files are saved in the cloud only, not on the computer. That's why it's better to keep the clients folder outside synced folders ([Chapter 2](02-install.md#ch02-first-run)).\
**Do this:** Wait until the files have finished downloading to your computer, then ask for the transcription again.

**What happened:** The client's fonts don't appear in Premiere, or a Fonts not installed message appears.\
**Why:** The fonts are only in `assets/Fonts`, and aren't installed on the computer. The preview video uses the font files directly, but Premiere needs them installed, and installing them is a step you do.\
**Do this:** Install every font in `assets/Fonts`: on a Mac double-click it then Install Font, and on Windows right-click it then Install.

**What happened:** The Arabic letters are disconnected in the graphic images.\
**Why:** The part of the engine that joins Arabic letters together wasn't fully installed, so a fallback method that separates the letters was used.\
**Do this:** Type `/whynot-cut:setup` so Claude fixes the engine.

**What happened:** The names of videos or folders have Arabic letters or spaces in them.\
**Why:** That's allowed: a video with an Arabic name gets a short name in Latin letters that you use in your requests, and spaces in names work as they are.\
**Do this:** Write to Claude “حطيت الملفات، افحصها” (“I added the files, check them”) to see the short name of each video ([Chapter 4](04-client-folder.md#ch04-check)).

## Speed and downloads {#ch17-speed}

**What happened:** Transcription is very slow.\
**Why:** It's running on the processor (CPU) alone, with no speed-up from the graphics card.\
**Do this:** On a Mac, or on Windows without an NVIDIA card, change the transcription model to `large-v3-turbo` ([Chapter 16](16-preferences.md#ch16-title)); with an NVIDIA card, agree to download the speed-up library when Claude offers it (about 520 MB).

**What happened:** The transcription model download stopped halfway.\
**Why:** The connection dropped or the computer was shut down, and what downloaded before that is saved.\
**Do this:** Ask Claude to finish the download, and it picks up where it stopped.

**What happened:** A long video takes a while to transcribe, or its transcription stopped halfway.\
**Why:** A video longer than 10 minutes is transcribed in parts, and each part is saved once it's complete.\
**Do this:** Ask for the transcription again, and it carries on from the last saved part.

> **In 3.0 — not verified yet:** These sections will be completed from real use, and the WhyNot Cut Bridge panel problems change with version 3.0.

## When work stops halfway {#ch17-stopped}

**What happened:** The work stopped halfway, for example because the Claude app or the computer was closed.\
**Why:** WhyNot Cut saves the result of each step once it's complete, so only the work on the step where it stopped is lost.\
**Do this:** Open a new chat in the client folder, and write “كمّل المونتاج” (“Continue the edit”).

**What happened:** Claude stopped in the middle of the edit because you reached your account's usage limit.\
**Why:** Every Claude account has a usage limit that resets after a while, and the steps completed on your computer are saved.\
**Do this:** Once the limit resets, write “كمّل المونتاج” (“Continue the edit”), and it carries on from the last step that finished.

**What happened:** The project build stopped with the message “not enough free space” or “The disk is full”.\
**Why:** Before the build writes anything, it checks that the disk has enough space for it, and if there isn't enough it changes nothing. If the disk fills up during the build, your previous project stays saved.\
**Do this:** Free up space on the disk the message names, then write to Claude “جرّب تاني” (“Try again”).

> **In 3.0 — not verified yet:** What happens if the internet drops, or the disk fills up during work other than the build, or with a damaged video file, will be written here after it's tested.

## Panel and install messages in version 3.0 {#ch17-v3}

In version 3.0 the WhyNot Cut panel shows each problem in one sentence with one button that fixes it, and you don't need to type any command. In the install window, each step's line starts with a mark that says its status: `[OK]` means done, `[!!]` needs attention, and `[XX]` means it failed ([Chapter 2](02-install.md#ch02-one-line)).

**What happened:** A line starting with the mark `[XX]` in the install window.\
**Why:** A step didn't complete, and the most common cause is a download that dropped or arrived incomplete, so the install rejected it. The exact cause is written in the line itself.\
**Do this:** Paste the install line again and press Enter: running it a second time is safe and completes whatever didn't complete.

**What happened:** A line starting with the mark `[!!]`, possibly with a line under it starting with the word `you:`.\
**Why:** A step needs something from you, or the install skipped it for a reason written next to it. The rest of the install completed, and you can start working.\
**Do this:** Do what the `you:` line says, and if it isn't clear, copy it to Claude and ask what to do.

**What happened:** The install stops at the very start because there isn't enough free space.\
**Why:** The disk has less than about 9 GB free, which is what the engine and the transcription model need together. Nothing was downloaded.\
**Do this:** Free up space until the disk has at least 9 GB free, then paste the line again.

**What happened:** A message starting with the word `ERROR` about downloading a file.\
**Why:** The internet dropped, or the file arrived incomplete so the install rejected it, and nothing half-installed is left on your computer.\
**Do this:** Check your internet connection, then paste the line again.

**What happened:** A message saying there's no suitable Python on the computer.\
**Why:** This is a new computer without Python, a program the engine needs. Never install it yourself: the installer that comes with WhyNot Cut downloads its own copy of Python, without computer administrator rights (admin), and on a Mac it doesn't open an Apple window to install extra tools. Before the install, Claude asks you to close Premiere Pro, and After Effects too if it's open, and to open Premiere once afterwards.\
**Do this:** Type `/whynot-cut:start`, and choose “ثبّت دلوقتي (موصى به)” (“Install now (recommended)”) when Claude asks you about installing WhyNot Cut on the computer (about 4 GB, 5 to 20 minutes).

**What happened:** On Windows, the install warns about non-English letters in the engine's location, then asks you for the location.\
**Why:** Some tools may fail in a location that has non-English letters, such as a user folder with an Arabic name.\
**Do this:** Press Enter to accept the suggested location `C:\WhyNotCut`.

**What happened:** On Windows, the same warning appeared and the install carried on without asking you for the location.\
**Why:** In a normal install, the install doesn't ask you for the location, so the engine stays in the location that has non-English letters.\
**Do this:** Run the install line again in customise mode, by pressing the C key during the countdown, and type `C:\WhyNotCut` when it asks you for the location.

**What happened:** The install finished and the Claude app didn't open.\
**Why:** The Claude app isn't on the computer, or the install couldn't open it.\
**Do this:** Open the Claude app, and in a new chat type `/whynot-cut:start`.

> **Tip:** If the Claude app isn't on your computer at all, install it first and sign in with your account ([Chapter 2](02-install.md#ch02-before)).

**What happened:** A “Restart Premiere” card appears in the panel after an update.\
**Why:** WhyNot Cut was updated while Premiere was open, so the old panel is still loaded. If the panel says the update is ready, it installs by itself the next time Premiere closes.\
**Do this:** Save your work, then quit Premiere and open it.

**What happened:** The panel says “The WhyNot Cut engine is not running.”\
**Why:** The engine hasn't started yet or it stopped. It starts by itself when the computer starts, when Premiere opens and when the Claude app opens, and the panel tries again automatically; with the `panel_link: false` setting it doesn't start with the chat ([Chapter 16](16-preferences.md#ch16-title)).\
**Do this:** If the message stays, click “Start engine”.

**What happened:** The Claude badge (the small indicator in the panel that shows Claude's status) says “Claude not installed”.\
**Why:** The Claude app isn't on the computer.\
**Do this:** Install the Claude app and sign in with your account ([Chapter 2](02-install.md#ch02-before)).

**What happened:** The Claude badge asks you to sign in (Sign in to Claude).\
**Why:** You signed out of your account in the Claude app, and signing in is always a step you do.\
**Do this:** Click the open-Claude button in the badge, and sign in with your account.

**What happened:** The Claude badge says the WhyNot Cut plugin in Claude is out of date, with an update button (Update).\
**Why:** The version of the plugin inside the Claude app is older than the rest of WhyNot Cut.\
**Do this:** Click the update button, then open a new chat in Claude.

**What happened:** You asked for some work, and the engine said the model is still downloading, and how many minutes are left.\
**Why:** A large model hasn't finished downloading yet.\
**Do this:** Wait until the download finishes, or agree to use the smaller model that's ready on the computer.

**What happened:** The install says it skipped some models.\
**Why:** There wasn't enough disk space for all the packs, so the install put in the strongest that fits on the disk, and wrote down what it skipped and how to add it.\
**Do this:** When you've freed up space, install the rest from the “Models” page in the panel.

**What happened:** A yellow item in the “Setup checklist” in the panel.\
**Why:** A step didn't complete, and its cause is written next to the item.\
**Do this:** Click the fix button next to the item.

> **In 3.0 — not verified yet:** The install window messages and the names of the panel's cards and buttons may change slightly when version 3.0 is released.

## Automatic fix {#ch17-fix}

In version 3.0, write to Claude “اصلح الجهاز” (“Fix the computer”), or click the fix button in the panel. WhyNot Cut fixes by itself whatever can be fixed without you, such as removing old test panels and restarting the engine, records everything it did, and it is safe to repeat. Whatever is left for you, it shows you in a list.

> **In 3.0 — not verified yet:** The list of what the automatic fix handles and what is left for you will be written here when it's released.

## The diagnostics bundle {#ch17-bundle}

In version 3.0 the check prepares a compressed file (zip) on the desktop with information about the computer and the logs, after hiding private data, and it doesn't include any video or transcript unless you choose to. In the panel, the “Copy diagnostics” button copies a summary of the status for you to send to support.

> **In 3.0 — not verified yet:** The steps for preparing and sending the bundle will be written here with pictures when it's released.

## Sending your feedback and problems {#ch17-feedback}

In version 3.0, to send us feedback about the experience or a problem you ran into: save the diagnostics file, then open the feedback form or email.

1. Save the diagnostics file ([The diagnostics bundle](#ch17-bundle)). The file doesn't include any video or transcript unless you choose to.
2. Open the feedback form or email, and write what you were doing, what happened, what you expected to happen, and the clip or episode number if there is one, such as `C0001`.
3. Attach the diagnostics file, then send.

> **In 3.0 — not verified yet:** Where the feedback form is, and who handles support and when, will be written here once they're decided; until then, send to the email in [“When the problem isn't solved”](#ch17-support).

## When the problem isn't solved {#ch17-support}

If you didn't find your situation in this chapter, or the fix didn't work, or the same error keeps coming back, ask Claude to sum up what it tried and what it found out, then email us at [info@thewhynot.ai](mailto:info@thewhynot.ai) with that summary and the check result.
