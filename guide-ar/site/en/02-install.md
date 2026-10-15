---
title: Installation step by step
slug: 02-install
order: 2
lang: en
dir: ltr
---

# Installation step by step {#ch02-title}

This chapter explains how to install WhyNot Cut on your computer. We start with what you do today, then explain installation in version 3.0: one line you paste into Terminal on a Mac or into PowerShell on Windows (both are text windows that come with the operating system: you paste a command into them and press Enter and it runs, and you type nothing in them except what this guide or Claude gives you), or from inside the Claude app: you add WhyNot Cut to it, then type one request. After installation, [Chapter 3](03-quick-tour.md#ch03-title) takes you to your first project.

> **Tip:** Today (before version 3.0): follow only the sections [“First time in the Claude app”](#ch02-claude-first) and [“Today: installing with the start wizard”](#ch02-first-run), then go to [Chapter 3](03-quick-tour.md#ch03-title). On a Mac, read [“macOS permissions before they appear”](#ch02-mac-permissions) before them. The rest of this chapter describes installation in version 3.0.

## First time in the Claude app {#ch02-claude-first}

Everything you ask of WhyNot Cut, you write to Claude in the Claude app on your computer. If you have not used it before, this is all you need to know:

- **The message box** at the bottom of the window: type your request or the command in it, then press Enter.
- **New chat**: a button at the top of the sidebar. Open a new chat after every install or update.
- **The folder**: before the first message in every new chat, choose the folder Claude works in, using the folder button in the chat window: the clients folder (such as `WhyNot Clients`), or the client folder you will work on.
- **The + button** next to the message box: this is where you add WhyNot Cut to the app, as in the next section.
- **Quitting the app completely**: closing the window alone may leave Claude running in the background. On a Mac press Cmd+Q with the Claude app in front. On Windows right-click the Claude icon next to the clock (it may be hidden under the ^ arrow) and choose Quit.

![The parts of the Claude app this guide mentions.](shots/02-install-1.png)

*The parts of the Claude app this guide mentions.*

> **Tip:** The first time the Claude app opens a chat in a new folder (the clients folder or a client folder), it asks whether you trust this folder. Approve once for each folder, and WhyNot Cut will not ask your permission at every step after that.

> **In 3.0 — not verified yet:** The names and places of the buttons in the Claude app may differ slightly depending on the app version.

## Today: installing with the start wizard {#ch02-first-run}

Today our team sends you the `whynot-cut-marketplace` folder. Move it to the Documents folder on your computer and leave it there: do not move or delete it after that, because the Claude app reads WhyNot Cut from that place, so if you move it, the app cannot find it.

1. **Copy the folder's path.** On a Mac: open the folder's menu with a right-click (on the trackpad click with two fingers, or hold Control while you click), then hold down the Option key while the menu is open, and the command Copy … as Pathname appears; choose it. On Windows: hold Shift and right-click the folder, and choose Copy as path.
2. **Add WhyNot Cut to the Claude app.** What you add is called “the WhyNot Cut plugin”: the part that teaches Claude WhyNot Cut's commands and how it works. Open a new chat, type the first line in the message box and press Enter, then the second line and press Enter. In the first line, delete all of `"<path>"`, quote marks included, and paste the path you copied in its place: on a Mac type the two quote marks around it yourself; on Windows the copied path comes with them, so the line ends up with only two quote marks.

   ```
   /plugin marketplace add "<path>"
   /plugin install whynot-cut@thewhynot-ai
   ```

   On a Mac, if the folder is in Documents, the first line looks like this after the change, with your computer's user name instead of `sample`:

   ```
   /plugin marketplace add "/Users/sample/Documents/whynot-cut-marketplace"
   ```

   If Claude replies to the line with a message that does not contain the word error or failed, the line worked; go on to the next line. If an error message appears after the first line, check the path you copied in step 1, then repeat the line. Or click + › Plugins › Add plugin (in this order: + first, then Plugins, then Add plugin), and choose the same folder.
3. **Quit the Claude app completely** ([First time in the Claude app](#ch02-claude-first)), then open it again.
4. **Run the start wizard.** Open a new chat, and type “أول مرة أستخدمه” (“First time using it”) or the following command, then press Enter:

   ```
   /whynot-cut:start
   ```

> **In 3.0 — not verified yet:** In version 3.0 this section is replaced by the one-line install (the section “Install with one line”).

The start wizard takes you one step per message, and checks each step before the next:

1. It checks the computer. If the engine is not installed, it explains what will be installed and asks you once.
2. It links Premiere Pro. If Premiere is not on this computer, it carries on: you get the preview video and an XML project file, a project file in a general format that Premiere imports from File › Import instead of a native Premiere project, so you can open it later on a computer that has Premiere.
3. It asks about your preferences: where the clients folder goes, whether it stops for you to approve every plan, the transcription speed, and what name to call you ([Chapter 16](16-preferences.md#ch16-title)).
4. It creates the first client folder, and shows you where each file goes ([Chapter 4](04-client-folder.md#ch04-title)).
5. After you add the files, it checks what you added and tells you what is missing, then starts setting up the new client ([Chapter 5](05-new-client.md#ch05-title)).

What the wizard installs with your approval, needing about 4 GB of free space in total:

- **The engine**, the program that does WhyNot Cut's work on your computer in the background: about 400 MB, in a few minutes, inside the `~/.whynot-cut` folder. The `~` sign means your user folder on the computer, such as `/Users/sample` on a Mac, or `C:\Users\Sample` on Windows. On a Mac this folder does not show in Finder because its name starts with a dot, and you don't need to open it.
- **The transcription model** `large-v3`: about 3 GB, once, and it carries on from where it stopped if the download is cut off.
- **The WhyNot Cut Bridge panel** ([Chapter 1](01-intro.md#ch01-panels)): quit Premiere before it is installed, then open it.
- **With an NVIDIA card**: an optional speed-up library (about 520 MB) that makes transcription about 8 times faster.
- **The clients folder**: do not put it inside a folder synced with iCloud, OneDrive or Dropbox, because files that are kept only in the cloud make transcription fail.

> **Careful:** The WhyNot Cut Bridge panel is not signed by Adobe. Signing is a digital seal from the company that proves the file is genuine and unchanged. So Premiere only opens it if the Adobe setting called `PlayerDebugMode` is turned on; that setting allows unsigned panels to load. You change it yourself with the command Claude gives you (see [Running a command Claude gave you](#ch02-run-command)); Claude never changes it. And you don't need to turn it on at all: without it you import the XML file into Premiere by hand from File › Import, everything else works as it is, and version 3.0 removes this panel.

## Running a command Claude gave you {#ch02-run-command}

Sometimes the fix is something Claude does not do itself, such as installing a program or changing an Adobe setting, so it gives you a ready command to run yourself. Don't type it in Claude's message box; run it like this:

1. Open the window. On a Mac: press Cmd+Space, type Terminal, then Enter. On Windows: open the Start menu, type PowerShell, then click it to open it as usual; do not choose Run as administrator.
2. Copy the command from Claude's message: click the copy button next to the command if there is one, or select it with the mouse and press Cmd+C on a Mac or Ctrl+C on Windows. Then click inside the window and paste it: Cmd+V on a Mac, and on Windows Ctrl+V or the right mouse button.
3. Press Enter, and wait until the command finishes: it has finished when a new line appears at the bottom of the window waiting for you to type in it. On a Mac that line ends with the `%` sign, and on Windows it starts with the two letters `PS`. If the word error appears, copy everything in the window and send it to Claude.
4. If the command is for Premiere, quit Premiere and open it again. Then go back to Claude and write that you have finished, so it can check the result.

![The command is pasted into Terminal on a Mac (or PowerShell on Windows), not into the Claude chat.](shots/02-install-2.png)

*The command is pasted into Terminal on a Mac (or PowerShell on Windows), not into the Claude chat.*

## macOS permissions before they appear {#ch02-mac-permissions}

On a Mac, macOS asks you the first time a program does something the system protects. These messages are normal, and each needs one click from you. Here is what you will see, why, and what to click.

### Access to files (Files & Folders) {#ch02-mac-files}

- **What you see:** a message from macOS saying that Claude, or Premiere Pro, “would like to access files” in the Documents folder or on an external drive.
- **Why:** the clients folder and your clients' files are in Documents or on an external drive. Claude and WhyNot Cut read them, and so does Premiere Pro when the project is built inside it.
- **What to click:** Allow. If you refused by mistake, open System Settings › Privacy & Security › Files and Folders, find the program you refused, Claude or Premiere Pro, and turn on the switch next to Documents Folder, and next to Removable Volumes if your files are on an external drive, then quit the program and open it again.

![Access to files: click Allow.](shots/02-install-3.png)

*Access to files: click Allow.*

### Controlling Adobe apps (Automation) {#ch02-mac-automation}

- **What you see:** a message saying that Claude “wants access to control” an Adobe app, such as After Effects.
- **Why:** WhyNot Cut asks the Adobe app to build the project, such as the motion project in After Effects, and macOS asks before one program controls another.
- **What to click:** OK or Allow. If you refused by mistake, open System Settings › Privacy & Security › Automation, and under Claude turn on the switch next to the Adobe app.

![Controlling Adobe apps: click OK.](shots/02-install-4.png)

*Controlling Adobe apps: click OK.*

### Pasting a line into Terminal {#ch02-mac-terminal}

- **What you see:** a Terminal window, and at the bottom of it a line ending with the `%` sign, waiting for you to type in it.
- **Why:** some steps are a ready line that you paste yourself, such as the install line, or a command Claude gives you that it does not run itself.
- **What to click:** paste the line with Cmd+V, then press Enter, and wait until a new line ending with the `%` sign comes back at the bottom of the window; that means the line has finished ([Running a command Claude gave you](#ch02-run-command)).

![The line has finished when the line ending with the % sign comes back.](shots/02-install-5.png)

*The line has finished when the line ending with the % sign comes back.*

### A password request in Terminal {#ch02-mac-password}

- **What you see:** the word Password: on the last line in Terminal.
- **Why:** some commands need the computer owner's permission before they run. The WhyNot Cut install line never asks for the password.
- **What to click:** type the password you use to unlock your Mac, then press Enter. Neither letters nor dots appear while you type; that is normal. If this request appears with a line that neither Claude nor this guide gave you, do not type the password.

![The password does not show while you type it.](shots/02-install-6.png)

*The password does not show while you type it.*

> **In 3.0 — not verified yet:** The wording of these messages and the places of their buttons will be matched against macOS when version 3.0 is tested on a Mac.

## What you need before installing version 3.0 {#ch02-before}

- **The Claude app** installed, with your account signed in. Download it from claude.ai/download and sign in yourself before you start.
- **Premiere Pro**, and **After Effects** if you use it, installed under your own licence, and **the Creative Cloud app** signed in with your Adobe account.
- **Free space**: at least about 9 GB for the engine and the transcription model, and more with the other models, then several GB per client. The first line the installation writes is the total size it will download.
- **The computer**: a Mac with an Apple Silicon or Intel processor and macOS 14 or later, or Windows 10/11. The captions tool WhyNot Kalam also works on an Intel Mac, but it is slower ([Chapter 13](13-kalam.md#ch13-pack)). The full requirements, including memory and the Claude account, are in [the table in Chapter 1](01-intro.md#ch01-requirements). You don't need computer administrator rights (admin), or to install any other program yourself.
- **An internet connection** until the downloads finish.

> **In 3.0 — not verified yet:** Installation on a Mac has not been tried yet on a real computer, so it stays “Not verified” until it is tried.

## Install with one line {#ch02-one-line}

In version 3.0 you install WhyNot Cut with one line: one line on a Mac and one line on Windows. You don't download or open any file yourself, and no warning from macOS or Windows appears.

1. **Open Terminal or PowerShell.** On a Mac: press Cmd+Space, type Terminal, then Enter. On Windows: open the Start menu, type PowerShell, then click it to open it as usual; do not choose Run as administrator. Before you paste the line, save your work and quit Premiere Pro, then After Effects, if they are open.
2. **Copy the line for your computer and paste it, then press Enter.** You also find both lines on the download page on the thewhynot.ai website. To paste, press Cmd+V on a Mac, and on Windows Ctrl+V or the right mouse button.

   On a Mac, in Terminal:

   ```
   curl -fsSL https://dl.thewhynot.ai/install.sh | bash
   ```

   On Windows, in PowerShell:

   ```
   irm https://dl.thewhynot.ai/install.ps1 | iex
   ```

   ![What appears first: the total size, then a 10-second countdown.](shots/02-install-7.png)

   *What appears first: the total size, then a 10-second countdown.*
3. **Don't press anything, and leave the window open.** The first thing to appear is two lines giving the total size: in English Installing everything WhyNot Cut needs, then in Arabic “جارٍ تثبيت كل ما يحتاجه WhyNot Cut (حوالي … جيجابايت)”. After them the line Press C to customise appears, with a 10-second countdown. If you press nothing, everything is installed with the default answers, which are the strongest settings your computer can handle. If you press C, it asks you about the engine's location, the transcription model, the language and the clients folder; each question has a default answer, and you press Enter to accept it.
4. **Wait until the lines finish.** The steps appear line after line. How long it takes depends on your internet speed, because most of the size is downloads. The transcription model keeps downloading in the background after the window finishes, and you can start working in the meantime.
5. **How you know it worked.** At the end the checklist appears: one line per step, starting with `[OK]` if it finished, or `[!!]` if it needs attention, with its reason, and under it a line starting with `you:` if something is needed from you. Then a line asks you to open Claude and type `/whynot-cut:start`. The Claude app may already have opened by itself on the start wizard, with the command typed in the message box: press Enter. If it did not open, open it yourself, open a new chat, and type `/whynot-cut:start`.

   ![Installation finished: every line \[OK\].](shots/02-install-8.png)

   *Installation finished: every line \[OK\].*
6. **If an error appears**, such as a line starting with `[XX]` or a message starting with the word `ERROR`, that is a step that did not finish, usually because a download was cut off or arrived incomplete, so the installation rejected it. Paste the same line again and press Enter: running the installation a second time is safe, and it finishes whatever did not finish. If the error repeats, see [Chapter 17](17-troubleshooting.md#ch17-v3).

> **In 3.0 — not verified yet:** The two lines work from the day version 3.0 is released, and have not been tried yet on a clean computer or on a real Mac.

## From inside Claude: “Install WhyNot Cut” {#ch02-from-claude}

If you are starting from the Claude app, you don't need Terminal or PowerShell:

1. Open the Claude app and make sure you are signed in.
2. Add WhyNot Cut to the Claude app: click + › Plugins › Add plugin (in this order: + first, then Plugins, then Add plugin), and paste the WhyNot Cut link you find on the download page.
3. Open a new chat and type “ثبّت WhyNot Cut” (“Install WhyNot Cut”), or type `/whynot-cut:start`, then press Enter.
4. A single choice card appears. Choose “Install everything (recommended)”, which is already selected. The other choice shows the models and packs in a list, all of them selected. A pack is a set of models and tools downloaded together, such as the WhyNot Kalam pack.
5. Follow the progress in the chat, stage after stage. Claude finishes every step that does not need you by itself, and at the end tells you what is left for you, such as restarting Premiere or opening a new chat.

![Adding WhyNot Cut to the Claude app before “Install WhyNot Cut”.](shots/02-install-9.png)

*Adding WhyNot Cut to the Claude app before “Install WhyNot Cut”.*

This path runs the same program as the one line, so the result is the same. Running either path again repairs and updates the installation ([Chapter 18](18-update-uninstall.md#ch18-title)).

> **In 3.0 — not verified yet:** The WhyNot Cut link you paste in step 2 appears on the download page when version 3.0 is released.

## What is installed automatically {#ch02-what-happens}

On both paths the installation finishes this list by itself, with the default answers, without questions:

1. **The engine**: the program that does WhyNot Cut's work on your computer in the background, with its own copy of Python (a programming language the engine needs; you never deal with it), the ffmpeg tool for processing video and audio, and the interface fonts. It is always running: it starts when the computer starts, when Premiere opens, and when Claude opens. You find it in Login Items on a Mac and in Startup apps on Windows, and you can stop it from there.
2. **The WhyNot Cut plugin in the Claude app**, turned on, with a permission that lets the Claude app run the WhyNot Cut engine without asking you every time (the default answer: yes).
3. **On Windows**: a small tool (Git for Windows) that Claude needs to run WhyNot Cut's commands on Windows; you never deal with it.
4. **The WhyNot Cut panel** in Premiere Pro (from Window › UXP Plugins) and in After Effects (from Window › Extensions): one panel in each app, and the old panels, such as WhyNot Cut Bridge, and the test panels are removed.
5. **The models** (next section), in the background. If your computer has an NVIDIA card, the speed-up libraries are installed with them, so transcription becomes about 8 times faster.
6. **Where the clients folder goes**: on a Mac, `WhyNot Clients` inside Documents. On Windows, `D:\WhyNot Clients` if your computer has a D drive, otherwise inside Documents too. If Documents is synced with iCloud or OneDrive, the clients folder goes in your user folder outside it, because files kept only in the cloud make transcription fail.
7. **The Claude app opens on the start wizard**, and the wizard asks about your preferences and creates the first client folder, then shows you where each file goes.
8. **A final check**: the checklist, where every line is `[OK]`, or `[!!]` with its reason and how to fix it (the section “Checking the result”). In the panel the same list appears in green and yellow.

The installation never asks for computer administrator rights, never turns on the Adobe setting for unsigned panels, never moves or deletes client folders, and never replaces the Claude app's settings file: it only adds what belongs to WhyNot Cut, after a backup copy.

> **In 3.0 — not verified yet:** Some things in this list, such as the engine starting with the computer and the new After Effects panel, have not been tried yet on a clean computer.

## The models {#ch02-models}

A model is a large file holding ready-made know-how for understanding speech; the engine uses it to turn audio into text. What WhyNot Cut needs is installed automatically, and the rest is one click away:

| Pack | Why | At install |
| --- | --- | --- |
| Main transcription: `large-v3` | The most accurate transcript (about 2.9 GB). | Installed |
| Fast transcription: `large-v3-turbo` | Faster transcription for long episodes. | Installed |
| Small models: `medium`, `small` | Smaller models, used only if there is not enough space or memory for the large ones. | Downloaded when needed |
| WhyNot Kalam pack | The captions tool: a model for Egyptian Arabic, a model for English, and a tool that sets the timing of every word ([Chapter 13](13-kalam.md#ch13-title)). | Installed |
| WhyNot Hush | The tool that removes silences; it uses the WhyNot Kalam models or the main transcription model ([Chapter 12](12-hush.md#ch12-title)). | Nothing extra |
| Fonts | The four interface and guide fonts. | Installed |

- **Matched to your computer**: the installation reads the graphics card (NVIDIA or Apple Silicon), the memory and the free space, and installs everything the computer has room for. If there is not enough space, it keeps the strongest that fits, and tells you what it skipped and how to add it later.
- **In the background**: if a download is cut off, it carries on from where it stopped.
- **No waiting at the first click**: if you ask for work whose model is still downloading, the engine tells you how many minutes are left, then waits or offers you a smaller model that is already on the computer.
- **The Models page** in the WhyNot Cut panel: for each model, its status (installed, downloading with the percentage, or available), its size, what it is used for, an install button and a delete button, and a button to download them all. You can also ask Claude to show you the list of models.

> **In 3.0 — not verified yet:** The sizes of some packs and the names of the buttons on the Models page will be added here when they are released.

## Five steps you do yourself {#ch02-only-you}

These are limits set by the operating system or by other companies, and each has one step:

1. **Installing the Claude app and signing in.** Download it from claude.ai/download, then sign in with your account. WhyNot Cut never shows you a sign-in page of its own.
2. **Adobe apps under your licence.** Install Premiere Pro and After Effects from the Creative Cloud app, and sign in to it.
3. **The big downloads.** Leave the computer on and connected to the internet until the models finish. You can work in the meantime.
4. **Folder permission on a Mac.** The first time Claude, or Premiere Pro, opens files in Documents or on an external drive, macOS asks for your permission: click Allow. If you refused by mistake, turn it on from System Settings › Privacy & Security › Files and Folders: find the program you refused, and turn on the switch next to Documents Folder ([macOS permissions](#ch02-mac-permissions)).
5. **Restarting Premiere and After Effects once** after the panels are installed. Claude or the installation does this itself if they have no unsaved work. If they have unsaved work, nothing is closed: you are asked to save your work, then click the restart button.

> **In 3.0 — not verified yet:** The messages and pictures for these steps will be reviewed when version 3.0 is released.

## Checking the result {#ch02-check}

The sign of success is that the checklist at the end of the installation has no line starting with `[XX]`. The best result is every line `[OK]`, and each `[!!]` line comes with its reason and what to do ([Chapter 17](17-troubleshooting.md#ch17-v3)). You find the same list in the WhyNot Cut panel inside Premiere, called “Setup checklist”, with four items: “Engine”, “Premiere link”, “Claude” and “Clients folder”. A yellow item comes with a button that fixes it in one click.

![All items green: the computer is ready for the first client.](shots/02-install-10.png)

*All items green: the computer is ready for the first client.*

The detailed check is optional, and you mostly need it only with support. Tell Claude “افحص الجهاز” (“Check the computer”), and it runs these two commands itself; the check changes nothing on the computer:

*Claude runs this — you don't type it*

```
reel --version
reel doctor
```

The check shows whether the computer is ready, the list of fixes and who does each fix (Claude or you), the graphics card and the Adobe apps found, and the copies of WhyNot Cut on the computer if there is more than one. The first line of the check has the name WhyNot Cut and its version number, such as `WhyNot Cut 3.0.0`; if Claude mentions another name or an old number, see [Chapter 17](17-troubleshooting.md#ch17-title).

> **In 3.0 — not verified yet:** Pictures of the checklist and of the “Setup checklist” will be taken when version 3.0 is released.

## The internal WhyNot Cut Setup program {#ch02-setup-app}

The WhyNot Cut Setup program does what the one line does, but it is an app you open with a double-click, and it shows the checklist in a window. It is an internal version for The Why Not AI team's own computers only, not for your agency's computers, and it is not published for public download because it is unsigned. If it did not reach you from us directly, install with the one line.

1. **Open the file with a double-click.** On a Mac open `WhyNotCut.dmg`, then the WhyNot Cut Setup app inside it. On Windows open `WhyNotCut-Setup.exe`.
2. **If the Claude app is not on your computer**, click Install Claude for me. The program downloads the official installer from Anthropic, checks its signature and opens it. Sign in with your account, then the program carries on by itself.
3. **Click Install everything**, and follow the checklist until all its items are green. The Customise button is optional, and opens the same questions with their default answers.

On a Mac, because the internal version is not notarised by Apple, macOS blocks it the first time you open it, and a message appears saying it cannot verify the app:

1. Click Done or OK to close the message; do not click Move to Trash.
2. Open System Settings › Privacy & Security, and scroll down to the Security section until you find a line about WhyNot Cut Setup, then click Open Anyway.
3. Type your Mac's password if asked, then click Open. After that the app opens, and the message does not appear again with this version.

![The internal version on a Mac: Open Anyway in the security settings.](shots/02-install-11.png)

*The internal version on a Mac: Open Anyway in the security settings.*

On Windows, because the version is unsigned, Windows shows a blue window when you open it, saying Windows protected your PC:

1. Click More info under the text.
2. Make sure the file name is `WhyNotCut-Setup.exe`, then click Run anyway.

![The Windows warning with an internal version: check the file name, then Run anyway.](shots/02-install-12.png)

*The Windows warning with an internal version: check the file name, then Run anyway.*

> **Careful:** Do this, on a Mac and on Windows, only with a file that reached you from our team directly. If the warning appears with a file you downloaded from anywhere else, don't open it; write to us, and install with the one line.

> **In 3.0 — not verified yet:** The look of this program and the names of its buttons may change, because it is for testing inside our team.

## Turning on Magnific (optional) {#ch02-magnific}

Linking your Magnific account to the Claude app is an optional step, and WhyNot Cut works fully without it. The details are in [Chapter 15](15-magnific.md#ch15-title).

> **In 3.0 — not verified yet:** The linking steps, with pictures, will be written here when they are released.
