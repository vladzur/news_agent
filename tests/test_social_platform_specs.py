"""Tests de la resolución de límites por plataforma."""

import pytest

from news_agent.social.platform_specs import (
    ALL_PLATFORMS,
    parse_platforms,
    platform_of_format,
    platform_spec,
    platform_specs,
    thread_bounds,
)


class TestPlatformOfFormat:
    """Derivación de la plataforma a partir del nombre del formato."""

    def test_extracts_the_platform_prefix(self):
        assert platform_of_format("instagram_feed") == "instagram"
        assert platform_of_format("instagram_story") == "instagram"

    def test_returns_the_name_when_there_is_no_suffix(self):
        assert platform_of_format("x") == "x"
        assert platform_of_format("facebook") == "facebook"

    def test_normalizes_case_and_spaces(self):
        assert platform_of_format(" Instagram_Feed ") == "instagram"


class TestPlatformSpecs:
    """Combinación de los defaults del código con la configuración de marca."""

    def test_returns_the_three_supported_platforms(self):
        assert set(platform_specs({})) == set(ALL_PLATFORMS)

    def test_applies_the_overrides_from_config(self):
        config = {"platforms": {"x": {"max_chars": 500, "max_hashtags": 9}}}

        specs = platform_specs(config)

        assert specs["x"]["max_chars"] == 500
        assert specs["x"]["max_hashtags"] == 9

    def test_ignores_unknown_keys(self):
        config = {"platforms": {"x": {"max_chars": 400, "inventado": "si"}}}

        specs = platform_specs(config)

        assert "inventado" not in specs["x"]

    def test_ignores_non_positive_and_non_numeric_values(self):
        config = {"platforms": {"x": {"max_chars": 0, "max_hashtags": "muchos"}}}

        specs = platform_specs(config)

        assert specs["x"]["max_chars"] > 0
        assert isinstance(specs["x"]["max_hashtags"], int)

    def test_ignores_a_malformed_platforms_section(self):
        specs = platform_specs({"platforms": "no es un diccionario"})

        assert set(specs) == set(ALL_PLATFORMS)

    def test_handles_a_none_config(self):
        assert set(platform_specs(None)) == set(ALL_PLATFORMS)

    def test_config_overrides_do_not_mutate_the_defaults(self):
        config = {"platforms": {"x": {"max_chars": 999}}}

        first = platform_specs(config)
        second = platform_specs({})

        assert first["x"]["max_chars"] == 999
        assert second["x"]["max_chars"] != 999


class TestPlatformSpec:
    """Acceso a los límites de una plataforma concreta."""

    def test_returns_the_requested_platform(self):
        spec = platform_spec({}, "instagram")

        assert spec["label"] == "Instagram"
        assert spec["caption_max_chars"] > 0

    def test_raises_for_an_unknown_platform(self):
        with pytest.raises(ValueError, match="no soportada"):
            platform_spec({}, "tiktok")


class TestThreadBounds:
    """Límites de largo del hilo de X."""

    def test_returns_the_configured_bounds(self):
        minimum, maximum = thread_bounds({"thread_min_tweets": 3, "thread_max_tweets": 9})

        assert (minimum, maximum) == (3, 9)

    def test_orders_an_inverted_range(self):
        minimum, maximum = thread_bounds({"thread_min_tweets": 8, "thread_max_tweets": 4})

        assert (minimum, maximum) == (4, 8)

    def test_never_returns_bounds_below_one(self):
        minimum, maximum = thread_bounds({"thread_min_tweets": -5, "thread_max_tweets": 0})

        assert minimum >= 1
        assert maximum >= 1


class TestParsePlatforms:
    """Interpretación de la lista de plataformas del CLI."""

    def test_parses_a_comma_separated_list(self):
        assert parse_platforms("x,instagram") == ["x", "instagram"]

    def test_returns_every_platform_by_default(self):
        assert parse_platforms(None) == list(ALL_PLATFORMS)
        assert parse_platforms("   ") == list(ALL_PLATFORMS)

    def test_normalizes_case_and_spaces(self):
        assert parse_platforms(" X , Facebook ") == ["x", "facebook"]

    def test_removes_duplicates_and_keeps_the_editorial_order(self):
        assert parse_platforms("instagram,x,x") == ["x", "instagram"]

    def test_raises_for_an_unknown_platform(self):
        with pytest.raises(ValueError, match="desconocida"):
            parse_platforms("x,tiktok")

    def test_ignores_empty_chunks(self):
        assert parse_platforms("x,,facebook") == ["x", "facebook"]
