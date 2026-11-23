"""Tests de la extracción de contenido para las portadas editoriales."""

from dataclasses import replace
from pathlib import Path

from news_agent.cover.source import (
    article_date,
    build_alt_text,
    build_content,
    extract_deck,
    extract_quote,
    select_figure,
    slug_for_article,
    source_sha256,
)
from news_agent.cover.specs import cover_specs
from news_agent.social.article_source import parse_article_file

APPENDIX_MARKER = "## 📰 Propuestas de portada"


def _without_appendix(text: str) -> str:
    """Quita el apéndice de propuestas de portada del Markdown.

    Args:
        text: Markdown original.

    Returns:
        str: Markdown sin el apéndice.
    """
    return text.split(APPENDIX_MARKER, 1)[0].rstrip() + "\n"


class TestDeck:
    """Extracción de la bajada."""

    def test_prefers_the_applied_proposal(self, cover_article):
        deck = extract_deck(cover_article)

        assert deck.startswith("La municipalidad de Villarrica")
        assert "42 familias" in deck

    def test_falls_back_to_the_italic_line(self, cover_article):
        article = replace(
            cover_article, raw_text=_without_appendix(cover_article.raw_text)
        )

        assert extract_deck(article).startswith("La municipalidad de Villarrica")

    def test_falls_back_to_the_body_paragraphs(self, cover_article):
        raw = _without_appendix(cover_article.raw_text)
        raw = raw.replace(
            "*La municipalidad de Villarrica confirmó el cierre de la escuela "
            "rural y 42 familias quedan sin matrícula para el próximo año.*",
            "",
        )
        article = replace(
            cover_article,
            raw_text=raw,
            paragraphs=[
                paragraph
                for paragraph in cover_article.paragraphs
                if "municipalidad de Villarrica confirmó" not in paragraph
            ],
        )

        deck = extract_deck(article)

        assert deck
        assert "concejo municipal" in deck


class TestQuote:
    """Extracción y limpieza de la cita de opinión."""

    def test_returns_a_clean_quote(self, cover_article):
        quote = extract_quote(cover_article)

        assert quote == "No vamos a permitir que nos arranquen la escuela"

    def test_falls_back_to_a_quoted_sentence(self, cover_article):
        article = replace(cover_article, quote_candidates=[])

        quote = extract_quote(article)

        assert quote
        assert "sostuvo" not in quote


class TestFigure:
    """Selección de la cifra protagonista."""

    def test_selects_the_title_figure_as_strong(self, cover_article):
        figure, caption, strong = select_figure(
            cover_article, cover_specs(None)["limits"]
        )

        assert figure == "42 familias"
        assert strong is True
        assert "42" in caption

    def test_ignores_a_time_fragment(self, tmp_path: Path):
        path = tmp_path / "articulo_9_nota.md"
        path.write_text(
            "# La sesión del concejo\n\n"
            "**Por La Chispa Sur**\n\n---\n\n"
            "La comisión sesiona a las 16:00 horas en la sala principal.\n\n"
            "El resto de la nota no tiene cifras relevantes.\n",
            encoding="utf-8",
        )
        article = parse_article_file(path)

        figure, caption, strong = select_figure(
            article, cover_specs(None)["limits"]
        )

        assert (figure, caption, strong) == ("", "", False)


class TestContent:
    """Construcción del contenido editorial."""

    def test_builds_a_text_first_cover(self, cover_article):
        content = build_content(
            cover_article, "Nacional", "text_first", cover_specs(None)
        )

        assert content.title.startswith("Cierre de la escuela rural")
        assert content.category == "Nacional"
        assert content.treatment == "text_first"
        assert content.deck
        assert content.byline == "Por La Chispa Sur"
        assert content.alt_text.startswith("Cierre de la escuela rural")

    def test_builds_an_opinion_quote(self, cover_article):
        content = build_content(
            cover_article, "Opinión", "auto", cover_specs(None)
        )

        assert content.treatment == "quote"
        assert content.quote == (
            "No vamos a permitir que nos arranquen la escuela"
        )
        assert "Cita destacada" in content.alt_text

    def test_builds_a_data_cover(self, cover_article):
        content = build_content(
            cover_article, "Política", "auto", cover_specs(None)
        )

        assert content.treatment == "data"
        assert content.figure == "42 familias"
        assert content.caption
        assert content.alt_text.startswith("42 familias")

    def test_falls_back_when_the_forced_quote_has_no_material(
        self, cover_article
    ):
        article = replace(
            cover_article,
            quote_candidates=[],
            paragraphs=[],
            lead="",
        )

        content = build_content(
            article, "Cultura", "quote", cover_specs(None)
        )

        assert content.treatment == "text_first"
        assert content.warnings


class TestAltText:
    """Texto alternativo por tratamiento."""

    def test_mentions_the_section_and_the_medium(self, cover_article):
        content = build_content(
            cover_article, "Nacional", "text_first", cover_specs(None)
        )

        assert "Nacional" in content.alt_text
        assert "La Chispa Sur" in content.alt_text

    def test_quote_alt_text_includes_the_quote(self, cover_article):
        content = build_content(
            cover_article, "Opinión", "auto", cover_specs(None)
        )

        assert "Cita destacada" in build_alt_text(content)


class TestSourceMetadata:
    """Huella, fecha y slug del artículo."""

    def test_hash_is_deterministic(self, cover_article):
        assert source_sha256(cover_article) == source_sha256(cover_article)
        assert len(source_sha256(cover_article)) == 64

    def test_extracts_the_creation_date_from_the_name(
        self, cover_article_file
    ):
        moment = article_date(cover_article_file)

        assert moment is not None
        assert (moment.year, moment.month, moment.day) == (2026, 11, 23)

    def test_returns_none_without_a_date(self, tmp_path):
        assert article_date(tmp_path / "articulo_1_slug.md") is None

    def test_builds_a_slug_from_the_title(self, cover_article):
        slug = slug_for_article(cover_article)

        assert slug.startswith("cierre-de-la-escuela-rural")
