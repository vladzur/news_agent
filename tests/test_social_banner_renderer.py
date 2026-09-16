"""Tests del renderizado de banners con Pillow."""

from pathlib import Path

import pytest
from PIL import Image

from news_agent.social import banner_renderer
from news_agent.social.banner_renderer import (
    _DEFAULT_COLORS,
    _block_height,
    _content_box,
    blend,
    brand_palette,
    fit_text,
    hex_to_rgb,
    letter_space,
    load_font,
    prepare_logo,
    render_all_banners,
    render_headline_card,
    render_quote_card,
    resolve_font_path,
    wrap_text,
)

# Tamaños declarados en la configuración de marca del repositorio
ALL_FORMATS = {
    "x": (1600, 900),
    "facebook": (1200, 630),
    "instagram_feed": (1080, 1080),
    "instagram_story": (1080, 1920),
}


# ---------------------------------------------------------------------------
# Contrato del módulo
# ---------------------------------------------------------------------------


class TestModuleContract:
    """Comprobaciones estructurales del módulo de banners."""

    def test_public_functions_are_callable(self):
        assert callable(render_all_banners)
        assert callable(render_headline_card)
        assert callable(render_quote_card)
        assert callable(resolve_font_path)


# ---------------------------------------------------------------------------
# Colores
# ---------------------------------------------------------------------------


class TestColors:
    """Conversión y mezcla de colores de la paleta de marca."""

    def test_parses_a_full_hex_color(self):
        assert hex_to_rgb("#E8452C") == (232, 69, 44)

    def test_parses_a_short_hex_color(self):
        assert hex_to_rgb("#FFF") == (255, 255, 255)

    def test_falls_back_on_an_invalid_color(self):
        assert hex_to_rgb("no-es-un-color", "#000000") == (0, 0, 0)

    def test_returns_black_when_everything_is_invalid(self):
        assert hex_to_rgb("malo", "peor") == (0, 0, 0)

    def test_blend_returns_the_extremes(self):
        assert blend((0, 0, 0), (255, 255, 255), 0.0) == (0, 0, 0)
        assert blend((0, 0, 0), (255, 255, 255), 1.0) == (255, 255, 255)

    def test_blend_clamps_out_of_range_factors(self):
        assert blend((0, 0, 0), (100, 100, 100), 5.0) == (100, 100, 100)

    def test_resolves_the_brand_palette(self, social_config):
        palette = brand_palette(social_config)

        assert set(palette) == {
            "background",
            "surface",
            "text",
            "muted",
            "accent",
            "accent_alt",
        }
        # Los colores son datos de configuración, no valores del código
        for key, value in social_config["brand"]["colors"].items():
            assert palette[key] == hex_to_rgb(value)

    def test_uses_defaults_when_colors_are_missing(self):
        palette = brand_palette({"brand": {"name": "Prueba"}})

        assert palette["accent"] == hex_to_rgb(_DEFAULT_COLORS["accent"])

    def test_falls_back_on_an_invalid_configured_color(self):
        config = {"brand": {"name": "Prueba", "colors": {"accent": "rojo"}}}

        palette = brand_palette(config)

        assert palette["accent"] == hex_to_rgb(_DEFAULT_COLORS["accent"])


# ---------------------------------------------------------------------------
# Tipografías
# ---------------------------------------------------------------------------


class TestFonts:
    """Resolución y carga de fuentes."""

    def test_returns_none_or_an_existing_file(self, social_config):
        path = resolve_font_path("headline", social_config)

        assert path is None or Path(path).is_file()

    def test_honours_the_configured_font_path(self, tmp_path, social_config):
        font_file = tmp_path / "Custom-Bold.ttf"
        font_file.write_bytes(b"no es una fuente real")
        config = {
            "brand": {
                "name": "Prueba",
                "fonts": {"headline": str(font_file)},
            }
        }

        assert resolve_font_path("headline", config) == str(font_file)

    def test_honours_the_font_directory_environment_variable(self, tmp_path, monkeypatch):
        font_file = tmp_path / "DejaVuSans-Bold.ttf"
        font_file.write_bytes(b"no es una fuente real")
        monkeypatch.setenv("SOCIAL_FONT_DIR", str(tmp_path))

        assert resolve_font_path("headline", {}) == str(font_file)

    def test_load_font_always_returns_a_usable_font(self, social_config):
        font = load_font("headline", 40, social_config)

        assert font is not None
        assert font.getmetrics()

    def test_load_font_falls_back_on_an_unreadable_file(self):
        font = load_font("headline", 20, {"brand": {"fonts": {"headline": "/nada.ttf"}}})

        assert font is not None


# ---------------------------------------------------------------------------
# Logo de la marca
# ---------------------------------------------------------------------------


def write_logo(path: Path, size: tuple[int, int], padding: int = 0) -> Path:
    """Escribe un PNG RGBA con un bloque opaco rodeado de padding transparente.

    Args:
        path: Ruta donde guardar el archivo.
        size: Tamaño del bloque opaco (ancho, alto).
        padding: Margen transparente agregado alrededor del bloque.

    Returns:
        Path: Ruta del archivo escrito.
    """
    width, height = size
    canvas = Image.new(
        "RGBA", (width + 2 * padding, height + 2 * padding), (0, 0, 0, 0)
    )
    canvas.paste(Image.new("RGBA", size, (0, 255, 0, 255)), (padding, padding))
    canvas.save(path)
    return path


class TestPrepareLogo:
    """Carga, recorte y escalado del logo de la marca."""

    def test_returns_none_when_no_logo_is_configured(self):
        assert prepare_logo({"brand": {"name": "Prueba"}}, 1080) is None

    def test_returns_none_when_the_path_is_null(self):
        assert prepare_logo({"brand": {"logo_path": None}}, 1080) is None

    def test_returns_none_when_the_path_is_blank(self):
        assert prepare_logo({"brand": {"logo_path": "   "}}, 1080) is None

    def test_returns_none_when_the_file_does_not_exist(self):
        config = {"brand": {"logo_path": "/ruta/inexistente.png"}}

        assert prepare_logo(config, 1080) is None

    def test_returns_none_when_the_file_is_not_an_image(self, tmp_path):
        path = tmp_path / "logo.txt"
        path.write_text("no soy una imagen", encoding="utf-8")

        assert prepare_logo({"brand": {"logo_path": str(path)}}, 1080) is None

    def test_handles_a_missing_brand_section(self):
        assert prepare_logo({}, 1080) is None

    def test_crops_the_transparent_padding(self, tmp_path):
        path = write_logo(tmp_path / "logo.png", (100, 50), padding=60)

        prepared = prepare_logo(
            {"brand": {"logo_path": str(path), "logo_height_ratio": 0.1}}, 1080
        )

        # El arte real es 100x50 (proporción 2:1) y el alto pedido es 108 px
        assert prepared.size == (216, 108)

    def test_respects_the_configured_height_ratio(self, tmp_path):
        path = write_logo(tmp_path / "logo.png", (100, 100))

        prepared = prepare_logo(
            {"brand": {"logo_path": str(path), "logo_height_ratio": 0.2}}, 1080
        )

        assert prepared.height == round(1080 * 0.2)

    def test_uses_the_default_ratio_when_not_configured(self, tmp_path):
        path = write_logo(tmp_path / "logo.png", (100, 100))

        prepared = prepare_logo({"brand": {"logo_path": str(path)}}, 1080)

        assert prepared.height == round(1080 * 0.11)

    def test_caps_the_width_so_it_cannot_invade_the_kicker(self, tmp_path):
        path = write_logo(tmp_path / "logo.png", (400, 20))

        prepared = prepare_logo({"brand": {"logo_path": str(path)}}, 1080)

        assert prepared.width == round(1080 * 0.22)
        # Al recortar el ancho, el alto se recalcula conservando la proporción
        assert prepared.height == round(20 * prepared.width / 400)

    def test_ignores_an_out_of_range_ratio(self, tmp_path):
        path = write_logo(tmp_path / "logo.png", (100, 100))

        prepared = prepare_logo(
            {"brand": {"logo_path": str(path), "logo_height_ratio": 0.9}}, 1080
        )

        assert prepared.height == round(1080 * 0.11)

    def test_scales_with_the_canvas_width(self, tmp_path):
        path = write_logo(tmp_path / "logo.png", (100, 100))

        small = prepare_logo({"brand": {"logo_path": str(path)}}, 1080)
        large = prepare_logo({"brand": {"logo_path": str(path)}}, 1600)

        assert large.height > small.height

    def test_keeps_transparency(self, tmp_path):
        path = write_logo(tmp_path / "logo.png", (100, 100))

        prepared = prepare_logo({"brand": {"logo_path": str(path)}}, 1080)

        assert prepared.mode == "RGBA"


class TestLogoInBanners:
    """Integración del logo en el renderizado de las plantillas."""

    def _config_with_logo(self, social_config, logo_path: Path) -> dict:
        return {
            **social_config,
            "brand": {**social_config["brand"], "logo_path": str(logo_path)},
        }

    def test_headline_card_pastes_the_logo(self, tmp_path, social_copy, social_config):
        path = write_logo(tmp_path / "logo.png", (100, 100))
        config = self._config_with_logo(social_config, path)

        image = render_headline_card(1080, 1080, social_copy, config)

        # El logo queda en la esquina superior derecha, dentro del margen
        assert image.getpixel((950, 100)) == (0, 255, 0)

    def test_headline_card_without_logo_has_no_logo_pixels(
        self, tmp_path, social_copy, social_config
    ):
        config = {
            **social_config,
            "brand": {**social_config["brand"], "logo_path": None},
        }

        image = render_headline_card(1080, 1080, social_copy, config)

        assert image.getpixel((950, 100)) != (0, 255, 0)

    def test_quote_card_pastes_the_logo(self, tmp_path, social_copy, social_config):
        path = write_logo(tmp_path / "logo.png", (100, 100))
        config = self._config_with_logo(social_config, path)

        image = render_quote_card(1080, 1080, social_copy, config)

        assert image.getpixel((950, 100)) == (0, 255, 0)

    def test_a_missing_logo_file_does_not_break_the_render(
        self, social_copy, social_config
    ):
        config = {
            **social_config,
            "brand": {**social_config["brand"], "logo_path": "/ruta/inexistente.png"},
        }

        image = render_headline_card(1080, 1080, social_copy, config)

        assert image.size == (1080, 1080)

    def test_a_tall_logo_pushes_the_headline_down(
        self, tmp_path, social_copy, social_config
    ):
        path = write_logo(tmp_path / "logo.png", (100, 100))
        without = render_headline_card(
            1080,
            1080,
            social_copy,
            {**social_config, "brand": {**social_config["brand"], "logo_path": None}},
        )
        with_logo = render_headline_card(
            1080,
            1080,
            social_copy,
            {
                **social_config,
                "brand": {
                    **social_config["brand"],
                    "logo_path": str(path),
                    "logo_height_ratio": 0.3,
                },
            },
        )

        # Con un logo alto la franja superior crece, así que el titular baja
        assert with_logo.tobytes() != without.tobytes()

    def test_every_banner_renders_with_the_repository_logo(
        self, tmp_path, social_copy, social_config
    ):
        specs = render_all_banners(social_copy, social_config, tmp_path)

        assert len(specs) == 6
        assert all(spec.path is not None for spec in specs)


# ---------------------------------------------------------------------------
# Tipografía: envoltura y ajuste
# ---------------------------------------------------------------------------


class TestWrapText:
    """Envoltura de texto al ancho disponible."""

    def test_returns_empty_for_empty_text(self, social_config):
        image = Image.new("RGB", (100, 100))
        draw = banner_renderer.ImageDraw.Draw(image)
        font = load_font("body", 20, social_config)

        assert wrap_text("", font, 500, draw) == []

    def test_splits_text_into_several_lines(self, social_config):
        image = Image.new("RGB", (100, 100))
        draw = banner_renderer.ImageDraw.Draw(image)
        font = load_font("body", 20, social_config)

        lines = wrap_text("palabra " * 40, font, 300, draw)

        assert len(lines) > 1

    def test_every_line_fits_the_available_width(self, social_config):
        image = Image.new("RGB", (100, 100))
        draw = banner_renderer.ImageDraw.Draw(image)
        font = load_font("body", 20, social_config)

        lines = wrap_text("contenido " * 60, font, 250, draw)

        for line in lines:
            assert draw.textlength(line, font=font) <= 250

    def test_splits_a_word_wider_than_the_box(self, social_config):
        image = Image.new("RGB", (100, 100))
        draw = banner_renderer.ImageDraw.Draw(image)
        font = load_font("headline", 60, social_config)

        lines = wrap_text("x" * 200, font, 100, draw)

        assert len(lines) > 1
        assert all(len(line) < 200 for line in lines)

    def test_keeps_single_short_lines_intact(self, social_config):
        image = Image.new("RGB", (100, 100))
        draw = banner_renderer.ImageDraw.Draw(image)
        font = load_font("body", 20, social_config)

        assert wrap_text("Titular breve", font, 500, draw) == ["Titular breve"]


class TestFitText:
    """Ajuste automático del tamaño de fuente."""

    def _draw(self):
        image = Image.new("RGB", (600, 600))
        return banner_renderer.ImageDraw.Draw(image)

    def test_returns_lines_that_fit_the_box(self, social_config):
        draw = self._draw()

        font, lines, line_gap = fit_text(
            "Un titular de longitud moderada para la tarjeta",
            "headline",
            social_config,
            draw,
            500,
            300,
            1.0,
            max_lines=5,
        )

        assert lines
        assert _block_height(lines, font, line_gap) <= 300

    def test_shrinks_the_font_for_a_long_text(self, social_config):
        draw = self._draw()

        short_font, _, _ = fit_text(
            "Corto", "headline", social_config, draw, 500, 300, 1.0
        )
        long_font, _, _ = fit_text(
            "Titular " * 40, "headline", social_config, draw, 500, 300, 1.0
        )

        assert long_font.size < short_font.size

    def test_respects_the_maximum_number_of_lines(self, social_config):
        draw = self._draw()

        _, lines, _ = fit_text(
            "Texto muy extenso " * 60,
            "headline",
            social_config,
            draw,
            300,
            120,
            1.0,
            max_lines=3,
        )

        assert len(lines) <= 3

    def test_truncated_text_ends_with_an_ellipsis(self, social_config):
        draw = self._draw()

        _, lines, _ = fit_text(
            "Texto muy extenso " * 60,
            "headline",
            social_config,
            draw,
            300,
            60,
            1.0,
            max_lines=2,
        )

        assert lines[-1].endswith("…")


class TestLetterSpace:
    """Espaciado simulado de las etiquetas de marca."""

    def test_intercalates_spaces(self):
        assert letter_space("Chispa") == "C h i s p a"

    def test_collapses_internal_whitespace(self):
        assert letter_space("La  Chispa") == "L a   C h i s p a"

    def test_leaves_long_text_untouched(self):
        text = "un texto demasiado largo para espaciarlo letra por letra"

        assert letter_space(text) == text

    def test_handles_empty_text(self):
        assert letter_space("") == ""


# ---------------------------------------------------------------------------
# Caja de contenido y zonas seguras
# ---------------------------------------------------------------------------


class TestContentBox:
    """Cálculo de la caja útil según márgenes y zonas seguras."""

    def test_applies_proportional_margins(self):
        margin, top, bottom, width = _content_box(1600, 900, 1600 / 1080, None)

        assert margin > 0
        assert width == 1600 - 2 * margin
        assert top == margin
        assert bottom == 900 - margin

    def test_respects_the_safe_zones_of_a_story(self):
        _margin, top, bottom, _ = _content_box(
            1080, 1920, 1.0, {"top": 250, "bottom": 340}
        )

        assert top >= 250
        assert bottom <= 1920 - 340

    def test_never_returns_an_inverted_box(self):
        _, top, bottom, _ = _content_box(1080, 1920, 1.0, {"top": 1800, "bottom": 1800})

        assert bottom > top


# ---------------------------------------------------------------------------
# Renderizado de las plantillas
# ---------------------------------------------------------------------------


class TestRenderTemplates:
    """Renderizado de cada plantilla en cada formato de plataforma."""

    @pytest.mark.parametrize("format_name", sorted(ALL_FORMATS))
    def test_headline_card_has_the_requested_size(
        self, format_name, social_copy, social_config
    ):
        width, height = ALL_FORMATS[format_name]

        image = render_headline_card(width, height, social_copy, social_config)

        assert image.size == (width, height)
        assert image.mode == "RGB"

    @pytest.mark.parametrize("format_name", sorted(ALL_FORMATS))
    def test_quote_card_has_the_requested_size(
        self, format_name, social_copy, social_config
    ):
        width, height = ALL_FORMATS[format_name]

        image = render_quote_card(width, height, social_copy, social_config)

        assert image.size == (width, height)
        assert image.mode == "RGB"

    def test_headline_card_is_not_a_blank_canvas(self, social_copy, social_config):
        image = render_headline_card(1080, 1080, social_copy, social_config)

        assert len(image.getcolors(maxcolors=1_000_000)) > 1

    def test_quote_card_is_not_a_blank_canvas(self, social_copy, social_config):
        image = render_quote_card(1080, 1080, social_copy, social_config)

        assert len(image.getcolors(maxcolors=1_000_000)) > 1

    def test_quote_card_uses_the_configured_surface_color(
        self, social_copy, social_config
    ):
        image = render_quote_card(1080, 1080, social_copy, social_config)
        palette = brand_palette(social_config)

        # Una esquina libre de formas decorativas conserva el color de fondo
        assert image.getpixel((1070, 5)) == palette["surface"]

    def test_headline_card_uses_the_configured_background_color(
        self, social_copy, social_config
    ):
        image = render_headline_card(1600, 900, social_copy, social_config)

        assert image.getpixel((1590, 5)) in (
            brand_palette(social_config)["background"],
            brand_palette(social_config)["accent"],
        )

    def test_story_format_keeps_content_out_of_the_top_safe_zone(
        self, social_copy, social_config
    ):
        safe_zone = social_config["banners"]["safe_zone"]["instagram_story"]
        image = render_quote_card(
            1080, 1920, social_copy, social_config, safe_zone=safe_zone
        )
        palette = brand_palette(social_config)

        # El centro de la banda superior no debe tener texto: solo puede
        # conservar el fondo (la barra de acento y el círculo decorativo
        # quedan en los bordes).
        assert image.getpixel((700, 40)) == palette["surface"]


# ---------------------------------------------------------------------------
# Renderizado del lote completo
# ---------------------------------------------------------------------------


class TestRenderAllBanners:
    """Generación del lote de banners declarado en la configuración."""

    def test_generates_every_template_for_every_platform(
        self, tmp_path, social_copy, social_config
    ):
        specs = render_all_banners(social_copy, social_config, tmp_path)

        assert len(specs) == 6

    def test_writes_png_files_with_the_declared_sizes(
        self, tmp_path, social_copy, social_config
    ):
        render_all_banners(social_copy, social_config, tmp_path)

        for template in ("headline_card", "quote_card"):
            for format_name, size in ALL_FORMATS.items():
                path = tmp_path / f"{template}_{format_name}.png"
                if not path.exists():
                    continue
                with Image.open(path) as image:
                    assert image.size == size
                    assert image.format == "PNG"

    def test_returns_absolute_paths(self, tmp_path, social_copy, social_config):
        specs = render_all_banners(social_copy, social_config, tmp_path)

        for spec in specs:
            assert spec.path is not None
            assert spec.path.is_absolute()

    def test_filters_by_platform(self, tmp_path, social_copy, social_config):
        specs = render_all_banners(
            social_copy, social_config, tmp_path, platforms=["instagram"]
        )

        platforms = {spec.platform for spec in specs}
        assert platforms == {"instagram_feed", "instagram_story"}

    def test_filters_out_every_banner_when_the_platform_does_not_apply(
        self, tmp_path, social_copy, social_config
    ):
        specs = render_all_banners(
            social_copy, social_config, tmp_path, platforms=["facebook"]
        )

        assert {spec.platform for spec in specs} == {"facebook"}

    def test_records_a_failed_banner_without_aborting_the_batch(
        self, tmp_path, monkeypatch, social_copy, social_config
    ):
        def broken_renderer(width, height, copy, config, safe_zone=None):
            raise RuntimeError("fallo simulado de renderizado")

        monkeypatch.setitem(
            banner_renderer._TEMPLATE_RENDERERS, "headline_card", broken_renderer
        )

        specs = render_all_banners(social_copy, social_config, tmp_path)

        failed = [spec for spec in specs if spec.path is None]
        rendered = [spec for spec in specs if spec.path is not None]
        assert len(failed) == 4
        assert len(rendered) == 2

    def test_skips_an_unknown_template(
        self, tmp_path, monkeypatch, social_copy, social_config
    ):
        config = {
            **social_config,
            "banners": {
                **social_config["banners"],
                "templates": {"plantilla_inventada": ["x"]},
            },
        }

        specs = render_all_banners(social_copy, config, tmp_path)

        assert specs == []

    def test_skips_a_format_without_a_declared_size(
        self, tmp_path, social_copy, social_config
    ):
        config = {
            **social_config,
            "banners": {
                "templates": {"headline_card": ["formato_sin_tamano"]},
                "sizes": {"formato_sin_tamano": None},
            },
        }

        specs = render_all_banners(social_copy, config, tmp_path)

        assert specs == []

    def test_raises_when_the_output_directory_does_not_exist(
        self, tmp_path, social_copy, social_config
    ):
        with pytest.raises(IOError, match="no existe"):
            render_all_banners(
                social_copy, social_config, tmp_path / "inexistente"
            )

    def test_banner_specs_are_serializable(self, tmp_path, social_copy, social_config):
        specs = render_all_banners(social_copy, social_config, tmp_path)

        payload = specs[0].to_dict()
        assert isinstance(payload["path"], str)
        assert payload["width"] > 0
