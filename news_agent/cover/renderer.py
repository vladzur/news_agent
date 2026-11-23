"""Renderizado determinista de portadas editoriales con Pillow.

Tres tratamientos comparten la misma identidad visual: la portada tipográfica
para la mayoría de las notas, la cita destacada para las columnas de opinión y
el dato duro para las notas que giran en torno a una cifra. El diseño se
parametriza por el ancho de la pieza, de modo que la cabecera 16:9 del sitio y
la tarjeta 1200x630 de ``og:image`` usan una sola implementación.
"""

import logging
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from ..config import (
    COVER_BASE_WIDTH,
    COVER_FONT_SERIF_CANDIDATES,
)
from ..social.banner_renderer import (
    base_size,
    blend,
    block_height,
    brand_name,
    brand_palette,
    draw_lines,
    fit_text,
    hex_to_rgb,
    letter_space,
    line_height,
    load_font,
    prepare_logo,
    resolve_font_path,
    wrap_text,
)
from .models import CoverContent, CoverFormat

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class CoverRenderError(Exception):
    """Excepción para errores al renderizar una portada."""


# ---------------------------------------------------------------------------
# Proporciones del diseño
# ---------------------------------------------------------------------------
_LOGO_HEIGHT_RATIO = 0.075
_LOGO_MAX_WIDTH_RATIO = 0.20
_MARGIN_RATIO = 0.06
_SERIF_BASE_SIZE = 76
_SERIF_MIN_SIZE = 34
_QUOTE_GLYPH_RATIO = 0.07
_AVATAR_RATIO = 0.035
_AVATAR_MIN_SIZE = 16


# ---------------------------------------------------------------------------
# Color y contraste
# ---------------------------------------------------------------------------


def _channel_luminance(value: int) -> float:
    """Convierte un canal sRGB a luminancia relativa.

    Args:
        value: Componente entre 0 y 255.

    Returns:
        float: Luminancia lineal del canal.
    """
    component = value / 255.0
    if component <= 0.03928:
        return component / 12.92
    return ((component + 0.055) / 1.055) ** 2.4


def relative_luminance(color: tuple[int, int, int]) -> float:
    """Calcula la luminancia relativa de un color RGB.

    Args:
        color: Color RGB.

    Returns:
        float: Luminancia entre 0 y 1.
    """
    return (
        0.2126 * _channel_luminance(color[0])
        + 0.7152 * _channel_luminance(color[1])
        + 0.0722 * _channel_luminance(color[2])
    )


def contrast_ratio(
    first: tuple[int, int, int],
    second: tuple[int, int, int],
) -> float:
    """Calcula el contraste entre dos colores.

    Args:
        first: Primer color RGB.
        second: Segundo color RGB.

    Returns:
        float: Contraste según WCAG (1 a 21).
    """
    first_lum = relative_luminance(first)
    second_lum = relative_luminance(second)
    lighter, darker = sorted((first_lum, second_lum), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _resolve_colors(
    category: str,
    palette: dict[str, tuple[int, int, int]],
    specs: dict[str, Any],
    warnings: list[str],
) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    """Resuelve fondo, acento legible y gris apagado de una portada.

    Args:
        category: Sección oficial.
        palette: Paleta de marca resuelta.
        specs: Especificaciones de portada.
        warnings: Lista donde se registran los ajustes de contraste.

    Returns:
        tuple: Fondo, acento y gris apagado, todos RGB.
    """
    category_spec = specs.get("categories", {}).get(category, {})
    accent = hex_to_rgb(
        str(category_spec.get("accent", "#DF3224")),
        "#DF3224",
    )
    intensity = float(specs.get("texture", {}).get("intensity", 0.09))

    background = blend(palette["background"], accent, intensity)
    if relative_luminance(background) > 0.25:
        warnings.append(
            f"El fondo teñido de la sección {category} era demasiado claro: "
            "se usa el fondo de marca."
        )
        background = palette["background"]

    readable_accent = accent
    if contrast_ratio(accent, background) < 3.0:
        warnings.append(
            f"El acento de la sección {category} no contrastaba con el fondo: "
            "se aclara para mantener la legibilidad."
        )
        readable_accent = blend(accent, (255, 255, 255), 0.45)

    muted = palette["muted"]
    if contrast_ratio(muted, background) < 4.5:
        muted = blend(muted, (255, 255, 255), 0.30)

    return background, readable_accent, muted


# ---------------------------------------------------------------------------
# Fondo y patrón de marca
# ---------------------------------------------------------------------------


def _draw_spark_pattern(
    image: Image.Image,
    width: int,
    height: int,
    accent: tuple[int, int, int],
    intensity: float,
    scale: float,
) -> None:
    """Dibuja el patrón radial de "chispa" sobre el fondo.

    Las líneas nacen fuera del lienzo, en la esquina inferior derecha, para
    sugerir un destello sin competir con el texto. Se dibujan en una capa
    aparte y se pegan con transparencia.

    Args:
        image: Lienzo RGB.
        width: Ancho del lienzo.
        height: Alto del lienzo.
        accent: Color de acento.
        intensity: Intensidad configurada de la textura.
        scale: Factor de escala del diseño.
    """
    alpha = max(round(26 * (intensity / 0.09)), 0)
    if alpha <= 0:
        return

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    color = (*accent, alpha)
    line_width = max(round(2 * scale), 1)
    center_x = width * 0.94
    center_y = height * 1.08
    radius = max(width, height) * 1.5

    for step in range(22):
        angle = math.radians(188 + step * 7.0)
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        draw.line(
            (center_x, center_y, x, y),
            fill=color,
            width=line_width,
        )

    for factor in (0.52, 0.72, 0.92):
        ring = width * factor
        draw.ellipse(
            (
                center_x - ring,
                center_y - ring,
                center_x + ring,
                center_y + ring,
            ),
            outline=color,
            width=line_width,
        )

    image.paste(overlay, (0, 0), overlay)


# ---------------------------------------------------------------------------
# Tipografía serif de la cita
# ---------------------------------------------------------------------------


def _resolve_serif_path(config: dict[str, Any]) -> tuple[str | None, bool]:
    """Resuelve la fuente serif para la cita de opinión.

    Orden de preferencia: la fuente declarada en ``brand.fonts.quote``, el
    directorio de ``SOCIAL_FONT_DIR`` y las rutas habituales del sistema. Si
    no hay una serif disponible, se devuelve la sans en negrita como respaldo
    y se informa que no es serif.

    Args:
        config: Configuración de marca.

    Returns:
        tuple[str | None, bool]: Ruta de la fuente y si es realmente serif.
    """
    brand = config.get("brand")
    brand = brand if isinstance(brand, dict) else {}
    fonts = brand.get("fonts")
    configured = fonts.get("quote") if isinstance(fonts, dict) else None

    candidates: list[str] = []
    if isinstance(configured, str) and configured.strip():
        return configured.strip(), True

    env_dir = os.environ.get("SOCIAL_FONT_DIR")
    if env_dir:
        base = Path(env_dir)
        for name in (
            "DejaVuSerif-Bold.ttf",
            "LiberationSerif-Bold.ttf",
            "NotoSerif-Bold.ttf",
        ):
            candidates.append(str(base / name))
        if base.is_dir():
            candidates.extend(
                str(item) for item in sorted(base.glob("*Serif*.ttf"))
            )

    candidates.extend(COVER_FONT_SERIF_CANDIDATES)

    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate, True

    return resolve_font_path("cover_quote", config), False


@lru_cache(maxsize=32)
def _load_serif_font(
    path: str | None, size: int
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Carga una fuente serif, con la fuente por defecto como último recurso.

    Args:
        path: Ruta de la fuente.
        size: Tamaño en píxeles.

    Returns:
        Fuente lista para dibujar.
    """
    if path:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError as exc:
            logger.warning("No se pudo cargar la fuente serif %s: %s", path, exc)

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow antiguo sin parámetro de tamaño
        return ImageFont.load_default()


def _fit_serif_text(
    text: str,
    config: dict[str, Any],
    draw: ImageDraw.ImageDraw,
    max_width: int,
    max_height: int,
    scale: float,
    max_lines: int,
) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, list[str], int]:
    """Ajusta la cita serif al espacio disponible.

    Es el equivalente de ``fit_text`` para la familia serif: reduce el tamaño
    de dos en dos píxeles y, si ni con el mínimo entra, recorta con puntos
    suspensivos.

    Args:
        text: Texto de la cita.
        config: Configuración de marca.
        draw: Lienzo de dibujo.
        max_width: Ancho máximo disponible.
        max_height: Alto máximo disponible.
        scale: Factor de escala del diseño.
        max_lines: Cantidad máxima de líneas.

    Returns:
        tuple: Fuente, líneas y separación entre líneas.
    """
    path, _ = _resolve_serif_path(config)
    base = max(round(_SERIF_BASE_SIZE * scale), 12)
    minimum = min(max(round(_SERIF_MIN_SIZE * scale), 12), base)
    size = base

    while size >= minimum:
        font = _load_serif_font(path, size)
        line_gap = max(round(size * 0.14), 1)
        lines = wrap_text(text, font, max_width, draw)
        if (
            len(lines) <= max_lines
            and block_height(lines, font, line_gap) <= max_height
        ):
            return font, lines, line_gap
        size -= 2

    font = _load_serif_font(path, minimum)
    line_gap = max(round(minimum * 0.14), 1)
    lines = wrap_text(text, font, max_width, draw)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(f"{last}…", font=font) > max_width:
            last = last[:-1]
        lines[-1] = f"{last.rstrip()}…"

    return font, lines, line_gap


# ---------------------------------------------------------------------------
# Piezas comunes
# ---------------------------------------------------------------------------


def _ellipsized(lines: list[str]) -> bool:
    """Indica si un bloque terminó recortado con puntos suspensivos.

    Args:
        lines: Líneas del bloque.

    Returns:
        bool: True si la última línea cierra con elipsis.
    """
    return bool(lines) and lines[-1].endswith("…")


def _draw_kicker(
    draw: ImageDraw.ImageDraw,
    label: str,
    accent: tuple[int, int, int],
    config: dict[str, Any],
    margin: int,
    top: int,
    scale: float,
) -> None:
    """Dibuja la etiqueta de sección con su marca cuadrada.

    Args:
        draw: Lienzo de dibujo.
        label: Etiqueta de la sección.
        accent: Color de acento.
        config: Configuración de marca.
        margin: Margen lateral.
        top: Coordenada vertical del bloque.
        scale: Factor de escala.
    """
    font = load_font("cover_kicker", base_size("cover_kicker", scale), config)
    marker = max(round(10 * scale), 4)
    gap = max(round(14 * scale), 3)

    text = letter_space(label.upper())
    text_height = line_height(font)
    marker_y = top + max((text_height - marker) // 2, 0)

    draw.rectangle(
        (margin, marker_y, margin + marker, marker_y + marker),
        fill=accent,
    )
    draw.text(
        (margin + marker + gap, top),
        text,
        font=font,
        fill=accent,
    )


def _draw_logo(
    image: Image.Image,
    config: dict[str, Any],
    width: int,
    margin: int,
    top: int,
) -> None:
    """Pega el logo de la marca en la esquina superior derecha.

    Args:
        image: Lienzo RGB.
        config: Configuración de marca.
        width: Ancho del lienzo.
        margin: Margen lateral.
        top: Coordenada vertical.
    """
    logo = prepare_logo(
        config,
        width,
        height_ratio=_LOGO_HEIGHT_RATIO,
        max_width_ratio=_LOGO_MAX_WIDTH_RATIO,
    )
    if logo is None:
        return
    image.paste(logo, (width - margin - logo.width, top), logo)


def _draw_footer(
    draw: ImageDraw.ImageDraw,
    config: dict[str, Any],
    palette: dict[str, tuple[int, int, int]],
    muted: tuple[int, int, int],
    byline: str,
    width: int,
    height: int,
    margin: int,
    scale: float,
) -> None:
    """Dibuja la regla inferior, la firma y los datos del medio.

    Args:
        draw: Lienzo de dibujo.
        config: Configuración de marca.
        palette: Paleta de marca resuelta.
        muted: Color apagado legible.
        byline: Firma que se muestra a la izquierda.
        width: Ancho del lienzo.
        height: Alto del lienzo.
        margin: Margen lateral.
        scale: Factor de escala.
    """
    brand = config.get("brand")
    brand = brand if isinstance(brand, dict) else {}
    website = brand.get("website")
    handle = brand.get("handle")
    right_parts = [
        str(value).strip()
        for value in (website, handle)
        if isinstance(value, str) and value.strip()
    ]

    font = load_font("cover_byline", base_size("cover_byline", scale), config)
    footer_y = height - margin - line_height(font)
    rule_y = footer_y - max(round(18 * scale), 4)

    draw.line(
        (margin, rule_y, width - margin, rule_y),
        fill=blend(palette["background"], muted, 0.45),
        width=max(round(1 * scale), 1),
    )

    left = letter_space((byline or brand_name(config)).upper())
    draw.text((margin, footer_y), left, font=font, fill=muted)

    right = letter_space("   ·   ".join(right_parts))
    if right:
        right_x = width - margin - draw.textlength(right, font=font)
        draw.text((right_x, footer_y), right, font=font, fill=muted)


def _circular_logo(
    config: dict[str, Any],
    width: int,
    diameter: int,
    accent: tuple[int, int, int],
    background: tuple[int, int, int],
) -> Image.Image:
    """Construye la marca circular que acompaña la firma de opinión.

    Si la marca no tiene logo, se dibuja un círculo con la inicial del medio.

    Args:
        config: Configuración de marca.
        width: Ancho del lienzo que determina la escala del logo.
        diameter: Diámetro del círculo en píxeles.
        accent: Color de acento.
        background: Color de fondo, usado para la inicial.

    Returns:
        Image.Image: Marca circular en RGBA.
    """
    size = max(int(diameter), _AVATAR_MIN_SIZE)
    logo = prepare_logo(
        config,
        width,
        height_ratio=size / max(width, 1),
        max_width_ratio=0.30,
    )

    if logo is not None:
        # La marca suele ser un logotipo vertical (símbolo arriba, wordmark
        # abajo). Para el avatar se usa la parte superior, que contiene el
        # símbolo, y se descarta el wordmark: dentro de un círculo pequeño el
        # texto se vuelve una mancha ilegible.
        if logo.height > logo.width * 1.05:
            top_height = int(logo.height * 0.66)
            side = min(logo.width, top_height)
            left = (logo.width - side) // 2
            logo = logo.crop((left, 0, left + side, side))
        else:
            side = min(logo.width, logo.height)
            left = (logo.width - side) // 2
            top = (logo.height - side) // 2
            logo = logo.crop((left, top, left + side, top + side))

        logo = logo.resize((size, size), Image.Resampling.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
        logo.putalpha(mask)
        return logo

    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    badge_draw = ImageDraw.Draw(badge)
    badge_draw.ellipse((0, 0, size - 1, size - 1), fill=accent)
    initial = (brand_name(config) or "L")[0].upper()
    font = load_font("cover_byline", max(round(size * 0.48), 8), config)
    box = badge_draw.textbbox((0, 0), initial, font=font)
    text_width = box[2] - box[0]
    text_height = box[3] - box[1]
    badge_draw.text(
        (
            (size - text_width) / 2 - box[0],
            (size - text_height) / 2 - box[1],
        ),
        initial,
        font=font,
        fill=background,
    )
    return badge


# ---------------------------------------------------------------------------
# Tratamientos
# ---------------------------------------------------------------------------


def _draw_quote_footer(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    config: dict[str, Any],
    palette: dict[str, tuple[int, int, int]],
    muted: tuple[int, int, int],
    accent: tuple[int, int, int],
    byline: str,
    width: int,
    height: int,
    margin: int,
    scale: float,
) -> None:
    """Dibuja el pie de la portada de opinión con la marca circular.

    La firma y su marca ocupan el lugar de la firma común, para no duplicar
    la identidad del medio en dos líneas seguidas.

    Args:
        image: Lienzo RGB.
        draw: Lienzo de dibujo.
        config: Configuración de marca.
        palette: Paleta de marca resuelta.
        muted: Color apagado legible.
        accent: Color de acento legible.
        byline: Firma que acompaña a la marca circular.
        width: Ancho del lienzo.
        height: Alto del lienzo.
        margin: Margen lateral.
        scale: Factor de escala.
    """
    font = load_font("cover_byline", base_size("cover_byline", scale), config)
    footer_y = height - margin - line_height(font)
    rule_y = footer_y - max(round(18 * scale), 4)

    draw.line(
        (margin, rule_y, width - margin, rule_y),
        fill=blend(palette["background"], muted, 0.45),
        width=max(round(1 * scale), 1),
    )

    diameter = max(round(width * _AVATAR_RATIO), _AVATAR_MIN_SIZE)
    badge = _circular_logo(
        config, width, diameter, accent, palette["background"]
    )
    avatar_y = footer_y - max(
        (diameter - line_height(font)) // 2, 0
    )
    image.paste(badge, (margin, avatar_y), badge)

    text_x = margin + diameter + max(round(18 * scale), 4)
    draw.text(
        (text_x, footer_y),
        letter_space((byline or brand_name(config)).upper()),
        font=font,
        fill=accent,
    )

    brand = config.get("brand")
    brand = brand if isinstance(brand, dict) else {}
    right_parts = [
        str(value).strip()
        for value in (brand.get("website"), brand.get("handle"))
        if isinstance(value, str) and value.strip()
    ]
    right = letter_space("   ·   ".join(right_parts))
    if right:
        right_x = width - margin - draw.textlength(right, font=font)
        draw.text((right_x, footer_y), right, font=font, fill=muted)


def _render_text_first(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    content: CoverContent,
    config: dict[str, Any],
    palette: dict[str, tuple[int, int, int]],
    category_label: str,
    accent: tuple[int, int, int],
    muted: tuple[int, int, int],
    scale: float,
    limits: dict[str, int],
    warnings: list[str],
) -> None:
    """Compone la portada tipográfica: sección, titular, bajada y pie.

    Args:
        image: Lienzo RGB.
        draw: Lienzo de dibujo.
        content: Contenido editorial.
        config: Configuración de marca.
        palette: Paleta de marca resuelta.
        category_label: Etiqueta visible de la sección.
        accent: Color de acento legible.
        muted: Color apagado legible.
        scale: Factor de escala.
        limits: Topes de texto.
        warnings: Lista de advertencias.
    """
    width, height = image.size
    margin = round(width * _MARGIN_RATIO)
    content_width = width - 2 * margin

    _draw_kicker(
        draw, category_label, accent, config, margin, round(height * 0.10), scale
    )
    _draw_logo(image, config, width, margin, round(height * 0.10))

    title_top = round(height * 0.24)
    title_bottom = round(height * 0.62)
    title_width = round(content_width * 0.88)
    title_height = max(title_bottom - title_top, 1)

    font, lines, gap = fit_text(
        content.title,
        "cover_title",
        config,
        draw,
        title_width,
        title_height,
        scale,
        max_lines=int(limits.get("title_max_lines", 4)),
    )
    if _ellipsized(lines):
        warnings.append(
            "El titular no cabía completo en la portada y se recortó."
        )

    title_y = title_top + max(
        (title_height - block_height(lines, font, gap)) // 2, 0
    )
    draw_lines(draw, lines, font, palette["text"], margin, title_y, gap)

    rule_y = title_y + block_height(lines, font, gap) + round(26 * scale)
    rule_height = max(round(6 * scale), 2)
    draw.rectangle(
        (
            margin,
            rule_y,
            margin + round(120 * scale),
            rule_y + rule_height,
        ),
        fill=accent,
    )

    if content.deck:
        deck_top = rule_y + round(24 * scale)
        deck_bottom = round(height * 0.80)
        deck_height = max(deck_bottom - deck_top, 1)
        deck_font, deck_lines, deck_gap = fit_text(
            content.deck,
            "cover_deck",
            config,
            draw,
            round(content_width * 0.90),
            deck_height,
            scale,
            max_lines=int(limits.get("deck_max_lines", 3)),
        )
        if _ellipsized(deck_lines):
            warnings.append(
                "La bajada no cabía completa en la portada y se recortó."
            )
        draw_lines(
            draw,
            deck_lines,
            deck_font,
            muted,
            margin,
            deck_top,
            deck_gap,
        )

    _draw_footer(
        draw,
        config,
        palette,
        muted,
        content.byline,
        width,
        height,
        margin,
        scale,
    )


def _render_quote(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    content: CoverContent,
    config: dict[str, Any],
    palette: dict[str, tuple[int, int, int]],
    category_label: str,
    accent: tuple[int, int, int],
    muted: tuple[int, int, int],
    scale: float,
    limits: dict[str, int],
    warnings: list[str],
) -> None:
    """Compone la portada de opinión: titular breve, cita serif y firma.

    Args:
        image: Lienzo RGB.
        draw: Lienzo de dibujo.
        content: Contenido editorial.
        config: Configuración de marca.
        palette: Paleta de marca resuelta.
        category_label: Etiqueta visible de la sección.
        accent: Color de acento legible.
        muted: Color apagado legible.
        scale: Factor de escala.
        limits: Topes de texto.
        warnings: Lista de advertencias.
    """
    width, height = image.size
    margin = round(width * _MARGIN_RATIO)
    content_width = width - 2 * margin

    _draw_kicker(
        draw, category_label, accent, config, margin, round(height * 0.09), scale
    )
    _draw_logo(image, config, width, margin, round(height * 0.09))

    title_font, title_lines, title_gap = fit_text(
        content.title,
        "cover_deck",
        config,
        draw,
        round(content_width * 0.86),
        round(height * 0.11),
        scale,
        max_lines=2,
    )
    if _ellipsized(title_lines):
        warnings.append(
            "El titular no cabía completo en la portada y se recortó."
        )
    draw_lines(
        draw,
        title_lines,
        title_font,
        palette["text"],
        margin,
        round(height * 0.17),
        title_gap,
    )

    path, is_serif = _resolve_serif_path(config)
    if not is_serif:
        warnings.append(
            "No hay una fuente serif disponible: la cita se dibuja con la "
            "sans en negrita."
        )

    glyph_font = _load_serif_font(
        path, max(round(_QUOTE_GLYPH_RATIO * width), 24)
    )
    glyph_y = round(height * 0.28)
    draw.text((margin, glyph_y), "\u201c", font=glyph_font, fill=accent)
    glyph_height = line_height(glyph_font)

    quote_top = glyph_y + glyph_height + round(6 * scale)
    quote_bottom = round(height * 0.78)
    quote_height = max(quote_bottom - quote_top, 1)
    quote_text = content.quote or content.title

    quote_font, quote_lines, quote_gap = _fit_serif_text(
        quote_text,
        config,
        draw,
        round(content_width * 0.92),
        quote_height,
        scale,
        max_lines=int(limits.get("quote_max_lines", 4)),
    )
    if _ellipsized(quote_lines):
        warnings.append(
            "La cita no cabía completa en la portada y se recortó."
        )
    draw_lines(
        draw,
        quote_lines,
        quote_font,
        palette["text"],
        margin,
        quote_top,
        quote_gap,
    )

    _draw_quote_footer(
        image,
        draw,
        config,
        palette,
        muted,
        accent,
        content.byline or brand_name(config),
        width,
        height,
        margin,
        scale,
    )


def _render_data(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    content: CoverContent,
    config: dict[str, Any],
    palette: dict[str, tuple[int, int, int]],
    category_label: str,
    accent: tuple[int, int, int],
    muted: tuple[int, int, int],
    scale: float,
    limits: dict[str, int],
    warnings: list[str],
) -> None:
    """Compone la portada de dato duro: cifra protagonista y leyenda.

    Args:
        image: Lienzo RGB.
        draw: Lienzo de dibujo.
        content: Contenido editorial.
        config: Configuración de marca.
        palette: Paleta de marca resuelta.
        category_label: Etiqueta visible de la sección.
        accent: Color de acento legible.
        muted: Color apagado legible.
        scale: Factor de escala.
        limits: Topes de texto.
        warnings: Lista de advertencias.
    """
    width, height = image.size
    margin = round(width * _MARGIN_RATIO)
    content_width = width - 2 * margin

    _draw_kicker(
        draw, category_label, accent, config, margin, round(height * 0.09), scale
    )
    _draw_logo(image, config, width, margin, round(height * 0.09))

    title_font, title_lines, title_gap = fit_text(
        content.title,
        "cover_deck",
        config,
        draw,
        round(content_width * 0.86),
        round(height * 0.11),
        scale,
        max_lines=2,
    )
    if _ellipsized(title_lines):
        warnings.append(
            "El titular no cabía completo en la portada y se recortó."
        )
    draw_lines(
        draw,
        title_lines,
        title_font,
        palette["text"],
        margin,
        round(height * 0.16),
        title_gap,
    )

    figure_top = round(height * 0.30)
    figure_bottom = round(height * 0.60)
    figure_height = max(figure_bottom - figure_top, 1)
    bar_width = max(round(6 * scale), 2)
    figure_x = margin + bar_width + round(24 * scale)
    figure_width = max(content_width - (figure_x - margin), 1)

    draw.rectangle(
        (margin, figure_top, margin + bar_width, figure_top + figure_height),
        fill=accent,
    )

    figure_font, figure_lines, figure_gap = fit_text(
        content.figure or content.title,
        "cover_figure",
        config,
        draw,
        figure_width,
        figure_height,
        scale,
        max_lines=1,
    )
    if _ellipsized(figure_lines):
        warnings.append(
            "La cifra no cabía completa en la portada y se recortó."
        )
    figure_y = figure_top + max(
        (figure_height - block_height(figure_lines, figure_font, figure_gap))
        // 2,
        0,
    )
    draw_lines(
        draw,
        figure_lines,
        figure_font,
        accent,
        figure_x,
        figure_y,
        figure_gap,
    )

    if content.caption:
        caption_top = round(height * 0.63)
        caption_bottom = round(height * 0.80)
        caption_height = max(caption_bottom - caption_top, 1)
        caption_font, caption_lines, caption_gap = fit_text(
            content.caption,
            "cover_caption",
            config,
            draw,
            figure_width,
            caption_height,
            scale,
            max_lines=int(limits.get("caption_max_lines", 4)),
        )
        if _ellipsized(caption_lines):
            warnings.append(
                "La leyenda del dato no cabía completa y se recortó."
            )
        draw_lines(
            draw,
            caption_lines,
            caption_font,
            muted,
            figure_x,
            caption_top,
            caption_gap,
        )

    _draw_footer(
        draw,
        config,
        palette,
        muted,
        content.byline,
        width,
        height,
        margin,
        scale,
    )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def render_cover(
    content: CoverContent,
    format_spec: CoverFormat,
    config: dict[str, Any],
    specs: dict[str, Any],
) -> tuple[Image.Image, list[str]]:
    """Renderiza una portada en el formato pedido.

    Args:
        content: Contenido editorial.
        format_spec: Formato de salida.
        config: Configuración de marca.
        specs: Especificaciones de portada resueltas.

    Returns:
        tuple[Image.Image, list[str]]: Imagen RGB y advertencias del render.

    Raises:
        CoverRenderError: Si el formato no tiene dimensiones positivas.
    """
    width = int(format_spec.width)
    height = int(format_spec.height)
    if width <= 0 or height <= 0:
        raise CoverRenderError(
            f"El formato {format_spec.name!r} no tiene dimensiones válidas: "
            f"{width}x{height}."
        )

    palette = brand_palette(config)
    warnings: list[str] = []
    background, accent, muted = _resolve_colors(
        content.category, palette, specs, warnings
    )
    scale = width / COVER_BASE_WIDTH
    intensity = float(specs.get("texture", {}).get("intensity", 0.09))
    limits = specs.get("limits", {})
    category_spec = specs.get("categories", {}).get(content.category, {})
    category_label = str(
        category_spec.get("label", content.category) or content.category
    )

    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)

    _draw_spark_pattern(image, width, height, accent, intensity, scale)
    draw.rectangle(
        (0, 0, width, max(round(8 * scale), 3)),
        fill=accent,
    )

    if content.treatment == "quote":
        _render_quote(
            image,
            draw,
            content,
            config,
            palette,
            category_label,
            accent,
            muted,
            scale,
            limits,
            warnings,
        )
    elif content.treatment == "data":
        _render_data(
            image,
            draw,
            content,
            config,
            palette,
            category_label,
            accent,
            muted,
            scale,
            limits,
            warnings,
        )
    else:
        _render_text_first(
            image,
            draw,
            content,
            config,
            palette,
            category_label,
            accent,
            muted,
            scale,
            limits,
            warnings,
        )

    return image, warnings


def save_cover_image(image: Image.Image, path: str | Path) -> Path:
    """Guarda una portada como PNG optimizado.

    Args:
        image: Imagen a guardar.
        path: Ruta de destino.

    Returns:
        Path: Ruta absoluta del archivo escrito.

    Raises:
        CoverRenderError: Si la imagen no se puede guardar.
    """
    destination = Path(path)
    try:
        image.save(destination, format="PNG", optimize=True)
    except OSError as exc:
        raise CoverRenderError(
            f"No se pudo guardar la portada en {destination}: {exc}"
        ) from exc
    return destination.resolve()
