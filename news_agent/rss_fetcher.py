"""Módulo de ingesta de noticias desde canales RSS.

Utiliza feedparser para extraer artículos de cada fuente configurada,
con tolerancia a fallos individuales por feed.
"""

import logging
import time
from typing import Any

import feedparser

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class FeedFetchError(Exception):
    """Excepción personalizada para errores en la obtención de un feed RSS."""

    def __init__(self, feed_name: str, detail: str) -> None:
        self.feed_name = feed_name
        self.detail = detail
        super().__init__(f"Error al obtener feed '{feed_name}': {detail}")


def fetch_feed(name: str, url: str) -> list[dict[str, Any]]:
    """Obtiene y parsea un único feed RSS.

    Args:
        name: Nombre descriptivo del medio.
        url: URL del canal RSS a consultar.

    Returns:
        list[dict]: Lista de artículos extraídos. Cada dict contiene:
            - title (str)
            - source (str) — nombre del medio
            - summary (str | None)
            - published_parsed (time.struct_time | None)
            - link (str | None)

    Raises:
        FeedFetchError: Si ocurre un error de red o de parseo del feed.
    """
    logger.info("Obteniendo feed '%s' desde %s", name, url)

    try:
        parsed = feedparser.parse(url)
    except Exception as exc:
        raise FeedFetchError(name, f"Excepción de red o parseo: {exc}") from exc

    # feedparser no lanza excepciones en XML malformado; usa el flag 'bozo'
    if parsed.bozo:
        bozo_msg = str(getattr(parsed, "bozo_exception", "Error desconocido"))
        logger.warning(
            "Feed '%s' tiene errores de formato (bozo=1): %s. "
            "Se intentará extraer las entradas disponibles.",
            name,
            bozo_msg,
        )

    entries = parsed.get("entries", [])
    if not entries:
        logger.info("Feed '%s' no contiene entradas en este momento.", name)
        return []

    items: list[dict[str, Any]] = []
    for entry in entries:
        items.append(
            {
                "title": entry.get("title", "").strip(),
                "source": name,
                "summary": entry.get("summary"),
                "published_parsed": entry.get("published_parsed"),
                "link": entry.get("link"),
            }
        )

    logger.info("Feed '%s': %d artículo(s) obtenido(s).", name, len(items))
    return items


def fetch_all(feeds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Obtiene artículos de todos los feeds configurados, con tolerancia a fallos.

    Si un feed falla (error de red, servidor caído, XML inválido),
    se registra el error y se continúa con el siguiente.

    Args:
        feeds: Lista de dicts con claves 'name' y 'url'.

    Returns:
        list[dict]: Lista consolidada de todos los artículos extraídos
                    exitosamente desde los feeds.
    """
    all_items: list[dict[str, Any]] = []
    success_count = 0
    fail_count = 0

    for feed in feeds:
        name = feed["name"]
        url = feed["url"]
        try:
            items = fetch_feed(name, url)
            all_items.extend(items)
            success_count += 1
        except FeedFetchError as exc:
            logger.error(
                "Fallo al procesar feed '%s': %s. Continuando con el siguiente.",
                exc.feed_name,
                exc.detail,
            )
            fail_count += 1
        except Exception:
            logger.exception(
                "Error inesperado al procesar feed '%s'. Continuando con el siguiente.",
                name,
            )
            fail_count += 1

    logger.info(
        "Resumen de ingesta: %d feeds exitosos, %d feeds fallidos, "
        "%d artículos totales recolectados.",
        success_count,
        fail_count,
        len(all_items),
    )

    return all_items
