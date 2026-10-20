# shellcheck shell=bash
# Shared scaffold for the WhyNot Cut eval cases (3.0 T3.7). Each case's scaffold.sh sources this file and calls the
# functions it needs. `claude plugin eval --scaffold` runs `bash <case>/scaffold.sh` with the run's empty working
# directory as cwd, HOME/USERPROFILE/TMP pointing into the eval sandbox and only PATH inherited; it is killed after
# 120 s. Everything here is FICTIONAL (the Example Clinic, Dr. Sample Example, EP12): never real client data.
#
# The clips are generated with ffmpeg (testsrc + sine, 3 s, 270x480): `ffmpeg` on PATH, else the first `ffmpeg*`
# binary in a PATH folder (e.g. the engine runtime's imageio_ffmpeg/binaries folder put on PATH by the operator).
# This folder holds no prompt.md / case.yaml, so the eval runner never treats it as a case.
set -eu

EVAL_FIXTURES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVAL_PLUGIN="$(cd "$EVAL_FIXTURES/../.." && pwd)"
_EVAL_CLIP=""            # the one generated clip; every other clip is a copy of it

die() { echo "scaffold: $*" >&2; exit 1; }

find_ffmpeg() {
  local d f
  if command -v ffmpeg >/dev/null 2>&1; then command -v ffmpeg; return 0; fi
  local IFS=:
  for d in $PATH; do
    for f in "$d"/ffmpeg*; do
      case "$f" in *.dll|*.txt|*.md) continue ;; esac
      if [ -f "$f" ] && [ -x "$f" ]; then echo "$f"; return 0; fi
    done
  done
  return 1
}

# make_clip <out file>: a 3-second 270x480 test clip with a 440 Hz tone (generated once, then copied)
make_clip() {
  local out="$1" ff
  mkdir -p "$(dirname "$out")"
  if [ -n "$_EVAL_CLIP" ] && [ -f "$_EVAL_CLIP" ]; then cp "$_EVAL_CLIP" "$out"; return 0; fi
  ff="$(find_ffmpeg)" || die "ffmpeg not found on PATH: put the folder that holds ffmpeg on PATH before running the eval"
  "$ff" -hide_banner -loglevel error -y -f lavfi -i "testsrc=size=270x480:rate=25:duration=3" \
    -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=3" \
    -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$out" 2>/dev/null \
  || "$ff" -hide_banner -loglevel error -y -f lavfi -i "testsrc=size=270x480:rate=25:duration=3" \
    -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=3" \
    -c:v mpeg4 -c:a aac -shortest "$out" \
  || die "ffmpeg could not write $out"
  _EVAL_CLIP="$out"
}

# make_still <out file>: one 270x480 test frame (PNG or JPG by extension)
make_still() {
  local ff
  mkdir -p "$(dirname "$1")"
  ff="$(find_ffmpeg)" || die "ffmpeg not found on PATH"
  "$ff" -hide_banner -loglevel error -y -f lavfi -i "testsrc=size=270x480:rate=1:duration=1" -frames:v 1 "$1" \
    || die "ffmpeg could not write $1"
}

# make_clinic [dir] [profile|no-profile]: the fictional client folder (default ./example-clinic, with its profile)
#   assets/  logo, brand brief, a font note      data/Raw/C0238.MP4 C0239.MP4 C0240.MP4
#   data/Episodes/EP12.mp4 + EP12.md (episode sheet)   .whynot-client marker
#   output/client_database/reel-profile/ = the shipped example-clinic profile (unless no-profile)
make_clinic() {
  local dir="${1:-example-clinic}" prof="${2:-profile}" c
  mkdir -p "$dir/assets/fonts" "$dir/data/Raw" "$dir/data/Episodes"
  printf '{"whynot_client": 1, "created": "2026-10-13T09:00:00+0300"}\n' > "$dir/.whynot-client"
  cat > "$dir/assets/logo.svg" <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60"><rect width="200" height="60" fill="#0E6E6E"/><text x="12" y="38" font-size="22" fill="#FFFFFF">Example Clinic</text></svg>
EOF
  cat > "$dir/assets/brand-brief.md" <<'EOF'
# Example Clinic — brand brief (fictional)
- Colours: teal #0E6E6E, sand #F2E6D0, white #FFFFFF
- Fonts: "Example Sans" for English, "Example Naskh" for Arabic (files not supplied yet)
- Doctor on camera: Dr. Sample Example (dermatology and laser)
- Tone: calm, clear, no hype; every health claim keeps its qualifier
EOF
  printf 'The font files were not delivered yet. Ask the client for Example Sans and Example Naskh.\n' \
    > "$dir/assets/fonts/README.txt"
  for c in C0238 C0239 C0240; do make_clip "$dir/data/Raw/$c.MP4"; done
  make_clip "$dir/data/Episodes/EP12.mp4"
  cat > "$dir/data/Episodes/EP12.md" <<'EOF'
---
show: Example Clinic Talks
episode: 12
title: Laser myths, one by one
host: Nour Placeholder
guest: Dr. Sample Example
guest_instagram: "@example.clinic.demo"
links: [https://example.com/clinic]
avoid: [prices, competitor names]
---
Fictional episode sheet for the WhyNot Cut evals. No sponsor for this episode.
EOF
  if [ "$prof" = "profile" ]; then
    mkdir -p "$dir/output/client_database/reel-profile"
    cp "$EVAL_PLUGIN"/profiles/example-clinic/*.json "$dir/output/client_database/reel-profile/"
  fi
}

# add_references <client dir>: two fictional reference edits the client likes
add_references() {
  make_clip "$1/data/References/ref-01-clinic-reel.mp4"
  make_clip "$1/data/References/ref-02-clinic-reel.mp4"
}

# add_project <client dir> <id>: a clip project that reached the plan (transcript, plan, reviews), not built yet
add_project() {
  local p="$1/output/projects/$2"
  mkdir -p "$p/01_analysis" "$p/02_transcription" "$p/08_quality_control"
  cat > "$p/02_transcription/subtitle-review.md" <<'EOF'
# Subtitle review — words to confirm by ear (fictional)
| time | heard | proposed | why |
|---|---|---|---|
| 00:00:12.4 | ميتفورمين | ميتفورمين (Metformin) | medical term, low confidence |
| 00:00:21.0 | اتش بي ايه وان سي | HbA1c | Latin term written in Arabic script |
| 00:00:27.8 | فراكشنال | Fractional (laser) | split word in the audio |
Not verified by the editor yet (no `transcript-verify` record).
EOF
  cat > "$p/01_analysis/medical-content-review.md" <<'EOF'
# Sensitive on-screen content — review (fictional)
| graphic | on-screen text | kind | needs | status |
|---|---|---|---|---|
| G03 | Laser can reduce acne scars in 3–5 sessions | medical claim with a number | the doctor's sign-off | approval_required, pending |
| G05 | «خير الأمور أوسطها» shown as a hadith | religious attribution | the speaker's sign-off on the attribution | approval_required, pending |
| G07 | Drink water every day | general advice | none | ok |
EOF
  # the compiled plan the editor approves (format of `reel plan`'s edit-plan.md); without it an approval had nothing
  # to match and the agent rightly doubted it (3.0 G3 evals)
  cat > "$p/01_analysis/edit-plan.md" <<'EOF'
# Edit Plan — C0238 (for editor approval)

Runtime 00:00:41:12 at 24 fps · 3 graphics · 1 camera moves (+2 automatic jump-cut zooms) · 2 SFX cues · speaker covered 9% · 2 items need content approval

Times are on the reel's timeline (after pause removal and word cuts).

Framing: fill

## Decisions

| # | Time | Treatment | On-screen text | Why (speaker's words) | Approval |
|---|---|---|---|---|---|
| G03 | 00:00:08:04 | statement_bar | Laser can reduce acne scars in 3–5 sessions | «الليزر بيقلل آثار حب الشباب في تلات لخمس جلسات» | YES |
| G05 | 00:00:19:10 | quote_card | «خير الأمور أوسطها» | «زي ما بنقول خير الأمور أوسطها» | YES |
| G07 | 00:00:33:02 | +12% punch-in; checklist_item | Drink water every day | «اشرب مية كل يوم» |  |

## Not included (and why)

- (none recorded)

Music: NOT_PLACED

**To approve:** reply 'approved' (or list changes). Adobe builds wait for `reel approve-plan`.
EOF
}

# add_episode_plan <client dir>: EP12's reels plan (fictional candidates) waiting for the editor to pick the reels
add_episode_plan() {
  local p="$1/output/episodes/EP12/01_analysis"
  mkdir -p "$p"
  cat > "$p/reels-plan.md" <<'EOF'
# EP12 — reel candidates (fictional; pick the reels)
| id | score | type | in → out | hook | flags |
|---|---|---|---|---|---|
| R01 | 88 | bold opinion | 00:03:10 → 00:03:52 | "Most laser myths start in salons" | — |
| R02 | 84 | advice | 00:07:40 → 00:08:25 | "Three questions before any laser session" | — |
| R03 | 79 | storytelling | 00:12:05 → 00:12:58 | "The patient who came back after ten years" | — |
| R04 | 71 | comedy | 00:15:30 → 00:16:02 | "My mother still calls it the light machine" | — |
| R05 | 66 | advice | 00:19:12 → 00:19:50 | "Prices differ, safety should not" | avoid: prices |
EOF
  # the topic map the episode analysis writes next to the reels plan (episode-craft): also the YouTube chapters
  cat > "$p/topics.json" <<'EOF'
{"topics": [
  {"id": "T01", "start": "00:00:00.000", "end": "00:02:40.000", "title": "Welcome and the guest", "summary": "Fictional: the host introduces the guest and the episode."},
  {"id": "T02", "start": "00:02:40.000", "end": "00:06:30.000", "title": "Where laser myths start", "summary": "Fictional: why salon talk spreads myths."},
  {"id": "T03", "start": "00:06:30.000", "end": "00:11:20.000", "title": "Questions before a session", "summary": "Fictional: three questions to ask first."},
  {"id": "T04", "start": "00:11:20.000", "end": "00:15:00.000", "title": "A patient ten years later", "summary": "Fictional: a patient comes back with the same question."},
  {"id": "T05", "start": "00:15:00.000", "end": "00:18:40.000", "title": "The light machine at home", "summary": "Fictional: family names for the device."},
  {"id": "T06", "start": "00:18:40.000", "end": "00:22:30.000", "title": "Safety before anything else", "summary": "Fictional: closing advice on safety."}
]}
EOF
}

# add_approved_reels <client dir>: EP12's picked reels R01 and R02 with plans the editor approved in the chat
add_approved_reels() {
  local r
  add_episode_plan "$1"
  for r in R01 R02; do
    mkdir -p "$1/output/projects/EP12_$r/01_analysis"
    printf '{"approved": true, "via": "chat", "by": "editor", "at": "2026-10-12T17:10:00+03:00", "format": 3}\n' \
      > "$1/output/projects/EP12_$r/01_analysis/plan-approval.json"
  done
}

# add_panel_approval <client dir> <id>: the editor approved the plan in the Premiere panel; not built since
add_panel_approval() {
  local p="$1/output/projects/$2/01_analysis"
  mkdir -p "$p"
  printf '{"approved": true, "via": "panel", "by": "editor", "editor_name": "Mona", "at": "2026-10-13T08:30:00+03:00", "format": 3, "plan_fingerprint": "5d0c9a41e27b8f36"}\n' \
    > "$p/plan-approval.json"
}

# add_motion_project <client dir> <id>: a motion video (e.g. EP12_R03_MO) whose motion script exists: three scenes,
# the second one long (9 s), its icons in the amber theme (#E07A1F, not the client's teal)
add_motion_project() {
  local p="$1/output/projects/$2/01_analysis"
  mkdir -p "$p"
  cat > "$p/motion-script.json" <<'EOF'
{
  "schema_version": 1,
  "reel_id": "R03",
  "theme": "clinic-teal",
  "captions": "on",
  "beats": [{"id": "B1", "role": "hook"}, {"id": "B2", "role": "point"}, {"id": "B3", "role": "close"}],
  "scenes": [
    {"id": "S01", "type": "title_card", "at": "00:00.0", "beat": "B1", "title": "The patient who came back"},
    {"id": "S02", "type": "icon_point", "at": "00:04.0", "beat": "B2", "theme": "amber", "icon": "laser",
     "text": "Ten years later, the same question", "recipe_note": "icons in amber #E07A1F; scene runs 9 s"},
    {"id": "S03", "type": "outro", "at": "00:13.0", "beat": "B3", "cta": "Ask before any session"}
  ]
}
EOF
}

# make_hugo_site [dir]: a small Hugo website (no client layout: no data/, no marker) for the should-not-trigger case
make_hugo_site() {
  local dir="${1:-.}"
  mkdir -p "$dir/assets/scss" "$dir/assets/images" "$dir/content" "$dir/layouts"
  printf 'baseURL = "https://example.org/"\ntitle = "Example Portfolio"\n' > "$dir/hugo.toml"
  printf -- '---\ntitle: Home\n---\nWelcome to the example portfolio.\n' > "$dir/content/_index.md"
  printf '.hero { width: 100%%; height: 100vh; object-fit: cover; }\n' > "$dir/assets/scss/main.scss"
  printf '{{ $css := resources.Get "scss/main.scss" | toCSS }}<link rel="stylesheet" href="{{ $css.RelPermalink }}">\n<img class="hero" src="/images/hero.jpg">\n' \
    > "$dir/layouts/index.html"
  make_still "$dir/assets/images/hero.jpg"
}

# add_review_case <client dir> <id> <case dir>: a clip whose plan is compiled and waits for the content review (3.0
# Task 53 = Addendum M1-T5, the review-domain evals). Copies the case's own plant/ folder, never the answer:
#   timeline-spec.json, edit-plan.md, review-scan.json (the engine's review-scan of that plan) -> <id>/01_analysis/
#   transcript.md -> <id>/02_transcription/        profile.json (optional: another domain or review_domains) ->
#   output/client_database/reel-profile/ (replaces the client's profile.json)
#   asset-manifest.json (optional) -> output/client_database/        stills.txt (optional): client-relative image
#   paths, one per line, each made with make_still (the files the plan and the manifest name)
add_review_case() {
  local c="$1" id="$2" src="$3/plant" p f
  [ -d "$src" ] || die "add_review_case: no plant/ folder in $3"
  p="$c/output/projects/$id"
  mkdir -p "$p/01_analysis" "$p/02_transcription" "$p/08_quality_control"
  for f in timeline-spec.json edit-plan.md review-scan.json; do
    [ -f "$src/$f" ] || die "add_review_case: $src/$f is missing"
    cp "$src/$f" "$p/01_analysis/$f"
  done
  if [ -f "$src/transcript.md" ]; then cp "$src/transcript.md" "$p/02_transcription/transcript.md"; fi
  if [ -f "$src/profile.json" ]; then
    mkdir -p "$c/output/client_database/reel-profile"
    cp "$src/profile.json" "$c/output/client_database/reel-profile/profile.json"
  fi
  if [ -f "$src/asset-manifest.json" ]; then
    mkdir -p "$c/output/client_database"
    cp "$src/asset-manifest.json" "$c/output/client_database/asset-manifest.json"
  fi
  if [ -f "$src/stills.txt" ]; then
    while IFS= read -r f || [ -n "$f" ]; do
      f="${f%$'\r'}"
      if [ -n "$f" ]; then make_still "$c/$f"; fi
    done < "$src/stills.txt"
  fi
  return 0
}
