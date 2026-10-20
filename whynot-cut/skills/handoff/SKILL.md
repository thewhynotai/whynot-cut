---
name: handoff
description: "Write the editor handoff for a finished or paused edit: \"write the handoff\", \"package it for the editor\", \"summarise what's left\", «سلّم الشغل», «جهّز التسليم»."
argument-hint: "[clip id]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Handoff

1. `reel qc` (this message), then `reel handoff`. This writes `09_handoff/README.md` and `final-editor-checklist.md`.
2. Update the client folder's `HANDOFF.md` (create it if missing) so the work can continue on another device. Include:
   - what was done, with dates
   - where everything is (paths relative to the client folder)
   - how to resume on another Mac or PC: install WhyNot Cut from the marketplace (`/plugin marketplace add <marketplace>`,
     `/plugin install whynot-cut@thewhynot-ai`), run `/whynot-cut:start`, then `/whynot-cut:status`
   - the open items ("Needs you"), with evidence
   - known caveats
3. When the editor says the finished video went to the client, record it (the lead only):
   `reel handoff --delivered --note "<where / when>"`. It needs qc passed and the handoff written (else it is refused,
   exit 2) and sets the status DELIVERED, which the client board, `reel next` and the stale checks count as done.
4. Never describe something as done unless it's verified (see `/whynot-cut:status`). Keep "Not verified" honest.
5. In your own messages, tables and file names, «الدكتور/الدكتورة» and he/she come only from people[] (reel-profile
   `profile.json`). Until a person's gender is known write «د.» or the name.
6. نقل عميل لمكان تاني: `reel client-move --root <العميل> --to <المكان الجديد>` (تجربة)، وبعدين نفس الأمر بـ `--apply`. لو اتنقل بالإيد: `reel client-move --root <مكانه دلوقتي> --already-moved --apply`. بعد النقل: اعرض على المونتير الموافقات اللي في NEEDS-YOU، وهو اللي يوافق تاني؛ ماتوافقش بداله.
7. عميل جديد بنفس براند عميل موجود: `reel client-clone --root <العميل> --to <فولدر جديد أو فاضي>` (تجربة، مابيكتبش حاجة)، وبعدين نفس الأمر بـ `--apply`. بينسخ قاعدة البراند بس، من غير ميديا، وعمره ما بيكتب جوه فولدر عميل.
