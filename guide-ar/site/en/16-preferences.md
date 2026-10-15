---
title: Preferences
slug: 16-preferences
order: 16
lang: en
dir: ltr
---

# Preferences {#ch16-title}

Preferences set how WhyNot Cut works with you: the language it talks to you in, whether it stops for you to approve each plan, how fast transcription is, and where the clients folder is. The start wizard `/whynot-cut:start` asks you about four of them the first time: where the clients folder is, approval, the transcription model, and the name it calls you by (optional), and it sets the talking language to the language of your messages. You can change them at any time.

## The list of preferences {#ch16-list}

What the values in the next table mean: `true` = yes, `false` = no; `ar` = Arabic, `en` = English; `ask` = ask me, `auto` = automatic. You don't need to type these values yourself: say what you want in your own words, as in the next section.

| Preference | Values | What it does |
| --- | --- | --- |
| `editor_name` | Text | The name Claude calls you by. If it's left empty (the default), no name is used. |
| `language` | `ar` (default) · `en` | The language it talks to you in. The on-screen text always follows the speaker's language. |
| `approval` | `ask` (default) · `auto` | `ask`: stops at every plan until you approve. `auto`: shows the plan and the preview video, then builds, and the approval is recorded as delegated, naming the settings file. |
| `whisper_model` | `large-v3` (default) · `large-v3-turbo` · `medium` · `small` | The balance between transcription accuracy and speed. The `medium` and `small` models are clearly weaker on Arabic medical terms. |
| `preview_video` | `true` (default) · `false` | Exports the preview video before approval. |
| `clients_root` | Folder | The clients folder. Used in the computer check, in the chat's opening message, and when you mention a client by its folder name only. |
| `notify_done` | `true` (default) · `false` | Starts the final report of long jobs with a clear line saying they're Finished. |
| `panel_link` | `true` (default) · `false` | In version 3.0: at the start of every chat, starts in the background the engine that the WhyNot Cut panel in Premiere connects to. With `false` the panel stays disconnected until Claude starts it ([Chapter 7](07-premiere-panel.md#ch07-title)). |
| `evidence_gate` | `true` · `false` (default) | With `true`: if Claude says the edit is ready or finished without running the quality check or verification, it's sent back once to check first. Doesn't work with `auto` approval. The rule “nothing is ready without the quality check” always applies ([Chapter 6](06-edit-one-video.md#ch06-qc)); this setting only adds a second check on top of it, so leave it as it is unless you want this extra check. |
| `magnific_budget_credits` | A number, 0 or more (default 300) | In version 3.0: the most Magnific credits one edit may spend. The value 0 means Magnific is never used ([Chapter 15](15-magnific.md#ch15-title)). |

> **In 3.0 — not verified yet:** The `panel_link` and `magnific_budget_credits` settings have no effect until the new WhyNot Cut panel and Magnific assets reach you.

## Change a preference {#ch16-change}

1. Say what you want in your own words, such as “كلمني بالعربي” (“Talk to me in Arabic”), “متسألنيش قبل ما تبني” (“Don't ask me before you build”) or “استخدم التفريغ الأسرع” (“Use the faster transcription”). Or use the command:

   ```
   /whynot-cut:preferences
   ```

   You can write the value directly after it, such as `/whynot-cut:preferences language=ar`.
2. Claude changes the value in the preferences file actually in use, and keeps the other values and the notes you wrote in the file as they are. An unknown setting or a wrong value is refused.
3. Claude shows you the current values again, to confirm the change was made.

![Changing a preference, then showing the current values to confirm.](shots/16-preferences-1.png)

*Changing a preference, then showing the current values to confirm.*

To see the current preferences at any time, ask Claude about them. It shows you all the values and the name of the file they came from. If the file has a wrong value, it's ignored and Claude tells you about it.

> **Tip:** WhyNot Cut commands see the change straight away. The chat's opening message reads the preferences only when a new chat starts.

## Saying “متسألنيش” (“don't ask me”) {#ch16-stop-asking}

If you say “متسألنيش” (“Don't ask me”) or “امشِ على طول” (“Just go”) when no plan is waiting for your approval, or it seems you mean all plans, Claude asks you one question, and changes nothing until you reply:

- **For this video only:** it counts as approval of this plan alone, and the preferences file doesn't change.
- **From now on:** the `approval` value becomes `auto`. Claude then reminds you that this is a standing, delegated approval of every future plan.

But if you say it while a plan is waiting for your approval, it counts as approval of that plan alone without a question, and the preferences file doesn't change ([Chapter 6](06-edit-one-video.md#ch06-approval-chat)).

> **Careful:** Even with `auto` some things are never approved automatically: a graphic that needs the doctor's sign-off, or the speaker's or content owner's sign-off for religious-content clients, stays in “Needs you”, and picking reels from the episode always stays your decision ([Pick the reels](08-podcast.md#ch08-pick)).

## Where the preferences file is saved {#ch16-file}

You don't need to open the preferences file or write it by hand. Tell Claude what you want, and it writes in the right file and shows you the result. If you want a preference for one client only, name the client in your request, such as “خلّي الموافقة auto لعيادة مثال بس” (“Set approval to auto for Example Clinic only”), and Claude writes a preferences file just for that client's folder, and the other clients' preferences stay as they are.

### For the curious: the file and the order it's read in {#ch16-file-details}

The preferences are saved in a text file called `whynot-cut.local.md` inside the `.claude` folder. The file holds only the preferences that were set in it. For example, the file the start wizard writes on a Mac (on Windows the clients folder location starts with the drive letter, such as `D:/WhyNot Clients`):

```
---
editor_name: ""
language: ar
approval: ask
whisper_model: large-v3
clients_root: "/Users/sample/Documents/WhyNot Clients"
---
```

Each preference's value is read from the first place that sets it, in this order:

| Order | Place | When it's used |
| --- | --- | --- |
| 1 | A file in the client folder you're working in (or the current folder), then the folders above it | For preferences for one client. |
| 2 | The computer's file: a file in the clients folder, then `~/.claude/whynot-cut.local.md` in the user folder on the computer | The general preferences for all clients. The second file is the one the start wizard writes. |
| 3 | The plugin's options inside the Claude app (plugin options) | Language, approval, transcription model, and the Magnific credit limit (in version 3.0), if no file sets them. |
| 4 | The default values | Every preference that no earlier place set. |

A preference the client's file doesn't mention is taken from the next place in the order, so your general preferences aren't lost. A wrong value in any file is ignored, and Claude tells you about it. On any change, Claude changes the value in the place it actually came from, whether a file or a plugin option, so a closer file doesn't override it. The one exception to this order is the clients folder location: if it's set in the plugin options, it wins over any file.

> **In 3.0 — not verified yet:** Where the plugin options are in the Claude app, including the clients folder location, the engine data location and the Magnific key, will be explained here with pictures.
