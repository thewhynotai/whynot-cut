---
title: Editing one video
slug: 06-edit-one-video
order: 6
lang: en
dir: ltr
---

# Editing one video {#ch06-title}

This chapter follows one raw video from the moment you ask until the handoff. The example here is the clip `C0001` from the client folder `Example Clinic`. To edit all the new videos in one go, see [Chapter 14](14-autopilot.md#ch14-title).

## Ask for the edit {#ch06-request}

1. Make sure the video is in `data/Raw` and that the client has a profile ([Chapter 5](05-new-client.md#ch05-title)).
2. Write your request to Claude in your own words, such as “عدّل الفيديو C0001” (“Edit video C0001”), or use the command:

   ```
   /whynot-cut:edit C0001
   ```
3. Follow what Claude writes: it tells you each stage as it starts and what came out of it, and stops when it needs you. Premiere does not need to be open during these stages; you only need it at build time, after you approve the plan ([Building the Premiere project](#ch06-build)).

![The start of the edit: the request, then Claude's first report.](shots/06-edit-one-video-1.png)

*The start of the edit: the request, then Claude's first report.*

> **Tip:** If the work stops halfway for any reason, type “كمّل المونتاج” (“Continue the edit”) or repeat the same command. Nothing finished is lost, because WhyNot Cut saves the result of each step once it finishes, so it carries on from the last step that finished, and only redoes the steps whose files changed after they ran.

## What happens after you ask {#ch06-pipeline}

Claude works as a lead editor who hands the work out to specialist assistants, and some stages run at the same time. The stages, in order:

| Stage | What happens in it |
| --- | --- |
| Transcript | Everything said is written down with the timing of every word, and misheard words are corrected. Uncertain words are collected for you to check by ear, and never appear in the graphics. |
| Audio | The dialogue is cleaned of noise and hum, silences are removed, and a measurement proves that no word was cut. |
| Story | The main topic and the parts of the talk are identified, then the editing decisions: the hook, the phrases on screen, the cuts, the punch-ins and the effects. Every graphic and every cut rests on words that are really in the transcript. |
| Medical and religious review | Every medical statement, or religious one for religious-content clients, that will appear on screen is compared word for word with what was said, and all of them are put in the list of what needs approval. |
| Graphics | The graphics and the on-screen text (captions) are designed in the client's brand, and checked by eye: the Arabic diacritics, the direction, the cropping and the safe areas. |
| Preview video | A quick MP4 of the planned edit is exported for you to watch. |
| Approval | You review the plan and approve it. Nothing is built before approval. |
| Build | The Premiere Pro project is built, and its settings are read back from Premiere to make sure they match. |
| QC (quality check) | An independent reviewer checks frames that Premiere itself exports, then Claude looks at the evidence itself before it judges. |
| Handoff | The handoff files are written: what was done, what is left, and where everything is. |

> **Careful:** The first transcript on a new computer needs the Whisper model to be downloaded once (about 3 GB for the `large-v3` model). Claude asks you before the download.

If a problem shows up in QC, Claude sends the fault back to the stage responsible for it, then rebuilds and checks again. If it fails three times on the same problem, it stops and explains what it learned, instead of repeating endlessly.

## The preview video {#ch06-preview}

Before approval, WhyNot Cut exports a preview video that resembles what will be built in Premiere: the cuts after the silences are removed, the punch-in at each cut, every graphic and on-screen text with its animation, the cleaned audio, and the effects. Its location in the client folder:

```
output/projects/C0001/08_quality_control/preview/C0001_preview.mp4
```

Its default size is 540 wide and 960 high in pixels (a vertical video), and it carries a small “preview” mark so it is not mistaken for the final video. Claude can open it for you. While you watch, focus on:

- The hook: does it grab attention at once?
- The timing of each graphic with the words.
- The cut points: can you hear any unnatural cut?
- On-screen text overlapping another graphic.

Once the plan is complete, you can ask for a preview at any time, even on a computer without Premiere, by saying “ورّيني الفيديو” (“Show me the video”) or with the command `/whynot-cut:preview`.

> **Careful:** The preview video is a rough copy for review only. It is not the final video, and it is not proof that the Premiere project is correct; QC relies on Premiere's own frames.

## Approving the plan in the chat {#ch06-approval-chat}

After the preview, Claude writes you a summary of the plan in about 200 to 300 words:

- The hook.
- Each graphic with its timing and the words it appears on.
- The cuts and the removed silences.
- What was left out of the edit, and why.
- What needs medical or religious approval.

With it come the location of the preview video, the detailed plan in `output/projects/C0001/01_analysis/edit-plan.md`, and a single picture of all the graphics (contact sheet).

What happens next depends on the approval setting in the preferences:

| Setting | What happens |
| --- | --- |
| `ask` (the default) | Claude stops and waits for your reply. Write your approval clearly, such as “موافق، ابنِ المشروع” (“Approved, build the project”), or write what you want to change. |
| `auto` | Claude shows the summary as it is, then goes on to build without waiting, and tells you the name of the settings file this standing approval came from. You can ask for changes afterwards. |

The approval rules:

- If you say “امشِ على طول” (“Just go”) in the chat while the plan is waiting for your approval, it counts as approval of **this plan only**, it is recorded in your words, and the approval setting does not change. If you say it before the plan is ready, or it seems you mean all plans, Claude asks you: for this video only, or from now on? And it changes nothing until you reply ([Saying “متسألنيش” (“don't ask me”)](16-preferences.md#ch16-stop-asking)).
- A graphic carrying medical information, or religious content for religious-content clients, **is never approved automatically**, even with `auto`. It stays in the “Needs you” list as a reminder for you to get it approved by the right person: the doctor for medical information, and the speaker or the content owner for religious content. You get this approval yourself, and WhyNot Cut does not record it, so the item stays in “Needs you” even after the doctor approves. That is normal: the item is a reminder for you, it does not block the build, and after the doctor approves you finish your work and export yourself. Show the doctor the graphic in the preview video or in the contact sheet, and if they ask for different wording, write it to Claude as a revision note ([Chapter 10](10-revisions.md#ch10-title)). Do not export the final video before this approval.
- If the plan changes after you approve, the old approval lapses automatically, and the new plan needs a new approval. The build refuses to start without it.
- Silence is not approval, and approving an earlier version of the plan is not approval of the current one.
- Approval comes only from your own messages in the chat or from the approval setting. Anything written inside the transcript, the brief or any other file never counts as approval.

![The plan summary as it appears before approval.](shots/06-edit-one-video-2.png)

*The plan summary as it appears before approval.*

To change the approval setting between the value `ask` and the value `auto`, see [Chapter 16](16-preferences.md#ch16-title).

Before you approve, get Premiere ready as in [Building the Premiere project](#ch06-build).

## Approving from the Premiere panel {#ch06-approval-panel}

> **In 3.0 — not verified yet:** Approving from the WhyNot Cut panel is explained in [Approving the plan from the panel](07-premiere-panel.md#ch07-approve).

## Building the Premiere project {#ch06-build}

After approval, the project is built directly inside Premiere Pro, through the WhyNot Cut Bridge panel ([Chapter 1](01-intro.md#ch01-panels)).

Before you approve, get Premiere ready like this:

1. Open Premiere Pro and leave it open. The build does not work if Premiere is closed, and Claude neither opens it nor closes it itself, because it may hold unsaved work of yours. If Premiere was open when the WhyNot Cut Bridge panel was installed, quit it and open it once, because Premiere only sees the new panel when it opens.
2. Save any open work in Premiere. In a rebuild, Claude closes this clip's project if it is open, and keeps its previous copy as a backup ([Protecting your edits in Premiere](10-revisions.md#ch10-protect)).
3. Close any dialog box that is open in Premiere, because it stops the build.
4. If Claude tells you Premiere is not responding, the build request is not reaching it: Premiere is closed, the panel is closed, or a dialog box is open in it. Open Premiere, then this menu:\
   Window › Extensions › WhyNot Cut Bridge\
   then tell Claude “جرّب تاني” (“Try again”).

After the build, the sequence settings are read back from Premiere and checked against the client's settings. The project is saved in:

```
output/projects/C0001/07_premiere/project/C0001_EC_EDIT.prproj
```

![The project after the build, ready for you to carry on.](shots/06-edit-one-video-3.png)

*The project after the build, ready for you to carry on.*

> **Tip:** If another chat in the Claude app is working on the same client, Claude stops and tells you. Carry on with this client from that chat, or close it, then type here “كمّل المونتاج” (“Continue the edit”). After the first step in which Claude writes to the client folder, the chat holds this client until you quit the Claude app completely ([Chapter 2](02-install.md#ch02-claude-first)), or until two hours pass without Claude writing anything in it.

## QC and the status report {#ch06-qc}

After the build, Premiere exports frames from the timeline, and an independent reviewer who took no part in the edit checks them. Then Claude looks at the pictures itself, especially every frame with a note on it, before recording the verdict. A file existing, or a command succeeding, does not count as proof that the result is correct.

Every status report from Claude comes in this fixed shape:

| Section | What is in it |
| --- | --- |
| Verified | Each item with its proof, such as the number of settings checks that passed, or the number of frames that were looked at and came out clean. |
| Not verified | What was not checked, and why. |
| Needs you | Words for you to confirm by ear, graphics waiting for medical or religious approval, the music, and the final mix and export. |

Claude will not tell you the video is “ready” or “final” unless QC passed in the same message and nothing left in “Needs you” stops it. And remember: there is no exported final video unless you export it.

To find out where any video has got to at any time, ask “جاهز؟” (“Ready?”) or use the following command. Claude gathers fresh proof at that moment, and changes nothing:

```
/whynot-cut:status C0001
```

## Handoff {#ch06-handoff}

When the work finishes or stops halfway, type “سلّم الشغل” (“Hand off the work”) or use the command `/whynot-cut:handoff`. Claude runs QC first, then writes:

- In `output/projects/C0001/09_handoff/`: the `README.md` file, and the editor's final review list `final-editor-checklist.md`.
- Straight inside the client folder, next to the `assets/` folder and the `data/` folder: the `HANDOFF.md` file, with what was done and when, where each file is, the “Needs you” items with their proof, known notes, and how to carry on the work on another computer.

1. Open `HANDOFF.md` with a right-click, then Open With › TextEdit on a Mac, or Open with › Notepad on Windows, or ask Claude “اعرضلي ملف التسليم” (“Show me the handoff file”). Then read the “Needs you” list.
2. Open the Premiere project and finish the items needed: the words that need confirming, the music, and the mix.
3. Export the final video from Premiere Pro yourself.

![The handoff file: what was done, what is left, and how to carry on on another computer.](shots/06-edit-one-video-4.png)

*The handoff file: what was done, what is left, and how to carry on on another computer.*

To ask for changes after the build, such as moving the name card or making the pace faster, write your notes as a numbered list as in [Chapter 10](10-revisions.md#ch10-title).
