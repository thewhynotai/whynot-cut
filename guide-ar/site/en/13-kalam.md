---
title: "Captions: WhyNot Kalam"
slug: 13-kalam
order: 13
lang: en
dir: ltr
---

# Captions: WhyNot Kalam {#ch13-title}

WhyNot Kalam (“Kalam”) comes with version 3.0 of WhyNot Cut. It turns the speech you hear in part of a Premiere Pro sequence into ready captions: timed to the sound, spelled correctly by the client's rules, and split into short phrases that follow the meaning. And it puts them where you need them: a captions track in the sequence, clips from a ready-made motion graphics template (MOGRT), or an SRT file (a text file with every caption and its timing). Its aim is one press, with no manual fixing afterwards.

> **Tip:** Today Kalam isn't in the version you have. In the full edit of raw footage, the on-screen text is designed in the client's brand as part of the plan ([Chapter 6](06-edit-one-video.md#ch06-pipeline)). The rest of this chapter describes version 3.0.

> **In 3.0 — not verified yet:** The button names and pictures in this chapter may change slightly when the tool is released.

## What Kalam does and doesn't do {#ch13-what}

- **It picks the best model for the language:** for Egyptian dialect, for English, or for any other language.
- **It puts every word exactly on its sound:** no caption appears before its first word is spoken, and there's no gap between one caption and the next.
- **It corrects the text with Claude** using spelling rules and the glossary, without rewording what the speaker said.
- **It splits the speech into units of meaning:** a whole phrase in each caption, usually on one line, and it never splits a term.
- **It puts the result where you want it:** a captions track, a MOGRT template, or an SRT file in sequence time.

It doesn't translate from one language to another, it doesn't design the captions' look beyond the template you choose, and it doesn't tell speakers apart. It doesn't cut or move any clip already in the sequence: it only adds.

> **In 3.0 — not verified yet:** These limits come from the tool's spec and haven't been tried on a real sequence yet.

## When to use Kalam {#ch13-when}

- A reel in Egyptian Arabic that you want captioned on a captions track.
- The same reel, but with the MOGRT template you use for the client, such as a 9:16 caption template.
- Only an SRT file for a part between In/Out points, to upload with the video to the platform.
- An English interview, with one line per caption.

In the full edit that WhyNot Cut does for raw footage, the on-screen text (captions) is designed in the client's brand as part of the plan ([Chapter 6](06-edit-one-video.md#ch06-pipeline)). Kalam is for the sequence you are working on yourself in Premiere.

> **In 3.0 — not verified yet:** These are examples of using the tool, and they will be reviewed when it is tried.

## Captions from the Kalam tab {#ch13-panel}

1. Open the sequence in Premiere Pro, then open the WhyNot Cut panel, choose the “Tools” section, then “Kalam”.
2. Choose the “Mode”, meaning the language of the speech (next section).
3. Choose the “Range”, and check the audio track buttons: only the selected tracks' audio is exported; the others are muted during the export.
4. Choose the “Output”: captions track, MOGRT, or SRT only ([Kalam's three outputs](#ch13-outputs)).
5. Review “Caption settings” and “Correction” if you want, or leave them as they are.
6. Click “Start”. Progress shows stage by stage: loading the models, then transcribing, then timing (with the hardware used: the graphics card or the processor), then correcting, then building the captions, then “Done” or an error message. With it is a “Stop” button.
7. Review the list of results: every caption with its timing. Click any caption to move the playhead to it and hear it.

### Mode: the language of the speech {#ch13-modes}

| Mode | Model |
| --- | --- |
| “Arabic”, the default | A Whisper model trained on Arabic dialects, the best for Egyptian speech. |
| “English” | The Parakeet model for English. |
| “Other” | The general Whisper model, which recognises the language by itself. |

The Whisper and Parakeet transcription models run on your computer. After transcription, in every mode, the timing tool places each word on the sound. Then the text is cleaned: non-speech tags such as \[music\] are removed, along with words the model writes by mistake that aren't in the sound, such as a long repeat of the same word, sentences the model sometimes invents such as “شكرًا للمشاهدة” (“Thanks for watching”), and any word that falls on a silence.

### Range {#ch13-range}

Four choices:

- **“In/Out”:** what's between the two points.
- **“Whole sequence”**.
- **“From playhead to end”**.
- **“Selected clips”:** the part covered by the clips you selected.

If what you chose isn't possible, the panel tells you why: there are no In/Out points, you didn't select any clip, or the playhead is at the end of the sequence. Then choose another range from the options above, or set In/Out points, or select the clips.

### Caption settings {#ch13-settings}

| Setting | Default |
| --- | --- |
| Most characters per line | 32 |
| Most lines per caption | 2 (set it to 1 for one-line captions) |
| Longest caption duration | 4.5 seconds |
| Shortest silence that separates two phrases | 0.22 seconds |

And the build rules are fixed:

- Each caption starts with its first word, each caption follows the one before it directly with no gap, and the last caption ends 0.3 seconds after the last word.
- Speech is split at the ends of sentences and at silences of 0.6 seconds or longer. A line where the sentence doesn't end is joined to the next one if the silence between them is shorter than that.
- A term is never split, so “الـ” (“the”) never comes apart from the word after it. A complete unit of meaning may go over the line length by a quarter, rather than being split.
- No small word is left alone in a caption, such as “ف” (“so”).

> **In 3.0 — not verified yet:** The button and setting names here are taken from the tool's spec, and may differ slightly in the panel.

![Kalam: mode, range and output, then the results.](shots/13-kalam-1.png)

*Kalam: mode, range and output, then the results.*

## Kalam's three outputs {#ch13-outputs}

| Output | What happens |
| --- | --- |
| “Captions track” | A captions track from Premiere itself in the sequence, in sequence time. |
| “MOGRT” | One clip from the template for each caption, on the video track you choose, with the text written into the template's text field. |
| “SRT only” | An SRT file next to the project file, in sequence time, with no change to the sequence. |

Whatever you choose, an SRT file is always written, in a folder next to the project file, named after the sequence and the time:

```
Kalam Captions/C0001_EC_EDIT 101500.srt
```

### Choosing a MOGRT template {#ch13-mogrt}

When you choose MOGRT, a card for the selected template appears with its picture, along with a choice of video track and a choice of text field. From it you open a gallery of all the `.mogrt` templates in Premiere's Local Templates folder, with each template's picture, name and folder. Search by name or show one folder, and click a template to choose it. For a template somewhere else, choose “From a file…”.

Where the Local Templates folder is:

- macOS: `~/Library/Application Support/Adobe/Common/Motion Graphics Templates`\
  To open it: in Finder press Cmd+Shift+G, paste the path, then Enter. The `Library` folder is usually hidden in Finder, and this way opens it directly.
- Windows: `%APPDATA%\Adobe\Common\Motion Graphics Templates`\
  To open it: paste the path into the address bar in File Explorer, then Enter.

The text field list shows the template's own text fields, and the default is its first real text field. Placing a template is all or nothing: if the template has no editable text, a clear message appears, and every clip placed up to that moment is removed. An example is the Basic Title template in Premiere 26, which doesn't offer a text field you can type into. Choose another template.

> **In 3.0 — not verified yet:** The three outputs and the template gallery haven't been tried on Windows yet.

![Choosing a MOGRT template from the gallery.](shots/13-kalam-2.png)

*Choosing a MOGRT template from the gallery.*

## Correcting without changing the meaning {#ch13-correct}

After transcription, the text is sent to Claude to correct the spelling. Only the text is sent, in groups of 60 phrases, with 3 lines before and 3 after each group so it understands the context. The audio and the timings never leave your computer. Claude returns one line for each line, and marks the end of each unit of meaning, which is where the captions are split.

The default Arabic rules (you can edit the rules for each mode in “Correction”):

- Full, correct spelling, with the hamza in its place, and “انت” (“you”) written without a hamza.
- The future tense written with “هـ”, not “حـ”: “هيروح” not “حيروح” (“he will go”).
- The Egyptian dialect stays as it is.
- English terms in English letters starting with a capital, with “الـ” (“the”) before them kept separate, as in “الـ Reputation”.
- Medical terms corrected from the context.
- No punctuation, and no vowel marks except the natural tanween (the doubled ending marks).
- No shortening, no adding, no rewording, and no merging, splitting or moving of words.

And the “Glossary”: each line has the correct spelling, then an = sign, then the mistakes you want corrected, separated by commas, such as “الكولاجين = الكلاجين، الكولاجن” (“collagen = two common misspellings of it”).

### Protecting what the speaker said {#ch13-faithful}

Every line Claude corrects is compared with what was actually said. If it shortened the line to less than 60% of the original, reworded it, translated it, or added words, the correction is rejected and the line stays as it was said, then WhyNot Cut applies the spelling rules to it automatically. So a wrong correction can't shorten a caption or change its meaning.

After Claude, WhyNot Cut applies these automatically every time: removing punctuation and vowel marks (keeping tanween), the glossary, and a capital first letter for English terms in Arabic mode. Then every corrected word is mapped back to the matching spoken word, so every caption starts at the start of a real word.

You can turn correction off in “Correction”. If Claude isn't available, the captions come out uncorrected, with a message saying so; open a Claude chat on your computer, then run Kalam again.

> **In 3.0 — not verified yet:** It hasn't been decided yet which route corrects the text by default when run from the panel ([Chapter 7](07-premiere-panel.md#ch07-ai)); protecting what the speaker said works on every route.

## Kalam from the chat {#ch13-chat}

Write to Claude “ترجم الريل ده” (“Caption this reel”; literally “Translate this reel”) or “كابشن الريل ده” (“Caption this reel”). The word “ترجم” (“translate”) here means captions in the same language as the speech, the way editors in Egypt say it: Kalam doesn't translate from one language to another. And say what you want if it isn't the default, such as captions with a MOGRT template, or only an SRT file for the part between In/Out points. Claude runs the same tool as the panel.

After every run, from the panel or from the chat, one report is written: what changed, where the captions were put, where the SRT file is, and how to undo. Claude reads it and passes it back to you under “Verified”, “Not verified” and “Needs you”.

> **In 3.0 — not verified yet:** Kalam requests from the chat don't work in the version you have today.

![Kalam from the chat: the same result and the same report.](shots/13-kalam-3.png)

*Kalam from the chat: the same result and the same report.*

## Undo in Kalam {#ch13-undo}

Kalam doesn't cut or move anything in the sequence; it only adds. So undo means removing what it added:

- **MOGRT:** click “Undo” in Kalam, and the clips it placed in this range are removed.
- **Captions track:** if you ran Kalam from the three-tools button ([Tidy → Cut → Caption](#ch13-flow)), “Undo” removes it from the backup copy. If you ran Kalam on its own, delete the track by hand in Premiere, because Premiere doesn't let add-on tools read or delete it.
- **SRT file:** a normal file in the `Kalam Captions` folder. Keep it or delete it.

> **In 3.0 — not verified yet:** Undo hasn't been tried on a real sequence yet.

## Privacy and safety in Kalam {#ch13-safety}

- Only the caption text goes to Claude. The audio and timings stay on your computer.
- An Anthropic API key (a secret code from an Anthropic developer account), if you use one, is saved in a settings file that only your account on the computer can read, and reaches the engine in a temporary file that is deleted as soon as the work starts. It is never written in logs or reports.
- When Kalam runs Claude in the background to correct the text, Claude works in a limited mode: it only reads and corrects the caption text, it doesn't open files or run anything, and the chat isn't saved.
- Protecting what the speaker said: a wrong correction can never shorten or reword a caption; the original stays.
- Placing a MOGRT template is all or nothing.

> **In 3.0 — not verified yet:** These rules come from the tool's spec, and our team checks them in a safety review before release.

## Kalam with the client folder {#ch13-client}

If the sequence belongs to a client in your clients folder, Kalam's glossary and rules start from the client profile: the medical terms, the names, and each person's title and how to refer to them as recorded in the profile. You can edit them in the panel. Outside a client folder it starts from the default rules. Protecting what the speaker said works in both cases.

> **In 3.0 — not verified yet:** The glossary starting from the client profile hasn't been tried yet.

## The Kalam pack on macOS and Windows {#ch13-pack}

Kalam's models come in one pack: the Arabic dialects model, the English model, the timing tool, and what they need to run. The install sets it up automatically with the rest of WhyNot Cut, installed separately from the rest of the program so the program stays light. You'll find it on the “Models” page in the panel with its status and size ([Models](02-install.md#ch02-models)). If you ask for captions while the pack is still downloading, the engine tells you how much is left.

- **macOS:** it works on every Mac. On a Mac with Apple Silicon it's at its fastest. On a Mac with an Intel processor it runs the same models on the processor (CPU), so it's slower.
- **Windows:** it runs on an NVIDIA card from the RTX 20 to 50 series, with card driver (the card's control program from NVIDIA) version 570 or newer. Without one it runs on the processor (CPU), and the progress tells you which hardware is in use. On the processor, expect it to be 2 to 4 times slower.

The tool is installed with the panel when you install WhyNot Cut, and the computer check checks Kalam and its models. The tool's menu has: open the logs, open the Kalam folder, save a report for support to the desktop (never with settings or keys), and reset the settings. Kalam's logs are also included in “Copy diagnostics” ([Chapter 7](07-premiere-panel.md#ch07-errors)).

> **In 3.0 — not verified yet:** The pack's size will be written here when it's released, and the Windows version of Kalam hasn't been tried on a real computer yet.

## Tidy → Cut → Caption {#ch13-flow}

The three tools work together in a natural order: tidy the project, then cut the silences, then write captions on the cut sequence. The panel has one button that runs all three in this order: Tidy, then Hush, then Kalam.

1. Open the sequence, and in the WhyNot Cut panel click the three-tools button.
2. Tidy scans the project and shows its preview. Approve or adjust, as in [Chapter 11](11-tidy.md#ch11-panel).
3. Hush scans the sequence and shows the cuts on the audio waveform. Approve or adjust, as in [Chapter 12](12-hush.md#ch12-panel).
4. Kalam shows the mode, range and output. Approve to build the captions ([the start of this chapter](#ch13-panel)).

![The three tools in order, each step waiting for your approval.](shots/13-kalam-4.png)

*The three tools in order, each step waiting for your approval.*

The button only saves you moving between the tools, and every protection stays as it is:

- Each step shows its preview, and only continues with your approval of that step.
- Tidy, Hush and Kalam each save their own backup copy before any change: Kalam writes (WhyNot Kalam backup …) before it adds the captions track or MOGRT clips, and needs no copy when it only writes an SRT file. Each step has its own undo as in its chapter, and Kalam's undo removes exactly what it added. To undo everything, undo in reverse order: Kalam, then Hush, then Tidy.
- Nothing is merged out of sight: each tool writes its report, and you see what each one did.

> **In 3.0 — not verified yet:** The button's name and place in the panel may differ slightly, and the three backup copies and the reverse undo haven't been tried yet.
