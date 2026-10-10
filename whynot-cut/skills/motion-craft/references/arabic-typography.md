# Arabic / RTL Typography

- Store all text in **logical order** (as spoken). Never pre-reverse or pre-shape strings in SRT/JSON/JSX.
- After Effects: the build sets `composerEngine = UNIVERSAL_TYPE_ENGINE` and `direction = RIGHT_TO_LEFT`
  per text layer (AE 24+ API). Global pref **Preferences › Type › Text Engine: South Asian and Middle Eastern**
  is recommended; if text looks disconnected, set it and restart AE (the plugin never changes prefs itself).
- Photoshop: the PSD builder sets paragraph direction RTL + World-Ready composer per Arabic text layer via ActionManager (`NHPS.setRTL`); verified to render correctly in Photoshop 2026 (27.11).
- Premiere captions from SRT: Premiere's caption engine handles RTL; check mixed lines (Arabic + Latin term).
- Stills: rendered with macOS CoreText (PyObjC) or HarfBuzz + FreeType (every OS, from the client's font file) = full GSUB shaping + RTL base direction. The last-resort fallback is arabic-reshaper + python-bidi, which BREAKS fonts lacking presentation-form glyphs (Thmanyah has only 89) — never judge Arabic from fallback previews.
- Line breaking: max 2 lines, ≈18–32 chars/line; never split a Latin term, a number+unit, or "ال" + Latin term
  (e.g. "الـ Isotretinoin"). Balance lines (no orphan word).
- Latin terms keep LTR runs inside Arabic lines; term callouts with Latin text set `"latin": true` (LTR layer).
- Digits: keep the speaker's form; Western digits are fine with Thmanyah.
- Font: thmanyah serif display covers Arabic + Latin (Light 300 … Black 900). Roles in `typography-roles.json`.
