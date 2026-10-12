"""Tests de las reglas de lenguaje simple del tríptico impreso.

Estas revisiones solo advierten: el tríptico nunca recorta ni reescribe. Los
tests fijan que las advertencias aparezcan cuando corresponde y que el detector
de siglas respete la lista permitida de la configuración.
"""

from pathlib import Path

import pytest

from news_agent.config import load_triptych_config
from news_agent.triptych.specs import triptych_specs
from news_agent.triptych.text_utils import (
    count_words,
    find_acronyms,
    longest_sentence_words,
    normalize_acronym,
    shorten,
    split_sentences,
    style_warnings,
)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "triptych_config.json"


@pytest.fixture
def specs() -> dict:
    """Especificaciones resueltas con la configuración del repositorio.

    Returns:
        dict: Especificaciones del tríptico.
    """
    return triptych_specs(load_triptych_config(CONFIG_PATH))


class TestModuleContract:
    """El módulo expone las funciones que declara."""

    @pytest.mark.parametrize(
        "name",
        [
            "split_sentences",
            "count_words",
            "longest_sentence_words",
            "normalize_acronym",
            "find_acronyms",
            "style_warnings",
            "shorten",
        ],
    )
    def test_exposes_helper(self, name):
        import news_agent.triptych.text_utils as module

        assert callable(getattr(module, name))


class TestSplitSentences:
    """División en oraciones."""

    def test_splits_on_closing_punctuation(self):
        assert split_sentences("Uno. Dos! Tres?") == ["Uno.", "Dos!", "Tres?"]

    def test_returns_empty_list_without_text(self):
        assert split_sentences("") == []

    def test_ignores_trailing_whitespace(self):
        assert split_sentences("Uno.   Dos.") == ["Uno.", "Dos."]


class TestCountWords:
    """Conteo de palabras."""

    def test_counts_words_without_punctuation(self):
        assert count_words("Uno, dos; tres.") == 3

    def test_counts_numbers_as_words(self):
        assert count_words("15 países firmaron") == 3

    def test_returns_zero_without_text(self):
        assert count_words("") == 0


class TestLongestSentenceWords:
    """Largo de la oración más extensa."""

    def test_returns_the_longest_one(self):
        assert longest_sentence_words("Uno. Uno dos tres cuatro. Dos.") == 4

    def test_returns_zero_without_sentences(self):
        assert longest_sentence_words("") == 0


class TestAcronyms:
    """Detección de siglas."""

    def test_normalizes_trailing_dot(self):
        assert normalize_acronym("EE.UU.") == "EE.UU"

    def test_finds_unknown_acronyms_sorted(self):
        assert find_acronyms("El FMI y la OTAN con el BID.") == [
            "BID",
            "FMI",
            "OTAN",
        ]

    def test_respects_the_allowlist(self):
        assert find_acronyms("El FMI y el PDI.", ["PDI"]) == ["FMI"]

    def test_does_not_repeat_matches(self):
        assert find_acronyms("FMI ahora y FMI después.") == ["FMI"]

    def test_returns_empty_list_without_text(self):
        assert find_acronyms("") == []

    def test_ignores_lowercase_words(self):
        assert find_acronyms("el fmi y la otan") == []


class TestStyleWarnings:
    """Advertencias de estilo."""

    def test_warns_about_a_long_sentence(self, specs):
        text = (
            "Esta oración es demasiado larga porque acumula demasiadas "
            "palabras seguidas sin respirar casi en ningún momento."
        )
        warnings = style_warnings(text, specs)

        assert len(warnings) == 1
        assert "oración de 16 palabras (máximo 15)" in warnings[0]

    def test_warns_about_an_unexplained_acronym(self, specs):
        warnings = style_warnings("El FMI presiona.", specs)

        assert any("siglas sin explicar (FMI)" in item for item in warnings)

    def test_names_the_block_in_the_warning(self, specs):
        warnings = style_warnings("El FMI presiona.", specs, label="nota 3")

        assert warnings[0].startswith("nota 3:")

    def test_warns_about_forbidden_terms(self, specs):
        custom = dict(specs)
        custom["style"] = dict(specs["style"], forbidden_terms=["gobernanza"])

        warnings = style_warnings("La gobernanza cambió.", custom)

        assert any("gobernanza" in item for item in warnings)

    def test_returns_no_warnings_for_clean_text(self, specs):
        text = (
            "Chile firmó un acuerdo. El texto trata de litio. "
            "Casi nadie lo votó."
        )

        assert style_warnings(text, specs) == []

    def test_tolerates_empty_text(self, specs):
        assert style_warnings("", specs) == []


class TestShorten:
    """Recorte de citas para las advertencias."""

    def test_keeps_short_text_untouched(self):
        assert shorten("Una frase breve.", 40) == "Una frase breve."

    def test_collapses_whitespace(self):
        assert shorten("Una   frase\nbreve.", 40) == "Una frase breve."

    def test_truncates_with_ellipsis(self):
        result = shorten("palabra " * 20, 20)

        assert len(result) == 20
        assert result.endswith("…")
