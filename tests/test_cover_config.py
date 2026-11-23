"""Tests de la configuración de portadas editoriales."""

import json
from pathlib import Path

import pytest

from news_agent.config import (
    COVER_CATEGORIES,
    COVER_DEFAULT_CATEGORY,
    COVER_FORMATS,
    COVER_LIMITS,
    ConfigurationError,
    load_cover_config,
    load_social_config,
)

BRAND = {
    "name": "La Chispa Sur",
    "colors": {
        "background": "#0E0E10",
        "surface": "#1A1A1F",
        "text": "#FFFFFF",
        "muted": "#A8A8B3",
        "accent": "#DF3224",
        "accent_alt": "#F2C14E",
    },
}


def _write(tmp_path: Path, payload: dict) -> Path:
    """Escribe una configuración JSON temporal.

    Args:
        tmp_path: Directorio de la prueba.
        payload: Contenido del archivo.

    Returns:
        Path: Ruta del archivo escrito.
    """
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class TestLoadCoverConfig:
    """Carga y normalización de la sección ``covers``."""

    def test_uses_the_defaults_without_a_covers_section(self, tmp_path):
        config = load_cover_config(_write(tmp_path, {"brand": BRAND}))
        covers = config["covers"]

        assert set(covers["categories"]) == set(COVER_CATEGORIES)
        assert covers["formats"] == {
            name: dict(spec) for name, spec in COVER_FORMATS.items()
        }
        assert covers["limits"] == COVER_LIMITS
        assert covers["default_category"] == COVER_DEFAULT_CATEGORY

    def test_merges_a_partial_categories_section(self, tmp_path):
        payload = {
            "brand": BRAND,
            "covers": {
                "categories": {
                    "Nacional": {"label": "País", "accent": "#123456"}
                }
            },
        }

        covers = load_cover_config(_write(tmp_path, payload))["covers"]

        assert covers["categories"]["Nacional"] == {
            "label": "País",
            "accent": "#123456",
        }
        assert "Opinión" in covers["categories"]

    def test_normalizes_the_category_names(self, tmp_path):
        payload = {
            "brand": BRAND,
            "covers": {"default_category": "opinion"},
        }

        covers = load_cover_config(_write(tmp_path, payload))["covers"]

        assert covers["default_category"] == "Opinión"

    def test_accepts_a_custom_format_size(self, tmp_path):
        payload = {
            "brand": BRAND,
            "covers": {
                "formats": {
                    "og": {"width": 1000, "height": 500}
                }
            },
        }

        covers = load_cover_config(_write(tmp_path, payload))["covers"]

        assert covers["formats"]["og"]["width"] == 1000
        assert covers["formats"]["og"]["filename"] == "portada_og.png"

    def test_accepts_custom_limits(self, tmp_path):
        payload = {
            "brand": BRAND,
            "covers": {"limits": {"title_max_lines": 3}},
        }

        covers = load_cover_config(_write(tmp_path, payload))["covers"]

        assert covers["limits"]["title_max_lines"] == 3
        assert covers["limits"]["deck_max_lines"] == COVER_LIMITS["deck_max_lines"]

    def test_does_not_require_the_social_sections(self, tmp_path):
        config = load_cover_config(_write(tmp_path, {"brand": BRAND}))

        assert config["brand"]["name"] == "La Chispa Sur"
        assert "covers" in config


class TestCoverConfigErrors:
    """Rechazo de configuraciones inválidas."""

    @pytest.mark.parametrize(
        "covers",
        [
            {"categories": {"Nacional": {"accent": "rojo"}}},
            {"categories": {"Nacional": {"label": "", "accent": "#FFFFFF"}}},
            {"categories": {"Nacional": {"accent": "#FFFFFF", "extra": 1}}},
            {"default_category": "Deportes"},
            {"proposal_categories": ["Nacional"]},
            {
                "proposal_categories": [
                    "Nacional",
                    "Nacional",
                    "Nacional",
                    "Internacional",
                    "Deportes",
                ]
            },
            {"formats": {"square": {"width": 10, "height": 10}}},
            {"formats": {"og": {"width": 0, "height": 10}}},
            {"formats": {"og": {"width": 10, "height": 10, "filename": "../x.png"}}},
            {"limits": {"title_max_lines": 0}},
            {"limits": {"desconocido": 1}},
            {"texture": {"intensity": 0.9}},
            {"texture": {"otro": 1}},
            {"desconocido": True},
        ],
    )
    def test_rejects_an_invalid_covers_section(self, tmp_path, covers):
        payload = {"brand": BRAND, "covers": covers}

        with pytest.raises(ConfigurationError):
            load_cover_config(_write(tmp_path, payload))

    def test_rejects_a_missing_brand(self, tmp_path):
        with pytest.raises(ConfigurationError, match="brand"):
            load_cover_config(_write(tmp_path, {}))

    def test_rejects_a_brand_without_colors(self, tmp_path):
        with pytest.raises(ConfigurationError, match="colors"):
            load_cover_config(_write(tmp_path, {"brand": {"name": "X"}}))

    def test_social_config_still_loads_with_the_covers_section(self, tmp_path):
        payload = {
            "brand": BRAND,
            "banners": {
                "templates": {"headline_card": ["x"]},
                "sizes": {"x": [100, 100]},
            },
            "visual_prompts": {
                "treatments": {
                    "photorealistic": "a",
                    "representative": "b",
                    "caricature": "c",
                },
                "treatment_rules": "regla",
                "negative_prompt": "negativo",
                "midjourney_suffix": "--v 8.2",
                "aspect_ratio": "16:9",
            },
            "covers": {},
        }

        config = load_social_config(_write(tmp_path, payload))

        assert "covers" in config


class TestRepositoryConfig:
    """La configuración versionada del repositorio es válida."""

    def test_the_repository_config_has_the_seven_categories(self):
        path = Path(__file__).resolve().parent.parent / "social_config.json"

        covers = load_cover_config(path)["covers"]

        assert set(covers["categories"]) == set(COVER_CATEGORIES)

    def test_the_repository_config_defines_the_two_formats(self):
        path = Path(__file__).resolve().parent.parent / "social_config.json"

        covers = load_cover_config(path)["covers"]

        assert covers["formats"]["og"] == COVER_FORMATS["og"]
        assert covers["formats"]["web"] == COVER_FORMATS["web"]
