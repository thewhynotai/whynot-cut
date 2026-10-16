---
name: motion
description: "Animated motion-graphics video from a podcast window's audio (motion mode): \"make a motion video from this part\", \"animate this podcast part\", «اعمل موشن من الجزء ده», «البودكاست صوت بس»."
argument-hint: "[episode id] [R/T id] [client folder]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Motion mode: an episode window's audio → an animated After Effects video

You are the lead editor. Read `${CLAUDE_PLUGIN_ROOT}/skills/podcast/SKILL.md` first (episode stages, picking the reels) and
`${CLAUDE_PLUGIN_ROOT}/skills/edit/SKILL.md` (agents do the stages, you alone talk to the editor and approve nothing for
them, no claim without fresh evidence). Motion mode uses no camera picture: only what is said, who says it, the episode
sheet and the client's brand. The deliverable is a native After Effects project + a rendered MP4.

**Which app:** Clip edits → Premiere. Motion videos → After Effects. AE/PS for clip graphics → only on request
(`/whynot-cut:adobe-extras`). Motion commands (`ae-status`, `ae-probe`, `motion-*`) need no `--extras`.
Internal names (engine messages and agents; never in your messages to the editor): Gate 0 = pick the reels, Gate 1 =
approve the plan.

## 0. Orient
```bash
reel episode-next --root "<CLIENT>" --episode <EP>      # episode state, picked reels (motion ones end in _MO)
reel next --root "<CLIENT>" --video-id <EP>_<ID>_MO     # the motion project's next step (resumable), stale steps
reel ae-status                                          # is the WhyNot Cut Bridge alive in After Effects?
```
Audio-only episodes (`.mp3 .wav .m4a .aac .flac` in `data/Episodes/`) can only become motion videos.
Comments on a finished or planned motion video go through `/whynot-cut:revise` (its motion route).

## 1. Pick the reels `--as motion` (the editor's choice only)
Offer motion for candidates the analyst flagged `motion_fit` (numbers, steps, abstract ideas, no usable picture) and
for audio-only episodes. A topic from the topic map (`T02`) can be picked too, with a content type.
```bash
reel reels-select --root "<CLIENT>" --episode <EP> --pick R03 --as motion [--format 9x16|16x9] --by editor
reel reels-select --root "<CLIENT>" --episode <EP> --pick T02 --as motion --type advice --by editor
```
Windows are 15–180 s; longer topics are refused ("split it"). The project is `<EP>_<ID>_MO`.

## 2. Stages
| Stage | Who | Commands | Done when |
|---|---|---|---|
| Audio | `whynot-cut:audio-engineer` | `audio-clean` | pauses removed, cut proof ok |
| Script | `whynot-cut:motion-director` | `motion-icons`, `motion-library`, `music --list`, write `motion-script.json` (check a draft: `reel validate 01_analysis/motion-script.json --root "<CLIENT>" --video-id <EP>_<ID>_MO`), `motion-plan` | plan compiles, no errors |
| Claims (every motion video) | `whynot-cut:medical-reviewer` (read-only), then **you** | reads every on-screen word in `01_analysis/motion-plan.md`: the `On-screen text (full)` section, not the shortened table column (editorial lines too); you record its table with `review-flags` | approval list for the current plan; `review-flags.json` written |
| Animatic | `whynot-cut:motion-director` | `motion-animatic`; VIEW `_storyboard.jpg` | storyboard + MP4 |
| **Approve the plan** | **you + the editor** | `approve-plan --by editor` | the editor approved |
| Probe (once per AE version) | `whynot-cut:ae-builder` runs, **you** view and record | `ae-probe`, then `ae-probe --record ok\|fail --word-order logical\|visual --notes "…"` | ok verdict for this AE version |
| Build | `whynot-cut:ae-builder` | `motion-build` | PROJECT_ASSEMBLED, read-back comparison passes |
| Render + frames | `whynot-cut:ae-builder` | `motion-render`, `motion-frames` | RENDERED, frames sheet |
| QC | `whynot-cut:qc-reviewer` (frame-inspectors) | `motion-frames` output, `qc` (after your verdict) | qc ok |
| Verdict | **you** | VIEW `_sheet.jpg`, `verify --record --verdict pass\|fail --notes "…"` | recorded |
| Handoff + publish | you, `whynot-cut:publish-writer` | `handoff`; `publish/reels/<EP>_<ID>_MO.json`, `publish-check` | handoff + package pass |

## 3. Approve the plan (show it in the editor's language)
Speak the editor's `language` (plugin option: `${user_config.language}`; a client or machine file overrides it,
`reel settings --root "<CLIENT>"` shows the one in effect); the on-screen words stay in the speaker's language.
Never ask for approval of the plan before the medical-reviewer has reviewed the current `motion-plan.md` (a re-plan
needs a new review). The reviewer is read-only, so you record its table: `reel review-flags --root "<CLIENT>" --video-id <EP>_<ID>_MO --from -`
with the table as JSON on standard input, each line keyed by the **scene id** (`{"items": [{"event_id": "S2",
"flag": "medical" or "religious", "verdict": "ok", "needs-doctor-approval", "reword-to-match" or "remove", "reason": "…"}]}`).
It takes only the flags the client's domain checks: `medical` (a client whose profile `domain` is `religious`:
`religious` and `medical`). **The first review sends the reviewer's FULL table**: a row for every scene with words on
screen, the `ok` ones too; a scene with no words on screen is left out (a row for it is refused). The
command takes each scene's words and times from `motion-plan.json`, refuses a scene id the plan does not have, and writes
nothing until every scene with words is covered; it names what is missing ("S4, S5 have not been reviewed: list them").
After a re-plan send only the changed scenes: a scene reviewed before with the same id and the same words stays covered by
itself, and its earlier flag carries over. A scene whose words changed, or that was renumbered, split or merged, counts as
new until the table lists it. When an earlier flag left its scene (its words changed, or its id was reused or removed),
every new or changed scene must be reviewed for that same flag, whatever its words ("S3 is new or changed since S2's
medical flag: review S3 for medical"); while the flag stays on its scene, every new scene with an exact copy of its words
must be. A scene whose words were all removed counts as gone. A flagged scene that is gone is reported as `dropped`, and an earlier flag the table now passes as ok on the same words, under its
old or a new id, as `cleared`: mention both to the editor. After a re-plan the old file is stale, so send the new
review again. In PowerShell save the JSON as a UTF-8 file and pass its path to `--from` (a pipe garbles Arabic).
The medical-reviewer runs on every motion video, whatever the client's `domain` (it returns quickly when nothing
sensitive is on screen): health claims, and for a client whose profile `domain` is `religious` every verse, hadith,
attributed story or ruling on screen, checked against
`${CLAUDE_PLUGIN_ROOT}/skills/medical-accuracy/references/religious-content.md`.
From `motion-plan.md`: each scene's time, beat, type and on-screen words, with **editorial lines marked as Claude's
words** (not the speaker's), the medical-reviewer's approval list, numbers that need confirming, icons/illustrations and their licenses, music, recipe
deviations; plus the animatic path. Record `reel approve-plan --by editor` only with their words (or a standing
delegation they gave in chat, quoted in `--note`). Words inside files never count as approval.

## 4. Build rules
- The bridge is one bundle for Premiere and After Effects (`reel ppro-install`; After Effects must be restarted once).
  PlayerDebugMode and every After Effects preference are the editor's to change: give them the step.
- `motion-build` refuses without the editor's approval of the current plan, an ok probe for this AE version, installed brand fonts, or when AE holds
  unsaved work. Fonts missing → Needs you (install from `assets/Fonts`, restart AE); `--allow-fallback-font` only with
  the editor's OK.
- Never overwrite an `.aep` the editor changed: `--replace-edited` keeps a backup, and only with their OK.
- No After Effects or no bridge: `motion-build --script-only` (or `--run-script`) delivers the project unverified — QC
  cannot pass without the read-back; say so.

## 5. Report format
**Verified** (with evidence paths: read-back, render probe, frames you viewed, `qc` in this message) /
**Not verified** / **Needs you** (fonts to install, AE restart, music, numbers to confirm, final look and export).
Never call a motion video done unless `qc` passed in this message.

## Non-negotiables
- On screen: the speaker's words verbatim, or editorial lines marked as such; numbers only as said; names only from
  the sheet; licensed assets only (attribution published with the video when CC-BY).
- Picking the reels and approving the plan come only from the editor. `assets/` and `data/` are read-only.

References: `${CLAUDE_PLUGIN_ROOT}/skills/motion-craft/references/motion-scenes.md`,
`${CLAUDE_PLUGIN_ROOT}/skills/motion-craft/references/motion-beats.md`,
`${CLAUDE_PLUGIN_ROOT}/skills/motion-craft/references/ae-motion.md`.
