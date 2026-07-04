"""Módulo orquestador del agente de noticias.

Coordina el pipeline completo: configuración → ingesta RSS → filtrado →
construcción de prompts → llamado a LLM → escritura del reporte.
"""

import logging
import sys
from pathlib import Path
from typing import Any

from .config import ConfigurationError, get_api_key, load_rss_feeds
from .llm_client import LLMClient, LLMClientError
from .news_filter import filter_items
from .prompt_builder import build_system_prompt, build_user_prompt
from .report_writer import save_report
from .rss_fetcher import fetch_all

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class OrchestratorError(Exception):
    """Excepción personalizada para errores fatales del orquestador."""


def setup_logging(verbose: bool = False) -> None:
    """Configura el logging del agente.

    Args:
        verbose: Si es True, establece nivel DEBUG. En caso contrario, INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(level=level, format=fmt, datefmt=datefmt)


def run_pipeline(
    feeds_path: str | Path | None = None,
    output_dir: str | Path = ".",
    verbose: bool = False,
) -> dict[str, Any]:
    """Ejecuta el pipeline completo del agente de noticias.

    Args:
        feeds_path: Ruta al archivo JSON de feeds. None = usar default.
        output_dir: Directorio donde guardar el reporte generado.
        verbose: Si es True, activa logging DEBUG.

    Returns:
        dict con las claves:
            - report_path (Path): Ruta al archivo generado.
            - item_count (int): Cantidad de artículos analizados.
            - feed_count (int): Cantidad de feeds configurados.

    Raises:
        OrchestratorError: En caso de error fatal que impida continuar.
        SystemExit: Si no hay noticias que procesar o falla la configuración.
    """
    setup_logging(verbose)

    logger.info("=== Iniciando Agente de Pauta Editorial - La Chispa Sur ===")

    # -----------------------------------------------------------------------
    # Paso 1: Validar API Key
    # -----------------------------------------------------------------------
    try:
        api_key = get_api_key()
    except ConfigurationError as exc:
        logger.error("Error de configuración: %s", exc)
        sys.exit(1)

    logger.info("API Key de DeepSeek validada correctamente.")

    # -----------------------------------------------------------------------
    # Paso 2: Cargar feeds RSS
    # -----------------------------------------------------------------------
    try:
        feeds = load_rss_feeds(feeds_path)
    except ConfigurationError as exc:
        logger.error("Error al cargar feeds RSS: %s", exc)
        sys.exit(1)

    if not feeds:
        logger.warning(
            "No hay feeds RSS configurados. Agrega fuentes en rss_feeds.json."
        )
        sys.exit(0)

    logger.info("%d feed(s) RSS cargado(s) desde configuración.", len(feeds))

    # -----------------------------------------------------------------------
    # Paso 3: Obtener artículos de todos los feeds
    # -----------------------------------------------------------------------
    raw_items = fetch_all(feeds)
    logger.info("Total de artículos crudos recolectados: %d.", len(raw_items))

    # -----------------------------------------------------------------------
    # Paso 4: Filtrar por ventana de 72h, limpiar HTML y truncar
    # -----------------------------------------------------------------------
    filtered_items = filter_items(raw_items)

    # -----------------------------------------------------------------------
    # Paso 5: Guardia — si no hay noticias, no llamar a la API
    # -----------------------------------------------------------------------
    if not filtered_items:
        logger.warning(
            "No se encontraron noticias dentro de la ventana de 72 horas. "
            "Se omite la llamada a la API de DeepSeek para evitar consumo "
            "innecesario de tokens."
        )
        sys.exit(0)

    logger.info("%d artículo(s) después del filtrado.", len(filtered_items))

    # -----------------------------------------------------------------------
    # Paso 6: Construir prompts
    # -----------------------------------------------------------------------
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(filtered_items)

    logger.info(
        "Prompts construidos: system_prompt=%d chars, user_prompt=%d chars.",
        len(system_prompt),
        len(user_prompt),
    )

    # -----------------------------------------------------------------------
    # Paso 7: Llamar a la API de DeepSeek
    # -----------------------------------------------------------------------
    client = LLMClient(api_key=api_key)

    try:
        llm_response = client.generate_report(system_prompt, user_prompt)
    except LLMClientError as exc:
        logger.error("Fallo al generar el reporte con DeepSeek: %s", exc)
        sys.exit(1)

    if not llm_response or not llm_response.strip():
        logger.error(
            "La API de DeepSeek devolvió una respuesta vacía. "
            "No se generará el reporte."
        )
        sys.exit(1)

    logger.info("Reporte generado por DeepSeek: %d caracteres.", len(llm_response))

    # -----------------------------------------------------------------------
    # Paso 8: Guardar reporte en archivo Markdown
    # -----------------------------------------------------------------------
    try:
        report_path = save_report(llm_response, len(filtered_items), output_dir)
    except IOError as exc:
        logger.error("Error al guardar el reporte: %s", exc)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Paso 9: Resumen final
    # -----------------------------------------------------------------------
    logger.info("=== Pipeline completado exitosamente ===")
    logger.info("Reporte generado: %s", report_path)
    logger.info(
        "Estadísticas: %d feeds configurados, %d artículos crudos, "
        "%d artículos analizados.",
        len(feeds),
        len(raw_items),
        len(filtered_items),
    )

    return {
        "report_path": report_path,
        "item_count": len(filtered_items),
        "feed_count": len(feeds),
    }
