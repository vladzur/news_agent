"""Tests del renderizado de portadas editoriales con Pillow."""

import copy

import pytest
from PIL import Image

from news_agent.cover.models import CoverContent, CoverFormat
from news_agent.cover.renderer import (
    CoverRenderError,
    _resolve_colors,
    contrast_ratio,
    relative_luminance,
    render_cover,
    save_cover_image,
)
from news_agent.cover.specs import cover_specs
from news_agent.social.banner_renderer import brand_palette

OG_FORMAT = CoverFormat("og", 1200, 630, "portada_og.png")
WEB_FORMAT = CoverFormat("web", 1600, 900, "portada_web.png")


def _content(treatment: str = "text_first", **overrides) -> CoverContent:
    """Construye un contenido de portada para las pruebas.

    Args:
        treatment: Tratamiento a probar.
        **overrides: Campos que se quieren reemplazar.

    Returns:
        CoverContent: Contenido listo para renderizar.
    """
    base = CoverContent(
        title="Cierre de la escuela rural: 42 familias quedan sin matrícula",
        category="Nacional",
        treatment=treatment,
        treatment_label="Editorial tipográfica",
        deck=(
            "La municipalidad de Villarrica confirmó el cierre de la escuela "
            "rural y las familias anunciaron un recurso ante la Contraloría."
        ),
        quote="No vamos a permitir que nos arranquen la escuela",
        figure="42 familias",
        caption=(
            "El concejo municipal aprobó el cierre con 56 votos a favor y "
            "seis en contra."
        ),
        byline="Por La Chispa Sur",
        alt_text="Portada de prueba",
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


class TestRenderFormats:
    """Renderizado de los formatos y tratamientos."""

    @pytest.mark.parametrize("format_spec", [OG_FORMAT, WEB_FORMAT])
    def test_renders_the_requested_size(self, social_config, format_spec):
        image, warnings = render_cover(
            _content(), format_spec, social_config, cover_specs(social_config)
        )

        assert image.size == (format_spec.width, format_spec.height)
        assert image.mode == "RGB"
        assert warnings == []

    @pytest.mark.parametrize("treatment", ["text_first", "quote", "data"])
    def test_renders_every_treatment(self, social_config, treatment):
        image, _ = render_cover(
            _content(treatment),
            WEB_FORMAT,
            social_config,
            cover_specs(social_config),
        )

        colors = image.getcolors(maxcolors=1_000_000)
        assert colors is not None
        assert len(colors) > 20

    def test_paints_the_top_accent_bar(self, social_config):
        image, _ = render_cover(
            _content(), WEB_FORMAT, social_config, cover_specs(social_config)
        )

        top_pixel = image.getpixel((WEB_FORMAT.width // 2, 2))
        background_pixel = image.getpixel((WEB_FORMAT.width // 2, 40))

        assert top_pixel != background_pixel

    def test_rejects_an_invalid_format(self, social_config):
        broken = CoverFormat("rotto", 0, 630, "portada.png")

        with pytest.raises(CoverRenderError, match="dimensiones"):
            render_cover(_content(), broken, social_config, cover_specs(social_config))


class TestRenderResilience:
    """Casos límite del renderizado."""

    def test_a_long_title_is_ellipsized_with_a_warning(self, social_config):
        content = _content(title="Palabra " * 80)

        image, warnings = render_cover(
            content, OG_FORMAT, social_config, cover_specs(social_config)
        )

        assert image.size == (OG_FORMAT.width, OG_FORMAT.height)
        assert any("titular" in warning.lower() for warning in warnings)

    def test_a_missing_logo_does_not_break_the_cover(self, social_config):
        config = copy.deepcopy(social_config)
        config["brand"]["logo_path"] = "assets/no-existe.png"

        image, _ = render_cover(
            _content("quote"), OG_FORMAT, config, cover_specs(config)
        )

        assert image.size == (OG_FORMAT.width, OG_FORMAT.height)

    def test_a_missing_serif_font_falls_back_to_sans(
        self, social_config, monkeypatch
    ):
        monkeypatch.delenv("SOCIAL_FONT_DIR", raising=False)
        monkeypatch.setattr(
            "news_agent.cover.renderer.COVER_FONT_SERIF_CANDIDATES", ()
        )
        config = copy.deepcopy(social_config)
        config["brand"].setdefault("fonts", {})["quote"] = None

        image, warnings = render_cover(
            _content("quote"), WEB_FORMAT, config, cover_specs(config)
        )

        assert image.size == (WEB_FORMAT.width, WEB_FORMAT.height)
        assert any("serif" in warning.lower() for warning in warnings)

    def test_a_low_contrast_accent_is_adjusted(self, social_config):
        config = copy.deepcopy(social_config)
        config["covers"]["categories"]["Nacional"]["accent"] = "#101010"

        _, warnings = render_cover(
            _content(), OG_FORMAT, config, cover_specs(config)
        )

        assert any("contrast" in warning.lower() for warning in warnings)

    def test_a_low_contrast_accent_is_clarified(self, social_config):
        config = copy.deepcopy(social_config)
        config["covers"]["categories"]["Nacional"]["accent"] = "#101010"
        specs = cover_specs(config)
        warnings: list[str] = []

        _, accent, _ = _resolve_colors(
            "Nacional", brand_palette(config), specs, warnings
        )

        assert relative_luminance(accent) > relative_luminance((16, 16, 16))


class TestColorHelpers:
    """Contraste y luminancia."""

    def test_black_and_white_have_maximum_contrast(self):
        assert contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21)

    def test_luminance_grows_with_brightness(self):
        assert relative_luminance((0, 0, 0)) < relative_luminance((255, 255, 255))


class TestSave:
    """Escritura de las portadas."""

    def test_saves_a_png(self, social_config, tmp_path):
        image, _ = render_cover(
            _content(), OG_FORMAT, social_config, cover_specs(social_config)
        )
        path = tmp_path / "portada.png"

        saved = save_cover_image(image, path)

        assert saved == path.resolve()
        assert Image.open(path).size == (OG_FORMAT.width, OG_FORMAT.height)
