---
name: publish-craft
description: "This skill should be used when writing publishing copy for whynot-cut podcast mode — YouTube titles, description, chapters, tags and SRT for an episode; Instagram/TikTok captions, hashtags and YouTube Shorts titles for each reel; thumbnail designs — and checking it with reel publish-check. Knowledge for the publish-writer agent."
user-invocable: false
---

# Publish craft

Copy that is true, in the client's voice, and inside every platform's limits. The engine checks the limits, the links
and the quotes (`reel publish-check`); you make it worth reading.

## Files (output/episodes/<EP>/publish/)
**publish.json** (the episode):
```json
{"episode_id": "EP12", "language": "ar",
 "youtube": {
   "titles": ["…", "…", "…"],
   "description": {"hook": "<2 lines shown before 'more'>", "summary": "…", "guest": "<who, from the sheet>",
                   "links": [{"label": "Instagram", "url": "<from the sheet>"}], "sponsor": "", "cta": "…",
                   "hashtags": ["#…", "#…", "#…"]},
   "chapters": [],
   "tags": ["…"]},
 "thumbnail": {"designs": [{"frame_ms": 734000, "text": "<≤5 words>", "zoom": 1.35}]},
 "approval_required": []}
```
`chapters` empty → the topic map (`01_analysis/topics.json`) is used. Give `chapters` only to rename or merge topics:
`[{"at": "00:00", "title": "…"}]`.

**reels/<REEL>.json** (one per reel, after its plan is approved):
```json
{"reel_id": "EP12_R03",
 "instagram": {"caption": "…", "hashtags": ["#…"]},
 "tiktok": {"caption": "…", "hashtags": ["#…"]},
 "shorts": {"title": "…", "description": "…"},
 "approval_required": []}
```
Then `reel publish-check --root "<CLIENT>" --episode <EP>` → it writes `youtube.md`, `chapters.txt`, `tags.txt`,
`<EP>.srt` and `reels/<REEL>.md`. Limits: `references/platform-rules.md`.

## Writing
- **Titles** (3–5 options): the strongest promise the episode keeps; ≤ 60–70 characters reads fully on phones; the
  guest's name when it helps; no ALL CAPS, no fake urgency. Quote the speaker only exactly («…»).
- **Description**: two hook lines (what you'll learn/feel), a short summary, who the guest is (sheet), chapters,
  links (sheet only), sponsor (sheet only), one call to action, 3 hashtags.
- **Tags**: the topic words people search, the show name, the guest's name; no tag stuffing (500-character budget).
- **Reel captions**: the recipe's `copy` tone (00_inputs/source.json → recipe.copy): question for storytelling,
  the number for success stories, "N things" for advice, gentle for emotional. First line = hook. 3–8 hashtags.
- **Shorts title**: the hook in ≤ 60 characters.
- **Thumbnail text**: ≤ 5 words, the hook or the number, the speaker's meaning (never a claim they didn't make).
  Pick frames from `publish/thumbnail/_candidates.jpg`: clear face, expressive, eyes open.
- Dialect and emoji: follow the profile `notes.md`; the recipe says if emoji fit (comedy yes, emotional no).

## Never
- A link, name, title, sponsor or offer that isn't in the episode sheet.
- A quote that isn't verbatim, a number the speaker didn't say, a stronger claim than the speaker made.
- Medical/financial/legal/religious claims without an `approval_required` entry.
- Posting anything. The editor posts.
