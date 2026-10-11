# Platform rules checked by `reel publish-check`

The numbers live in `config/defaults/platform-limits.json` (a client profile may override them). Platforms change their
rules; update that file rather than the code. Last reviewed for WhyNot Cut 2.1 (October 2026).

## YouTube (episode)
| item | rule | engine |
|---|---|---|
| Titles | 1–100 characters; offer ≥ 3 options | error |
| Title length | > 70 characters gets cut in search and on phones | warning |
| `<` `>` | not allowed in titles or descriptions | error |
| Description | ≤ 5000 characters, assembled with chapters, links, sponsor, CTA, hashtags | error |
| Chapters | first at `00:00`, at least 3, ascending, each ≥ 10 s | error |
| Tags | ≤ 500 characters in total (commas count; a tag with a space counts its quotes) | error |
| Hashtags | ≤ 15 in the description (more and YouTube ignores them); `#word`, no spaces (use `_`) | error |
| SRT | the episode subtitles, valid timing | error |

## Reels
| platform | rule | engine |
|---|---|---|
| Instagram Reels | caption ≤ 2200 characters; ≤ 30 hashtags (caption + list) | error |
| TikTok | caption + hashtags ≤ 2200 characters | error |
| YouTube Shorts | title 1–100 characters, no `<` `>` | error |

## Facts
- Every URL anywhere in the copy must appear in the episode sheet (compared without scheme, `www.`, case or trailing
  punctuation). An invented link is an error.
- Every quote in «…», “…” or "…" must be found in the transcript (Arabic-normalised). A paraphrase in quotes is an error.
- `approval_required` items are listed in `youtube.md` and the reel files for the editor.

## Thumbnails (`reel publish-thumbnail`)
- 1280×720, ≤ 2 MB (PNG, else JPEG). Text ≤ 5 words reads at phone size (warning above).
- `--candidates`: frames with a face, scored on face size, sharpness and contrast, at least 30 s apart.
- `--render`: the face in one third, the text on the other side over a dark gradient (right side first for Arabic),
  the client's headline font, a brand-colour bar, the logo when the client database has one.
