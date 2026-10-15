# Round 2: owner decisions (D-01 … D-08)

Date: 2026-10-15. Source: `R2-fix-list.md` §5.

Yunus delegated these decisions to the Adobe track ("do what's right"), with one exception: signing is decided by him. It
is done at the very end, together with the paid edition and its extra features, which is a second phase.

Facts about Anthropic below come from Anthropic's own public pages, read on 2026-10-15. Re-check them on release day:
- claude.com/pricing;
- support.claude.com: "What is the Pro plan?" and "What is the Max plan?";
- anthropic.com: "Updates to Consumer Terms";
- privacy.claude.com: "How long do you store my data?";
- code.claude.com/docs: "Data usage".

## D-01: Claude plan and cost (decided)

**Facts.** Claude Code is included in Pro ($20 a month billed monthly, $17 a month billed yearly; prices vary by
region) and in Max ($100 or $200 a month). It shares the plan's usage limits. The API credits that come with Max do
not cover Claude Code.

**Wording.** State the cost plainly. Never say "no extra charge" alone.
- **EN:** "Each editor needs their own Claude Pro or Max plan, paid to Anthropic (Pro from $20 a month; prices vary by
  country). WhyNot Cut adds nothing on top."
- **AR:** «كل مونتير محتاج اشتراك Claude Pro أو Max باسمه، بيدفعه لـ Anthropic (Pro بيبدأ من 20 دولار في الشهر، والسعر بيختلف من بلد للتاني). WhyNot Cut مش بيزوّد عليه حاجة.»

**Where:** I-05, P-01 (Claude row), P-12, P-22. Link: "See plans", to support.claude.com, Pro plan article.

**P-22:** "Billed by Anthropic" stays. The API-key mode is labelled "Paid per use to Anthropic. Not needed if you
have Pro or Max", and it is never the default.

**Not in the UI:** a price list. One "from" price only, plus the link.

## D-02: client data at Anthropic (decided: option b now, c later)

**Facts:**
- On Free, Pro and Max, the user chooses "Help improve our AI models" in Privacy settings.
  - If it is on, data may be kept, de-identified, for up to 5 years for training.
  - If it is off, the 30-day retention applies.
- On Team and Enterprise (commercial terms), chats and Claude Code sessions are not used for training.

**Wording,** shown under the approved privacy line on I-05, P-01, P-12 and P-22, never on every screen:
- **EN:** "What Claude reads is handled under your Claude plan's terms. For client work, turn off 'Help improve our AI
  models' in Claude's privacy settings. Medical clients: use a Team or Enterprise plan, where data isn't used for
  training."
- **AR:** «اللي Claude بيقراه بيتعامل معاه حسب شروط اشتراكك في Claude. لشغل العملاء، اقفل "Help improve our AI models" من إعدادات الخصوصية في Claude. للعملاء الطبيين: استخدم اشتراك Team أو Enterprise، لأن بياناته ما بتتستخدمش في التدريب.»

**Data sheet:** one page, "Cost and data", linked from I-05, P-01 and P-22 (thewhynot.ai/data). It covers what is sent
and to whom, what is never sent, retention per plan (with links to Anthropic's pages), how to remove data, and the
recommended plan per client type. This is a website page, to be written with the guide track (backlog). The mockups
show the link.

**Later (backlog B-11):** a per-client "Sensitive client" switch that warns when the active Claude account is a
personal plan.

## D-03: the privacy line in Egyptian Arabic (decided: b)

- **AR (approved):** «ملفات الفيديو والصوت عمرها ما بتترفع. Claude بيقرا نصوص بس (التفريغ والخطة) وشوية صور ثابتة: لقطات قليلة من التايملاين عشان المراجعة، وصور البراند.»
- The English line is unchanged.
- The line ends with a full stop everywhere (P-12, P-22 and I-05 were missing it).
- "No telemetry; WhyNot Cut trains on nothing" stays.

## D-04: signing and notarization (Yunus: phase 2)

- Signing is decided by Yunus, at the end, with the paid edition and its extra features (phase 2).
- Until then, the 3.0 beta ships with the "internal / test build" state: honest wording that the build is not yet
  checked by Apple or Microsoft, shown only on beta builds.
- Sales material never shows that state.
- Nothing is bought.

## D-05: support (decided, conservative)

- **Channel:** "Contact support" opens thewhynot.ai/support. "Copy details and open support" is one click: it copies
  the support details and opens the page.
- **Promise shown:** "We reply within one working day (Sun–Thu, Cairo time)."
  - AR: «بنرد خلال يوم عمل واحد (من الأحد للخميس، بتوقيت القاهرة).»
  - This is a conservative promise that can be kept.
  - A faster target (4 working hours, or a WhatsApp line) belongs to the paid phase 2 and needs Yunus to name the
    channel and the person.

### D-05 update (2026-10-16): the support channel is WhatsApp (Yunus)

- Yunus named the channel: the TWN WhatsApp line (he shared https://wa.link/eywgzn).
- That short link opens WhatsApp with a sales message pre-filled ("book a strategy call"), which is wrong for a support
  request. The panel therefore uses the same number as `https://wa.me/<number>?text=WhyNot%20Cut%20support`, so the chat
  opens marked as support. Yunus can swap in a support-specific wa.link at any time; it is one config value
  (`support_url` in `config/defaults/links.json`).
- WhatsApp is live, so the support link is shown by default (H24 is met). Wording: "Copy details and open WhatsApp" /
  «انسخ التفاصيل وافتح واتساب»: one action that copies the details, then opens the chat; the editor pastes them. The
  details are never put in the link.
- The reply promise (D-05) is shown with it: "We reply within one working day (Sun–Thu, Cairo time)."
- The "Cost and data" page (thewhynot.ai/data) and the guide (thewhynot.ai/help) are still not live: they stay gated.
- Allowlist: `wa.me` added for `support.url` only (eng-data-contract §7.10).

## D-06: the build runs without opening a window (decided: b, once proven)

- The default mode is the one that needs no open Claude window, after the engine proves it works on Pro and Max
  (backlog B-12).
- Until then, the mockups keep today's wording.
- The API-key mode is never a default.

## D-07: pricing tiers (phase 2, not on any screen)

The recommendation for the paid phase: team tiers by editor count (up to 5, up to 12, 20 or more), a per-seat add-on,
and a 30-day paid pilot that measures real raw-to-approved times (backlog B-03). No price appears in the UI.

## D-08: Arabic sign-off (decided)

- An AI native-register pass (professional Egyptian) checks the full Arabic UI after the group fixes.
- Yunus reads the screens in the private Artifact when he reviews them; his comments win.
- An outside native writer is used later, for the sales material only.

## Rule: never link to a page that isn't live (executor H24)

thewhynot.ai/support and thewhynot.ai/data are public pages, and Yunus publishes or OKs them. Until a page is live, the
panel and the installer never link to it:
- **Support.** The panel shows the link only when the engine provides `support.url` (G-ENG-DATA contract). Without
  it, "Copy details for support" stays: it copies the details, and the panel opens nothing. Next to it, a plain-text
  line says «صفحة الدعم قريب» / "Support page coming soon".
- **Data sheet.** "Cost and data" appears only when the engine provides a `data.url`. This is a new contract key, an
  executor request. Without it, the D-02 line stands on its own, with the "See plans" link to support.claude.com,
  which is live.
- **Mockups.** Both states are shown: live (link) and not yet live (text).
