---
title: "Removing silences: WhyNot Hush"
slug: 12-hush
order: 12
lang: en
dir: ltr
---

# Removing silences: WhyNot Hush {#ch12-title}

WhyNot Hush (“Hush”) comes with version 3.0 of WhyNot Cut. It removes silences and hesitation words, such as “اممم” and “آه” or um, from a Premiere Pro timeline: it scans the part you choose, draws every cut for you on the audio waveform, then cuts when you ask it to. Before any cut it saves a backup copy of the sequence, and the undo button brings it back.

> **Tip:** Today Hush isn't in the version you have. Silences in raw footage are removed today in the audio stage of the full edit ([Chapter 6](06-edit-one-video.md#ch06-pipeline)), or with the audio command alone ([Chapter 10](10-revisions.md#ch10-title)). The rest of this chapter describes version 3.0.

> **In 3.0 — not verified yet:** The button names and pictures in this chapter may change slightly when the tool is released.

## What Hush does and doesn't do {#ch12-what}

- **It removes silences to the frame**, and never cuts into speech, not even part of a frame.
- **It removes hesitation words** in (Egyptian) Arabic and in English, even drawn-out ones such as “اممممم” or ummmm.
- **It keeps the edit workable:** it closes the gaps after cutting, the video stays linked to its audio, and tracks you didn't choose don't move.
- **Or it only adds markers** where each cut would be, without cutting anything, so you decide.
- **It can be fully undone:** a backup copy of the sequence, and a button that brings it back.

It doesn't clean noise or set loudness, it doesn't do multi-camera editing, and it doesn't write captions (that's Kalam's job). All the analysis happens on your computer. It doesn't touch the media files on the disk, or `assets/` or `data/` in the client folder: all it changes is the sequence open in your project.

> **In 3.0 — not verified yet:** These limits come from the tool's spec and haven't been tried on a real sequence yet.

## When to use Hush {#ch12-when}

- **A single-camera, single-mic reel:** it cuts every silence with no padding. Cutting by hand usually takes 20 to 40 minutes per minute of speech.
- **A podcast before the fine edit:** it removes the long silences first.
- **When you want to decide yourself:** choose “Markers” instead of cutting.
- **Before captions:** the sequence after cutting is the best input for Kalam ([Chapter 13](13-kalam.md#ch13-title)).

Hush is for the timeline you are working on yourself in Premiere. In the full edit that WhyNot Cut does for raw footage, silences are already removed in the audio stage, before the build ([Chapter 6](06-edit-one-video.md#ch06-pipeline)).

> **In 3.0 — not verified yet:** These are examples of using the tool, and they will be reviewed when it is tried.

## Remove silences from the Hush tab {#ch12-panel}

The same steps as all the editor tools: scan, then preview, then apply, then undo if you need to.

1. Open the sequence in Premiere Pro, then open the WhyNot Cut panel, choose the “Tools” section, then “Hush”.
2. Set what you want analysed: if you selected clips in the timeline, the part they cover is analysed. If you selected nothing and set In/Out points, what's between them is analysed. Otherwise the whole sequence is analysed. The panel writes the target, such as “3 clips”, “In/Out” or “Whole sequence”.
3. Check the track buttons (V1, A1, …). Tracks that have clips and aren't locked are selected from the start. Only the selected tracks are cut and move, and the panel warns you about any track with clips that won't move. Only the audio of the selected audio tracks is analysed; the others are muted during the analysis, then go back to how they were.
4. If you also want hesitation words removed, turn on “Fillers”, and choose the language: “auto”, “en” (English) or “ar” (Arabic).
5. Click “Scan”. A progress bar appears with what is happening, such as “Exporting audio…” then “Finding fillers…”, and a “Stop” button.
6. Set the strength, and review the fillers and the cuts on the audio waveform (the next sections).
7. Choose “Cut” or “Markers”, then click “Go”, and approve in the confirmation box.

> **Tip:** If one of the selected tracks in the sequence is locked, the cut stops with a clear message, and nothing is cut. Unlock it or deselect the track, then try again.

### Strength: “Simple” and “Advanced” {#ch12-strength}

In “Simple” there is one strength slider from 0 to 100, with three presets: “Soft” at 25, “Medium” at 50, and “Strong” at 80. The higher the strength, the shorter the silences that get cut. The actual numbers are worked out for each clip from its own sound, from its noise level and speech level, so you don't need different settings for each microphone.

“Tight” is on from the start: the cut reaches right to the start and end of the speech, with no padding. Turn it off if you want a little padding before and after the speech.

In “Advanced” you type the numbers yourself: “Threshold” in decibels (the sound level below which counts as silence), “Min silence” in seconds, and “Pad” before/after in seconds; you can link the two pads so they change together. You can save your settings under a name in “Presets” and come back to them later, and the tool remembers the last settings you used.

In every case:

- A click shorter than 30 milliseconds inside a silence doesn't break the silence.
- A silence touching the start or end of the part gets no padding on that side.
- A cut shorter than 80 milliseconds isn't made.
- The edges of every cut are rounded inwards to a whole frame, and a cut shorter than two frames isn't made.

### Hesitation words {#ch12-fillers}

To find hesitation words, the transcription model writes out all the speech with the timing of each word, and it is asked to write the hesitation words too. The panel has two lists you can edit (here Strong and Soft are the names of the two filler lists, not cutting strengths):

- **“Strong”, selected from the start:** such as “اممم”, “آه” and “اوه”, and in English: um, uh, erm, hmm.
- **“Soft”, shown unticked:** such as “يعني” (“I mean”), “طيب” (“okay”), “أصلًا” (“actually”) and “بقى” (“so”), and in English: like, you know, basically, I mean. These are words that may be part of the meaning, so the decision is yours.

Two-word phrases are recognised too, and drawn-out hesitations are always recognised. Matching isn't affected by upper and lower case, punctuation, Arabic vowel marks, or the different forms of the letters alif and ya.

Each filler appears on a line with a tick and a play button. The play button moves the playhead to half a second before it so you can hear it. When a filler is cut, the small gap touching it is cut too, so no tiny slivers are left behind.

Optional: “Unclear sounds”: loud sounds 0.15 to 1.2 seconds long with no word written next to them. They appear in the list unticked, so listen and decide.

### The preview on the audio waveform {#ch12-preview}

All the cuts are drawn on the “Audio waveform”, in one colour for silences and another for fillers. Hover over any cut to see its time and kind, and click the waveform to move the playhead to that moment. Under the waveform is a summary: the length before and after and the time saved, the number of silences and the number of fillers, and the numbers used (threshold, min silence, and padding).

> **In 3.0 — not verified yet:** The button and list names here are taken from the tool's spec, and may differ slightly in the panel.

![The Hush preview: every cut drawn before it happens.](shots/12-hush-1.png)

*The Hush preview: every cut drawn before it happens.*

## Cut or markers {#ch12-apply}

- **“Cut”:** every selected track is cut at the edges of every cut, the parts inside the cuts are removed, then all the gaps are closed in one go, so each clip moves left by the total cut before it. Then each piece of video is relinked to the piece of audio under it.
- **“Markers”:** a marker in the sequence at each cut, named after the kind of cut, with no edit. To remove them all later, choose “Remove all Hush markers” from the tool's menu.

> **In 3.0 — not verified yet:** Neither cutting nor markers has been tried on a real sequence yet.

## Hush from the chat {#ch12-chat}

Write to Claude “شيل السكتات والآآ” (“Remove the silences and the ums”) with your sequence open in Premiere. Claude runs the same tool as the panel on the open sequence, and shows you what will be cut before it cuts. But if you say the same thing about a client clip that is still in the editing stages before the build, Claude runs audio cleanup and silence removal for that clip (`/whynot-cut:fix-audio`, [Chapter 10](10-revisions.md#ch10-title)).

Today this phrase cleans the audio of a raw clip in the client folder and removes its silences ([Chapter 6](06-edit-one-video.md#ch06-pipeline)); it doesn't work on your open sequence.

After every run, from the panel or from the chat, one report is written: what changed, the name of the backup copy, and how to undo. Claude reads it and passes it back to you under “Verified”, “Not verified” and “Needs you”. Claude only changes your own project in Premiere, and it only starts cutting after the backup copy is recorded.

> **In 3.0 — not verified yet:** Asking for Hush on an open sequence from the chat doesn't work in the version you have today.

![Hush from the chat: the same preview and the same report.](shots/12-hush-2.png)

*Hush from the chat: the same preview and the same report.*

## Backup and undo in Hush {#ch12-undo}

“Backup copy” is on from the start. Before cutting, the tool copies the sequence under its name followed by the time, then goes back to the original sequence to cut in it:

```
C0001_EC_EDIT (WhyNot Hush backup 10:15:00)
```

If the tool can't make the original sequence the open one, it stops and cuts nothing. If you turn the backup off, the confirmation box tells you: “No backup copy is made. This cannot be undone.”

To undo, click “Undo” in Hush, or ask Claude to undo. After the undo, the open sequence is your sequence as it was before the cut, with its original name, and the cut copy is kept next to it in the project in case you need it, named:

```
C0001_EC_EDIT (WhyNot Hush cut 10:15:00)
```

> **Tip:** Once you're done and sure of the cut, Tidy can remove the backup sequences and cut copies from the project ([Chapter 11](11-tidy.md#ch11-title)).

> **In 3.0 — not verified yet:** Undo hasn't been tried yet, and the copies' names may differ slightly when the tool is released.

## Safety rules in Hush {#ch12-safety}

These rules are fixed in the tool, and no setting changes them:

- No cut ever goes into speech: the edges of every cut are rounded inwards to a whole frame.
- The backup copy comes before cutting (on from the start), and the tool confirms that the original sequence is the open one before any edit.
- After every cut the tool reads the tracks from Premiere again, and doesn't rely on an old reading, because Premiere changes them after every cut.
- Gaps are closed once for the whole sequence, not after each cut, because closing them after each cut was slow and pushed clips out of place.
- Tracks you didn't choose and media files on the disk are never touched. A locked track stops the whole cut.

> **In 3.0 — not verified yet:** These rules come from the tool's spec, and our team checks them in a safety review before release.

## Hush with the client folder and Kalam {#ch12-client}

If the sequence belongs to a client in your clients folder, Hush starts from the silence style in the client profile, and you can change it in the panel. Outside a client folder it starts from its own default settings.

The same part's audio isn't exported or transcribed twice: if Kalam has already transcribed this part, Hush uses the same word timings to find the fillers.

> **In 3.0 — not verified yet:** Hush starting from the client's style hasn't been tried yet.

## Hush's limits on macOS and Windows {#ch12-limits}

Hush works on macOS and Windows with the same steps, with the Premiere Pro version the WhyNot Cut panel runs on ([Chapter 1](01-intro.md#ch01-requirements)), and it's installed with the panel when you install WhyNot Cut. Removing silences doesn't need any model. Fillers need the transcription model, which is already there: the Kalam pack's models or the main transcription model, so nothing extra is downloaded ([Models](02-install.md#ch02-models)). On a Mac with Apple Silicon, transcription runs on its graphics processor; on a Mac with an Intel processor it runs on the processor (CPU). On Windows it runs on an NVIDIA card if there is one, otherwise on the processor (CPU), which is slower.

- Finding fillers depends on the transcription model writing them down. If it misses one, the fallback is “Unclear sounds”.
- By design, tracks you didn't choose don't move; the panel warns you about them before cutting. Check them after cutting.

> **In 3.0 — not verified yet:** Hush hasn't been tried on Windows yet.
