---
title: Autopilot and the “Needs you” list
slug: 14-autopilot
order: 14
lang: en
dir: ltr
---

# Autopilot and the “Needs you” list {#ch14-title}

Instead of asking for each video to be edited by name, ask for all the new videos to be edited at once. This is autopilot. All the rules for editing one video in [Chapter 6](06-edit-one-video.md#ch06-title) apply here as they are; the only difference is how the videos are picked and how you approve.

## Ask for everything new to be edited {#ch14-request}

1. Put the raw videos in `data/Raw` for one or more clients.
2. Write to Claude “عدّل الفيديوهات الجديدة” (“Edit the new videos”), or use the command; you can write the client's name or folder after it:

   ```
   /whynot-cut:autopilot
   ```
3. Review the work table Claude shows, and agree to start if it asks you.
4. Review the single approval message for all the plans, then approve or ask for changes.
5. Read the final report, then complete what's in the “Needs you” list.

![The work table before starting.](shots/14-autopilot-1.png)

*The work table before starting.*

## How Claude finds the new videos {#ch14-find}

- If the chat is open inside a client folder, meaning you chose that client folder itself when starting the chat in the Claude app, or you named the client, it looks in that client only. Otherwise it looks in every client folder inside the clients folder you chose in the first setup: every folder that has an `assets/` folder and a `data/` folder.
- It shows a short table: the client, the new videos, the videos in progress, and the missing files.
- A video that stopped halfway carries on from the last step that was completed. A finished video isn't touched unless you ask.
- If it finds nothing new, it tells you so and shows what's in progress, then stops.
- Old project folders that don't match any video are shown to you and it asks you about them; it never deletes them.
- A client with no client profile goes through new-client setup first ([Chapter 5](05-new-client.md#ch05-title)).
- If the transcription model isn't on the computer, it asks you before downloading it, then transcribes one video first so the model is downloaded only once.

Claude asks you once before starting if the work covers more than one client, or more than about 3 new videos, or if this is the first time on this computer. Asking “عدّل الفيديوهات الجديدة” (“Edit the new videos”) for one client by name starts without an extra question.

> **Tip:** If another chat in the Claude app is working on the same client, Claude stops and tells you. Continue the work on this client from that chat, or close it, then write “كمّل المونتاج” (“Continue the edit”) here. After the first step in which Claude writes in the client folder, the chat holds that client until it is closed, or until two hours pass without it writing anything there.

## One approval for all the videos {#ch14-one-approval}

Once the previews are ready for all the videos, Claude writes a single approval message, with this for each video:

- The hook.
- Every graphic with its timing.
- The parts that were cut.
- What needs medical or religious sign-off.
- Where the preview video is.

What happens next follows each client's approval setting:

| Setting | What happens |
| --- | --- |
| `ask` | Claude stops and waits for your reply. You can approve some videos and ask for changes to others; only what you approved is built. |
| `auto` | Claude shows the message and names the settings file the approval came from, then continues. A graphic that needs medical or religious sign-off is built, but it stays in the “Needs you” list. |

A client folder can have its own setting that differs from the computer's setting, and one client's setting is never applied to another client. The Premiere projects are built one after another, then each project gets its own quality check (QC).

## Podcast episodes in autopilot {#ch14-episodes}

If Claude finds a new episode in `data/Episodes`, it prepares the reels plan for it and shows the table of suggested reels in the same message as the videos. No reel starts until you pick the reels yourself ([Chapter 8](08-podcast.md#ch08-title)). The `auto` approval setting never picks reels for you.

## The final autopilot report {#ch14-report}

If the `notify_done` setting is on ([Chapter 16](16-preferences.md#ch16-title)), the report starts with a clear line saying the work is Finished. Then a row for each video with its sections: Verified, Not verified, and Needs you. Then the combined “Needs you” list for all the videos. Claude doesn't describe any video as finished unless its quality check passed in that same message.

## The “Needs you” list in the `NEEDS-YOU.md` file {#ch14-needs-you}

Today the “Needs you” list comes in the final report inside the chat.

In version 3.0, autopilot writes one file for each client, `output/NEEDS-YOU.md`, with: the words for you to confirm by ear, the medical and religious sign-offs, music, missing fonts and logos, and the final mix and export. The Premiere panel shows the same list ([Chapter 7](07-premiere-panel.md#ch07-title)).

> **In 3.0 — not verified yet:** The `NEEDS-YOU.md` file isn't in the version you have today; the list reaches you in the final report.

In version 3.0, the WhyNot Cut panel inside Premiere has a “Needs you” badge showing the number of items waiting for you. Click it to open the same list inside the panel, without looking for the file ([The panel header](07-premiere-panel.md#ch07-header)).

> **In 3.0 — not verified yet:** The badge is part of the new WhyNot Cut panel, and isn't in the version you have today.
