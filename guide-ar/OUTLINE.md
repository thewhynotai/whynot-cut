# Arabic guide — outline (19 chapters)

Order of the PDF. File names are in `guide-ar/chapters/`; the section id is `chNN`, the h1 id is `chNN-title`, and the h1 text starts with `N · ` (checked by `test_chapter_numbers_match_files`).

State: **written** = describes today's verified behaviour (may still carry a few `.todo` boxes); **3.0-spec** = mostly the binding 3.0 spec, every section behind a `.todo data-phase` box; **skeleton** = title, one intro paragraph and a `.todo` only.

"Finalising phase" = the `data-phase` values still present in the chapter's `.todo` boxes (the master-plan phases that verify that behaviour live). "—" means no `.todo` box is left.

| # | File | Arabic title | Main sources | State | Finalising phase |
|---|---|---|---|---|---|
| 1 | `01-intro.html` | مقدمة | `whynot-cut/skills/help`, `start` | written | 6, 7 (round 2, task 7A) |
| 2 | `02-install.html` | التثبيت خطوة بخطوة | `whynot-cut/skills/setup`, `start`; `whynot-cut/README.md` (Install); Addenda D, E (E2: «WhyNot Cut Setup»), F (F1: public install = one-liner); `installer/` (README, bootstrap, core) | written (today first) + 3.0-spec | 5, 7, 9 (round 2, task 7B: banner, today sections first, one-line install, Setup app internal only) |
| 3 | `03-quick-tour.html` | الجولة السريعة | `skills/start`, `help`, `edit`; Addenda C, D, F | 3.0-spec | 9 (round 2, task 7B: banner, one-line install) |
| 4 | `04-client-folder.html` | فولدر العميل | `skills/client-craft`, `new-client` | written | — |
| 5 | `05-new-client.html` | إعداد عميل جديد | `skills/new-client`, `client-craft` | written | — |
| 6 | `06-edit-one-video.html` | مونتاج فيديو واحد | `skills/edit`, `story-craft`, `transcript-craft`, `audio-craft`, `premiere-craft`, `qc-craft` | written | 6 |
| 7 | `07-premiere-panel.html` | لوحة WhyNot Cut داخل Premiere | Master plan 3.0 (D4/D5); Addendum C; `adobe/panel-ui/i18n/ar.json` | 3.0-spec | 6 (banner and reader boxes, round 2, task 7A) |
| 8 | `08-podcast.html` | وضع البودكاست | `skills/podcast`, `episode-craft`, `publish-craft`; podcast-mode design spec | written | — |
| 9 | `09-motion.html` | وضع الموشن في After Effects | `skills/motion`, `motion-craft`, `adobe-extras`; motion-from-audio design spec | written | 6 |
| 10 | `10-revisions.html` | التعديلات | `skills/revise`, `premiere-craft`, `qc-craft` | written | — |
| 11 | `11-tidy.html` | ترتيب المشروع: WhyNot Tidy | Addendum A (A2, A6b); `addendum-a/prd/tidy-prd.md` (§5 flow, §8 safety rules, §11 tests) | 3.0-spec | 6 (written in round 2, task 6; reader boxes and banner, task 7A) |
| 12 | `12-hush.html` | حذف السكتات: WhyNot Hush | Addendum A (A2, A6b); `addendum-a/prd/hush-prd.md` (§5 flow, §8 safety rules, §11 tests) | 3.0-spec | 6 (written in round 2, task 6; reader boxes and banner, task 7A) |
| 13 | `13-kalam.html` | الكابشن: WhyNot Kalam | Addendum A (A2, A6b); `addendum-a/prd/kalam-prd.md` (§5 flow, §8 safety rules, §11 tests) | 3.0-spec | 6 (written in round 2, task 6; reader boxes and banner, task 7A) |
| 14 | `14-autopilot.html` | التشغيل التلقائي وقائمة «مطلوب منك» | `skills/autopilot`; Master plan 3.0 (Needs you) | written | 4, 6 |
| 15 | `15-magnific.html` | مواد Magnific | Master plan 3.0 (Magnific rules); `skills/motion-craft` | 3.0-spec | 5 (rules moved out of the boxes, banner, round 2, task 7A) |
| 16 | `16-preferences.html` | الإعدادات | `skills/preferences` | written | 3, 6 |
| 17 | `17-troubleshooting.html` | حل المشاكل | `skills/setup`, `start`; agent `setup-doctor`; Addendum D; `installer/` (checklist marks, exit codes) | written | 7, 9 (round 2, task 7B: one-line install rows, reader boxes) |
| 18 | `18-update-uninstall.html` | التحديث وإلغاء التثبيت | `skills/setup`; `whynot-cut/README.md`, `CHANGELOG.md` (Migration); Addenda D, E, F; `installer/` (`uninstall.py`) | written (today first) + 3.0-spec | 7 (round 2, task 7B: banner, today section, one-liner / Setup-app split) |
| 19 | `19-glossary.html` | قاموس المصطلحات والتواصل | all skills; `skills/help`; `guide-ar/STYLE.md` terms table | written | 6 |

Notes

- The three tool chapters (11–13) sit after «التعديلات» (10) so the editor learns the main pipeline first, then the three Premiere tools, then autopilot, Magnific, preferences, troubleshooting, update, glossary.
- Chapters 14–19 were numbered 11–16 before round 2 (renumbered in round 2, task 1). The internal-gate-name lint allows those names only in the glossary, `#ch19`.
- Everything in `STYLE.md` binds every chapter. The truth rule applies: spec-bound 3.0 behaviour is written in the present tense only inside a section with a `.todo data-phase="N"` box.
- Round 2, task 7A (ruling R2-9): every `.todo` box prints «في الإصدار 3.0 — لم يُتحقَّق منه بعد» and keeps one plain reader sentence; team notes sit in `<!-- فريق: … -->` inside the box. Chapters 7, 11, 12, 13 and 15 open with a `.tip` banner saying what works today. The Needs-you label is «مطلوب منك» everywhere (ruling R2-8). Chapters 2, 3, 17, 18 got the same treatment in task 7B: banners in 2, 3 and 18; today's sections first in 2 and 18; the 3.0 public install is the one-line installer (Addendum F), the «WhyNot Cut Setup» app (Addendum E) is for internal builds only.
