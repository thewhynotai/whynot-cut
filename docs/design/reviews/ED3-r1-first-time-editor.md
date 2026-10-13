# E-D3 round 1 — first-time Arabic editor (pattern round: P-01, P-03, P-07)

Reviewer: AI agent role-playing a non-technical Egyptian editor, Arabic first. Input: the contact sheets in
adobe/panel-ui/design/renders/_sheets/ (pattern round). Result: 20 «مش فاهم» moments, 10 MAJOR, 10 MINOR.
Verdict: the layout is clear (the violet button is obvious), but "engine" and "Claude" are never explained, errors
give no next step, and the flagged-lines box leaves the editor unsure whether approving is allowed.

## P-01 first-run
1. MAJOR — «المحرّك» means nothing. Explain it once (e.g. «خدمة WhyNot Cut على جهازك»).
2. MAJOR — "Claude" never explained; why does something open outside Premiere? One explanatory line.
3. MAJOR — offline status row drops the names («لا يعمل / غير معروف / غير متصل»; EN too). Always show the name.
4. MAJOR — error «Premiere غير مرتبط بالمحرّك» + retry: no next step if retry fails. Add the hint.
5. MINOR — stale banner: does «تحقق مرة أخرى» restart Premiere? Say the order: close, reopen, then check.
6. MINOR — «لم يُختَر أي عنصر»: element of what? → video.
7. MINOR — version number is noise; «نسخ التشخيص» → copy a problem report for support.

## P-03 home
8. MAJOR — «مطلوب منك 2/3» badge disagrees with the tab count and doesn't look clickable. One count; make it open the list.
9. MAJOR — error state contradicts itself (engine "connected ✓" + "engine did not answer"; title still "ready").
10. MAJOR — offline: Tidy/Hush/Kalam stay active (Kalam "ready"). Disable them like the step cards.
11. MAJOR — tool names need Arabic-first labels; «الترجمة النصية» reads as translation → «كابشن»; «قصّ السكتات» → «شيل السكتات».
12. MINOR — «جاهز لـ C0239» renders with a detached ل; «جاهز» overused → «الفيديو الحالي: C0239».
13. MINOR — «أضف ملفاتك» card with arrow: what happens? → «افتح مجلد العميل».
14. MINOR — «(Sequence)», «(Models)»: Models is scary; hide under Settings.
15. MINOR — empty state shows English folder names in code font; explain them.

## P-07 approval
16. MAJOR — flagged lines: is Approve allowed before the doctor confirms? «الطبيب» for a religious line? Domain-specific wording + an «اتأكدت» confirmation before Approve enables.
17. MAJOR — stale «تغيّرت الخطة»: shows only hash and number drift. Show what changed (diff summary).
18. MAJOR — «افتح Claude»: open what, where?
19. MAJOR — error «لم تنجح العملية»: which operation; did my approval go through? → «الموافقة ما اتسجلتش. جرّب تاني».
20. MINOR — English in brackets everywhere; plan hash shown; «أشرطة عبارات» literal; «طلب» vs «اطلب»;
    «يمكن أن يبدأ البناء» ambiguous; timecodes and step arrow look clickable (make them seek, or not look clickable).
