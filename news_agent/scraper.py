"""Módulo de ingesta de noticias mediante scraping web.

Provee una alternativa a los feeds RSS para medios que no disponen de ellos,
utilizando requests + BeautifulSoup con selectores CSS configurables por sitio.
"""

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class ScrapingError(Exception):
    """Excepción personalizada para errores en el scraping de un sitio web."""

    def __init__(self, feed_name: str, detail: str) -> None:
        self.feed_name = feed_name
        self.detail = detail
        super().__init__(f"Error al scrapear '{feed_name}': {detail}")


def _resolve_url(link: str, prefix: str | None = None) -> str:
    """Resuelve una URL relativa usando el prefijo configurado.

    Si la URL ya es absoluta (comienza con http:// o https://),
    se retorna sin cambios.

    Args:
        link: URL absoluta o relativa extraída del HTML.
        prefix: Prefijo configurado en link_prefix para resolver URLs relativas.

    Returns:
        str: URL absoluta resuelta.
    """
    if not link:
        return ""

    link = link.strip()

    # Si ya es absoluta, retornar tal cual
    if link.startswith(("http://", "https://")):
        return link

    # Resolver con el prefijo si existe
    if prefix:
        return urljoin(prefix.rstrip("/") + "/", link.lstrip("/"))

    # Sin prefijo, retornar tal cual (posiblemente relativa)
    return link


def _parse_date(
    date_text: str, date_format: str | None = None
) -> time.struct_time | None:
    """Intenta parsear una fecha desde texto usando el formato especificado.

    Si no se proporciona formato o el parseo falla, retorna None.
    También intenta formatos ISO 8601 comunes como fallback.

    Args:
        date_text: Texto con la fecha a parsear (debe ser naive, sin zona horaria).
        date_format: Formato strptime configurado para este medio.

    Returns:
        struct_time en UTC, o None si el parseo falla.
    """
    if not date_text or not date_text.strip():
        return None

    text = date_text.strip()

    formatos_a_intentar: list[str] = []

    # Formato principal configurado por el usuario
    if date_format:
        formatos_a_intentar.append(date_format)

    # Formatos ISO 8601 comunes como fallback
    formatos_a_intentar.extend(
        [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]
    )

    for fmt in formatos_a_intentar:
        try:
            dt = datetime.strptime(text, fmt)
            # Si el datetime es timezone-aware, convertir a UTC
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
            # Convertir a struct_time (UTC)
            return dt.timetuple()
        except ValueError:
            continue

    logger.debug("No se pudo parsear la fecha '%s' con ningún formato conocido.", text)
    return None


def _extract_text(
    soup: BeautifulSoup | Any, selector: str, attribute: str | None = None
) -> str | None:
    """Extrae texto o un atributo de un elemento BeautifulSoup usando un selector CSS.

    Args:
        soup: Elemento BeautifulSoup (Tag o BeautifulSoup) donde buscar.
        selector: Selector CSS para encontrar el elemento.
        attribute: Si se especifica (ej: 'href'), devuelve el valor de ese atributo
                   en lugar del texto. Por defecto devuelve el texto del elemento.

    Returns:
        str | None: El texto o valor del atributo, o None si no se encuentra
                    el elemento.
    """
    element = soup.select_one(selector)
    if element is None:
        return None

    if attribute:
        return element.get(attribute, "").strip() or None

    return element.get_text(strip=True) or None


def scrape_feed(name: str, url: str, feed_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Obtiene artículos desde un sitio web mediante scraping con selectores CSS.

    Args:
        name: Nombre descriptivo del medio.
        url: URL del sitio web a scrapear.
        feed_config: Diccionario completo de configuración del feed, que incluye:
            - selectors (dict): Selectores CSS con claves 'article', 'title',
              'link' (opcional), 'summary' (opcional), 'date' (opcional).
            - date_format (str, opcional): Formato strptime para parsear fechas.
            - link_prefix (str, opcional): Prefijo para resolver URLs relativas.
            - request_headers (dict, opcional): Headers HTTP adicionales.

    Returns:
        list[dict]: Lista de artículos extraídos. Cada dict contiene:
            - title (str)
            - source (str) — nombre del medio
            - summary (str | None)
            - published_parsed (time.struct_time | None)
            - link (str | None)

    Raises:
        ScrapingError: Si ocurre un error de red o HTTP.
    """
    logger.info("Scrapeando '%s' desde %s", name, url)

    # -----------------------------------------------------------------------
    # Preparar headers HTTP
    # -----------------------------------------------------------------------
    headers: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-CL,es;q=0.9",
    }

    # Permitir que la configuración del feed sobreescriba o extienda los headers
    custom_headers = feed_config.get("request_headers", {})
    if custom_headers:
        headers.update(custom_headers)

    # -----------------------------------------------------------------------
    # Obtener la página
    # -----------------------------------------------------------------------
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout:
        raise ScrapingError(name, "Timeout de red tras 30 segundos")
    except requests.RequestException as exc:
        raise ScrapingError(name, f"Error HTTP/de red: {exc}")

    # -----------------------------------------------------------------------
    # Parsear HTML y extraer artículos
    # -----------------------------------------------------------------------
    soup = BeautifulSoup(response.text, "html.parser")
    selectors: dict[str, str] = feed_config.get("selectors", {})

    article_selector = selectors.get("article", "")
    if not article_selector:
        logger.warning("No se configuró selector 'article' para '%s'.", name)
        return []

    article_containers = soup.select(article_selector)

    if not article_containers:
        logger.info(
            "No se encontraron contenedores de artículos en '%s' "
            "con el selector '%s'.",
            name,
            article_selector,
        )
        return []

    # -----------------------------------------------------------------------
    # Extraer datos de cada contenedor de artículo
    # -----------------------------------------------------------------------
    items: list[dict[str, Any]] = []
    date_format = feed_config.get("date_format")
    link_prefix = feed_config.get("link_prefix")

    for container in article_containers:
        # Título (obligatorio)
        title_text = _extract_text(container, selectors["title"])
        if not title_text:
            # Contenedor sin título: probablemente malformado o selector incorrecto
            continue

        # Enlace (usa el mismo selector que title si no se especifica link)
        link_selector = selectors.get("link", selectors["title"])
        raw_link = _extract_text(container, link_selector, attribute="href")
        resolved_link = _resolve_url(raw_link, link_prefix) if raw_link else None

        # Resumen (opcional)
        summary_text: str | None = None
        if "summary" in selectors:
            summary_text = _extract_text(container, selectors["summary"])

        # Fecha (opcional) — primero intenta selector CSS, luego regex sobre la URL
        published_parsed: time.struct_time | None = None
        if "date" in selectors:
            date_text = _extract_text(container, selectors["date"])
            if date_text:
                published_parsed = _parse_date(date_text, date_format)

        # Fallback: extraer fecha desde la URL del artículo usando regex
        if published_parsed is None and resolved_link:
            date_regex = feed_config.get("date_regex")
            if date_regex:
                match = re.search(date_regex, resolved_link)
                if match:
                    # Reconstruir la fecha capturada (grupos en orden Y, m, d)
                    date_str = "/".join(match.groups())
                    published_parsed = _parse_date(date_str, date_format)

        items.append(
            {
                "title": title_text,
                "source": name,
                "summary": summary_text,
                "published_parsed": published_parsed,
                "link": resolved_link,
            }
        )

    logger.info(
        "Feed '%s' (scraping): %d artículo(s) extraído(s) de %d contenedor(es).",
        name,
        len(items),
        len(article_containers),
    )

    return items
