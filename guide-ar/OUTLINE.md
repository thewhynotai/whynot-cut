# Arabic guide — outline (19 chapters)

Order of the PDF. File names are in `guide-ar/chapters/`; the section id is `chNN`, the h1 id is `chNN-title`, and the h1 text starts with `N · ` (checked by `test_chapter_numbers_match_files`).

State: **written** = describes today's verified behaviour (may still carry a few `.todo` boxes); **3.0-spec** = mostly the binding 3.0 spec, every section behind a `.todo data-phase` box; **skeleton** = title, one intro paragraph and a `.todo` only.

"Finalising phase" = the `data-phase` values still present in the chapter's `.todo` boxes (the master-plan phases that verify that behaviour live). "—" means no `.todo` box is left.

| # | File | Arabic title | Main sources | State | Finalising phase |
|---|---|---|---|---|---|
| 1 | `01-intro.html` | مقدمة | `whynot-cut/skills/help`, `start` | written | 7 |
| 2 | `02-install.html` | التثبيت خطوة بخطوة | `whynot-cut/skills/setup`, `start`; Addendum D (zero-effort install); `installer/` | written | 5, 6, 7 |
| 3 | `03-quick-tour.html` | الجولة السريعة | `skills/start`, `help`, `edit`; Addendum C | written | 7, 9 |
| 4 | `04-client-folder.html` | فولدر العميل | `skills/client-craft`, `new-client` | written | — |
| 5 | `05-new-client.html` | إعداد عميل جديد | `skills/new-client`, `client-craft` | written | — |
| 6 | `06-edit-one-video.html` | مونتاج فيديو واحد | `skills/edit`, `story-craft`, `transcript-craft`, `audio-craft`, `premiere-craft`, `qc-craft` | written | 6 |
| 7 | `07-premiere-panel.html` | لوحة WhyNot Cut داخل Premiere | Master plan 3.0 (D4/D5); Addendum C; `adobe/panel-ui/i18n/ar.json` | 3.0-spec | 6 |
| 8 | `08-podcast.html` | وضع البودكاست | `skills/podcast`, `episode-craft`, `publish-craft`; podcast-mode design spec | written | — |
| 9 | `09-motion.html` | وضع الموشن في After Effects | `skills/motion`, `motion-craft`, `adobe-extras`; motion-from-audio design spec | written | 6 |
| 10 | `10-revisions.html` | التعديلات | `skills/revise`, `premiere-craft`, `qc-craft` | written | — |
| 11 | `11-tidy.html` | ترتيب المشروع: WhyNot Tidy | Addendum A (A2, A6b); `addendum-a/prd/tidy-prd.md` (§5 flow, §8 safety rules, §11 tests) | skeleton | 6 (written in round 2, task 6) |
| 12 | `12-hush.html` | حذف السكتات: WhyNot Hush | Addendum A (A2, A6b); `addendum-a/prd/hush-prd.md` (§5 flow, §8 safety rules, §11 tests) | skeleton | 6 (written in round 2, task 6) |
| 13 | `13-kalam.html` | الكابشن: WhyNot Kalam | Addendum A (A2, A6b); `addendum-a/prd/kalam-prd.md` (§5 flow, §8 safety rules, §11 tests) | skeleton | 6 (written in round 2, task 6) |
| 14 | `14-autopilot.html` | التشغيل التلقائي وقائمة «محتاجك» | `skills/autopilot`; Master plan 3.0 (Needs you) | written | 4 |
| 15 | `15-magnific.html` | مواد Magnific | Master plan 3.0 (Magnific rules); `skills/motion-craft` | 3.0-spec | 5 |
| 16 | `16-preferences.html` | الإعدادات | `skills/preferences` | written | 3 |
| 17 | `17-troubleshooting.html` | حل المشاكل | `skills/setup`; agent `setup-doctor`; Addendum D | written | 7, 9 |
| 18 | `18-update-uninstall.html` | التحديث وإلغاء التثبيت | `skills/setup`; Addendum D; `installer/` | written | 7 |
| 19 | `19-glossary.html` | قاموس المصطلحات والتواصل | all skills; `skills/help`; `guide-ar/STYLE.md` terms table | written | — |

Notes

- The three tool chapters (11–13) sit after «التعديلات» (10) so the editor learns the main pipeline first, then the three Premiere tools, then autopilot, Magnific, preferences, troubleshooting, update, glossary.
- Chapters 14–19 were numbered 11–16 before round 2 (renumbered in round 2, task 1). The internal-gate-name lint allows those names only in the glossary, `#ch19`.
- Everything in `STYLE.md` binds every chapter. The truth rule applies: spec-bound 3.0 behaviour is written in the present tense only inside a section with a `.todo data-phase="N"` box.
