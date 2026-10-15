# Round 2: D-08 Arabic register pass (professional Egyptian)

Date: 2026-10-16. Owner decision: D-08 in `R2-owner-decisions.md`. Yunus reads the screens next; his comments win.

**Scope:**
- `adobe/panel-ui/design/strings.js`;
- `strings/premiere-core.js`, `strings/tools-ae.js` and `strings/installer.js`;
- the Arabic literals in `screens/*.html` and `js/*.js`.

**Target register:** how a senior Cairo editor talks to a colleague in a pro tool. Not MSA, not slang, short.

**Locked, not touched:**
- the D-01, D-02, D-03 and D-05 lines (`claude.cost`, `claude.data`, `privacy.claude_sees` and its copies
  `p12.privacy`, `p22.privacy.fact` and `i05.know.footage`, `support.promise`);
- the older-approval line (`approval.older`);
- names and string keys.

The script asserted that the locked lines are byte-identical after the pass. No English string changed.

## Counts

| | Reviewed | Changed |
|---|---|---|
| `strings.js` (AR) | 196 | 16 |
| `strings/premiere-core.js` (AR) | 459 | 102 |
| `strings/tools-ae.js` (AR) | 430 | 76 |
| `strings/installer.js` (AR) | 310 | 31 |
| Arabic literals in `screens/*.html`, `js/*.js` | 19 | 0 |
| **Total** | **1,414** | **225** |

**Not changed:**
- 16 more AR values are Latin only (product names, `EN`).
- The 19 literals are spoken data (caption and frame text, filler words, a sample path), not UI copy.

**Length:** 109 changed strings are longer, almost all by 1 or 2 characters. The cause is the space in «ما … ش» and
in «و» before a Latin word. The renders below check the fit.

## Glossary (applied in all four files)

| English | Arabic (only this) | Not |
|---|---|---|
| the background program | «خدمة WhyNot Cut», short «الخدمة» | engine, المحرّك |
| panel / panels | «البانل» (masc.) / «البانلز» | اللوحة، لوحات |
| approve / approval | «وافق» / «الموافقة» / «اتوافق عليها» | |
| turn on (a button) / off | «يشتغل» / «مقفول» | يتفعّل، واقف |
| render | «ريندر» («اعمل ريندر»، «بنعمل ريندر») | صدّر (for render) |
| export (frames, final) | «صدّر» | |
| project / sequence / timeline | «المشروع» / «السيكوينس» / «التايملاين» | التايم لاين |
| clip / video | «كليب» for clip, «فيديو» for video (as in EN) | |
| frame, frame check | «صورة»، «مراجعة الصور» | |
| playhead | «البلاي هيد» | مؤشر التشغيل |
| sync (podcast, by sound) | «سينك» | مزامنة، متزامن |
| filler words | «اللزمات» | كلمات التردد |
| music / track | «المزيكا» / «تراك» | الموسيقى، مزيكات |
| preset | «البريسيت» | الإعداد المحفوظ |
| profile (client) | «بروفايل» | ملف |
| connection | «الاتصال»; connected «متوصّل» | التوصيل |
| signed in | «مسجّل دخول» | متسجّل دخول |
| installed / install | «متسطّب» / «سطّب» | |
| passes the check | «عدّى الفحص» | نجح في الفحص |
| show in folder | «وريني في الفولدر» («وريني الفولدر» for "Show folder") | اعرضها، افتح الفولدر |
| hide (details) | «خبّي» | اخفي |
| Try again / Check again / Undo / Contact support | «جرّب تاني» / «افحص تاني» / «تراجع» / «كلّم الدعم» | الرجوع |
| agency owner | «صاحب الشركة» | صاحب الشغل |
| not recommended | «مش منصوح بيه» | مش مُوصى بيه |
| GB in Arabic copy | «جيجا» with U+00A0 («1.6 جيجا») | GB |
| list | «القائمة» | القايمة |
| durations | «دقيقتين»، «3 دقايق»، «4 ساعات ونص»، «ساعة و10 دقايق» | 2 دقيقة، و30 دقيقة |

**Spelling rules:**
- Negation is «ما … ش», written apart: «ما اتسجّلتش»، «ما قدرناش»، «ما بقتش». This matches D-02 «ما بتتستخدمش».
  Joined «ماتسجّلتش» and «م» forms («متقطّعش»، «مقدرناش») are gone. «متقطّعش» also read as the order "don't cut".
  The fixed contractions «مفيش»، «مينفعش»، «مفيهوش» stay.
- «و» before a Latin word takes a space: «و Claude»، «In و Out»، «Premiere و After Effects». «فClaude» is reworded.
- Imperatives are masculine singular. All progress stages are «بن…» verbs: «بنوقّت كل كلمة»، «بنحط الكابشن».
- The Arabic comma «،» and question mark «؟» are used. Full sentences end in a full stop. There are no doubled spaces.
- Latin script is used for product and brand names and for file types (Premiere, After Effects, Claude, MP4, SRT,
  B-roll). Editors' loanwords stay in Arabic script, like the locked D-03 line («التايملاين»). See question 1.

## The 20 most important changes

| # | Key | Before | After | Why |
|---|---|---|---|---|
| 1 | `p02.panel.ok` | الإصدار {version} · آخر تحديث | الإصدار {version} · محدّث | EN/AR diverged: «آخر تحديث» is "last update"; EN says "up to date". |
| 2 | `i05.know` | خلي بالك | حاجات تعرفها | EN/AR diverged: «خلي بالك» is a warning ("watch out"); EN is "Good to know". Same phrase as `i03.sum.note`. |
| 3 | `p09.render` | صدّر نسخة المراجعة MP4 | اعمل ريندر MP4 للمراجعة | Glossary: render is «ريندر», and export stays for frames. The whole P-09/P-11 render family follows. |
| 4 | `p09.failed.sub` | Premiere وقف التصدير، غالبًا عشان الذاكرة خلصت. | Premiere وقف الريندر، غالبًا عشان الرام خلصت. | Render term; editors say «الرام». |
| 5 | `p11.p.snapshot.sub` (and 31 more) | … اللوحة بتجرّب تاني لوحدها. | … البانل بيجرّب تاني لوحده. | «اللوحة» is a translation. Editors say «البانل» (masc.), so the agreement is fixed too. |
| 6 | `p08.hint` | … عشان مؤشر التشغيل يروح عندها. | … عشان البلاي هيد يروح عندها. | Same word as the tools group (`p16.wave.hint`). It is the editors' word. |
| 7 | `p13.hush.sub` | بيشيل السكتات وكلمات التردد. | بيشيل السكتات واللزمات. | «كلمات التردد» is MSA. «اللزمات» is the Egyptian word for يعني/طيب, and it is shorter (P-16/P-17 too). |
| 8 | `p15.sync.title` | مزامنة البودكاست | سينك البودكاست | Editors say «سينك». The whole sync family follows. |
| 9 | `p16.track_locked` | … متقطّعش حاجة. | … ما اتقطّعش حاجة. | «متقطّعش» reads as the order "don't cut". The EN says "Nothing was cut". |
| 10 | `p14.error` | … فاتشالوا من الخطة. | … فاتسابوا برّه الخطة. | EN/AR diverged: «اتشالوا» sounds deleted; EN says "left out". |
| 11 | `p05.locked.sub` | … ماتاخدهوش منه غير بعد ما تسأله. | … ما تاخدهوش غير بعد ما تسأل {who}. | EN/AR diverged: the EN names the person. It also uses «الكليب» (glossary). |
| 12 | `p05.failed.sub` | النت فصل، فClaude ماوصلهوش الطلب. … | النت فصل، فالطلب ما وصلش لـ Claude. … | «فClaude» was glued; reworded, with negation apart. |
| 13 | `p20.stage.placing` | حط الكابشن في Premiere | بنحط الكابشن في Premiere | P-20 stages mixed nouns, a verb and an order. All are «بن…» now, as in Hush. |
| 14 | `home.week` | وفّرت حوالي 4 ساعات و30 دقيقة (تقدير) · 7 ريلز | وفّرت حوالي 4 ساعات ونص (تقدير) · 7 ريلز | Natural duration, and shorter (also `p04.demo.s1`). |
| 15 | `p20.error.hint` | … أبطأ، حوالي 2 دقيقة. | … أبطأ، حوالي دقيقتين. | Egyptian dual. |
| 16 | `approval.with` | اتأكد مع {who} | أكّدها {who} | «اتأكد مع» reads as an order. The record line now says who confirmed. |
| 17 | `approval.need_name` (and 4 more) | اكتب اسمك عشان يتفعّل «وافق». | اكتب اسمك عشان «وافق» يشتغل. | One phrase for "turn on" in every group (A-02, P-05, P-18 already said «يشتغل»). |
| 18 | `p22.ai.key.sub` | … بيشتغل وClaude مقفول. Anthropic بتحاسبك على حسابك. | … بيشتغل و Claude مقفول. الفاتورة من Anthropic على حسابك. | «بتحاسبك» also means "holds you to account". EN is "Billed by Anthropic to your account". Spaced «و». |
| 19 | `i00.unsigned` | نسخة تجربة (بيتا). للتجربة بس. | نسخة بيتا للتجربة بس. | No gloss in brackets, no repeated word, and shorter (also `i01.internal`). |
| 20 | `p10.k.render` | راجع الصوت النهائي وصدّر. | راجع المكس النهائي وصدّر. | EN says "final mix". «المكس» is the editors' word. |

Also changed (same reasons):
- «اتفرّج على الأنيماتيك» (was «النسخة التجريبية»);
- «غيّره {who}» (was «اتغيّر بواسطة»);
- «من بروفايل {client}» (was «ملف», which reads as "file");
- `p16.off` «مقفولة» (was «واقفة»);
- «هوك البداية»;
- «الصوت أوطى من» for the silence threshold;
- «بنحسبه إزاي؟», for both "How is this worked out?" keys;
- «خطوط البراند» in the installer, as in D-03 «صور البراند».

## For Yunus to decide

1. **Script of editors' loanwords.** The brief says timeline, render, preset and reel stay in Latin. I kept them in
   Arabic script (السيكوينس، التايملاين، ريل، ريندر، البريسيت، البانل) because the locked D-03 line writes
   «التايملاين». Switching to Latin means one sweep in all files, but D-03 stays as approved.
2. **«البانل» instead of «اللوحة».** This is the biggest change (32 strings). Say if you prefer «اللوحة».
3. **«اللزمات» for filler words.** It is short and Egyptian, but it is a new word in the UI. The fallback is «كلمات
   التردد».
4. **Premiere bins are still «فولدرات».** That is how editors say it, but in Tidy it sits next to folders on disk.
   The alternative is «بِنز».
5. **"Claims review" (A-02) is «مراجعة الجمل الطبية».** That is narrower than the EN, because a claim can be
   religious. It fits this medical-client mock. Option: «مراجعة الجمل الحسّاسة».
6. **«لـ Claude» / «لـ Anthropic» keep a tatweel.** It is the D-01 pattern, and the only exception to "no tatweel".
7. **System names are as the OS shows them in Arabic.** «عناصر تسجيل الدخول», «سماح» and the macOS access dialog are
   MSA on purpose. «حماية التطبيقات الذكية» may not match Windows' own Arabic name for Smart App Control. Check it on
   an Arabic Windows.
8. **Seen on P-01 and P-22: the locked lines have bidi faults.** The words are locked, so I did not touch them:
   - the straight quotes in D-02's "Help improve our AI models" land on the wrong sides in RTL;
   - the bracket before «Pro» in D-01 shows as "Pro)" when it wraps.

   The fix belongs in mockup.js (keep brackets and quotes with their Latin run), or in a decision to use «…» there.
