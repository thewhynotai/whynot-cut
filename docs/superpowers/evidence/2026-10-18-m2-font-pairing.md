<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- © 2026 The Why Not AI (thewhynot.ai) -->

# Arabic + Latin font pairing (Addendum M M2-T4, Task 56): measured traits, score, latin_scale, the OFL table draft

| | |
|---|---|
| Date | 2026-10-18 |
| Engine | `whynot-cut/engine/reel/lib/font_pairing.py` (traits, coverage gate, score, `latin_scale`, `pick`, table builder, specimen sheet) |
| Table | `whynot-cut/config/defaults/font-pairings.json` (draft: classes are the curator's, every number is measured) |
| Tests | `whynot-cut/tests/test_font_pairing.py` (tiny fontTools-made fonts with known boxes, plus the committed OFL fonts) |
| Fonts measured | the repo's `guide-ar/fonts` (5 families, 12 files) and, with the owner's OK, 19 families from the pinned font source of `setup/components.json` (commit `bd8f81dd`), parsed only, never copied into the repo |
| Not in this task | wiring: the looks track hooks `looks_type.font_chain` and wnc-queue adds `typography.pairing` (patches, not applied); AE/MOGRT use (Phase 6) |

## How a pair is measured and scored
- **Traits** are read from the font file, never from its name, at the role's weight: a static family uses its file of
  the nearest `usWeightClass` (ties to the heavier; a one-file family serves every weight and is judged by its ink); a
  variable font is instanced at the weight with the fontTools instancer (other axes at their defaults).
  - Latin x-height: the ink top of "x" per em, else OS/2 `sxHeight`.
  - Arabic letter body: the median tooth height of the isolated «س ب ن ي». Only the letter's body counts: contours
    that touch the largest contour's box. Dots and marks floating free of it are dropped, also when a font draws the
    dot as a separate glyph (Noto Sans/Naskh Arabic, Aref Ruqaa).
  - Stroke contrast: 1 - thin/thick from scanlines through a FreeType raster ("o" sides vs top and bottom; the alef
    stem vs the base stroke of ب).
  - Ink density (visual weight): ink of a fixed string / (its advance x the script's body height).
  - Width and rhythm: advance per letter and the word space, both per body height.
  - Terminal shape: the share of straight segments in a fixed glyph set (stands in for the class when a face is not
    curated, at most 30 of the 40 class points).
- **Coverage gate**: Arabic letters with ڤ, ٪ ، ؛ ؟, Arabic-Indic digits and the lam-alef ligature; Latin A-Z a-z 0-9
  % & ®. lam-alef passes as one glyph or as a lam and an alef that both differ from their plain joining forms: four of
  the spec's candidates (Amiri, Aref Ruqaa, Noto Naskh Arabic, Noto Sans Arabic) build it from two contextual glyphs,
  and a one-glyph rule would have refused them.
- **Score 0-100** = class 40 + weight 20 + height 15 + contrast 15 + width/rhythm 10. A superfamily (one family that
  passes both gates) earns the full class part. Bands: >= 70 automatic, 50-69 shown with `explain()` as the reason,
  < 50 never used. A pair whose `latin_scale` must be clamped to 0.7-1.4 and still misses the body by more than 3 %
  is at most "shown": its heights stay apart.
- **latin_scale** = 1.00 x Arabic body / Latin x-height (target ratio 1.00, executor ruling Q56-4), so the scaled
  x-height sits on the Arabic letter body.
- **Licence proof per face** (the J4.2 open-font index does not exist yet): nameID 13 and 14, the sha256 of the
  family's OFL.txt with LF line endings (this repo's working tree holds three OFL.txt files with CRLF while git stores
  LF, so a raw hash would differ per checkout), and the font file's sha256. A face whose name table does not say OFL,
  or whose folder has no OFL text, makes the builder refuse the whole build before anything is written.
- **Which pairs**: every superfamily, and every Arabic family with a Latin-only family whose classes earn at least 20
  class points (same class, or geometric with humanist). Rows are grouped by the weights they serve (400 small,
  500 body, 700 caption and term, 900 headline).
- **Rebuild**: `python -m lib.font_pairing build --fonts <folder> [--fonts <folder> ...] --write` from
  `whynot-cut/engine/reel`. With both folders it gives the same bytes twice. Without the downloaded folder, its
  families and rows are kept as measured, so the repo-only rebuild in the tests gives the committed bytes too
  (`test_rebuilding_from_the_repo_fonts_is_byte_identical`). A newly downloaded folder is added the same way; each
  new file's sha256 goes into `families.<name>.files`.

## Results
rows 153: auto 100, refused 2, shown 51; kinds: pair 124, superfamily 29

3 % check: 144 of 144 unclamped rows align within 3 %. 137 rows scale freely (largest deviation 0.000065, from rounding latin_scale to 4 decimals); 7 rows hit a range edge but still land within 3 % (largest deviation 0.0294); 9 rows are clamped (below).

| Arabic family (class) | weights | best Latin partner (class) | score | band | latin_scale |
|---|---|---|---|---|---|
| Lalezar (display) | 400, 500, 700, 900 | Lalezar (display) (superfamily) | 76.05 | auto | 0.738 |
| Rakkas (display) | 400, 500, 700, 900 | Syne (display) | 86.04 | auto | 0.8813 |
| Amiri (formal) | 400, 500 | Amiri (formal) (superfamily) | 85.34 | auto | 0.9255 |
| Amiri (formal) | 700 | Amiri (formal) (superfamily) | 81.78 | auto | 0.9344 |
| Noto Naskh Arabic (formal) | 400 | Markazi Text (formal) | 75.75 | auto | 0.9333 |
| Noto Naskh Arabic (formal) | 500 | Markazi Text (formal) | 77.78 | auto | 0.9981 |
| Noto Naskh Arabic (formal) | 700 | Markazi Text (formal) | 76.17 | auto | 1.0398 |
| Alexandria (geometric) | 500 | Alexandria (geometric) (superfamily) | 96.34 | auto | 0.9796 |
| Alexandria (geometric) | 700 | Montserrat (geometric) | 94.69 | auto | 1.0093 |
| Alexandria (geometric) | 900 | Montserrat (geometric) | 93.5 | auto | 0.9817 |
| Cairo (geometric) | 400 | Cairo (geometric) (superfamily) | 95.98 | auto | 1.0 |
| Cairo (geometric) | 500 | Cairo (geometric) (superfamily) | 96.24 | auto | 1.0 |
| Cairo (geometric) | 700 | Cairo (geometric) (superfamily) | 94.99 | auto | 1.0 |
| Cairo (geometric) | 900 | Cairo (geometric) (superfamily) | 94.2 | auto | 1.0 |
| Readex Pro (geometric) | 400 | Readex Pro (geometric) (superfamily) | 78.91 | auto | 0.7429 |
| Readex Pro (geometric) | 500 | Readex Pro (geometric) (superfamily) | 88.15 | auto | 0.8539 |
| Readex Pro (geometric) | 700 | Readex Pro (geometric) (superfamily) | 89.29 | auto | 0.8908 |
| Tajawal (geometric) | 400 | Montserrat (geometric) | 87.7 | auto | 0.8152 |
| Tajawal (geometric) | 500 | Montserrat (geometric) | 88.3 | auto | 0.8189 |
| Tajawal (geometric) | 700 | Tajawal (geometric) (superfamily) | 88.39 | auto | 0.9868 |
| Tajawal (geometric) | 900 | Tajawal (geometric) (superfamily) | 88.31 | auto | 1.0143 |
| Aref Ruqaa (handwritten) | 400, 500 | Aref Ruqaa (handwritten) (superfamily) | 81.35 | auto | 1.1478 |
| Aref Ruqaa (handwritten) | 700 | Aref Ruqaa (handwritten) (superfamily) | 77.47 | auto | 1.0967 |
| IBM Plex Sans Arabic (humanist) | 400 | Noto Sans (humanist) | 82.34 | auto | 0.7 |
| IBM Plex Sans Arabic (humanist) | 500 | Noto Sans (humanist) | 91.54 | auto | 0.8469 |
| IBM Plex Sans Arabic (humanist) | 700 | IBM Plex Sans Arabic (humanist) (superfamily) | 86.82 | auto | 0.8745 |
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
| Noto Naskh Arabic + Noto Serif | 400 | 70.42 | shown | 0.7 | 1.104 |
| Noto Naskh Arabic + Noto Naskh Arabic | 400 | 69.25 | shown | 0.7 | 1.104 |
| Aref Ruqaa + Dancing Script | 400 | 67.83 | shown | 1.4 | 0.873 |
| Aref Ruqaa + Dancing Script | 500 | 67.6 | shown | 1.4 | 0.873 |
| Aref Ruqaa + Dancing Script | 700 | 61.02 | shown | 1.4 | 0.863 |

Refused (< 50, kept in the table, never used):

- Readex Pro + Noto Sans @ [400]: 49.75
- Readex Pro + IBM Plex Sans @ [400]: 49.67

Findings: IBM Plex Mono: not used (monospace: not a caption face); Markazi Text: Arabic coverage gate: MarkaziText[wght].ttf cannot draw ٪

Downloaded set: 54 files (35 fonts, 19 OFL.txt); 54 of 54 re-hashed equal to the manifest; 35 font files in the table carry the manifest's sha256 (0 differ).

| folder | file | bytes | sha256 |
|---|---|---|---|
| cairo | OFL.txt | 4473 | `a4554e1799d42e1405924b61eb0e0722ae1623b1f1f07f995348f96c496362a9` |
| tajawal | OFL.txt | 4464 | `9b584984f9db0ee30347391a76eff9c0a6b03dc450c3c6afe3757a2cb3a4db87` |
| tajawal | Tajawal-Black.ttf | 59028 | `da582a579d3200869535dc994d2349608a8582042f8776b3679b157015db287c` |
| tajawal | Tajawal-Bold.ttf | 59988 | `0342ab6b74b6bd1b4b5bf7beda45a9734a2b3147a31e8a3a45b6a3417a52d9d7` |
| tajawal | Tajawal-ExtraBold.ttf | 59648 | `3d1298b747c22579f9e1bdeb0d4165064cb17f7e66145e2f43f9deb12ad7a2cf` |
| tajawal | Tajawal-ExtraLight.ttf | 55784 | `a12ffbfaaec30ab8142edc60fa4727b104a90eb54c6a200a76988a1ec2ec11dc` |
| tajawal | Tajawal-Light.ttf | 61864 | `ab26ed3e0c5af2c71b469b5780decff8088d290ab91aa29b07321580136e813a` |
| tajawal | Tajawal-Medium.ttf | 62280 | `1ff8bd943a261c9dd7906bdb1993cab87b6d925a7fb5f848cdb51ed301531090` |
| tajawal | Tajawal-Regular.ttf | 60364 | `6882892da3e03527d5db2bbab3b48bde6ef2e878a43f522d1a4eebda90010a19` |
| readexpro | OFL.txt | 4444 | `b41267a3903a45955f77b44596e080480c577fb7221df59672d0bc8cd8cd4b6f` |
| notosansarabic | OFL.txt | 4382 | `07fc70bfeb985cc1a87a8587d0a0c80bab11c86c9dc3fd95b6f0cb332f983e96` |
| notosans | OFL.txt | 4396 | `cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a` |
| notonaskharabic | OFL.txt | 4382 | `a7a5a25eb188bf1cd96982030d53e23c33485c69b1044a562254226857ee13af` |
| amiri | Amiri-Bold.ttf | 413480 | `cfccb794268e7d573d857e6d6a67f89cf8a053e8ffd85dfa0c8ec1bb36fc4827` |
| amiri | Amiri-Regular.ttf | 431116 | `ab391c4147d054c48976e98322ad0eefe1427aa0e0502a12a4c75d80a70cfcd7` |
| amiri | OFL.txt | 4389 | `72de68e5954f4fdd24702292ef5a32f003ca960ec9330dc86e5eefb5dffb9b22` |
| markazitext | OFL.txt | 4485 | `6e7f259edf178c70b2ee36acfcc934b76d1cd56bb58d2c8f2ab8b5dded8bd430` |
| arefruqaa | ArefRuqaa-Bold.ttf | 123852 | `247071015b7eefd63f94d6e47949c5d10294ed31bd432f809ba9a219d93f91bb` |
| arefruqaa | ArefRuqaa-Regular.ttf | 110696 | `ceb786d83ba92f35e96efcd8623c2858d288e0c543c8761ba35b1020989464f9` |
| arefruqaa | OFL.txt | 4464 | `41ac14451a624c69490e24b9aaaaa1f65dc9dc17c3f6f38172fc43d5ba654a1b` |
| lalezar | Lalezar-Regular.ttf | 290016 | `7b80807bc831f141de0f7dcf6816412bf0c548968d548c5156ca388733390ea9` |
| lalezar | OFL.txt | 4383 | `327bac41d89cf9f32e0efe353228018e1661cff458a5d4905714958514df7bd5` |
| rakkas | OFL.txt | 4423 | `5c36e7ec460b285185ea23847aa1f508708d9ce15d5c055279defd022972f836` |
| rakkas | Rakkas-Regular.ttf | 146824 | `54278882e4774c14d50c3b555f127d0fe586366d5b787316ebbcbd8108829e60` |
| ibmplexsans | OFL.txt | 4456 | `7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da` |
| poppins | OFL.txt | 4385 | `6be04893d770899a015649c7aa3b582f871b272f8747a92b78b17c3e5c8b2573` |
| poppins | Poppins-Black.ttf | 153440 | `d82aaaf98a9283f9a8edd24e51173337d8eaf09e25cd3d98831f8ec8461748a1` |
| poppins | Poppins-Bold.ttf | 155996 | `983676516167748b74de6f4771fb384c664fd913acb8b471122ecacf5da5ea6c` |
| poppins | Poppins-ExtraBold.ttf | 154836 | `f2ab17c1a63a0ecc12c2461848fc8a469395e3cd2d641803e889c643d9f958e1` |
| poppins | Poppins-ExtraLight.ttf | 163568 | `55c03314cc754e26f741f97890e5e9cbe3b3278fe3abcecfecafd60111b2643d` |
| poppins | Poppins-Light.ttf | 161936 | `650ba57fa99d12ec40c31ccfb680be656be4497fbe14164617d67e32ffe9cd46` |
| poppins | Poppins-Medium.ttf | 158576 | `90373e7d838d32468438fc3e152dca0bdb12edcab99ea639f158790b1ba1fd05` |
| poppins | Poppins-Regular.ttf | 160316 | `7e65201e9b79159e2300267cc885e16c8dcef2424cdfa09a29bfb0980a94a7ba` |
| poppins | Poppins-SemiBold.ttf | 157312 | `d3bf1bdaf0550e83da9ac0b1d1d9fe6db086835a83aa28578e609a394b9a0286` |
| poppins | Poppins-Thin.ttf | 163672 | `6d8e5d9d29140cc93e321745fa1243c67889e6bc3639ec34db64f3da7a496352` |
| montserrat | OFL.txt | 4400 | `8b7141c03fa4f8d44e6345d5d4931709290f0f67875e452e95ac1fd3a027802e` |
| notoserif | OFL.txt | 4396 | `cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a` |
| lora | OFL.txt | 4423 | `1d9a970809ac804b582a6ce7f0ebc4e7fefcbfd7ff6299cad35ee656a21be716` |
| dancingscript | OFL.txt | 4443 | `6f090277c00af96651ce6dbcc38ff1591047a3bffef486e80b6a32e8276a8201` |
| anton | Anton-Regular.ttf | 170812 | `a4ba3a92350ebb031da0cb47630ac49eb265082ca1bc0450442f4a83ab947cab` |
| anton | OFL.txt | 4484 | `ee67e6ee22790b7929f1a3769ca2801d565c64b5a9096942c1adf5596de9c9e4` |
| bebasneue | BebasNeue-Regular.ttf | 61400 | `08e4623805102d819f58601e46e345648846075e363b2ceb23313c2d1c83ec73` |
| bebasneue | OFL.txt | 4337 | `72082f6cb4d04be2ecf7cc7d9e1e7d73787f0af8a5a278a47cade70c16b78341` |
| cairo | Cairo[slnt,wght].ttf | 599548 | `667c987182391c91f4e57a2f455b1794fb5e3ee6ca4ef3383e86bb690fa9c964` |
| readexpro | ReadexPro[HEXP,wght].ttf | 278544 | `268bba7e1e8f3b14d798b3fb0e40ebaa3fc39308c9ac0020e2faf6df181cc30e` |
| notosansarabic | NotoSansArabic[wdth,wght].ttf | 844676 | `63111b5b2e074dd48cc67692e0a2726d86ee94c1c37fe8598257b7b4e87e869e` |
| notosans | NotoSans[wdth,wght].ttf | 2049096 | `bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d` |
| notonaskharabic | NotoNaskhArabic[wght].ttf | 307592 | `67b5a525a661b607971fbd3f96a81b89d3a768e74534fca84f18ac97e6fab72f` |
| markazitext | MarkaziText[wght].ttf | 296896 | `424b7331681160ff2a4b209bfc356ea9564d429a7daea43ee4dc28de8ff4f9fe` |
| ibmplexsans | IBMPlexSans[wdth,wght].ttf | 537244 | `3b031aa4216174205bd8471f88a49b91f093169e9e87bd5262242bc5967fe2e3` |
| montserrat | Montserrat[wght].ttf | 744936 | `0f7b311b2f3279e4eef9b2f968bcdbab6e28f4daeb1f049f4f278a902bcd82f7` |
| notoserif | NotoSerif[wdth,wght].ttf | 1887192 | `4d8e6761424656867019081a1a01336f3cb086982682698714054fc33f782713` |
| lora | Lora[wght].ttf | 212196 | `822a6621ccbe8d97d20ac88c1c41f5615c9c2c202eaa75f272cd452aac6475a7` |
| dancingscript | DancingScript[wght].ttf | 133636 | `21808625578fe8d8cd10cb684be546dca077b27cd03a53a2f1ec11dc743c924c` |

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
- `tests/test_font_pairing.py`: 63 tests. Traits on made fonts with known boxes (dots, split base+dot clusters, a
  variable font, a collection face, 20 000 glyphs, an Arabic path with spaces), the coverage gate (also lam-alef from two
  contextual glyphs), score parts and bands, `latin_scale` and the 3 % bound, `pick` order, the licence refusals, and
  the table itself (structure, OFL shas, sorted rows, byte-identical rebuild).
- Mutation (scratch copy, one heavy.sh job): 47 mutants of the weights, bands, tolerances, coverage strings, lam-alef
  rule, body measure, `latin_scale` and clamp, `pick` order, licence checks, row weights and the trait cache: all 47
  killed.

## What is not measured, and why
- **No spec candidate is left unmeasured.** Every family the spec names was measured. Markazi Text fails the Arabic
  gate (no ٪, U+066A): it serves only as a Latin partner of the formal Arabic families.
- **IBM Plex Mono** is left out (monospace, not a caption face).
- **Weights out of reach** get no row: for example, IBM Plex Sans Arabic has no face within 150 of 900 in the repo, and
  Noto Naskh Arabic stops at 700.
- **Variable instances in rendering**: the table measures variable fonts at the row's weight. Today's caption engines
  draw a font file at its default instance, so the looks hook uses only static faces from the table until the
  renderer sets the instance (written in the patch README).

## Not verified
- **Specimen sheet verdict (H29):** sheets for every row, per class and the best caption pair per Arabic family were
  drawn by `specimen_sheet()` (outside the repo, Builder A's work folder). The brand-systems-designer verdict and
  Yunus's approval (HM-4) are pending. The classes in the table are the curator's draft until then.
- **Rendered frames:** pairing on Premiere/AE frames is M2-T5 (Phase 6). Only our own stills were inspected.
- **Hook behaviour live:** the looks and wnc-queue patches are tested on a scratch copy and are not applied here.
