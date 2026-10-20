<!-- Verbatim copy of BACKLOG.md section BL-19, taken 2026-10-20. BACKLOG.md stays the source if they differ. -->
### BL-19 [Stage 2]: Root-normalised fingerprints, so a client move keeps its approvals (BL-14 Q1 option (a), deferred by the executor 2026-10-19)
- **Today (Gate 4, BL-14 ruling (c)):** a move or clone rewrites the hashed files (timeline-spec, words, pauses, motion-script, reels-plan, brand-tokens) to the new root. Their approvals and sign-offs become void, and NEEDS-YOU lists each one to approve again.
- **Later:** compute those fingerprints over a root-normalised form, so a move keeps every approval. Accept the legacy hash once, then re-seal. Touches plan.py, transcribe.py, cut_proposals.py, motion_plan.py (Adobe), reels.py and cli's transcript record.
- Risk: medium (approval integrity). Needs its own pre-mortem.
