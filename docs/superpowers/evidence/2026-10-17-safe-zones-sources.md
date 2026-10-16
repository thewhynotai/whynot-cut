<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- © 2026 The Why Not AI (thewhynot.ai) -->

# Safe-zone profiles: where every number comes from (Phase 4 Task 27, R-4.5)

Read on **2026-10-17** by the API-credit lane. File: `whynot-cut/config/defaults/safe-zones.json`. Basis order:
official → template → screenshot → community (last resort, flagged in the file and in the QC line). Quotes are at most
15 words. No screenshot of a third-party UI is stored in the repo; the TikTok template images were opened only to
measure them and live outside the repo.

**Honest summary:** the platforms publish most safe zones only as pictures or downloadable templates. What a page
states as text is `official`; what we measured from a platform's own template is `template`; where we could read neither,
the number is `community` (a third-party reading of the platform's figure) and is flagged. Yunus can replace every
community number with a measured one (see "Open items").

## Instagram Reels, ads — `ig_reels_ads` (official)
| Number (1080×1920) | Value | Source | Quote / method |
|---|---|---|---|
| top band | 14 % = 268.8 → 269 px | https://www.facebook.com/business/ads-guide/update/image/instagram-reels (and `/video/instagram-reels`) | Arabic page, read 2026-10-17: «14% … 35% … 6% في كل جانب» |
| bottom band | 35 % = 672 px → starts y = 1248 | same | same sentence |
| left / right margin | 6 % = 64.8 → 65 px | same | same sentence |

Rounding is toward safety (zones grow). The action rail has **no published number**: it is not guessed.

## Instagram Reels, organic — `ig_reels_organic`
Meta publishes no organic figure. The ads numbers above are reused as the closest official numbers; every zone note
says «Ads figure reused for organic». The right-hand action rail (like / comment / share) has **no published number and
we did not guess one**: the profile carries it as an explicit gap (`gaps`), which the QC line prints, so a clean result
never silently claims the rail was checked. Needs Yunus: an in-app screenshot of an organic Reel to measure the rail
(see "Open items"). The same gap is stated on the two ads profiles.

## Instagram Reels, ads with disclaimer — `ig_reels_ads_disclaimer` (bottom band: community)
| Number | Value | Source | Quote / method |
|---|---|---|---|
| bottom band | 40 % = 768 px → starts y = 1152 | `source` = https://www.solidlabs.com/social-safe-zones (where we actually read it) | Origin: Meta help article https://www.facebook.com/business/help/980593475366490/ (its title only loaded for us). The third-party page quotes it: «you should leave the bottom 40% of your ad free from text». **Re-verify by hand.** Other three sides: as `ig_reels_ads`. |

## TikTok — `tiktok` (template, measured by us)
Source page: https://ads.tiktok.com/resources/help/article/tiktok-reservation-in-feed-ads-reach-frequency?lang=en
(official in-feed specs page listing the safe-zone template files). Used for organic TikTok too: no organic template is published. Method: the page's own
downloadable «In-Feed — Standard Version LTR» zip (folder «1. Vertical Feed- 540x960», images feed1.png … feed_4.png;
and the RTL zip's feed_1_RTL.png), whose images carry the platform's own labelled dimension arrows (126, 60, 120, 760
and 406/507). Each label was read from the image; the arrow ends were checked against the green safe area on a 750×1334
render of the 540×960 frame (e.g. green top at 176 px × 960/1334 = 127 ≈ 126; right block end at 278 px → 200). Values at
540×960, doubled to 1080×1920 (images kept outside the repo, in the lane's work folder):
| Number | At 540×960 | At 1080×1920 |
|---|---|---|
| top block | 126 | 252 |
| left margin | 60 | 120 |
| right margin beside the top block (height 200 → 400) | 60 | 120 |
| right action rail (below that) | 120 | 240 (x ≥ 840) |
| bottom, one line of ad copy / four lines | 406 / 507 | 812 / 1014 (the four-line case y = 906 is used, for safety) |
The page itself says the standard (left-to-right) version applies everywhere except the Arabic region; the «In-Feed —
Arabic Version RTL» template mirrors the layout, which `load(..., rtl=True)` applies to TikTok.
Encode: the same page says non-Spark videos need a bitrate of at least 2,500 kbps and mp4/mov (`official`). It gives
no GOP, level or loudness number: those stay absent.

## YouTube Shorts — `yt_shorts` (community, flagged)
Google's page https://support.google.com/google-ads/answer/9128498?hl=en shows the safe zone for a 1080×1920 frame only
as an image (the page text says: «within the red safe area»); we could not read numbers from it. The numbers come
from a third-party reading of Google's universal all-YouTube template, https://www.solidlabs.com/social-safe-zones :
15 % top (288 px), 35 % bottom (672 px), 4.4 % left (47.5 → 48 px), 17.8 % right (192.24 → 193 px, x ≥ 887; rounded up, as every zone is). The Shorts-only template is smaller
(10 % top, 25 % bottom, 10 % right); the wider one is used for safety. **Re-verify with a screenshot or Google's overlay.**
The page https://support.google.com/youtube/answer/10059070?hl=en states no safe-zone, codec or loudness number.

## 4:5 feed — `feed_4x5` (community, flagged)
No platform publishes a 4:5 number. The side margin borrows the 6 % of the Reels ads guide; the page
https://www.facebook.com/business/ads-guide/update/video/instagram-feed states none. The feed UI sits outside the
video frame, so no top/bottom zone is claimed.

## Delivery-encode blocks
| Profile | Values | Source | Quote |
|---|---|---|---|
| ig_reels_organic | codec H.264 or HEVC, closed GOP, 4:2:0, 23–60 fps, AAC ≤ 48 kHz, 1–2 channels, MOV/MP4 | https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media | «HEVC or H264, progressive scan, closed GOP, 4:2:0 chroma subsampling.» · «23-60 FPS.» · «AAC, 48khz sample rate maximum, 1 or 2 channels» · «MOV or MP4 (MPEG-4 Part 14), no edit lists, moov atom at the front of the file.» (read 2026-10-17) |
| ig_reels_ads, ig_reels_ads_disclaimer | H.264, AAC ≥ 128 kbps, MP4/MOV | https://www.facebook.com/business/ads-guide/update/video/instagram-reels | Arabic page, read in Arabic and translated: «نوع الملف: MP4، MOV» (file type MP4, MOV), «فيديو مضغوط بتنسيق H.264» (video compressed as H.264), AAC stereo at 128 kbps or higher |
| tiktok | bitrate ≥ 2,500 kbps, MP4/MOV | TikTok in-feed page above | the page's spec lines (as summarised on reading 2026-10-17): non-Spark videos «bitrate ≥2,500kbps»; Spark Ads Pull «normally .mp4 or .mov» |
No platform page we read publishes a GOP length, an H.264 profile/level or a loudness target, so those keys are absent
and `encode_findings` never checks them (the tests use a fixture profile with made-up limits).

## Open items (Yunus, optional)
1. Replace the community numbers (YouTube Shorts, the 40 % disclaimer band, the 4:5 sides, the organic IG rail) with a
   measurement: one screenshot per platform taken on your phone and account, kept outside the repo.
2. Re-verify everything at each minor release.
