<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- © 2026 The Why Not AI (thewhynot.ai) -->

# Cut proposals v2 (Phase 4 Task 25, R-4.3): precision and recall per kind

| | |
|---|---|
| Date | 2026-10-17 |
| Engine | `whynot-cut/engine/reel/lib/cut_proposals.py` (`compute`, starting values of `DEFAULTS`) |
| Fixtures | `whynot-cut/tests/fixtures/cut_proposals/*.json`: made-up transcripts, no client speech |
| Target (R-4.3 acceptance) | retake precision ≥ 0.8, filler precision ≥ 0.9; laughter, «اه», «إيه», «امم» (unstretched) and the sign-off never proposed |
| Test that holds it | `tests/test_cut_proposals.py::TestAcceptance::test_precision_targets_and_no_trap_on_the_labelled_fixtures` (runs over every fixture, the blind set included) |

## How it is counted
- A **label** is what an editor removes: R retake (every word of the worse take), S false start, F filler, W the first
  copy of a doubled word, and `-` a trap that must never be proposed.
- Only proposals whose default is `proposed` count. A `keep` proposal (low confidence, a soft «اه», a take holding a
  number) is shown to the editor unticked and is not counted as a cut.
- A proposal is correct (tp) when any of its words carries the label of its kind; otherwise it is a false positive (fp).
- A labelled item (consecutive words with the same label) that no correct proposal touches is a miss (fn).
- A trap is any `proposed` proposal touching a `-` word.

## Set A: fixtures written with the rules (5 files: eg_doctor, eg_emphasis, en_talk, mixed, signoff)
The same lane wrote these and the rules, so this set shows that the rules do what they say, not how well they
generalise.

| kind | proposed | correct | missed | precision | recall |
|---|---|---|---|---|---|
| retake | 5 | 5 | 0 | 1.00 | 1.00 |
| false_start | 1 | 1 | 0 | 1.00 | 1.00 |
| filler | 11 | 11 | 0 | 1.00 | 1.00 |
| repeat_word | 2 | 2 | 0 | 1.00 | 1.00 |

Traps proposed: 0.

## Set B: a blind set (4 files: blind_b1_eg_clinic, blind_b2_eg_casual, blind_b3_en, blind_b4_mixed)
Written and labelled by a separate agent that read only the R-4.3 spec, never the code. It contains:
- Egyptian Arabic from a clinic and from a casual podcast, plus English and mixed Arabic/English;
- 4 retakes (one across a 1.5 s pause, two that differ by one word), 4 false starts, 12 fillers and 4 doubled words;
- traps: «اه» meaning yes, «إيه», «أمم» as "nations", laughter, emphasis repeats, an unstretched «يعني», «يعني» before a
  question, a number said twice on purpose, and a drug name.

**First run, before any change (the honest blind result):**

| kind | proposed | correct | missed | precision | recall |
|---|---|---|---|---|---|
| retake | 5 | 4 | 0 | 0.80 | 1.00 |
| false_start | 2 | 2 | 2 | 1.00 | 0.50 |
| filler | 12 | 12 | 0 | 1.00 | 1.00 |
| repeat_word | 4 | 4 | 0 | 1.00 | 1.00 |

Traps proposed: 1. It was a dose said twice on purpose ("is ten milligrams. Ten milligrams …"), proposed as a retake.

**Two rule changes made from that run.** Both are general rules, not fitted to the blind words:
1. A take that holds a number or a dose (K-T1's number reader; «واحد» meaning "someone" does not count) is never
   ticked. It is shown with confidence 0.5 and the reason «فيها رقم أو جرعة». A doctor who repeats a dose usually means
   to.
2. A fragment that is no word of its own and starts the next word («عاو» → «عاوز») is a false start even when it is not
   short or unsure. Arabic fragments may be one letter short; Latin ones need two. Common whole words that also start
   longer ones («كان»/«كانت», "the"/"there") are excluded.

**After the change (no longer blind):**

| kind | proposed | correct | missed | precision | recall |
|---|---|---|---|---|---|
| retake | 4 | 4 | 0 | 1.00 | 1.00 |
| false_start | 3 | 3 | 1 | 1.00 | 0.75 |
| filler | 12 | 12 | 0 | 1.00 | 1.00 |
| repeat_word | 4 | 4 | 0 | 1.00 | 1.00 |

Traps proposed: 0. The one miss left is "ri" → "reel": the fragment is not a spelling prefix of the restarted word. It
is accepted, because a looser rule would also call real short words false starts.

## Verdict against the target
- **Blind, before any change:** retake precision 0.80 (target ≥ 0.8), filler precision 1.00 (target ≥ 0.9), one trap.
- After the two general rule changes: 1.00 and 1.00, and no trap on either set.
- These are small samples: 4 blind retakes and 12 blind fillers. One more wrong retake would move blind retake
  precision below 0.8. R-4.3 sets no recall target; recall is shown for information.
- The review fix round (2026-10-17) left both tables unchanged:
  - snapping stays inside the neighbouring words;
  - retakes are within one speaker only;
  - the better take is judged on hesitation sounds only;
  - a take the transcript closed beats one that only stops at a pause;
  - a pause counts once.

## Not verified (live, editor)
- Labels from a real editor on a real clip (PODCAST-TEST and a medical client's reel): Gate 6 live check. These
  numbers come from made-up transcripts with synthetic timings, so they are not field precision.
- Every threshold keeps `basis: starting` in `config/defaults/cut-proposals.json`. A threshold moves to
  `measured: <fixture set>, <date>` only after a precision/recall run on editor-labelled clips.
- **Premiere markers:** `ppro_build` passes each proposal's marker, with its colour index and duration. The
  bridge JSX (`wnc_ppro_lib.jsx`, Adobe track) today sets only the marker's time, name and comment. Colour per kind and
  the marker's duration wait for that JSX change (routed to the Adobe track, with a UXP parity line). Until then the
  markers show in the right place with the kind in their name, but as points: a retake shows where it starts, not as
  a span. This part of R-4.3 ("colour per kind") stays open until the Adobe track lands it.
- An accepted proposal is cut as one range (`range_ms`, plan.py patch), never word by word. This is unit-tested; it
  has not been heard on a real render.
- Snapping cut points to the quietest 10 ms frame (`propose(..., samples, sr)`) is unit-tested on synthetic samples.
  `reel cut-proposals` passes `02_transcription/dialogue_16k_mono.wav` when it exists (cli.py patch). It has not been
  heard on a real cut yet.
