"""Renderizado del carrusel vertical de Instagram.

El carrusel es una secuencia autocontenida de cinco piezas verticales: la
portada, tres slides que resumen los puntos centrales del artículo y una firma
de marca. Las cinco comparten la misma retícula, la misma paleta y el mismo
encabezado y pie que los banners, para que la publicación se lea como una sola
pieza y no como cinco imágenes sueltas.

El formato lo declara ``social_config.json`` en la sección
``instagram_carousel``. El renderizador rechaza cualquier formato que no sea
4:5 vertical y de Instagram. La configuración del repositorio usa 1080×1350,
el formato vertical del feed, más legible que el 9:16 de un reel.
"""

import logging
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from ..config import (
    SOCIAL_BANNER_BASE_WIDTH,
    SOCIAL_IG_CAROUSEL_FORMAT,
    SOCIAL_IG_CAROUSEL_SLIDES,
)
from .banner_renderer import (
    base_size,
    block_height,
    brand_name,
    brand_palette,
    content_box,
    draw_background,
    draw_lines,
    fit_text,
    letter_space,
    line_height,
    load_font,
    prepare_logo,
)
from .models import InstagramSlide, InstagramSlideSpec, SocialCopy

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Nombres de archivo y geometría
# ---------------------------------------------------------------------------
COVER_FILE_NAME = "01_cover.png"
SIGNATURE_FILE_TEMPLATE = "{position:02d}_signature.png"
SUMMARY_FILE_TEMPLATE = "{position:02d}_point_{number}.png"

# Tope de ancho de lectura del texto. En 1080 px deja márgenes generosos para
# que las líneas no se estiren y el slide se lea en el móvil.
_MAX_TEXT_WIDTH_RATIO = 0.86

# Geometría de la firma: logo, nombre y datos de contacto.
_SIGNATURE_LOGO_HEIGHT_RATIO = 0.24
_SIGNATURE_LOGO_MAX_WIDTH_RATIO = 0.46


class InstagramRenderError(Exception):
    """Excepción para errores estructurales del carrusel de Instagram."""


# ---------------------------------------------------------------------------
# Resolución del formato
# ---------------------------------------------------------------------------


def resolve_carousel_layout(
    config: dict[str, Any],
) -> tuple[str, int, int, dict[str, Any] | None]:
    """Resuelve el formato 4:5 vertical, su tamaño y sus zonas seguras.

    Args:
        config: Configuración de marca cargada desde ``social_config.json``.

    Returns:
        tuple[str, int, int, dict | None]: Nombre del formato, ancho, alto y
        zonas seguras declaradas.

    Raises:
        InstagramRenderError: Si la configuración no declara un formato 4:5
                              vertical de Instagram utilizable.
    """
    carousel = config.get("instagram_carousel")
    carousel = carousel if isinstance(carousel, dict) else {}
    format_name = carousel.get("format", SOCIAL_IG_CAROUSEL_FORMAT)
    format_name = (
        str(format_name).strip() if isinstance(format_name, str) else ""
    )
    if not format_name:
        format_name = SOCIAL_IG_CAROUSEL_FORMAT

    banners = config.get("banners")
    banners = banners if isinstance(banners, dict) else {}
    sizes = banners.get("sizes")
    sizes = sizes if isinstance(sizes, dict) else {}
    size = sizes.get(format_name)

    if (
        not format_name.startswith("instagram_")
        or not isinstance(size, (list, tuple))
        or len(size) != 2
    ):
        raise InstagramRenderError(
            "El carrusel necesita un formato de Instagram declarado en "
            f"'banners.sizes'; se recibió '{format_name}'."
        )

    width, height = int(size[0]), int(size[1])
    if width <= 0 or height <= 0 or height <= width:
        raise InstagramRenderError(
            "El formato del carrusel debe ser vertical; "
            f"'{format_name}' mide {width}x{height}."
        )

    if width * 5 != height * 4:
        raise InstagramRenderError(
            "El formato del carrusel debe ser 4:5 vertical; "
            f"'{format_name}' mide {width}x{height}."
        )

    safe_zones = banners.get("safe_zone")
    safe_zone = (
        safe_zones.get(format_name) if isinstance(safe_zones, dict) else None
    )

    return format_name, width, height, safe_zone


# ---------------------------------------------------------------------------
# Primitivas compartidas por las cinco piezas
# ---------------------------------------------------------------------------


def _text_width(content_width: int) -> int:
    """Calcula el ancho de lectura del texto.

    Args:
        content_width: Ancho útil del lienzo.

    Returns:
        int: Ancho máximo de una línea de texto.
    """
    return max(round(content_width * _MAX_TEXT_WIDTH_RATIO), 1)


def _draw_header(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    config: dict[str, Any],
    palette: dict[str, tuple[int, int, int]],
    scale: float,
    margin: int,
    top: int,
    logo: Image.Image | None,
) -> int:
    """Dibuja el encabezado de marca y devuelve su alto.

    Args:
        image: Lienzo donde pegar el logo.
        draw: Lienzo de dibujo.
        config: Configuración de marca.
        palette: Paleta resuelta.
        scale: Factor de escala respecto del ancho de referencia.
        margin: Margen lateral.
        top: Coordenada vertical superior del encabezado.
        logo: Logo ya escalado, o None.

    Returns:
        int: Alto ocupado por el encabezado, para que el contenido empiece
        siempre por debajo.
    """
    rule_height = max(round(6 * scale), 2)
    rule_width = max(round(72 * scale), 8)
    draw.rectangle(
        (margin, top, margin + rule_width, top + rule_height),
        fill=palette["accent"],
    )

    kicker_gap = max(round(18 * scale), 4)
    kicker_font = load_font("kicker", base_size("kicker", scale), config)
    kicker_height = line_height(kicker_font)
    draw.text(
        (margin, top + rule_height + kicker_gap),
        letter_space(brand_name(config).upper()),
        font=kicker_font,
        fill=palette["accent_alt"],
    )

    if logo is not None:
        image.paste(logo, (image.width - margin - logo.width, top), logo)

    return max(rule_height + kicker_gap + kicker_height, logo.height if logo else 0)


def _draw_footer(
    draw: ImageDraw.ImageDraw,
    config: dict[str, Any],
    palette: dict[str, tuple[int, int, int]],
    scale: float,
    width: int,
    margin: int,
    bottom: int,
    index: int,
    total: int,
) -> None:
    """Dibuja el pie de marca con el contador de slides.

    Args:
        draw: Lienzo de dibujo.
        config: Configuración de marca.
        palette: Paleta resuelta.
        scale: Factor de escala respecto del ancho de referencia.
        width: Ancho del lienzo.
        margin: Margen lateral.
        bottom: Borde inferior de la caja útil.
        index: Posición del slide, desde 1.
        total: Cantidad total de slides.
    """
    brand = config.get("brand")
    brand = brand if isinstance(brand, dict) else {}
    parts = [
        str(value).strip()
        for value in (brand.get("handle"), brand.get("website"))
        if isinstance(value, str) and value.strip()
    ]
    if not parts:
        parts = [brand_name(config)]

    font = load_font("body", base_size("body", scale), config)
    footer_height = line_height(font)
    baseline_y = bottom - footer_height

    separator_y = baseline_y - max(round(24 * scale), 4)
    draw.rectangle(
        (margin, separator_y, width - margin, separator_y + max(round(1 * scale), 1)),
        fill=palette["surface"],
    )

    square = max(round(14 * scale), 4)
    center_y = baseline_y + footer_height // 2
    draw.rectangle(
        (
            margin,
            center_y - square // 2,
            margin + square,
            center_y + square // 2,
        ),
        fill=palette["accent"],
    )
    draw.text(
        (margin + square + round(14 * scale), baseline_y),
        letter_space("   ·   ".join(parts)),
        font=font,
        fill=palette["muted"],
    )

    counter = f"{index:02d} / {total:02d}"
    counter_width = draw.textlength(counter, font=font)
    draw.text(
        (width - margin - counter_width, baseline_y),
        counter,
        font=font,
        fill=palette["accent_alt"],
    )


def _draw_progress(
    draw: ImageDraw.ImageDraw,
    palette: dict[str, tuple[int, int, int]],
    scale: float,
    center_x: int,
    y: int,
    index: int,
    total: int,
) -> None:
    """Dibuja los puntos de progreso de los slides de resumen.

    Args:
        draw: Lienzo de dibujo.
        palette: Paleta resuelta.
        scale: Factor de escala respecto del ancho de referencia.
        center_x: Centro horizontal del grupo de puntos.
        y: Coordenada vertical de los puntos.
        index: Slide actual, desde 1.
        total: Cantidad de slides de resumen.
    """
    radius = max(round(7 * scale), 3)
    gap = max(round(18 * scale), 6)
    total_width = total * radius * 2 + (total - 1) * gap
    cursor = center_x - total_width // 2

    for position in range(1, total + 1):
        box = (cursor, y, cursor + radius * 2, y + radius * 2)
        if position == index:
            draw.ellipse(box, fill=palette["accent"])
        else:
            draw.ellipse(box, outline=palette["muted"], width=max(round(2 * scale), 1))
        cursor += radius * 2 + gap


def _draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: Any,
    color: tuple[int, int, int],
    center_x: int,
    y: int,
    line_gap: int,
) -> None:
    """Dibuja un bloque de líneas centrado horizontalmente.

    Args:
        draw: Lienzo de dibujo.
        lines: Líneas a dibujar.
        font: Fuente del bloque.
        color: Color del texto.
        center_x: Centro horizontal del bloque.
        y: Coordenada vertical de inicio.
        line_gap: Separación adicional entre líneas, en píxeles.
    """
    cursor = y
    for line in lines:
        line_width = draw.textlength(line, font=font)
        draw.text(
            (center_x - line_width / 2, cursor),
            line,
            font=font,
            fill=color,
        )
        cursor += line_height(font) + line_gap


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: Any,
    palette: dict[str, tuple[int, int, int]],
    scale: float,
    x: int,
    y: int,
) -> tuple[int, int]:
    """Dibuja una etiqueta con fondo de acento y devuelve su tamaño.

    Args:
        draw: Lienzo de dibujo.
        text: Texto de la etiqueta.
        font: Fuente de la etiqueta.
        palette: Paleta resuelta.
        scale: Factor de escala respecto del ancho de referencia.
        x: Coordenada horizontal de inicio.
        y: Coordenada vertical de inicio.

    Returns:
        tuple[int, int]: Ancho y alto de la etiqueta dibujada.
    """
    text_width = draw.textlength(text, font=font)
    padding_x = max(round(18 * scale), 4)
    padding_y = max(round(10 * scale), 3)
    width = max(round(text_width + 2 * padding_x), 1)
    height = max(round(line_height(font) + 2 * padding_y), 1)
    radius = max(round(6 * scale), 2)

    draw.rounded_rectangle(
        (x, y, x + width, y + height),
        radius=radius,
        fill=palette["accent"],
    )
    draw.text(
        (x + padding_x, y + padding_y),
        text,
        font=font,
        fill=palette["text"],
    )
    return width, height


# ---------------------------------------------------------------------------
# Plantillas
# ---------------------------------------------------------------------------


def render_cover_slide(
    width: int,
    height: int,
    copy: SocialCopy,
    config: dict[str, Any],
    safe_zone: dict[str, Any] | None = None,
) -> Image.Image:
    """Renderiza la portada del carrusel con la estética del banner actual.

    Args:
        width: Ancho del lienzo en píxeles.
        height: Alto del lienzo en píxeles.
        copy: Copys del artículo, de donde se toma el titular y el gancho.
        config: Configuración de marca.
        safe_zone: Zonas seguras de la plataforma, si corresponde.

    Returns:
        Image.Image: Portada renderizada en modo RGB.
    """
    palette = brand_palette(config)
    scale = width / SOCIAL_BANNER_BASE_WIDTH
    margin, top, bottom, content_width = content_box(
        width, height, scale, safe_zone
    )
    text_width = _text_width(content_width)

    image = Image.new("RGB", (width, height), palette["background"])
    draw = ImageDraw.Draw(image)
    draw_background(draw, width, height, palette, scale, surface=False)

    logo = prepare_logo(config, width)
    header_height = _draw_header(
        image, draw, config, palette, scale, margin, top, logo
    )
    content_top = top + header_height + max(round(48 * scale), 8)

    footer_font = load_font("body", base_size("body", scale), config)
    footer_y = bottom - line_height(footer_font)

    # Etiqueta que anuncia el formato del carrusel
    label_font = load_font("kicker", base_size("kicker", scale), config)
    _, label_height = _draw_pill(
        draw,
        f"{SOCIAL_IG_CAROUSEL_SLIDES} CLAVES",
        label_font,
        palette,
        scale,
        margin,
        content_top,
    )

    # Llamado a deslizar, fijado sobre el pie
    cta_font = load_font("body", base_size("body", scale), config)
    cta_gap = max(round(26 * scale), 4)
    cta_y = footer_y - line_height(cta_font) - cta_gap
    cta_text = "Desliza para leer los puntos clave  \u2192"
    draw.text((margin, cta_y), cta_text, font=cta_font, fill=palette["accent_alt"])

    title_top = content_top + label_height + max(round(34 * scale), 6)

    # Bajada: se mide antes del titular para reservarle su espacio
    deck = copy.hook or ""
    deck_font, deck_lines, deck_gap = fit_text(
        deck,
        "deck",
        config,
        draw,
        text_width,
        max(round(height * 0.14), 1),
        scale,
        max_lines=4,
    )
    deck_height = block_height(deck_lines, deck_font, deck_gap) if deck_lines else 0
    deck_margin = max(round(28 * scale), 4) if deck_lines else 0

    title_height = max(cta_y - title_top - deck_height - deck_margin, 1)
    title_font, title_lines, title_gap = fit_text(
        copy.title,
        "headline",
        config,
        draw,
        text_width,
        title_height,
        scale,
        max_lines=6,
    )
    draw_lines(
        draw, title_lines, title_font, palette["text"], margin, title_top, title_gap
    )

    if deck_lines:
        deck_y = title_top + block_height(title_lines, title_font, title_gap)
        deck_y += deck_margin
        deck_y = min(deck_y, cta_y - deck_height)
        draw_lines(
            draw, deck_lines, deck_font, palette["muted"], margin, deck_y, deck_gap
        )

    _draw_footer(
        draw,
        config,
        palette,
        scale,
        width,
        margin,
        bottom,
        index=1,
        total=SOCIAL_IG_CAROUSEL_SLIDES + 2,
    )

    return image


def render_summary_slide(
    width: int,
    height: int,
    copy: SocialCopy,
    slide: InstagramSlide,
    number: int,
    config: dict[str, Any],
    safe_zone: dict[str, Any] | None = None,
) -> Image.Image:
    """Renderiza un slide de resumen con la retícula compartida.

    Args:
        width: Ancho del lienzo en píxeles.
        height: Alto del lienzo en píxeles.
        copy: Copys del artículo; se conserva por simetría con el resto de las
              plantillas y para el pie de marca.
        slide: Slide de resumen que se va a dibujar.
        number: Número del punto, desde 1.
        config: Configuración de marca.
        safe_zone: Zonas seguras de la plataforma, si corresponde.

    Returns:
        Image.Image: Slide renderizado en modo RGB.
    """
    palette = brand_palette(config)
    scale = width / SOCIAL_BANNER_BASE_WIDTH
    margin, top, bottom, content_width = content_box(
        width, height, scale, safe_zone
    )
    text_width = _text_width(content_width)

    image = Image.new("RGB", (width, height), palette["background"])
    draw = ImageDraw.Draw(image)
    draw_background(draw, width, height, palette, scale, surface=False)

    logo = prepare_logo(config, width)
    header_height = _draw_header(
        image, draw, config, palette, scale, margin, top, logo
    )
    content_top = top + header_height + max(round(42 * scale), 8)

    footer_font = load_font("body", base_size("body", scale), config)
    footer_y = bottom - line_height(footer_font)

    # Número del punto: identifica la serie sin ocupar el lugar de un titular.
    number_font = load_font(
        "attribution", base_size("attribution", scale) + 12, config
    )
    number_text = f"{number:02d}"
    number_width = draw.textlength(number_text, font=number_font)
    number_height = line_height(number_font)
    draw.text(
        (margin, content_top),
        number_text,
        font=number_font,
        fill=palette["accent"],
    )

    rule_y = content_top + number_height // 2
    rule_x = margin + number_width + max(round(20 * scale), 6)
    draw.rectangle(
        (
            rule_x,
            rule_y,
            rule_x + max(round(56 * scale), 8),
            rule_y + max(round(3 * scale), 2),
        ),
        fill=palette["accent_alt"],
    )

    text_top = content_top + number_height + max(round(28 * scale), 6)

    # Tarjeta de dato: se reserva antes del texto para que no invada el cuerpo
    figure_font = load_font("deck", base_size("deck", scale) + 8, config)
    figure_label_font = load_font("kicker", base_size("kicker", scale), config)
    figure_card_height = 0
    figure_card_y = 0
    if slide.figure:
        figure_card_height = max(round(150 * scale), 40)
        figure_card_y = footer_y - max(round(48 * scale), 8) - figure_card_height

    body_bottom = (
        figure_card_y - max(round(24 * scale), 6)
        if slide.figure
        else footer_y - max(round(40 * scale), 8)
    )
    body_height = max(body_bottom - text_top, 1)

    body_font, body_lines, body_gap = fit_text(
        slide.text,
        "slide_body",
        config,
        draw,
        text_width,
        body_height,
        scale,
        max_lines=8,
    )
    block = block_height(body_lines, body_font, body_gap)
    body_y = text_top + max((body_height - block) // 2, 0)
    draw_lines(
        draw, body_lines, body_font, palette["text"], margin, body_y, body_gap
    )

    if slide.figure:
        draw.rounded_rectangle(
            (
                margin,
                figure_card_y,
                width - margin,
                figure_card_y + figure_card_height,
            ),
            radius=max(round(12 * scale), 3),
            fill=palette["surface"],
        )
        card_rule_width = max(round(8 * scale), 3)
        draw.rectangle(
            (
                margin,
                figure_card_y,
                margin + card_rule_width,
                figure_card_y + figure_card_height,
            ),
            fill=palette["accent_alt"],
        )
        draw.text(
            (margin + max(round(32 * scale), 6), figure_card_y + max(round(24 * scale), 4)),
            letter_space("DATO CLAVE"),
            font=figure_label_font,
            fill=palette["accent_alt"],
        )
        _, figure_lines, figure_gap = fit_text(
            slide.figure,
            "deck",
            config,
            draw,
            text_width - max(round(32 * scale), 6),
            max(round(90 * scale), 20),
            scale,
            max_lines=2,
        )
        draw_lines(
            draw,
            figure_lines,
            figure_font,
            palette["text"],
            margin + max(round(32 * scale), 6),
            figure_card_y + max(round(70 * scale), 8),
            figure_gap,
        )

    progress_y = footer_y - max(round(36 * scale), 8)
    _draw_progress(
        draw,
        palette,
        scale,
        width // 2,
        progress_y,
        index=number,
        total=SOCIAL_IG_CAROUSEL_SLIDES,
    )

    _draw_footer(
        draw,
        config,
        palette,
        scale,
        width,
        margin,
        bottom,
        index=number + 1,
        total=SOCIAL_IG_CAROUSEL_SLIDES + 2,
    )

    return image


def render_signature_slide(
    width: int,
    height: int,
    copy: SocialCopy,
    config: dict[str, Any],
    safe_zone: dict[str, Any] | None = None,
) -> Image.Image:
    """Renderiza la firma de La Chispa Sur como cierre del carrusel.

    Args:
        width: Ancho del lienzo en píxeles.
        height: Alto del lienzo en píxeles.
        copy: Copys del artículo; se conserva por simetría con las demás
              plantillas.
        config: Configuración de marca.
        safe_zone: Zonas seguras de la plataforma, si corresponde.

    Returns:
        Image.Image: Firma renderizada en modo RGB.
    """
    palette = brand_palette(config)
    scale = width / SOCIAL_BANNER_BASE_WIDTH
    margin, top, bottom, content_width = content_box(
        width, height, scale, safe_zone
    )
    text_width = _text_width(content_width)

    image = Image.new("RGB", (width, height), palette["background"])
    draw = ImageDraw.Draw(image)
    draw_background(draw, width, height, palette, scale, surface=False)

    logo = prepare_logo(config, width)
    header_height = _draw_header(
        image, draw, config, palette, scale, margin, top, logo
    )
    content_top = top + header_height + max(round(48 * scale), 8)

    footer_font = load_font("body", base_size("body", scale), config)
    footer_y = bottom - line_height(footer_font)
    available = max(footer_y - content_top - max(round(36 * scale), 6), 1)

    brand = config.get("brand")
    brand = brand if isinstance(brand, dict) else {}
    tagline = brand.get("tagline")
    tagline = tagline.strip() if isinstance(tagline, str) else ""
    website = brand.get("website")
    website = website.strip() if isinstance(website, str) else ""
    handle = brand.get("handle")
    handle = handle.strip() if isinstance(handle, str) else ""

    name = brand_name(config).upper()

    # Se miden todos los bloques antes de dibujar para centrar el conjunto
    signature_logo = prepare_logo(
        config,
        width,
        height_ratio=_SIGNATURE_LOGO_HEIGHT_RATIO,
        max_width_ratio=_SIGNATURE_LOGO_MAX_WIDTH_RATIO,
    )
    logo_height = signature_logo.height if signature_logo else 0

    name_font, name_lines, name_gap = fit_text(
        name,
        "signature_name",
        config,
        draw,
        text_width,
        max(round(160 * scale), 1),
        scale,
        max_lines=2,
    )
    name_height = block_height(name_lines, name_font, name_gap)

    rule_width = max(round(120 * scale), 12)
    rule_height = max(round(8 * scale), 2)

    tagline_font, tagline_lines, tagline_gap = fit_text(
        tagline,
        "signature_body",
        config,
        draw,
        text_width,
        max(round(130 * scale), 1),
        scale,
        max_lines=2,
    )
    tagline_height = (
        block_height(tagline_lines, tagline_font, tagline_gap)
        if tagline_lines
        else 0
    )

    cta_font = load_font("body", base_size("body", scale), config)
    cta_text = "Lee la nota completa en"
    cta_height = line_height(cta_font)

    web_font = load_font("signature_web", base_size("signature_web", scale), config)
    web_height = line_height(web_font)

    handle_font = load_font("attribution", base_size("attribution", scale), config)
    handle_height = line_height(handle_font) if handle else 0

    gap_logo = max(round(36 * scale), 6)
    gap_name = max(round(28 * scale), 6)
    gap_rule = max(round(26 * scale), 6)
    gap_tagline = max(round(52 * scale), 8)
    gap_web = max(round(12 * scale), 3)
    gap_handle = max(round(10 * scale), 3)

    total_height = (
        logo_height
        + (gap_logo if logo_height else 0)
        + name_height
        + gap_name
        + rule_height
        + (gap_rule if tagline_height else 0)
        + tagline_height
        + (gap_tagline if website else 0)
        + cta_height
        + gap_web
        + (web_height if website else 0)
        + (gap_handle if handle else 0)
        + handle_height
    )
    cursor = content_top + max((available - total_height) // 2, 0)
    center_x = width // 2

    if signature_logo is not None:
        image.paste(
            signature_logo,
            (center_x - signature_logo.width // 2, cursor),
            signature_logo,
        )
        cursor += logo_height + gap_logo

    _draw_centered_lines(
        draw, name_lines, name_font, palette["text"], center_x, cursor, name_gap
    )
    cursor += name_height + gap_name

    draw.rectangle(
        (
            center_x - rule_width // 2,
            cursor,
            center_x + rule_width // 2,
            cursor + rule_height,
        ),
        fill=palette["accent"],
    )
    cursor += rule_height
    if tagline_height:
        cursor += gap_rule
        _draw_centered_lines(
            draw,
            tagline_lines,
            tagline_font,
            palette["accent_alt"],
            center_x,
            cursor,
            tagline_gap,
        )
        cursor += tagline_height

    if website:
        cursor += gap_tagline
        cta_width = draw.textlength(cta_text, font=cta_font)
        draw.text(
            (center_x - cta_width / 2, cursor),
            cta_text,
            font=cta_font,
            fill=palette["muted"],
        )
        cursor += cta_height + gap_web

        web_width = draw.textlength(website, font=web_font)
        draw.text(
            (center_x - web_width / 2, cursor),
            website,
            font=web_font,
            fill=palette["accent_alt"],
        )
        cursor += web_height

    if handle:
        cursor += gap_handle
        handle_width = draw.textlength(handle, font=handle_font)
        draw.text(
            (center_x - handle_width / 2, cursor),
            handle,
            font=handle_font,
            fill=palette["muted"],
        )

    _draw_footer(
        draw,
        config,
        palette,
        scale,
        width,
        margin,
        bottom,
        index=SOCIAL_IG_CAROUSEL_SLIDES + 2,
        total=SOCIAL_IG_CAROUSEL_SLIDES + 2,
    )

    return image


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def render_instagram_carousel(
    copy: SocialCopy,
    config: dict[str, Any],
    output_dir: str | Path,
) -> list[InstagramSlideSpec]:
    """Renderiza y guarda la portada, los tres resúmenes y la firma.

    Las cinco piezas se escriben juntas en el directorio recibido. Un slide
    que falla no interrumpe el resto: se registra sin ruta y el manifiesto lo
    deja como pendiente.

    Args:
        copy: Copys del artículo, con los slides de resumen ya validados.
        config: Configuración de marca cargada desde ``social_config.json``.
        output_dir: Subdirectorio exclusivo del carrusel.

    Returns:
        list[InstagramSlideSpec]: Especificaciones de los slides generados.

    Raises:
        OSError: Si el directorio de salida no existe.
        InstagramRenderError: Si el formato configurado no es 4:5 vertical.
    """
    output_path = Path(output_dir)
    if not output_path.exists():
        raise OSError(f"El directorio de salida no existe: {output_path.resolve()}")

    format_name, width, height, safe_zone = resolve_carousel_layout(config)
    total = SOCIAL_IG_CAROUSEL_SLIDES + 2
    specs: list[InstagramSlideSpec] = []

    slides: list[InstagramSlide] = list(copy.instagram.slides)
    if len(slides) < SOCIAL_IG_CAROUSEL_SLIDES:
        logger.warning(
            "El carrusel de Instagram tiene %d slide(s) de resumen; se esperaban "
            "%d. Se renderizan los disponibles.",
            len(slides),
            SOCIAL_IG_CAROUSEL_SLIDES,
        )

    def _render(
        index: int,
        kind: str,
        text: str,
        file_name: str,
        renderer: Any,
    ) -> None:
        """Renderiza una pieza y registra su resultado.

        Args:
            index: Posición en el carrusel.
            kind: Tipo de slide.
            text: Texto principal del slide.
            file_name: Nombre del archivo PNG.
            renderer: Callable que devuelve la imagen.
        """
        destination = output_path / file_name
        try:
            image = renderer()
            image.save(destination, format="PNG", optimize=True)
        except Exception as exc:  # noqa: BLE001 - un slide no debe romper el lote
            logger.error(
                "No se pudo renderizar el slide %s (%dx%d): %s",
                file_name,
                width,
                height,
                exc,
            )
            specs.append(
                InstagramSlideSpec(
                    index=index,
                    kind=kind,
                    text=text,
                    width=width,
                    height=height,
                    path=None,
                )
            )
            return

        logger.info(
            "Slide de Instagram generado: %s (%dx%d, %s).",
            destination.name,
            width,
            height,
            format_name,
        )
        specs.append(
            InstagramSlideSpec(
                index=index,
                kind=kind,
                text=text,
                width=width,
                height=height,
                path=destination.resolve(),
            )
        )

    _render(
        1,
        "cover",
        copy.title,
        COVER_FILE_NAME,
        lambda: render_cover_slide(width, height, copy, config, safe_zone=safe_zone),
    )

    for number, slide in enumerate(slides, start=1):
        _render(
            number + 1,
            "summary",
            slide.text,
            SUMMARY_FILE_TEMPLATE.format(position=number + 1, number=number),
            lambda slide=slide, number=number: render_summary_slide(
                width,
                height,
                copy,
                slide,
                number,
                config,
                safe_zone=safe_zone,
            ),
        )

    _render(
        total,
        "signature",
        brand_name(config),
        SIGNATURE_FILE_TEMPLATE.format(position=total),
        lambda: render_signature_slide(
            width, height, copy, config, safe_zone=safe_zone
        ),
    )

    return specs
