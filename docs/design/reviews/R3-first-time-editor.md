# R3: first-time Arabic editor (full day I-01 → P-22, HEAD aa36352)

Reviewer: AI agent role-playing a 24-year-old Egyptian agency editor in Cairo. Uses Premiere and After Effects every
day, reads Arabic first, new to WhyNot Cut. Read-only apart from this file.

**What I looked at:**
- Renders, mostly AR:
  - I-01, I-02, I-03, I-04, I-05 and I-06 (Windows); I-05 long, I-07 manifest, I-08 normal, I-09 confirm;
  - P-01 normal, P-03 normal, P-04 normal, P-05 normal;
  - P-06 normal and no-internet; P-07 older and stale; P-08 normal; P-10 older; P-11 normal; P-22 normal;
  - A-02 normal.
- Wording: the full AR blocks of `strings.js`, `strings/premiere-core.js` and `strings/tools-ae.js`, and a grep of
  `strings/installer.js` for the lines I questioned.
- **Not viewed as renders:** P-02, P-09, P-12 to P-21, A-01, A-03 and A-04. I judged these from their strings only.
  I did not open every state of every screen.

## 1. Verdict

**YES. I would use it on a real client job, with one condition:** on After Effects motion jobs for medical or
religious clients, I get the doctor's or sheikh's OK myself, outside the panel, until A-02 asks me for it (P1-02).

**Why yes:**
- All 6 of my round-2 P1s are closed. Several of the fixes are better than what I asked for.
- I can switch client from the header.
- While Claude builds, the panel tells me which sequence not to open, and what «إلغاء» does.
- The internet-down state is calm and honest: «مفيش نت… والمونتاج هيكمّل لوحده لما النت يرجع».
- The privacy line now sounds like us.
- The Arabic mostly sounds like a colleague now, not a translation.

**What still makes me hesitate:**
- The new "approved with an older WhyNot Cut" state wipes my doctor ticks without saying whether anything changed.
- The panel tells me to «كلّم الدعم», but there is no support channel yet («صفحة الدعم قريب»).
- The cost line reads as if I pay Claude out of my own pocket.

## 2. Round-2 P1 items: closure

| R2 # | Finding | Status | Evidence at aa36352 |
|---|---|---|---|
| P1-01 | Can't switch client or clip | **Closed** | Header row 2 is «C0239 · Sahha Clinic ⌄» on every screen. Home has «غيّر الفيديو» under the hero. P-04 «عملاءك» lists the clients with ✓ on the current one. |
| P1-02 | Build: what is safe, what Cancel does | **Closed** | P-06 running: «Claude بيبني السيكوينس الجديد {seq}… بس ما تفتحش {seq} لحد ما البناء يخلص». Under Cancel: ««إلغاء» بيوقّف البناء ويشيل السيكوينس اللي ما خلصش. الخطة وموافقتك بيفضلوا محفوظين.» The sequence name itself is new trouble: see P1-04. |
| P1-03 | No "no internet" state | **Closed** | P-06 no-internet: amber card «مفيش نت. Claude محتاج نت عشان يعمل الخطة.», the step shows «واقفة» with a pause icon, and the pill reads «Claude مفيش نت». P-05 failed: «النت فصل، فالطلب ما وصلش لـ Claude. مفيش حاجة بدأت…». On P-12 the shared line has the wrong subject: see P2-03. |
| P1-04 | Stale plan numbers disagree | **Closed** | P-07 stale: «48 ثانية بدل 52 · 7 قطعات بدل 6 · لقطة B-roll واحدة بدل 2». The summary says «ريل 48 ثانية», the map ends at 0:48, and the saved line reads «ريل 48 ثانية · هيوفّر حوالي 45 دقيقة (تقدير)». |
| P1-05 | Settings: three Claude modes, API key could cost money | **Closed** | P-22 shows only «استخدم Claude المفتوح على جهازي». The rest sits under the collapsed «إعدادات متقدمة (لصاحب الشركة)», and the API key is labelled paid and «مش محتاجه لو عندك Pro أو Max». |
| P1-06 | MSA privacy line, no full stop | **Closed** | The D-03 line is everywhere I looked (P-01, P-07, P-22, I-05): «ملفات الفيديو والصوت عمرها ما بتترفع. Claude بيقرا نصوص بس…». It ends with a full stop. |

**6 of 6 closed.** Several round-2 P2s are also closed:
- P2-01, the Arabic verbs in the tools («اللي هيحصل في المشروع»);
- P2-03, «ما تطبّقش»;
- P2-05, «ساعة و10 دقايق»;
- P2-09, «هتعمل مونتاج C0241 (مش C0239)»;
- P2-10, the step names «تصدير الصور» → «فحص الجودة» → «جاهز ليك»;
- P2-11, the open-project note;
- P2-13, a tick per flagged line;
- P2-17, «ليك إنت بس. مش محتاج صلاحيات الأدمن.»;
- P2-18, the numbered I-06 steps.

P2-07, the Mac keycaps, is still open (see P2-15).

## 3. Findings (round 3)

P0 = I would not use it on a client job. P1 = I'd hesitate, ask a colleague, or risk a mistake. P2 = friction or
polish.

**Counts:** P0 = 0, P1 = 6, P2 = 17 (23 findings in total).

### P1

| id | Screen + state | What confused or worried me | Exact string now | Suggested Egyptian rewrite / fix |
|---|---|---|---|---|
| P1-01 | P-07 older (the new state); also P-10 older | My ticks and «اتأكدت مع مين؟» are empty again, but nothing says whether the plan or the medical lines changed. I either call Dr. Hana again for nothing, or I tick blindly, and blind ticking is exactly what the ticks exist to stop. It also doesn't say what happens to the sequence that was already built. | «الخطة دي اتوافق عليها بنسخة أقدم من WhyNot Cut. بص عليها بصّة كمان ووافق عليها تاني.» | Show who approved and when, and whether anything changed: «الخطة دي وافق عليها Yunus يوم 14 أكتوبر بنسخة أقدم من WhyNot Cut، وأكّدت الجمل د. هناء مصطفى. الخطة نفسها ما اتغيّرتش. علّم على الجمل تاني ووافق.» If the lines did change, mark the changed ones and say «الجملة دي اتغيّرت، راجعها مع الدكتور تاني». Add one line on the built sequence (engine behaviour to confirm): «السيكوينس اللي اتبنى قبل كده مش هيتلمس.» |
| P1-02 | A-02 normal / checked (motion approval, medical client) | The tick reads as if the medical lines are approved, but Claude did the review, not a doctor. P-07 makes me tick each line and type who confirmed it, and P-22 says «اتأكدت مع» is required for medical and religious clients. A-02 asks for neither. Claude even changed a medical word («بيعالج» → «ممكن يساعد») and nobody human signs it. | «مراجعة الجمل الطبية ✓ — اتراجعت للخطة دي: 5 سطور متوافق عليها.» | Title: «مراجعة الجمل الحسّاسة» (see §5). Body: «Claude راجع 5 جمل وخفّف واحدة. لسه لازم تأكّدها مع الدكتور أو الشيخ.» Then the same per-line tick and «اتأكدت مع مين؟» as P-07, with «وافق» locked until they are done. |
| P1-03 | I-07 manifest; P-11 normal; P-22 support; every «كلّم الدعم» hint (P-11, A-01, A-02, P-03) | The errors tell me «كلّم الدعم», but support is «قريب». The download page is «قريب» too, and so is the guide. On I-07 the install stopped and I have no next step at all. «انسخ التفاصيل للدعم» copies them to… whom? «قريب» with a feminine noun also sounds half-finished. | «صفحة الدعم قريب» · «صفحة التحميل قريب» · «الدليل قريب» · «… ولو ده اتكرر كلّم الدعم.» | Until the page is live, name a person: «صفحة الدعم لسه ما نزلتش. لحد ما تنزل، ابعت التفاصيل اللي اتنسخت لمسؤول WhyNot Cut في شركتكم.» I-07: «صفحة التحميل لسه ما نزلتش. اطلب ملف التسطيب من مسؤول WhyNot Cut عندكم.» Change the error hints to «ولو اتكرر، ابعت تقرير المشكلة للمسؤول عندكم.» Guide: «الدليل لسه ما نزلش.» |
| P1-04 | P-07 (all) vs P-06 running vs P-09 vs the tools | The safety rule is "don't open THIS sequence", but each screen names a different sequence. Approval promises C0239_v1. The build says don't open C0239_reel_v3, split over two lines as «C0239_» / «reel_v3». Hush and Kalam work on C0239_main. I won't know which one to keep my hands off. | P-07: «هيتعمل سيكوينس جديد C0239_v1». P-06: «… بس ما تفتحش C0239_reel_v3 لحد ما البناء يخلص.» | One name from the plan (`plan.sequence_name`) on P-07, P-06, P-09 and P-10. Keep the name on one line (a no-break LTR run, with a middle ellipsis if it is too long). |
| P1-05 | P-08 normal (failed tile); A-04 frames | I am the editor, so «محتاج المونتير بتاعك» talks about someone else. The violet button under it, «صلّح دي», sends the frame to Claude. I can't tell if this is my job or Claude's. A-04 has the same chip, «محتاجة المونتير». | «محتاج المونتير بتاعك» + «صلّح دي» | Chip: «فيها مشكلة». Button: «خلّي Claude يصلّحها». Only when the fix really is mine: «محتاجة تدخّل منك» + one line on what to do. |
| P1-06 | P-01 normal (Claude row), I-05, P-22: the cost and data lines (locked D-01 / D-02, owner to re-approve) | **(a)** «كل مونتير محتاج اشتراك… باسمه، بيدفعه لـ Anthropic» reads as: I pay $20 a month out of my own salary. In an agency the company pays. **(b)** The data line says «للعملاء الطبيين: استخدم اشتراك Team أو Enterprise», but our first client is Sahha Clinic. Nothing tells me if MY account is OK for this client, so it worries me instead of reassuring me. **(c)** On P-01 the Claude row is now about 17 lines, and «مسجّل دخول» is buried at the bottom. | D-01: «كل مونتير محتاج اشتراك Claude Pro أو Max باسمه، بيدفعه لـ Anthropic (Pro بيبدأ من 20 دولار في الشهر، والسعر بيختلف من بلد للتاني)…». D-02: «… لشغل العملاء، اقفل "Help improve our AI models"… للعملاء الطبيين: استخدم اشتراك Team أو Enterprise…» | **(a)** «كل مونتير محتاج اشتراك Claude Pro أو Max على اسمه. الاشتراك بيتدفع لـ Anthropic، مش لـ WhyNot Cut، واسأل شركتك مين بيدفعه. Pro بيبدأ من 20 دولار في الشهر.» **(b)** Say it where it matters, per client: on a medical client's P-05 / P-07, «العميل ده طبي: اشتغل على اشتراك Team أو Enterprise بتاع الشركة.» Add an «إزاي؟» link next to «اقفل Help improve…». **(c)** On P-01 keep the status plus one cost line plus the links «شوف الاشتراكات» and «Claude بيشوف إيه». Keep the full block for I-05 and P-22. |

### P2

| id | Screen + state | Exact string now | Suggested fix |
|---|---|---|---|
| P2-01 | P-01 normal (3 of 4 ready, no client folder) | Header pill «كله تمام» | «فاضل خطوة» (waiting dot) until the checklist is complete. |
| P2-02 | P-06 running | «بنبني السيكوينس… 23 من 47» | 47 what? «بنبني السيكوينس… 23 من 47 حتة». |
| P2-03 | P-12 no-internet (shared `net.off`) | «مفيش نت. Claude محتاج نت عشان يعمل الخطة.» + «… والمونتاج هيكمّل لوحده» | This sheet fixes captions, not the plan: «مفيش نت. «صحّح الكابشن» محتاج نت. كابشنك زي ما هو.» |
| P2-04 | P-03 Home vs P-13 Tools, last Hush run | Home: «آخر مرة: اتشال 18 سكتة · من ساعتين». P-13: «آخر مرة: اتقطّع 24 قطعة · من ساعتين». | One run, one number (the canonical 24 pauses) and one verb on both screens. |
| P2-05 | I-04 progress (Windows) | «أدوات أمان Claude» (this is Git Bash) | It isn't a safety tool. If I later see Git installed, I'd feel misled. Use «أدوات بيحتاجها Claude على Windows (Git)». |
| P2-06 | I-04 progress | Step «خلّي WhyNot Cut جاهز»; a bare «0:42» under the bar | «شغّل WhyNot Cut مع الجهاز»; «عدّى 0:42». |
| P2-07 | I-09 confirm | Safe button «خليه» | «خليه» can read "let it (go)". Use «لا، سيبه متسطّب». |
| P2-08 | I-07 manifest | The sidebar shows «فحص الجهاز» ✓, but the step list shows «فحص الجهاز» ✗. The failure is the file check. | Name the failed row «فحص ملفات التسطيب». |
| P2-09 | I-03 preflight | «المستندات متزامنة مع OneDrive. هنحط العملاء في فولدر مش متزامن.» | Glossary word, not MSA: «فولدر المستندات عليه سينك مع OneDrive، فهنحط العملاء في فولدر برّه السينك.» |
| P2-10 | P-16 / P-13 / P-17 «اللزمات» | «بيشيل السكتات واللزمات.» | Keep it; it's how we talk. The first time it appears (P-16), give examples: «اللزمات (إممم، آآ، يعني)», so nobody thinks it means a host's catchphrase. |
| P2-11 | P-14 Tidy scan | «هيتنقل للفولدرات» next to «ملفاتك على الهارد مش هتتلمس» | «فولدرات» is right, but here it sits next to disk folders. On first use: «هيتنقل لفولدرات جوه المشروع (Bins)». |
| P2-12 | P-16 confirm | «الفراغات هتتقفل، فكل اللي بعد القطع هيقدّم.» | «هيقدّم» reads as "will present". Use «الفراغات هتتقفل، وكل اللي بعد القطع هيتسحب لقدّام.» |
| P2-13 | P-10 normal / older | «الدكتور أو المتكلم لازم يوافق على الجمل دي.» · «3 جمل · طبية ودينية» | P-07 says «مع الشيخ أو المتكلم» for the religious line. Use «الدكتور أو الشيخ لازم يأكّد الجمل دي.» |
| P2-14 | P-22 advanced, API key | «مدفوع لـ Anthropic على حسب الاستخدام… الفاتورة من Anthropic على حسابك.» | It says the same thing twice. Drop the last sentence; D-01's «مدفوع لـ Anthropic على حسب الاستخدام» covers it. |
| P2-15 | P-03, P-05, P-07, P-08 primary buttons (default render) | «⌘ ↵», «⌘ O», «⌘ .» | Still Mac keys (R2 P2-07, backlog B-09). Our PCs run Windows: «Ctrl Enter», or no chip. |
| P2-16 | P-22 sign-off setting | «شغّال من الأول. الموافقة الطبية ما بتتسجّلش من غيره.» | The setting covers religious lines too: «الموافقة على الجمل الطبية والدينية ما بتتسجّلش من غيره.» |
| P2-17 | P-08 normal, bottom card; footer on every AR screen | The info card ««صلّح دي» بتطلب من Claude نسخة جديدة…» has a red ✕ error icon. The footer reads «Powered by thewhynot.ai». | Use an info icon; a red ✕ reads as "something failed". AR footer: «من thewhynot.ai». |

## 4. Walk notes (the day)

1. **Install (I-01..I-09, Windows).**
   - What worked: «سطّب كل حاجة» and «اختار بنفسك» are clear. I-02's permission box is unticked, with one honest
     line. I-06's numbered steps («1. افتح Premiere… Window › UXP Plugins › WhyNot Cut. 2. من البانل دوس «جهّز أول
     عميل».») finally tell me the order. I-08 has «ارجع للإصدار 2.2.1», a big comfort.
   - Problems: P2-05 to P2-09. On failure, I have nowhere to go (P1-03).
2. **First run (P-01).** Clear: one violet button and «جرّب على كليب تجريبي». The Claude row is too long (P1-06c),
   and the pill lies a little (P2-01).
3. **Client and footage (P-03..P-05).**
   - P-04 is excellent: per-client «وفّرت… · تقدير», and the total for all clients.
   - P-05: «هتعمل مونتاج C0241 (مش C0239).» plus the radio rows means I no longer edit the wrong clip.
   - The missing-logo card tells me what happens and gives the fix.
4. **Pipeline and approval (P-06, P-07, P-10).**
   - What worked: the build card is now exactly what a senior would say. Paused-for-internet looks paused, not
     broken. P-07 stale is consistent.
   - The new older-version state is the weak spot (P1-01), and the sequence names disagree (P1-04).
5. **QC (P-08) and errors (P-11).**
   - What worked: QC sorts the failed frame first and shows the safe-area box.
   - Who acts on it is unclear (P1-05).
   - P-11 cards: one cause and one button each («صلّح الإعدادات», «حمّل البانل تاني»), and «عملاءك ومشاريعك مش
     هتتلمس» reassures me. But «كلّم الدعم» has no channel (P1-03).
6. **Tools (P-13..P-20)**, from the strings.
   - What worked: the Arabic verbs, «بنحفظ نسخة احتياطية من السيكوينس الأول دايمًا», the formulas under «بنحسبه إزاي؟»
     and «اسألني الأول (غالبًا كلام حقيقي)». These make me trust the cuts.
   - Problems: P2-10 to P2-12.
7. **After Effects (A-01..A-04).**
   - What worked: «كلام Claude مش كلام المتكلم» per scene, «أكّد الأرقام دي» with ticks, and «الموافقة مش بتغيّر
     حاجة دلوقتي…» are great.
   - The claim review is the gap (P1-02).
8. **Settings (P-22).** One default mode, the owner-only advanced section, «من شركتك» on the rate, and «اتأكدت مع»
   required for medical and religious clients. Everything an editor needs, nothing to break. Support is a dead end
   (P1-03).

## 5. Answers to the five questions

1. **Do I know what to do next on every screen?**
   - Yes, on almost every screen. There is one violet action per screen, and blocked buttons say why («علّم على كل جملة
     فوق عشان «وافق» يشتغل»).
   - **Exceptions:**
     - I-07, P-11 and P-22 when support is needed (P1-03);
     - P-07 older, where I don't know whether to call the doctor again (P1-01);
     - P-08, where it's unclear if a failed frame is mine or Claude's (P1-05).
2. **Does the Arabic sound like a colleague?**
   - Mostly yes. This is a big jump from round 2.
   - **The glossary words are ours:**
     - «البانل» (masc.) yes, everyone says it;
     - «ريندر» yes, and «صدّر» for frames is right;
     - «اللزمات» yes, with examples once (P2-10);
     - «فولدرات» yes for disk; for Premiere bins add «(Bins)» once (P2-11);
     - «سينك», «البلاي هيد», «المكس», «البريسيت» and «بصّة كمان» are all how we talk.
   - **MSA still shows in a few places:**
     - «متزامنة» (P2-09);
     - «الإزالة بتشيلهم كلهم» (I-01);
     - «قائمة الملفات أصلية» (I-07);
     - «اللي حصل مؤخرًا» (P-22);
     - «هيقدّم» (P2-12).
     - Better words: «لما تشيله بيشيل كله», «اللي حصل الفترة اللي فاتت».
3. **The Claude cost and data wording.**
   - The privacy line builds trust.
   - The cost line is honest, but it worries me: it sounds like I pay, and it doesn't fit our medical client
     (P1-06).
   - Advice for the owner: keep the facts, and change who pays and where the medical rule shows up.
4. **The "coming soon" lines.** Confusing as they are now.
   - "Coming soon" is fine for a guide.
   - It is not fine for support or the installer download: those are dead ends on error screens.
   - Name an in-house contact until the pages are live (P1-03).
5. **A-02 «مراجعة الجمل الطبية».**
   - It's not the right name for every client.
     - For a medical client it's clear and much better than «الادعاءات».
     - On a religious client, or a podcast with both, it would make me think nobody checked the verse or hadith lines.
   - Use **«مراجعة الجمل الحسّاسة»** as the one title, with a chip per line («طبي» / «ديني»), the same chips as P-07.
   - The bigger issue is not the name: A-02 must ask for the doctor's or sheikh's confirmation the way P-07 does
     (P1-02).
