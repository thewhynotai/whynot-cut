---
title: "Tidying the project: WhyNot Tidy"
slug: 11-tidy
order: 11
lang: en
dir: ltr
---

# Tidying the project: WhyNot Tidy {#ch11-title}

WhyNot Tidy (“Tidy”) comes with version 3.0 of WhyNot Cut. It cleans and organises a Premiere Pro project in one go, and in podcast mode it builds a single sequence in which all the cameras and microphones are synced by sound. It is one of three editor tools inside the WhyNot Cut panel, alongside Hush ([Chapter 12](12-hush.md#ch12-title)) and Kalam ([Chapter 13](13-kalam.md#ch13-title)).

> **Tip:** Today Tidy isn't in the version you have, so organise your project in Premiere by hand as usual. The rest of this chapter describes version 3.0.

> **In 3.0 — not verified yet:** The button names and pictures in this chapter may change slightly when the tool is released.

## What Tidy does and doesn't do {#ch11-what}

Tidy reads the whole project and shows you what it will do before it changes anything:

- **It removes from the project whatever no sequence uses:** old renders, unused duplicates of a file that is in use, and Hush's backup and cut sequences. It removes them from the project only; no file is deleted from the disk.
- **It sorts everything into fixed, numbered bins** by each file's real type. Camera footage is recognised from the file's own data, not its name, so it stays camera footage even if you renamed it.
- **It names the nests**, meaning sequences placed inside another sequence, after what they contain, instead of names like Nested Sequence 07.
- **It gives each type a fixed colour**, and deletes old bins once they are empty.
- **In podcast mode:** it puts each camera in its own bin and the microphones in one bin, and builds a sequence synced by sound for all the cameras and microphones.

It never deletes a file from the disk: files are only read. It doesn't delete an item that is in use, or any sequence other than Hush's backup and cut sequences, and it doesn't edit your existing sequences. It doesn't relink offline files, and it doesn't convert video formats. And it doesn't touch `assets/` or `data/` in the client folder: all it changes is your own Premiere project.

> **In 3.0 — not verified yet:** These limits come from the tool's spec and haven't been tried on a real project yet.

## When to use Tidy {#ch11-when}

- **Before handing over or archiving a project:** when the project has filled up with old renders, duplicates, and bins that other tools created automatically.
- **Before editing a podcast episode:** to separate the cameras and microphones and get a synced sequence ready for cutting.
- **After Hush:** to get rid of backup sequences you no longer need.

> **In 3.0 — not verified yet:** These are examples of using the tool, and they will be reviewed when it is tried.

## Tidy the project from the Tidy tab {#ch11-panel}

The steps are the same in all the editor tools: scan, then preview, then apply, then undo if you need to.

1. Open your project in Premiere Pro, then open the WhyNot Cut panel, choose the “Tools” section, then “Tidy”.
2. Choose the project type: “Reels” or “Podcast”.
3. Click “Scan”. The tool reads the project without changing anything in it, then shows a summary: the number of items, the size of all the media, what will be removed (how many and how large), the share of the project's size that is unused, and the count of each type.
4. Review the sections under the summary, and untick any item you don't want (see the next table).
5. Choose what you want from the three options: “Remove ticked items”, “Organise into bins” (with nest names), and “Colour by type”.
6. Click “Clean & organise”. A confirmation box appears with “What will change” and “Backup copy”. Approve to continue.
7. The tool saves the project, then saves a backup copy of it, then applies the changes, then scans the project again and shows a report of what was done, with an “Open the pre-clean copy” button.

| Section in the preview | What's in it |
| --- | --- |
| What will be removed | Grouped by reason, with sizes: media that no sequence that stays in the project uses, neither directly nor from inside a nest; unused duplicates of a file that is in use; and Hush sequences: the backup copies (WhyNot Hush backup …) and the cut copies that remain after an undo (WhyNot Hush cut …). Use of an item inside a Hush backup copy doesn't count as use. |
| Optional items (unticked) | Caption files, because Premiere doesn't say which caption track uses them. And in podcast mode: camera footage, microphones, and any recording 180 seconds long or more, because they are the raw material for the sync. They are only removed if you tick them yourself. |
| What will be moved | Grouped by the bin it will move to. |
| Nest names | The new name for each nest, with a tick you can remove. |
| Old bins | Bins that are deleted once they're empty, such as Assets, Recovered Clips, Kalam Captions, and bins that other tools created automatically or duplicates with the same name. |
| Duplicates in use | One file with two items in the project, both in use. For your information only; neither is removed. |
| Offline files | For your information only. The tool checks for itself that the file exists on the disk. |

> **Careful:** If you still need a Hush sequence, whether a backup copy to undo a cut or a cut copy you kept after an undo, untick it before you click “Clean & organise”.

### The fixed bins {#ch11-bins}

After tidying, the project has this fixed layout, and only the bins that received something remain. Each type has a fixed colour, and all images share one colour:

| Bin | What goes in it |
| --- | --- |
| `01 Footage` | Only what came out of a camera, even after it was renamed, and RAW files. In a podcast: `01 Footage/Cam 1` and onwards. The camera with the most footage gets number 1. |
| `02 Renders & Stock` | Renders and exports, such as output from After Effects, Media Encoder, HandBrake, CapCut or DaVinci, and ready-made videos. |
| `03 Audio`, containing `Voice`, `Music`, `SFX`, `Mics` | Audio by type. Sound effects are recognised by their name or by being short (8 seconds or less). In a podcast, recorder files (wav, bwf, aif) that are 180 seconds long or more go to `Mics`. |
| `04 Images`, containing `PNG`, `JPG`, `Icons`, `Other` | Images by format. An icon is an svg, ico or icns file, or an image with icon, logo or emoji in its name, or an image whose longest side is 512 pixels or less. |
| `05 Graphics` | Graphics. |
| `06 Sequences` | Sequences. |
| `07 Nests` | Sequences used inside another sequence. |
| `08 Captions` | Caption files. |
| `09 Other` | Everything else. |

A nest's new name is taken from the text written in it; if there isn't any, from its first image, then its first clip, then the name of the inner sequence. The name is at most 50 characters, and a repeated name gets a number added: 2, then 3.

> **In 3.0 — not verified yet:** The button and section names here are taken from the tool's spec, and may differ slightly in the panel.

![The Tidy preview, before any change.](shots/11-tidy-1.png)

*The Tidy preview, before any change.*

## Syncing the podcast by sound {#ch11-sync}

In “Podcast” mode a “Sync the podcast by sound” button appears. It takes every camera clip and every microphone recording (one copy of each file), matches them by sound, then builds a new sequence in which all the cameras and microphones sit in the right place.

1. Choose “Podcast” and click “Scan”. In the preview, each camera appears in its own bin, and the microphones in `03 Audio/Mics`. Similar cameras stay separate if their files are in different folders on the disk.
2. Click “Sync the podcast by sound”. Premiere exports each clip's audio to a temporary file, and the progress shows clip by clip. The temporary sequences it uses for this are deleted afterwards, and the sequence you were working on comes back.
3. Each clip is matched by sound against the longest recording, then fine-tuned, with the aim of being within one frame.
4. The new sequence appears in `06 Sequences` with the project name followed by - Synced, such as `EP01_EC_PODCAST - Synced`. If you run the sync a second time, the new sequence gets a number: - Synced 2.
5. Read the report: the clips that were left out of the sync, and why.

What the synced sequence looks like:

- The first clip starts at zero, and every clip sits in its place relative to it.
- The first camera is on the first video track, the second on the second, and so on. If a clip would cover another clip from the same camera, it gets a new track, so a camera angle is never wiped out.
- The cameras' audio goes where Premiere puts it, and the microphones go on the audio tracks after the last track the cameras' audio uses.
- The sequence settings come from the longest clip in Cam 1.
- After the build, every clip is read back from Premiere to confirm its place (within a frame), and any difference is noted in the report.

A clip whose sound isn't enough for a confident match, such as a clip from another recording, isn't put in the wrong place: it's left out of the sequence and its name is listed. The same goes for a clip whose audio export failed.

> **In 3.0 — not verified yet:** The sync hasn't been tried on a real podcast project yet.

![The result of syncing the podcast by sound.](shots/11-tidy-2.png)

*The result of syncing the podcast by sound.*

## Tidy from the chat {#ch11-chat}

You don't need to open the tab. Write to Claude “رتّب البروجكت” (“Tidy the project”) to organise the project, or “سنك البودكاست” (“Sync the podcast”) to build the synced sequence. Claude runs the same tool as the panel, and shows you what will change before it applies anything.

![Tidy from the chat: the same preview and the same report.](shots/11-tidy-3.png)

*Tidy from the chat: the same preview and the same report.*

After every run, from the panel or from the chat, one report is written: what changed, the name of the backup copy, and how to undo. Claude reads it and passes it back to you under “Verified”, “Not verified” and “Needs you”. So the result from the chat is the same as from the panel.

Claude only changes your own project in Premiere, and it only starts the change after the backup copy is recorded.

> **In 3.0 — not verified yet:** Tidy requests from the chat don't work in the version you have today.

## Backup and undo in Tidy {#ch11-undo}

Before any change, Tidy saves the project, then copies the project file next to it with a name that includes the date and time:

```
C0001_EC_EDIT (WhyNot Tidy backup 2026-10-13 101500).prproj
```

To undo, click “Open the pre-clean copy” in the report, or ask Claude to undo. Undo opens this copy, so you're back to the project exactly as it was before the clean. Note: what opens is the backup file itself, and the original file stays cleaned. To keep the old version for good, save it with File › Save As under your project's name, or work on it directly. The sync doesn't need an undo: it only adds a new sequence and doesn't change anything that exists.

> **In 3.0 — not verified yet:** Undo hasn't been tried on a real project yet.

## Safety rules in Tidy {#ch11-safety}

These rules are fixed in the tool, and no setting changes them:

- Removal is from the project only. Media files are read and never changed.
- No item in use is removed, and no sequence other than Hush's backup and cut sequences. The preview checks this, then the tool checks again inside Premiere at the time it applies, and refuses to remove an item in use even if asked to.
- No bin that contains anything is deleted. Bins are identified by their internal number, not their name, because real projects can contain two bins with the same name.
- Saving and a backup copy always come before applying, and undo opens the backup copy.
- The sync only builds a new sequence, and the temporary sequences are deleted at the end even if a step fails.
- Each step in applying is independent: if one fails, it's recorded in the report and the rest continue.

> **In 3.0 — not verified yet:** These rules come from the tool's spec, and our team checks them in a safety review before release.

## Tidy with the client folder and podcast mode {#ch11-client}

Tidy uses the same fixed bins for every project and every client, so you know where everything is in any project you open. It doesn't take any settings from the client profile.

The synced sequence it builds can become the episode's source in podcast mode ([Chapter 8](08-podcast.md#ch08-title)), if you want. This is optional, and podcast mode works as it is if you don't use it.

> **In 3.0 — not verified yet:** Exactly how to ask for this will be explained here when the tool is released.

## Tidy's limits on macOS and Windows {#ch11-limits}

Tidy works on macOS and Windows with the same steps, with the Premiere Pro version the WhyNot Cut panel runs on ([Chapter 1](01-intro.md#ch01-requirements)). It doesn't need an AI model or any extra install: it's installed with the panel when you install WhyNot Cut, and the computer check checks it along with the rest of the program.

Tidy handles these cases by itself:

- Recordings at 44.1 kHz are converted to 48 kHz before matching, so the sound doesn't drift away from the picture over time.
- A second sync gets a numbered name (- Synced 2) instead of a duplicate name.
- Temporary sync sequences that may be left behind after a sudden crash are deleted at the start of the next run.
- A very short clip that is left out of the sync is shown with the reason.

And these are its limits:

- Premiere doesn't let add-on tools create a multi-camera (multicam) source sequence. So the result is a normal sequence, with each camera on its own track.
- In very long recordings the camera may not be recognised from the file's data, so the file's type is recognised from its name.
- Premiere doesn't say which caption track uses a caption file, so caption files stay unticked until you decide.

> **In 3.0 — not verified yet:** Tidy hasn't been tried on Windows yet.
