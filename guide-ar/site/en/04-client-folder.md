---
title: The client folder
slug: 04-client-folder
order: 4
lang: en
dir: ltr
---

# The client folder {#ch04-title}

Each client has one folder on your computer, which this guide calls “the client folder”. It holds everything about the client: their visual identity, their raw videos, the example edits they like, and then the results WhyNot Cut writes. WhyNot Cut works on everything from inside this folder, and you don't need to rename any file you put in it.

Inside the client folder there are three main folders:

- `assets/`: the client's brand (logo, fonts, photos, brief and colours).
- `data/`: the material to work on (raw videos, episodes, references, music, sound effects).
- `output/`: the editing results. It is created automatically, and WhyNot Cut writes all the editing results in it; the handoff file `HANDOFF.md` is written straight into the client folder, next to the `assets/` folder and the `data/` folder.

> **Careful:** The `assets/` folder and the `data/` folder belong to the client. WhyNot Cut never writes to them, moves anything out of them or deletes any file from them, and this protection is built into the software itself, not just an instruction. You are the one who adds files to them.

## Creating a folder for a client {#ch04-create}

The first client folder is created for you during the first setup with the command `/whynot-cut:start`. For any client after that, Claude creates the folder for you inside the clients folder, the folder you chose in the first setup to hold all the client folders, such as `~/Documents/WhyNot Clients` on a Mac or `D:\WhyNot Clients` on Windows:

1. Write a request to Claude with the client's name, such as “اعمل فولدر عميل جديد اسمه Example Clinic” (“Make a new client folder called Example Clinic”).
2. Claude creates the folder with all the subfolders, and shows you what goes in each one.
3. You find the same table in the file `START_HERE.md` inside the new folder, with a summary in Arabic. Open it with a right-click, then Open With › TextEdit on a Mac, or Open with › Notepad on Windows.
4. Put the client's files in their places as in the next table, then tell Claude, and it checks them and finishes setting up the client ([Chapter 5](05-new-client.md#ch05-title)).

![The client folder right after it is created.](shots/04-client-folder-1.png)

*The client folder right after it is created.*

> **Tip:** When you name the folder, avoid these characters on both Mac and Windows, because Windows refuses them and the folder may be opened on both: `\ / : * ? " < > |`, and don't end the name with a dot or a space.

## What goes in each folder {#ch04-folders}

| Folder | Put in it |
| --- | --- |
| `assets/Logo` | Logo files. Best is a PNG with a transparent background, plus an SVG or AI if there is one. |
| `assets/Fonts` | The brand's font files (.otf or .ttf). Install them on the computer as well. |
| `assets/Photos` | Approved photos of the speaker (JPG or PNG; camera RAW formats work on a Mac). |
| `assets/Brand` | A file introducing the client (a brief, a bio or a CV), and a colour file with HEX codes, such as a `colors.txt` file containing `#20ACAF`. |
| `data/Raw` | The raw videos to edit (MP4, MOV or MXF), one file per video. |
| `data/Episodes` | Full 16:9 podcast episodes to cut into reels, with an optional sheet named after each episode (see “Episode sheet” below). |
| `data/References` | Reference edits you want the edit to look like, and any written notes about the style. Optional. |
| `data/Broll` | Licensed stock or B-roll videos you are allowed to use, with a `SOURCES.md` file or the licence file. Optional. |
| `data/Music` | Licensed music only. Optional. |
| `data/SFX` | Your own sound-effects library. Optional; if there is none, original effects are made. |

**The clip's short name.** Each raw video gets a short name (clip id) that you use in your requests. If the file name is in Latin letters, the short name is the file name itself without the extension (the extension is what comes after the dot in a file name, such as `.mp4` or `.md`), in capital letters, with an underscore in place of spaces and symbols: the file `C0001.MP4` has the short name `C0001`, and the file `Dr intro.mp4` has the short name `DR_INTRO`. If the file name is in Arabic, it is given a short name such as `CLIP_1A2B3C`, and the list of short names is saved in `output/discovery/clip-ids.json`, a data file that WhyNot Cut reads and you don't need to open: ask Claude for the short name of any video.

**What if brand files are missing?** You can start without the logo, the fonts or the colours, but Claude will tell you what will look generic without them, and it will not invent a substitute of its own.

## Checking the files after you add them {#ch04-check}

After you finish copying the files, and after any download from cloud storage has finished:

1. Write to Claude that you added files, such as “حطيت الملفات، افحصها” (“I added the files, check them”).
2. Claude shows you the clips it found and the missing material. It can also check more deeply: the formats, the video's orientation, the audio, and files put in the wrong place, without changing anything.
3. Add what is missing, or start editing if what is there is enough.

In Claude's messages you will see the command it runs itself for this check; you don't need to type it. The example is from a Mac; on Windows the location starts with the drive letter, such as `D:/`:

*Claude runs this — you don't type it*

```
reel inbox --root "/Users/sample/Documents/WhyNot Clients/Example Clinic"
```

![The check result: what was found, what is missing, and how the gap affects the look.](shots/04-client-folder-2.png)

*The check result: what was found, what is missing, and how the gap affects the look.*

## The episode sheet {#ch04-episode-sheet}

For each episode in `data/Episodes` you can add a short text sheet with the same name as the episode and the extension `.md`. For example, the episode `EP01.mp4` has the sheet `EP01.md`. The sheet is optional, but it improves the result a lot, because publishing links are taken only from it. WhyNot Cut does not write it into `data/` itself; you are the one who saves it there, in one of two ways:

- **Easiest: ask Claude for its text.** Type, for example, “اكتبلي ورقة الحلقة EP01” (“Write me the episode sheet for EP01”), with the show's name, the host, the guest and the links. Claude writes the full text for you in the chat, and you copy it and save it with the steps below.
- **Or write it yourself** from the example after the steps.

1. Open an ordinary text editor. On a Mac open TextEdit, then choose Format › Make Plain Text so the file becomes plain text. On Windows open Notepad: type Notepad in the Start menu and open it.
2. Paste the text Claude wrote, or copy the example after the steps and change only the words after the colons. Leave everything else as it is: the two `---` lines at the top and bottom of the sheet, the colons, the quote marks, the square brackets, and the two spaces before the dash. If there is no sponsor, leave the line `sponsor: ""` as it is. The easiest way is to ask Claude for the sheet's text.
3. Save the file as `EP01.md` in `data/Episodes`, next to the episode. On a Mac: choose File › Save, type the name, choose the `data/Episodes` folder, then Save; if TextEdit asks about the extension, choose Use .md. On Windows: choose File › Save As, and under “Save as type” choose All files so the file is not saved with the `.txt` extension, then type the name and save it in the same folder.
4. Write to Claude that you added the sheet.

![Save the sheet with the .md extension, not .txt.](shots/04-client-folder-3.png)

*Save the sheet with the .md extension, not .txt.*

An example of a complete episode sheet:

```
---
show: "Example Clinic"
episode: 1
host: "Dr. Sample Example"
guest: "Sample Guest — fitness coach"
links:
  - https://example.com
sponsor: ""
avoid: [prices, politics]
---
```

You can write the values in Arabic too, such as the show name “عيادة مثال” (Example Clinic).

| Field | What it means |
| --- | --- |
| `show` | The show's name. |
| `episode` | The episode number. |
| `host` | The show's host. |
| `guest` | The guest and their role, in the form: name — role. |
| `links` | The links mentioned in the publishing text, each link on a line that starts with two spaces and then a dash, as in the example. |
| `sponsor` | The sponsor if there is one, or left empty. |
| `avoid` | Topics you want to avoid. If Claude suggests a reel about one of them, it writes a warning next to it, and the decision is yours. |

The details of podcast mode are in [Chapter 8](08-podcast.md#ch08-title).

## The results folder `output/` {#ch04-output}

All editing results are written to `output/`. Each clip has a folder named with its short name inside `output/projects/`, and the main things you will open in it are:

| Location (for clip C0001) | What is in it |
| --- | --- |
| `output/projects/C0001/01_analysis/edit-plan.md` | The edit plan you approve. |
| `output/projects/C0001/07_premiere/project/` | The Premiere Pro project, such as `C0001_EC_EDIT.prproj`. |
| `output/projects/C0001/08_quality_control/preview/` | The preview video `C0001_preview.mp4`. |
| `output/projects/C0001/08_quality_control/` | The QC (quality check) results. |
| `output/projects/C0001/09_handoff/` | The two handoff files: the `README.md` file and the `final-editor-checklist.md` file. |

Also in `output/`:

- `output/client_database/`: the client profile and their reference style ([Chapter 5](05-new-client.md#ch05-title)).
- `output/episodes/EP01/`: the results for each podcast episode: the transcript, the reels plan, the candidates' previews and the publish package. Each reel you pick becomes a separate clip in `output/projects/`.

## Common mistakes in the client folder {#ch04-mistakes}

| The mistake | Why it causes a problem | The right way |
| --- | --- | --- |
| Putting a full podcast episode in `data/Raw` | `data/Raw` is for raw videos, and each file in it becomes one video. A full episode has podcast mode, which suggests reels from it with timecodes. | Put the episode in `data/Episodes` and ask “طلّع ريلز من الحلقة” (“Make reels from the episode”). |
| The clients folder inside iCloud, OneDrive or Dropbox | Files kept “online only” are not really on the computer, so transcription fails. | Choose an ordinary folder on the disk that is not synced. |
| Starting before copying or downloading has finished | A file that is incomplete or not there yet gets checked. | Wait until copying finishes, then ask for the check. |
| Adding font files without installing them on the computer | Premiere Pro and After Effects need the fonts installed. A font that is not installed is reported as a blocker, and is never silently swapped for another font. | Install all the fonts in `assets/Fonts` on the computer. |
| Files in the wrong folder, such as photos in `data/Raw` | They are not used in their right place. | Move them yourself; the file check warns you about anything put in the wrong place. |
| Changing or replacing a file in `data/` after work on it has started | Every step that relied on the old file becomes stale, and its result is no longer valid after the change. | If the material changed, ask “جاهز؟” (“Ready?”) and Claude shows you the steps that need redoing. |
