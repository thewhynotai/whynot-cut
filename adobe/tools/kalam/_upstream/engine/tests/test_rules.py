from kalam.rules import capitalize_latin, enforce, strip_diacritics, strip_punct


def test_strip_punct_removes_arabic_and_latin_marks():
    assert strip_punct("صحح، الكلام. ده! إزاي؟ (مثلا) \"كده\"…") == "صحح الكلام ده إزاي مثلا كده"


def test_strip_punct_turns_hyphens_into_spaces():
    assert strip_punct("X-Ray و 50-60 سنتي") == "X Ray و 50 60 سنتي"


def test_strip_punct_keeps_percent_and_article_tatweel():
    assert strip_punct("زادت 80% في الـ Fracture") == "زادت 80% في الـ Fracture"


def test_strip_diacritics_keeps_only_tanween_fath():
    assert strip_diacritics("جدًّا مَثلًا فِعلًا") == "جدًا مثلًا فعلًا"


def test_strip_diacritics_keeps_tatweel_of_article():
    assert strip_diacritics("الـ Fracture") == "الـ Fracture"


def test_capitalize_latin_title_cases_each_word_and_keeps_acronyms():
    assert capitalize_latin("founder content CRP associated with broken bone") == \
        "Founder Content CRP Associated With Broken Bone"


def test_enforce_never_puts_hamza_on_inta():
    assert enforce("إنت عارف وأنتو شايفين وإنتي فاهمة", {}) == "انت عارف وانتو شايفين وانتي فاهمة"


def test_enforce_applies_glossary_case_insensitively_on_whole_words():
    g = {"Granudacyn": ["graniodasin"], "ESR": ["esr"], "Masquelet Technique": ["muscular technique"]}
    assert enforce("استخدمنا GranioDasin و esr ثم muscular technique", g) == \
        "استخدمنا Granudacyn و ESR ثم Masquelet Technique"


def test_enforce_glossary_does_not_touch_parts_of_words():
    assert enforce("esrabc", {"ESR": ["esr"]}) == "Esrabc"


def test_enforce_full_line():
    assert enforce("الدرس، اللي اتعلمته: safety  الأمان!", {}) == "الدرس اللي اتعلمته Safety الأمان"


def test_english_mode_keeps_sentence_case_but_drops_punctuation():
    assert enforce("Hello, and welcome to this short test.", {}, mode="en") == "Hello and welcome to this short test"


def test_glossary_still_applies_in_english_mode():
    assert enforce("we used graniodasin here", {"Granudacyn": ["graniodasin"]}, mode="en") == "we used Granudacyn here"
