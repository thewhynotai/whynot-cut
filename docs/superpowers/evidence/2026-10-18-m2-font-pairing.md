<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- © 2026 The Why Not AI (thewhynot.ai) -->

# Arabic + Latin font pairing (Addendum M M2-T4, Task 56): measured traits, score, latin_scale, the OFL table draft

| | |
|---|---|
| Date | 2026-10-18; fix round 1 (review 515ddc7) 2026-10-19; fix round 2 (review ca5f2cb) 2026-10-19 |
| Engine | `whynot-cut/engine/reel/lib/font_pairing.py` (traits, coverage gate, score, `latin_scale`, `pick`, table builder, specimen sheet) |
| Table | `whynot-cut/config/defaults/font-pairings.json` (draft: classes are the curator's, every number is measured) |
| Tests | `whynot-cut/tests/test_font_pairing.py` (tiny fontTools-made fonts with known boxes, plus the committed OFL fonts) |
| Fonts measured | the repo's `guide-ar/fonts` (5 families, 12 files) and, with the owner's OK, 19 families from the pinned font source of `setup/components.json` (commit `bd8f81dd`), parsed only, never copied into the repo |
| Not in this task | wiring: the looks track hooks `looks_type.font_chain` and wnc-queue adds `typography.pairing` (patches, not applied); AE/MOGRT use (Phase 6) |

## Fix round 2 (review ca5f2cb), what changed
- **pick() fixes the faces the caption chain draws first** (looks_type.font_chain), and never swaps them:
  - Arabic: the role face when it draws Arabic, else the client's Arabic body face;
  - Latin: the role face when it draws Latin;
  - both fixed (a face drawing both scripts, or a Latin caption face plus an Arabic body face): those faces are scored
    together, else no pair;
  - one fixed: the other script is measured against it.

  A stored `table` pair is used only when it names exactly the fixed faces (review P1-1).
- **The ٫ ٬ separators** are required only for clients whose captions use Arabic-Indic digits (style.json
  `captions.digits`; Western is the default and never draws them).
  - Each row records `arabic_indic_missing`.
  - Tajawal and Aref Ruqaa are back for Western-digit clients: 153 rows (96 auto, 57 shown), against 143 after round 1.
  - Handwritten has pairs again; Tajawal is an Arabic face again (no longer a Latin-only partner).
- **A required native library that fails to load** (freetype-py raises RuntimeError) is a named refusal, like a missing
  package.
- **The looks hook (patches, not in this file):** a pair's Latin face keeps `latin_scale` when it is also the role
  face. The golden stills of phrase-boxed and phrase-highlight change accordingly; before/after sheets go with the
  patch.

## Fix round 1 (review 515ddc7), what changed
- **Arabic letter body (P1-1).**
  - **Before:** 515ddc7 kept every contour touching the largest contour's box. That kept a dot dipping into the bowl's
    box (IBM Plex Sans Arabic SemiBold ن: +13.8 %; Alexandria Bold ن: +5.4 %) and dropped a tooth touching only a
    middle stroke (Readex Pro 400 س: −11 %). 33 rows missed the 3 % height target.
  - **Now:** the body is read from the dotless forms (ٮ ں ى, and س), so no dot can count. Without a dotless form, ب
    and ي use their full top (their dots sit below), and only ن goes through contour classes: contours joined
    transitively to the largest one, minus small marks (< 15 % of its area) centred outside its height.
  - **Check:** against an independent FreeType ink measure (below) every face agrees within 0.24 %, and no unclamped
    row misses 3 %.
- **pick() (P1-2).** The role's face comes from `font_roles.resolve`. When it is the client's own face, the other
  script is measured against that very face: first the client's own families, then the installed table faces.
  - The best result >= 50 wins; otherwise there is no pair, and today's chain is kept.
  - A superfamily is accepted only from the role face's own family.
  - A coverage miss on the client's face is a finding, never a switch to another family.
  - Another family's table row is never handed over.
- **Role weights (P2-1):** typography.json roles, brand.json `font_roles_fallback.weights`, then the house default; table
  rows follow that weight.
- **Coverage gate (P2-2):** the Arabic side also needs tatweel ـ and the harakat U+064B–0652. Round 1 also required
  ٫ ٬ for everyone; round 2 made that digit-aware (above).
- **Missing modules (P2-3):** a missing fontTools, uharfbuzz, freetype-py or numpy is a `FontProbeError` naming it.
  `pick()` returns no pair with that finding.
- **P3:**
  - the pairing entry is checked (source, `latin_scale` 0.5–2.0, classes) and every rejection is a finding;
  - `licence()` refuses a truncated font instead of raising;
  - the specimen draws the Arabic sample as one right-to-left line, with guides from a fresh measure;
  - the evidence lists raw and LF OFL hashes.

## How a pair is measured and scored
- **Traits** are read from the font file, never from its name, at the role's weight: a static family uses its file of
  the nearest `usWeightClass` (ties to the heavier; a one-file family serves every weight and is judged by its ink); a
  variable font is instanced at the weight with the fontTools instancer (other axes at their defaults).
  - Latin x-height: the ink top of "x" per em, else OS/2 `sxHeight`.
  - Arabic letter body: the median tooth height of the isolated «س ب ن ي», read from their dotless forms (see above).
  - Stroke contrast: 1 - thin/thick from scanlines through a FreeType raster ("o" sides vs top and bottom; the alef
    stem vs the base stroke of the dotless beh ٮ).
  - Ink density (visual weight): ink of a fixed string / (its advance x the script's body height).
  - Width and rhythm: advance per letter and the word space, both per body height.
  - Terminal shape: the share of straight segments in a fixed glyph set (stands in for the class when a face is not
    curated, at most 30 of the 40 class points).
- **Coverage gate**:
  - **Arabic:** letters with ڤ, ٪ ، ؛ ؟, Arabic-Indic digits, tatweel, harakat, and the lam-alef ligature; ٫ ٬ only for Arabic-Indic caption digits.
  - **Latin:** A-Z a-z 0-9 % & ®.
  - **lam-alef** passes as one glyph or as a lam and an alef that both differ from their plain joining forms (Amiri,
    Noto Naskh Arabic and Noto Sans Arabic build it from two contextual glyphs).
- **Score 0-100** = class 40 + weight 20 + height 15 + contrast 15 + width/rhythm 10. A superfamily earns the full class
  part. Bands: >= 70 automatic, 50-69 shown with `explain()` as the reason, < 50 never used. A pair whose
  `latin_scale` must be clamped to 0.7-1.4 and still misses the body by more than 3 % is at most "shown".
- **latin_scale** = 1.00 x Arabic body / Latin x-height (target ratio 1.00, executor ruling Q56-4).
- **Licence proof per face:** nameID 13 and 14, the sha256 of the family's OFL.txt with LF line endings, and the font
  file's sha256. A face whose name table does not say OFL, or whose folder has no OFL text, makes the builder refuse
  the whole build before anything is written.
- **Which pairs:** every superfamily, and every Arabic family with a Latin-only family whose classes earn at least 20
  class points. Rows are grouped by the weights they serve (400 small, 500 body, 700 caption and term, 900 headline).
- **Rebuild:** `python -m lib.font_pairing build --fonts <folder> [--fonts <folder> ...] --write` from
  `whynot-cut/engine/reel`.
  - With both folders it gives the same bytes twice.
  - Without the downloaded folder, its families and rows are kept as measured, so the repo-only rebuild in the tests
    gives the committed bytes (`test_rebuilding_from_the_repo_fonts_is_byte_identical`).

## Results
rows 153: auto 96, shown 57; kinds: pair 124, superfamily 29

### Arabic body against an independent measure

The module reads the body from the dotless forms (ٮ ں ى, and س) through HarfBuzz and fontTools pens. The second method shares none of that: FreeType rasterises the cmap glyphs of س ب ي ں at one pixel per font unit, and the first inked row is the ink top; a variable font is set through FreeType's own design coordinates. (515ddc7's evidence compared `latin_scale` with the module's own body, so it could not fail; that check is gone.)

| Arabic face | instance | table arabic_body | independent (FreeType ink) | off by |
|---|---|---|---|---|
| Alexandria-Black.ttf | static | 0.537 | 0.5370 | +0.00 % |
| Alexandria-Bold.ttf | static | 0.515 | 0.5150 | +0.00 % |
| Alexandria-SemiBold.ttf | static | 0.505 | 0.5050 | +0.00 % |
| Amiri-Bold.ttf | static | 0.4046 | 0.4055 | -0.22 % |
| Amiri-Regular.ttf | static | 0.3887 | 0.3890 | -0.08 % |
| ArefRuqaa-Bold.ttf | static | 0.5385 | 0.5385 | +0.00 % |
| ArefRuqaa-Regular.ttf | static | 0.5321 | 0.5325 | -0.08 % |
| Cairo[slnt,wght].ttf | 400 | 0.5 | 0.5000 | +0.00 % |
| Cairo[slnt,wght].ttf | 500 | 0.5 | 0.5010 | -0.20 % |
| Cairo[slnt,wght].ttf | 700 | 0.502 | 0.5020 | +0.00 % |
| Cairo[slnt,wght].ttf | 900 | 0.503 | 0.5040 | -0.20 % |
| IBMPlexSansArabic-Regular.ttf | static | 0.374 | 0.3740 | +0.00 % |
| IBMPlexSansArabic-SemiBold.ttf | static | 0.401 | 0.4010 | +0.00 % |
| Lalezar-Regular.ttf | static | 0.3395 | 0.3395 | +0.00 % |
| NotoNaskhArabic[wght].ttf | 400 | 0.34 | 0.3400 | +0.00 % |
| NotoNaskhArabic[wght].ttf | 500 | 0.3545 | 0.3550 | -0.14 % |
| NotoNaskhArabic[wght].ttf | 700 | 0.384 | 0.3840 | +0.00 % |
| NotoSansArabic[wdth,wght].ttf | 400 | 0.403 | 0.4030 | +0.00 % |
| NotoSansArabic[wdth,wght].ttf | 500 | 0.419 | 0.4200 | -0.24 % |
| NotoSansArabic[wdth,wght].ttf | 700 | 0.4585 | 0.4585 | +0.00 % |
| NotoSansArabic[wdth,wght].ttf | 900 | 0.4885 | 0.4885 | +0.00 % |
| Rakkas-Regular.ttf | static | 0.438 | 0.4380 | +0.00 % |
| ReadexPro[HEXP,wght].ttf | 400 | 0.438 | 0.4380 | +0.00 % |
| ReadexPro[HEXP,wght].ttf | 500 | 0.4485 | 0.4490 | -0.11 % |
| ReadexPro[HEXP,wght].ttf | 700 | 0.4695 | 0.4695 | +0.00 % |
| Tajawal-Black.ttf (no ں: module and independent both on «س ب ي») | static | 0.455 | 0.4550 | +0.00 % |
| Tajawal-Bold.ttf (no ں: module and independent both on «س ب ي») | static | 0.444 | 0.4440 | +0.00 % |
| Tajawal-Medium.ttf (no ں: module and independent both on «س ب ي») | static | 0.434 | 0.4340 | +0.00 % |
| Tajawal-Regular.ttf (no ں: module and independent both on «س ب ي») | static | 0.428 | 0.4280 | +0.00 % |

Largest difference: 0.24 % over 29 Arabic faces.
3 % check against the independent body: 153 rows; unclamped rows outside 3 %: 0 []
Readex Pro 400 «س»: module body top 0.4380, contour classes 0.4380, glyph control box 0.4380 (515ddc7 measured the bowl's horn, 0.342).

### Best pair per Arabic family and weight

| Arabic family (class) | weights | best Latin partner (class) | score | band | latin_scale |
|---|---|---|---|---|---|
| Lalezar (display) | 400, 500, 700, 900 | Lalezar (display) (superfamily) | 76.05 | auto | 0.738 |
| Rakkas (display) | 400, 500, 700, 900 | Syne (display) | 86.04 | auto | 0.8813 |
| Amiri (formal) | 400, 500 | Amiri (formal) (superfamily) | 85.34 | auto | 0.9255 |
| Amiri (formal) | 700 | Amiri (formal) (superfamily) | 81.78 | auto | 0.9344 |
| Noto Naskh Arabic (formal) | 400 | Markazi Text (formal) | 75.75 | auto | 0.9333 |
| Noto Naskh Arabic (formal) | 500 | Markazi Text (formal) | 77.25 | auto | 0.9628 |
| Noto Naskh Arabic (formal) | 700 | Markazi Text (formal) | 77.17 | auto | 1.0186 |
| Alexandria (geometric) | 500 | Alexandria (geometric) (superfamily) | 94.57 | auto | 0.9387 |
| Alexandria (geometric) | 700 | Alexandria (geometric) (superfamily) | 94.42 | auto | 0.9519 |
| Alexandria (geometric) | 900 | Montserrat (geometric) | 93.5 | auto | 0.9817 |
| Cairo (geometric) | 400 | Cairo (geometric) (superfamily) | 95.98 | auto | 1.0 |
| Cairo (geometric) | 500 | Cairo (geometric) (superfamily) | 96.24 | auto | 1.0 |
| Cairo (geometric) | 700 | Cairo (geometric) (superfamily) | 94.99 | auto | 1.0 |
| Cairo (geometric) | 900 | Cairo (geometric) (superfamily) | 94.2 | auto | 1.0 |
| Readex Pro (geometric) | 400 | Readex Pro (geometric) (superfamily) | 87.26 | auto | 0.8343 |
| Readex Pro (geometric) | 500 | Readex Pro (geometric) (superfamily) | 88.13 | auto | 0.851 |
| Readex Pro (geometric) | 700 | Readex Pro (geometric) (superfamily) | 89.23 | auto | 0.8842 |
| Tajawal (geometric) | 400 | Montserrat (geometric) | 87.7 | auto | 0.8152 |
| Tajawal (geometric) | 500 | Montserrat (geometric) | 88.3 | auto | 0.8189 |
| Tajawal (geometric) | 700 | Tajawal (geometric) (superfamily) | 88.32 | auto | 0.978 |
| Tajawal (geometric) | 900 | Tajawal (geometric) (superfamily) | 88.23 | auto | 1.0022 |
| Aref Ruqaa (handwritten) | 400, 500 | Aref Ruqaa (handwritten) (superfamily) | 81.44 | auto | 1.1468 |
| Aref Ruqaa (handwritten) | 700 | Aref Ruqaa (handwritten) (superfamily) | 77.47 | auto | 1.0967 |
| IBM Plex Sans Arabic (humanist) | 400 | Noto Sans (humanist) | 82.34 | auto | 0.7 |
| IBM Plex Sans Arabic (humanist) | 500, 700 | IBM Plex Sans Arabic (humanist) (superfamily) | 85.52 | auto | 0.7682 |
| Noto Sans Arabic (humanist) | 400 | Inter (humanist) | 81.13 | auto | 0.7382 |
| Noto Sans Arabic (humanist) | 500 | Noto Sans Arabic (humanist) (superfamily) | 80.77 | auto | 0.7774 |
| Noto Sans Arabic (humanist) | 700 | Noto Sans Arabic (humanist) (superfamily) | 83.02 | auto | 0.8397 |
| Noto Sans Arabic (humanist) | 900 | Noto Sans (humanist) | 82.32 | auto | 0.8834 |

Clamped (the heights stay apart, so at most shown):

| pair | weights | score | band | latin_scale | scaled x-height / body |
|---|---|---|---|---|---|
| Lalezar + Anton | 400, 500, 700, 900 | 71.78 | shown | 0.7 | 1.511 |
| Rakkas + Anton | 400, 500, 700, 900 | 65.68 | shown | 0.7 | 1.171 |
| Lalezar + Bebas Neue | 400, 500, 700, 900 | 64.68 | shown | 0.7 | 1.443 |
| Rakkas + Bebas Neue | 400, 500, 700, 900 | 63.19 | shown | 0.7 | 1.119 |
| Noto Naskh Arabic + Noto Serif | 500 | 71.54 | shown | 0.7 | 1.058 |
| Noto Naskh Arabic + Noto Serif | 400 | 70.42 | shown | 0.7 | 1.104 |
| Noto Naskh Arabic + Noto Naskh Arabic | 500 | 69.39 | shown | 0.7 | 1.058 |
| Noto Naskh Arabic + Noto Naskh Arabic | 400 | 69.25 | shown | 0.7 | 1.104 |
| Aref Ruqaa + Dancing Script | 400 | 67.88 | shown | 1.4 | 0.874 |
| Aref Ruqaa + Dancing Script | 500 | 67.64 | shown | 1.4 | 0.874 |
| Aref Ruqaa + Dancing Script | 700 | 61.02 | shown | 1.4 | 0.863 |

Refused (< 50, kept in the table, never used):

- none

Candidates (no row; never picked): 

Findings: IBM Plex Mono: not used (monospace: not a caption face); Markazi Text: Arabic coverage gate: MarkaziText[wght].ttf cannot draw ٪; Aref Ruqaa: cannot draw ٫ ٬ (ArefRuqaa-Regular.ttf): its rows are not used for clients with Arabic-Indic digits; Tajawal: cannot draw ٫ ٬ (Tajawal-Regular.ttf): its rows are not used for clients with Arabic-Indic digits

### Downloaded set (pinned font source of setup/components.json)

54 files (35 fonts, 19 OFL.txt); 54 of 54 re-hashed equal to the manifest; 35 font files in the table carry the manifest's sha256 (0 differ). For OFL.txt the table stores the sha256 of the text with LF line endings (`ofl_sha256`); six of these files have CRLF endings, so their raw sha256 differs from the stored one. Both are listed.

| folder | file | bytes | sha256 (raw, the manifest's) | OFL.txt sha256 with LF (the table's) |
|---|---|---|---|---|
| cairo | OFL.txt | 4473 | `a4554e1799d42e1405924b61eb0e0722ae1623b1f1f07f995348f96c496362a9` | `ce39edb04b690f144cd40dc59a1be26dcb089e539c8118289d1081cde4449d6f` (CRLF file) |
| tajawal | OFL.txt | 4464 | `9b584984f9db0ee30347391a76eff9c0a6b03dc450c3c6afe3757a2cb3a4db87` | `184de01d11c016e7d7bb2f2f81db9a036171acb5374f006e74a36828faca1f12` (CRLF file) |
| tajawal | Tajawal-Black.ttf | 59028 | `da582a579d3200869535dc994d2349608a8582042f8776b3679b157015db287c` |  |
| tajawal | Tajawal-Bold.ttf | 59988 | `0342ab6b74b6bd1b4b5bf7beda45a9734a2b3147a31e8a3a45b6a3417a52d9d7` |  |
| tajawal | Tajawal-ExtraBold.ttf | 59648 | `3d1298b747c22579f9e1bdeb0d4165064cb17f7e66145e2f43f9deb12ad7a2cf` |  |
| tajawal | Tajawal-ExtraLight.ttf | 55784 | `a12ffbfaaec30ab8142edc60fa4727b104a90eb54c6a200a76988a1ec2ec11dc` |  |
| tajawal | Tajawal-Light.ttf | 61864 | `ab26ed3e0c5af2c71b469b5780decff8088d290ab91aa29b07321580136e813a` |  |
| tajawal | Tajawal-Medium.ttf | 62280 | `1ff8bd943a261c9dd7906bdb1993cab87b6d925a7fb5f848cdb51ed301531090` |  |
| tajawal | Tajawal-Regular.ttf | 60364 | `6882892da3e03527d5db2bbab3b48bde6ef2e878a43f522d1a4eebda90010a19` |  |
| readexpro | OFL.txt | 4444 | `b41267a3903a45955f77b44596e080480c577fb7221df59672d0bc8cd8cd4b6f` | `b41267a3903a45955f77b44596e080480c577fb7221df59672d0bc8cd8cd4b6f` |
| notosansarabic | OFL.txt | 4382 | `07fc70bfeb985cc1a87a8587d0a0c80bab11c86c9dc3fd95b6f0cb332f983e96` | `07fc70bfeb985cc1a87a8587d0a0c80bab11c86c9dc3fd95b6f0cb332f983e96` |
| notosans | OFL.txt | 4396 | `cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a` | `cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a` |
| notonaskharabic | OFL.txt | 4382 | `a7a5a25eb188bf1cd96982030d53e23c33485c69b1044a562254226857ee13af` | `a7a5a25eb188bf1cd96982030d53e23c33485c69b1044a562254226857ee13af` |
| amiri | Amiri-Bold.ttf | 413480 | `cfccb794268e7d573d857e6d6a67f89cf8a053e8ffd85dfa0c8ec1bb36fc4827` |  |
| amiri | Amiri-Regular.ttf | 431116 | `ab391c4147d054c48976e98322ad0eefe1427aa0e0502a12a4c75d80a70cfcd7` |  |
| amiri | OFL.txt | 4389 | `72de68e5954f4fdd24702292ef5a32f003ca960ec9330dc86e5eefb5dffb9b22` | `72de68e5954f4fdd24702292ef5a32f003ca960ec9330dc86e5eefb5dffb9b22` |
| markazitext | OFL.txt | 4485 | `6e7f259edf178c70b2ee36acfcc934b76d1cd56bb58d2c8f2ab8b5dded8bd430` | `3dbd57839ffb6ca4f9b274de6ddfae5e676778f19eeb6469a2dd4da1a62b850b` (CRLF file) |
| arefruqaa | ArefRuqaa-Bold.ttf | 123852 | `247071015b7eefd63f94d6e47949c5d10294ed31bd432f809ba9a219d93f91bb` |  |
| arefruqaa | ArefRuqaa-Regular.ttf | 110696 | `ceb786d83ba92f35e96efcd8623c2858d288e0c543c8761ba35b1020989464f9` |  |
| arefruqaa | OFL.txt | 4464 | `41ac14451a624c69490e24b9aaaaa1f65dc9dc17c3f6f38172fc43d5ba654a1b` | `41ac14451a624c69490e24b9aaaaa1f65dc9dc17c3f6f38172fc43d5ba654a1b` |
| lalezar | Lalezar-Regular.ttf | 290016 | `7b80807bc831f141de0f7dcf6816412bf0c548968d548c5156ca388733390ea9` |  |
| lalezar | OFL.txt | 4383 | `327bac41d89cf9f32e0efe353228018e1661cff458a5d4905714958514df7bd5` | `327bac41d89cf9f32e0efe353228018e1661cff458a5d4905714958514df7bd5` |
| rakkas | OFL.txt | 4423 | `5c36e7ec460b285185ea23847aa1f508708d9ce15d5c055279defd022972f836` | `f88ba31111587584657d69fe6d7fa501dd9b95762ac0c3120f3f98520c524d46` (CRLF file) |
| rakkas | Rakkas-Regular.ttf | 146824 | `54278882e4774c14d50c3b555f127d0fe586366d5b787316ebbcbd8108829e60` |  |
| ibmplexsans | OFL.txt | 4456 | `7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da` | `37784b44044a4ffd9256702b7c0982c37e5c8887ba90c6dca0479aea93dc898d` (CRLF file) |
| poppins | OFL.txt | 4385 | `6be04893d770899a015649c7aa3b582f871b272f8747a92b78b17c3e5c8b2573` | `6be04893d770899a015649c7aa3b582f871b272f8747a92b78b17c3e5c8b2573` |
| poppins | Poppins-Black.ttf | 153440 | `d82aaaf98a9283f9a8edd24e51173337d8eaf09e25cd3d98831f8ec8461748a1` |  |
| poppins | Poppins-Bold.ttf | 155996 | `983676516167748b74de6f4771fb384c664fd913acb8b471122ecacf5da5ea6c` |  |
| poppins | Poppins-ExtraBold.ttf | 154836 | `f2ab17c1a63a0ecc12c2461848fc8a469395e3cd2d641803e889c643d9f958e1` |  |
| poppins | Poppins-ExtraLight.ttf | 163568 | `55c03314cc754e26f741f97890e5e9cbe3b3278fe3abcecfecafd60111b2643d` |  |
| poppins | Poppins-Light.ttf | 161936 | `650ba57fa99d12ec40c31ccfb680be656be4497fbe14164617d67e32ffe9cd46` |  |
| poppins | Poppins-Medium.ttf | 158576 | `90373e7d838d32468438fc3e152dca0bdb12edcab99ea639f158790b1ba1fd05` |  |
| poppins | Poppins-Regular.ttf | 160316 | `7e65201e9b79159e2300267cc885e16c8dcef2424cdfa09a29bfb0980a94a7ba` |  |
| poppins | Poppins-SemiBold.ttf | 157312 | `d3bf1bdaf0550e83da9ac0b1d1d9fe6db086835a83aa28578e609a394b9a0286` |  |
| poppins | Poppins-Thin.ttf | 163672 | `6d8e5d9d29140cc93e321745fa1243c67889e6bc3639ec34db64f3da7a496352` |  |
| montserrat | OFL.txt | 4400 | `8b7141c03fa4f8d44e6345d5d4931709290f0f67875e452e95ac1fd3a027802e` | `8b7141c03fa4f8d44e6345d5d4931709290f0f67875e452e95ac1fd3a027802e` |
| notoserif | OFL.txt | 4396 | `cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a` | `cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a` |
| lora | OFL.txt | 4423 | `1d9a970809ac804b582a6ce7f0ebc4e7fefcbfd7ff6299cad35ee656a21be716` | `1d9a970809ac804b582a6ce7f0ebc4e7fefcbfd7ff6299cad35ee656a21be716` |
| dancingscript | OFL.txt | 4443 | `6f090277c00af96651ce6dbcc38ff1591047a3bffef486e80b6a32e8276a8201` | `6f090277c00af96651ce6dbcc38ff1591047a3bffef486e80b6a32e8276a8201` |
| anton | Anton-Regular.ttf | 170812 | `a4ba3a92350ebb031da0cb47630ac49eb265082ca1bc0450442f4a83ab947cab` |  |
| anton | OFL.txt | 4484 | `ee67e6ee22790b7929f1a3769ca2801d565c64b5a9096942c1adf5596de9c9e4` | `eee1d24ff8f553eb732237c7dd9b945a78313ed49ad6de02872a47277741b44a` (CRLF file) |
| bebasneue | BebasNeue-Regular.ttf | 61400 | `08e4623805102d819f58601e46e345648846075e363b2ceb23313c2d1c83ec73` |  |
| bebasneue | OFL.txt | 4337 | `72082f6cb4d04be2ecf7cc7d9e1e7d73787f0af8a5a278a47cade70c16b78341` | `72082f6cb4d04be2ecf7cc7d9e1e7d73787f0af8a5a278a47cade70c16b78341` |
| cairo | Cairo[slnt,wght].ttf | 599548 | `667c987182391c91f4e57a2f455b1794fb5e3ee6ca4ef3383e86bb690fa9c964` |  |
| readexpro | ReadexPro[HEXP,wght].ttf | 278544 | `268bba7e1e8f3b14d798b3fb0e40ebaa3fc39308c9ac0020e2faf6df181cc30e` |  |
| notosansarabic | NotoSansArabic[wdth,wght].ttf | 844676 | `63111b5b2e074dd48cc67692e0a2726d86ee94c1c37fe8598257b7b4e87e869e` |  |
| notosans | NotoSans[wdth,wght].ttf | 2049096 | `bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d` |  |
| notonaskharabic | NotoNaskhArabic[wght].ttf | 307592 | `67b5a525a661b607971fbd3f96a81b89d3a768e74534fca84f18ac97e6fab72f` |  |
| markazitext | MarkaziText[wght].ttf | 296896 | `424b7331681160ff2a4b209bfc356ea9564d429a7daea43ee4dc28de8ff4f9fe` |  |
| ibmplexsans | IBMPlexSans[wdth,wght].ttf | 537244 | `3b031aa4216174205bd8471f88a49b91f093169e9e87bd5262242bc5967fe2e3` |  |
| montserrat | Montserrat[wght].ttf | 744936 | `0f7b311b2f3279e4eef9b2f968bcdbab6e28f4daeb1f049f4f278a902bcd82f7` |  |
| notoserif | NotoSerif[wdth,wght].ttf | 1887192 | `4d8e6761424656867019081a1a01336f3cb086982682698714054fc33f782713` |  |
| lora | Lora[wght].ttf | 212196 | `822a6621ccbe8d97d20ac88c1c41f5615c9c2c202eaa75f272cd452aac6475a7` |  |
| dancingscript | DancingScript[wght].ttf | 133636 | `21808625578fe8d8cd10cb684be546dca077b27cd03a53a2f1ec11dc743c924c` |  |

| repo family | file | sha256 |
|---|---|---|
| Alexandria | Alexandria-SemiBold.ttf | `d074f67e30a0072993e3e4c23e3c71ddbb3d9f1f0825b0ae76b44fba5632c74b` |
| Alexandria | Alexandria-Bold.ttf | `542966745b840827bf71f7f59ba2fd86e82c2c969c279d0c23f69e811cb450ab` |
| Alexandria | Alexandria-ExtraBold.ttf | `b10ea6fdacb2fe0945480c2bd36c9b4f68961a0a9ac9b139c6b065ac53d3e595` |
| Alexandria | Alexandria-Black.ttf | `b19a04b7fac3a7de61fe8d805dbd8f4161184f9b5382164a215fb17b97ab91dc` |
| Alexandria | OFL.txt (LF line endings) | `f26bcd4d98e9f5b035f52df3760c9fa3daa1ae7d253f1453c7435e9f8241c2ed` |
| IBM Plex Mono | IBMPlexMono-Regular.ttf | `6a3412f058c7d8dfd9170c41e85ade48e5156ecb89356110ca57a0a27734af46` |
| IBM Plex Mono | OFL.txt (LF line endings) | `37784b44044a4ffd9256702b7c0982c37e5c8887ba90c6dca0479aea93dc898d` |
| IBM Plex Sans Arabic | IBMPlexSansArabic-Light.ttf | `0af9d1effbb36ff74d13c64f752c771ecb9162a451cf151c5425f4d00d4daa7c` |
| IBM Plex Sans Arabic | IBMPlexSansArabic-Regular.ttf | `6f611412270a132bbac838da9259d4c68569b4175f3b3b8fa3fa36a30b56dab9` |
| IBM Plex Sans Arabic | IBMPlexSansArabic-SemiBold.ttf | `597bd5502e5997be4414e4c9c88834b30ff3784250c84f20bce2b20e53ebd467` |
| IBM Plex Sans Arabic | OFL.txt (LF line endings) | `37784b44044a4ffd9256702b7c0982c37e5c8887ba90c6dca0479aea93dc898d` |
| Inter | Inter-Regular.ttf | `40d692fce188e4471e2b3cba937be967878f631ad3ebbbdcd587687c7ebe0c82` |
| Inter | Inter-SemiBold.ttf | `78a843fade9d4612a5567302fb595b56976eb5fcebf4fea5a5912d638bafcde3` |
| Inter | Inter-Bold.ttf | `288316099b1e0a47a4716d159098005eef7c0066921f34e3200393dbdb01947f` |
| Inter | OFL.txt (LF line endings) | `262481e844521b326f5ecd053e59b98c8b2da78c8ee1bdbb6e8174305e54935a` |
| Syne | Syne-Bold.ttf | `3d52dbaf7cb6fe7d96f038f0fcce8d51dc4c0b76b98487091e67174ed3742e43` |
| Syne | OFL.txt (LF line endings) | `cc43cdce6f91c57989af8459341c276655e34224e954fa69c2ad700831a742d8` |

## How it is held
- **`tests/test_font_pairing.py`: 102 tests.**
  - Traits on made fonts with known boxes: dots, a dot dipping into the tooth box, a tooth touching only a middle
    stroke, dotless forms, split base+dot clusters, a variable font, a collection face, 20 000 glyphs, an Arabic path
    with spaces.
  - The repo noon dots (IBM Plex Sans Arabic SemiBold, Alexandria Bold).
  - The repo Arabic bodies and table rows against the independent FreeType ink measure.
  - The coverage gate, including tatweel, harakat, contextual lam-alef and the digit-aware ٫ ٬.
  - `pick()` on the faces the chain draws: a stored table pair naming another Arabic, a Latin caption face with an Arabic body face (review ca5f2cb P1-1).
  - Score parts and bands, `latin_scale` and the 3 % bound.
  - `pick()`: the reviewer's cases A, B, B2 and H, the Latin role face, role weights from typography.json roles and
    brand.json, a validated pairing entry, missing modules.
  - The licence refusals (also a truncated name table), the specimen geometry, and the table itself: structure, a
    wrong band, italic files, OFL shas, sorted rows, byte-identical rebuild.
- **Mutation (fix round 1 only; fix round 2 is LIGHT, no mutation run):** 84 mutants (the round-0 47, the reviewer's
  24, 20 fix-round behaviours): the first run killed 79, one test per survivor was added, the second run killed all 84.
  The review of ca5f2cb found 7 further code mutants that survive; they are listed as known limits in the close-out.
- **Readex Pro 400 «س»** (not in the suite: the downloaded fonts never enter the repo): measured in the independent
  check above. The suite pins the same geometry with a made font, a tooth that touches only a middle stroke.

## What is not measured, and why
- **Arabic-Indic digit clients:** Tajawal and Aref Ruqaa lack ٫ ٬, so their 27 rows are left out for such clients
  (and so is the handwritten class, until a handwritten face with ٫ ٬ is added).
- **Markazi Text** fails the Arabic gate (no ٪): it serves only as a Latin partner of the formal Arabic families.
- **Tajawal** has no ں: its noon body comes from contour classes (checked letter by letter in round 2's review).
- **IBM Plex Mono** is left out (monospace, not a caption face).
- **Weights out of reach** get no row (IBM Plex Sans Arabic has no face within 150 of 900 in the repo; Noto Naskh Arabic
  stops at 700).
- **Variable instances in rendering:** the table measures variable fonts at the row's weight. Today's caption engines
  draw a file at its default instance, so the looks hook uses only static faces from the table until the renderer
  sets the instance (written in the patch README).

## Not verified
- **Specimen sheet verdict (H29):** the sheets were re-drawn after fix round 2, outside the repo in Builder A's work
  folder `lane4\work\task56-fu2\specimen\`. They show the Arabic as one right-to-left line, with guides measured afresh.
  The brand-systems-designer verdict and Yunus's approval (HM-4) are pending. The classes in the table are the
  curator's draft until then.
- **Rendered frames:** pairing on Premiere/AE frames is M2-T5 (Phase 6). Only our own stills were inspected.
- **Hook behaviour live:** the looks and wnc-queue patches are tested on a scratch copy and are not applied here.
- **A real Mac run:** the Windows/macOS file-name branches are tested by patching `sys.platform`; no macOS machine ran
  the module.
