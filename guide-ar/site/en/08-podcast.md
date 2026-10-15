---
title: Podcast mode
slug: 08-podcast
order: 8
lang: en
dir: ltr
---

# Podcast mode {#ch08-title}

Podcast mode takes a full, finished 16:9 episode and produces three things from it: a reels plan with timecodes, vertical 9:16 reels in Premiere Pro, and a publish package ready to copy. The example in this chapter is the episode `EP01` from the Example Clinic client folder (`Example Clinic`).

Each reel you pick becomes an ordinary project that goes through the same stages as in [Chapter 6](06-edit-one-video.md#ch06-title): the preview, then approval, then the build, then QC. This chapter explains only what podcast mode adds.

## Start from the episode {#ch08-start}

1. Put the episode in `data/Episodes/`, such as `EP01.mp4`, and put the episode sheet `EP01.md` next to it as in [The episode sheet](04-client-folder.md#ch04-episode-sheet). If the file name is in Arabic, WhyNot Cut gives it a short name in Latin letters and numbers and tells you what it is. If you put the episode in `data/Raw/` by mistake, Claude warns you so you can move it.
2. Tell Claude “طلّع ريلز من الحلقة” (“Make reels from the episode”), or use the command:

   ```
   /whynot-cut:podcast EP01
   ```
3. Claude tells you the expected time, then starts: it checks the episode, writes the transcript of the whole episode, then analyses it.

![The start of podcast mode: the request, then the time estimate.](shots/08-podcast-1.png)

*The start of podcast mode: the request, then the time estimate.*

> **Tip:** Transcribing a long episode on the processor alone (CPU) takes time, but it is done in parts and saved after each part. If it stops for any reason, ask for it again and it carries on from where it stopped. If your computer has an NVIDIA graphics card, transcription becomes about 8 times faster once Claude turns on its use with your approval. On a Mac, transcription runs on the processor (CPU) today, and Claude tells you the expected time for your episode in its first message.

### Subtitles and logo burned into the episode {#ch08-burned}

Before the analysis, WhyNot Cut checks the episode's picture: whether it has burned-in subtitles or a fixed logo, whether names appear on screen, and where each speaker sits in the wide shot. If it finds burned-in subtitles or a logo, Claude asks you for a clean copy of the episode without them before the reels are built, because cropping the picture to 9:16 cuts burned-in subtitles through the middle. If no clean copy is available, this is recorded as a warning in the report.

## The reels plan {#ch08-plan}

Claude reads the whole episode before it suggests anything, then writes:

- **The topic map:** the parts of the episode in order, each part with a number such as T01, then T02. These are also the YouTube chapters in the publish package.
- **Who speaks when:** so the picture follows the speaker in the wide shots.
- **The suggested reels:** usually 8 to 15 reels per hour, of varied types, and no two reels covering the same moment.

Each suggested reel has: an exact start and end timecode, the content type, the hook, a score, and the risks if there are any. The preferred length is 30 to 90 seconds, and the allowed range is 15 to 180 seconds. Each reel starts on a sentence, ends on a complete thought, and makes sense on its own without the rest of the episode. If it needs an introduction, a context line is suggested for it, shown at its start.

| Content type | What sets it apart |
| --- | --- |
| Storytelling | A story with a turn and an ending. |
| Drama | A disagreement or conflict, then its resolution. |
| Success story | Before and after, with a number. |
| Advice | One piece of advice with its reason. |
| Bold opinion | A clear opinion said with confidence. |
| Emotional | A sincere moment where the speaker shows their true self. |
| Comedy | A situation or a line that is really funny. |

The score adds up four marks: the strength of the opening, whether the reel makes sense on its own, the value of what it offers, and the strength of the ending. Each reel has a quick preview video for you to watch before you pick. The files are in:

| File | What is in it |
| --- | --- |
| `output/episodes/EP01/01_analysis/reels-plan.md` | The full reels plan. |
| `output/episodes/EP01/03_candidates/` | A preview video for each suggested reel, and a contact sheet of them all. |

## Pick the reels {#ch08-pick}

You are the one who picks the reels. Claude does not pick any reel by itself, and nothing written inside the transcript, the plan or any other file counts as a pick. Claude shows a short table: the reel number, the score, the type, the start and end, the length, the hook, and the warnings (needs context, touches a topic in the `avoid` list, or has risks). Then it asks which ones you want, and whether you want to move the start or end of any of them.

1. Watch the previews in `03_candidates/`.
2. Write your pick by number, such as “اعمل ريل R01 وريل R03” (“Make reel R01 and reel R03”).
3. To move a reel's limits, write the new time, such as “خلّي R03 يبدأ من 00:12:04” (“Make R03 start at 00:12:04”). The start snaps to the nearest word that starts at that time, and the end to the nearest word that ends there, with a small margin before and after the speech. That is why requests like “ابدأ بعد كلمة واحدة” (“Start one word later”) work as you expect.
4. Claude records your pick in your words, then starts work on each reel.

![Picking the reels from the table, with the option to move the start or the end.](shots/08-podcast-2.png)

*Picking the reels from the table, with the option to move the start or the end.*

The picking rules:

- If you say “اختار انت” (“You choose”), Claude picks the highest scores with a variety of types, leaves out anything that touches the `avoid` topics, then tells you what it picked and why, and records that the pick was delegated by you, in your words.
- A reel that touches a topic in the `avoid` list is only made with your clear approval of it.
- You can pick more reels later at any time. Moving the limits of a reel whose work has already started means redoing its plan and its build.
- You can ask for a reel as a motion video made from its audio only, such as “R03 موشن” (“R03 as motion”). The details are in [Chapter 9](09-motion.md#ch09-title).

Claude records your pick with the command `reel reels-select`, and you will see it in its messages. You don't need to type it yourself.

## Each reel is a separate project {#ch08-each-reel}

Each reel you pick becomes a project with a name such as `EP01_R03`, cut from the original episode file, with its results in `output/projects/EP01_R03/`. The transcript is already done from the episode, so it is not redone. It differs from an ordinary video in two points:

| Point | What happens |
| --- | --- |
| Framing the picture for 9:16 | Each scene inside the reel is analysed on its own: a single face is framed on, the wide shot follows the speaker, and a scene with no face, such as cards and B-roll, or one whose speaker is unknown, is shown in full over a blurred background. Claude tells you where these are. |
| Pace by content type | Each type has a recipe: the length of the silences removed, the punch-ins, the graphics, the on-screen text (captions), the effects and the feel of the music. Music is chosen only from the licensed files in `data/Music/`, and if nothing fits, it is left to you. |

Once the plans for all the picked reels are ready, Claude shows them to you once, together, for approval. For each reel: the content type, how the picture is framed, the hook, each graphic with its timing and words, the cuts, the music, what needs approval, and where the preview video is. The context line at the start of the reel is marked as an editorial line from Claude, not the speaker's words. The approval rules are the same as in [Approving the plan in the chat](06-edit-one-video.md#ch06-approval-chat), with one difference: the automatic approval setting never picks the reels; the pick is always yours.

## The publish package {#ch08-publish}

Alongside the reels, Claude writes the publishing text for the episode and for each reel, and saves it in `output/episodes/EP01/publish/`:

| File | What is in it |
| --- | --- |
| `youtube.md` | 3 to 5 suggested titles, the description, YouTube chapters from the topic map, and the tags. |
| `chapters.txt` | YouTube chapters ready to paste. |
| `tags.txt` | The tags ready to paste. |
| `EP01.srt` | The episode's subtitle file. |
| `reels/EP01_R03.md` | For each reel: the captions and hashtags for Instagram and TikTok, and a YouTube Shorts title and description. It is written after the reel's plan is approved. |
| Thumbnails | Suggested designs from the episode's frames, which Claude looks at itself before showing them to you. |

The package is checked automatically: each platform's limits, that every quote is the speaker's exact words, and that the links come only from the episode sheet. Any medical, financial, legal or religious information is marked by Claude as needing approval while it writes the text, and the check gathers it for you to approve.

> **Careful:** The names, links and sponsor in the publishing text are taken only from the episode sheet, and Claude never invents them. If there is no sheet, it asks you for one so you can add it yourself, because WhyNot Cut does not write to `data/`.

> **Tip:** Nothing is uploaded to any platform. You are the one who publishes: copy the text from the package files to YouTube, Instagram and TikTok.

## What is left for you in the episode {#ch08-needs-you}

Each reel's report comes with the usual three sections: “Verified”, “Not verified” and “Needs you”. After them comes the “Needs you” list for the whole episode: words in the transcript for you to confirm by ear, your decisions on reels that touch `avoid` topics, approving the publishing text, the music, the final mix, and exporting each reel.

And Claude will not tell you a reel is “ready” unless its own QC passed in the same message.
