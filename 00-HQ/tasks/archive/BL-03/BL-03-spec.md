<!-- Verbatim copy of BACKLOG.md section BL-03, taken 2026-10-19 00:40. BACKLOG.md stays the source if they differ. -->
### BL-03 [Gate 4]: Task 22 R-T11 GPL-compliance + trademark notice templates  [Gate 4 value: med]  Model: opus
- Depends on: none
- Spec: plan "### Task 22"; Addendum I §I4 (R5.6 reduced).
- Owned files: new `docs/legal/notices/**` (Arabic + English templates), `whynot-cut/tests/test_legal_notices.py`.
- Must not touch: anything else.
- Done criteria: two templates (GPL-compliance request; trademark notice), each Arabic + English, listing what to attach (commit history, release hashes, tag names); templates only: no person's name, no email, no DMCA or cease-and-desist kit; a test checks both languages exist, no personal names/emails/phone numbers, and the "Source-R" naming rule (no audited project names).
- **Pre-mortem 2026-10-18 (owner rule; part of the done criteria):** templates use `{{contact}}`-style placeholders (allow-listed in the test) instead of a banned email/phone; each template starts with a "not legal advice; have a lawyer review before sending" banner in both languages; a test refuses any law article number (no invented articles of Law 82/2002).
- Risk: normal

