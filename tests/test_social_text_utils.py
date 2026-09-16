"""Tests de las utilidades de texto del subsistema de RRSS."""

from news_agent.social.text_utils import (
    ensure_list_of_text,
    fit_char_limit,
    render_hashtags,
    sanitize_hashtag,
    sanitize_hashtags,
    strip_trailing_hashtags,
)


class TestStripTrailingHashtags:
    """Retiro de la tanda final de hashtags que agrega el modelo."""

    def test_removes_the_trailing_run(self):
        assert strip_trailing_hashtags("Cierre del hilo. #Chile #Protesta") == (
            "Cierre del hilo."
        )

    def test_removes_hashtags_separated_by_line_breaks(self):
        assert strip_trailing_hashtags("Texto del post\n\n#Chile\n#Protesta") == (
            "Texto del post"
        )

    def test_keeps_internal_hashtags(self):
        text = "La etiqueta #Chile aparece dentro de la frase."

        assert strip_trailing_hashtags(text) == text

    def test_leaves_text_without_hashtags_untouched(self):
        assert strip_trailing_hashtags("Sin etiquetas al final") == (
            "Sin etiquetas al final"
        )

    def test_handles_empty_text(self):
        assert strip_trailing_hashtags("") == ""
        assert strip_trailing_hashtags(None) == ""

    def test_removes_a_text_made_only_of_hashtags(self):
        assert strip_trailing_hashtags("#Chile #Protesta") == ""

# ---------------------------------------------------------------------------
# fit_char_limit
# ---------------------------------------------------------------------------


class TestFitCharLimit:
    """Ajuste de textos a los límites de caracteres de cada plataforma."""

    def test_returns_text_unchanged_when_it_fits(self):
        text, trimmed = fit_char_limit("Hola mundo", 50)

        assert text == "Hola mundo"
        assert trimmed is False

    def test_returns_text_unchanged_exactly_at_limit(self):
        text, trimmed = fit_char_limit("abcde", 5)

        assert text == "abcde"
        assert trimmed is False

    def test_cuts_at_last_complete_sentence(self):
        text = "Primera oración completa. Segunda oración que ya no cabe del todo"

        result, trimmed = fit_char_limit(text, 40)

        assert trimmed is True
        assert result == "Primera oración completa."
        assert len(result) <= 40

    def test_cuts_at_word_boundary_with_ellipsis(self):
        text = "palabra " * 20

        result, trimmed = fit_char_limit(text.strip(), 30)

        assert trimmed is True
        assert len(result) <= 30
        assert result.endswith("…")

    def test_never_exceeds_the_limit(self):
        text = "x" * 500

        result, trimmed = fit_char_limit(text, 100)

        assert trimmed is True
        assert len(result) <= 100

    def test_non_positive_limit_returns_empty(self):
        result, trimmed = fit_char_limit("contenido", 0)

        assert result == ""
        assert trimmed is True

    def test_none_text_is_treated_as_empty(self):
        result, trimmed = fit_char_limit(None, 10)

        assert result == ""
        assert trimmed is False


# ---------------------------------------------------------------------------
# sanitize_hashtag
# ---------------------------------------------------------------------------


class TestSanitizeHashtag:
    """Normalización de hashtags sueltos."""

    def test_removes_leading_hash(self):
        assert sanitize_hashtag("#Chile") == "Chile"

    def test_joins_words_in_camel_case(self):
        assert sanitize_hashtag("La Araucania") == "LaAraucania"

    def test_keeps_underscores_and_accents(self):
        assert sanitize_hashtag("#La_Araucanía") == "La_Araucanía"

    def test_removes_punctuation(self):
        assert sanitize_hashtag("#derechos-humanos!") == "derechoshumanos"

    def test_returns_empty_for_blank_input(self):
        assert sanitize_hashtag("   ") == ""
        assert sanitize_hashtag("#") == ""
        assert sanitize_hashtag("") == ""


# ---------------------------------------------------------------------------
# sanitize_hashtags
# ---------------------------------------------------------------------------


class TestSanitizeHashtags:
    """Normalización de listas de hashtags."""

    def test_cleans_and_respects_limit(self):
        raw = ["#Chile", "La Araucania", "DerechosHumanos", "Extra"]

        result = sanitize_hashtags(raw, 3)

        assert result == ["Chile", "LaAraucania", "DerechosHumanos"]

    def test_removes_duplicates_ignoring_case(self):
        result = sanitize_hashtags(["chile", "#Chile", "CHILE"], 10)

        assert result == ["chile"]

    def test_ignores_non_string_entries(self):
        result = sanitize_hashtags(["Chile", 42, None, "Protesta"], 10)

        assert result == ["Chile", "Protesta"]

    def test_non_list_input_returns_empty(self):
        assert sanitize_hashtags("Chile", 10) == []
        assert sanitize_hashtags(None, 10) == []

    def test_zero_limit_returns_empty(self):
        assert sanitize_hashtags(["Chile"], 0) == []


# ---------------------------------------------------------------------------
# render_hashtags y ensure_list_of_text
# ---------------------------------------------------------------------------


class TestRenderHashtags:
    """Composición de la cadena final de hashtags."""

    def test_adds_hash_symbol_and_joins_with_spaces(self):
        assert render_hashtags(["Chile", "Protesta"]) == "#Chile #Protesta"

    def test_skips_empty_entries(self):
        assert render_hashtags(["Chile", "", "Protesta"]) == "#Chile #Protesta"

    def test_empty_list_returns_empty_string(self):
        assert render_hashtags([]) == ""


class TestEnsureListOfText:
    """Coacción de valores crudos del modelo a listas de textos."""

    def test_string_becomes_single_item_list(self):
        assert ensure_list_of_text("texto") == ["texto"]

    def test_blank_string_becomes_empty_list(self):
        assert ensure_list_of_text("   ") == []

    def test_list_is_cleaned_and_filtered(self):
        assert ensure_list_of_text(["  uno  ", "", 3, "dos"]) == ["uno", "dos"]

    def test_non_list_input_returns_empty(self):
        assert ensure_list_of_text(None) == []
        assert ensure_list_of_text(42) == []
