---
title: Setting up a new client
slug: 05-new-client
order: 5
lang: en
dir: ltr
---

# Setting up a new client {#ch05-title}

Before the first edit for any client, Claude reads that client's files and builds a “client profile” for them: their name and field, their colours, fonts and photos, the editing style they like, and the people who appear in their videos. This profile is what makes the graphics and the on-screen text look like the client's brand, not generic.

## When you need to set up a new client {#ch05-when}

- The first time you work for a client who has no profile yet.
- If you start an edit and Claude finds the client has no profile, it starts the setup first and does not guess the brand or the style.
- In the program's first setup, the start wizard moves on to this step automatically after creating the first client folder.

## Steps to set up the client {#ch05-steps}

1. Make sure the client folder is ready, with the brand files in `assets/` and the material in `data/` ([Chapter 4](04-client-folder.md#ch04-title)). If there is no folder yet, Claude creates it and shows you what goes in it, then waits until you add your files.
2. Tell Claude “عميل جديد” (“New client”), or use the command:

   ```
   /whynot-cut:new-client
   ```
3. Claude chooses the profile id and the prefix (see the next part) if you did not set them, and tells you what they are.
4. Claude reads the client's files and writes the profile. This can take a while depending on the number of photos and reference videos, and you can work on something else in the meantime: Claude writes in the chat what it found when it finishes.
5. It shows you what it found and what is missing, and asks you about anything it cannot learn from the files.
6. After that the client is ready for editing with the command `/whynot-cut:edit` ([Chapter 6](06-edit-one-video.md#ch06-title)).

![The setup summary: what was found and where it came from, what is missing, and what needs you.](shots/05-new-client-1.png)

*The setup summary: what was found and where it came from, what is missing, and what needs you.*

## The profile id and the prefix {#ch05-id-prefix}

Each client has two short names used in the files:

| Item | Its form | Example Clinic example |
| --- | --- | --- |
| Profile id | Lowercase Latin words with a dash between them | `example-clinic` |
| Prefix | Two or three capital Latin letters | `EC` |

The prefix appears in the names of the output files, so the Premiere project for clip `C0001` is named `C0001_EC_EDIT.prproj`. If you don't set the two names, Claude derives them from the folder name and tells you what they are. If you want other names, write them to Claude before it starts, such as “خلّي البادئة EC” (“Make the prefix EC”). Claude saves the profile inside `output/client_database/reel-profile/` in the client folder.

## What Claude reads from the client's files {#ch05-research}

Claude reads only the client's own files, and builds the following from them, naming the file each piece of information came from:

- **The brand:** the colours, the fonts, the logo, and the sorting of the photos. It looks at every photo itself.
- **The name and the field** exactly as written in the brief, so they are spelled correctly in the transcript.
- **A glossary of the field's terms**, so medical or professional terms are spelled correctly.
- **The visual style** as it appears in the reference videos.
- **The client's standing notes** in the `notes.md` file.

Every piece of information about the brand or the style must rest on a file that exists in `assets/` or `data/`.

## The client's reference editing style {#ch05-reference-style}

From the videos in `data/References`, Claude writes a description of the client's editing style and its rules, once only, in the `output/client_database/reference_style/` folder. Every new video for this client uses this same style, so the references are not analysed again with every clip.

If you add, delete or change a reference video, Claude notices that the recorded style is out of date, and updates it before the next edit. A difference that belongs to a single video is recorded for that video alone, without changing the client's style.

> **Tip:** Put videos in `data/References` that show the look the client really wants. The clearer the references, the closer the first edit comes to what is wanted.

## People: title and pronoun {#ch05-people}

The profile has a list of the people who appear in the client's videos (`people`), and for each person: the name, the role, the gender, the title in Arabic and English, and the pronoun. This list is the only source for the title Dr. (in Arabic “الدكتور” for a man or “الدكتورة” for a woman) and for a masculine or feminine pronoun.

> **Careful:** A person's gender is never guessed from their name. As long as the gender is unknown in the list, Claude writes “Dr.” or the name only, in its messages, its tables and its file names, and asks you to confirm.

An example from the Example Clinic profile:

| Name | Role | Gender | Title | How it is written |
| --- | --- | --- | --- | --- |
| Dr. Sample Example | The doctor who appears on camera | Male | Dr. (“الدكتور”) | “Dr. Sample” and he/him |
| Nour Placeholder | Leads the conversation from off camera and reads the questions | Unknown | Empty | “Nour Placeholder”, by name only, until you confirm |

When Claude asks you about a person whose gender is unknown, answer clearly. Until you answer, only the name is used.

## When the client's information is missing {#ch05-missing}

Claude does not fill the gap on its own. Any information not found in the client's files is written as “unavailable”, and appears in the summary it shows you. What is most often missing:

- **Fonts not installed on the computer:** these count as a blocker that is reported, and the font is never silently swapped for another. Install the fonts, then carry on.
- **HEX colour codes:** if there is no colour file in `assets/Brand`, ask the client for one.
- **The approved name-card format:** how the speaker's name and title are written on screen, as the client approves it.

When the missing information reaches you, put its file in its place in the client folder and tell Claude.

## Which profile applies to the client {#ch05-layers}

The client profile starts from the program's general settings, such as the Premiere sequence specifications, and then changes whatever is specific to this client. The client's own copy is saved in their folder, in `output/client_database/reel-profile/`.

The program also comes with a fictional example profile, `example-clinic`. It is never applied to any client unless you ask for it by name, and it is never applied just because a folder name looks similar.

To find out where any value came from, such as a colour, a font or a size, ask Claude, for example, “اللون ده جاي منين في ملف عيادة مثال؟” (“Where does this colour come from in the Example Clinic profile?”). It shows you the profile that applies and the source of every value in it.
