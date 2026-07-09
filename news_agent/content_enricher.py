"""Módulo de enriquecimiento de contenido de artículos.

Cuando el resumen RSS es demasiado corto para un análisis de calidad,
este módulo intenta extraer el texto completo del artículo desde su URL
utilizando la librería trafilatura (extracción especializada para noticias).

Usa ThreadPoolExecutor para procesar varias URLs en paralelo, con rate limiting
por dominio para evitar saturar los servidores de origen. Incluye caché en
archivo JSON para no re-descargar URLs ya procesadas en ejecuciones recientes.
"""

import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import trafilatura

from .config import (
    FULL_CONTENT_CACHE_DIR,
    FULL_CONTENT_DELAY,
    FULL_CONTENT_FETCH_ENABLED,
    FULL_CONTENT_MAX_WORKERS,
    FULL_CONTENT_TIMEOUT,
    MIN_SUMMARY_LENGTH,
)

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class ContentEnricherError(Exception):
    """Excepción personalizada para errores en el enriquecimiento de contenido.

    Se usa solo para logging; el enriquecimiento es best-effort y nunca
    interrumpe el pipeline principal.
    """

    def __init__(self, url: str, detail: str) -> None:
        self.url = url
        self.detail = detail
        super().__init__(f"Error al enriquecer {url}: {detail}")


# ---------------------------------------------------------------------------
# Utilidades de caché
# ---------------------------------------------------------------------------


def _url_cache_key(url: str) -> str:
    """Genera una clave de caché basada en el hash SHA-256 de la URL.

    Args:
        url: URL del artículo.

    Returns:
        Hex digest de 64 caracteres.
    """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _load_cache(cache_path: Path) -> dict[str, str]:
    """Carga el caché de contenido extraído desde un archivo JSON.

    Args:
        cache_path: Ruta al archivo de caché.

    Returns:
        Diccionario {clave_hash: texto_extraído}. Vacío si el archivo
        no existe o está corrupto.
    """
    if not cache_path.exists():
        return {}

    try:
        with open(cache_path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, IOError):
        logger.warning(
            "Archivo de caché corrupto, se ignorará: %s", cache_path
        )

    return {}


def _save_cache(cache_path: Path, cache: dict[str, str]) -> None:
    """Persiste el caché de contenido extraído a un archivo JSON.

    Args:
        cache_path: Ruta al archivo de caché.
        cache: Diccionario {clave_hash: texto_extraído}.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------


def _should_enrich(summary: str | None, min_length: int | None = None) -> bool:
    """Determina si un artículo necesita enriquecimiento de contenido.

    Args:
        summary: Resumen RSS original (puede ser None).
        min_length: Longitud mínima en caracteres. Si es None, usa MIN_SUMMARY_LENGTH.

    Returns:
        True si el resumen es demasiado corto y se debe intentar enriquecer.
    """
    threshold = min_length if min_length is not None else MIN_SUMMARY_LENGTH

    if summary is None:
        return True

    return len(summary.strip()) < threshold


def _extract_domain(url: str) -> str:
    """Extrae el dominio de una URL para rate limiting.

    Args:
        url: URL completa del artículo.

    Returns:
        Nombre del dominio (ej: 'www.bbc.com').
    """
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def _extract_with_timeout(html: str, timeout: int) -> str | None:
    """Ejecuta trafilatura.extract() en un hilo separado con timeout.

    Args:
        html: HTML de la página a extraer.
        timeout: Tiempo máximo en segundos para la extracción.

    Returns:
        Texto extraído, o None si falla o excede el timeout.
    """
    result: list[str | None] = [None]
    error: list[Exception | None] = [None]

    def _run():
        try:
            result[0] = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                output_format="txt",
                favor_precision=True,
            )
        except Exception as exc:
            error[0] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        logger.debug(
            "trafilatura.extract excedió el timeout de %ds", timeout
        )
        return None

    if error[0] is not None:
        logger.debug("trafilatura.extract falló: %s", error[0])
        return None

    return result[0]


def _fetch_article_content(url: str, timeout: int | None = None) -> str | None:
    """Extrae el texto principal de un artículo desde su URL.

    Usa requests para descargar la página y trafilatura para extraer
    el contenido relevante, descartando navegación, publicidad y otros
    elementos no textuales.

    Args:
        url: URL del artículo a extraer.
        timeout: Timeout HTTP en segundos. Si es None, usa FULL_CONTENT_TIMEOUT.

    Returns:
        Texto extraído del artículo, o None si ocurre cualquier error.
    """
    fetch_timeout = timeout if timeout is not None else FULL_CONTENT_TIMEOUT

    try:
        # Timeout partido: (connect, read) para detectar cuelgues más rápido
        response = requests.get(
            url,
            timeout=(5, fetch_timeout),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "es-CL,es;q=0.9",
            },
        )
        response.raise_for_status()

        # Extraer con timeout para evitar cuelgues en HTML patológico
        extracted = _extract_with_timeout(response.text, fetch_timeout)

        if extracted is None:
            logger.debug(
                "trafilatura.extract no pudo extraer contenido de %s", url
            )
            return None

        return extracted.strip()

    except Exception as exc:
        logger.debug(
            "Error al extraer contenido de %s: %s", url, exc
        )
        return None


def _is_feed_enabled(feed_config: dict[str, Any] | None) -> bool:
    """Verifica si el enriquecimiento está habilitado para un feed específico.

    Args:
        feed_config: Diccionario de configuración del feed, o None.

    Returns:
        True si el enriquecimiento está habilitado para este feed.
    """
    if feed_config is None:
        return FULL_CONTENT_FETCH_ENABLED

    return feed_config.get("enrich", FULL_CONTENT_FETCH_ENABLED)


def _get_feed_min_length(feed_config: dict[str, Any] | None) -> int | None:
    """Obtiene el umbral de longitud mínima configurado por feed.

    Args:
        feed_config: Diccionario de configuración del feed, o None.

    Returns:
        Umbral en caracteres, o None si no está configurado (usar default).
    """
    if feed_config is None:
        return None

    return feed_config.get("min_summary_length")


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------


def enrich_items(
    raw_items: list[dict[str, Any]],
    feeds_config: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enriquece artículos con resúmenes cortos extrayendo su contenido completo.

    Procesa los artículos en paralelo usando ThreadPoolExecutor, con rate
    limiting por dominio y caché en archivo para evitar descargas repetidas.

    El enriquecimiento es best-effort: si falla la extracción, el artículo
    se conserva sin modificar y se usa su resumen RSS original.

    Args:
        raw_items: Lista de artículos crudos desde el fetcher RSS. Cada uno
                   debe tener las claves 'title', 'source', 'summary', 'link'.
        feeds_config: Lista de configuraciones de feeds (desde rss_feeds.json).
                      Se usa para aplicar configuraciones por-feed.

    Returns:
        Lista de artículos enriquecidos. Se agrega la clave 'full_content'
        cuando se logra extraer contenido adicional. Todos los campos
        originales se preservan intactos.
    """
    if not raw_items:
        return []

    # Construir mapa de feed por nombre para búsqueda rápida
    feed_map: dict[str, dict[str, Any]] = {
        feed["name"]: feed for feed in feeds_config
    }

    # Determinar qué artículos necesitan enriquecimiento
    to_enrich: list[tuple[int, dict[str, Any]]] = []

    for idx, item in enumerate(raw_items):
        source = item.get("source", "")
        feed_config = feed_map.get(source)

        if not _is_feed_enabled(feed_config):
            continue

        min_length = _get_feed_min_length(feed_config)
        summary = item.get("summary")
        link = item.get("link")

        if _should_enrich(summary, min_length) and link:
            to_enrich.append((idx, item))

    if not to_enrich:
        logger.info(
            "Enriquecimiento: 0/%d artículos requieren extracción.",
            len(raw_items),
        )
        return raw_items  # Sin cambios, preserva orden original

    logger.info(
        "Enriquecimiento: %d/%d artículos serán procesados en paralelo "
        "(%d workers, rate limit %.1fs por dominio).",
        len(to_enrich),
        len(raw_items),
        FULL_CONTENT_MAX_WORKERS,
        FULL_CONTENT_DELAY,
    )

    # Cargar caché
    cache_dir = Path(FULL_CONTENT_CACHE_DIR)
    cache_path = cache_dir / "enriched_content.json"
    cache = _load_cache(cache_path)
    cache_hits = 0

    # Estado compartido thread-safe
    domain_lock = threading.Lock()
    domain_last_request: dict[str, float] = {}
    results_lock = threading.Lock()
    enriched_count = 0
    failed_count = 0

    def enrich_one(idx: int, item: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Tarea de enriquecimiento para un artículo individual."""
        nonlocal cache_hits, enriched_count, failed_count

        link = item["link"]
        cache_key = _url_cache_key(link)

        # Verificar caché
        if cache_key in cache:
            with results_lock:
                cache_hits += 1
            enriched_item = dict(item)
            enriched_item["full_content"] = cache[cache_key]
            return (idx, enriched_item)

        # Rate limiting por dominio
        domain = _extract_domain(link)
        with domain_lock:
            last = domain_last_request.get(domain, 0)
            elapsed = time.time() - last
            if elapsed < FULL_CONTENT_DELAY:
                time.sleep(FULL_CONTENT_DELAY - elapsed)
            domain_last_request[domain] = time.time()

        # Extraer contenido
        title_preview = item.get("title", "Sin título")[:60]
        source = item.get("source", "")
        summary_len = (
            len(item["summary"].strip()) if item.get("summary") else 0
        )
        logger.info(
            "Enriqueciendo: %s (%s) — resumen RSS: %d chars [%s]",
            title_preview,
            source,
            summary_len,
            domain,
        )

        full_content = _fetch_article_content(link)

        if full_content:
            cache[cache_key] = full_content
            with results_lock:
                enriched_count += 1
            enriched_item = dict(item)
            enriched_item["full_content"] = full_content
            logger.info(
                "  → Contenido extraído: %d caracteres", len(full_content)
            )
            return (idx, enriched_item)
        else:
            with results_lock:
                failed_count += 1
            logger.info(
                "  → No se pudo extraer contenido. Se usará resumen RSS."
            )
            return (idx, dict(item))

    # Procesar en paralelo y recolectar resultados por índice original
    results_by_idx: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=FULL_CONTENT_MAX_WORKERS) as executor:
        futures = {
            executor.submit(enrich_one, idx, item): idx
            for idx, item in to_enrich
        }

        for future in as_completed(futures):
            try:
                idx, result_item = future.result()
                results_by_idx[idx] = result_item
            except Exception as exc:
                logger.warning(
                    "Error inesperado en worker de enriquecimiento: %s", exc
                )
                orig_idx = futures[future]
                results_by_idx[orig_idx] = dict(to_enrich[orig_idx][1])

    # Persistir caché
    try:
        _save_cache(cache_path, cache)
        logger.debug("Caché guardado: %d entradas en %s", len(cache), cache_path)
    except IOError as exc:
        logger.debug("No se pudo guardar el caché: %s", exc)

    # Reconstruir lista en orden original
    result: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_items):
        if idx in results_by_idx:
            result.append(results_by_idx[idx])
        else:
            result.append(item)

    logger.info(
        "Enriquecimiento completado: %d extraídos, %d fallidos, "
        "%d desde caché, %d sin cambios.",
        enriched_count,
        failed_count,
        cache_hits,
        len(raw_items) - len(to_enrich),
    )

    return result
