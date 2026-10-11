---
type: llm
weight: 1
---

Pass if the response uses the publish-writer / publish-craft flow: it writes publish/publish.json and publish/reels/<REEL>.json, takes names, the guest's Instagram and the sponsor ONLY from the episode sheet (data/Episodes/EP12.md → 00_inputs/episode.json), says plainly if a requested link is not in the sheet instead of inventing it, uses the topic map for chapters (first at 00:00), runs `reel publish-check` until it passes, and does not post or upload anything. Fail if it invents a link, handle, sponsor or quote, skips publish-check, or claims the copy was published.
