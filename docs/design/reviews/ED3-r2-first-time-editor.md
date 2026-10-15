# E-D3 round 2: first-time Arabic editor (full journey I-01 → A-04)

Reviewer: AI agent role-playing a 24-year-old Egyptian agency editor. Fluent in Premiere and After Effects, reads
Arabic first, not technical, never used WhyNot Cut. I looked at the contact sheets in
`adobe/panel-ui/design/renders/_sheets/` and the single AR-360 renders where a sheet was too small to read
(P-01, P-03, P-04, P-05, P-06, P-07, P-09, P-10, P-12, P-16, P-17, P-22, A-02, I-02, I-06, plus P-03 EN). I checked
the exact wording in `design/strings.js` and `design/strings/{installer,premiere-core,tools-ae}.js`. Read-only.

## 1. Verdict

**Yes, I would use it on a real client job tomorrow, with two conditions:** I run «جرّب على كليب تجريبي» first,
and I keep my hands off Premiere while the sequence builds, because nothing tells me whether that is safe.

Why yes:
- The installer and the panel now talk like my team lead: «سطّب كل حاجة», «حط الفيديو الخام في فولدر raw»,
  «ابدأ المونتاج», «وافق». I always knew which violet button to press next.
- Every risky screen says what stays safe. Examples: «هيتعمل سيكوينس جديد… والسيكوينس الأصلي وملفاتك مش هيتلمسوا»,
  the rebuild dialog with the backup `.prproj` name, and the Hush backup plus Undo.
- Errors now say what happened and the one thing to do.
- Claude is explained («المساعد الذكي… بيفتح في نافذة لوحده، بحسابك انت، من غير تكلفة زيادة»).
- The doctor or sheikh tick-box makes me feel covered on medical and religious lines.

Why not a full yes yet: I can't find how to switch client, there is no screen for "no internet", the build screen
invites me to keep editing without saying where it's safe, and Settings offers an "API key" option that could cost
me money.

## 2. Round-1 findings: status

| r1 # | Finding | Status | Evidence in round 2 |
|---|---|---|---|
| 1 | «المحرّك» meaningless | Fixed | Everywhere «خدمة WhyNot Cut… شغّالة على جهازك وبتعمل الشغل التقيل» |
| 2 | Claude never explained | Fixed | `checklist.claude.explain` + account line + privacy line on P-01 |
| 3 | Offline pills drop names | Fixed | P-01/P-03 offline: «خدمة WhyNot Cut مش شغّالة», «Premiere مش متوصّل», «Claude لسه ماتفحصش» |
| 4 | No next step if retry fails | Fixed | «لو «حاول تاني» مانفعتش، اقفل Premiere وافتحه تاني» |
| 5 | Stale banner order unclear | Fixed | «اقفل Premiere وافتحه تاني، وبعدين اضغط «افحص تاني»» |
| 6 | «لم يُختَر أي عنصر» | Fixed | «مفيش فيديو مختار» |
| 7 | Version noise, «نسخ التشخيص» | Fixed | Version gone from P-01. «انسخ تقرير المشكلة» + «كلّم الدعم» |
| 8 | Badge count disagrees, not clickable | Fixed | «مطلوب منك 1 ‹» pill with chevron; the Edit tab shows the same 1; P-10 shows 6/6 |
| 9 | Error state contradicts itself | Fixed | P-03 error: the pill now reads «مش بترد» (warn), and the verbs are disabled |
| 10 | Offline: tools stay active | Fixed | P-03 offline: the tool cards are greyed out |
| 11 | Arabic-first tool names | **Partly** | Home and Tools say «رتّب المشروع / شيل السكتات / كابشن», but tool pages still put the English brand inside Arabic sentences: «افحص المشروع عشان تشوف Tidy هينضّف إيه», «Tidy هيعمل إيه», «حزمة كلام» (see P2-01) |
| 12 | «جاهز لـ C0239» | Fixed | «الفيديو الحالي C0239» |
| 13 | «أضف ملفاتك» unclear | Fixed | «ضيف الفيديوهات · بيفتح فولدر العميل» |
| 14 | Models scary on Home | Fixed | Only «الإعدادات» on Home; Models sits inside Settings |
| 15 | English folder names unexplained | Fixed | «فولدر للّوجو والخطوط والصور (assets)، وفولدر WhyNot Cut بيملاه لوحده (data)» |
| 16 | Flagged lines: approve allowed? doctor for religion? | Fixed | Per-line «اتأكد منها مع الدكتور» / «مع الشيخ أو المتحدث», a tick-box, and «وافق» stays locked until I tick |
| 17 | Stale plan shows only a hash | Fixed | «7 قطعات بدل 6 · لقطة B-roll واحدة بدل 2» (but see P1-04) |
| 18 | «افتح Claude»: open what, where? | Fixed | «بيفتح في نافذة لوحده برّه Premiere» |
| 19 | «لم تنجح العملية» | Fixed | «الموافقة ماتسجّلتش» + «حاول تاني. لو فشلت تاني، انسخ تقرير المشكلة وكلّم الدعم» |
| 20 | Brackets, hash, «طلب», ambiguous build line, timecodes | Fixed | No English glosses or hash; «اطلب تعديلات»; timecodes have a ▷ play icon |

19 of 20 are fixed and 1 is partly fixed. This is a big step up from round 1.

## 3. Findings (round 2)

P0 = I would not use it on a client job. P1 = I'd hesitate, ask a colleague, or risk a mistake. P2 = friction or polish.
**Count: P0 = 0, P1 = 6, P2 = 19.**

### P1

| id | Screen + state | What confused or scared me | Exact fix |
|---|---|---|---|
| P1-01 | P-03 Home (all states), header row 2 | I can't find how to switch to another client or clip. «Sahha Clinic · C0239» is plain text. The only route to P-04 I found is inside other screens. | Make header row 2 a button with a chevron: «Sahha Clinic · C0239 ⌄», with an aria label and tooltip «غيّر العميل أو الفيديو». On Home, add a small glass link under the C0239 hero: «غيّر الفيديو». |
| P1-02 | P-06 running | «Claude شغّال عليه. تقدر تكمّل مونتاج في Premiere عادي». It is building a sequence inside **my** Premiere right now. If I touch the timeline, will I break it, or will it break my work? «إلغاء» doesn't say what happens to the half-built sequence. | Replace with: «Claude بيبني السيكوينس الجديد {seq}. تقدر تشتغل في أي سيكوينس تاني عادي، بس ماتفتحش {seq} لحد ما البناء يخلص.» Under Cancel: «الإلغاء بيوقّف البناء ويشيل السيكوينس اللي ماكملش. الخطة وموافقتك محفوظين.» |
| P1-03 | P-02 / P-05 / P-06 / P-12, internet down | Our office internet drops often. The panel never says "no internet". «Make my edit» fails with «الخدمة ماعرفتش تتواصل مع Claude», which makes me think the program is broken. Only P-12 and P-21 mention «النت فصل». | Add an internet state to P-02 and the pills. Card: «مفيش نت. Claude محتاج نت عشان يعمل الخطة. التفريغ والأدوات شغّالين على جهازك عادي، والمونتاج هيكمّل لوحده لما النت يرجع.» No button. P-05 failed sub, when offline: «النت فصل، فـClaude ماوصلهوش الطلب. مفيش حاجة بدأت؛ هنبعته تاني لوحدنا لما النت يرجع.» |
| P1-04 | P-07 stale | The new summary says «ريل 48 ثانية», but the edit map still ends at 0:52 and the saved line still says «ريل 52 ثانية». If the numbers disagree, I stop trusting the whole plan. | Every number on the card comes from the new plan: map end 0:48 and «ريل 48 ثانية». Add the duration to the diff line: «48 ثانية بدل 52 · 7 قطعات بدل 6 · لقطة B-roll واحدة بدل 2». |
| P1-05 | P-22 Settings, «Claude وأزرار الذكاء الاصطناعي» | There are three radio options. «استخدم جلسة Claude المفتوحة» and «استخدم تسجيل دخولي في Claude» sound the same to me. «استخدم مفتاح Anthropic بتاعي» + «Anthropic بتحاسبك على حسابك» + «الصق مفتاح API» could cost the agency money, and I don't know what an API key is. | Show only the default to editors. Put the other two under a collapsed «إعدادات متقدّمة (للمسؤول بس)». Rename the options: «استخدم Claude المفتوح على جهازي (من غير تكلفة زيادة)»; «اشتغل وClaude مقفول، بحساب الاشتراك»; «مفتاح API (بفلوس، من Anthropic)». |
| P1-06 | P-01, P-02, P-07, P-12, P-22, I-05: the privacy line | This is the most reassuring sentence in the product, and it is the only MSA sentence: «ملفات الفيديو والصوت لا تُرفع أبدًا؛ يقرأ Claude…». It reads like a legal disclaimer. It also has no final period (P-12, P-22, I-05). | Use Egyptian Arabic, with the same facts: «ملفات الفيديو والصوت عمرها ما بتترفع. Claude بيقرا نصوص بس (التفريغ والخطة) وشوية صور ثابتة: لقطات قليلة من التايملاين عشان المراجعة، وصور البراند.» It is marked executor-APPROVED, so the owner must re-approve the Arabic wording. |

### P2

| id | Screen + state | What confused me | Exact fix |
|---|---|---|---|
| P2-01 | P-14/P-15/P-17/P-21/P-11 | English brand names inside Arabic sentences: «Tidy هيعمل إيه», «Tidy مقدرش يقرا», «امسح كل ماركرز Hush». The pack has two names, «حزمة كلام» and «حزمة الكابشن». | In the Arabic sentences use the Arabic verbs: «اللي هيحصل في المشروع», «الترتيب ماقدرش يقرا عنصرين», «امسح ماركرز شيل السكتات». Use one pack name everywhere: «حزمة الكابشن». Keep the brand only as the small grey sublabel. |
| P2-02 | All screens, button names quoted in hints | The same button has different names: «حاول تاني» (core) and «جرّب تاني» (installer, tools); «افحص تاني» and «اتأكد تاني»; «اضغط» and «دوس»; «نافذة» and «شباك»; «موديل» and «نموذج»; «المتحدث» and «المتكلم»; «انت» and «إنت». So a hint like «دوس «اتأكد تاني»» points at a button labelled «افحص تاني». | One word list: «جرّب تاني», «افحص تاني», «دوس», «شباك», «نموذج», «المتكلم», «إنت». |
| P2-03 | P-12 ready | «سيبك منه» for Discard is street slang next to a client's caption. | «ماتطبّقش» |
| P2-04 | A-02 normal / blocked | «مراجعة الادعاءات» sounds like an accusation or a lawsuit. | «مراجعة الجمل الطبية» (and «الجمل الحساسة» for religious clients) |
| P2-05 | P-13 normal | «حوالي 2 ساعة و10 دقايق» is wrong Arabic. | «حوالي ساعتين و10 دقايق» |
| P2-06 | P-17, P-12, P-15, P-20, A-04 (time saved) | «وفّرت لك حوالي 12 دقيقة مونتاج» for 14 s of silences in a 1:12 clip is not believable; by hand that is 3–5 minutes. «10 دقايق مراجعة» for 3 typo fixes is not believable either, since I still review the 42 lines myself. These tool lines also drop «تقدير», which Home and the approval card keep. The approval card says «وفّرت» before anything is built. | Cut the Hush mock to «حوالي 4 دقايق» and P-12 to «حوالي 3 دقايق». Always end with «· تقدير». On P-07 use the future tense: «هيوفّر حوالي 45 دقيقة (تقدير)». Home's «4 ساعات و30 دقيقة · 7 ريلز» (about 38 min per reel) is believable; keep it. |
| P2-07 | Every primary button | The key chips «⌘ ↵», «⌘ N», «⌘ .», «esc» are Mac keys. Our agency PCs run Windows. | Show «Ctrl Enter» / «Esc» on Windows, or drop the chips at 360 px and below. |
| P2-08 | P-03 hero | The placeholder in the grey well is a person icon, so it reads as "profile/account". | Use a film-frame or clapper icon until a real poster frame exists. |
| P2-09 | P-05 normal | The header says C0239, but «ابدأ المونتاج» will edit C0241. The clip rows don't look selectable. | Make each «جديد» row a radio row. Change the bar to «هتبدأ مونتاج: C0241 (مش C0239)» when the two differ. |
| P2-10 | P-06 steps | «مراجعة الصور» followed by «الفحص» sounds like the same step twice. «التسليم / اتسلّم»: handed to whom? | Rename the steps «تصدير الصور» → «فحص الجودة» → «جاهز ليك». Done sub: «اتبنى واتفحص. افتح المشروع وكمّل المونتاج.» |
| P2-11 | P-06 done | «افتح المشروع». Will it close the project I have open? | Add one line under the button: «بيفتح المشروع الجديد في Premiere جنب شغلك؛ مش هيقفل حاجة.» |
| P2-12 | P-03 / P-01 Claude signed out | The text says «ارجع هنا واضغط «افحص تاني»», but the card only has «سجّل دخول Claude». | Add «افحص تاني» as the secondary button, or change the hint to «هنعرف لوحدنا أول ما تسجّل.» |
| P2-13 | P-07 flagged | One tick-box covers 3 lines. I can tick it without opening the medical lines. | One small tick per flagged line, or keep one box but show it only after «اعرض الكل» has been opened. |
| P2-14 | P-12 ready | «راجع كل تعديل قبل ما تطبّقه», but I can only apply all of them or none. | A tick on each change (all ticked by default). Button: «طبّق المتعلّم عليه ({n})». |
| P2-15 | P-17 result | The big violet «تراجع» right after success invites a mis-click. | Make «تمام» the primary and «تراجع» glass. The note already says the cut copy is kept. |
| P2-16 | P-09 confirm-nobackup | «ابني من غير نسخة احتياطية» is one click away. The card doesn't say how much space to free. | «فضّي حوالي {gb} عشان نحفظ نسخة احتياطية». Keep «ابني من غير نسخة احتياطية» as a red glass button, below «سيب مشروعي». |
| P2-17 | I-01 / I-03 / I-02 | «Homebrew», «Xcode», «Gatekeeper» mean nothing to me. «ما تسألنيش كل مرة Claude يستخدم WhyNot Cut»: what is it asking, and is it safe? | I-01: «ليك إنت بس. مش محتاج باسورد الأدمن ولا برامج مطوّرين.» I-03: «حماية macOS فاضلة شغّالة.» I-02 sub: «Claude مش هيوقّفك يسألك إذن قبل كل خطوة مونتاج. أي حاجة برّه WhyNot Cut هتفضل تسألك.» |
| P2-18 | I-06 finish (Windows) | There are two "next" paths («افتح Claude» primary, plus a text line about Premiere), and I don't know which comes first. The button renders as «Claudeافتح» (bidi bug). | Number them: «1. افتح Premiere ← Window ▸ UXP Plugins ▸ WhyNot Cut. 2. من اللوحة دوس «جهّز أول عميل».» Keep «افتح Claude» as secondary. Wrap the Latin name in `<bdi>`. |
| P2-19 | A-02 normal | «رخصة مجانية (ISC)», «رخصة CC-BY، والمصدر مذكور في البوست»: licence jargon. Does this mean **I** must credit someone? The number «2 · 00:14» doesn't say what "2" is. «Claude بيعمل المونتاج» (P-01) contradicts «بيخطّط المونتاج» (P-02). | «6 أيقونات مجانية، مسموح نستخدمها» / «الموسيقى: Calm Pulse. لازم تكتب اسم الفنان في البوست (مكتوب في حزمة النشر)». Number row: «2 (مرتين ورا بعض) · 00:14». Use «بيخطّط المونتاج» everywhere. |

## 4. Walk notes (what worked, by step)

1. **Install (I-01..I-09):** Clear and calm. «التسطيب بيضيف 6 حاجات… ومش بتلمس فولدرات العملاء أبدًا» and
   «شوف إيه بيتحط فين» remove the fear. Failure cards (I-07) say what happened and that nothing changed. Uninstall
   says my client folders stay. Jargon: P2-17.
2. **First run (P-01):** «4 فحوصات سريعة», one violet button per row, «جرّب على كليب تجريبي» (40 s, 5 min). This is
   the best new thing; I'd start there. The Claude row is long (4 lines) but it answers my questions.
3. **Home and status (P-02, P-03):** Error, offline and signed-out states are now coherent. P1-01, P2-08, P2-12.
4. **Client and footage (P-04, P-05):** «فولدر العملاء: Clients · الفولدر اللي جواه فولدر لكل عميل» is clear;
   the per-client "saved this week" line is a nice touch. The missing-logo card tells me the result (plain graphics)
   and the fix. P2-09.
5. **Pipeline (P-06):** The steps with times are readable. The done card (verified / not verified / needs you) is
   exactly what a senior would tell me. P1-02, P2-10, P2-11.
6. **Approve (P-07):** Strong. The edit map, «شوف المعاينة», per-line doctor/sheikh notes, and the lock until I
   tick. P1-04, P2-13.
7. **QC (P-08):** «تمام / فيها مشكلة / لسه ماتفحصتش» with icons; «صدّر تاني بيعمل صور جديدة بس» reassures.
8. **Actions (P-09):** The rebuild confirm is the most reassuring screen: what changes, after which time, and the
   backup file name. P2-16.
9. **Needs you (P-10):** Grouped by clip, one button each, and the count matches the badge.
10. **Errors (P-11):** Every card has a "why" and one button. I'd still need P1-03 for internet drops.
11. **AI sheet (P-12):** Before and after per line, plus «السطر الجديد غيّر المعنى، فماستخدمناهوش». P2-03, P2-06, P2-14.
12. **Tools (P-13..P-20):** Hush gives me the waveform, before/after times, the backup name and Undo, so I trust it.
    Kalam's «تراك كابشن جديد… الكليبات والصوت بتوعك مش هيتلمسوا» plus Edit > Undo is enough. P2-01.
13. **Models and settings (P-21, P-22):** Models are clear («للأجهزة الأبطأ»). The time-saved formula is honest and
    editable. P1-05.
14. **After Effects (A-01..A-04):** «قبل البناء» gates with one fix each; «كلام Claude مش كلام المتكلم» is a great
    flag; «الموافقة مش بتغيّر حاجة دلوقتي» should also be added to P-07. P2-04, P2-19.

EN sheets: same structure. The wording is clear with no jargon left, except the Mac key chips (P2-07).
