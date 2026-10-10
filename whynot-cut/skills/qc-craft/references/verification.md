# Verification: evidence before claims

Adapted from the *verification-before-completion* idea in obra/superpowers (MIT), applied to this pipeline.
Every example below happened in the first production run (C0238).

## Claim → required evidence (gathered in the same message as the claim)

| Claim | Not enough | Required evidence |
|---|---|---|
| "Audio cleaned" | filter chain ran | `dialogue-clean-report.json` speech-to-noise before/after, spectrograms viewed, cleaned file on A1/A2 in the built project |
| "Pauses removed, nothing lost" | pause list written | `cut-verification.json`: re-transcription of the tightened audio has 0 missing words |
| "AE project built" (extras only) | osascript / AfterFX.exe exit 0; DoScript printed `0` (AE always prints `0`) | `.aep` exists **and** `ae-build-result.json` status `AEP_CREATED` |
| "Graphics rendered" | aerender exit 0 | each `<EVENT>.mov` exists, probes 1080×1920 @24 with alpha (`qc`), **and** you viewed it on the verify sheet |
| "Graphics look right" / "on brand" | previews rendered; QC passed | viewed `verify_sheet.jpg`: every tile checked against `verify-checklist.md` |
| "Arabic is correct" | text present in JSON/SRT | viewed AE render or CoreText preview: letters joined, first word on the **right**. Fallback (non-CoreText) previews can't show this |
| "PSD is right" | `PSD_CREATED` | viewed `*_preview.png` tile: RTL order, logo without a white box, nothing overlapping |
| "Transcript is correct" | high Whisper confidence; your context corrections | the editor confirmed by ear → `transcript-verify` |
| "Fixed" | you changed the code/plan | the **original symptom** re-checked after the change (re-render + re-view, or re-run the failing command) |
| "Premiere project ready" | XML parses; `qc` ok; `ppro-build` printed PRPROJ_BUILT | `.prproj` saved this run **and** all `ppro-build-result.json` read-back checks true **and** you viewed `ppro-frames` output (Premiere's own render of its timeline) mid-animation |
| "Done" / "ready to send" | most stages ran | `qc` ok in this message, visual verification PASS newer than the renders, plan approved, **and** nothing in "Needs you" blocks that claim |

## Red flags: stop and verify
- You're about to write "done", "all set", "ready", "fixed", "looks good", "perfect", "should work now", or "probably fine".
- Your evidence is a status string, an exit code, or a subagent's report rather than an output you inspected.
- You verified before your last change and are reusing that result.
- You checked one tile, clip or PSD and are generalizing to the rest.
- The editor is waiting or excited, and verifying feels like it would slow you down.

## Rationalizations seen or expected, and the reality

| Thought | Reality |
|---|---|
| "The script returned success, so it worked." | In C0238 the PSD reported success with the headline word order reversed. |
| "QC passed, so it's ready." | QC can't see faces, glyphs or word order. Visual verification is its own gate. |
| "The previews looked fine earlier." | Earlier previews used a renderer that broke Arabic. Evidence must come from the current output. |
| "It's just a small tweak, no need to re-render and look." | The face-crop bug came from a one-line template change. |
| "I'll mention the caveats later." | The editor acts on your summary. Caveats go in "Not verified / Needs you", in the same message. |
| "Whisper's confidence is high, so the medical term is right." | "Hypertrophic" came out as "هايبر ترافيك" at p=0.66. Medical words are confirmed by ear. |
| "The editor said 'go ahead' last time." | Approval covers a specific plan. A changed plan needs new approval (the gate enforces this). |

## Recording
Premiere path: `reel ppro-frames` → view the frames (qc-reviewer fans out frame-inspectors) → the LEAD runs `reel verify --record --verdict pass|fail --sheet <frames sheet> --notes "…"`.
Non-Premiere path: `reel verify` builds `verify_sheet.jpg` → view → record.
The record is refused if the sheet is older than the newest render or PSD. A `fail` with clear notes is useful: fix, re-render, re-verify.
