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
`reel review-flags --from` table to `<project>/review-input.json`. Graders:
- one `regex` on `target: trace` per expected (event id, flag, verdict) tuple, anchored inside the Write call whose
  path ends in `<id>/review-input.json` and inside ONE row object of the table (the runner's trace is the child's
  stream-json messages, each JSON.stringify-ed, one per line; the table therefore appears JSON-escaped);
- one `not_contains` regex per case for a flag that must NOT be there;
- `no-gate-jargon`, one `llm` rubric (never the only counted decision), and `skill-fired`.

| domain | + cases | − case |
|---|---|---|
| medical | dose-claim (500 mg on screen, 250 mg spoken), general-client (a `general` client's «بتعالج السكر نهائي»), cure-promise («علاج نهائي ١٠٠٪»: a medical AND a business row) | negative-clean |
| religious | hadith-attribution (a saying shown as a hadith), ruling («حرام» on screen), hadith-and-dose (a hadith and a dose on one line: a religious AND a medical row) | business-word-in-hadith («التاجر» inside a quoted hadith: no business flag) |
| business | roi («هتكسب ٢٠ ألف في الشهر», a business client → needs-evidence), guarantee («نتيجة مضمونة ١٠٠٪» → needs-approval), doctor-price («الكشف ٣٠٠ جنيه», per-line detection; the spoken validity was dropped) | negative-clean (a business client) |
| ai | accuracy-claim («بدقة ٩٩٪» → needs-approval), broll-no-label (an `ai_generated` still with no label → needs-disclosure), voice-claim (the screen says the voice is AI, the doctor says it is his own) | negative-clean |

## Engine pins (tests/test_review_domains_evals.py, 12 tests)
Per case, on its own planted files: the planted review-scan.json equals `review_domains.scan()`; the expected
table passes `review_flags.write()` with every tuple in the file and `load()` serves it; each wrong answer (a missing
flag row) is refused naming the line (all 17 wrong answers are refused; none is silently accepted); each trace
grader passes the expected table (pretty, compact, content before path, keys reordered) and fails each mutation (row
missing, wrong verdict, flag on another line, other flag, keys split across rows, near-miss key names, another file,
another project, only seen in a Read result, written with Edit); each negative grader fails on its forbidden row and
passes an ok row for that flag; 3 + 1 per domain; no verse markers; `structure_problems()` lists no missing eval.

**Pinned known limit:** «حرام» alone is not detected (everyday speech), and for a religious client a `medical` row
covers religious by T4.13's implied coverage, so the engine accepts a ruling passed as `medical: ok`. Only the eval's
`g02-religious` grader catches that answer.

Lexicon observations from building the cases (not changed here, not in scope): «الأعشاب دي بتعالج السكر نهائي» detects
no medical domain, and «الصيام في الحالة دي حرام» no religious one. Both are covered in the cases by the client set
(medical always on; a religious client), so the review still has to cover them.

The grader regexes were also checked with JS RegExp (node, the runner's engine) on 823 synthetic trace variants:
0 wrong, 530 of 530 mutations caught (lane-4 work folder, `grader-mutation.log`; optional under the light tier).

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

The tuple and negative graders did not change. The case folders exactly as measured are kept in the lane-4 work
folder (`measured-cases/`, `eval-run-of-record.json`).

## Not verified
- A live run of the cases as committed (after the changes above). One re-run (≈ USD 12, ≈ 23 min) would score them.
- Any run with Task 52's guidance applied (the business and ai cases need it to be meaningful).
- The hadith fragments («تداووا», «التاجر الصدوق الأمين مع النبيين والصديقين والشهداء») and the saying «خير الأمور أوسطها»
  (shown as a hadith on purpose: its attribution is the point of that case) are from memory, not checked against a
  source by a qualified reviewer. The cases never assert their grading; a qualified reviewer should confirm the text.
