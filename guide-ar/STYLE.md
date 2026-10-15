> This file binds every chapter author of the Arabic guide (guide-ar/chapters). Read it before writing or editing a chapter.

# Arabic writing style for the guide (binding)

Reader: a video editor in Egypt (also KSA/UAE), comfortable with Premiere, not a programmer.

## Register
- Clear, simple Modern Standard Arabic that an Egyptian reads naturally. Short sentences. No heavy classical words
  (avoid: «يتعيّن»، «آنفًا»، «ريثما»). No Egyptian slang in prose («عايز»، «بتاع»، «هتلاقي» → no).
  Exception: the exact phrases the editor SAYS to Claude are quoted as the editor would type them, in «…», e.g.
  «عدّل الفيديوهات الجديدة»، «طلّع ريلز من الحلقة»، «اختار انت»، «ثبّت WhyNot Cut»، «رتّب البروجكت»، «شيل السكتات
  والآآ». The three verbs tagline is kept exactly: «حط الملفات · قول عايز إيه · وافق على الخطة».
- Address the reader with the generic masculine imperative (افتح، اكتب، ضع) — the standard convention of Arabic
  software documentation. Never refer to a specific person's gender; people in examples are «د.» + name or a role.
- English UI terms in parentheses after the Arabic the first time in a chapter: «لوحة WhyNot Cut (panel)»،
  «الموافقة على الخطة (approve the plan)»، «المعاينة (preview)». Product/app names stay in Latin: WhyNot Cut, Claude,
  Premiere Pro, After Effects, Magnific, YouTube, Instagram, TikTok.

## Owner decisions
- Product line: «WhyNot Cut · Powered by thewhynot.ai» (never "Powered by Claude"); «Claude Code» is never the
  product name (the app the editor installs is «تطبيق Claude»).
- Tools: **WhyNot Tidy** «تايدي» (organise + podcast sync), **WhyNot Hush** «هَش» (silence and filler cut),
  **WhyNot Kalam** «كلام» (captions). "Hoka" never appears.
- Where the panel has an Arabic string for the same thing (`adobe/panel-ui/i18n/ar.json`), use the panel's wording.

## Terms (use exactly these)
| Concept | Arabic |
|---|---|
| client folder | فولدر العميل (first use: «فولدر العميل (client folder)») |
| raw footage | الخام / الفيديوهات الخام |
| episode | الحلقة |
| reel | ريل (plural ريلز) |
| plan | الخطة |
| approve | توافق على / الموافقة |
| preview video | فيديو المعاينة |
| quality check (QC) | فحص الجودة (QC) |
| hand-off | التسليم (handoff) |
| preferences | الإعدادات (preferences) |
| transcript | التفريغ النصي (transcript) |
| graphics | الجرافيك |
| captions | on-screen: «الكلام المكتوب على الشاشة (captions)» / Kalam output: «الكابشن»; social post text: «الكابشن» |
| motion mode | وضع الموشن |
| podcast mode | وضع البودكاست |
| Claude | Claude (no article), «تطبيق Claude» for the desktop app |
| Needs you | «مطلوب منك (Needs you)» — one label everywhere, the panel's own label (`needs.label` in `ar.json`); «(Needs you)» at first use per chapter, then «مطلوب منك» alone (ruling R2-8 replaced the round-1 «محتاجك») |
| Verified / Not verified | «تم التحقق (Verified)» / «لم يُتحقَّق منه (Not verified)» |
| example ids | clip `C0001`, client «عيادة مثال», client folder `Example Clinic`, profile id `example-clinic`, prefix `EC`, episode `EP01`, reel `EP01_R03` |

## Typography / markup (the build lint enforces most)
- Every command, path, file name, folder name, clip id, timecode, version, flag, URL, email:
  `<bdi dir="ltr"><code>…</code></bdi>` (commands/paths/files) or `<bdi dir="ltr">…</bdi>` (timecodes, versions,
  ratios like 9:16, URL, email). Isolate a whole Latin name+number together (`<bdi dir="ltr">Windows 10/11</bdi>`).
- Western digits 0–9 everywhere.
- Procedures = `<ol class="steps">` + a `.shot` placeholder (fictional example-clinic) whose caption says what the
  screenshot will show. Label paragraphs ending in «:» before a list/block get `class="lead-in"`.
- Callouts: `.tip` (نصيحة), `.warn` (تنبيه), `.todo data-phase="N"` for anything a later phase finalises/verifies.
- Chapter: `<section class="chapter" id="chNN">`, `<h1 class="ch-title" id="chNN-title">N · العنوان</h1>`, `<h2 id="chNN-…">`
  with unique heading text across the guide; h3 sparingly. Cross-references are links: `<a href="#chNN-title">الفصل&nbsp;N</a>`.
- Never "Gate 0/1/2", stage numbers or agent names as things the reader must know (one glossary line excepted).
- Truth rule: today's verified behaviour needs no box; spec-bound 3.0 behaviour may be written in the present tense
  only in a section that has a `.todo data-phase="N"` naming the phase that verifies it live; undecided items only
  inside `.todo`. Facts only from the named sources.

## Explained once
No developer words anywhere a reader sees (Addendum G2). The build lint (`build.py` `DEV_WORDS`, `dev_word_problems`)
reads the visible prose of the chapters (no `<code>`, `.cmd` boxes, comments or `›` menu paths) and fails on:
- a word from `DEV_WORDS` (token, daemon, JSON, CLI, API, venv, Python, MCP, PATH, XML, CEP, …, and Arabic forms such
  as «مسار»، «امتداد»، «جذر»، «برمجيًا»، «سطر أوامر»، «للمطوّر») that this table does not list;
- a term this table lists whose FIRST use in reading order is not inside an element with `data-term-first="<key>"`
  (the key is the first backticked form in the row). That first use carries the explanation in the same sentence;
  later uses are free. Wrap it as `<span data-term-first="مسار">…</span>` (or put the attribute on the element).

Everywhere else use the plain Arabic replacement: «مكان» for where a file is, «داخل فولدر العميل مباشرة» for "root",
«ثابت داخل البرنامج نفسه» for "programmatic", «للدعم» for "for the developer". One word means one thing: «إضافة» is only
the WhyNot Cut plugin in Claude, Adobe's add-ons are «لوحات»; «مسار» is only a file path, Premiere's are «تراكات».
«hook» is not a developer word here: it is the editing term «البداية الجاذبة (hook)».

| Term (forms the lint matches) | First-use explanation (Arabic) | Where (after round 3) |
|---|---|---|
| `محرك` (engine) | «وهو البرنامج الذي ينفّذ عمل WhyNot Cut على جهازك في الخلفية» | ch01, requirements lead |
| `نموذج` `نماذج` (model) | «ملف كبير فيه خبرة جاهزة في فهم الكلام، يستخدمه WhyNot Cut ليحوّل الصوت إلى نص» | ch01, «ما الذي يقدّمه» |
| `مكتبة` `مكتبات` (NVIDIA library) | «ملف إضافي من NVIDIA يجعل كارت الشاشة يسرّع التفريغ» | ch01, «ما الذي يقدّمه» |
| `مسار` (path) | «والمسار عنوان الملف على جهازك: أسماء الفولدرات التي توصل إليه بالترتيب» | ch01, «كيف تقرأ هذا الدليل» |
| `Terminal` `PowerShell` | «نافذة نصية تأتي مع نظام التشغيل: تلصق فيها أمرًا وتضغط Enter فيُنفَّذ» | ch02, chapter lead |
| `إضافة` `إضافات` (plugin in Claude) | «الجزء الذي يعرّف Claude بأوامر WhyNot Cut وطريقة عمله» | ch02, «اليوم: التثبيت» step 2 |
| `XML` | «ملف مشروع بصيغة عامة يستورده Premiere من File › Import، بدل مشروع Premiere الأصلي» | ch02, setup wizard step 2 |
| `توقيع` (signed) | «ختم رقمي من الشركة يثبت أن الملف أصلي ولم يُعدَّل» | ch02, Bridge warning |
| `حزمة` `حزم` (bundle) | «مجموعة نماذج وأدوات تُنزَّل معًا، مثل حزمة «كلام»» | ch02, «من داخل Claude» step 4 |
| `Python` | «لغة برمجة يحتاجها المحرك، ولا تتعامل معها أنت» | ch02, «ما الذي يُثبَّت تلقائيًا» |
| `امتداد` (file extension) | «ما بعد النقطة في اسم الملف، مثل .mp4 أو .md» | ch04, short clip names |
| `API` (Anthropic API key) | «رمز سري من حساب مطوّر في Anthropic؛ لا تحتاج إليه» | ch07, AI buttons |
| `سكريبت` (AE script; also the English `Script` in the glossary and in Adobe's own labels) | «ملف يبني المشروع داخل After Effects عندما تشغّله» | ch09, script fallback |
| `تعريف الكارت` (driver) | «برنامج تشغيل الكارت من NVIDIA» | ch13, Kalam on Windows |
| `PATH` (installer checkbox) | «يجعل الجهاز يجد Python عندما يطلبه المحرك» | ch17 (only while the Python row exists) |
| admin, ffmpeg, Git for Windows, CPU, zip, السجل | explained in place, Arabic first, English in parentheses (not linted) | ch02, ch07, ch08, ch17 |

## 3.0 boxes are written for the reader (ruling R2-9)
- The `.todo` box prints the label «في الإصدار 3.0 — لم يُتحقَّق منه بعد» (CSS, no phase number). `data-phase="N"`
  stays on every box: the lint needs it and a release build fails on any `.todo`.
- Visible text in a box: ONE plain sentence that says what this means for the reader (e.g. «أسماء الأزرار قد تتغيّر
  قليلًا في اللوحة النهائية.»). An undecided item the reader must know about is said in that sentence in plain words.
- Everything for the team goes into an HTML comment inside the same aside, starting «فريق:», with the exact wording
  kept: `<aside class="todo" data-phase="6"><p>…</p><!-- فريق: … --></aside>`. Team notes are: H-item codes (H12,
  H14 …), phase numbers and «6B», «حسب الإضافة A», hosting, certificates, test projects and test machines, label-
  matching notes, spec conflicts. Comments are never printed.
- Never move a safety rule or a fact the reader needs out of visible text: put it in the section's body (the
  section has the box, so present tense is allowed) and keep the box to its one sentence.
- Chapters that are mostly 3.0 (7, 11, 12, 13, 15; 2, 3, 17, 18 in their own way) open with a `.tip` before the
  first h2: what works today, with a link to it, and «باقي هذا الفصل يصف الإصدار 3.0».
- Today's wording never says «النسخة الحالية» (a draft phrase the release lint rejects): write «اليوم» or «النسخة
  التي معك اليوم».
