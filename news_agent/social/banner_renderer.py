"""Renderizado local de banners promocionales con Pillow.

Genera las piezas gráficas de la marca sin depender de servicios externos:
dos plantillas (tarjeta de titular y tarjeta de cita) dibujadas en los cuatro
formatos de plataforma declarados en ``social_config.json``.

El diseño se parametriza por un factor de escala respecto de un ancho de
referencia, de modo que una sola implementación sirva para 1600x900, 1200x630,
1080x1080 y 1080x1920. En el formato vertical se respetan las zonas seguras
superior e inferior, porque la interfaz de la plataforma las tapa.
"""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from ..config import (
    SOCIAL_BANNER_BASE_WIDTH,
    SOCIAL_FONT_BOLD_CANDIDATES,
    SOCIAL_FONT_REGULAR_CANDIDATES,
)
from .models import BannerSpec, SocialCopy
from .platform_specs import ALL_PLATFORMS, platform_of_format

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class BannerRenderError(Exception):
    """Excepción para errores al renderizar un banner."""


# ---------------------------------------------------------------------------
# Paleta y colores
# ---------------------------------------------------------------------------

_DEFAULT_COLORS: dict[str, str] = {
    "background": "#0E0E10",
    "surface": "#1A1A1F",
    "text": "#FFFFFF",
    "muted": "#A8A8B3",
    "accent": "#DF3224",
    "accent_alt": "#F2C14E",
}

# Tamaños base de la tipografía, definidos para el ancho de referencia
_FONT_SIZES: dict[str, tuple[int, int]] = {
    # rol: (tamaño base, tamaño mínimo)
    "headline": (78, 40),
    "quote": (74, 34),
    "kicker": (26, 14),
    "attribution": (32, 18),
    "body": (24, 14),
}

# Roles que se resuelven con una fuente en negrita
_BOLD_ROLES = frozenset({"headline", "kicker", "quote", "attribution"})

# Altura del logo como fracción del ancho del lienzo, tope admisible de esa
# proporción y ancho máximo que puede ocupar sin invadir la etiqueta de marca
_LOGO_HEIGHT_RATIO = 0.11
_LOGO_MAX_HEIGHT_RATIO = 0.3
_LOGO_MAX_WIDTH_RATIO = 0.22

# Nombres de archivo esperados dentro del directorio de fuentes alternativo
_BOLD_FILE_NAMES = (
    "DejaVuSans-Bold.ttf",
    "LiberationSans-Bold.ttf",
    "NotoSans-Bold.ttf",
)
_REGULAR_FILE_NAMES = (
    "DejaVuSans.ttf",
    "LiberationSans-Regular.ttf",
    "NotoSans-Regular.ttf",
)


def _parse_hex(value: str) -> tuple[int, int, int] | None:
    """Convierte un color hexadecimal en una tupla RGB.

    Args:
        value: Color en formato ``#RRGGBB`` o ``#RGB``.

    Returns:
        tuple[int, int, int] | None: Color RGB, o None si no es parseable.
    """
    text = (value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) != 6:
        return None
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return None


def hex_to_rgb(value: str, fallback: str = "#000000") -> tuple[int, int, int]:
    """Convierte un color hexadecimal en RGB, con respaldo ante valores inválidos.

    Un color mal escrito en el JSON de marca no debe abortar el renderizado:
    se registra la advertencia y se usa el color de respaldo.

    Args:
        value: Color en formato hexadecimal.
        fallback: Color a usar si ``value`` no es parseable.

    Returns:
        tuple[int, int, int]: Color RGB válido.
    """
    parsed = _parse_hex(value)
    if parsed is not None:
        return parsed

    logger.warning("Color inválido %r: se usa %s.", value, fallback)
    fallback_rgb = _parse_hex(fallback)
    return fallback_rgb if fallback_rgb is not None else (0, 0, 0)


def blend(
    base: tuple[int, int, int],
    other: tuple[int, int, int],
    factor: float,
) -> tuple[int, int, int]:
    """Mezcla dos colores, dando a ``other`` el peso indicado.

    Se usa para conseguir formas de fondo apenas insinuadas, sin recurrir a
    capas con transparencia ni a imágenes externas.

    Args:
        base: Color de partida.
        other: Color que se mezcla.
        factor: Peso de ``other``, entre 0.0 y 1.0.

    Returns:
        tuple[int, int, int]: Color mezclado.
    """
    weight = min(max(factor, 0.0), 1.0)
    return tuple(
        round(base[index] * (1 - weight) + other[index] * weight)
        for index in range(3)
    )  # type: ignore[return-value]


def brand_palette(config: dict[str, Any]) -> dict[str, tuple[int, int, int]]:
    """Resuelve la paleta de marca a RGB, aplicando respaldos por color.

    Args:
        config: Configuración de marca cargada desde ``social_config.json``.

    Returns:
        dict[str, tuple[int, int, int]]: Paleta indexada por rol de color.
    """
    brand = config.get("brand")
    colors = brand.get("colors") if isinstance(brand, dict) else None
    if not isinstance(colors, dict):
        colors = {}

    return {
        key: hex_to_rgb(str(colors.get(key, default)), default)
        for key, default in _DEFAULT_COLORS.items()
    }


def brand_name(config: dict[str, Any]) -> str:
    """Obtiene el nombre de marca declarado en la configuración.

    Args:
        config: Configuración de marca.

    Returns:
        str: Nombre de marca.
    """
    brand = config.get("brand")
    name = brand.get("name") if isinstance(brand, dict) else None
    if isinstance(name, str) and name.strip():
        return name.strip()
    return "La Chispa Sur"


# ---------------------------------------------------------------------------
# Tipografías
# ---------------------------------------------------------------------------


def resolve_font_path(role: str, config: dict[str, Any]) -> str | None:
    """Resuelve la ruta del archivo de fuente para un rol tipográfico.

    Orden de preferencia: la fuente declarada en la configuración de marca, el
    directorio indicado por ``SOCIAL_FONT_DIR`` y, por último, las rutas
    habituales de los sistemas operativos.

    Args:
        role: Rol tipográfico ("headline", "kicker", "body", etc.).
        config: Configuración de marca.

    Returns:
        str | None: Ruta a la fuente, o None si no se encontró ninguna.
    """
    bold = role in _BOLD_ROLES
    candidates: list[str] = []

    brand = config.get("brand")
    fonts = brand.get("fonts") if isinstance(brand, dict) else None
    configured = fonts.get(role) if isinstance(fonts, dict) else None
    if isinstance(configured, str) and configured.strip():
        candidates.append(configured.strip())

    env_dir = os.environ.get("SOCIAL_FONT_DIR")
    if env_dir:
        base = Path(env_dir)
        names = _BOLD_FILE_NAMES if bold else _REGULAR_FILE_NAMES
        candidates.extend(str(base / name) for name in names)
        if base.is_dir():
            candidates.extend(sorted(str(item) for item in base.glob("*.ttf")))

    candidates.extend(
        SOCIAL_FONT_BOLD_CANDIDATES if bold else SOCIAL_FONT_REGULAR_CANDIDATES
    )

    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate

    logger.warning(
        "No se encontró ninguna fuente del sistema para el rol '%s': se usa "
        "la fuente por defecto de Pillow, que tiene cobertura limitada de "
        "acentos.",
        role,
    )
    return None


@lru_cache(maxsize=64)
def _load_font(
    path: str | None, size: int
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Carga una fuente, con la fuente por defecto de Pillow como respaldo.

    Args:
        path: Ruta al archivo de fuente, o None para usar la por defecto.
        size: Tamaño en píxeles.

    Returns:
        ImageFont.FreeTypeFont | ImageFont.ImageFont: Fuente lista para dibujar.
    """
    if path:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError as exc:
            logger.warning("No se pudo cargar la fuente %s: %s", path, exc)

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow antiguo sin parámetro de tamaño
        return ImageFont.load_default()


def load_font(
    role: str, size: int, config: dict[str, Any]
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Carga la fuente de un rol en el tamaño pedido.

    Args:
        role: Rol tipográfico.
        size: Tamaño en píxeles.
        config: Configuración de marca.

    Returns:
        ImageFont.FreeTypeFont | ImageFont.ImageFont: Fuente lista para dibujar.
    """
    return _load_font(resolve_font_path(role, config), max(int(size), 1))


def _base_size(role: str, scale: float) -> int:
    """Calcula el tamaño base de un rol para el factor de escala dado.

    Args:
        role: Rol tipográfico.
        scale: Factor de escala respecto del ancho de referencia.

    Returns:
        int: Tamaño en píxeles.
    """
    base, _ = _FONT_SIZES.get(role, (28, 14))
    return max(round(base * scale), 8)


def _min_size(role: str, scale: float) -> int:
    """Calcula el tamaño mínimo de un rol para el factor de escala dado.

    Args:
        role: Rol tipográfico.
        scale: Factor de escala respecto del ancho de referencia.

    Returns:
        int: Tamaño mínimo en píxeles.
    """
    _, minimum = _FONT_SIZES.get(role, (28, 14))
    return max(round(minimum * scale), 8)


def _line_height(font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    """Devuelve el alto de línea de una fuente.

    Args:
        font: Fuente cargada.

    Returns:
        int: Alto de línea en píxeles.
    """
    ascent, descent = font.getmetrics()
    return ascent + descent


# ---------------------------------------------------------------------------
# Tipografía: envoltura y ajuste
# ---------------------------------------------------------------------------


def _split_long_word(
    word: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    """Parte por caracteres una palabra más ancha que la caja disponible.

    Args:
        word: Palabra a partir.
        font: Fuente con la que se mide.
        max_width: Ancho máximo disponible en píxeles.
        draw: Lienzo de dibujo, usado para medir.

    Returns:
        list[str]: Fragmentos que caben en el ancho disponible.
    """
    chunks: list[str] = []
    current = ""

    for char in word:
        candidate = current + char
        if not current or draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            chunks.append(current)
            current = char

    if current:
        chunks.append(current)
    return chunks


def wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    """Envuelve un texto en líneas que quepan en el ancho disponible.

    Args:
        text: Texto a envolver.
        font: Fuente con la que se mide.
        max_width: Ancho máximo disponible en píxeles.
        draw: Lienzo de dibujo, usado para medir.

    Returns:
        list[str]: Líneas del texto envuelto.
    """
    lines: list[str] = []
    current = ""

    for word in (text or "").split():
        if draw.textlength(word, font=font) > max_width:
            # La palabra sola no cabe: se parte por caracteres
            if current:
                lines.append(current)
                current = ""
            chunks = _split_long_word(word, font, max_width, draw)
            lines.extend(chunks[:-1])
            current = chunks[-1] if chunks else ""
            continue

        candidate = f"{current} {word}".strip()
        if not current or draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def _block_height(lines: list[str], font: Any, line_gap: int) -> int:
    """Calcula el alto total de un bloque de líneas.

    Args:
        lines: Líneas del bloque.
        font: Fuente del bloque.
        line_gap: Separación adicional entre líneas, en píxeles.

    Returns:
        int: Alto total en píxeles.
    """
    if not lines:
        return 0
    line_height = _line_height(font)
    return len(lines) * line_height + max(0, len(lines) - 1) * line_gap


def fit_text(
    text: str,
    role: str,
    config: dict[str, Any],
    draw: ImageDraw.ImageDraw,
    max_width: int,
    max_height: int,
    scale: float,
    max_lines: int | None = None,
) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, list[str], int]:
    """Elige el tamaño de fuente más grande con el que el texto cabe en la caja.

    Reduce el tamaño de dos en dos píxeles hasta que el bloque entra en el
    ancho y el alto disponibles. Si ni con el tamaño mínimo entra, recorta a
    la cantidad de líneas permitida y cierra con puntos suspensivos.

    Args:
        text: Texto a ajustar.
        role: Rol tipográfico.
        config: Configuración de marca.
        draw: Lienzo de dibujo, usado para medir.
        max_width: Ancho máximo disponible en píxeles.
        max_height: Alto máximo disponible en píxeles.
        scale: Factor de escala respecto del ancho de referencia.
        max_lines: Cantidad máxima de líneas permitidas, o None sin tope.

    Returns:
        tuple[fuente, líneas, separación]: La fuente elegida, las líneas del
        texto y la separación entre líneas usada.
    """
    base = _base_size(role, scale)
    minimum = min(_min_size(role, scale), base)
    size = base

    while size >= minimum:
        font = load_font(role, size, config)
        line_gap = max(round(size * 0.18), 1)
        lines = wrap_text(text, font, max_width, draw)
        within_lines = max_lines is None or len(lines) <= max_lines
        if within_lines and _block_height(lines, font, line_gap) <= max_height:
            return font, lines, line_gap
        size -= 2

    # Ni con el tamaño mínimo entra: se recorta a las líneas permitidas
    font = load_font(role, minimum, config)
    line_gap = max(round(minimum * 0.18), 1)
    lines = wrap_text(text, font, max_width, draw)

    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(f"{last}…", font=font) > max_width:
            last = last[:-1]
        lines[-1] = f"{last.rstrip()}…"

    return font, lines, line_gap


# ---------------------------------------------------------------------------
# Primitivas de dibujo
# ---------------------------------------------------------------------------


def letter_space(text: str, separator: str = " ") -> str:
    """Espacia las letras de un texto, simulando el tracking tipográfico.

    Pillow no expone el espaciado entre letras, así que se intercala el
    separador. Solo se aplica a textos cortos, como las etiquetas de marca.

    Args:
        text: Texto original.
        separator: Cadena que se intercala entre caracteres.

    Returns:
        str: Texto espaciado.
    """
    compact = " ".join((text or "").split())
    if not compact or len(compact) > 40:
        return compact
    return separator.join(compact)


def draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: Any,
    color: tuple[int, int, int],
    x: int,
    y: int,
    line_gap: int,
) -> None:
    """Dibuja un bloque de líneas alineado a la izquierda.

    Args:
        draw: Lienzo de dibujo.
        lines: Líneas a dibujar.
        font: Fuente del bloque.
        color: Color del texto.
        x: Coordenada horizontal de inicio.
        y: Coordenada vertical de inicio.
        line_gap: Separación adicional entre líneas, en píxeles.
    """
    cursor = y
    for line in lines:
        draw.text((x, cursor), line, font=font, fill=color)
        cursor += _line_height(font) + line_gap


def _draw_background_shapes(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    palette: dict[str, tuple[int, int, int]],
    scale: float,
    surface: bool = False,
) -> None:
    """Dibuja las formas de fondo del diseño.

    Una barra de acento en el borde izquierdo da identidad de marca, y un
    círculo apenas insinuado aporta profundidad sin competir con el texto.

    Args:
        draw: Lienzo de dibujo.
        width: Ancho del lienzo.
        height: Alto del lienzo.
        palette: Paleta de marca resuelta.
        scale: Factor de escala respecto del ancho de referencia.
        surface: Si es True, el fondo es el color de superficie de la marca.
    """
    background = palette["surface"] if surface else palette["background"]
    accent = palette["accent"]

    bar_width = max(round(10 * scale), 4)
    draw.rectangle((0, 0, bar_width, height), fill=accent)

    radius = int(width * 0.42)
    circle_color = blend(background, accent, 0.14)
    draw.ellipse(
        (
            width - radius,
            height - radius,
            width + int(radius * 0.35),
            height + int(radius * 0.35),
        ),
        fill=circle_color,
    )


def prepare_logo(
    config: dict[str, Any],
    canvas_width: int,
) -> Image.Image | None:
    """Carga el logo de la marca y lo deja listo para pegar en el banner.

    Se recorta el margen transparente del archivo antes de escalarlo: los
    logos suelen venir con padding interno, y sin recortarlo el arte visible
    quedaría bastante más chico que el espacio reservado en el diseño.

    Args:
        config: Configuración de marca.
        canvas_width: Ancho del lienzo en píxeles.

    Returns:
        Image.Image | None: Logo recortado y escalado, o None si la marca no
        tiene un logo utilizable. Un logo ausente no es un error: el banner
        se genera igual, sin logo.
    """
    brand = config.get("brand")
    brand = brand if isinstance(brand, dict) else {}

    logo_path = brand.get("logo_path")
    if not isinstance(logo_path, str) or not logo_path.strip():
        return None

    path = Path(logo_path.strip())
    if not path.is_file():
        logger.warning("El logo configurado no existe: %s", path)
        return None

    try:
        logo = Image.open(path).convert("RGBA")
    except OSError as exc:
        logger.warning("No se pudo abrir el logo %s: %s", path, exc)
        return None

    # Recorte del padding transparente, para usar el arte real del archivo
    bounds = logo.getchannel("A").getbbox()
    if bounds:
        logo = logo.crop(bounds)

    target_height = max(round(canvas_width * _logo_height_ratio(brand)), 12)
    target_width = max(round(logo.width * (target_height / logo.height)), 1)

    # El logo no puede invadir la etiqueta de marca del encabezado
    max_width = max(round(canvas_width * _LOGO_MAX_WIDTH_RATIO), 12)
    if target_width > max_width:
        target_width = max_width
        target_height = max(round(logo.height * (target_width / logo.width)), 1)

    return logo.resize((target_width, target_height), Image.Resampling.LANCZOS)


def _logo_height_ratio(brand: dict[str, Any]) -> float:
    """Resuelve la altura del logo como fracción del ancho del lienzo.

    Args:
        brand: Sección 'brand' de la configuración de marca.

    Returns:
        float: Proporción a usar. Los valores fuera de rango se ignoran y se
        vuelve al valor por defecto, para que un error de tipeo en el JSON no
        deforme el diseño.
    """
    configured = brand.get("logo_height_ratio")
    if (
        isinstance(configured, (int, float))
        and not isinstance(configured, bool)
        and 0 < float(configured) <= _LOGO_MAX_HEIGHT_RATIO
    ):
        return float(configured)

    return _LOGO_HEIGHT_RATIO


def _paste_logo(
    image: Image.Image,
    logo: Image.Image | None,
    margin: int,
    top: int,
) -> None:
    """Pega el logo preparado en la esquina superior derecha del banner.

    Args:
        image: Lienzo donde pegar el logo.
        logo: Logo ya escalado, o None para no pegar nada.
        margin: Margen lateral en píxeles.
        top: Coordenada vertical donde alinear el logo.
    """
    if logo is None:
        return

    image.paste(logo, (image.width - margin - logo.width, top), logo)


def _draw_footer(
    draw: ImageDraw.ImageDraw,
    config: dict[str, Any],
    palette: dict[str, tuple[int, int, int]],
    scale: float,
    margin: int,
    baseline_y: int,
) -> None:
    """Dibuja la barra inferior con la identidad de marca.

    Args:
        draw: Lienzo de dibujo.
        config: Configuración de marca.
        palette: Paleta de marca resuelta.
        scale: Factor de escala respecto del ancho de referencia.
        margin: Margen lateral en píxeles.
        baseline_y: Coordenada vertical del bloque.
    """
    brand = config.get("brand")
    brand = brand if isinstance(brand, dict) else {}
    handle = brand.get("handle")
    website = brand.get("website")
    parts = [
        str(value).strip()
        for value in (handle, website)
        if isinstance(value, str) and value.strip()
    ]
    if not parts:
        parts = [brand_name(config)]

    font = load_font("body", _base_size("body", scale), config)
    text = "   ·   ".join(parts)

    square = max(round(14 * scale), 4)
    center_y = baseline_y + _line_height(font) // 2
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
        letter_space(text),
        font=font,
        fill=palette["muted"],
    )


def _content_box(
    width: int,
    height: int,
    scale: float,
    safe_zone: dict[str, Any] | None,
) -> tuple[int, int, int, int]:
    """Calcula la caja útil del diseño, descontando márgenes y zonas seguras.

    Args:
        width: Ancho del lienzo.
        height: Alto del lienzo.
        scale: Factor de escala respecto del ancho de referencia.
        safe_zone: Zonas seguras superior e inferior, si la plataforma las tiene.

    Returns:
        tuple[int, int, int, int]: Margen lateral, borde superior, borde
        inferior y ancho útil.
    """
    margin = max(round(64 * scale), 12)
    safe_top = int(safe_zone.get("top", 0)) if isinstance(safe_zone, dict) else 0
    safe_bottom = (
        int(safe_zone.get("bottom", 0)) if isinstance(safe_zone, dict) else 0
    )

    top = min(safe_top + margin, height // 3)
    bottom = max(height - safe_bottom - margin, top + 1)
    content_width = max(width - 2 * margin, 1)

    return margin, top, bottom, content_width


# ---------------------------------------------------------------------------
# Plantillas
# ---------------------------------------------------------------------------


def render_headline_card(
    width: int,
    height: int,
    copy: SocialCopy,
    config: dict[str, Any],
    safe_zone: dict[str, Any] | None = None,
) -> Image.Image:
    """Renderiza la tarjeta de titular: marca, titular y barra inferior.

    Args:
        width: Ancho del banner en píxeles.
        height: Alto del banner en píxeles.
        copy: Copys del artículo, de donde se toma el titular.
        config: Configuración de marca.
        safe_zone: Zonas seguras de la plataforma, si corresponde.

    Returns:
        Image.Image: Banner renderizado en modo RGB.
    """
    palette = brand_palette(config)
    scale = width / SOCIAL_BANNER_BASE_WIDTH
    margin, top, bottom, content_width = _content_box(
        width, height, scale, safe_zone
    )

    image = Image.new("RGB", (width, height), palette["background"])
    draw = ImageDraw.Draw(image)
    _draw_background_shapes(draw, width, height, palette, scale, surface=False)

    logo = prepare_logo(config, width)

    # Etiqueta de marca
    kicker_font = load_font("kicker", _base_size("kicker", scale), config)
    kicker_gap = max(round(22 * scale), 4)
    kicker_height = _line_height(kicker_font)

    rule_height = max(round(6 * scale), 2)
    draw.rectangle(
        (margin, top, margin + round(72 * scale), top + rule_height),
        fill=palette["accent"],
    )

    kicker_y = top + rule_height + kicker_gap
    draw.text(
        (margin, kicker_y),
        letter_space(brand_name(config).upper()),
        font=kicker_font,
        fill=palette["accent_alt"],
    )

    # Barra inferior
    footer_font = load_font("body", _base_size("body", scale), config)
    footer_height = _line_height(footer_font)
    footer_y = bottom - footer_height

    # El titular arranca por debajo de la franja superior completa, que puede
    # estar marcada por la etiqueta de marca o por el logo, el que sea más alto
    header_height = max(
        rule_height + kicker_gap + kicker_height,
        logo.height if logo is not None else 0,
    )
    headline_top = top + header_height + max(round(28 * scale), 4)
    headline_height = max(footer_y - round(28 * scale) - headline_top, 1)

    indent = max(round(28 * scale), margin // 4)
    text_x = margin + indent
    text_width = max(content_width - indent, 1)

    font, lines, line_gap = fit_text(
        copy.title,
        "headline",
        config,
        draw,
        text_width,
        headline_height,
        scale,
        max_lines=5,
    )

    block_height = _block_height(lines, font, line_gap)
    headline_y = headline_top + max((headline_height - block_height) // 2, 0)
    draw_lines(draw, lines, font, palette["text"], text_x, headline_y, line_gap)

    _draw_footer(draw, config, palette, scale, margin, footer_y)
    _paste_logo(image, logo, margin, top)

    return image


def render_quote_card(
    width: int,
    height: int,
    copy: SocialCopy,
    config: dict[str, Any],
    safe_zone: dict[str, Any] | None = None,
) -> Image.Image:
    """Renderiza la tarjeta de cita: comillas, cita textual y atribución.

    Args:
        width: Ancho del banner en píxeles.
        height: Alto del banner en píxeles.
        copy: Copys del artículo, de donde se toma la cita.
        config: Configuración de marca.
        safe_zone: Zonas seguras de la plataforma, si corresponde.

    Returns:
        Image.Image: Banner renderizado en modo RGB.
    """
    palette = brand_palette(config)
    scale = width / SOCIAL_BANNER_BASE_WIDTH
    margin, top, bottom, content_width = _content_box(
        width, height, scale, safe_zone
    )

    image = Image.new("RGB", (width, height), palette["surface"])
    draw = ImageDraw.Draw(image)
    _draw_background_shapes(draw, width, height, palette, scale, surface=True)

    text_x = margin + max(round(28 * scale), margin // 4)
    text_width = max(content_width - max(round(28 * scale), margin // 4), 1)

    # Barra inferior
    footer_font = load_font("body", _base_size("body", scale), config)
    footer_height = _line_height(footer_font)
    footer_y = bottom - footer_height

    # Glifo de comillas
    glyph_size = max(round(190 * scale), 24)
    glyph_font = load_font("quote", glyph_size, config)
    glyph_y = top
    draw.text((margin, glyph_y), "\u201c", font=glyph_font, fill=palette["accent"])
    glyph_height = _line_height(glyph_font)

    # Atribución, medida antes para reservarle espacio a la cita
    attribution_text = copy.quote_card.attribution or brand_name(config)
    attribution_font = load_font(
        "attribution", _base_size("attribution", scale), config
    )
    attribution_line_gap = max(round(6 * scale), 1)
    attribution_lines = wrap_text(
        attribution_text, attribution_font, text_width, draw
    )[:2]
    attribution_gap = max(round(26 * scale), 4)
    attribution_height = _block_height(
        attribution_lines, attribution_font, attribution_line_gap
    )

    quote_top = glyph_y + glyph_height + round(12 * scale)
    quote_height = max(
        footer_y
        - attribution_gap
        - attribution_height
        - round(30 * scale)
        - quote_top,
        1,
    )

    quote_text = copy.quote_card.quote or copy.hook or copy.title
    font, lines, line_gap = fit_text(
        quote_text,
        "quote",
        config,
        draw,
        text_width,
        quote_height,
        scale,
        max_lines=7,
    )

    block_height = _block_height(lines, font, line_gap)
    quote_y = quote_top + max((quote_height - block_height) // 2, 0)
    draw_lines(draw, lines, font, palette["text"], text_x, quote_y, line_gap)

    attribution_y = quote_y + block_height + attribution_gap
    attribution_y = min(attribution_y, footer_y - attribution_height - 2)
    _draw_attribution(
        draw,
        attribution_lines,
        attribution_font,
        palette,
        text_x,
        attribution_y,
        scale,
        attribution_line_gap,
    )

    _draw_footer(draw, config, palette, scale, margin, footer_y)
    _paste_logo(image, prepare_logo(config, width), margin, top)

    return image


def _draw_attribution(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: Any,
    palette: dict[str, tuple[int, int, int]],
    x: int,
    y: int,
    scale: float,
    line_gap: int,
) -> None:
    """Dibuja la atribución de la cita, precedida por una regla de acento.

    Args:
        draw: Lienzo de dibujo.
        lines: Líneas de la atribución.
        font: Fuente de la atribución.
        palette: Paleta de marca resuelta.
        x: Coordenada horizontal de inicio.
        y: Coordenada vertical de inicio.
        scale: Factor de escala respecto del ancho de referencia.
        line_gap: Separación adicional entre líneas, en píxeles.
    """
    gap = max(round(18 * scale), 2)
    rule_width = max(round(40 * scale), 4)
    rule_height = max(round(4 * scale), 2)
    center_y = y + _line_height(font) // 2

    draw.rectangle(
        (x, center_y, x + rule_width, center_y + rule_height),
        fill=palette["accent_alt"],
    )
    draw_lines(
        draw, lines, font, palette["accent_alt"], x + rule_width + gap, y, line_gap
    )


# Mapa de plantillas disponibles, con la firma común que espera el renderizador
_TEMPLATE_RENDERERS = {
    "headline_card": render_headline_card,
    "quote_card": render_quote_card,
}


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def render_all_banners(
    copy: SocialCopy,
    config: dict[str, Any],
    output_dir: str | Path,
    platforms: list[str] | None = None,
) -> list[BannerSpec]:
    """Renderiza y guarda todos los banners declarados en la configuración.

    Un banner que falla no interrumpe el resto: se registra el error y se
    devuelve la especificación sin ruta, para que el manifiesto refleje que
    esa pieza quedó pendiente.

    Args:
        copy: Copys del artículo, fuente del titular y de la cita.
        config: Configuración de marca cargada desde ``social_config.json``.
        output_dir: Directorio donde guardar los PNG.
        platforms: Plataformas habilitadas. Por defecto, todas.

    Returns:
        list[BannerSpec]: Especificaciones de los banners generados.

    Raises:
        IOError: Si el directorio de salida no existe.
    """
    output_path = Path(output_dir)
    if not output_path.exists():
        raise OSError(f"El directorio de salida no existe: {output_path.resolve()}")

    selected = list(platforms) if platforms else list(ALL_PLATFORMS)

    banners_config = config.get("banners")
    banners_config = banners_config if isinstance(banners_config, dict) else {}
    templates = banners_config.get("templates", {})
    sizes = banners_config.get("sizes", {})
    safe_zones = banners_config.get("safe_zone", {})

    specs: list[BannerSpec] = []

    for template_name, targets in templates.items():
        renderer = _TEMPLATE_RENDERERS.get(template_name)
        if renderer is None:
            logger.warning(
                "Plantilla de banner desconocida, se omite: %s", template_name
            )
            continue
        if not isinstance(targets, (list, tuple)):
            continue

        for target in targets:
            target_name = str(target)
            if platform_of_format(target_name) not in selected:
                continue

            size = sizes.get(target_name)
            if not size:
                logger.warning(
                    "El formato '%s' no tiene tamaño declarado: se omite.",
                    target_name,
                )
                continue

            width, height = int(size[0]), int(size[1])
            destination = output_path / f"{template_name}_{target_name}.png"
            safe_zone = safe_zones.get(target_name) if isinstance(safe_zones, dict) else None

            try:
                image = renderer(width, height, copy, config, safe_zone=safe_zone)
                image.save(destination, format="PNG", optimize=True)
            except Exception as exc:  # noqa: BLE001 - un banner no debe romper el lote
                logger.error(
                    "No se pudo renderizar %s en %dx%d: %s",
                    template_name,
                    width,
                    height,
                    exc,
                )
                specs.append(
                    BannerSpec(
                        template=template_name,
                        platform=target_name,
                        width=width,
                        height=height,
                        path=None,
                    )
                )
                continue

            logger.info(
                "Banner generado: %s (%dx%d).", destination.name, width, height
            )
            specs.append(
                BannerSpec(
                    template=template_name,
                    platform=target_name,
                    width=width,
                    height=height,
                    path=destination.resolve(),
                )
            )

    return specs
