"""Módulo de filtrado y limpieza de noticias.

Aplica la ventana de 7 días (168 horas), limpia HTML residual de los resúmenes
y trunca el texto según las especificaciones.
"""

import calendar
import html as html_mod
import logging
import re
import time
from typing import Any

from .config import SUMMARY_MAX_CHARS, TIME_WINDOW_HOURS

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


def is_within_window(
    published_parsed: time.struct_time | None,
    window_hours: int | None = None,
) -> bool:
    """Determina si una noticia está dentro de la ventana de tiempo operativa.

    Args:
        published_parsed: Tupla struct_time de la fecha de publicación (UTC),
                          o None si la fecha no está disponible.
        window_hours: Horas de la ventana de análisis. Por defecto usa
                      TIME_WINDOW_HOURS (168h, 7 días).

    Returns:
        bool: True si la noticia está dentro de la ventana, False en caso
              contrario o si published_parsed es None.
    """
    if published_parsed is None:
        return False

    hours = window_hours if window_hours is not None else TIME_WINDOW_HOURS
    now_epoch = time.time()
    try:
        # calendar.timegm interpreta la tupla como UTC,
        # a diferencia de time.mktime que la interpreta como hora local.
        pub_epoch = calendar.timegm(published_parsed)
    except (OverflowError, ValueError):
        logger.warning(
            "Fecha de publicación inválida (fuera de rango): %s", published_parsed
        )
        return False

    diff_seconds = now_epoch - pub_epoch
    return diff_seconds <= hours * 3600


def strip_html(raw: str | None) -> str:
    """Elimina etiquetas HTML y decodifica entidades HTML de un texto.

    Utiliza únicamente la biblioteca estándar (html.parser + regex)
    para evitar dependencias externas.

    Args:
        raw: Texto potencialmente con HTML. Si es None, retorna cadena vacía.

    Returns:
        str: Texto limpio, sin etiquetas HTML y con entidades decodificadas.
    """
    if raw is None:
        return ""

    # 1. Eliminar etiquetas de script y style junto con su contenido
    cleaned = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>",
        "",
        raw,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 2. Eliminar comentarios HTML <!-- ... -->
    cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)

    # 3. Eliminar todas las etiquetas HTML restantes
    cleaned = re.sub(r"<[^>]*>", " ", cleaned)

    # 4. Reemplazar entidades HTML comunes que no caza html.unescape fácilmente
    cleaned = cleaned.replace("&nbsp;", " ")
    cleaned = cleaned.replace("&amp;", "&")

    # 5. Decodificar entidades HTML restantes
    cleaned = html_mod.unescape(cleaned)

    # 6. Normalizar espacios en blanco
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def truncate(text: str, max_chars: int | None = None) -> str:
    """Trunca un texto al número máximo de caracteres especificado.

    Args:
        text: Texto a truncar.
        max_chars: Número máximo de caracteres. Por defecto usa
                   SUMMARY_MAX_CHARS (200).

    Returns:
        str: Texto truncado al límite, sin cortar palabras a la mitad
             cuando es posible.
    """
    limit = max_chars if max_chars is not None else SUMMARY_MAX_CHARS

    if len(text) <= limit:
        return text

    # Buscar el último espacio antes del límite para no cortar palabras
    truncated = text[:limit]
    last_space = truncated.rfind(" ")

    if last_space > limit // 2:
        return truncated[:last_space] + "…"

    return truncated.rstrip() + "…"


def filter_items(
    raw_items: list[dict[str, Any]],
    window_hours: int | None = None,
    max_chars: int | None = None,
) -> list[dict[str, Any]]:
    """Filtra y normaliza una lista de artículos crudos.

    Aplica en secuencia:
    1. Filtro de ventana de tiempo (168 horas, 7 días).
    2. Limpieza HTML del resumen.
    3. Truncado del resumen limpio.

    Args:
        raw_items: Lista de artículos crudos desde el RSS fetcher.
        window_hours: Horas de la ventana (None = usar default).
        max_chars: Caracteres máximos del resumen (None = usar default).

    Returns:
        list[dict]: Artículos filtrados con las claves:
            - title (str)
            - source (str)
            - summary_clean (str) — resumen limpio y truncado
            - link (str | None)
    """
    filtered: list[dict[str, Any]] = []

    for item in raw_items:
        # Filtro de ventana de tiempo
        if not is_within_window(item.get("published_parsed"), window_hours):
            continue

        # Limpieza HTML + truncado del resumen
        # Preferir full_content (contenido completo extraído) si está disponible,
        # de lo contrario usar el resumen RSS original.
        if item.get("full_content"):
            raw_summary = item["full_content"]
        else:
            raw_summary = item.get("summary", "") or ""

        clean_summary = strip_html(raw_summary)
        truncated_summary = truncate(clean_summary, max_chars)

        filtered.append(
            {
                "title": item.get("title", "").strip(),
                "source": item.get("source", ""),
                "summary_clean": truncated_summary,
                "link": item.get("link"),
                # Campos de depuración preservados para el archivo intermedio
                "summary_raw": item.get("summary") or "",
                "full_content": item.get("full_content"),
            }
        )

    logger.info(
        "Filtrado completado: %d de %d artículos pasaron la ventana de %d horas.",
        len(filtered),
        len(raw_items),
        window_hours if window_hours is not None else TIME_WINDOW_HOURS,
    )

    return filtered
