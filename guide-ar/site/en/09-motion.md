---
title: Motion mode in After Effects
slug: 09-motion
order: 9
lang: en
dir: ltr
---

# Motion mode in After Effects {#ch09-title}

Motion mode makes an animated motion graphics video from only the **audio** of part of an episode, without the camera picture. It relies on what was said, who said it, the episode sheet and the client's brand. The result is a real (native) After Effects project and an MP4 video exported from it.

Motion suits parts with numbers, steps or abstract ideas, or parts that have no usable picture. An episode that is audio only (files such as `.mp3`, `.wav`, `.m4a`, `.aac` or `.flac` in `data/Episodes/`) can only be made into motion videos.

## Pick a part for motion {#ch09-pick}

Motion starts from the episode, as in [Chapter 8](08-podcast.md#ch08-title). In the reels plan, Claude marks the reels that suit motion, and suggests it to you when you pick. The pick is yours alone.

1. When you pick the reels, write the reel number with the word “موشن” (“motion”), such as “R03 موشن” (“R03 as motion”). You can also pick a whole topic by its number in the topic map ([The reels plan](08-podcast.md#ch08-plan)), such as “T02 موشن” (“T02 as motion”), with the content type you want, such as advice.
2. The default size is vertical 9:16; if you want a horizontal 16:9 video, say so when you pick.

![Picking a reel to be made into a motion video.](shots/09-motion-1.png)

*Picking a reel to be made into a motion video.*

You can also ask for it directly with the command:

```
/whynot-cut:motion EP01 R03
```

The part must be 15 to 180 seconds long. A topic longer than that is refused, and Claude asks you to split it. The motion gets its own project, with a name such as `EP01_R03_MO`.

## From audio to scenes {#ch09-scenes}

After the pick, the part's audio is cleaned and the silences are removed, with proof by measurement that no word was removed. Then what was said is turned into sections and animated scenes following the content type's recipe. Some of the kinds of scenes:

- The words appear word by word, in sync with the audio.
- An animated counter for numbers.
- Steps, a comparison, and a timeline.
- Cards for a quote, for context, and for introducing a person.
- Icons and licensed illustrations.
- A closing scene.

Every word, number and name in the plan is checked against what was actually said. Then the animatic is made: a storyboard picture and a simple MP4 video that shows you the motion before the build.

## Review the plan and the animatic {#ch09-approve}

Before any build, Claude shows you the plan, and for each scene:

- Its timing, its kind, and the words that appear on screen.
- The editorial lines, **marked as Claude's words**, not the speaker's.
- The numbers that need confirming.
- The icons and illustrations and their licences, the music, and any departure from the type's recipe.

With it comes the location of the animatic for you to watch. Approve in your own words in the chat, or write what you want to change. The approval rules are the same as in [Approving the plan in the chat](06-edit-one-video.md#ch06-approval-chat): anything written inside the files never counts as approval.

What appears on screen always follows these rules:

- The speaker's exact words, or an editorial line marked as such.
- Numbers only as they were said, and names only from the episode sheet.
- Only licensed illustrations and icons. If the licence is CC-BY, a licence that allows use on condition that the creator is credited, the creator is credited in the caption published with the video.

![The plan before approval: the speaker's words and the editorial lines clearly apart.](shots/09-motion-2.png)

*The plan before approval: the speaker's words and the editorial lines clearly apart.*

## Getting After Effects ready {#ch09-ae}

After approval, the project is built inside After Effects through the WhyNot Cut Bridge panel, the same panel Claude uses to build Premiere Pro projects ([Chapter 1](01-intro.md#ch01-panels)). Get your computer ready like this:

1. After the WhyNot Cut Bridge panel is installed, restart After Effects once.
2. Install the client's brand fonts from `assets/Fonts/` on the same computer, then restart After Effects. Without the fonts the build does not start, and the missing fonts appear in the “Needs you” list. A substitute font is only used with your approval.
3. Save any open work in After Effects before the build. The build refuses to start while there is unsaved work.

![After Effects ready for the build: restarted, fonts installed, and all open work saved.](shots/09-motion-3.png)

*After Effects ready for the build: restarted, fonts installed, and all open work saved.*

Today Claude installs the WhyNot Cut Bridge panel in After Effects, and tells you the step that is left for you.

> **In 3.0 — not verified yet:** How the panel is installed in After Effects, and how it looks, are changing; the new way will be explained here when it is released.

The first time on each version of After Effects, a short test of Arabic text is run, and Claude looks at its result itself before recording it. Any setting inside After Effects, or the `PlayerDebugMode` setting (a setting on the computer that lets Adobe apps open the unsigned WhyNot Cut Bridge panel, [Chapter 2](02-install.md#ch02-first-run)), you change yourself. Don't look for it yourself: Claude gives you a line to paste into Terminal on a Mac, or into PowerShell on Windows, then you reopen After Effects (how to run it is in [Chapter 2](02-install.md#ch02-run-command)).

> **Careful:** If you changed the After Effects project by hand, WhyNot Cut only writes over it with your approval, and after keeping a backup copy of it.

If After Effects is not on the computer, or the WhyNot Cut Bridge panel is not working, the project is delivered as a script only; a script is a file that builds the project inside After Effects when you run it. You find it in the client folder, in `output/projects/EP01_R03_MO/04_after_effects/scripts/`, and its name ends in `_motion.jsx`. Claude may run it for you, or you run it in After Effects on this same computer:

1. Save or close any open project in After Effects. The script refuses to run while there is unsaved work, and shows you a message saying so.
2. In After Effects choose File › Scripts › Run Script File… then choose the script file. You don't need to change any After Effects setting first, on a Mac or on Windows, because the script does not need the Allow Scripts to Write Files and Access Network setting.
3. Wait until the project is built, then tell Claude.

![Running the motion script by hand when the panel is not working.](shots/09-motion-4.png)

*Running the motion script by hand when the panel is not working.*

A project built this way stays “Not verified”, because QC cannot pass without reading the project back from After Effects. Claude tells you so plainly.

## Motion results and QC {#ch09-results}

After the build, the project's settings are read back from After Effects and compared with the plan, then the video is exported, and frames are taken from it for an independent reviewer to check, and Claude looks at them itself before judging. Then the handoff and the publishing caption are written, as for any reel. The results are in `output/projects/EP01_R03_MO/`:

| Location | What is in it |
| --- | --- |
| `04_after_effects/project/` | The After Effects project (an `.aep` file). |
| `04_after_effects/render/` | The exported video; its name ends in `_motion.mp4`. |
| `08_quality_control/ae_frames/` | The QC frames from After Effects. |
| `09_handoff/README.md` | The handoff file. |

In the “Needs you” list you will usually find: fonts to install, restarting After Effects, the music, numbers to confirm, and the final look and export. And Claude will not tell you the motion video is “ready” unless QC passed in the same message.
