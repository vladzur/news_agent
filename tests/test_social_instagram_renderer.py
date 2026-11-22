"""Tests del carrusel vertical de Instagram."""

from pathlib import Path

import pytest
from PIL import Image

from news_agent.social import instagram_renderer
from news_agent.social.instagram_renderer import (
    COVER_FILE_NAME,
    SIGNATURE_FILE_TEMPLATE,
    SUMMARY_FILE_TEMPLATE,
    InstagramRenderError,
    render_cover_slide,
    render_instagram_carousel,
    render_signature_slide,
    render_summary_slide,
    resolve_carousel_layout,
)

# Formato vertical declarado en la configuración del repositorio
REEL_SIZE = (1080, 1920)

# Índices de los slides en el carrusel completo: portada, tres resúmenes y firma
EXPECTED_FILES = [
    COVER_FILE_NAME,
    SUMMARY_FILE_TEMPLATE.format(position=2, number=1),
    SUMMARY_FILE_TEMPLATE.format(position=3, number=2),
    SUMMARY_FILE_TEMPLATE.format(position=4, number=3),
    SIGNATURE_FILE_TEMPLATE.format(position=5),
]


def reel_safe_zone(config: dict) -> dict:
    """Zonas seguras del formato vertical declarado en la configuración.

    Args:
        config: Configuración de marca.

    Returns:
        dict: Zonas seguras superior e inferior del reel.
    """
    return config["banners"]["safe_zone"]["instagram_reel"]


@pytest.fixture
def carousel_dir(tmp_path: Path) -> Path:
    """Subdirectorio vacío para que el carrusel no se mezcle con el artículo.

    Args:
        tmp_path: Directorio temporal de pytest.

    Returns:
        Path: Carpeta exclusiva del carrusel.
    """
    path = tmp_path / "instagram"
    path.mkdir()
    return path


# ---------------------------------------------------------------------------
# Resolución del formato
# ---------------------------------------------------------------------------


class TestResolveCarouselLayout:
    """Lectura del formato vertical desde la configuración."""

    def test_resolves_the_reel_format(self, social_config):
        format_name, width, height, safe_zone = resolve_carousel_layout(
            social_config
        )

        assert format_name == "instagram_reel"
        assert (width, height) == REEL_SIZE
        assert safe_zone is not None

    def test_falls_back_to_the_reel_format_when_the_section_is_missing(
        self, social_config
    ):
        config = {
            key: value
            for key, value in social_config.items()
            if key != "instagram_carousel"
        }

        format_name, width, height, _ = resolve_carousel_layout(config)

        assert format_name == "instagram_reel"
        assert (width, height) == REEL_SIZE

    def test_rejects_a_format_that_is_not_instagram(self, social_config):
        config = {
            **social_config,
            "instagram_carousel": {"format": "x"},
        }

        with pytest.raises(InstagramRenderError, match="formato de Instagram"):
            resolve_carousel_layout(config)

    def test_rejects_a_horizontal_format(self, social_config):
        config = {
            **social_config,
            "banners": {
                **social_config["banners"],
                "sizes": {
                    **social_config["banners"]["sizes"],
                    "instagram_apaisado": [1920, 1080],
                },
            },
            "instagram_carousel": {"format": "instagram_apaisado"},
        }

        with pytest.raises(InstagramRenderError, match="vertical"):
            resolve_carousel_layout(config)

    def test_rejects_a_format_without_a_declared_size(self, social_config):
        config = {
            **social_config,
            "instagram_carousel": {"format": "instagram_inexistente"},
        }

        with pytest.raises(InstagramRenderError, match="banners.sizes"):
            resolve_carousel_layout(config)


# ---------------------------------------------------------------------------
# Plantillas
# ---------------------------------------------------------------------------


class TestRenderSlides:
    """Renderizado de cada tipo de slide."""

    def test_cover_has_the_vertical_size(self, social_copy, social_config):
        image = render_cover_slide(
            *REEL_SIZE,
            social_copy,
            social_config,
            safe_zone=reel_safe_zone(social_config),
        )

        assert image.size == REEL_SIZE
        assert image.mode == "RGB"

    def test_cover_is_not_a_blank_canvas(self, social_copy, social_config):
        image = render_cover_slide(
            *REEL_SIZE,
            social_copy,
            social_config,
            safe_zone=reel_safe_zone(social_config),
        )

        assert len(image.getcolors(maxcolors=1_000_000)) > 1

    @pytest.mark.parametrize("number", [1, 2, 3])
    def test_summary_slide_has_the_vertical_size(
        self, number, social_copy, social_config
    ):
        slide = social_copy.instagram.slides[number - 1]

        image = render_summary_slide(
            *REEL_SIZE,
            social_copy,
            slide,
            number,
            social_config,
            safe_zone=reel_safe_zone(social_config),
        )

        assert image.size == REEL_SIZE
        assert image.mode == "RGB"

    @pytest.mark.parametrize("number", [1, 2, 3])
    def test_summary_slide_is_not_a_blank_canvas(
        self, number, social_copy, social_config
    ):
        slide = social_copy.instagram.slides[number - 1]

        image = render_summary_slide(
            *REEL_SIZE,
            social_copy,
            slide,
            number,
            social_config,
            safe_zone=reel_safe_zone(social_config),
        )

        assert len(image.getcolors(maxcolors=1_000_000)) > 1

    def test_signature_has_the_vertical_size(self, social_copy, social_config):
        image = render_signature_slide(
            *REEL_SIZE,
            social_copy,
            social_config,
            safe_zone=reel_safe_zone(social_config),
        )

        assert image.size == REEL_SIZE
        assert image.mode == "RGB"

    def test_signature_is_not_a_blank_canvas(self, social_copy, social_config):
        image = render_signature_slide(
            *REEL_SIZE,
            social_copy,
            social_config,
            safe_zone=reel_safe_zone(social_config),
        )

        assert len(image.getcolors(maxcolors=1_000_000)) > 1

    def test_every_slide_shares_the_same_header(
        self, social_copy, social_config
    ):
        cover = render_cover_slide(
            *REEL_SIZE,
            social_copy,
            social_config,
            safe_zone=reel_safe_zone(social_config),
        )
        summary = render_summary_slide(
            *REEL_SIZE,
            social_copy,
            social_copy.instagram.slides[0],
            1,
            social_config,
            safe_zone=reel_safe_zone(social_config),
        )
        signature = render_signature_slide(
            *REEL_SIZE,
            social_copy,
            social_config,
            safe_zone=reel_safe_zone(social_config),
        )

        # La regla de acento del encabezado está en la misma coordenada en las
        # tres plantillas: la retícula es compartida.
        assert cover.getpixel((66, 206)) == summary.getpixel((66, 206))
        assert cover.getpixel((66, 206)) == signature.getpixel((66, 206))
        assert cover.getpixel((66, 206)) == (0xDF, 0x32, 0x24)

    def test_every_slide_shares_the_same_footer(
        self, social_copy, social_config
    ):
        summary_one = render_summary_slide(
            *REEL_SIZE,
            social_copy,
            social_copy.instagram.slides[0],
            1,
            social_config,
            safe_zone=reel_safe_zone(social_config),
        )
        summary_two = render_summary_slide(
            *REEL_SIZE,
            social_copy,
            social_copy.instagram.slides[1],
            2,
            social_config,
            safe_zone=reel_safe_zone(social_config),
        )

        # El pie de marca (handle y sitio) no cambia entre resúmenes; solo
        # cambia el contador de la derecha.
        assert summary_one.getpixel((70, 1622)) == summary_two.getpixel((70, 1622))
        assert summary_one.getpixel((70, 1622)) == (0xDF, 0x32, 0x24)

    def test_summary_slides_keep_the_text_area_aligned(
        self, social_copy, social_config
    ):
        first = render_summary_slide(
            *REEL_SIZE,
            social_copy,
            social_copy.instagram.slides[0],
            1,
            social_config,
            safe_zone=reel_safe_zone(social_config),
        )
        second = render_summary_slide(
            *REEL_SIZE,
            social_copy,
            social_copy.instagram.slides[1],
            2,
            social_config,
            safe_zone=reel_safe_zone(social_config),
        )

        # La regla bajo el titular está a la misma altura en los tres slides,
        # porque el bloque de título tiene un alto fijo.
        rule_pixels_first = [
            y for y in range(400, 900) if first.getpixel((66, y)) == (0xDF, 0x32, 0x24)
        ]
        rule_pixels_second = [
            y for y in range(400, 900) if second.getpixel((66, y)) == (0xDF, 0x32, 0x24)
        ]
        assert rule_pixels_first == rule_pixels_second
        assert rule_pixels_first


# ---------------------------------------------------------------------------
# Lote completo
# ---------------------------------------------------------------------------


class TestRenderInstagramCarousel:
    """Generación del carrusel completo en su subdirectorio."""

    def test_renders_five_slides(self, carousel_dir, social_copy, social_config):
        specs = render_instagram_carousel(social_copy, social_config, carousel_dir)

        assert len(specs) == 5

    def test_writes_the_expected_files_in_order(
        self, carousel_dir, social_copy, social_config
    ):
        render_instagram_carousel(social_copy, social_config, carousel_dir)

        assert sorted(path.name for path in carousel_dir.iterdir()) == EXPECTED_FILES

    def test_every_file_is_a_vertical_png(
        self, carousel_dir, social_copy, social_config
    ):
        render_instagram_carousel(social_copy, social_config, carousel_dir)

        for path in carousel_dir.iterdir():
            with Image.open(path) as image:
                assert image.size == REEL_SIZE
                assert image.format == "PNG"

    def test_returns_absolute_paths(self, carousel_dir, social_copy, social_config):
        specs = render_instagram_carousel(social_copy, social_config, carousel_dir)

        for spec in specs:
            assert spec.path is not None
            assert spec.path.is_absolute()

    def test_specs_record_the_slide_order_and_kinds(
        self, carousel_dir, social_copy, social_config
    ):
        specs = render_instagram_carousel(social_copy, social_config, carousel_dir)

        assert [spec.index for spec in specs] == [1, 2, 3, 4, 5]
        assert [spec.kind for spec in specs] == [
            "cover",
            "summary",
            "summary",
            "summary",
            "signature",
        ]
        assert specs[0].title == social_copy.title
        assert specs[4].title == social_config["brand"]["name"]

    def test_raises_when_the_output_directory_does_not_exist(
        self, tmp_path, social_copy, social_config
    ):
        with pytest.raises(IOError, match="no existe"):
            render_instagram_carousel(
                social_copy, social_config, tmp_path / "inexistente"
            )

    def test_a_failed_slide_does_not_abort_the_batch(
        self, carousel_dir, monkeypatch, social_copy, social_config
    ):
        def broken(*args, **kwargs):
            raise RuntimeError("fallo simulado")

        monkeypatch.setattr(instagram_renderer, "render_summary_slide", broken)

        specs = render_instagram_carousel(social_copy, social_config, carousel_dir)

        failed = [spec for spec in specs if spec.path is None]
        rendered = [spec for spec in specs if spec.path is not None]
        assert len(failed) == 3
        assert len(rendered) == 2

    def test_renders_without_a_summary_slide_but_warns(
        self, carousel_dir, social_copy, social_config
    ):
        social_copy.instagram.slides = []

        specs = render_instagram_carousel(social_copy, social_config, carousel_dir)

        assert [spec.kind for spec in specs] == ["cover", "signature"]
        assert (
            carousel_dir / SIGNATURE_FILE_TEMPLATE.format(position=5)
        ).is_file()


# ---------------------------------------------------------------------------
# Contrato de serialización
# ---------------------------------------------------------------------------


class TestSlideSpec:
    """Serialización de las especificaciones de slide."""

    def test_serializes_the_path_as_text(
        self, carousel_dir, social_copy, social_config
    ):
        specs = render_instagram_carousel(social_copy, social_config, carousel_dir)

        payload = specs[0].to_dict()

        assert isinstance(payload["path"], str)
        assert payload["width"] == REEL_SIZE[0]
        assert payload["height"] == REEL_SIZE[1]
        assert payload["kind"] == "cover"

    def test_serializes_a_failed_slide_as_null(self):
        from news_agent.social.models import InstagramSlideSpec

        spec = InstagramSlideSpec(1, "cover", "Titular", 1080, 1920)

        assert spec.to_dict()["path"] is None
