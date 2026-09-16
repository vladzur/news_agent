"""Tests del parseo del artículo de origen del subsistema de RRSS."""

from pathlib import Path

import pytest

from news_agent.social.article_source import ArticleParseError, parse_article_file
from news_agent.social.models import ArticleSource, normalize_for_match

# ---------------------------------------------------------------------------
# Parseo de un artículo válido
# ---------------------------------------------------------------------------


class TestParseArticleFile:
    """Extracción de las piezas reutilizables del artículo."""

    def test_returns_article_source(self, article):
        assert isinstance(article, ArticleSource)

    def test_extracts_title_from_h1(self, article):
        assert article.title == (
            "Disparo simbólico, cárcel real: la criminalización de la "
            "disidencia digital"
        )

    def test_extracts_byline(self, article):
        assert article.byline == "Por La Chispa Sur"

    def test_extracts_lead_without_rules_or_byline(self, article):
        assert article.lead.startswith("Un hombre de 44 años fue detenido")
        assert "---" not in article.lead
        assert "Por La Chispa Sur" not in article.lead

    def test_extracts_sections_in_order(self, article):
        headings = [section.heading for section in article.sections]

        assert headings == [
            "La captura en Cunco: ¿amenaza grave o intolerancia penalizada?",
            "Ampliar el delito de opinión",
        ]

    def test_section_body_excludes_the_next_heading(self, article):
        first = article.sections[0]

        assert "El problema es otro" in first.body
        assert "Ampliar el delito de opinión" not in first.body

    def test_extracts_sources_without_bullets(self, article):
        assert len(article.sources) == 2
        assert article.sources[0].startswith(
            "Radio Universidad de Chile: cobertura original"
        )

    def test_sources_block_is_not_part_of_the_body(self, article):
        body = article.body_text()

        assert "Fuentes consultadas" not in body
        assert "Artículo generado a partir de la pauta" not in body

    def test_counts_words_of_the_body_only(self, article):
        assert article.word_count > 150

    def test_extracts_key_figures_from_the_body(self, article):
        assert "44 años" in article.key_figures

    def test_extracts_quote_candidates_within_a_readable_range(self, article):
        assert article.quote_candidates
        for candidate in article.quote_candidates:
            assert 60 <= len(candidate) <= 240

    def test_quote_candidates_exclude_transition_openers(self, article):
        for candidate in article.quote_candidates:
            assert not candidate.lower().startswith("según")

    def test_paragraphs_preserve_paragraph_breaks(self, article):
        assert len(article.paragraphs) >= 5

    def test_path_is_absolute(self, article, article_file):
        assert article.path.is_absolute()
        assert article.path == article_file.resolve()

    def test_keeps_the_raw_markdown(self, article, article_markdown):
        assert article.raw_text == article_markdown


# ---------------------------------------------------------------------------
# Verificación de citas literales
# ---------------------------------------------------------------------------


class TestContainsVerbatim:
    """Verificación de que una cita proviene del artículo."""

    def test_accepts_a_literal_sentence(self, article):
        quote = (
            "No se trata de negar la gravedad de una comunicación amenazante "
            "contra una autoridad pública."
        )

        assert article.contains_verbatim(quote) is True

    def test_accepts_a_quote_with_normalized_typographic_quotes(self, article):
        # El artículo usa comillas tipográficas y el modelo suele devolver
        # comillas rectas: la verificación debe tolerarlo.
        quote = (
            "La alerta advertía sobre una publicación violenta difundida en "
            'un grupo de redes sociales llamado "Los Laureles Chile".'
        )

        assert article.contains_verbatim(quote) is True

    def test_rejects_a_fabricated_sentence(self, article):
        quote = (
            "El ministro renunció a su cargo tras una semana de protestas "
            "masivas en todo el país."
        )

        assert article.contains_verbatim(quote) is False

    def test_rejects_short_quotes_that_prove_nothing(self, article):
        assert article.contains_verbatim("44 años") is False


# ---------------------------------------------------------------------------
# Errores y casos límite
# ---------------------------------------------------------------------------


class TestParseArticleFileErrors:
    """Guardas de formato del artículo de origen."""

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(ArticleParseError, match="no encontrado"):
            parse_article_file(tmp_path / "inexistente.md")

    def test_directory_instead_of_file_raises(self, tmp_path: Path):
        with pytest.raises(ArticleParseError, match="no es un archivo"):
            parse_article_file(tmp_path)

    def test_empty_file_raises(self, tmp_path: Path):
        path = tmp_path / "vacio.md"
        path.write_text("   \n", encoding="utf-8")

        with pytest.raises(ArticleParseError, match="vacío"):
            parse_article_file(path)

    def test_file_without_h1_raises(self, tmp_path: Path):
        path = tmp_path / "sin-titulo.md"
        path.write_text("Solo un párrafo suelto sin titular.", encoding="utf-8")

        with pytest.raises(ArticleParseError, match="titular de"):
            parse_article_file(path)

    def test_article_without_sections_keeps_everything_in_the_lead(
        self, tmp_path: Path
    ):
        path = tmp_path / "sin-secciones.md"
        path.write_text(
            "# Titular de prueba\n\n**Por La Chispa Sur**\n\n---\n\n"
            "Un único párrafo de cuerpo sin subtítulos de ningún tipo.\n",
            encoding="utf-8",
        )

        article = parse_article_file(path)

        assert article.sections == []
        assert article.lead == "Un único párrafo de cuerpo sin subtítulos de ningún tipo."

    def test_article_without_byline_has_empty_byline(self, tmp_path: Path):
        path = tmp_path / "sin-firma.md"
        path.write_text(
            "# Titular de prueba\n\n---\n\nCuerpo del artículo sin firma.\n",
            encoding="utf-8",
        )

        article = parse_article_file(path)

        assert article.byline == ""
        assert article.lead == "Cuerpo del artículo sin firma."

    def test_article_without_sources_has_empty_sources(self, tmp_path: Path):
        path = tmp_path / "sin-fuentes.md"
        path.write_text(
            "# Titular de prueba\n\nCuerpo del artículo sin bloque de fuentes.\n",
            encoding="utf-8",
        )

        article = parse_article_file(path)

        assert article.sources == []


# ---------------------------------------------------------------------------
# Normalización para comparaciones
# ---------------------------------------------------------------------------


class TestNormalizeForMatch:
    """Normalización de textos para comparar coincidencias literales."""

    def test_lowercases_and_collapses_whitespace(self):
        assert normalize_for_match("Hola   MUNDO\n\tnuevo") == "hola mundo nuevo"

    def test_removes_markdown_emphasis(self):
        assert normalize_for_match("Texto **en negrita** y _cursiva_") == (
            "texto en negrita y cursiva"
        )

    def test_unifies_typographic_quotes_and_dashes(self):
        assert normalize_for_match("“cita” — guion") == '"cita" - guion'

    def test_handles_none_as_empty(self):
        assert normalize_for_match(None) == ""
