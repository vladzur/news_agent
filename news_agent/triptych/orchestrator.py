"""Orquestador del subsistema de tríptico impreso.

Coordina el flujo completo: configuración → clave de API → material de origen
desde la pauta → generación con el modelo → bundle en disco.

El flujo no tiene etapas tolerantes a propósito: si el modelo no devuelve un
tríptico que cumpla el contrato estructural, no se escribe nada, para no dejar
en disco una pieza impublicable. Las advertencias de estilo y de largo no
abortan: viajan al manifiesto y al Markdown para que el equipo editorial
ajuste a mano.
"""

import logging
import sys
from pathlib import Path
from typing import Any

from ..config import (
    DEFAULT_PRINT_OUTPUT_DIR,
    TRIPTYCH_MAX_TOKENS,
    TRIPTYCH_REASONING_EFFORT,
    TRIPTYCH_TEMPERATURE,
    ConfigurationError,
    get_api_key,
    load_triptych_config,
)
from ..llm_client import LLMClient, LLMClientError
from ..orchestrator import setup_logging
from .generator import TriptychGenerationError, generate_triptych
from .pauta_source import TriptychSourceError, load_triptych_source
from .specs import triptych_specs
from .writer import (
    build_bundle_dir,
    render_triptych_markdown,
    save_manifest,
    save_markdown,
    save_triptych_json,
)

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class TriptychError(Exception):
    """Excepción para errores fatales del flujo de tríptico impreso."""


# ---------------------------------------------------------------------------
# Helpers de preparación
# ---------------------------------------------------------------------------


def _load_config(config_path: str | Path | None) -> dict[str, Any]:
    """Carga la configuración del tríptico, abortando con un error claro.

    Args:
        config_path: Ruta al archivo de configuración, o None para la default.

    Returns:
        dict[str, Any]: Configuración cargada.
    """
    try:
        return load_triptych_config(config_path)
    except ConfigurationError as exc:
        logger.error("Error de configuración del tríptico: %s", exc)
        sys.exit(1)


def _resolve_api_key() -> str:
    """Obtiene la clave API, abortando con un error claro.

    Returns:
        str: Clave API de DeepSeek.
    """
    try:
        return get_api_key()
    except ConfigurationError as exc:
        logger.error("Error de configuración: %s", exc)
        sys.exit(1)


def _build_client(api_key: str) -> LLMClient:
    """Construye el cliente LLM del tríptico con salida JSON.

    Args:
        api_key: Clave API de DeepSeek.

    Returns:
        LLMClient: Cliente listo para generar el tríptico.
    """
    return LLMClient(
        api_key=api_key,
        temperature=TRIPTYCH_TEMPERATURE,
        max_tokens=TRIPTYCH_MAX_TOKENS,
        reasoning_effort=TRIPTYCH_REASONING_EFFORT,
        response_format={"type": "json_object"},
    )


# ---------------------------------------------------------------------------
# Flujo principal
# ---------------------------------------------------------------------------


def run_print(
    pauta_path: str | Path,
    output_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Genera el tríptico impreso a partir de la pauta semanal.

    Args:
        pauta_path: Ruta a la pauta semanal en Markdown.
        output_dir: Directorio base del bundle. Por defecto, "impresos".
        config_path: Ruta a la configuración del tríptico, o None para la
            default.
        verbose: Si es True, activa logging DEBUG.

    Returns:
        dict[str, Any]: Resumen del bundle generado, con las rutas de los
        archivos, la cantidad de notas y las advertencias pendientes.

    Raises:
        TriptychError: Si el modelo no logra producir un tríptico válido.
        SystemExit: Si falta la API key, la configuración es inválida o la
            pauta no se puede leer.
    """
    setup_logging(verbose)

    config = _load_config(config_path)
    api_key = _resolve_api_key()
    specs = triptych_specs(config)

    base_dir = Path(output_dir) if output_dir else Path(DEFAULT_PRINT_OUTPUT_DIR)

    logger.info("=== Iniciando tríptico impreso desde %s ===", pauta_path)

    try:
        source = load_triptych_source(
            pauta_path, notes=specs["layout"]["notes"]
        )
    except TriptychSourceError as exc:
        logger.error("No se pudo cargar el material de origen: %s", exc)
        sys.exit(1)

    client = _build_client(api_key)

    try:
        package = generate_triptych(source, config, client)
    except (TriptychGenerationError, LLMClientError) as exc:
        raise TriptychError(f"No se pudo generar el tríptico: {exc}") from exc

    bundle_dir = build_bundle_dir(base_dir, source.pauta_path)
    triptych_path = save_triptych_json(package, bundle_dir)
    markdown_path = save_markdown(
        render_triptych_markdown(package, source, specs), bundle_dir
    )
    manifest_path = save_manifest(package, source, bundle_dir, specs)

    overflowing = package.overflowing_notes
    if overflowing:
        panels = ", ".join(f"panel {note.panel}" for note in overflowing)
        logger.warning(
            "%d nota(s) superan el tope de %.1f columnas (%s). "
            "No se recortó nada: hay que ajustarlas a mano.",
            len(overflowing),
            specs["limits"]["block_max_columns"],
            panels,
        )

    return {
        "bundle_dir": bundle_dir,
        "triptych_path": triptych_path,
        "markdown_path": markdown_path,
        "manifest_path": manifest_path,
        "title": package.cover.title,
        "notes": len(package.notes),
        "panels": package.panels,
        "fold": package.fold,
        "overflowing": len(overflowing),
        "warnings": len(package.warnings)
        + sum(len(note.warnings) for note in package.notes),
    }
