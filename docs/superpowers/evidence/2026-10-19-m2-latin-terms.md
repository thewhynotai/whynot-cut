<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- © 2026 The Why Not AI (thewhynot.ai) -->

# M2-T3: Whisper and English terms in Latin letters, three approaches measured (Phase 4 Task 55)

Measured on **2026-10-19** by Builder A on the owner's PC: Lenovo LOQ, i7-14700HX, 32 GB, **RTX 4060 Laptop 8 GB**
(driver 617.42), Windows 11. Engine: the release/3.0 working tree at HEAD e95a4a5; the decoder files it imports
(`whisper_backends.py`, `episode.py`, `transcribe.py`, `wer.py`, `common.py`) were unmodified there and are unchanged up
to 9f411f0. faster-whisper 1.2.1 / CTranslate2 4.8.2, model **large-v3** (Systran CT2), **float16 on CUDA** (the shipped
precision, G13), `HF_HUB_OFFLINE=1`. Every GPU run went through `heavy.sh gpu` (one job, 01:35–01:45); the machine was
shared with other sessions' test suites, which moves speed, not text. Premiere and After Effects were not used.

**Not verified on mixed speech.** The spec's set is 3–5 real mixed clips with 25–50 % English words (M7 HM-1); they are
not in `whynot-test` yet. Everything below is EP02 only: a doctor speaking Egyptian Arabic about faith, with a short run
of English medical words and some English words in passing (about 1 % of the words).

**Labels: NOT verified by ear** (executor ruling Q55-1). See "Labels" below; the uncertain ones are one listening item
for the editor (about 15 minutes) in the live PODCAST-TEST checklist.

## How it was measured
- **Harness outside the repo** (`D:\ClaudeData\claude-api-lane\lane4\work\task55\harness.py`). It imports the engine's
  own decoder (`whisper_backends.make_runner`, `episode.plan_chunks`/`stitch`) and passes the prompt and the language in
  from outside, so no engine file was edited to measure. Raw rows: `rows.jsonl` and `runs/*.json` in the same folder;
  the table is `analyse.py` → `analysis.json` / `table.md`.
- **Sets** (test copies only, read only):
  - **R02**: the R02 window 125.15–179.45 s of `Dr Sherin Helmy/data/Raw/EP02.mp4` (54.3 s, the R02 project's 16 kHz
    wav), decoded as `reel transcribe` decodes a clip under 10 minutes: one pass, no VAD, sequential;
  - **EP02**: the whole episode (34:41), decoded as `reel episode-transcribe` does: ~10-minute chunks cut in silence,
    VAD, batched (the VRAM fit chose batch 3), language detected on chunk 1 and reused.
- **Approaches:**
  - **today (base)**: today's prompt, built exactly as `transcribe()` builds it (client hint + R02's
    `vocabulary.txt`; the harness asserts it equals the prompt recorded in the R02 machine transcript), language auto;
  - **1, mixed prompt**: today's prompt + the Latin forms of `config/defaults/latin-terms.json` for the client's review
    domains (ai, medical, religious: `insulin، vitamin، cholesterol، ChatGPT، GPT، AI`) + the glossary's `english` list
    (empty), appended the way the video vocabulary is appended;
  - **2, per-chunk language**: today's output, then Whisper's language detection on every 30 s window; a window detected
    English with p ≥ 0.5 is decoded again with `language="en"` and its words replace today's there;
  - **3, back-map**: `lib/latin_backmap.py` on today's words (CPU), its proposals applied *virtually* (as if the editor
    accepted every one) to measure what it can reach. The product never applies them.
- **Columns:**
  - Latin-script accuracy: a labelled English occurrence counts when a decoded word overlapping its time (± 150 ms) has
    Latin letters; n and a 95 % Wilson interval;
  - Arabic diff vs today: `lib/wer.py` between today's words and the approach's words, on the Arabic part only (words
    with no Latin letter that overlap no labelled or uncertain occurrence); edits = substitutions + deletions +
    insertions, rate = edits / today's tokens;
  - WER / CER vs corrected (R02 only, informational): against the R02 project's `words.json`, machine words with
    editor-side corrections, never verified by ear (the G13 "vs corrected" reference); not used by the rules;
  - prompt-term insertions: an output word equal to a mixed-prompt term (Latin, or its pair-list Arabic spelling) at no
    labelled occurrence of it; for approach 3, a proposal at no labelled occurrence;
  - RTF = audio seconds / decode seconds (model load excluded), median of the runs.
- **Determinism:** every repeated run gave the same text (R02: 3 runs each; EP02: today and approach 1 twice each).

## Results

### R02 (54.3 s; 1 labelled English occurrence, 1 uncertain)
| Approach | Latin-script accuracy (k/n, 95 % CI) | Arabic diff vs today (edits/n, rate, CER) | WER / CER vs corrected | Insertions | RTF (median, runs) | Model / backend / precision |
|---|---|---|---|---|---|---|
| today | 0/1 = 0 % (0–79 %) | 0/89, 0.0 %, 0.0 % | 10.1 % / 4.1 % | 0 | 8.82 (3) | large-v3 / faster-whisper / cuda float16, sequential |
| 1 mixed prompt | 0/1 = 0 % (0–79 %) | 1/89, **1.1 %**, 0.3 % | 9.0 % / 3.9 % | 0 | 9.31 (3) | same |
| 2 per-chunk language | 0/1 = 0 % (0–79 %) | 0/89, 0.0 %, 0.0 % | 10.1 % / 4.1 % | 0 | 7.39 (3) | same + 0.51 s detection |
| 3 back-map | 0/1 = 0 % (0–79 %) | 0/89, 0.0 %, 0.0 % | 10.1 % / 4.1 % | 0 | 8.82 (3) | same + 0.5 ms (CPU) |

### EP02 (34:41; 24 labelled English occurrences, 17 uncertain)
| Approach | Latin-script accuracy (k/n, 95 % CI) | Arabic diff vs today (edits/n, rate, CER) | Insertions | RTF (median, runs) | Model / backend / precision |
|---|---|---|---|---|---|
| today | 2/24 = 8.3 % (2.3–25.8 %) | 0/3776, 0.0 %, 0.0 % | 0 | 15.44 (2) | large-v3 / faster-whisper / cuda float16, batch 3, VAD |
| 1 mixed prompt | 4/24 = 16.7 % (6.7–35.9 %) | 147/3776, **3.9 %**, 2.0 % | 0 | 17.07 (2) | same |
| 2 per-chunk language | 2/24 = 8.3 % (2.3–25.8 %) | 0/3776, 0.0 %, 0.0 % | 0 | 13.66 (1) | same + 18.5 s detection |
| 3 back-map | 2/24 = 8.3 % (2.3–25.8 %) | 0/3776, 0.0 %, 0.0 % | 0 | 15.44 (2) | same + 56 ms (CPU) |

What each approach did:
- **1, mixed prompt:** wrote «manual», «insulin» (the only prompt term spoken), «background» and «overtime» in Latin,
  and «regulation» before «تنظيم» at 15:20 where today's output has no such word (not a prompt term; said or
  invented is an uncertain item for the editor). It also changed 147 Arabic tokens across the episode: for example
  «لازم تسلي، لازم يلي منحك» → «لازم تصلي، عشان ليه منحك», «نعم، نعم» dropped, «القسبة» → «القصبة», and an extra
  «لأنه مرأة واحدة» after a recited verse at 3:38. Without an editor-verified reference nobody can say whether these
  are better or worse; on R02 its one change («معاه» → «معاها») matches the corrected transcript.
- **2, per-chunk language:** no window of either set is mostly English (the highest English probability is 0.072 on
  EP02, 0.004 on R02; Arabic ≥ 0.81 everywhere), so nothing was decoded again and the text is today's. It adds the
  detection time (0.51 s per 54 s, 18.5 s per 35 min, about 12–14 % of the decode). Its RTF uses today's first decode
  (the slowest, first-run one) plus the detection; the detection time is the real added cost.
- **3, back-map:** no proposal on either set. The one pair-list word spoken, «إنسولين» at 16:17 (p = 0.74), was
  skipped as `no_context`: its 3 neighbours on each side («العسارة المعادية، يطلع» / «فأنت بترهق الجسم») hold no
  English word, no medical-lexicon word and no other listed term; the English run «كربوهايدريت … جاستريك جيوس» ends 5
  words earlier. The other English words of EP02 (manual, frame, standard, carbohydrate …) are not in our lexicons, so
  they are not in the pair list (Q55-2: our own lists only). No false proposal, no Arabic change by construction.

## Decision (rules as the task states them, not tuned after measuring)
1. **Insertions > 0 block:** none of the four inserted a prompt term (0 everywhere).
2. **An Arabic diff > 0.5 pp blocks:** **approach 1 is blocked** (3.9 % on EP02, 1.1 % on R02).
3. **Quality first, then speed**, among today, 2 and 3: the same Latin-script accuracy (8.3 % on EP02, 0 % on R02),
   no Arabic change; 3 costs about nothing, 2 costs 12–14 % more decode time for no gain.

**Kept: approach 3, the back-map, as proposals only.** It is the only approach that passes the rules and can never
lower Arabic accuracy (nothing is applied without the editor), and it costs milliseconds. **Today's decoding stays as
it is**: no mixed-prompt change and no per-chunk language in `transcribe.py`, `whisper_backends.py` or `episode.py`.
How it lands: `lib/latin_backmap.py`, `config/defaults/latin-terms.json` and `tests/test_latin_backmap.py` (Task 55);
the call from `transcribe.finalize` (every clip, long clip, episode and `transcript-correct`: it writes
`02_transcription/latin-proposals.json` and a "Latin term proposals" section in `subtitle-review.md`) is the executor's
patch `m2t3-transcribe.patch`; until it lands nothing calls the back-map. A client who keeps English terms in Arabic
letters sets `latin_backmap: false` in profile.json (executor ruling Q55-3).

**The target is NOT met.** Latin-script accuracy ≥ 95 % is not reached by any approach on EP02 (best unblocked: 8.3 %,
n = 24, 95 % CI 2.3–25.8 %; the blocked mixed prompt: 16.7 %). On this audio the limit is not the decoder but the pair
list: the English words the doctor said are mostly not in our review lexicons. Gate 4 cannot claim M2-T3's target from
this evidence; what it can claim is: measured, the best non-regressing approach kept, the gap and its cause named.

## Labels (source and limits)
- Built by agreement, **not verified by ear** (Q55-1): an occurrence is English when any decoder wrote it in Latin
  letters, or when today's output writes a code-switched English word in Arabic letters (read from the transcripts,
  not heard). Established Arabic loanwords (تلفزيون، تاكسي، موبايل، سينما، كيلومتر، دولار، تريليونات) are not
  labelled. Names (نادال، جيكوفيتش) are never English terms here.
- **Uncertain (17, excluded from the accuracy and from the Arabic part):** tennis «تينيس», dish, matches/match, baby ×4,
  ego «إيجوا», catalogue ×4 «كتالوج», protein «بروتين», enzymes «الإنزيمات», system «السيستامة», and «regulation»
  (heard by approach 1 only). The editor's listening item lists each with its time.
- Labels file: `labels.json` in the work folder. A different labelling moves the accuracy numbers; it cannot move
  the decision, which the Arabic-diff rule and the zero proposals settle.

## Not verified
- Mixed speech (HM-1 clips not dropped yet): "Not verified on mixed speech".
- The labels by ear (the PODCAST-TEST listening item).
- Whether approach 1's 147 Arabic changes are better or worse (no editor-verified reference exists, G13).
- The back-map's precision on real proposals: on EP02 it made none, so its rules are proven by unit tests and
  mutation only (`tests/test_latin_backmap.py`), not by a live proposal.
- macOS / MLX: not run (the back-map is pure Python and platform-free; the decoder rows are CUDA only).

## Follow-ups
- Grow the pair list the only allowed way: add the English medical terms seen here (carbohydrate, protein, enzyme,
  gastric juice, saliva …) with their Arabic spellings to `config/review-domains/lexicons/medical.json` first (they
  then also trigger medical review, which is a separate decision), then to `latin-terms.json`.
- Re-measure on the HM-1 mixed clips when they arrive (same harness, `harness.py`), including the context window
  (3 words) against real proposals; never tune it on the single EP02 case.
- Revisit approach 1 only with an editor-verified reference clip: its Arabic changes may be improvements, but the rule
  cannot tell without one.
