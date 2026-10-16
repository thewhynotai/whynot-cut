# Addendum I: open source, the strongest of everything, no sale for now

| | |
|---|---|
| Date | 2026-10-15 |
| Owner decision (Yunus) | «فكك من البيع خلاص بقي انا عاوزها اوبن سورس ومتحدد المودلز انا عاوزها اقوي حاجه وفيها كل حاجه ولما هحتاج بيع هقولك نعملها» |
| Overrides | the commercial parts of Addendum G; Addendum H R4 (proprietary licence) and most of R5 (anti-theft) |
| Keeps | the G quality bar (the "Premium bar" and the 24 benchmark gaps); H R1–R3 (clean Source-R rebuild, evolved styles, feature map); every QC gate; zero cost (F1) |

## I1. What changes
- **No sale edition until Yunus says so.** The following are parked indefinitely, not deleted: billing (H16), legal drafts (H17), licence and billing modules (G-T3, G-T4), the pre-sale licence checklist (G-T2), signing and notarization (H4, H4-Mac), and the sale-edition hardening (R-T12).
- **The strongest model wins every slot, chosen by measurement.** No model is swapped or dropped for licence reasons; customer-facing pricing doesn't constrain model choice.
  - Each model keeps its own licence. We download it at install with its notice; we never re-licence it.
  - **G-ALIGN changes meaning.** MMS is no longer a ship blocker. Keep whichever aligner measures more accurate on our Arabic set (MMS-300m vs the Apache-2.0 Arabic wav2vec2).
  - If MMS wins, ship it, and say plainly in THIRD-PARTY-NOTICES and the guide that its own terms are non-commercial.
- **No telemetry at all (D17 fully restored).** The R5.2 update-check misuse reporting and its email endpoint (R-T9 reporting part) are dropped. The update check only checks for updates.

## I2. Licence (executor ruling; Yunus may override)
- **Yunus (same day): «بس اهم حاجه كل الحقوق محفوظه لينا باسمنا».**
  - Every file, the About screen, the README, the guide and the LICENSE carry «© 2026 The Why Not AI (thewhynot.ai)».
  - The copyright is ours and never transferred. GPL is a permission we give; it is not a transfer of ownership.
  - The name, logo and brand stay «All rights reserved» under `TRADEMARKS.md`.
  - The literal phrase "All rights reserved" is NOT used on the code itself, because that would make it not open source.
  - If Yunus later wants the code visible but unusable without permission, the switch is to "source-available" (all rights reserved). That is his call.
- **Code:** GPL-3.0-or-later.
  - Anyone may use, study and change it, but a fork must stay open, so nobody can take it closed and sell it.
  - Because The Why Not AI owns all the copyright, it can still offer a separate paid licence later (dual licensing), which keeps "when I need to sell" open.
  - It is compatible with the full GPL FFmpeg build.
- **Contributions:** add a short CLA (or DCO plus a copyright-assignment line) before accepting any outside pull request. Without it, a future paid licence becomes impossible.
- **Name and logo stay ours:** WhyNot Cut, Kalam, Hush, Tidy, the thewhynot.ai logo and brand assets. A `TRADEMARKS.md` says forks must rename. This matches H22, where registration is in The Why Not AI's name.
- **File headers:** `SPDX-License-Identifier: GPL-3.0-or-later` plus `© 2026 The Why Not AI`. The About screen shows both.
- `whynot-cut/LICENSE` (now "All rights reserved") is replaced in Phase 4. THIRD-PARTY-NOTICES is unchanged.

## I3. Going public (a release-day step, Yunus's OK in chat on the day)
- The public repo is a **fresh repo built from a clean snapshot, with no history**. It is not the private repo flipped to public.
  - **Why:** the private history may hold client names, profiles, test media paths and old secrets.
- **Before publishing, every check must be clean:**
  - a secrets scan (gitleaks or trufflehog, free);
  - a client-data scan: no `D:\WhyNot Clients` paths, no client profiles, no real client footage or transcripts;
  - the Source-R identity scan (H R5.4, hashed list);
  - the evidence report stays outside the repo.
- The private repo stays the development home. Public releases go through the planned `dl.thewhynot.ai`.

## I4. What remains of H R5 (now: protecting the brand and the repo, not the code)
| Item | Status |
|---|---|
| R5.1 `security-watch.yml` (email on push, collaborator or visibility change) | **kept** |
| Branch rules | **become free** once a repo is public (GitHub Free protects public repos); applied on the public repo on release day |
| R5.2 update-check misuse reporting | **dropped** (I1, no telemetry) |
| R5.3 Google Alerts (H21) | kept, optional: it watches for brand misuse |
| R5.4 identity scan | kept, as a publish check |
| R5.5 weekly `gh search code` watch | **dropped** (copies are allowed now) |
| R5.6 takedown kit | reduced to a GPL-compliance and trademark notice template |

## I5. Unchanged
- Quality first. No review, test or gate is shortened.
- The Premium bar from G stays the bar: "the strongest and most complete editing plugin", now measured against the same competitors without a price tag.
- Customers (users) use their own Claude and Magnific accounts. H14 stays open.
- Zero cost unless Yunus approves.
