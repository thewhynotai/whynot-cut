# خطة المشروع التنفيذية — WhyNot Cut (Adobe Premiere Pro Plugin)

<!-- AUTO:STATUS START -->
> آخر تحديث فعلي: 2026-10-20 01:59 — Africa/Cairo
> مصدر التحديث: hq_status.py / info@ / release/3.0 @ 4c1e59c3
> حالة التشغيل: RUNNING
> حالة المزامنة: HQ = LOCAL+GITHUB_VERIFIED · release/3.0 = LOCAL_AHEAD 50

| Task | Owner | Status (BOARD) |
|---|---|---|
| SETUP-H1 | H1 (Mayar) | IN PROGRESS |
| BL-16 | H1 | READY |
| BL-02 | H1 | READY |
| BL-17 | H1 | READY |
| SETUP-H2 | H2 (marketing@) | IN PROGRESS |
| BL-03 | H2 | READY |
| BL-04 | H2 | READY |
| BL-18 | H2 | READY |
| BL-14 | EXECUTOR | handed over 10-19 |
| (lane 1) | — | STOPPED |
| S6b | H1 | NOT READY |
| STAGE3-DRAFTS | MASTER | NOT READY |
| ENV-01 | MASTER | IN PROGRESS |
| OPS-01 | MASTER | IN PROGRESS |
| OPS-02 | MASTER | NOT READY |
| OPS-03 | MASTER | READY |
| OPS-04 | EXECUTOR | NOT READY |
| OPS-05 | MASTER (observe) | NOT READY |
| OPS-06 | MASTER | READY |
| API-500 | LANE | PLANNED_NOT_AUTHORIZED |
<!-- AUTO:STATUS END -->

الملف ده هو اللوحة بتاعتك. أعلاه بيتحدّث أوتوماتيك 4 مرات في اليوم، والباقي بيتحدّث مع كل تاسك بتتقفل.
مش محتاج تعدّل فيه حاجة. التفاصيل الفنية في `00-HQ/` (نقطة البداية `00-HQ/README.md`).

## 1. ملخص الحالة الحالية

- **المنتج:** WhyNot Cut = plugin لـ Claude Code + engine بايثون (`reel`) + bridge جوه Premiere و After Effects.
  بياخد خام أو حلقة بودكاست ويطلّع مشروع Premiere وريلز وموشن وباكدج نشر.
- **المرحلة:** Stage 1 من الـ roadmap = قفل **Gate 4** (الإصدار `v3.0.0-p4`). بعده نبدأ **V1 = الـ panel جوه Premiere**.
- **آخر نسخة شغالة ومتجرّبة على Premiere فعلًا:** `v2.2.1` (متسطّبة على الجهاز ده)، و 3.0 اتجرّب منها live
  build + frames على Premiere 26.5.2 يوم 14–15 أكتوبر بالـ bridge 3.1.1 (الدليل:
  `WhyNotCut/docs/adobe/live-roundtrip-2026-10-14.md`).
- **نسخة تجربة 3.0:** `PREVIEW-3.0.0-p4` في فولدرات «خد دا كوبي للويندوز/للماك» (commit 322d8a5). دي **مش release**،
  ومتأخرة عن الكود الحالي بـ 50 commit.
- **إيه شغال جوه Premiere فعلًا:** الشات في Claude بيبني sequence في Premiere عن طريق الـ bridge، ويصدّر frames
  ويتأكد منها، ويعيد البنا بعد تعديل. **مش شغال لسه:** الـ panel نفسه جوه Premiere (UXP) بالشات والزراير = V1.
- **أهم إنجاز النهارده:** نظام الإدارة الجديد اتأسس فوق `00-HQ`، والـ API اتقفل لحد أمرك، ونسخة احتياطية كاملة
  اتعملت، ولقينا سبب فشل tests المساعدين.
- **أهم مشكلة:** المساعدين ماكانش ينفع يتقبل منهم أي شغل لأن الـ tests عندهم بتفشل (563) لسبب في البيئة مش في
  الكود. الحل شغال دلوقتي (ENV-01).

## 2. الـ Product Roadmap بالكامل

كل Milestone لازم يطلّع حاجة تتشاف وتتجرّب. `[x]` = متقفلة بدليل بس.

- [ ] **M0 — نظام التشغيل والإدارة (Operations Bootstrap)** — Command Center — شغالين فيه النهارده
  - شروط الإغلاق: checklist الـ charter §29 كلها بدليل (شوف §7 تحت).
  - [x] OPS-00 — Audit + baseline + أرشفة أول دفعة — Command Center — DONE — دليل: `00-HQ/reports/2026-10-20-audit.md`, `00-HQ/ARCHIVE_MANIFEST.md`
  - [ ] ENV-01 — بيئة الـ tests للمساعدين — Command Center — IN_PROGRESS — دليل: `00-HQ/tasks/ENV-01.md`
  - [x] OPS-01 — مولّد الحالة والتقارير + المزامنة مع GitHub — Command Center — DONE_ARCHIVED — 25/25 tests، مراجعتين مستقلتين، GitHub `ops/hq` d7ac597 — `00-HQ/tasks/archive/OPS-01/`
  - [ ] OPS-02 — جدولة 4 تقارير يومية وتجربة التسليم — IN_PROGRESS — الـ routine اتعملت (9/1/5/9)، أول تشغيل مستني موافقتك مرة واحدة (Q-005)
  - [ ] OPS-05 — أول دورة handoff حقيقية بين H1 و H2 (peer review) بدليل — بعد ENV-01
- [ ] **M1 — Gate 4 → `v3.0.0-p4` (أول build متجرّب جوه Premiere لـ 3.0)** — الـ executor — IN_PROGRESS
  - النتيجة اللي هتشوفها: build حي لـ PODCAST-TEST جوه Premiere + frames، والنسخة في `Releases`.
  - شروط الإغلاق: review مستقل 0 Critical / 0 Important، الـ suite كاملة 0 failures، `validate --strict` مرتين،
    evals، macOS CI أخضر، تجربة live، سطر الأمان، ميزانية T4.14، تقرير `GATE-4-REPORT-AR.md`، tag.
  - المفتوح (من `WhyNotCut/PROGRESS.md`): T4.1، Task 18/22 (BL-02/BL-03)، Task 25 + K-T7، Task 26 wiring، Task 29،
    Tasks 50–60، manual verse slot، «كل features الـ S1 متوصلة»، BL-01، BL-04، BL-15، **T4.14 (محتاجك: 60 ثانية تفريغ)**.
  - تاسكات المساعدين لـ Gate 4: BL-16 (H1، DONE مستني review)، BL-02 (H1، شغالة)، BL-04 و BL-03 و BL-18 (H2).
- [ ] **M1b — تجربة ماك صغيرة (ساعة)** بعد الـ tag على طول — Mac tester — BACKLOG
- [ ] **M2 — خطة بناء V1 (Stage 2)** — Command Center — BACKLOG — الشرط: الـ tag. الناتج: خطط Stage 3–9 مكتوبة.
- [ ] **M3 — أساس الـ panel (Stage 3) = أول plugin بيشتغل جوه Premiere بالـ UI بتاعه** — H1/H2 (+ API-500 لو اتفعّلت)
  - النتيجة: الـ panel يفتح في Premiere 26.5، الشات جواه يشغّل raw-clip و reels-plan، والـ sequence يتبني. live على ويندوز.
- [ ] **M4 — أدوات الضغطة الواحدة (Kalam / Hush / Tidy)** — Stage 4 — كل tab شغال على كليب حقيقي.
- [ ] **M5 — الكابشن والصوت** — Stage 5.
- [ ] **M6 — Beat sync و multicam و tracking** — Stage 6.
- [ ] **M7 — Liquid Glass و AE looks** — Stage 7.
- [ ] **M8 — Hardening** — Stage 8 (gates الأمان والأداء).
- [ ] **M9 — باكدج الفلاشة والدليل** — Stage 9: تسطيب offline على ويندوز وماك نضيف في أقل من 10 دقايق.
- [ ] **M10 — تجربة حقيقية + ماك live** — Stage 10.
- [ ] **M11+ — الإصدارات اللي بعد كده.**
- Release cuts (R) بتتعمل عند كل milestone متقفلة، في session attended، بكلمتك.

المرجع الكامل: `WhyNotCut/docs/superpowers/plans/2026-10-18-master-roadmap-v1.md` والـ spec
`WhyNotCut/docs/superpowers/specs/2026-10-18-v1-premiere-panel-design.md`.

## 3. قائمة التنفيذ بالترتيب

- [x] آخر تاسكات مكتملة: OPS-00 (audit + baseline + أرشفة) — `00-HQ/reports/2026-10-20-audit.md`؛ OPS-01 (الـ pilot الكامل: tests → مراجعة مستقلة → commit → GitHub → أرشفة) — `00-HQ/tasks/archive/OPS-01/`
- [ ] **التاسك الحالية:** ENV-01 — تسطيب الـ runtime في البيئة الحقيقية، وبعدها suite كاملة لـ H1 تثبت إن الـ 563
  اتحلوا. المسؤول: Command Center.
- [ ] **اللي بعدها:** OPS-01 → OPS-02 (التقارير)، وفي نفس الوقت الـ executor بيكمّل Gate 4، والمساعدين بيكمّلوا كروتهم.
- [ ] **المحجوب:** API-500 (مستني أمرك)، T4.14 (مستني 60 ثانية تفريغ منك)، H14 (موافقة Anthropic، مهم بس برّه الوكالة).

كل تاسك بتمشي بالـ checklist دي (الـ charter §24.2):
فحص المتطلبات ← معايير القبول ← تنفيذ محدود ← tests ← مراجعة مستقلة ← تجربة Premiere لو مطلوبة ← تحديث الملفات ←
commit/push والتأكد من الـ SHA ← محضر أدلة + أرشفة سجلها ← تسليم التاسك اللي بعدها.

## 4. الحسابات الثلاثة

| الحساب | الدور | الحالة الموثّقة |
|---|---|---|
| **PRIMARY** = حسابك (info@) | Command Center: القرارات، الاستلام، المراجعة، التقارير، تفعيل الـ API | الشات ده |
| **ASSISTANT_A** = H1 (mayar@) | Engine builder | AUTO شغال (من 00:46) على BL-02 |
| **ASSISTANT_B** = H2 (marketing@) | Product builder + peer review لشغل H1 | واقف بـ STOP من 20:55 امبارح، بيرجع مع ENV-01 |

- التسليم بين الحسابات عن طريق الملفات بس: الكارت في `00-HQ/tasks/`، والتقرير في `00-HQ/inbox/<h>/`،
  والـ review في `00-HQ/reviews/`، والـ branch `<h>/<ID>`. محدش بيكلّم حد في الشات.
- **مفيش إثبات لسه** على دورة كاملة بين الحسابين (peer review حقيقي). ده OPS-05.

## 5. نسخ البرنامج والإصدارات

| النسخة | القناة | فين | Premiere / OS متجرّب | الحالة |
|---|---|---|---|---|
| `v2.2.1` (tag، main 4831de5) | stable داخلي | متسطّبة على الجهاز | Premiere 26.5.2 / Windows 11 | شغالة ومتجرّبة |
| `v3.0.0-p3.1` (tag 29c1b38) | gate داخلي | GitHub tag | Windows suite 3374 OK + macOS CI | Gate 3 عدّى (ويندوز) |
| `PREVIEW-3.0.0-p4` (322d8a5) | preview للتجربة | `خد دا كوبي للويندوز` / `للماك` + checksums | لسه مفيش تجربة live لـ panel 3.0 | قديمة بـ 50 commit |
| `v3.0.0-p4` | gate | — | — | **مخطط** (Gate 4)، مش موجود لسه |
| V1 | alpha للوكالة | — | — | **مخطط** (M3–M9) |

## 6. الملفات والأرشيف وGitHub

- **الهيكل المعتمد:** الملف ده (لوحتك) ← `00-HQ/README.md` (البداية لأي session) ← `PLAYBOOK.md` (القواعد) ←
  `BOARD.md` (التاسكات) ← `tasks/` و `inbox/` و `reviews/`. الكود في `WhyNotCut/` (git).
- **اتأرشف النهارده (8 ملفات، من غير مسح):** `V1-SCOPE-AR.md`، `NEW-PLAN-BRIEF-AR.md`، `WHYNOT-CUT-3.1-PLAN.md`،
  `PROJECT-PLAN-AR.md` القديم، `API-LANES-PLAN.md`، نسختين `.bak-kt8`، و `00-HQ/MASTER-PLAN-AR.md`.
  كلهم في `_archive/plans-2026-10/`، والسجل في `00-HQ/ARCHIVE_MANIFEST.md`.
- **Git:** `release/3.0` = 4c1e59c محلي، و GitHub عليه 322d8a5 (فرق 50 commit؛ الـ push بتاع الـ executor بعد الـ suite).
  نسخة احتياطية: branch `ops/backup-release-3.0-20261020` على GitHub = 4c1e59c (متأكد منها).

## 7. Plugins / Skills / Routines

- **الـ Plugins:** superpowers (TDD/review)، plugin-dev، andrej-karpathy-skills (اتسطّب امبارح، نفس نص `CLAUDE.md`)،
  whynot-cut 2.2.1. التفاصيل والتجارب: `00-HQ/PLUGIN_CAPABILITY_MATRIX.md`.
- **الـ Routines:** كلها كانت **متوقفة (disabled)** من امبارح 8:40 بالليل (السبب مش معروف، اتكرر قبل كده). حالة كل
  واحدة وإيه اللي رجع: `00-HQ/AUTOMATION_RUNBOOK.md`.
- **Checklist الـ charter §29 (M0):**
  - [x] Inventory للمشروع والـ agents والـ routines والشاتات
  - [x] Baseline محفوظ (backup + git bundle + branch على GitHub)
  - [x] أرشفة أول دفعة بـ manifest
  - [x] مزامنة GitHub للـ HQ (`ops/hq`) — OPS-01، local = remote متأكد في كل تشغيل
  - [x] Queue و lease و handoff و archive موجودين (00-HQ) — الـ TASK_QUEUE.yaml المولّد في OPS-01
  - [x] هويات الحسابات الثلاثة اتأكدت (D-002)
  - [ ] تجربة read/write و handoff لكل حساب — OPS-05
  - [x] scheduler + runner (helper AUTO loop + keepalive) موجودين ومتجرّبين 21/21 بـ fake Claude
  - [ ] resume بعد restart للجهاز — اتشاف فعليًا النهارده لـ H1 (keepalive 00:46)، لسه لـ H2
  - [ ] تقرير الصبح والليل + 4 تقارير PRIMARY مجدولة ومتجرّبة — OPS-02
  - [x] خطة الـ $500 جاهزة ومش متفعّلة (`00-HQ/BUDGET-API.md`)
  - [x] Pilot كامل: تاسك → QA مستقل → commit → GitHub → أرشفة → التاسك اللي بعدها — OPS-01 → OPS-02

## 8. خطة الـ API بحد أقصى 500 دولار

- **الحالة: PLANNED_NOT_AUTHORIZED.** المصروف عليها: 0.
- **المهمة:** Stage 3 (أساس الـ panel)، الجزء الميكانيكي اللي مش محتاج Premiere live، + review مستقل لكل تسليم.
- **التفعيل:** بس لما تكتب «نفذ خطة الـ API». ساعتها: login للـ Console، screenshot للرصيد، حد 500 في الـ Console لو متاح.
- **الضوابط:** تنبيه عند 250/400/475، مفيش run جديد تحت 40 متبقي، وقفة كاملة عند 480 تقديري.
- **اتقفل النهارده:** خطة نوفمبر القديمة (450) كانت هتشتغل لوحدها يوم 1/11. اتحوّلت لـ HOLD مايتفكش غير بأمرك.
- التفاصيل: `00-HQ/BUDGET-API.md`.

## 9. تقرير الصبح / تقرير الليل

بيتكتب هنا أوتوماتيك الساعة 9 الصبح و 9 بالليل (بعد OPS-02). التقارير القديمة في `00-HQ/reports/`.

## 10. سجل التحديثات المختصر

- 2026-10-20 — تأسيس نظام الـ charter فوق 00-HQ، baseline، أرشفة 8 ملفات، HOLD على الـ API، اكتشاف سبب فشل tests
  المساعدين. الأدلة: `00-HQ/reports/2026-10-20-audit.md`.
