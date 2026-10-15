---
title: The WhyNot Cut panel in Premiere
slug: 07-premiere-panel
order: 7
lang: en
dir: ltr
---

# The WhyNot Cut panel in Premiere {#ch07-title}

In version 3.0 the WhyNot Cut panel becomes the place where you follow the work and approve the plan without leaving Premiere Pro or After Effects. This chapter explains the new panel screen by screen. We start with what you use today.

> **Tip:** Today you follow the work and approve the plan in the chat with Claude, and the panel you find in Premiere is WhyNot Cut Bridge ([the first section of this chapter](#ch07-today), and [Chapter 1](01-intro.md#ch01-panels)). The rest of this chapter describes version 3.0.

## Today's panel: WhyNot Cut Bridge {#ch07-today}

Today Claude builds the project inside Premiere through the WhyNot Cut Bridge panel ([Chapter 1](01-intro.md#ch01-panels)), which you find in Window › Extensions › WhyNot Cut Bridge. Don't click anything in it; it only shows the status of the work. You follow the work and approve the plan in the chat with Claude, as in [Approving the plan in the chat](06-edit-one-video.md#ch06-approval-chat).

In the rest of this chapter, every button name, title or message written in quotes, such as “Needs you”, is in the exact words the panel shows in English. The panel says “folder” and “frames”, the same words as this guide.

## Where to find the WhyNot Cut panel {#ch07-where}

Each app has only one panel, called **WhyNot Cut**, and the installation removes the old panels, such as WhyNot Cut Bridge, and the test panels ([Chapter 2](02-install.md#ch02-title)).

- **In Premiere Pro:** Window › UXP Plugins › WhyNot Cut.
- **In After Effects:** Window › Extensions › WhyNot Cut.

Drag the panel to the side of the screen and leave it docked there. It is designed to work while narrow, with no side scroll bar. It looks like the thewhynot.ai website: always a black background, glass cards, and one purple button on each screen, which is the next step. Status shows with a colour and an icon together: green for fine, yellow for a warning, and red for an error. At the bottom is the line “Powered by thewhynot.ai”.

The After Effects panel has the same look and parts, and shows the stages of the motion video, the approval, the QC frames and the export ([Chapter 9](09-motion.md#ch09-title)).

> **In 3.0 — not verified yet:** In After Effects the menu may be called Extensions (Legacy) instead of Extensions.

![Where the WhyNot Cut panel is in Premiere Pro.](shots/07-premiere-panel-1.png)

*Where the WhyNot Cut panel is in Premiere Pro.*

## The panel header {#ch07-header}

At the top of the panel is the WhyNot Cut logo, and under it the name of the client and the clip you are working on now, or “No item selected” if no work has started yet. Next to them are three status marks:

- **“Engine”:** “connected” or “not running”.
- **“Premiere”:** “linked”, “linked (compat)” or “not connected”. Compat mode means the link with Premiere goes through an older type of Adobe panel, not through the new panel; everything works, and nothing is asked of you.
- **The Claude badge:** the status of the Claude app on your computer in a few words, with a button when you need to do something, such as a button that opens Claude so you can sign in, or an update button. The badge only checks the Claude app on your computer. The panel never asks you to sign in to Claude inside it; signing in happens in the Claude app itself. Click the badge to refresh it.

**The “Needs you” badge** with a number: the count of things nobody but you can do, such as approving a plan, listening to a word the transcript is unsure of, a missing font, or choosing the music. Click it to open the same “Needs you” list inside the panel ([Chapter 14](14-autopilot.md#ch14-needs-you)).

**The language button “ع” / “EN”:** switches the whole panel between Arabic and English. In Arabic the panel reads from right to left, while timings, numbers and file names stay left to right. The panel remembers your choice on your computer, and the first time you open it, it starts in the language set in the `language` setting ([Chapter 16](16-preferences.md#ch16-title)).

> **In 3.0 — not verified yet:** The words for the Claude badge's states may differ slightly in the final panel.

![The panel header: the status, the Claude badge, “Needs you”, and the language button.](shots/07-premiere-panel-2.png)

*The panel header: the status, the Claude badge, “Needs you”, and the language button.*

## The home screen {#ch07-home}

The panel has three sections you move between at the top: “Home”, “Edit” and “Tools”.

The “Home” screen has three big buttons, the same three steps as WhyNot Cut's slogan “Drop the files · Say what you want · Approve the plan”: a button to add the raw videos, a button that asks Claude to start the edit, and a button that opens the plan waiting for your approval. The edit-request button does not run Claude out of sight: the request reaches the open Claude chat, so you follow it in front of you. If no chat is open, the panel shows a button that opens Claude so you can follow the request there.

Under the buttons are the cards for the three tools; each card has a line saying what the tool does, and the result of the last time you used it:

- **WhyNot Tidy:** organising the project ([Chapter 11](11-tidy.md#ch11-title)).
- **WhyNot Hush:** removing silences ([Chapter 12](12-hush.md#ch12-title)).
- **WhyNot Kalam:** captions ([Chapter 13](13-kalam.md#ch13-title)).

If the panel has nothing to show yet, it does not stay empty; it tells you the next step with one button. For example, before any client is chosen it shows “No client folder yet” and the button “Choose client folder”.

> **In 3.0 — not verified yet:** The names of the three buttons may differ slightly, and it is not decided yet whether the edit-request button opens Claude with the request already typed in it, or shows you the request to copy.

![The home screen: the three steps and the tool cards.](shots/07-premiere-panel-3.png)

*The home screen: the three steps and the tool cards.*

## Following progress in the panel {#ch07-progress}

On the “Edit” screen the “Pipeline” section appears, with a bar showing the stages in order: “Transcript”, then “Plan”, then “Approve”, then “Build”, then “Frames”, then “QC”, then “Handoff”. Under each stage is its status: “done”, “running”, “waiting for you”, “not yet” or “failed”. In Arabic the bar starts from the right.

The stage that is running now has a progress bar, and with it:

- A simple sentence saying what is happening, such as “Building your sequence…”, and a counter such as “23 of 47”.
- “elapsed”: the time that has passed since the stage started.
- A “Cancel” button to stop the stage.

When nothing is running, the panel says “Nothing is running.” The panel does not guess: it shows what Claude and the engine wrote in the clip's files, so what you see in it is the same as what Claude tells you in the chat.

> **In 3.0 — not verified yet:** This screen has not been tried yet on a real clip.

![Following progress: the stages, the current stage, and the cancel button.](shots/07-premiere-panel-4.png)

*Following progress: the stages, the current stage, and the cancel button.*

## Approving the plan from the panel {#ch07-approve}

When the plan is ready, a card appears in the “Approval” section with:

- **“Plan summary”:** the same summary Claude writes you in the chat.
- **“Watch preview”:** opens the preview video in the Source Monitor inside Premiere.
- **“Needs a second look”:** the graphics carrying medical information or religious content, each item marked “Medical” or “Religious”.
- **“Your name”:** recorded with the approval.
- The two buttons “Approve” and “Request changes”.

1. Read the summary, and click “Watch preview”.
2. If the “Your name” field appears, type your name in it.
3. Click “Approve”. The panel says “Approved. The build can start.”
4. Or, if you want changes, write what you want in “What should change?” then click “Request changes”. The panel says “Your changes were sent.”
5. Don't write anything in the chat: if the Claude chat is open, Claude sees your approval or your changes and carries on by itself. If it is not open, Claude finds them when you open a new chat, and tells you that you approved from Premiere, and when.

The rules for approving from the panel:

- Approving in the chat still works as before ([Chapter 6](06-edit-one-video.md#ch06-approval-chat)). Use whichever way is easier for you.
- The approval is for exactly this plan. If the plan changed after you opened it, the panel says “The plan changed. Review it and approve again.”
- The “Approve” button is for you alone. Claude cannot click it on your behalf.
- Approving the plan is not the doctor's or the content owner's approval. The medical and religious items stay in “Needs you” until you get their approval yourself ([the approval rules](06-edit-one-video.md#ch06-approval-chat)).

> **In 3.0 — not verified yet:** If Claude does not carry on after you approve from the panel, approving in the chat always works ([Chapter 6](06-edit-one-video.md#ch06-approval-chat)).

![Approving the plan from the panel.](shots/07-premiere-panel-5.png)

*Approving the plan from the panel.*

## QC frames and project buttons {#ch07-qc-frames}

After the build, Premiere itself exports frames from the sequence for QC, and they appear in the “Frames and QC” section as a grid of small pictures. Before the build the section says “No frames yet. They appear after the build.”

- Each frame shows its status: “Pass”, “Fail” or “Pending”.
- “Media pending”: Premiere exported the frame before it finished loading the video. Click “Re-export”.
- Click any frame to jump to the same moment in the timeline and see it yourself, as the panel reminds you: “Tap a frame to move the playhead there.”

Claude writes the QC result after looking at the frames itself; the panel only shows it.

The “Actions” section holds the project buttons:

- “Open project”, and “Reveal folder” (the clip's folder).
- “Export frames”, and “Render review MP4”.
- “Copy diagnostics” (see the next part).
- “Rebuild”: it first asks you “Rebuild this project?”, says that a rebuild replaces any edits you made by hand in Premiere since the last build, and shows the name of the backup copy it saves from your project before it starts. Click “Rebuild” to go ahead, or “Keep my project” to back out ([Protecting your edits in Premiere](10-revisions.md#ch10-protect)).

> **In 3.0 — not verified yet:** The frame grid and the project buttons have not been tried yet on a real clip.

![QC frames, and the project buttons.](shots/07-premiere-panel-6.png)

*QC frames, and the project buttons.*

## When a problem shows in the panel {#ch07-errors}

Every problem in the panel appears as one sentence saying what happened, and one button that fixes it. The panel shows no commands or technical messages, and never asks you to type anything. For example:

- “The WhyNot Cut engine is not running.” with the button “Start engine”. The reason is that the engine has not started yet or has stopped, and the panel also tries again by itself: “The panel tries again by itself.”
- “That did not work.” with the button “Try again”. Its reason is written in the “Log” (the next paragraph); if it keeps happening, click “Copy diagnostics” and send it to us.

Technical details don't show on the screen; they are in the “Log”: a folded drawer at the bottom of the panel that you open when you need it. When you see “The details are in the log.”, that is where they are. At the bottom of the log are the name WhyNot Cut and its version number, with the “Copy diagnostics” button next to it.

If you need support, click “Copy diagnostics”, and the panel says “Copied.” Then paste what was copied into your message to us ([Contact and support](19-glossary.md#ch19-contact)). The panel's common messages and their fixes are in [Chapter 17](17-troubleshooting.md#ch17-v3).

> **In 3.0 — not verified yet:** Some messages, such as the one about restarting Premiere after an update, will be added to this part when the panel is released.

![A problem in one sentence and one button, with the details in the “Log”.](shots/07-premiere-panel-7.png)

*A problem in one sentence and one button, with the details in the “Log”.*

## The setup checklist on first run {#ch07-checklist}

If you open the panel before your computer's setup is complete, it shows the “Setup checklist”, the same checklist you see at the end of the installation ([Checking the result](02-install.md#ch02-check)). It has four items:

| Item | What it means |
| --- | --- |
| “Engine” | The program that does the work in the background is running. |
| “Premiere link” | The panel is connected to Premiere. |
| “Claude” | The Claude app is installed, you are signed in to it, and the WhyNot Cut plugin in it is up to date. |
| “Clients folder” | The clients folder is set. |

A green item is ready. A yellow or red item has its reason next to it and one button that fixes it, such as “Start engine”. The button on the “Clients folder” item is the first-client setup button: it opens Claude on the start wizard, which asks you only about the client and your preferences, and skips everything that is already ready ([Chapter 5](05-new-client.md#ch05-title)).

> **In 3.0 — not verified yet:** It is not decided yet whether the first-client setup button opens Claude straight on the start wizard, or shows you the request to copy.

![The setup checklist the first time the panel runs.](shots/07-premiere-panel-8.png)

*The setup checklist the first time the panel runs.*

## The AI buttons {#ch07-ai}

The panel has a fixed set of buttons that ask Claude for text with one click:

- Correcting the on-screen text (captions).
- Suggesting titles.
- Summarising.

Each of these buttons only writes a suggestion, and shows it to you to review. Nothing in your project changes until you click the Apply button yourself. These buttons only write text: they don't open files, run tools or build anything. Long work, such as editing a whole video, stays in the Claude chat in front of you.

The request is carried out by the first route available, in this order: the open Claude chat on your computer; then an Anthropic API key if you saved one, which is a secret code from an Anthropic developer account (you don't need it: the buttons work as long as a Claude chat is open); then the button opens Claude with the request typed in it for you to send. If none of these is available, the button says what is missing. WhyNot Kalam's AI correction works by the same rules ([Chapter 13](13-kalam.md#ch13-title)).

![A suggestion from an AI button, waiting for you to review and apply it.](shots/07-premiere-panel-9.png)

*A suggestion from an AI button, waiting for you to review and apply it.*

> **In 3.0 — not verified yet:** It is not decided yet whether these buttons will work from the Claude account on your computer without an open chat; if that is added, it will stay off until you turn it on yourself.
