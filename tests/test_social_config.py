"""Tests de la configuración del subsistema de RRSS."""

import json
from pathlib import Path

import pytest

from news_agent.config import (
    DEFAULT_SOCIAL_OUTPUT_DIR,
    SOCIAL_BANNER_BASE_WIDTH,
    SOCIAL_CONFIG_PATH,
    SOCIAL_FONT_BOLD_CANDIDATES,
    SOCIAL_FONT_REGULAR_CANDIDATES,
    SOCIAL_IG_MAX_HASHTAGS,
    SOCIAL_JSON_MAX_RETRIES,
    SOCIAL_MAX_HOOKS,
    SOCIAL_MIN_ARTICLE_WORDS,
    SOCIAL_MIN_HOOKS,
    SOCIAL_X_MAX_CHARS,
    SOCIAL_X_THREAD_MAX_TWEETS,
    SOCIAL_X_THREAD_MIN_TWEETS,
    ConfigurationError,
    load_social_config,
)

# Raíz del repositorio, para resolver las rutas de los recursos de marca
REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Constantes del subsistema
# ---------------------------------------------------------------------------


class TestSocialConstants:
    """Valores por defecto del subsistema de RRSS."""

    def test_x_character_limit_matches_the_platform(self):
        assert SOCIAL_X_MAX_CHARS == 280

    def test_thread_bounds_are_coherent(self):
        assert 1 <= SOCIAL_X_THREAD_MIN_TWEETS <= SOCIAL_X_THREAD_MAX_TWEETS

    def test_hook_bounds_are_coherent(self):
        assert 1 <= SOCIAL_MIN_HOOKS <= SOCIAL_MAX_HOOKS

    def test_retries_are_bounded(self):
        assert 0 <= SOCIAL_JSON_MAX_RETRIES <= 5

    def test_article_guard_is_positive(self):
        assert SOCIAL_MIN_ARTICLE_WORDS > 0

    def test_banner_base_width_is_positive(self):
        assert SOCIAL_BANNER_BASE_WIDTH > 0

    def test_output_dir_and_config_path_are_declared(self):
        assert DEFAULT_SOCIAL_OUTPUT_DIR
        assert SOCIAL_CONFIG_PATH.endswith(".json")

    def test_font_candidates_are_absolute_ttf_paths(self):
        for candidate in SOCIAL_FONT_BOLD_CANDIDATES:
            assert candidate.endswith(".ttf")
            assert candidate.startswith("/")
        assert SOCIAL_FONT_REGULAR_CANDIDATES

    def test_instagram_hashtag_cap_is_generous(self):
        assert SOCIAL_IG_MAX_HASHTAGS >= 10


# ---------------------------------------------------------------------------
# Carga del archivo de marca
# ---------------------------------------------------------------------------


class TestLoadSocialConfig:
    """Carga y validación del archivo de configuración de marca."""

    def test_loads_the_repository_config(self):
        config = load_social_config(
            Path(__file__).resolve().parent.parent / SOCIAL_CONFIG_PATH
        )

        assert set(config) >= {"brand", "platforms", "banners", "visual_prompts"}

    def test_accepts_an_explicit_path(self, config_file):
        config = load_social_config(config_file)

        assert config["brand"]["name"]

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ConfigurationError, match="no encontrado"):
            load_social_config(tmp_path / "inexistente.json")

    def test_invalid_json_raises(self, tmp_path):
        path = tmp_path / "roto.json"
        path.write_text("{ no es json", encoding="utf-8")

        with pytest.raises(ConfigurationError, match="JSON válido"):
            load_social_config(path)

    def test_non_object_json_raises(self, tmp_path):
        path = tmp_path / "lista.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")

        with pytest.raises(ConfigurationError, match="objeto JSON"):
            load_social_config(path)

    def test_missing_section_raises(self, tmp_path, social_config):
        payload = {key: value for key, value in social_config.items() if key != "brand"}
        path = tmp_path / "sin-brand.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="'brand'"):
            load_social_config(path)

    def test_section_with_wrong_type_raises(self, tmp_path, social_config):
        payload = {**social_config, "banners": "no es un objeto"}
        path = tmp_path / "banners-malos.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="debe ser un objeto JSON"):
            load_social_config(path)

    def test_brand_without_name_raises(self, tmp_path, social_config):
        payload = {**social_config, "brand": {"colors": {"accent": "#FFF"}}}
        path = tmp_path / "sin-nombre.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="'name'"):
            load_social_config(path)

    def test_brand_without_colors_raises(self, tmp_path, social_config):
        payload = {**social_config, "brand": {"name": "Prueba"}}
        path = tmp_path / "sin-colores.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="'colors'"):
            load_social_config(path)

    def test_banners_without_templates_raises(self, tmp_path, social_config):
        payload = {**social_config, "banners": {"sizes": {"x": [100, 100]}}}
        path = tmp_path / "sin-plantillas.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="'templates'"):
            load_social_config(path)

    def test_banners_without_sizes_raises(self, tmp_path, social_config):
        payload = {**social_config, "banners": {"templates": {"a": ["x"]}}}
        path = tmp_path / "sin-tamanos.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="'sizes'"):
            load_social_config(path)

    def test_invalid_size_raises(self, tmp_path, social_config):
        payload = {
            **social_config,
            "banners": {
                "templates": {"headline_card": ["x"]},
                "sizes": {"x": [1600]},
            },
        }
        path = tmp_path / "tamano-malo.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="ancho, alto"):
            load_social_config(path)

    def test_negative_size_raises(self, tmp_path, social_config):
        payload = {
            **social_config,
            "banners": {
                "templates": {"headline_card": ["x"]},
                "sizes": {"x": [1600, -900]},
            },
        }
        path = tmp_path / "tamano-negativo.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="enteros positivos"):
            load_social_config(path)

    def test_template_pointing_to_an_unknown_format_raises(
        self, tmp_path, social_config
    ):
        payload = {
            **social_config,
            "banners": {
                "templates": {"headline_card": ["formato_inexistente"]},
                "sizes": {"x": [100, 100]},
            },
        }
        path = tmp_path / "formato-malo.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="no está declarado"):
            load_social_config(path)

    def test_template_with_an_empty_list_raises(self, tmp_path, social_config):
        payload = {
            **social_config,
            "banners": {"templates": {"headline_card": []}, "sizes": {"x": [1, 1]}},
        }
        path = tmp_path / "plantilla-vacia.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="lista de formatos"):
            load_social_config(path)


# ---------------------------------------------------------------------------
# Coherencia entre el archivo de marca y el código
# ---------------------------------------------------------------------------


class TestRepositoryConfigCoherence:
    """El archivo versionado debe satisfacer lo que el código espera leer."""

    def test_every_banner_format_has_a_declared_size(self, social_config):
        sizes = social_config["banners"]["sizes"]

        for targets in social_config["banners"]["templates"].values():
            for target in targets:
                assert target in sizes

    def test_declares_the_four_platform_formats(self, social_config):
        assert set(social_config["banners"]["sizes"]) == {
            "x",
            "facebook",
            "instagram_feed",
            "instagram_story",
        }

    def test_declares_the_headline_and_quote_templates(self, social_config):
        templates = social_config["banners"]["templates"]

        assert "headline_card" in templates
        assert "quote_card" in templates

    def test_declares_the_three_platform_limits(self, social_config):
        assert set(social_config["platforms"]) == {"x", "facebook", "instagram"}

    def test_platform_limits_match_the_code_defaults(self, social_config):
        assert social_config["platforms"]["x"]["max_chars"] == SOCIAL_X_MAX_CHARS
        assert (
            social_config["platforms"]["x"]["thread_min_tweets"]
            == SOCIAL_X_THREAD_MIN_TWEETS
        )
        assert social_config["platforms"]["instagram"]["max_hashtags"] == (
            SOCIAL_IG_MAX_HASHTAGS
        )

    def test_visual_prompts_section_has_every_required_key(self, social_config):
        visual = social_config["visual_prompts"]

        for key in (
            "style",
            "negative_prompt",
            "midjourney_suffix",
            "aspect_ratios",
            "default_settings",
        ):
            assert key in visual

    def test_negative_prompt_excludes_text(self, social_config):
        negative = social_config["visual_prompts"]["negative_prompt"].lower()

        assert "text" in negative
        assert "letters" in negative
        assert "watermark" in negative

    def test_aspect_ratios_cover_every_platform(self, social_config):
        platforms = set()
        for spec in social_config["visual_prompts"]["aspect_ratios"].values():
            platforms.update(spec["platforms"])

        assert platforms == {"x", "facebook", "instagram_feed", "instagram_story"}

    def test_story_safe_zones_are_declared(self, social_config):
        safe_zone = social_config["banners"]["safe_zone"]["instagram_story"]

        assert safe_zone["top"] > 0
        assert safe_zone["bottom"] > 0

    def test_brand_declares_the_palette_and_an_optional_logo(self, social_config):
        brand = social_config["brand"]

        assert brand["name"]
        assert brand["handle"].startswith("@")
        assert "logo_path" in brand
        for color in ("background", "text", "accent"):
            assert brand["colors"][color].startswith("#")

    def test_the_configured_logo_file_exists(self, social_config):
        logo_path = social_config["brand"]["logo_path"]

        assert logo_path, "La marca debería declarar la ruta de su logo"
        assert (REPO_ROOT / logo_path).is_file()
