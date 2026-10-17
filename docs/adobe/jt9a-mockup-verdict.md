# J-T9a: "Set up a client" mockups — critique verdicts (Addendum J12, E-D2 / E-D3)

Task: J-T9a (Addendum J §J10, Phase 6, E-D2, Adobe track, P1). Hi-fi mockups of the five J12 screens before any screen
code, critiqued by the `brand-systems-designer` agent against the G2 design bar, plus a first-time Arabic editor round.
These are AI reviews, not a human designer's sign-off; the Arabic copy still needs a native writer.

**What was made** (all under `adobe/panel-ui/design/`):
- `screens/J-01-client-entry.html`, `J-02-client-folder.html`, `J-03-client-website.html`, `J-04-client-review.html`,
  `J-05-client-report.html`; `js/client-setup.js`, `css/client-setup.css`, `strings/client-setup.js` (EN + AR copy, sample
  data); the shared shell gained a Premiere host-theme frame (`?theme=dark|light`, `mockup.js` / `mockup.css`) and
  `_build/render_all.py` gained `<meta name="mock-themes">` and a manifest merge for `--only` runs; `_build/check_css.py`
  gained the C1.4 command rule and the J5.2 developer-word denylist for the new copy.
- Renders: `renders/J-0*/<state>-<lang>-<width>-<theme>.png` (300 / 360 / 480 px, AR + EN, Premiere Dark + Light), sheets
  in `renders/_sheets/J-0*`, rows in `manifest.csv`.

## Critique round 1 — designer, pass 1 (verbatim)

```
VERDICT: NOT YET

AI design review, not a human designer's sign-off. Arabic copy still needs a native writer. Most hard rules hold. No gender is pre-selected on J-04 normal, people or focus. The title list is off until a gender is picked, and then shows only that gender's titles. Copy stays off and says how many answers are left. The `untrusted` tagline shows `<img src=x onerror=alert(1)>` as plain text. The busy copy and button match the spec word for word. The J-01 empty state has one button. A grep of the strings file found no command, no "Claude Code" and no developer word. The P1s below are what block a pass.

1. **P1 · J-04 people / honorific / focus / long · AR + EN · all widths.** The person's name card shows the website's title as if it were the name: «د. هناء مصطفى» / "Dr. Hana Mostafa". Picking «الدكتورة» would then give «الدكتورة د. هناء مصطفى». The specialty is shown in the masculine form («استشاري الباطنة والسكر») outside the quote, while the quote itself says «استشارية». That is a gender signal shown as fact before the editor answers. **Fix:** in `CS_DATA.people`, set `ar:"هناء مصطفى"`, `en:"Hana Mostafa"` (same for Karim). Show the specialty without gender («الباطنة والسكر» / "Internal medicine and diabetes"). Keep every website title and gendered word only inside `CS.quote`. In J-05, drop the `.replace(/^د\. /,"")`.

2. **P1 · J-04 honorific / ready / photos (any state with a chosen gender) · all.** The chosen gender is hard to see. The selected segment is #383838 against #242424, a measured **1.32:1**, plus a muted-to-white text change. The 3:1 rule for control states fails on the most important answer on the screen. **Fix:** in `CS.gender`, add a 12 px `check` icon (`ink-text`) before the chosen label and keep the white text. Focus stays the border, so focus and selection never look alike. No new visual language: this is the S-09 "neutral plus mark" pattern.

3. **P1 · J-04 loading · AR + EN · all widths.** The skeleton is broken. The six section cards render as empty boxes; I sampled the pixels and found no skeleton bars inside them. The count line already says "Not decided 15" before anything has loaded. J-05 loading renders correctly. **Fix:** build each section skeleton like J-05's: `<div class="m-col m-grow">` + `M.skel(35)` + `M.skel(22,16)`, inside a box as tall as a closed section head. Hide `cs-counts` and `copy.undecided` while loading.

4. **P1 · Latin runs break across lines (rule 6).**
   - J-03 error-redirect, AR 360 and 300: the redirect host splits at the hyphen into «sahhaclinic-» / «eg.example», inside a security question.
   - J-04 summary: every path breaks, e.g. "assets/Logo/from-" / "website" at AR 300, and "assets/Fonts/" / "from-website" at AR 360.
   - J-04 long, AR 360: every source line is a 3-line URL.

   **Fix:** make `CS.host` and `M.path` one no-wrap run with a middle ellipsis (`M.mid`, the R3 S-13 rule). In the summary, put each path in a mono chip on its own row (direction §12). The source line shows only the host (`sites.google.com`), never the full path.

5. **P1 · J-02 long · AR · 360 and 300.** The clients-folder name is reordered: it renders as «· Clients 2026 / Medical and healthcare (Pegasus IMC Agency)», with the middle dot leading the line. **Fix:** print `C.root` as `M.ltr(C.root,"lat")` inside `.m-trunc` in `picked()` and `newForm()`, never through `M.txt`.

6. **P1 · J-03 every state with the form · AR + EN.** The privacy line over-claims: «مفيش أي حاجة عنك أو عن جهازك بتتبعت لأي حد» / "Nothing about you or this computer is sent anywhere." The website does receive the computer's address and a request. R3 removed claims like this. **Fix:** «بيقرا الموقع بس، زي زيارة عادية من المتصفح. WhyNot Cut مش بيبعت أي بيانات عنك لينا ولا لأي حد.» / "It only reads the site, like a normal browser visit. WhyNot Cut sends nothing about you to us or anyone else."

7. **P1 · Home empty state exists twice.** J-01 empty says «مفيش عميل مفتوح» + «إعداد عميل جديد». P-03 empty still says «لسه مفيش فولدر عميل» + «اختار فولدر العميل». J-T9c needs one Home empty state. **Fix:** make P-03 `empty` reuse J-01's `emptyState()`, or mark P-03 empty as replaced by J-01 in its header comment and in the manifest.

8. **P1 · J-05 no-website · AR + EN.** With the website skipped and assets/Fonts "Empty", the missing card still says "Brand font Gotham Rounded: ask the client…". That name can only come from the website. **Fix:** in `missing({skipped})`, show «لسه مفيش خط للهوية في assets/Fonts: اطلب ملفات الخط من العميل.» / "No brand font in assets/Fonts yet: ask the client for the font files."

9. **P2 · J-03 partial.** The counts contradict each other. The notice says 1 logo and 9 colours; the stage rows say "14 colours, 2 fonts" and "3 found". **Fix:** use the notice's counts in the partial stage rows.

10. **P2 · J-05 complete.** It says "Nothing's missing" while card 1 still shows fonts "1 name only" and card 2 still flags the misplaced file. **Fix:** in this state use data where the font was licensed and the file was moved.

11. **P2 · J-04 people conflict.** The difference between «مصطفى» and «مصطفي» is two dots in meta-size text, and only the brief's spelling is shown. **Fix:** show both spellings (site · brief), as J-05 does, and name the letter: «آخر حرف: ى على الموقع، ي في البريف».

12. **P2 · J-03 error-link.**
    - The same message appears twice (in the field card and under Fetch).
    - "clinic-name.com." ends with a period that reads as part of the address.
    - A typo turns the header red ("Needs you").

    **Fix:** keep only the field's line, drop the final period, and let a field-validation state leave the header pill alone.

13. **P2 · J-03 long · AR.** The link field cuts off the start of the address, so the host is hidden. **Fix:** `dir="ltr"`, left-aligned, ellipsis at the end.

14. **P2 · J-03 busy.** Skip is still live next to the one fix («استنى وجرّب تاني»). **Fix:** disable Skip and give the busy reason.

15. **P2 · J-05 has no busy state.** **Fix:** add `busy` (the report and the hand-over both write to the client folder).

16. **P2 · J-05 loading and error.** The disabled "Add what's missing" has no reason line (R3 S-12), and on loading it chooses the next step before the data exists. **Fix:** loading shows a disabled neutral button; error adds «جرّب تاني الأول.».

17. **P2 · Arabic number agreement.** «اتستخدم 9 مرة / 4 مرة» should be «9 مرات / 4 مرات». «7 ملف في assets» should be «7 ملفات». The section count «2 لسه» should be «لسه 2». Native writer to confirm.

18. **P2 · J-05 hand-over copy.** "…finishes the profile: names, titles…" suggests Claude decides names and titles. **Fix:** «…بيكمّل ملف العميل بالأسماء والألقاب اللي إنت أكدتها، وستايل المونتاج.»

19. **P2 · J-05 no-website copy.** It tells the editor to reopen «إعداد عميل جديد» for an existing client. **Fix:** «…افتح «إعداد عميل جديد» واختار نفس الفولدر.» Also use «ملفات العميل» in card 4's title instead of «ملفاتك».

20. **P2 · J-02 states.**
    - `new`: the trust line about not changing existing files doesn't apply to a new folder.
    - `error-exists`: there is no way forward with a different name. Add «أو غيّر الاسم».
    - `error-inside`: the primary button repeats the "Pick the client's folder" choice shown below it.

21. **P2 · J-01 normal.** Home is shortened: no Tools section and no week line, so the position of the Clients section is undefined. **Fix:** render the full P-03 Home and say where Clients sits.

Does it look like a $1,000/month product? Not yet. It is close, and every gap is fixable.
- For: it uses only the shared shell (one violet fill per screen, verified on the states I opened). The trust lines say what is never touched. The safety design is right: a confirm-summary with the keycap on the safe button, conflicts flagged but never auto-resolved, and website text shown inert. The 62 states cover the full G2 list, and the Arabic reads as natural Egyptian.
- Against: a premium product doesn't ship a loading skeleton that renders empty boxes. It doesn't split a security prompt's host across a line break or reorder a folder path in Arabic. It doesn't make the gender answer hard to see, or show a website title as the person's name on the one screen built to keep the website out of that decision.

Fix the 8 P1s and this group reaches the level of the R3-fixed P-07.
```
(The reviewer also listed the render files it opened and what it could not check: 480 px in detail, light theme beyond
samples, the G2 two-reference-panel side-by-side, motion / hover / real UXP paint.)

### What changed after pass 1 (all 21 findings)
| # | Fix |
|---|---|
| 1 | People data: the name without any title (هناء مصطفى / Hana Mostafa), the specialty without a gendered form; the site's title and gendered words only inside the «من الموقع» quote; J-05 no longer strips a title |
| 2 | The chosen gender carries a 12 px check mark + white label (`CS.gender`, `.cs-seglbl`); focus stays the border |
| 3 | J-04 loading: skeleton bars inside section heads of the real height; the bar shows only the off Copy button |
| 4 | `CS.host` = one no-wrap run with a middle ellipsis; source lines show the host only (`CS.hostOf`); the reading URL is truncated; the summary lists a count per bullet and the folder as a mono chip on its own row |
| 5 | J-02: the clients-folder name is an LTR isolate in `.m-trunc` (picked, new) |
| 6 | Privacy line replaced with the reviewer's wording (EN + AR) |
| 7 | P-03 `empty` now draws the J12 empty state (same copy, one button); J-01 says it replaces P-03 empty |
| 8 | J-05 no-website: "No brand font in assets/Fonts yet: ask the client for the font files" |
| 9–21 | Partial counts consistent; J-05 complete consistent; both spellings + "the last letter differs"; error-link = one field line, neutral icon, no trailing period, Fetch has its own reason; link value LTR, ellipsis at the end; J-03 busy: Skip off with the reason; J-05 `busy` added; J-05 loading / error: a neutral off "Next step" with why; AR number agreement; hand-over copy names "the names and titles you confirmed"; no-website copy + card 4 title; J-02 new trust line, "If not, change the name", error-inside alternative; J-01 normal = the full P-03 Home with Clients between Tools and Settings |

Re-rendered the changed screens only (all J-0x, 756 renders, and P-03, 72 renders), 0 failed.

## Critique round 1 — designer, pass 2 (verbatim)

```
VERDICT: PASS
J-T9a pass 2 (AI design review, not a human designer's sign-off; the Arabic still needs the native-writer pass).

All 8 P1s from pass 1 are fixed. I checked each one on the re-renders:
- 1: names have no title. Specialty is ungendered («الباطنة والسكر» / "Internal medicine and diabetes"). The website's gendered title appears only inside the «من الموقع» quote. Checked J-04 people/honorific AR 360, EN 360, EN 300 light.
- 2: the chosen gender now has a check mark and a white label («أنثى ✓» / "✓ Female"), so it no longer depends on the 1.32:1 fill change. Nothing is chosen in normal, people or focus.
- 3: J-04 loading shows skeleton bars in every section head. The bar shows only the off Copy button, with no counts.
- 4: the redirect host «sahhaclinic-eg.example» stays on one line at AR 300 and 360. In the J-04 summary every folder is a mono chip on its own row at AR 300 and 360, with no breaks. In J-04 long the source lines show only "sites.google.com".
- 5: the J-02 long folder name is no longer reordered (AR 300 and 360).
- 6: the privacy line now reads «…زي زيارة عادية من المتصفح. WhyNot Cut مش بيبعت أي بيانات عنك لينا ولا لأي حد.» (strings checked).
- 7: P-03 empty now uses the J12 empty state with one button.
- 8: J-05 no-website now says «لسه مفيش خط للهوية في assets/Fonts…».

The P2s I checked are also fixed:
- J-03: error-link, long (LTR, left-aligned, ellipsis at the end), busy (Skip off with its reason).
- J-05: busy, loading ("الخطوة الجاية" with its reason), error («دوس «جرّب تاني» الأول»), complete (now consistent).
- J-02 error-inside.
- J-01 normal is the full Home, with Clients between Tools and Settings.
- AR number agreement in the strings.

Remaining findings (polish only, none blocking):
1. P2 · J-02 long / picked · AR 300 and 360: the clients-folder name is cut from the START («...thcare (Pegasus IMC Agency)»), which hides "Clients 2026 · Medical". Fix: inside the `.m-trunc` isolate set dir=ltr, text-align:left, ellipsis at the end (the same fix as the J-03 link field), or use `M.mid`.
2. P2 · P-03 empty · AR 360: the header context line still says «مفيش فيديو مختار» while the card says «مفيش عميل مفتوح». Fix: set `noclient` there so it reads «مفيش عميل مفتوح», like J-01 empty.
3. P2 · `cs.ppl.spell` and `cs.rep.c.name` AR: «و {b}» puts a space after «و» before an Arabic name. The rule's space is only for Latin words. Fix: «و{b}» when {b} is Arabic. Native writer to confirm.

Not checked:
- 480 px in detail.
- Every light-theme state (I opened EN 300 light).
- The G2 side-by-side against two reference panels.
- Real UXP paint and motion.
- The self-check output for the J screens (no manifest rows).

Does it look like a $1,000/month product? Yes, as a mockup set, with the not-checked items above still open.
- It uses only the shared shell: one violet fill per screen and quiet amber/pink status.
- The decision with consequences is clear: the gender answer is visible, never pre-selected, and kept apart from the quoted website text.
- The summary dialog lists exactly what will be added and where, as one chip per folder, with the keycap on the safe button.
- All 63 states are drawn, including skeletons, busy, offline and no-Claude.
- Hosts and paths now hold together in Arabic at 300 px, which is where the first pass failed.
The real panel still has to prove the same in UXP (J-T9c, E-D5).
```
(Note on "no manifest rows": the reviewer read the committed `manifest.csv`; the J rows are in this task's commit, 756
rows, every one `ok=yes`.)

### Polish after pass 2 (the three P2s)
- J-02: the clients-folder name is LTR, left-aligned and cut at its end (`.cs-ltrval`).
- P-03 / J-01 empty: the header line says «مفيش عميل مفتوح» (the shell's new `view.noclientKey`).
- «و» joins an Arabic name with no space (`cs.ppl.spell`, `cs.rep.c.name`).

## Critique round 2 — first-time Arabic editor (verbatim)

Reviewer: an AI agent role-playing a 24-year-old, non-technical Egyptian agency editor, walking the flow on the AR renders
(dark, 360 and 300 px). Brief: the full J12 journey, one client with a website.

```
VERDICT: NOT YET

الفلو نفسه واضح وكنت هعرف أكمّله لآخره. اللي مانعني أشتغل بيه على عميل حقيقي النهارده: سطر بايظ ظاهر في شاشة قراية الموقع، وكام جملة بتطلب مني قرار مش لاقي له زرار أو بتخوّفني على ملفات العميل.
(The flow is clear and I could finish it. What stops me today: one broken line on the main fetching screen, and a few lines that ask for a decision with no button for it, or that scare me about the client's files.)

## P1: «مش فاهم» أو ممكن أعمل حاجة غلط

1. J-03 `fetching`، عرض 360 و 300
- تحت «بنقرا صفحة 3 من 6» مكتوب حرفياً `[object Object]`.
- فهمت إيه: افتكرت البرنامج ضرب. (I thought the tool had crashed.)
- السبب: `screens/J-03-client-website.html` سطر 69 بيلزق ناتج `CS.host(o.url, 40)` جوّه النص مباشرةً. الدالة دي بترجع `M.html(...)`، وده كائن (object) مش نص (string).
- التصليح: يتعرض الرابط `sahha-clinic.example/about` كنص.

2. J-03 `error-proxy`، عرض 360
- النص: «البروكسي بتاع الشبكة محتاج تسجيل دخول.»
- فهمت إيه: معرفش يعني إيه بروكسي. وافتكرت إن أنا اللي لازم أسجّل دخول في حتة، ومش عارف فين. (I don't know "proxy"; I thought I had to log in somewhere.)
- البديل: «شبكة المكتب مانعة WhyNot Cut يفتح المواقع.»
- وسطر تحتها: «اسأل مسؤول الشبكة أو الـ IT في الشركة، أو اطلب ملفات الهوية من العميل وكمّل من غير الموقع.»

3. J-04 `colours` و `normal` (اللوجو)، وكمان J-05 `normal`، عرض 360
- النصوص:
  - «قريب من #2BB5A8 اللي في colors.txt بس مش هو. مين الصح؟»
  - «شبه اللوجو اللي في assets/Logo بس مش هو.»
  - وفي التقرير: «ملفات العميل هي اللي بتكسب: ما اتغيّرش حاجة. القرار ليك.»
- فهمت إيه: البرنامج بيسألني مين الصح، والزرارين الوحيدين ✓ و ✕. خفت إن ✓ يكتب لون الموقع فوق اللون اللي في colors.txt. وجملة «القرار ليك» مش بتقولّي أعمل إيه. (I feared ✓ overwrites colors.txt; "your call" gives me no action.)
- البديل في المراجعة: «قريب من #2BB5A8 اللي في colors.txt بس مش هو. ✓ بيضيف لون الموقع جنبه، ومش بيغيّر colors.txt. لو مش متأكد، اسأل العميل.»
- ونفس الفكرة للوجو: «✓ بيضيف لوجو الموقع جنبه، ومش بيغيّر اللي في assets/Logo.»
- البديل في التقرير: «ما غيّرناش أي حاجة في ملفات العميل. لو الموقع هو الصح، اتأكد من العميل وصلّح الملف بنفسك.»

4. J-04 `summary`، عرض 360
- النص: «الصور اللي ما اخترتهاش بتتمسح من نسخة الموقع.»
- فهمت إيه: كلمة «بتتمسح» وقّفتني قبل ما أدوس «انسخ». افتكرت إن صور هتتمسح من فولدر العميل. ومش عارف يعني إيه «نسخة الموقع». (I read "deleted" and thought client photos would be deleted.)
- البديل: «الصور اللي رفضتها مش هتتحفظ. دي نسخة اتنزلت من الموقع بس، مش من ملفات العميل.»

5. J-04 `error-changed` و `error-stale`، عرض 360
- النصوص: «اقرا الموقع تاني» و «افتح الأحدث».
- فهمت إيه: أنا أكدت ورفضت 15 حاجة، واخترت النوع واللقب. هل كل ده هيضيع ولا هيفضل؟ ماحدش قالّي، فهتردد قبل ما أدوس. (Will my 15 decisions be lost? Nothing says.)
- البديل حسب اللي بيحصل فعلاً، فلازم الفريق يأكد أنهي واحدة صح:
  - لو الاختيارات بتتحفظ: «اختياراتك هتفضل زي ما هي في الحاجات اللي ما اتغيّرتش.»
  - لو مش بتتحفظ: «هتراجع من الأول، عشان اللي على الموقع اتغيّر.»

## P2: تلميع الكلام

6. J-02 `normal`:
   - «لو العميل عنده فولدر. هنعمل الفولدرات الناقصة بس.» جملة ناقصة. الأحسن: «لو للعميل فولدر بالفعل. هنضيف الفولدرات الناقصة بس.»
   - «اسم ومكان. بيتعمل في فولدر العملاء…» الأحسن: «هتكتب اسم العميل، والفولدر بيتعمل جوّه فولدر العملاء، إلا لو اخترت مكان تاني.»
7. J-02 `picked` و `new`: «أسماء البروجكتات والسيكوينسات هتبدأ بـ SC.» SC جت منين؟ وأقدر أغيّرها؟ الأحسن: «أسماء البروجكتات والسيكوينسات هتبدأ بـ SC (أول حروف اسم العميل).»
8. رسالة «في جلسة Claude شغالة» (J-02، J-03، J-04، J-05 `busy`):
   - «في جلسة Claude شغالة…» بتتقري كأنها «جوّه جلسة». الأحسن: «فيه جلسة Claude شغالة على العميل ده دلوقتي».
   - زرار «استنى وجرّب تاني»: أدوسه دلوقتي ولا أستنى؟ الأحسن: «جرّب تاني».
9. J-03 كل الحالات: «تخطي» بتتقري كأنها اسم مش أمر. ونفس الشاشة فيها «كمّل من غير الموقع» في الأخطاء، فالأحسن توحيدهم: «كمّل من غير الموقع». وسطر الشرح: «بيوديك على التقرير على طول. تقدر تقرا الموقع بعدين.»
10. J-03 `error-certificate`:
    - «وفي الوقت ده اطلب ملفات الهوية» تقيلة. الأحسن: «وعلى ما يتحل، اطلب ملفات الهوية من العميل.»
    - العنوان الأحسن: «جهازك مش قادر يتأكد إن الموقع ده آمن.»
11. J-03 `error-js`: «…ما نقدرش نقراها من غير متصفح.» خلّتني أسأل: طب ما أفتحه أنا في المتصفح؟ الأحسن: «الموقع ده معمول بطريقة WhyNot Cut ما يعرفش يقراها.»
12. J-03 `error-redirect`: زرار «لأ» بيعمل إيه؟ الأحسن: «لأ، وقّف».
13. J-03 `partial`:
    - «وقفنا عند الحد (3 دقايق)» الأحسن: «الوقت المسموح (3 دقايق) خلص بعد 4 صفحات.»
    - «راجع اللي اتلقى» الأحسن: «راجع اللي لقيناه».
14. J-04:
    - «حاد في أي مقاس» الأحسن: «واضح في أي مقاس».
    - «لون جاهز من قالب الموقع» الأحسن: «لون جاهز من قالب الموقع، غالباً مش من هوية العميل».
    - «اتقرا النهارده الساعة 14:32» الأحسن: «اتقرا النهارده 2:32 الضهر».
15. J-04 `people`:
    - «النوع: فاضل 2» الأحسن: «لسه محتاج تختار النوع لـ 2».
    - «جاوب على النوع لكل شخص الأول»: لو رفضت دكتور ✕، لازم برضه أختار نوعه؟ لو لأ، الأحسن: «جاوب على النوع لكل شخص أكدته (فاضل {n}).»
    - «مش معروف»: الكابشن هيعمل إيه ساعتها؟ محتاج سطر صغير تحت الاختيارات يشرح ده، والفريق يأكد السلوك الحقيقي الأول.
16. J-04 `photos`: النقطة «·» بتنزل لوحدها في أول السطر في «· فيها وش» و «· مفيهاش وش» على عرض 360. ده مشكلة شكل مش كلام.
17. J-05:
    - «اللي في assets و data، ومتنظّم إزاي» الأحسن: «إيه اللي في فولدر العميل».
    - «1 بالاسم بس» الأحسن: «1 لقينا اسمه بس، من غير ملف».
18. J-05 `no-website`: «افتح «إعداد عميل جديد» واختار نفس الفولدر» خوّفتني إنه يعمل عميل تاني. الأحسن أزوّد: «… ومش هيعمل عميل تاني ولا هيلمس ملفاته.»
19. J-05 `handover-sent` و `no-claude`:
    - «أول ما تفتحه» مش واضح بيرجع على مين. الأحسن: «أول ما تفتح Claude».
    - «الطلب هيستناه» الأحسن: «الطلب محفوظ ومستنيه. سجّل دخول في Claude وافتحه، وهو هيكمّل.»
    - الشارة فوق لسه مكتوب فيها «محتاج مراجعة» بعد ما خلصت كل حاجة. لو السبب الاختلافات الـ 3، الأحسن تبقى «خلص · فيه 3 اختلافات».

## اللي عجبني
- الطمأنة في كل خطوة شغالة فعلاً، زي «مفيش أي حاجة موجودة في الفولدر هتتغيّر أو تتنقل أو تتمسح» و «ملفات العميل ما بتتلمسش». ده اللي خلّاني أدوس من غير خوف.
- النوع واللقب معمولين صح: بيوريني كلام الموقع نفسه «الدكتورة هناء مصطفى…» كدليل، ومش بيخمّن، وقايمة الألقاب مش بتفتح غير لما أختار النوع.
- أغلب رسايل الأخطاء بتقولّي أعمل إيه، ومعاها زرار واحد واضح زي «كمّل من غير الموقع» و «صلّح التثبيت».
- كلام الموقع المشبوه (`<img onerror>`) ظهر كنص عادي، فقدرت أرفضه.
- العربي مصري وطبيعي في أغلب الشاشات، والعرض 300 مقروء من غير ما حاجة تتقص.
```
(The reviewer also listed every render it opened: all the J-01..J-05 states named in its brief, AR dark, 360 and some 300.)

### Round 2 fixes
| # | Finding | Fix |
|---|---|---|
| 1 | `[object Object]` under «بنقرا صفحة 3 من 6» | Real bug (a markup object pasted into a string). Fixed: the page address is an LTR no-wrap run with a middle ellipsis. **Guard added:** the shell's self-check now counts "[object Object]" in a panel's text (`objtext`) and `render_all.py` fails the render; proven by re-planting the bug (1 render failed) and removing it (0 failed) |
| 2 | «البروكسي» unknown | «شبكة المكتب محتاجة تسجيل دخول عشان WhyNot Cut يفتح المواقع.» (same J2 meaning: the network needs a login; no "proxy"), with the existing sub (ask the client for the brand files, carry on without the website) |
| 3 | ✓ on a conflict could overwrite? «القرار ليك» gives no action | Colour: «… ✓ بيضيف لون الموقع جنبه، ومش بيغيّر colors.txt. لو مش متأكد، اسأل العميل.»; logo: «… ✓ بيضيف ده جنبه، واللوجو بتاعك بيفضل زي ما هو.»; report: «ما غيّرناش أي حاجة في ملفات العميل. لو الموقع هو الصح، اتأكد من العميل وصلّح الملف بنفسك.» |
| 4 | «بتتمسح» in the summary scared | «… الصور اللي ما أكدتهاش مش هتتحفظ: دي نسخة اتنزلت من الموقع بس، مش من ملفات العميل.» |
| 5 | Are my decisions kept after a re-read? | The honest default until J-T9b decides otherwise: «… هتراجعها من الأول، عشان اللي على الموقع اتغيّر.» / «… هتراجعه من الأول.» **Engine-data item for J-T9b:** if `brand.candidates` can carry decisions forward for items whose sha256 did not change, the copy becomes «اختياراتك هتفضل زي ما هي في الحاجات اللي ما اتغيّرتش.» |
| 6, 7 | J-02 sentences; where SC comes from | Both subs rewritten as proposed; «(أول حروف اسم العميل)» added |
| 8 | «في جلسة» / «استنى وجرّب تاني» | **Kept** (J12 gives both verbatim, and «في» is the common Egyptian spelling of «فيه»). The sub now says when to press: «لما Claude يخلص، دوس «استنى وجرّب تاني».» For the native writer: the spec owner may switch to «فيه». |
| 9 | «تخطي» → «كمّل من غير الموقع» | **Kept** «تخطي» (J12's label); its line already says what it does. Native writer / spec owner to decide |
| 10 | certificate | «وعلى ما يتحل اطلب ملفات الهوية من العميل.»; the title **kept** (J2.3 verbatim) |
| 11 | JS site | «الموقع ده معمول بطريقة WhyNot Cut ما يقدرش يقراها، حتى لو بيفتح عادي في المتصفح.» |
| 12 | redirect «لأ» | «لأ، وقّف» / "No, stop" |
| 13 | partial | «الوقت المسموح (3 دقايق) خلص بعد 4 صفحات.»; «راجع اللي لقيناه» |
| 14 | J-04 words | «واضح في أي مقاس»; the template colour gets a line «غالباً مش من هوية العميل.» (the chip stays short for 300 px); 24-hour time **kept** (every mockup uses it; panel-wide decision) |
| 15 | people | «اختار النوع: فاضل {n}»; «جاوب على النوع لكل شخص ما رفضتوش (فاضل {n}).» (a rejected person needs no answer, as built); the why line now says what «مش معروف» does: no gendered title for that person (people.py's rule) |
| 16 | «·» starting a line | No-break spaces round the dot in the photo meta |
| 17 | J-05 words | «إيه اللي في فولدر العميل، ومتنظّم إزاي»; «{n} بالاسم بس، من غير ملف» |
| 18 | no-website scare | «… مش هيعمل عميل تاني ولا هيلمس ملفاته.» |
| 19 | hand-over wording; header after done | «تمام. أول ما تفتح Claude، هيكمّل ملف العميل.»; «الطلب محفوظ ومستنيه. سجّل دخول في Claude وافتحه، وهو هيكمّل.»; handover-sent header: «خلص · فيه 3 اختلافات» (amber stays: the differences are still open) |

Re-rendered the changed screens (all J-0x, 756, and P-03, 72), 0 failed.

## Critique round 2 — first-time Arabic editor, pass 2 (verbatim)

```
VERDICT: YES (J-T9a round 2, pass 2). All 5 P1s are fixed in the renders. No P1 left; 4 small P2s, all layout or line-break, none about meaning.

P1 check, all OK:
- [object Object] gone. J-03 fetching at 360 and 300 now shows sahha-clinic.example/about.
- Proxy now reads «شبكة المكتب محتاجة تسجيل دخول عشان WhyNot Cut يفتح المواقع.» I understand it now.
- Colour, logo and report conflicts now say what ✓ does and that nothing is overwritten.
- Summary photos: no more «بتتمسح». Clear and calm now.
- error-changed / error-stale: «هتراجعها من الأول» is honest. I know my choices won't carry over.

Remaining P2:
1. J-05 normal at 300 (360 too tight): the fonts row overlaps. «لقينا 2 · اتنسخ 1 · 1 بالاسم بس، من غير ملف» runs under the label «الخطوط», and «لقينا 2» is hidden. Fix: shorten cs.rep.fcn to «لقينا {f} · اتنسخ {c} · {n} من غير ملف», or let the meta wrap below the label when it doesn't fit.
2. J-04 photos at 360: the size line now breaks inside the dimensions: «× 1600» on one line, then «2000 بكسل · فيها وش». Fix: make the dimensions and «بكسل» non-breaking and allow the break only after the dot: "{w} × {h} بكسل · فيها وش". Same for cs.photo.noface.
3. J-04 colours at 360: ✓ wraps away from its verb. Line 1 ends «…بس مش هو. ✓» and line 2 starts «بيضيف لون الموقع…». Fix: "✓ بيضيف" in cs.colour.close and cs.conf.logo.
4. J-02 picked at 360: the parent path «WhyNot Clients» under «Sahha Clinic» is no longer start-aligned (right in RTL). It floats toward the middle, probably from the new end-truncation. Fix: keep it start-aligned (text-align:start / dir=auto inside a right-aligned block) and truncate at its end.
5. Optional: J-03 error-proxy. Who logs in? Add one line: «لو مش عارف تسجّل دخول فين، اسأل مسؤول الـ IT في الشركة.»

Fine as kept: «في جلسة Claude…» with the new sub «لما Claude يخلص، دوس «استنى وجرّب تاني».», «تخطي», the certificate title, and 24-hour time. The «مش معروف» explanation is clear. «لأ، وقّف», «راجع اللي لقيناه», «الوقت المسموح (3 دقايق) خلص», «خلص · فيه 3 اختلافات», «تمام. أول ما تفتح Claude، هيكمّل ملف العميل.», «الطلب محفوظ ومستنيه», and «مش هيعمل عميل تاني ولا هيلمس ملفاته» are all good.
```

## Critique round 1 — designer, final confirmation after round 2 (verbatim)

```
VERDICT: PASS
J-T9a final confirmation pass (AI design review, not a human designer's sign-off; the Arabic still needs the native-writer pass).

Checked on the new renders:
- J-03 fetching, AR and EN 300: «بنقرا صفحة 3 من 6» / "Reading page 3 of 6" with the page address under it. No `[object Object]`.
- Manifest: all 756 J rows are ok=yes with an empty problems column.
- J-02 long, AR 300: the folder name is cut at the end («Clients 2026 · Medical a…»).
- P-03 empty, AR 360: the header says «مفيش عميل مفتوح».
- J-04 colours, AR 300 and 360: the conflict line says what ✓ does. The template colour has a meta line («غالباً مش من هوية العميل.»). «9 مرات / 4 مرات» are right.
- J-04 people, AR 300 and 360: «مش معروف» is explained under the gender choice. Nothing is pre-selected. Names have no title. The spelling conflict reads «هناء مصطفى على الموقع، وهناء مصطفي…» with no space after «و».
- J-04 summary, AR 300: one folder chip per row, plus the new photo sentence.
- J-05 handover-sent, AR 360: the header pill says «خلص · فيه 3 اختلافات» in amber, so it doesn't read "All set" over the 3 conflicts. Back to Home is the only button.
- J-05 normal, AR 360: the conflicts card wording is fine.
- One light render per screen: J-01 offline AR 360, J-02 busy EN 360, J-03 error-certificate AR 300, J-04 ready AR 480, J-05 no-claude EN 360. Only the host bar changes; the panel is the same.

Findings (polish only, none blocking):
1. P2 · J-04 photos · AR 300 (new since the no-break dot change). The size now splits at the ×: «1600 ×» / «2000 بكسل · فيها وش». Same for 900 × 1200 and 1920 × 1080. Fix: put no-break spaces around «×» in `cs.photo.face` / `cs.photo.noface`, so «1600 × 2000 بكسل» is one unit. Leave a normal space after the «·» so the line can break there.
2. P2 · ✓ inside Arabic sentences (`cs.rev.sub`, the new colour/logo conflict lines) · AR 300 and 360. The text ✓ looks like a radical sign «√» in the Arabic font, while the buttons use the Lucide check. Fix: use the words («أكّد» / «ارفض»), or put the 12 px `check` / `x` icon inline. Don't rely on the Unicode character. (At this zoom I'm not certain of the glyph. Please confirm on a full-size crop.)

Not checked:
- 480 beyond one render.
- The 72 P-03 renders other than empty AR 360.
- The first-time-editor round's other copy changes beyond the states named above (proxy, re-read and redirect wording not viewed).
- Real UXP paint and motion.
- The G2 side-by-side against two reference panels.

Does it look like a $1,000/month product? Yes, as a mockup set, with the G2 two-reference-panel side-by-side still not done.
- One visual language with one violet fill per screen.
- The gender answer is clear and never pre-selected, and it explains what «مش معروف» does.
- Website text is shown as quoted data, and the source lines show the host only.
- The copy summary names exactly what goes where.
- The header never says "done" over open conflicts.
- Every state is drawn, Arabic is checked at 300 px, and render_all now fails any state that prints an object as text.
The real panel still has to match this inside Premiere (J-T9c, E-D5).
```

### Final polish (the last P2s of both reviewers)
- No typed ✓ / ✕ inside a sentence any more (the Arabic face draws ✓ like √): the review's sub says «أكّد أو ارفض كل حاجة لوحدها بالزرارين اللي جنبها.», the conflict lines say «لو أكدته، بيتضاف … جنبه، و … بيفضل زي ما هو.» (this also settles the editor's "✓ wraps away from its verb").
- The photo size: «1600 × 2000» is one no-break unit, the line may break before «بكسل» and after the dot; the landscape preview is 64 px wide like the others, so its line stays inside its column at 300 px.
- J-05 "What the website gave": the counts sit under each label (no overlap at 300 px); «{n} من غير ملف».
- J-02 clients-folder name: start-aligned in Arabic, still cut at its end.
- J-03 proxy: its own sub, «لو مش عارف تسجّل دخول فين، اسأل مسؤول الـ IT في الشركة. أو اطلب ملفات الهوية من العميل، وكمّل دلوقتي من غير الموقع.»
Each was checked in a quick render at the widths the reviewers named (0 failed); the J screens were then re-rendered once
more in full (below). These are layout and wording polish after two PASS / YES verdicts, so no further review round.

## Result
- **Designer (G2 bar): PASS** (pass 2 and the final confirmation). **First-time Arabic editor: YES** (pass 2).
- E-D2 / E-D3 for J-T9a: the mockups exist before any screen code; the designer's verdict is recorded; a first-time
  Arabic editor round is done. Both report no major issue.

## Open, for the owners (not blocking J-T9a)
- **Native Arabic writer:** every AR line in `strings/client-setup.js` (both reviewers are AI). Two spec-verbatim lines
  the editor questioned and that were kept as the spec gives them: «في جلسة Claude شغالة على العميل ده دلوقتي» (the
  editor reads «فيه») with «استنى وجرّب تاني», and the label «تخطي» (the editor prefers «كمّل من غير الموقع»). The spec
  owner may change them; the certificate title (J2.3) is kept verbatim too.
- **J-T9b (engine data):** whether `brand.candidates` can carry the editor's decisions over to a re-read for items whose
  sha256 did not change. Until then the copy says the review starts again.
- **G2 side-by-side** against two reference panels: not done in this round (the reviewer's "not checked").
- **Not verified:** real UXP paint, hover / pressed states and motion (J-T9c, E-D5); 480 px and the light theme were
  sampled, not viewed state by state; the AE CEP panel at 280 px (J-T9c's B-T6 widths) has no mockup render.
