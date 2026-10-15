---
title: Revisions
slug: 10-revisions
order: 10
lang: en
dir: ltr
---

# Revisions {#ch10-title}

After you watch the preview or the built project, write your notes to Claude. Claude turns each note into a specific change that can be checked, makes it, rebuilds and re-checks, and writes you a report on each note separately. The example here is clip `C0001` from Example Clinic.

## Write numbered notes {#ch10-write}

1. Write your notes in the chat, numbered, one number per note, like this:

   “1- انقل بطاقة الاسم لفوق. 2- خلّي الإيقاع أسرع. 3- كلمة "الكوليسترول" مكتوبة غلط.” (“1- Move the name card up. 2- Make the pace faster. 3- The word 'cholesterol' is spelled wrong.”)

   Or use the command, with the clip number if there is more than one clip:

   ```
   /whynot-cut:revise "1- … 2- …" C0001
   ```

   Write your numbered notes in place of “1- … 2- …”, keep the quotation marks around all of them, then put the clip number after them.
2. Claude restates each note as a specific change. For example, “شيل كل السكتات” (“Remove all the silences”) becomes: remove every silence of 250 milliseconds or longer, then check again that no word was removed.
3. If a note is a question, such as “هل الكتابة زي الريفرنس؟” (“Does the text look like the reference?”), Claude answers you honestly, with the evidence, before changing anything.
4. If a note could mean two things that would each lead to a different edit, Claude asks you which one you mean. Otherwise it doesn't interrupt you with questions.
5. Watch the new preview video, review the plan summary after the change, then approve it as in [Approving the plan in the chat](06-edit-one-video.md#ch06-approval-chat). If you said “امشِ على طول” (“Just go”) with your notes, your approval is recorded in your own words.
6. Claude rebuilds the project in Premiere Pro, runs the quality check again, and updates the handoff files.

![The numbered notes, and what Claude understood from each one.](shots/10-revisions-1.png)

*The numbered notes, and what Claude understood from each one.*

> **Tip:** If all your notes are about the sound of a clip that is still in the editing stages before the build, such as “الصوت فيه دوشة” (“There's noise in the sound”) or “شيل السكتات” (“Remove the silences”), the audio command alone is enough: `/whynot-cut:fix-audio`. Its cleanup is measured, with before-and-after evidence. Removing silences from a sequence open in Premiere is Hush's job in version 3.0 ([Chapter 12](12-hush.md#ch12-title)).

## Which note changes what {#ch10-kinds}

Claude sends each note to the part responsible for it, and independent notes are carried out together, at the same time:

| The note is about | Example | What changes |
| --- | --- | --- |
| Sound: noise, hum, loudness, silences, breaths | “الصوت واطي في الآخر” (“The sound is low at the end”) | The audio is cleaned again with new settings, with measured evidence. |
| Content: the words on screen, the moments that get a graphic, timing, cuts, the style of the statements | “خلّي الإيقاع أسرع” (“Make the pace faster”) | The edit decisions in the plan, then the graphic images and the preview video. |
| How the graphics and the on-screen text (captions) look and move | “الكابشن صغير” (“The captions are small”) | The graphic template settings, then new preview images. |
| Transcript words | “الاسم مكتوب غلط” (“The name is spelled wrong”) | The transcript is corrected, then everything that depends on it. |
| The wording of a medical or religious statement | “العبارة دي محتاجة مراجعة” (“This statement needs review”) | Review only: the list of what needs medical or religious sign-off is updated, and it stays in “Needs you”. |

## A standing rule for this client {#ch10-standing}

Some notes aren't for this video alone: they're a way the client always wants things, such as “دايمًا خلّي الجرافيك الزجاجي في الآخر بس” (“Always keep the glass graphic for the end only”). Claude saves these in the client's style file, so every video after that follows them:

```
output/client_database/reel-profile/style.json
```

With a written explanation in `notes.md` in the same folder.

> **Tip:** If your note is a standing rule, say so clearly with a word like “دايمًا” (“always”) or “في كل الفيديوهات” (“in every video”), so it isn't taken as being for this video only.

## Protecting your edits in Premiere {#ch10-protect}

A rebuild always starts from the plan. So if you edited the Premiere project by hand after the build, your edits will not carry over to the new project. WhyNot Cut detects this: a warning appears in the quality check, or the build stops with a message saying you edited the project by hand (it may appear in English as `EDITOR_CHANGES_PRESENT`). This is not an error but protection for your edits: Claude tells you so plainly, and you choose what happens next. If the project is rebuilt, the old project is kept as a backup copy with a name like:

```
C0001_EC_EDIT_prev_<time>.prproj
```

Then you choose between three options:

| Option | What happens |
| --- | --- |
| Rebuild anyway | A new project is built from the plan, and your manual edits don't carry over to it. This only happens with your explicit approval. |
| Make the change by hand | Claude gives you the exact timings and values so you make the change yourself in your current project, and your edits stay as they are. |
| Rebuild, then redo your edits | The project is built again, then you redo your manual edits on it. |

> **Careful:** Save your project in Premiere Pro before any rebuild, because a rebuild closes the open project.

## The report on each note {#ch10-report}

After the rebuild and the quality check, Claude writes a report for each note, by its number: what changed, the evidence for it (numbers or frames), and any caveat. Then the usual three sections: “Verified”, “Not verified” and “Needs you”.

![A report for each note, in the same order you wrote them.](shots/10-revisions-2.png)

*A report for each note, in the same order you wrote them.*
