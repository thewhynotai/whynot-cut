# WhyNot Cut 3.0 — Addendum M: owner requests of 2026-10-16 (review domains, mixed Arabic/English, expressive style, B-roll with choice, token efficiency)

| | |
|---|---|
| Date | 2026-10-16 |
| Requested by | Yunus, via the plan session on 2026-10-16. All five requests are binding (M0) |
| Applies to | Phases 4, 5, 6, 6B, 9 and 10; the agents medical-reviewer, claim-checker, story-editor, motion-director, transcript-editor, segment-proofreader, graphic-checker, frame-inspector, qc-reviewer and asset-scout; the review-flags file (T4.13), the Magnific guard (T5.5) and the evals. It adds tasks; it removes none |
| Section prefix | **M** (tasks `M<n>-T<k>`; human items in M7) |
| Standing rules | Decide and continue. Zero cost (F1): the only spend anywhere in M is Magnific credits, and only after the editor says yes each time (M4). Quality first (G2): no review, test or check is shortened to save tokens (M5). Error-free first (G10). No telemetry (D17). Arabic first |
| Related addenda | K (decision log K-T9, Arabic integrity K-T5, kashida K-T13, motion palette K-T14, local B-roll search K-T16), H (looks and scenes R-4.1/R-6.1/R-6.2, Tasks 23/25/27/28), J (open-font index J4, fetch core J-T1), L (security, written in parallel: free-source API keys, downloads and the new network paths in M4 follow it) |
| Commit | The executor commits this to `docs/superpowers/specs/addendum-m/` (single writer). The session that wrote it commits nothing |

### ملخص ليونس
- **M1 — المراجعة بقت ٤ مجالات:** طبي، ديني، **بيزنس** (أرباح، عائد، ضمانات، أسعار، وعود قانونية، مقارنة بمنافسين)، و**الذكاء الاصطناعي** (ادعاءات عن قدراته، والإفصاح إن الصورة أو الصوت أو الـ B-roll متولّد). كل مجال له تعليمات مراجعة وبوابة وسجل موافقات واختبارات. قائمة المجالات بتتحدد من ملف العميل؛ الطبي والـ AI شغالين دايماً لكل عميل (الطبي شغال كده النهارده ومش هنضعّفه). والمحرك بيكتشف لوحده لو سطر معيّن دخل مجال تاني (مثلاً دكتور بيتكلم عن أسعار) ويطلب مراجعة السطر ده بس.
- **M2 — العربي مع الإنجليزي:** ترتيب الكلام صح في الكابشن والجرافيك (اتجاه، علامات ترقيم، أرقام، كلمة إنجليزي جوه سطر عربي، وتقسيم السطور من غير ما يكسر الجملة الإنجليزي). Whisper يكتب الكلمات الإنجليزي بحروف إنجليزي. **الخط العربي والإنجليزي لازم يكونوا من نفس الشخصية** (رسمي مع رسمي، يدوي مع يدوي، هندسي مع هندسي): من قاعدة بيانات العميل لو المونتير حددها، وإلا من جدول خطوط مجانية (OFL) بدرجة توافق. وفحص على الفريمات اللي اترندرت فعلاً.
- **M3 — ستايل غني ومتنوع ومش فوضوي:** عائلة ستايل قوية بتنويع مقصود في الخطوط والحركة، بقواعد: قد إيه تنويع، فين، وليه، وفحص آلي وبصري.
- **M4 — الـ B-roll باختيارك:** (أ) مكتبة العميل ومصادر مجانية رخصتها تجارية والرخصة متسجلة لكل ملف، (ب) Magnific بحث وتنزيل، (ج) توليد بالذكاء الاصطناعي. **في كل توليد** البلاجن يسألك تختار الموديل، يقترح واحد، يشرح كل موديل في سطر ويقول التكلفة التقريبية بالكريدت، ويحذرك بوضوح إن الكريدت هيتخصم **قبل** أي صرف. فيه وضع «نقرر مع بعض». ولا حاجة بتتصرف من غير «أيوه» منك: أي أداة في Magnific مش في قائمة القراءة بس بتترفض لوحدها لو مفيش موافقة، وتنزيل الـ stock بموافقة لكل ملف لحد ما نثبت إنه مجاني، ولا فريم من فيديو العميل بيترفع للبحث.
- **M5 — توفير التوكنز من غير ما الجودة تقل:** قياس النهارده لكل مرحلة ولكل فيديو، ميزانية مستهدفة لكل فيديو، اختبار بيفشل لو فيديو عدّاها، وقاعدة إن الجودة عمرها ما تقل عشان نوفر. الشغل الثابت ينتقل للمحرك، ملخصات صغيرة بدل الملفات الكبيرة، موديلات أرخص للخطوات الميكانيكية بعد ما نثبت إن الجودة زي ما هي، كاش لتحليل العميل، تشغيل كذا فيديو مرة واحدة، ونقطة استكمال لو الليميت خلص.

---

## M0. Owner words (2026-10-16, binding)
Yunus asked, in the plan session, for: review gates for **medical, religious, business, and AI in all its forms**; correct
**mixed Arabic + English** (most videos are Arabic with 25–50 % English words) including **font harmony between the
Arabic and Latin faces**; a **rich, expressive, varied style that stays on-brand and never chaotic**; **B-roll from free,
Magnific or AI sources with a model choice and a credit warning every time**; and a plugin that is **token- and
session-efficient by design**, so a user makes a reasonable number of videos per Claude session with strong results.
The plan session records his exact Arabic words in PROGRESS.md when it commits this file.

---

## M1. Review gates widen: medical, religious, business, AI

### M1.1 Requirements
1. Four review domains in 3.0: `medical`, `religious`, `business`, `ai`. The list is **data, not code**: a new domain is
   added by a registry entry plus its checker guidance, its trigger lexicon and its eval cases, with no engine change.
2. **Per-client choice.** The client profile says which domains apply. Two domains are **always on**:
   - `medical`: today's medical-reviewer checks health claims for every client, `general` and `religious` included (`DOMAIN_FLAGS` in `review_flags.py`), and M1 must not weaken an existing guard;
   - `ai`: disclosure concerns our own pipeline's generated assets.

   Domains the engine **detects** in a clip's words but the profile does not list are reviewed too by default (safety first). The editor can set this to "suggest" or "off" per client.
3. **Every domain has:** its own checker guidance, its own gate (a line under it is clear only when reviewed and, if
   flagged, reworded, removed or approved), its own decision-log entries (K-T9) and its own eval cases.
4. **Business** covers: financial, earnings or ROI claims; guarantees; pricing (amounts, currency, validity, "from"
   prices, VAT wording); legal and compliance promises (licensed, certified, "approved by" an authority); competitor
   comparisons (named or implied, superiority claims such as "the best", "#1", «الأول»).
5. **AI** covers: claims about AI capabilities and facts ("our AI diagnoses…", "AI replaces…", accuracy numbers), and
   **disclosure or labelling** of AI-generated visuals, voice or B-roll used in the reel (from M4's manifest).
6. The reviewer never gives legal, financial or religious rulings and never rewrites claims into new claims: it checks
   wording against the speech and the client's own material, flags, and names who must approve.
7. **T4.13 is not reworked.** It is done and committed (PROGRESS.md, commit 0db008f). M1 specifies only the follow-up
   delta (M1-T2), written against that commit.

### M1.2 Design
**Registry** `whynot-cut/config/defaults/review-domains.json` (schema 1):

```json
{"schema": 1, "domains": {
  "medical":   {"label": {"ar": "طبي", "en": "Medical"}, "reference": "medical-accuracy.md",
                "lexicon": "review-lexicons/medical.json", "approver": {"ar": "الطبيب", "en": "the doctor"},
                "verdicts": ["ok", "reword-to-match", "needs-doctor-approval", "remove"], "always_on": true},
  "religious": {"label": {"ar": "ديني", "en": "Religious"}, "reference": "religious-content.md",
                "lexicon": "review-lexicons/religious.json", "approver": {"ar": "صاحب المحتوى", "en": "the content owner"},
                "verdicts": ["ok", "reword-to-match", "needs-approval", "remove"], "always_on": false},
  "business":  {"label": {"ar": "بيزنس", "en": "Business"}, "reference": "business-claims.md",
                "lexicon": "review-lexicons/business.json", "approver": {"ar": "صاحب البيزنس أو المستشار القانوني", "en": "the business owner or their legal adviser"},
                "verdicts": ["ok", "reword-to-match", "needs-approval", "needs-evidence", "remove"], "always_on": false},
  "ai":        {"label": {"ar": "ذكاء اصطناعي", "en": "AI"}, "reference": "ai-claims-and-disclosure.md",
                "lexicon": "review-lexicons/ai.json", "approver": {"ar": "العميل", "en": "the client"},
                "verdicts": ["ok", "reword-to-match", "needs-approval", "needs-disclosure", "remove"], "always_on": true}
}}
```

**Profile** (`profile.json`) fields:
- `review_domains: ["business"]`;
- `review_detect: "review" | "suggest" | "off"` (default `review`).

Back-compat: when `review_domains` is absent, the old `domain` maps to `[domain]`, and `general` maps to `[]`. `common.content_domain()` stays for its current uses (glossary labels).

Two sets, kept apart so the review key stays stable:
- **Client set** = profile domains ∪ always-on (`medical`, `ai`). It changes only when the profile changes. It is the set stored as T4.13's `domain` key (M1-T2).
- **Detected domains** (`review_domains_detected(plan)`) are per line, not per file. A line whose words hit a domain outside the client set gets that domain as a **required flag check** for that line only (with `review_detect: review`). The reviewer must cover the line for that flag: a verdict row with that flag, or an `ok` row whose `flags` list names it (M1-T2).
- **Detection is a floor, never a ceiling.** Whatever `review_detect` says (`off` included), the reviewer may flag any line for any registry domain, including a business claim the lexicon missed. A plan edit that adds or removes one price word therefore changes what that one line needs; it never changes the file's key, and never forces a full re-review.

Detection is deterministic: lexicons and patterns run over the compiled plan's on-screen text and the transcript spans that text cites. The same plan always gives the same result.

**Engine pre-scan** `reel review-scan <item>` (deterministic, no LLM): per on-screen line, the domains whose triggers hit
and why (the matched words), plus the transcript evidence span. Examples of triggers (the lexicons ship in Arabic and
English, Egyptian forms included):
- business: currency and amounts (جنيه، EGP، $، ريال، درهم، «بس بـ»), returns and gains («ربح»، «عائد»، ROI، «دخل
  شهري»، «ضاعف»), guarantees («مضمون»، «ضمان»، «١٠٠٪»، "guaranteed"), comparisons («أحسن من»، «أفضل من»، «الأول في»،
  "better than", "#1"), compliance («مرخّص»، «معتمد»، «حاصل على موافقة»، "FDA approved", «وزارة الصحة»), urgency («لفترة
  محدودة»، «آخر فرصة»);
- ai: «ذكاء اصطناعي»، "AI", tool and model names, capability verbs («يشخّص»، «يتنبأ»، «بيعرف»، "detects", "replaces"),
  accuracy numbers next to AI words; and every timeline element whose asset manifest says `ai_generated: true`.

The reviewer agent receives the line list with these hints (M5: it does not search the whole plan for them) but still
reads every line: a hint is a pointer, never a filter.

**Checker guidance** (in `skills/medical-accuracy/references/`, the skill keeps its name and its ≤ 90-char description):
- `business-claims.md`: wording vs speech (any meaning change fails); numbers and currencies exactly as spoken; earnings
  and ROI claims marked `needs-evidence` unless the client's own material substantiates them, and a typical-results
  qualifier kept where the speaker gave one; guarantees `needs-approval`; prices checked for currency, "from", validity
  date and tax wording as spoken; "approved/licensed by" claims `needs-evidence` with the authority named exactly;
  competitor comparisons: a named competitor or a superiority claim `needs-approval`; local consumer-protection and
  advertising rules are the client's responsibility: the reviewer flags, it never advises.
- `ai-claims-and-disclosure.md`: capability and accuracy claims about AI follow the same evidence rules as business;
  **disclosure:** a realistic AI-generated image, video or voice in the reel → `needs-disclosure` until the plan carries
  the client's chosen label (an on-screen tag such as «صورة توضيحية مولّدة بالذكاء الاصطناعي», per client style) **and**
  the publish package carries each platform's AI-content label instruction (YouTube, Instagram/Facebook, TikTok; their
  rules recorded with a basis and a date like Task 27's safe zones). A clearly illustrative non-realistic asset (an icon,
  a vector) needs the manifest record only. No AI voice of the client is ever produced (T5.5 already denies TTS of client
  content).
- `medical-accuracy.md` and `religious-content.md`: unchanged, plus K-T1 (risk words) and K-T8 (two-source verses).

**Agents.** `medical-reviewer` keeps its name (renaming breaks hooks, evals and saved approvals) and becomes the content
reviewer for every active domain: one table, a `flag` per row from the registry, verdicts from that domain's list, and
fan-out to `claim-checker` batches grouped by domain. Description text stays within the D11 budget test.

**Gate per domain.** `reel review-gate <item>` reads `review-flags.json` and the decision log (K-T9) and prints one line
per active domain («طبي ✔ ١٢/١٢ · بيزنس ⚠ ١ محتاج موافقة صاحب البيزنس · AI ✔»). A domain is **clear** when every line is
covered and every flag in it is `ok`, or the wording was changed/removed and re-reviewed, or the decision log holds an
approval for that exact wording (sha256) by that domain's approver role. Plan approval and the build may proceed with open
flags (the editor needs the build to show the client); **`handoff` and the READY state refuse while any active domain is
not clear**, naming the line and who must approve. `NEEDS-YOU.md` (T4.7) and the panel (Phase 6) show the same lines.

### M1-T2 Delta to T4.13 (one additive field, no breaking format change), written against commit 0db008f
**The code as committed** (`whynot-cut/engine/reel/lib/review_flags.py`):
- `domain` is a plain string from `common.content_domain()`, compared only for equality. A changed value already makes the previous file unusable, so the next write must list every line (a full re-review).
- The flags allowed per domain live in `DOMAIN_FLAGS`: `medical → (medical,)`, `religious → (religious, medical)`, `general → (medical,)`.
- `_all_flags()` derives every flag from that dict. `_allowed(domain)` returns `DOMAIN_FLAGS.get(domain, DOMAIN_FLAGS["general"])`.
- `VERDICTS` is one global tuple.

As committed, a composite key such as `ai+business+medical` would fall back to `general`, and every `business` or `ai` row would be refused. M1 therefore changes values and the lookup, and adds one **optional** field. Old files still load, because `_rows`
ignores extra keys. The executor implements this in T4.13's code under M1-T2.

**The delta:**
- **Canonical key.** One client may have several domains (a doctor who also sells a course is medical + business). The **client set** (M1.2) is stored in the existing `domain` string in canonical form, made by one function, `common.review_domain_key(ids) -> str`:
  - each id is lower-cased and trimmed;
  - duplicates are removed;
  - only registry ids are allowed (an unknown id is refused when the profile loads, naming it);
  - ids are sorted by code point and joined with `+`.

  Examples: `ai+business+medical`, `ai+medical+religious`, `ai+medical`. Detected domains are never part of the key (M1.2).
- **Allowed vs required flags.**
  - **Allowed on write:** any registry flag is accepted on any line, whatever `review_detect` says. A claim the lexicon misses can still be flagged, and a reviewer's extra concern is never refused. `off` only turns detection off.
  - **Required on write:** the union over the key, plus the line's detected required flags (`review` only). Each one must be covered on that line.
  - **On read** (`load()`): any registry flag is accepted on a row. A shipped lexicon update that stops detecting a line therefore never makes a stored `business` row "not allowed", and never makes the whole file unusable.
- **`DOMAIN_FLAGS` comes from the registry.** Each registry id flags itself, and the `medical`-always-on rule comes from `always_on`. `_all_flags()` keeps reading it at call time. An unknown key part is refused, never mapped to `general`.
- **`ok` rows record what they cleared (the additive field).** An `ok` row gains an optional `flags` list: the flags for which the line was reviewed and found fine. Rules (executor ruling, 2026-10-17):
  - `_rows` validates `flags` as a list of distinct registry flags.
  - A new `ok` row is written with the line's required flags that are not flagged on that line, minus `ai`. An ai review depends on the assets, not the words, so a carried line must ask for `ai` again when an AI asset appears later. `counts()` reports `ai` as "not applicable / no AI asset" on lines that never had an ai review, never as ok (executor ruling, M1-T2 review P2-1).
  - **An `ok` row may name a line that also has flag rows**, as long as its `flags` do not overlap that line's flagged ones. For example, a line flagged `business` can carry an `ok` row for `medical`. Today's refusal "an ok row may not name a flagged line" changes meaning to "an ok row may not name a line **for a flag that line is flagged for**".
  - A carried `ok` row satisfies only the flags it lists. A required flag it lacks (for example, a newly detected `business`) makes the line need review for that flag, naming it, without forcing a full re-review.
  - An old `ok` row with no `flags` is read as covering `key.split("+")` of its file's key, minus `ai`, so it never counts as an ai review (same reason as above; review P3-3).
  - Per-domain counts in `review-gate` ("بيزنس ١٢/١٢") come from verdict rows plus `ok` rows' `flags`.
- **Code that changes for this:** `_rows` (validating `flags`, the overlap rule), `write()` (the allowed/required checks, writing `flags`, carrying), and `load()` (accepting any registry flag, reading `ok` rows without `flags`).
- **Legacy values keep today's checks.** A profile with only the old `domain` maps:
  - `general` → `ai+medical`;
  - `medical` → `ai+medical`;
  - `religious` → `ai+medical+religious`.

  Medical checking is never dropped. Every existing file's key differs once after the upgrade, so the first review after it lists every line once, through today's domain-change path, with one message saying why. Nothing is rewritten by migration.
- **Verdicts per flag.** `VERDICTS` stays as the union, for reading old files. Validation of a row checks the verdict against its own flag's registry list:
  - `medical` keeps `needs-doctor-approval`;
  - the new values are `needs-approval`, `needs-evidence` and `needs-disclosure`.
- **No approver role per row.** The panel and `review-gate` look it up from the registry by `flag`.
- **Meanings unchanged, except one.** Coverage, carrying, the "uncarried flag needs the same-flag re-review" rule and every refusal keep their meaning. The exception is the ok/flagged-line refusal, which narrows to overlapping flags as described above. Their tests are parameterised over the registry's domains.
- Contract §7.6 delta for the Adobe track (a note, like T413-contract-7.6): `domain` may now be a `+`-joined set (the panel
  compares it for equality with the engine's current key, never parses meaning from order), the optional `ok[].flags`
  list (absent in old files), the two new flag values,
  the new verdict labels in Arabic and English, domain chips on flagged spans, and the registry labels the engine sends
  in engine-state.

### M1.3 Tasks, acceptance and tests
| Task | Content | Acceptance (tests written first, seen failing) | Phase | Size | Owner |
|---|---|---|---|---|---|
| M1-T1 | Registry, profile fields, client set, `review_domain_key()`, per-line detection, lexicons, `reel review-scan` | `test_review_domains.py`: `test_domain_key_canonical` (order, duplicates, case, whitespace → one key; unknown id refused; legacy `general`/`medical` → `ai+medical`, `religious` → `ai+medical+religious`); `medical` and `ai` always in the client set; a detected domain never enters the key; adding or removing one price word in a plan changes only that line's required flags, never the key; detected required flags only with `review_detect: review`; deterministic per plan; a registry entry missing its reference, lexicon or eval case fails a structure test (extensibility proof: a fixture fifth domain works with no code change); Arabic/English/Egyptian triggers per domain; no false business trigger on a plain medical fixture | 4 | M | executor |
| M1-T2 | T4.13 delta against 0db008f: canonical key, allowed vs required flags, `ok` rows' optional `flags` list, `DOMAIN_FLAGS` generated from the registry, per-flag verdicts, contract note | `test_review_flags.py` parameterised over the registry's domains; a `business` flag on a line the lexicon missed is accepted under `review`, `suggest` and `off`; a line flagged `business` with an `ok` row for `medical` → accepted, and both domain counts are right; an `ok` row whose `flags` overlap that line's flag rows → refused; `ok.flags` with a duplicate or a non-registry flag → refused; a carried `ok` row without `business` in its `flags` does not cover a newly detected `business` line (that one line is named, no full re-review); an old file whose `ok` rows have no `flags` loads and counts as `key.split("+")`; a lexicon update that drops a detection never makes a stored row invalid; per-domain counts from verdict rows + `ok` flags; a composite key `ai+business+medical` accepts `business` and `ai` rows (fails today); an unknown key part refused, never mapped to `general`; **a `general` client's dose line still needs a `medical` row** (regression guard); a file written for `ai+medical` is not carried after the client adds `business` (full-review message); a legacy `medical` file → full review once; a verdict outside its flag's list refused; generated `DOMAIN_FLAGS` ≡ registry (structure test); every existing T4.13 test still passes unchanged | 4 | S–M | executor |
| M1-T3 | Checker guidance files + agent/skill text | `test_skill_text.py`: each registry `reference` exists and is named by the skill; agent description within D11; review table columns unchanged | 4 | S | executor |
| M1-T4 | Gate per domain: `reel review-gate`, handoff/READY refusal, NEEDS-YOU lines, decision-log check (needs K-T9) | `test_review_gate.py`: open business flag blocks handoff with the approver named; approval of the exact wording clears; a reworded line needs a new review; an approval of other words does not clear; READY never set while open | 6 (first engine wave, with K-T9) | M | executor |
| M1-T5 | Evals per domain | ≥ 3 positive + 1 negative case per domain (Arabic prompts first): ROI promise «هتكسب ٢٠ ألف في الشهر», guarantee «نتيجة مضمونة ١٠٠٪», a named competitor, «معتمد من وزارة الصحة», an AI accuracy claim, an AI-generated B-roll still with no label, a doctor's clip that mentions a price (per-line detection case), a `general` client with a health claim (medical still reviewed), a clean business clip (negative); each counted case ≥ 2/3 runs | 4 (engine evals), 6 (panel) | M | executor |
| M1-T6 | Panel: domain chips, per-domain gate line, approval with role (Adobe track, E-D2 mockup first) | E-D5 visual diff; contract tests | 6 | S–M | Adobe track |

**QC at Gate 4 (M6 list):** M1-T1, T2, T3 and T5 (engine evals) green; a live stage-7 run on a `whynot-test` copy with a business-heavy fixture clip
shows all four domains in the review table and in `review-flags.json`. **Gate 6:** M1-T4 and T6 live through the panel.

---

## M2. Mixed Arabic + English speech

### M2.1 Requirements
1. **Bidi correct** in captions, graphics, motion text, thumbnails and caption files: right-to-left and left-to-right
   runs in the right visual order; punctuation on the correct side; numbers, percentages, ranges, decimals, units, phone
   numbers and prices in the right order; Latin terms inside Arabic lines (including «الـ» attached to a Latin word, as
   in «الـ MRI»); diacritics kept.
2. **Line breaking never splits a run badly:** no break inside a short Latin run (≤ 3 words) when another break exists;
   never between «الـ» and its Latin word, a number and its unit, an opening bracket or quote and its word. The order
   follows the Unicode Bidirectional Algorithm (UAX #9):
   1. resolve the paragraph direction and embedding levels once per paragraph (HL1: RTL if the paragraph has any
      Arabic letter, bidi class AL; otherwise P2/P3; then W1–W7, N1–N2, I1–I2);
   2. break the paragraph into lines;
   3. reorder each line with L1–L4.

   Reordering never runs on the whole paragraph before breaking, and the direction is never re-decided per line.
3. **Whisper keeps English terms in Latin script** in mixed speech, without translating anything and without lowering
   Arabic accuracy.
4. **Typographic harmony.** The Arabic and Latin faces in one video match in personality: formal with formal,
   handwritten with handwritten, geometric with geometric, humanist with humanist, display with display. The pairing
   comes from the client database when the editor set it there; otherwise from a curated table of free (OFL) faces with
   a **matching score**. Weights and visual sizes are matched too (Latin scaled so its x-height sits right against the
   Arabic letter body).
5. **QC on rendered frames** checks pairing and bidi, not only our own stills.

### M2.2 Design
**Bidi and line layout (one module, every renderer).** A new shared module `whynot-cut/engine/reel/lib/bidi_lines.py`
holds the run segmentation, the no-break rules and the per-line reorder. It is extracted from, and replaces, the
duplicated logic in `hb_text.runs` (executor) and `looks_type.segments` (looks & motion track).

Ownership: the module sits under the executor's `engine/reel/**`, so the **executor writes it** and rewires
`hb_text.py`/`previews.py`. The looks & motion track supplies the fixture table and rewires its own `looks_type.py`.
`lib/bidi_lines.py` is added to LOCKED-AREAS (executor) when this addendum is accepted.

Rules beyond today's (each one a UAX #9 rule, not a shortcut):
- **Paragraph direction**: set once per caption or graphic paragraph, before line breaking. Every line of that
  paragraph keeps it.
  - A paragraph that contains **any Arabic letter is RTL**, even when it starts with a Latin term («AI بيغيّر الطب»).
    UAX #9 allows this as a higher-level protocol (HL1), and it keeps today's `hb_text.runs` rule.
  - First-strong detection (P2/P3) applies only to paragraphs with no Arabic letter at all, so a paragraph that is
    entirely Latin is LTR.
  - An Arabic caption whose wrapped second line is all Latin («... بالـ MRI scan.») stays RTL-aligned, with the period
    on the paragraph's side.
  - A client setting can force RTL for every paragraph of an Arabic-first client.
- **Neutrals** (spaces, punctuation, brackets) follow N1 first: a neutral between two runs of the same direction takes
  that direction, so «blood sugar level» keeps its word order inside an Arabic line. Only then does N2 apply (otherwise
  the embedding direction). Today's `hb_text.runs` already joins neutrals between same-direction runs (its docstring);
  this rule keeps that behaviour.
- **Numbers** follow W2: European digits after Arabic letters are Arabic numbers for ordering. Arabic punctuation
  (، ؛ ؟) appears only in Arabic context. Brackets mirror (L4).
- digits: the client's choice of Western or Arabic-Indic (`style.json` `digits`), never mixed in one line; a number keeps
  its unit, sign, percent and decimal separator in one unbreakable unit;
- `الـ` + Latin word is one unbreakable unit with a thin non-joining join;
- Latin acronyms and multi-word English terms stay one LTR unit in order;
- caption grouping (Task 23) and kinetic units (K-T5) call the same module.

**Host text.** Our stills draw runs explicitly (no control characters). Text for hosts may carry bidi isolates
(LRI/RLI/FSI … PDI); where it does, UAX #9 rules X1–X10 apply, and the module's reorder honours them. Text sent to Premiere (captions, MOGRT text),
After Effects (text layers) and caption files (SRT/VTT) may need invisible direction marks (RLM/LRM or isolates) to keep
the order. **M2-T2 measures** each host with and without marks on the fixture lines and records the rule per host in
`docs/adobe/uxp-parity.md`; a mark that a host shows as a box is never used for that host.

**Whisper and Latin terms.** Three approaches are measured on a mixed set (M7 HM-1) and the best kept, by the T4.14 rule
(quality first, then speed):
1. `language="ar"` with a mixed prompt: the client's Latin terms written in Latin inside an Arabic sentence (today's
   `initial_prompt` path, extended with the glossary's Latin forms);
2. per-chunk language handling for chunks that are mostly English;
3. a deterministic **back-map** after transcription: a word in Arabic letters that matches a glossary or shipped
   lexicon entry's Arabic spelling (e.g. «إنسولين» → insulin) is proposed in Latin, only when the audio confidence and
   the context agree; proposals go through segment-proofreader and are listed for the editor, never silently applied.

Metrics: Latin-script accuracy of English words (share of words spoken in English that end in Latin letters), WER and CER
(`wer.py`, Task 14) on the whole set and on the Arabic part alone. **Target:** Latin-script accuracy ≥ 95 % with Arabic
WER not worse than today's (a rise > 0.5 pp blocks the change). The Kalam correction path (tools track) uses the same
lexicon and back-map.

**Font harmony.**
- **Personality classes:** each face gets a class (formal/classic: Naskh, serif; geometric: geometric Kufi, geometric
  sans; humanist: humanist Naskh-sans, humanist sans; handwritten: Ruqaa, script; display: heavy display Kufi, display
  sans) and measured traits read from the font file with fontTools and a raster probe: stroke contrast, x-height vs
  Arabic tooth height, weight (ink density per weight), width, terminal shape.
- **Score 0–100** = class match 40 + weight match at the role's weight 20 + height ratio fit 15 + contrast match 15 +
  width and rhythm 10. A pair ≥ 70 can be used automatically; 50–69 is shown to the editor with the reason; < 50 is never
  used. The Latin scale factor that aligns the visual heights is part of the pair.
- **Sources, in order:** (1) the client database: `typography.json` gains `pairing` per role
  `{arabic, latin, latin_scale, source: "client" | "table", score}`, set by the editor or by client-researcher from client
  material (the client's choice always wins, with its score shown, never overridden); (2) a superfamily that ships both
  scripts by design (scored, usually high); (3) the curated table `config/defaults/font-pairings.json`.
- **The curated table** is built with the brand-systems-designer from OFL families in the J4.2 open-font index (licence
  checked there), each pair scored by the module and viewed on an AR+EN specimen sheet. Starting candidates to measure
  (not decided): geometric (Alexandria, Cairo, Tajawal, Readex Pro with geometric Latin companions), humanist (IBM Plex
  Sans Arabic + IBM Plex Sans, Noto Sans Arabic + Noto Sans), formal (Amiri, Noto Naskh Arabic, Markazi Text with serif
  Latin companions), handwritten (Aref Ruqaa with a script Latin companion), display (Lalezar, Rakkas with display Latin
  companions). Fonts outside the installer's font pack download on demand through J4.3's pinned, hash-checked source
  (G13: the pack stays small).
- **Where it applies:** the font chain in `looks_type.font_chain` takes the pair (Arabic runs → pair.arabic, Latin runs →
  pair.latin at `latin_scale`) before its fallbacks; previews, thumbnails, MOGRT text and AE text all read the same pair.
  A host that cannot set a font per run (measured in M2-T2) gets the closest legal option recorded per host (a face
  covering both scripts from the same pair class), and QC says so.

**QC on rendered frames.**
1. **Deterministic:** for each text element the engine writes the expected run order and the face per run
   (`08_quality_control/text-expectations.json`). After the build, the read-back gives each layer's fonts (Premiere and AE
   read-back fields, added where missing) and the check compares faces per run; then the rendered frame's text region is
   compared with our own reference render of the same text in the same faces (edge-map similarity, threshold measured on
   correct and wrong-order fixtures). A mismatch names the element and the time.
2. **Visual:** frame-inspector and graphic-checker get a mixed-text checklist (order of the Latin term, punctuation side,
   digits, unit attached, pair consistency across the reel) and look at **every** QC frame, as today.

### M2.3 Tasks, acceptance and tests
| Task | Content | Acceptance (tests first, seen failing) | Phase | Size | Owner |
|---|---|---|---|---|---|
| M2-T1 | `lib/bidi_lines.py` + rewiring of caption grouping, stills, thumbnails | `test_bidi_lines.py` with a fixture table of ≥ 60 mixed lines giving the expected visual order per line. The table covers Egyptian Arabic with English terms, prices, doses «٥٠٠ mg», percentages, ranges, phone numbers, «الـ MRI», brackets, quotes, Arabic punctuation, and Latin-only and Arabic-only paragraphs. Named cases: an Arabic paragraph whose wrapped second line is all Latin stays RTL; «AI بيغيّر الطب» (Latin first) stays RTL (HL1); «blood sugar level» keeps its order inside an Arabic line (N1); Western digits after Arabic letters order as Arabic numbers (W2). Also no-break tests, a per-line reorder test (a run split across two lines keeps logical order on each), the expected order cross-checked against an independent UAX #9 implementation (licence-checked, test-only dependency), golden stills AR/mixed per look, and existing caption tests unchanged | 4 (with Task 23) | M | executor (module, `hb_text`/`previews`) + looks & motion track (fixture table, `looks_type`) |
| M2-T2 | Host text rule (marks or not) per host | Fixture lines built in Premiere (CEP now, UXP in Phase 6), AE and SRT played in Premiere: frames viewed, rule recorded per host; a test pins the rule | 4 (CEP, AE), 6 (UXP) | S–M | Adobe track + looks & motion track |
| M2-T3 | Whisper Latin terms: the three approaches measured; back-map + lexicon; skill text | Evidence file with the table (Latin-script accuracy, WER, CER, speed); the chosen approach meets the target; `test_latin_backmap.py` (glossary hit, low confidence → no proposal, context disagreement → no proposal, never auto-applied) | 4 (measure + engine) and 6B (Kalam path) | M | executor + tools track |
| M2-T4 | Font pairing module, table, client DB field, font chain hook | `test_font_pairing.py`: traits measured on tiny test fonts (fontTools-made); score bounds and weights; client pair always wins; < 50 never used; superfamily recognised; `latin_scale` aligns measured heights within 3 %; `test_looks_type` chain takes the pair first; specimen sheet viewed by brand-systems-designer (verdict recorded) | 4 (module, table draft) and 6 (AE/MOGRT use) | M | looks & motion track (module as `lib/looks_pairing.py`, under its `looks*.py`; `looks_type` chain hook) + brand-systems-designer (table) + wnc-queue track (`typography.pairing` field in `lib/client_db.py`, which it owns) + executor (`config/defaults/font-pairings.json`) |
| M2-T5 | QC: text expectations, read-back fonts, reference compare, checklists | Fixture builds with a wrong run order and a wrong Latin face are both caught with element id and time; correct builds pass on all QC frames; frame-inspector checklist named in `qc-craft` | 6 (needs read-back fields) | M | executor + Adobe track (read-back) |
| M2-T6 | Evals | Arabic prompt with a mixed clip → the transcript keeps Latin terms and the review sheet lists back-map proposals; "change the English font to match" → pairing command, score shown | 4/6 | S | executor |

**QC:** Gate 4 (M6 list) needs M2-T1, T3 (measured) and T4 (module and table draft) green, and the mixed fixture sheet
viewed. Gate 6 needs M2-T2 (all hosts incl. UXP) and T6, plus T5 live on a mixed reel in Premiere and AE. Phase 9 T9.2 (a)–(c) use a mixed clip from HM-1.

---

## M3. A rich, expressive, varied style that is never chaotic

### M3.1 Requirements
1. A strong **style family** ("expressive", working code `STYLE-X`; the final name is proposed by the brand-systems-designer
   and approved by Yunus, as for the looks) with deliberate variety in **fonts and motion**.
2. **Consistent within the brand:** only the client's colours, its fonts and their M2 pairs, its motion intensity.
3. **Never chaotic:** written limits on how much variety, where and why; measured by a linter and checked visually.
4. Linked to K-T10 (preset gallery), K-T14 (motion palette and history), K-T13 (kashida), R-6.1 (one motion law per look).

### M3.2 Design: the variety rules
Starting values below are the designer's first proposal; M3-T1 tunes them on real reels and records the final numbers and
their basis. The linter reads them from `config/defaults/style-rules.json`, so tuning needs no code.

**Type**
- At most 2 families per script per video: the brand face (its M2 pair) and one **accent** face from the same pairing
  class or a deliberate contrast class chosen by the designer for that client; at most 3 weights in total.
- The accent face appears only on emphasis roles (hook, key number, short quote, key term), at most ~20 % of on-screen
  words in a video; never on captions body, warnings, disclaimers, verses or legal lines.
- Kashida only on accent/display roles (K-T13), at most once per screen.

**Motion**
- Each video's palette (K-T14): one signature move (the hook and the payoff), two or three supporting moves, one
  transition family. Every animated element carries a reason tag: `emphasis`, `structure` (list, steps, comparison),
  `transition` or `brand`. A move with no reason is refused.
- **Where:** content type decides the move family: a list → staggered entries; a number → count-up or scale; a contrast
  → split or wipe; a quote → reveal; a warning or a sensitive line (medical warning, verse, legal) → calm (fade only, no
  SFX accents, the religious tone rule already in religious-content.md).
- **How much:** at most 2 animated elements at the same moment; the same move not on two consecutive beats unless it is a
  rhythmic pattern the plan declares; an energy curve per video (rises to the hook, lower in explanation, peak at the
  payoff); no animation inside 0.4 s of a cut unless it is the transition.
- **Across videos:** K-T14's history (no repeat of the last three videos' signature move).

**Colour**: only palette colours (ΔE ≤ 3 to a brand colour) plus neutral black/white; the accent colour on at most one
element per screen.

**Intensity levels**: `calm`, `balanced`, `expressive` per client (default from the client's reference style, R-4.6), and
per content type (a medical warning video caps at `balanced`).

### M3.3 Tasks, acceptance and tests
| Task | Content | Acceptance (tests first, seen failing) | Phase | Size | Owner |
|---|---|---|---|---|---|
| M3-T1 | Style family spec + rules file, designed with brand-systems-designer on three real `whynot-test` reels (one medical, one business, one religious) | Rules file with a basis per number; designer verdict on the three reels' contact sheets and motion strips: "rich, on-brand, not chaotic" (R2.7 distinctiveness too) | 6 (with R-6.1) | M | looks & motion track + brand-systems-designer |
| M3-T2 | `reel style-check <item>` linter over the timeline-spec / motion plan, called by `plan`, `motion-plan` and `qc` | `test_style_check.py`: a plan with 3 families, 4 weights, an accent on a warning, 3 simultaneous animations, a move with no reason, the same move on consecutive beats, an off-palette colour, a repeated signature move from history → each refused or warned per the rules file with the element id; the three M3-T1 reels pass | 6 | M | executor (engine) + looks & motion track (rules data) |
| M3-T3 | Visual QC: a motion strip (frames at each animation's start, middle, end) beside the contact sheet; graphic-checker checklist "variety where and why"; brand-systems-designer gate verdict | On the three reels the strips are viewed and the verdict recorded; a deliberately chaotic fixture plan is called chaotic | 6 | S–M | executor + looks & motion track |
| M3-T4 | Panel: intensity control and the style gallery entry (K-T10) | E-D2 mockup, E-D5 diff | 6 | S | Adobe track |

**QC at Gate 6:** M3-T1…T3 green; the Premium-bar design verdict covers the three reels.

---

## M4. B-roll sourcing with choice

### M4.1 Requirements
1. The editor can add B-roll from: **(0)** the client's own library (K-T16, always searched first); **(a)** free sources
   with licences that allow commercial use, with the licence recorded **per file**; **(b)** Magnific stock search and
   download; **(c)** AI generation.
2. For **every** AI generation, the plugin asks which model to use: a recommendation first, one short line per model
   (what it is good at, speed), the **estimated credit cost of this exact request** for each, the remaining reel budget
   (`max_credits`) and the account balance, and a **clear warning that credits will be consumed**, before anything is
   spent. "Decide together" is allowed: discussion first, still no spend without a final explicit yes.
3. Integrated with Phase 5: `asset_needs[]` and `max_credits` (T5.3), the spend guard (T5.5), the manifest (T5.4/T5.7),
   handoff licence rules (T5.8), and the policy "no people, no footage of real events, no claims" (T5.2).
4. Nothing paid without the editor's yes; with Magnific absent or unauthorised, sources 0 and (a) still work (graceful
   absence, Gate 5).

### M4.2 Design
**Order shown to the editor for each need:** client library → free stock → Magnific stock → AI generation. The lead
shows what each earlier source found («لقيت ٣ في مكتبة العميل و٥ مجاني؛ لسه عايز Magnific أو توليد؟») before offering a
paid or generative source.

**One manifest for every source.** `05_assets/magnific-manifest.json` becomes `05_assets/asset-manifest.json` (the old file
is still read). Each record keeps Appendix F's fields and adds: `source_type` (`client_library` | `free_stock` |
`magnific_stock` | `magnific_ai`), `provider`, `provider_item_id`, `page_url`, `licence {name, version, url, terms_sha256,
retrieved_at}`, `commercial_ok`, `attribution_required`, `attribution_text`, `restrictions` (people, trademarks,
sensitive use, model release status), `ai_generated`, `realistic` (feeds M1 `ai` disclosure), `model` and
`credits_estimate` / `credits_actual` for generations. The licence page text is saved under
`output/client_database/licences/<provider>/<sha256>.txt` (once per terms version), so the record proves what the terms
said on that day. Attribution lines flow into the publish package automatically.

**(a) Free sources.** Step 1 of M4-T2 picks the providers by reading each one's official licence and API terms, dated. A provider qualifies only when:
- commercial use is allowed;
- there is no attribution trap;
- it has an official free API;
- the terms allow use inside our tool.

Candidates to verify:
- Pexels and Pixabay (photo and video), with free API keys from the editor's own free account;
- Wikimedia Commons, which has per-file licences. Only CC0, public domain and CC BY are accepted by default; NC, ND and SA are excluded.

Requests reuse J-T1's fetch core: the OS trust store, size caps, no private addresses, exact URLs. They follow Addendum L's rules for keys and downloads. API keys live in the OS credential store (userConfig `sensitive`), never in client folders or logs.

**People.** People in stock are excluded by default for medical and religious clients, and never allowed for AI generation. The editor may allow them per need for non-sensitive clips. The provider APIs have no "no people" filter, so the engine enforces it: a local person/face detector runs on each candidate's preview frames before the candidate is shown. It reuses the detector behind `previews._face_center`, licence-checked, at a threshold measured on fixtures. A candidate with a person is dropped, and the count of drops is shown. Magnific stock searches use the same check, plus T5.6's `--people exclude` where the API offers it.

**(b) Magnific stock.** Correction to Phase 5's facts: the Magnific MCP now exposes `stock_search` (filters: content type,
`license: free | premium`, `ai_generated`, orientation, colour, video type) and `stock_download` (a signed download URL),
so stock no longer needs the REST key path of T5.6. The REST path stays as a fallback.
- **Cost is unknown until proven.** `stock_download` is not in `simulate_cost`'s tool list, so its cost cannot be
  estimated before the call. Until M4-T3 proves live (H1) that a stock download consumes no credits and no plan quota,
  `stock_download` and `stock_to_creation` are treated as **spend**:
  - one card and one single-use approval per item, as in (c);
  - a D6 batched per-reel approval does **not** cover them.

  If M4-T3 proves zero cost, the free tier may move to the batched approval. A `premium` item always needs its own card.
- **Licence and attribution.** M4-T3 records in `asset-craft` what attribution the free tier requires. The licence tier
  (`free` | `premium`), the attribution text and the item's `ai_generated` flag are copied into the manifest. That flag
  feeds M1's `ai` disclosure.
- **Searches default to `ai_generated: excluded`.** The editor can include AI-generated stock per need.
- **No client material leaves the machine through search.** `stock_search` accepts `imageBase64` and `imageCreationId`
  for visual search. The guard denies `imageBase64` always. It denies `imageCreationId` unless that creation is one of
  our own approved generated assets in the reel's manifest. A frame from the client's footage (a patient, the doctor)
  is never uploaded.

**(c) AI generation, every time.**
1. The need exists in the plan (`asset_needs[]`, kind `broll_still` or `broll_video`), its anchor is in the transcript,
   and sources 0, (a) and (b) were shown first.
2. Read-only calls (no spend): `images_models_list` / `video_models_list` (recommended models), `simulate_cost` for each
   candidate with the exact intended arguments (prompt, aspect ratio 9:16, duration, resolution, count),
   `account_balance`.
3. The **model card** (AskUserQuestion in chat; a dialog in the panel in Phase 6), Arabic first:
   - the recommended model first, marked «(مقترح)», with why it fits this need;
   - 2–3 alternatives, one line each (strength, speed);
   - for each: «التكلفة التقريبية: X كريدت» from `simulate_cost`;
   - the remaining reel budget and the account balance;
   - the warning, always: «⚠️ التوليد هيخصم حوالي X كريدت من رصيد Magnific بتاعك (الرصيد دلوقتي Y). مفيش أي خصم غير لما
     توافق.»;
   - options: each model · «نقرر مع بعض» · «مش عايز توليد».
4. On a yes, the lead records a **single-use generation approval**:
   `reel assets-approve-gen --by editor --need N03 --tool images_generate --slug <model> --args-sha <sha256> --estimate
   <credits> --count <n>`.
   - It is editor-only; the guard blocks subagents from recording it.
   - It expires after 30 minutes.
   - **`--args-sha`** is the sha256 of the call's arguments in canonical JSON, made by one engine function shared by the
     command and the guard:
     - the tool's input object, minus transport-only keys (listed in the function);
     - keys sorted;
     - no insignificant whitespace;
     - UTF-8, strings NFC-normalised;
     - integers as integers and other numbers in shortest round-trip form.
   - A `broll_video` need's approval carries T5.5's `allow_video: true`; a `broll_still` approval never does.
5. The **spend guard** (T5.5, extended) allows a generation call only when:
   - an unused approval matches the tool, the model slug and the arguments' sha256; and
   - the estimate fits both the need's `max_credits` and the reel budget.

   Otherwise it **denies** with the reason; it never asks again silently. The approval is consumed by the call.
   - **A failed call** (an error or a timeout) keeps its approval consumed until two checks pass. Generation is
     asynchronous, so a charge can land late. The approval is restored once, still within its 30 minutes, only when:
     - `creations_search`/`creation_status` shows that no creation came from that call; and
     - after a settle wait, the balance is unchanged.

     The settle wait can only be measured live (M4-T6, H1). **Until it is measured and recorded in `asset-craft`, an
     approval is never restored.** Every failed call then needs a new card and yes.

     Otherwise the approval stays consumed, and the spend is logged and shown.
   - Balance before and after is logged. `credits_actual` vs `credits_estimate` goes in the manifest; a difference over
     20 % is shown at the next card.
6. A retry, a variation, a re-prompt or an upscale of a generated asset is a **new** generation and gets a new card.
7. **Autopilot (`approval: auto`) never generates:** the rule "ask every time" overrides `approval: auto`; autopilot lists
   the need in `NEEDS-YOU.md` with the card's data instead.
8. If `simulate_cost` or the model list fails, no generation is offered (fail closed for spend), with a plain message.
9. **The guard denies by default.** A hook sees only the tool name, so the guard first decides whether a call is a
   Magnific call. **Each connector prefix is classified once** and recorded in `magnific-prefixes.json` as `magnific` or
   `other`:
   - The three prefixes named in Phase 5 are `magnific` from the start.
   - A connector UUID (G78) is classified at setup, or from its first identity call (`account_profile`, read-only).
     - Magnific's identity in the answer → `magnific`.
     - `other` is recorded **only on positive evidence**: the identity call answered and named a different service.
     - A failed or unknown identity call (offline, not signed in, an error, an unrecognised answer) leaves the prefix
       **unclassified**, so its catalogue names stay denied. Setup never marks a prefix `other` by default.
   - `magnific-prefixes.json` is written only by the engine (setup and the identity check). The guard blocks any agent
     edit, write or shell redirect to it, like the approval files.
   - Under a `magnific` prefix, every tool is a Magnific call.
   - Under an `other` prefix, nothing is a Magnific call, whatever its name. The Adobe connector's `video_metadata`
     shares a name with a Magnific tool and passes untouched.
   - Only under a prefix **not yet classified** does the pinned Magnific catalogue decide: a catalogue name is treated
     as a Magnific call (and denied unless allowlisted or approved) until that prefix is classified; any other name
     passes.
   - Only tools on a **read-only allowlist** pass without an approval:
     - `account_balance` and **`account_profile`**, which is the identity call that classifies a new prefix and so
       must never be denied;
     - `*_models_list|show` and `simulate_cost`;
     - `stock_search` (subject to rule (b)) and `stock_get|show`;
     - `creation_status` and `creations_get|show|wait|search`;
     - the other listings named in the guard.
   - Every other Magnific tool needs a matching approval or is denied, whether it is listed or not. Under a known
     `magnific` prefix, that includes names not in the catalogue. That covers today's
     credit tools (`images_variations`, `images_reimagine`, `images_restyle`, `video_upscale`, `video_speak`,
     `audio_music_generate`, `models3d_text_generate`, `stock_to_creation`, `flows_run`, `spaces_run` and the rest) and any tool
     the MCP adds later.
   - A test pins the guard's spend list to `simulate_cost`'s tool enum, so a new priced tool fails CI until it is
     classified. Another test checks that an unknown tool name under a `magnific` prefix is denied.
   - This works in bypass-permissions mode too, because a hook `deny` is not a prompt.

   **Amendments to Phase 5, stated explicitly:**
   - T5.5's `ask` branch becomes `deny` with the reason. A prompt from the host is not the per-generation card, and in
     bypass mode it may not appear at all.
   - T5.5's fixed spend list becomes deny-by-default with the read-only allowlist above.
   - D6's batched per-reel approval stays for deterministic, non-generative spend (upscale, cutout, vectorise of our
     own assets, and stock only once proven free). Every AI generation, and every stock item not proven free, needs its
     own card and approval.
10. The generated asset then follows T5.2/T5.7: no people or faces, sensitivity review for medical and religious clips,
    `ai_generated: true` and `realistic` set from the model's output type → M1's `ai` domain decides disclosure.

### M4.3 Tasks, acceptance and tests
| Task | Content | Acceptance (tests first, seen failing) | Phase | Size | Owner |
|---|---|---|---|---|---|
| M4-T1 | `asset-manifest.json` for all sources, licence snapshots, attribution into publish | `test_asset_manifest.py`: old manifest still read; every source type validates; a record without licence fields is refused; terms snapshot stored once per version; attribution line appears in the publish package; `transferable_to_client` rules from T5.8 unchanged | 5 | M | executor |
| M4-T2 | Free sources: provider check (step 1), connectors, keys in the credential store, people filter | Provider table with dated licence basis in `docs/legal/third-party-licences.md`; `test_free_stock.py` on recorded API responses (no live network in tests): NC/ND/SA items dropped, attribution captured, no key → plain how-to and the pipeline continues; a socket-guard test like J's; **people filter** on fixture preview images with and without people (person present → dropped and counted; detector licence recorded; threshold from fixtures) | 5 | M | executor (+ L review) |
| M4-T3 | Magnific stock via MCP | Mocked MCP tests: search defaults to `ai_generated: excluded`; download recorded with tier, attribution, terms and the item's `ai_generated`; guard: `stock_download` and `stock_to_creation` need a per-item approval (a batched approval does not cover them); a `premium` item never covered by a batch; `imageBase64` denied; `imageCreationId` denied unless it is an approved generated asset in the manifest. Live (H1): one free-tier stock item on a test client, balance and quota before and after recorded, manifest checked; the result decides whether free-tier stock may move to the batch | 5 | S–M | executor |
| M4-T4 | AI generation card + single-use approval + guard extension (deny-by-default, Phase 5 amendments) | `test_magnific_guard_gen.py`: no approval → deny; other slug → deny; changed arguments → deny; canonical JSON (key order, whitespace, NFC, number forms → one sha); second use → deny; expired → deny; failed call before the settle wait is measured → never restored; after it is measured, no creation and unchanged balance after the wait → approval restored once, otherwise consumed and logged; a late charge after a failed call is never followed by a second spend on the same approval; over need or reel budget → deny; `video_generate` without `allow_video` → deny; subagent recording → blocked; autopilot → no generation, NEEDS-YOU line; every prefix incl. G78 covered; **under a `magnific` prefix, `images_variations`, `images_reimagine`, `images_restyle`, `video_upscale`, `video_speak`, `audio_music_generate`, `stock_to_creation`, `flows_run`, `spaces_run` and the made-up name `zz_unknown_tool` → each deny without an approval**; `account_profile` under an unclassified UUID → allowed and classifies the prefix; a catalogue name (`images_generate`) under an unclassified UUID → deny; `video_metadata` under the Adobe connector's UUID (classified `other` from its identity answer) → passes untouched; the identity call fails at setup → the prefix stays unclassified → `images_generate` under it → deny; an agent edit of `magnific-prefixes.json` → blocked; a non-catalogue name under an unclassified UUID → passes; the spend list ≡ `simulate_cost`'s enum (pinned from a recorded catalogue, re-checked live at H1); deny works with bypass permissions (hook output, not a prompt). Evals (mocked Magnific): «ولّدلي بي رول لعيادة أسنان» → the card shows a recommendation, one line per model, credits per model and the warning **before** any generate call (tool_used graders: `simulate_cost` before `images_generate`, `assets-approve-gen` before `images_generate`); "decide together" → no spend until the final yes | 5 | M | executor |
| M4-T5 | Panel: source picker and model card dialog | E-D2 mockups, E-D5 diff; the dialog's numbers come from the engine/lead, never computed in the panel | 6 | S–M | Adobe track |
| M4-T6 | Live (H1 + a yes at that moment): one AI still on `example-clinic` | Card seen, credits before/after recorded, manifest complete, disclosure flag raised and resolved | 5 gate (or Not verified) | S | executor |

**QC at Gate 5:** M4-T1…T4 green; the whole pipeline with Magnific disabled still completes (sources 0 and a only); live
items recorded or listed under Not verified with the H item.

---

## M5. Token- and session-efficient by design

### M5.1 Requirements
1. A **measured baseline**: tokens per stage and per video today.
2. A **target budget per video**, per mode (single clip, podcast reel, motion video).
3. An **eval that fails** when a fixture video goes over its budget.
4. **Quality is never reduced to save tokens.** Every saving is measured on both axes: tokens down, quality not down.
5. A user makes a reasonable number of videos per Claude session; a usage limit never wastes finished work.

### M5.2 Baseline (provisional, measured 2026-10-16)
Measured by the plan session's read-only pass over this PC's Claude Code transcripts (355 sessions). Item ids are
anonymised, and the scripts and full table stay outside the repo; M5-T1 rebuilds the same numbers in the repo tool.

**Unit.** Token counts are reported raw (fresh input, cache write, cache read, output). They are also reported as one
**weighted** number: fresh input ×1, cache write ×1.25, cache read ×0.1, output ×5. These are the API's relative prices
within one model.
- **The weights are per model.** Each model's tokens are scaled by its price relative to the lead's model, so moving an
  agent to a cheaper tier (technique 3) shows up in the number. The report also prints the model mix (share of weighted
  tokens per model). The baseline below is lead-model-equivalent: all of its agents ran on today's models.
- **Assumption, labelled as one:** Claude plan usage limits track roughly with this cost-weighted number. Anthropic
  does not publish the limit formula. M5-T8 checks the assumption by counting how many clips one session really
  finishes (M5.3, "videos per session").

**Data quality.** It is thin, and the evidence file must say so. Only one real pipeline session exists. It holds 3
single clips, 1 podcast episode and 10 reels, all test runs made while the plugin was being fixed. Development turns
were removed (8.8 % of fresh+write+output), so the stage numbers are upper bounds. Token counts are de-duplicated by
message id: high confidence. Stage attribution follows the latest `reel` command: medium confidence.

| Measure | Single clip, raw → Premiere (n = 3) | Podcast reel, to plan (n = 8) |
|---|---|---|
| Fresh + cache write + output | median 260k (252k – 1.10M) | median 284k |
| Cache read | median 71M (56M – 169M) | median 5.9M |
| **Weighted** | **median 7.8M (6.2M – 19.6M)** | **1.28M + ~0.7M episode share ≈ 2.0M** |

A podcast reel built in Premiere and a motion video were never measured. M5-T1 measures them.

**Where it goes:**
- **The lead's context is the sink.**
  - Cache reads are 98 % of all tokens: the main conversation carries about 470k tokens into every turn. A story-editor
    turn carries about 113k, a proofreader turn about 5k.
  - Every loop the lead runs re-reads that whole context. That is why previews (12.3M weighted) and ppro-build (7.3M)
    rank high even though their command outputs are small.
- **Top stages by weighted tokens:** previews 12.3M, plan 12.2M, ppro-build 7.3M, transcript-correct 7.2M, audio-clean
  4.3M.
- **Large reads:**
  - Shell `cat`/`sed` reads of plugin and engine files: 158 reads, about 1.1M characters.
  - The episode transcript text (34.5k characters), read 4 times by subagents.
  - By contrast, all 160 `reel` command outputs together came to only 136k characters.
- **Subagents** carried 57 % of fresh+write+output but only 27 % of weighted tokens. Delegating is already the cheap
  path.
- **Projection, not a measurement:** with a lead context of about 110k per turn, the two cleaner clips would cost about
  1.5–1.9M weighted.

### M5.3 Budget
Provisional targets. They are re-measured on clean fixtures in M5-T1/T2 and fixed at Gate 6. After that a budget may
only tighten; loosening one needs a written reason in PROGRESS.md.

| Per video | Today (weighted) | Budget (weighted) | Stretch |
|---|---|---|---|
| Single clip, raw → Premiere project → QC | 7.8M median | **≤ 2.5M** (about −68 %) | 1.5M |
| Podcast reel, from the picked candidate → Premiere → QC (episode share included) | ≈ 2.0M to plan; build not measured | **≤ 2.5M** (set from M5-T1) | 1.5M |
| Motion video, script → AE render → QC | not measured | **set at Gate 6 from M5-T1** (no basis today; a placeholder of ≤ 3.5M is used only so the report-only eval prints a verdict) | — |

How the numbers read:
- **The podcast budget covers more work than today's figure.** It covers the whole path to a QC'd Premiere project,
  while today's ≈ 2.0M stops at the plan. A run that meets it may still cost more per reel than the plan stage does
  today. That is accepted, because the build and QC stages were never measured. M5-T1 replaces it with a measured
  number.
- **The eval statistic:** a mode passes when the **median of 3 runs** is ≤ its budget and **no single run** is over
  1.25× the budget.
- **Runs use the production model mix:** the agent models in the shipped frontmatter. A cheaper model used only in the
  eval never counts.

Guard rails, measured by the same tool:
- **Lead context:** during an edit the main conversation stays at or below about 150k tokens per turn. Subagent reports
  follow the existing report format and stay short.
- **Resume:** resuming one item after a usage limit costs ≤ 100k weighted (M5-T7).
- **Videos per session:** the number of clips one session can finish is reported from the measured per-clip cost
  (M5-T8). The target is at least 3× today's on the same plan. Claude plan limits are not published as token numbers, so
  this ratio, measured live in Phase 9, is the honest form of "a reasonable number of videos per session".

### M5.4 Techniques (each one lands with a before/after measurement and the quality evals)
0. **Keep the lead small (the biggest lever, from M5.2).** The lead orchestrates and decides; it does no reading
   that a subagent or a `reel` command can do.
   - Every stage that reads more than a summary runs in a subagent that returns the short report.
   - The lead never `cat`s or `sed`s plugin, engine or skill files: the skills already carry what the lead needs, and
     the M5-T6 hook notes it when it happens.
   - Preview/build/QC loops call commands that print a summary line and a path, never a dump.
   - The lead-context guard rail in M5.3 is measured in every budget eval.
1. **Deterministic work in the engine, not the LLM.** Everything that is a rule runs as a `reel` command and hands Claude
   findings, not raw data: review pre-scan (M1), risk words (K-T1), hook rules (K-T6), takes (K-T7), safe zones (K-T4),
   bidi lint (M2), style lint (M3), topic search (K-T11), B-roll search (K-T16).
2. **Compact artifacts instead of raw dumps.**
   - `reel brief <item>`: the item's state, key numbers, open issues and next step, **capped at 1,500 tokens**
     (enforced by `test_brief.py`). The lead reads this, not the JSON files;
   - `02_transcription/transcript.compact.md`: sentence ids + text, no per-word timing or probabilities (story-editor and
     reviewers read this; word timing stays in the engine);
   - checkers get slices (their 3–5 graphics, their 10-minute chunk), never the whole file;
   - command output is short JSON by default with `--verbose` for the full form; long outputs go to a file and the command
     prints the path and a summary.
3. **Cheaper models for mechanical steps, proven by evals.** For each candidate agent (segment-proofreader, frame-inspector,
   graphic-checker, moment-scout, intake-inspector, setup-doctor, publish-writer's checks), run its eval set on the current
   model and on the next cheaper tier (several candidates already run on Sonnet, so for them the cheaper tier is Haiku).
   Switch only when every grader holds (≥ 2/3, no case worse) and the live QC catch-rate on planted defects is equal.
   These stay on their current model as judgement steps: medical-reviewer, **claim-checker** (it checks medical, and now
   business and AI, claims against the transcript), story-editor, motion-director, qc-reviewer and episode-analyst. The
   decision table goes in the evidence file.
4. **No re-reading of big files.** Skills say "read once, then use `reel brief`"; a light PostToolUse hook notes a second
   full read of the same large file in a session (a one-line reminder, never a block); an eval checks no full transcript is
   read twice in the edit flow.
5. **Client-level cache.** `output/client_database/client-brief.md`, **capped at 1,000 tokens** (enforced by
   `test_client_brief.py`): brand, people (gender and honorifics),
   fonts and pairs, style family and intensity, standing rules, review domains. Built by the engine from the client DB,
   fingerprinted, rebuilt only when a source changes; every video and agent starts from it instead of reading the files.
6. **Batch mode.** Autopilot over several videos: the client brief loads once; engine stages (transcription, audio clean,
   previews, builds, renders) run as engine or wnc-queue jobs with zero tokens; per-video subagents get compact briefs;
   the lead handles decisions and approvals only.
7. **Progressive loading (D11).** Craft skills load only in their agents; references load on demand per stage; skill bodies
   are split so the lead reads the current stage's section; MCP tools stay limited to asset-scout (T3.3).
8. **Stop-and-resume checkpoint.** `output/projects/<ID>/run-state.json`: each finished stage with its input fingerprint
   and output paths; every stage idempotent. After a usage limit, `reel next` resumes at the first unfinished stage
   without re-analysis; engine jobs keep running during the limit. Resume cost is measured (target in M5.3).
9. **Prompt-cache friendly order.** Stable content (skill text, client brief) comes before changing content, so repeated
   turns read from the cache.

### M5.5 Tasks, acceptance and tests
| Task | Content | Acceptance | Phase | Size | Owner |
|---|---|---|---|---|---|
| M5-T1 | `tools/token_report.py`: reads Claude Code session transcripts (main + subagents), de-duplicates API responses by message id, attributes usage to stages by `reel` command markers, reports raw and weighted (M5.2 unit) per video and per stage plus the lead's per-turn context; the eval runner keeps each run's transcript (today only the grader sessions are kept) so usage per case can be measured; then clean fixture runs of the three modes (incl. a built podcast reel and a motion video, unmeasured today) replace the provisional baseline | Unit tests on recorded transcript fixtures (dedupe, subagent attribution, stage attribution, per-model weights and model mix, anonymised output: item ids only); the baseline evidence file regenerated from it | 4 (now) | M | executor |
| M5-T2 | Budget evals: three fixture runs per mode (short clip on `example-clinic`, one podcast reel from a 10-min fixture episode, one motion video) end to end in eval mode with the production model mix; pass = median of 3 ≤ budget and no run > 1.25× budget; quality graders in the same runs | The eval fails on a planted over-budget run and passes on the fixture; quality graders must pass in the same runs (a pass on tokens with a quality fail is a fail); the lead-context guard rail reported per run | 4 (report-only), binding from Gate 6 | M | executor |
| M5-T3 | Engine briefs: `reel brief`, `transcript.compact.md`, short JSON outputs, file-and-path for long outputs | `test_brief.py`: the brief is at most 1,500 tokens (counted with one pinned token estimator, named in the test; the same one `test_client_brief.py` uses) on the largest fixture, every field from engine data, Arabic intact, no client paths outside the client root; skills name them (`test_skill_text`) | 4 | M | executor |
| M5-T4 | Client brief cache, in a new `lib/client_brief.py` that reads the client DB through `client_db.py`'s public functions (no edit to that wnc-queue-owned file; a missing accessor is requested from wnc-queue) | `test_client_brief.py`: rebuilt on a source change only; at most 1,000 tokens on the largest fixture client; people gender never inferred (T1.7) | 4 | S | executor |
| M5-T5 | Model tiering by eval A/B | Evidence table per agent; agent frontmatter changed only where the rule holds; a regression eval per switched agent | 6 | M | executor |
| M5-T6 | Read-once reminder hook + eval | Hook latency < 50 ms; reminder appears on a second full read; never blocks; eval green | 4 | S | executor |
| M5-T7 | `run-state.json` + resume | `test_run_state.py`: kill after each stage → resume at the next stage with no repeated stage; changed input re-runs only the affected stages; a live usage-limit simulation in Phase 9 fault injection (G10 list) | 4–6 | M | executor |
| M5-T8 | Batch autopilot measurement | Phase 9: 5 clips in one session on this PC; tokens per clip and clips per session recorded against M5.3 | 9 | S | executor |

**The quality rule (binding).** A technique lands only when, on the same fixtures, every quality grader still passes at
≥ 2/3 runs with no case worse than before, QC catch-rates on planted defects are unchanged, and the live gate's frames
look the same. A token saving that lowers any of these is reverted, and the evidence file says so.

**QC:** Gate 4 (M6 list) needs M5-T1, T3 and T4 green, and records M5-T1's baseline and M5-T2 in report-only mode.
From Gate 6 on, the budget evals are binding and T6/T7 are green.
Gate 9 reports clips per session (M5-T8).

---

## M6. Placement summary
| Request | Phase 4: Gate 4 waits | Phase 4: lands if ready, else Phase 6 (no Gate 4 wait) | Phase 5 | Phase 6 / 6B | Phase 9 / 10 |
|---|---|---|---|---|---|
| M1 | T1, T2, T3, T5 (engine evals) | — | — | T4 (with K-T9), T5 (panel), T6 | live review on business and AI fixtures; guide chapter "review domains" |
| M2 | T1, T3 (measured), T4 (module + table draft) | T2 (CEP, AE), T6 | — | T2 (UXP), T4 (AE/MOGRT), T5; 6B: Kalam back-map | mixed clip in T9.2 (a)–(c); guide section on mixed text and fonts |
| M3 | — | — | — | T1–T4 | three-reel design verdict at the Premium bar |
| M4 | — | — | T1–T4, T6 | T5 | T9.2 (e) extended to all four sources; guide chapter on B-roll sources and credits |
| M5 | T1, T3, T4; T2 in report-only mode (recorded, not a pass/fail) | T6, T7 | — | T5, T2 binding, T7 if not landed | T8; fault injection "usage limit mid-edit" |

**The Gate 4 list is exactly the first column:** M1-T1, T2, T3, T5 (engine evals); M2-T1, T3, T4 (module and table draft); M5-T1, T3, T4; and M5-T2 recorded in report-only mode. Nothing else in M holds Gate 4. The M1, M2 and M5 "QC" lines above are read against this list.

**Rough effort** (agent working time):

| Part | Effort |
|---|---|
| M1 | 5–7 days |
| M2 | 7–9 days |
| M3 | 4–5 days |
| M4 | 5–6 days (more guard work after review: deny-by-default, per-item stock approval) |
| M5 | 6–8 days |

The work is spread over the executor, the looks & motion track, the wnc-queue track, the Adobe track and the tools track.

**The Gate 4 list adds about 12–16 agent-days.** About 9–11 of them fall on the executor's lane, so **Gate 4 moves by roughly 2–3 weeks**. The executor schedules this work after Tasks 31–38 (Addendum J) and Addendum L's tasks. Gate 4 waits for it because it is engine work Gate 4 already reviews. Yunus accepted this default on 2026-10-17 (M7). Moving the list to Gate 6 stays available as an overrule only. Plan task numbers are assigned by the executor at scheduling.

**LOCKED-AREAS additions** (the executor makes them in the commit that accepts this addendum):
- `lib/bidi_lines.py`: executor;
- `lib/looks_pairing.py`: looks & motion track, already covered by `looks*.py`;
- `lib/client_brief.py`: executor;
- the `typography.pairing` field in `lib/client_db.py`: wnc-queue.

## M7. Rulings Yunus may overrule, and human items
**Status (2026-10-17):** Yunus accepted every default below in chat («موافق على الافتراضي، كمّل»). In particular:
- Gate 4 waits for M's Gate 4 list (about 2–3 weeks more on the executor's lane);
- `review_detect: review`;
- autopilot never generates.

The human items HM-1 to HM-4 stay open. Until each is done, the "If not done" column applies.

| Ruling | Default | If Yunus overrules |
|---|---|---|
| Domains detected in the words but not in the profile are reviewed too | `review_detect: review` | `suggest` (listed, not reviewed) or `off` |
| Handoff and READY wait for every active domain to be clear; the build does not | On | The build also waits |
| `ai` disclosure is always on; `medical` review stays on for every client (as today) | On | Per-client setting for `ai`; `medical` stays always on (it is an existing guard) |
| Gate 4 waits for M's Gate 4 list (M6; about 2–3 weeks more on the executor's lane) | On | The list moves to Gate 6; Gate 4 keeps today's scope |
| Every AI generation and every stock download not proven free needs its own card and yes; the Magnific guard denies any tool not on the read-only allowlist | On | (no weaker rule is offered) |
| Autopilot never generates with AI, even with `approval: auto` | On | Autopilot may generate within a per-client credit cap he sets |
| A cheaper model replaces a stronger one only when every quality grader holds | On | (no weaker rule is offered) |
| Font pairs under 50 are never used automatically; the client's own pair always wins | On | — |

| ID | What only Yunus can do | Needed by | If not done |
|---|---|---|---|
| HM-1 | 3–5 short real mixed clips (Egyptian Arabic with 25–50 % English words), as copies in `whynot-test/`, ideally one medical, one business | M2-T3, Phase 9 | M2-T3 is measured on EP02 excerpts only and the target is marked "Not verified on mixed speech" |
| HM-2 | Free API keys from his own free accounts on the chosen free stock providers (after M4-T2 step 1 names them) | M4-T2 live | Free stock works only with recorded fixtures; live listed as Not verified |
| HM-3 | A yes at the moment of M4-T6's live AI generation (it spends a few Magnific credits) | Gate 5 | AI generation verified with mocks only |
| HM-4 | Approve the expressive style family's final name and the font-pairing table's specimen sheet | M3-T1, M2-T4 | Working codes stay; table used as the designer approved it |

(The executor renumbers HM-n into the next free H numbers when it commits; H1 is still needed for every live Magnific
item.)
