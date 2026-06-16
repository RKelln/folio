from __future__ import annotations

from folio.core.classifier import detect_language


def test_detect_language_french():
    text = "Le projet de recherche et la creation pour les artistes dans le cadre du programme"
    assert detect_language(text) == "fr"


def test_detect_language_english():
    text = "The project will support research and creation for artists under the program"
    assert detect_language(text) == "en"


def test_detect_language_mixed():
    text = "Le projet de recherche and the creation pour les artistes dans le cadre du programme with support from"
    assert detect_language(text) == "mixed"


def test_detect_language_empty():
    assert detect_language("") == "en"


def test_detect_language_no_common_words():
    assert detect_language("xyzzy plugh quux") == "en"


def test_detect_language_english_with_common_words():
    text = "The board has approved this for the project and will have been completed with support from all that can"
    assert detect_language(text) == "en"


def test_detect_language_ratio_just_over_threshold():
    text = "le la les de du des et est que qui dans pour sur une avec sont par plus faire peut ces leur"
    assert detect_language(text) == "fr"
