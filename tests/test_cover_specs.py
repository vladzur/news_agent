"""Tests de las especificaciones de portadas editoriales."""

import pytest

from news_agent.config import (
    COVER_CATEGORIES,
    COVER_DEFAULT_CATEGORY,
    COVER_FORMATS,
    COVER_LIMITS,
    COVER_PROPOSAL_CATEGORIES,
)
from news_agent.cover.models import CoverFormat
from news_agent.cover.specs import (
    category_for_article,
    cover_specs,
    format_specs,
    resolve_category,
    resolve_treatment,
    treatment_label,
)


class TestCoverSpecs:
    """Resolución de categorías, formatos y límites."""

    def test_uses_the_defaults_without_config(self):
        specs = cover_specs(None)

        assert set(specs["categories"]) == set(COVER_CATEGORIES)
        assert set(specs["formats"]) == set(COVER_FORMATS)
        assert specs["limits"] == COVER_LIMITS
        assert specs["default_category"] == COVER_DEFAULT_CATEGORY
        assert specs["proposal_categories"] == list(COVER_PROPOSAL_CATEGORIES)

    def test_merges_a_partial_section(self):
        config = {
            "covers": {
                "categories": {
                    "Actualidad": {"label": "Actualidad", "accent": "#123456"}
                },
                "formats": {
                    "og": {
                        "width": 1000,
                        "height": 500,
                        "filename": "otra.png",
                    }
                },
                "limits": {"title_max_lines": 3},
                "default_category": "Actualidad",
            }
        }

        specs = cover_specs(config)

        assert specs["categories"]["Actualidad"]["accent"] == "#123456"
        assert specs["formats"]["og"]["width"] == 1000
        assert specs["formats"]["web"]["width"] == 1600
        assert specs["limits"]["title_max_lines"] == 3
        assert specs["limits"]["deck_max_lines"] == COVER_LIMITS["deck_max_lines"]


class TestResolveCategory:
    """Resolución tolerante de nombres de sección."""

    def test_returns_the_official_key(self):
        specs = cover_specs(None)

        assert resolve_category("Opinión", specs) == "Opinión"
        assert resolve_category("opinion", specs) == "Opinión"
        assert resolve_category("  POLÍTICA  ", specs) == "Política"

    def test_rejects_an_unknown_category(self):
        with pytest.raises(ValueError, match="Sección desconocida"):
            resolve_category("Deportes", cover_specs(None))


class TestCategoryForArticle:
    """Sección por defecto según el número editorial."""

    def test_maps_the_first_three_proposals_to_nacional(self):
        specs = cover_specs(None)

        for number in (1, 2, 3):
            path = f"articulo_{number}_2026_11_23_slug.md"
            assert category_for_article(path, specs) == "Nacional"

    def test_maps_the_last_two_proposals_to_internacional(self):
        specs = cover_specs(None)

        for number in (4, 5):
            path = f"articulo_{number}_2026_11_23_slug.md"
            assert category_for_article(path, specs) == "Internacional"

    def test_falls_back_to_the_default_category(self):
        specs = cover_specs(None)

        assert category_for_article("nota-suelta.md", specs) == "Actualidad"

    def test_an_explicit_category_wins(self):
        specs = cover_specs(None)

        assert (
            category_for_article(
                "articulo_1_2026_11_23_slug.md", specs, "Cultura"
            )
            == "Cultura"
        )


class TestResolveTreatment:
    """Precedencia de los tratamientos editoriales."""

    def test_auto_uses_quote_for_opinion_with_a_quote(self):
        treatment, warnings = resolve_treatment(
            "auto", "Opinión", has_quote=True, has_figure=False
        )

        assert treatment == "quote"
        assert warnings == []

    def test_auto_falls_back_when_opinion_has_no_quote(self):
        treatment, warnings = resolve_treatment(
            "auto", "Opinión", has_quote=False, has_figure=False
        )

        assert treatment == "text_first"
        assert warnings

    def test_auto_uses_data_for_a_strong_figure(self):
        treatment, warnings = resolve_treatment(
            "auto", "Política", has_quote=False, has_figure=True, strong_figure=True
        )

        assert treatment == "data"
        assert warnings == []

    def test_auto_keeps_text_first_for_a_weak_figure(self):
        treatment, _ = resolve_treatment(
            "auto", "Política", has_quote=False, has_figure=True
        )

        assert treatment == "text_first"

    def test_forced_quote_falls_back_without_a_quote(self):
        treatment, warnings = resolve_treatment(
            "quote", "Cultura", has_quote=False, has_figure=False
        )

        assert treatment == "text_first"
        assert warnings

    def test_forced_data_falls_back_without_a_figure(self):
        treatment, warnings = resolve_treatment(
            "data", "Cultura", has_quote=False, has_figure=False
        )

        assert treatment == "text_first"
        assert warnings

    def test_forced_treatment_is_respected(self):
        treatment, warnings = resolve_treatment(
            "data", "Cultura", has_quote=True, has_figure=True
        )

        assert treatment == "data"
        assert warnings == []

    def test_rejects_an_unknown_treatment(self):
        with pytest.raises(ValueError, match="Tratamiento desconocido"):
            resolve_treatment("collage", "Nacional", False, False)


class TestFormats:
    """Orden y validación de los formatos de salida."""

    def test_returns_og_before_web(self):
        formats = format_specs(cover_specs(None))

        assert [item.name for item in formats] == ["og", "web"]
        assert all(isinstance(item, CoverFormat) for item in formats)

    def test_rejects_a_format_without_dimensions(self):
        specs = cover_specs(None)
        specs["formats"]["og"] = {
            "width": 0,
            "height": 630,
            "filename": "portada_og.png",
        }

        with pytest.raises(ValueError, match="dimensiones"):
            format_specs(specs)

    def test_exposes_the_treatment_label(self):
        assert treatment_label("quote") == "Cita de opinión"
        assert treatment_label("desconocido") == "desconocido"
