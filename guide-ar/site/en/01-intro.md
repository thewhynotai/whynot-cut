---
title: Introduction
slug: 01-intro
order: 1
lang: en
dir: ltr
---

# Introduction {#ch01-title}

WhyNot Cut is an editing tool from The Why Not AI that works inside the Claude app. Its full name is WhyNot Cut · Powered by thewhynot.ai. It takes the raw video of a person talking to camera, in Arabic, in English or in both, and turns it into a native Premiere Pro project with the graphics and the on-screen text (captions) in the client's brand, so you carry on editing from where the tool stopped.

This guide takes you from installation to your first finished project, and then through daily work: setting up clients, editing videos, cutting podcast episodes into reels, and motion videos.

## What WhyNot Cut gives you {#ch01-what}

For every raw video you ask it to edit, you get:

- **A complete Premiere Pro project** with the right sequence settings, with the animated graphics and the on-screen text in the client's fonts and colours, with correct Arabic diacritics and correct right-to-left direction.
- **A transcript** with the timing of every word, made with the Whisper `large-v3` model on your computer. A model is a large file holding ready-made know-how for understanding speech; WhyNot Cut uses it to turn audio into text. If your computer has an NVIDIA graphics card, transcription becomes about 8 times faster once the NVIDIA library is installed with your approval; that library is an extra file from NVIDIA that lets the graphics card speed up transcription ([Chapter 2](02-install.md#ch02-first-run)). On a Mac, transcription for editing runs on the processor (CPU) today, so it is slower than with an NVIDIA card. The speed of WhyNot Hush and WhyNot Kalam on a Mac is in Chapters [12](12-hush.md#ch12-limits) and [13](13-kalam.md#ch13-pack).
- **Cleaned dialogue audio** with the silences removed, plus proof that no word was removed.
- **Editing decisions built on the story**: the hook, the key phrases on screen, lists, B-roll cards, punch-ins and sound effects (SFX).
- **A preview video** in MP4 where you watch the planned edit before anything is built.
- **An evidence-based QC (quality check)**: the project is checked from Premiere's own frames, not from assumptions.

Besides editing a single video, WhyNot Cut has two other modes:

- **Podcast mode**: from a full 16:9 episode to a reels plan with timecodes and content types; then you pick the reels, and each reel is made in 9:16 with the publishing text for YouTube, Instagram and TikTok ([Chapter 8](08-podcast.md#ch08-title)).
- **Motion mode**: from the audio of part of an episode to a motion graphics video built as a native After Effects project ([Chapter 9](09-motion.md#ch09-title)).

Version 3.0 adds three tools for the editor inside the WhyNot Cut panel in Premiere: WhyNot Tidy organises the project, WhyNot Hush removes silences, and WhyNot Kalam writes the captions (Chapters [11](11-tidy.md#ch11-title), [12](12-hush.md#ch12-title) and [13](13-kalam.md#ch13-title)).

## What WhyNot Cut does not do {#ch01-not}

The tool prepares a strong project for you, but it does not replace the editor. These are its limits, plainly:

- **It does not export the final video.** The editor finishes the edit, sets the final sound (mix) and exports the video (render). There is no exported final video unless you export it. The only exception is motion mode: it exports an MP4 from After Effects, but the final look and the final export are still up to you ([Chapter 9](09-motion.md#ch09-results)).
- **It does not change the client's original files.** The `assets/` folder and the `data/` folder are read-only: nothing is written to them, moved out of them or deleted from them. All editing results are written to `output/`, and the handoff file `HANDOFF.md` is written straight into the client folder, next to the `assets/` folder and the `data/` folder (how to open this kind of file is in [How to read this guide](#ch01-reading)).
- **It does not lose your work.** A rebuild keeps your previous project as a backup copy ([Chapter 10](10-revisions.md#ch10-protect)), and work that stopped halfway carries on from the last step that finished ([Chapter 6](06-edit-one-video.md#ch06-request)).
- **It does not make things up.** It does not invent facts about the client, brand rules, words nobody said, timings, medical information, music or licences. Anything not found in the client's files is written as “unavailable”.
- **It does not publish anything.** The publishing text in podcast mode is written to files, and nothing is uploaded to any platform.
- **It does not change system settings or Adobe security settings.** If a change like that is needed, Claude gives you the command to run yourself (how to run it is in [Chapter 2](02-install.md#ch02-run-command)).
- **It does not say “ready” without proof.** A video is only called ready if QC passed in the same message and nothing in the “Needs you” list stops it. That list holds what is waiting for your decision or your work.

## Three phrases sum up the work {#ch01-verbs}

All you need to know at the start is three actions: **Drop the files · Say what you want · Approve the plan**.

| What you do | What that means in practice | Details |
| --- | --- | --- |
| Drop the files | Put the logo, fonts, photos and colour file in `assets/`, and the raw videos in `data/Raw/`. | [Chapter 4](04-client-folder.md#ch04-title) |
| Say what you want | Write your request to Claude in your own words, such as “عدّل الفيديوهات الجديدة” (“Edit the new videos”), or use a command such as `/whynot-cut:edit`, typed in the same message box ([How to read this guide](#ch01-reading)). | [Chapter 6](06-edit-one-video.md#ch06-title) |
| Approve the plan | Review the plan summary and the preview video, then approve, and the project is built in Premiere Pro. | [Chapter 6](06-edit-one-video.md#ch06-approval-chat) |

![You write the request in your own words; you don't need to memorise any command.](shots/01-intro-1.png)

*You write the request in your own words; you don't need to memorise any command.*

## Requirements for version 3.0 {#ch01-requirements}

These are the requirements for version 3.0. Today, the version you have works with Premiere Pro 2022 or later through the WhyNot Cut Bridge panel, and needs about 4 GB for the engine (the program that does WhyNot Cut's work on your computer in the background) and for the transcription model. To find out your version, ask Claude “إيه رقم نسخة WhyNot Cut؟” (“What version of WhyNot Cut do I have?”); it checks the installed version and tells you its number.

The requirements:

| Item | What you need |
| --- | --- |
| Operating system | macOS 14 (Sonoma) or later, or Windows 10/11 |
| Processor in a Mac | Apple Silicon or Intel; everything works on both. On an Intel Mac the captions tool WhyNot Kalam runs the same models on the processor (CPU), so it is slower |
| Memory (RAM) | 16 GB recommended; 8 GB works but is slower |
| Premiere Pro | 26.5 or later for the new WhyNot Cut panel and its tools |
| After Effects | Version 25 or later, only for motion mode and for After Effects outputs when you ask for them |
| Claude | The Claude app on the computer, and a separate Claude account for each editor, who signs in to it themselves. The Pro plan is enough; we recommend the Max plan for daily agency work. WhyNot Cut adds no charges for using AI |
| Disk space | At least about 9 GB for the engine and the transcription model, and more with the other models; then a few GB per client |
| Graphics card | Optional on Windows: an NVIDIA card, with the NVIDIA library installed with your approval, makes transcription about 8 times faster |

To see what is in your Mac: open the Apple menu (the apple at the top of the screen), then About This Mac. There you find the macOS number, and next to Chip the name of an Apple processor, such as Apple M1 or Apple M2, if your computer is Apple Silicon, or next to Processor the word Intel if your computer is Intel. To find the Premiere Pro number: on a Mac from Premiere Pro › About Premiere Pro, and on Windows from Help › About Premiere Pro.

> **In 3.0 — not verified yet:** The final minimums, including memory, will be published after testing on real computers, and it is not decided yet whether version 3.0 works with Premiere Pro versions older than 26.5.

## For the agency owner {#ch01-owner}

If you are deciding for a whole team, here is what matters to you in one place:

> - **What it gives your team:** each editor turns raw video into a native Premiere Pro project in the client's brand, with a preview video and a quality check. A podcast episode becomes a reels plan, usually 8 to 15 reels per hour ([Chapter 8](08-podcast.md#ch08-title)). Review, approval and export stay with the editor.
> - **What each editor needs:** their own Claude account that they sign in to themselves, their own Adobe licence, and WhyNot Cut installed on their own computer, meeting the requirements in the table above. Magnific is optional.
> - **Where the data stays:** Video and audio files are never uploaded. Claude reads text (the transcript and the plan) and a few still images: some timeline frames for checking, and brand photos. ([Where your clients' data stays](#ch01-data)) Besides the transcript and the plan, it reads the client's brief and notes. In version 3.0, when you use WhyNot Kalam, only the caption text reaches Claude ([Chapter 13](13-kalam.md#ch13-title)). If the editor uses Magnific, only the images they ask it to process, such as the client's logo, are sent to it, from their own account ([Chapter 15](15-magnific.md#ch15-title)).
> - **Where client folders are kept:** on the computer's own disk, or on an external drive. A drive shared between computers will be supported once it has been tested.
> - **Working as a team:** two editors can work on one client, each on a different video. If two people start building the same video, WhyNot Cut stops the second build and says why in a clear message.
> - **When you reach the Claude usage limit:** everything finished stays saved on the computer, and once the limit resets the editor types “كمّل المونتاج” (“Continue the edit”), and it carries on from the last step that finished ([When work stops halfway](17-troubleshooting.md#ch17-stopped)).
> - **Updating the team's computers:** each computer is updated on its own, by running the installation on it again ([Updating in version 3.0](18-update-uninstall.md#ch18-update)). The update keeps the previous version on the computer.
> - **Help:** each editor sends their feedback and problems as in [“Sending your feedback and problems”](17-troubleshooting.md#ch17-feedback).
> - **Mac status:** WhyNot Cut supports Macs with Apple Silicon or Intel processors (the table above), but it has not been tried yet on a real Mac, neither the version you have today nor version 3.0.
> - **What is not finished yet:** the one-line install on clean computers, the new WhyNot Cut panel, the three tools WhyNot Tidy, WhyNot Hush and WhyNot Kalam, the Magnific link, and storage on a shared drive. Each of them carries the grey line “not verified yet” in its chapter.

> **In 3.0 — not verified yet:** Storage on a shared drive, what happens at the Claude usage limit, going back to an earlier version, and who your team contacts for support will be written in their final form after testing.

## Where your clients' data stays {#ch01-data}

Video and audio files are never uploaded. Claude reads text (the transcript and the plan) and a few still images: some timeline frames for checking, and brand photos.

- Each client's folder stays on your computer, or on the drive you chose, and the transcript is made on your computer.
- Claude runs on the editor's own Claude account. Besides the transcript and the plan, it reads the client's brief and the client's standing notes ([Chapter 5](05-new-client.md#ch05-research)).
- WhyNot Cut sends no data about your use to anyone, and does not train any model on your files or your clients' files.
- What Anthropic does with what Claude reads follows the privacy settings in your own Claude account.

## The WhyNot Cut panel inside Adobe apps {#ch01-panels}

Claude builds Premiere Pro projects and After Effects projects through a small panel inside each app. Today it is called “WhyNot Cut Bridge”, and you find it in both apps in this menu:\
Window › Extensions › WhyNot Cut Bridge\
You don't need to click anything in it; it only shows the status of the work. If Claude tells you the app is not responding, open the panel from this menu. This guide always calls it “the WhyNot Cut Bridge panel”.

In version 3.0 a new panel takes its place in Premiere Pro, called “the WhyNot Cut panel”. You open it from Window › UXP Plugins, the menu that holds the new panels in Premiere; you don't need to install anything from it yourself. From the panel you follow the work and approve the plan ([Chapter 7](07-premiere-panel.md#ch07-title)). In After Effects the WhyNot Cut panel is in Window › Extensions. Wherever the guide says “the WhyNot Cut panel”, it means the new panel in both apps.

> **In 3.0 — not verified yet:** The new panel is not in the version you have today; use the WhyNot Cut Bridge panel until it reaches you.

## How to read this guide {#ch01-reading}

Commands, paths (a path is a file's address on your computer: the names of the folders that lead to it, in order) and file names are always written in a different typeface, such as `data/Raw/`. You don't need to memorise any command: it is enough to write your request to Claude in your own words. You can write to Claude in English or in Arabic; where this guide shows a request in Arabic, its English meaning follows in parentheses. In the chapters you will find two kinds of dark command boxes.

**A box that starts with `/`:** a command you type yourself in the message box in the Claude app, then press Enter (on a Mac keyboard it is called return, and that is what the guide means wherever it says Enter). For example:

```
/whynot-cut:help
```

This command shows a short sheet of WhyNot Cut's commands and highlights the right one for where you are now.

**A box with “Claude runs this — you don't type it” above it:** a command Claude runs by itself in the background. These commands start with the word `reel`, the name of the engine's tool. We show them only so you recognise them in Claude's messages; you never type them yourself. For example, the command that checks the computer:

*Claude runs this — you don't type it*

```
reel doctor
```

Some boxes show a file's path so you know where it is, or ready-made text for you to copy, and the text before them tells you what to do with it.

Files whose names end in `.md`, such as `HANDOFF.md`, are ordinary text files. Open them with a right-click, then Open With › TextEdit on a Mac, or Open with › Notepad on Windows. Or ask Claude to show you their contents in the chat, such as “اعرضلي ملف التسليم” (“Show me the handoff file”). Where the guide says “right-click” on a Mac without a mouse: click with two fingers on the trackpad, or hold the Control key while you click.

In the chapters you will find three kinds of boxes: a **Tip** that saves you time, a **Careful** box that protects you from a common mistake, and a quiet line under a thin grey rule that starts with the badge **“In 3.0 — not verified yet”**, for a part of version 3.0 that has not been tested yet: if you have the 3.0 test version, try it and tell us what you found; if you have version 2.x, it is not there for you yet ([Chapter 0](00-welcome-testers.md#ch00-title)). All the examples and screenshots come from a fictional client called “Example Clinic”, whose doctor is “Dr. Sample Example”.

> **Tip:** Chapters [2](02-install.md#ch02-title) and [3](03-quick-tour.md#ch03-title) are for installation and the first project. Chapters [4](04-client-folder.md#ch04-title), [5](05-new-client.md#ch05-title) and [6](06-edit-one-video.md#ch06-title) are the daily work: the client folder, setting up a new client, and editing one video. [Chapter 19](19-glossary.md#ch19-title) has a glossary and all the commands on one page.
