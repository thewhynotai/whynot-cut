# M1-T5 (Task 53): review-domain evals — evidence, 2026-10-19

Scope (owner decision 2026-10-19 ~15:30, light tier): 3 positive + 1 negative case per domain, 16 cases, one eval run
of 3 runs per case. No verse text anywhere (owner decision 2026-10-18: the editor adds verses by hand).

## What the cases are
Each case is a flat folder `whynot-cut/evals/review-<domain>-<name>/` (`name:` = folder, `runs: 3`, Arabic prompt).
Its `scaffold.sh` builds the fictional client (`make_clinic`) and calls `add_review_case <client> <id> <case dir>`
(the fixture function, executor patch), which copies the case's `plant/` folder: a compiled 3-line plan
(`timeline-spec.json`, `edit-plan.md`), the engine's own review-scan of that plan (`review-scan.json`), a
transcript, and where needed a profile (a general, religious or business client) or an asset manifest with an
AI-generated still. The answer is never planted.

The eval has no shell (Q53-1 option C). The prompt allows `Write`, and the note asks the reviewer to write the exact
`reel review-flags --from` table to `<project>/review-input.json`. Graders (as of fix round 1, review 6275496):
- one `regex` per expected (event id, flag, verdict) tuple on the table LEFT ON DISK (`target: {source: file, path:
  <client>/output/projects/<id>/review-input.json}`, resolved in the run's sandbox cwd), anchored inside ONE row
  object. A later overwrite counts and an earlier Write does not. The run of record used `target: trace` (every Write
  in the trace), which let a correct first Write followed by a wrong overwrite pass (P2-2);
- one `not_contains` per case for a flag that must NOT be there, and one (`no-duplicate-rows`) for two rows on the
  same (line, flag), which `review_flags.write()` refuses ("listed twice");
- `no-gate-jargon`, one `llm` rubric (never the only counted decision, but it does count at the runner's
  threshold), and a record-only `skill-fired`.

| domain | + cases | − case |
|---|---|---|
| medical | dose-claim (500 mg on screen, 250 mg spoken), general-client (a `general` client's «بتعالج السكر نهائي»), cure-promise («علاج نهائي ١٠٠٪»: a medical AND a business row) | negative-clean |
| religious | hadith-attribution (a saying shown as a hadith), ruling («حرام» on screen), hadith-and-dose (a hadith and a dose on one line: a religious AND a medical row) | business-word-in-hadith («التاجر» inside a quoted hadith: no business flag) |
| business | roi («هتكسب ٢٠ ألف في الشهر», a business client → needs-evidence), guarantee («نتيجة مضمونة ١٠٠٪» → needs-approval), doctor-price («الكشف ٣٠٠ جنيه», per-line detection; the spoken validity was dropped) | negative-clean (a business client) |
| ai | accuracy-claim («بدقة ٩٩٪» → needs-approval), broll-no-label (an `ai_generated` still with no label → needs-disclosure), voice-claim (the screen says the voice is AI, the doctor says it is his own) | negative-clean |

## Engine pins (tests/test_review_domains_evals.py, 17 tests after fix round 1)
Per case, on its own planted files:
- the planted review-scan.json equals `review_domains.scan()`;
- the expected table passes `review_flags.write()` with every tuple in the file, and `load()` serves it;
- each wrong answer (a missing flag row) is refused naming the line: all 17 refused, none silently accepted;
- each case's graders are exactly the ones in the test's own `GRADERS` table, kept apart from the grader files: the
  file path, the event id, the accepted flags and the accepted verdicts of every grader. A loosened set or a deleted
  grader goes red (review P2-1; both of the reviewer's mutants now fail, `work\task53\review-mutants-fu1.log`);
- every flagged expected row has exactly one grader, and that grader never accepts `ok`. Two medical-side rows are
  deliberately ungraded, listed in `UNGRADED`;
- a hadith on screen is never accepted as `religious: ok` (P1, the owner's human religious gate);
- a guarantee has one contract: business `needs-approval` in business-guarantee and medical-cure-promise alike
  (P2-4, Task 52's business-claims.md rule 4);
- the cases that wait for Task 52 say so (P2-5);
- every grader passes the expected table (pretty, compact, keys reordered) and fails each mutation: row missing,
  wrong verdict, flag on another line, other flag, keys split across rows, near-miss key names, a later all-ok
  overwrite, no file;
- each negative grader fails on its forbidden row and passes an ok row for that flag;
- the duplicate grader fails on a contradicting row;
- 3 + 1 per domain; no verse markers and no hit of the religious lexicon's verse rules; `structure_problems()` lists
  no missing eval.

**Pinned engine gap (review P2-3, leftover for the executor: `lane4\work\task53\leftover-engine-religious-ok.md`):**
for a religious client (key `ai+medical+religious`), ONE `medical: ok` row clears a line for religious too.
- Cause: `review_flags._cover`'s implied coverage exempts only a triggered ai, not a triggered religious.
- It holds even when the words DO trigger religious (a «قال رسول الله ﷺ …» citation, `review-religious-hadith-attribution`
  and `-business-word-in-hadith`), not only for the undetected «حرام» (`review-religious-ruling`).
- On a medical client the same row is refused.
- The engine accepts it and NEEDS-YOU lists nothing. Only the eval's `g02-religious` grader, and the editor's own
  read, catch it.

Lexicon observations from building the cases (not changed here, not in scope): «الأعشاب دي بتعالج السكر نهائي» detects
no medical domain, and «الصيام في الحالة دي حرام» no religious one. Both are covered in the cases by the client set
(medical always on; a religious client), so the review still has to cover them.

The round-0 trace graders were also checked with JS RegExp (node, the runner's engine) on 823 synthetic trace
variants: 0 wrong, 530 of 530 mutations caught (lane-4 work folder, `grader-mutation.log`). That set never included
a second Write or a duplicate row (review P2-2). The fix-round file graders were checked with Python `re` only (no
mutation run under the light tier). They use no construct whose meaning differs between Python and JS (lookaheads,
classes, backreferences).

## Run of record
`claude plugin eval . --case 'review-*' --runs 3 -j 3 --ablation none --scaffold --trust-plugin --no-publish
--allow-tools Write --judge-model sonnet --keep-temp`, CLI 2.1.299, subscription login (claude.ai, team), one
`heavy.sh job builderA-t53-evals`, 2026-10-19 19:51–20:13 (+03:00), against a scratch copy of HEAD 05b90d3 with the
fixture patch applied. HEAD has the review-domain engine (`review_domains.scan`, M1-T1/T2) but **not** Task 52's business/ai checker
guidance (`business-claims.md`, `ai-claims-and-disclosure.md`, the four-domain reviewer text) nor Task 50's stage-7
skill paragraph.
Cost: agents USD 11.20 + judge USD 0.57 (runner estimate). Raw results are not committed.

`tools/eval_summary.py`: **0/16 cases ≥ 2/3** at the runner's bar. Two graders failed for reasons in the case
design, not in the review:
- `skill-fired` failed 48 of 48 runs: no run invoked a Skill. The note tells the lead to do the review itself, and
  the reviewer guidance (`medical-accuracy`) is not user-invocable, so no skill call is expected.
- the `llm` rubric failed 38 of 48 runs on answers that were right: it said "does not approve anything itself", and
  the judge counted a reviewer's `ok` (and a remark that an attribution is not the speaker's) as an approval or a
  ruling.

The counted decision (the trace tuples, the negative grader and no-gate-jargon), per run, from the runner's own
grader results:

| case | runs with every counted grader passing | what failed |
|---|---|---|
| review-medical-dose-claim | 3/3 | — |
| review-medical-general-client | 3/3 | — |
| review-medical-cure-promise | 3/3 | — |
| review-medical-negative-clean | 3/3 | — |
| review-religious-hadith-attribution | 3/3 | — |
| review-religious-ruling | 3/3 | — |
| review-religious-hadith-and-dose | 3/3 | — |
| review-religious-business-word-in-hadith | 3/3 | — |
| review-business-roi | 3/3 | — |
| review-business-guarantee **below 2/3** | 0/3 | g02-business: `business: remove` in all 3 (the spec says a guarantee is `needs-approval`) |
| review-business-doctor-price **below 2/3** | 1/3 | g03-ok: `medical: reword-to-match` in 2 runs; the planted speech had «… الأول» that the screen dropped (a fixture flaw) |
| review-business-negative-clean **below 2/3** | 0/3 | G01 flagged for business (planted speech «أكاديمية العيادة» vs screen «أكاديمية Example Clinic»: a fixture flaw); G02 «الكورس فيه ٦ محاضرات» flagged `needs-evidence` / `needs-approval` in all 3 (over-flagging) |
| review-ai-accuracy-claim **below 2/3** | 1/3 | g02-ai: `ai: reword-to-match` in 2 runs; the planted speech had «عندنا جهاز …» that the screen dropped (a fixture flaw) |
| review-ai-broll-no-label **below 2/3** | 0/3 | g02-ai: `ai: remove` in all 3 (expected `needs-disclosure`) |
| review-ai-voice-claim | 2/3 | run 3 timed out at 420 s after 3 turns (wrote nothing) |
| review-ai-negative-clean | 3/3 | — |

11/16 cases meet ≥ 2/3 on the counted decision: every medical and religious case, business-roi, ai-voice-claim and
ai-negative-clean. The two clear review misses (guarantee → `remove`, AI still → `remove`) are the verdicts Task 52's
guidance defines (`needs-approval` for a guarantee; `needs-disclosure` until the label exists). That guidance is not in
HEAD, so these results measure today's text.

## Changed after the run (not re-run: the owner allowed one run)
- `skill-fired` is record-only (`min: 0`), as protect-client-sources already is: no skill call is expected here.
- The rubric now says that marking a line ok is the reviewer's job and not an approval, and that saying an
  attribution or claim is not the speaker's own is a check and not a ruling.
- Every line expected `ok` now has planted speech identical to its screen text (the three fixture flaws above, and
  the same pattern on other ok lines). Flagged lines keep their designed differences.

The tuple and negative graders did not change in that step. The case folders exactly as measured are kept in the
lane-4 work folder (`measured-cases/`, `eval-run-of-record.json`).

## Fix round 1 (review 6275496: P1, P2-1..5, P3; LIGHT tier, no mutation run, no live re-run)
- **P1:** every hadith or religious-citation line expects `needs-approval`, never `ok` (Builder A's ruling; the
  owner's human religious gate). `g02-religious` in `review-religious-hadith-and-dose` and
  `review-religious-business-word-in-hadith` now accepts `needs-approval` only (it accepted `ok` before). The conflict
  with `religious-content.md` §2 is a leftover for the executor and Yunus: `lane4\work\task53\leftover-religious-content-s2.md`.
- **P2-1:** the test pins every grader against its own table (above).
- **P2-2:** the counted graders read the final `review-input.json` (`target: {source: file, path}`; the CLI's
  grader schema accepts it, and it is resolved in the run's sandbox cwd). A `no-duplicate-rows` grader was added.
- **P2-3:** the pin and this text name the real cause (above). The engine fix is a leftover:
  `leftover-engine-religious-ok.md`.
- **P2-4, one guarantee contract:** a guarantee («مضمونة ١٠٠٪», «علاج نهائي ١٠٠٪») gets business `needs-approval`
  (Task 52's business-claims.md rule 4: a guarantee needs the business owner's approval; the strongest verdict
  wins). `review-medical-cure-promise`'s business grader is narrowed from `needs-approval|needs-evidence|remove` to
  `needs-approval`, like `review-business-guarantee`. Its live runs wrote `remove` once and `needs-evidence` twice,
  so it now depends on Task 52's guidance too.
- **P2-5:** `review-business-guarantee`, `review-ai-broll-no-label` and (since P2-4) `review-medical-cure-promise`
  carry `tags: [..., pending, needs-task52]`. Their description names the Task 52 reference they wait for and says
  they are expected to fail until it lands. `tools/eval_summary.py` lists `pending` cases without counting them in
  the ≥ 2/3 bar, so a Gate 4 run before Task 52 shows why they fail. Re-score these three after Task 52 lands.
- **P3-1:** `review-business-negative-clean` G02 is now «الكورس ده معمول للتمريض اللي شغالين في العيادات» (no number,
  no product claim).
- **P3-3:** the no-verse test also runs the religious lexicon (`verse-phrase`, the `quran-verse` zone) on every line of
  every case file.

**The fix-round graders on the 48 recorded runs** (`rescore-recorded-fu1.log`: each run's final review-input.json,
taken from its trace, scored with the new graders; the plants of the run of record, not today's): 10/16 cases ≥ 2/3.
- Every medical (except cure-promise, now pending) and religious case passes.
- business-roi, ai-voice and ai-negative pass.
- Below the bar: the three pending cases, plus doctor-price and ai-accuracy (fixture flaws fixed since) and
  business-negative-clean (G01 fixture flaw fixed; G02 replaced).
- Counting only the 13 non-pending cases: 10/13.
- No run wrote the table twice except business-negative-clean run 3, whose final file is what the new graders read.

## Known limits
- **Not re-run live** (owner decision, one run). The cases as they stand were never scored by the runner. The
  file-target graders, the narrowed sets and the new plants are checked by unit tests and by re-scoring the recorded
  runs only. One re-run costs ≈ USD 12 and ≈ 23 min.
- The runner's handling of a `{source: file}` target was read from the CLI's own schema and code (CLI 2.1.299), not
  from a run. A missing file fails the grader (the positive graders cannot pass without the table).
- Three cases wait for Task 52 (pending, above).
- The `llm` rubric counts at the runner's threshold (`threshold: 1`). The clarified rubric is unmeasured.
- A reason text holding `{` or `}` can hide a row from the row-anchored regexes. The reviewer writes plain Arabic
  reasons; none of the 48 tables written in the 47 runs that wrote one had such a reason.
- The owner minimum dropped:
  - Q53-1's `review_detect: off` case (B+6);
  - the «معتمد من وزارة الصحة» case (B+3);
  - the named-competitor case (B+5).
- No case checks that a filler-only trim (screen drops «يعني», «اللي تحت») stays `ok`: every ok line's speech now
  equals its screen text (review P3-2; a later case).
- Lexicon misses seen and not in scope:
  - «بتعالج السكر نهائي» (medical);
  - «الصيام … حرام» (religious).

## Not verified
- Any run with Task 52's guidance applied (the three pending cases need it).
- The religious texts, for Yunus's qualified reviewer (review P3-4; `leftover-religious-content-s2.md`):
  - «خير الأمور أوسطها»: shown as a hadith on purpose (its misattribution is that case's point); widely regarded as not
    an authentic saying;
  - «التاجر الصدوق الأمين مع النبيين والصديقين والشهداء»: its grading is disputed;
  - «تداووا»: a one-word fragment of a longer reported hadith.

  They are from memory, not checked against a source.
