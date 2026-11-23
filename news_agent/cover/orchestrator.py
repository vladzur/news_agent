"""Orquestador del subsistema de portadas editoriales.

Coordina el flujo completo a partir de un artículo ya publicado: carga de la
configuración visual, parseo del artículo, resolución de sección y tratamiento,
renderizado determinista con Pillow y escritura del bundle.

No interviene ningún LLM: la portada es reproducible y no consume tokens. Un
fallo de un formato no impide guardar el otro; si ninguno se puede renderizar,
el flujo aborta sin escribir un manifiesto incompleto.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import (
    DEFAULT_COVERS_OUTPUT_DIR,
    ConfigurationError,
    load_cover_config,
)
from ..orchestrator import setup_logging
from ..social.article_source import ArticleParseError, parse_article_file
from ..social.banner_renderer import brand_name
from .models import CoverOutput
from .renderer import (
    CoverRenderError,
    render_cover,
    save_cover_image,
)
from .source import (
    article_date,
    build_content,
    slug_for_article,
    source_sha256,
)
from .specs import category_for_article, cover_specs, format_specs
from .writer import (
    build_bundle_dir,
    metadata_path,
    read_metadata,
    save_metadata,
)

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class CoverError(Exception):
    """Excepción para errores fatales del subsistema de portadas.

    Attributes:
        code: Código de salida sugerido para el CLI. Los errores de uso
              (sección o tratamiento inexistente) usan 2; el resto, 1.
    """

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _merge_warnings(*groups: list[str]) -> list[str]:
    """Une advertencias conservando el orden y sin duplicados.

    Args:
        *groups: Listas de advertencias.

    Returns:
        list[str]: Advertencias únicas en orden de aparición.
    """
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for warning in group:
            if warning and warning not in seen:
                seen.add(warning)
                merged.append(warning)
    return merged


def _matches_existing(
    existing: dict[str, Any],
    digest: str,
    category: str,
    treatment: str,
) -> bool:
    """Indica si el manifiesto existente ya corresponde a esta portada.

    Args:
        existing: Manifiesto leído del bundle.
        digest: Huella del artículo.
        category: Sección resuelta.
        treatment: Tratamiento resuelto.

    Returns:
        bool: True si la portada no necesita regenerarse.
    """
    return (
        existing.get("source_sha256") == digest
        and existing.get("category") == category
        and existing.get("treatment") == treatment
    )


def _filename_for(outputs: list[CoverOutput], name: str) -> str | None:
    """Devuelve el nombre de archivo de un formato, si se generó.

    Args:
        outputs: Piezas renderizadas.
        name: Identificador del formato.

    Returns:
        str | None: Nombre del PNG, o None si no se generó.
    """
    for output in outputs:
        if output.format.name == name and output.path is not None:
            return output.path.name
    return None


def _first_filename(outputs: list[CoverOutput]) -> str | None:
    """Devuelve el nombre del primer PNG generado.

    Args:
        outputs: Piezas renderizadas.

    Returns:
        str | None: Nombre del primer PNG disponible, o None.
    """
    for output in outputs:
        if output.path is not None:
            return output.path.name
    return None


# ---------------------------------------------------------------------------
# Flujo principal
# ---------------------------------------------------------------------------


def run_cover(
    article_path: str | Path,
    output_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    category: str | None = None,
    treatment: str = "auto",
    verbose: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Genera la portada editorial de un artículo.

    Args:
        article_path: Ruta al artículo Markdown.
        output_dir: Directorio base de salida. Por defecto ``portadas/``.
        config_path: Ruta a la configuración visual. Por defecto
                     ``social_config.json``.
        category: Sección pedida. Si se omite, se deduce del número editorial.
        treatment: Tratamiento pedido (``auto``, ``text_first``, ``quote`` o
                   ``data``).
        verbose: Si es True, activa logging DEBUG.
        force: Si es True, regenera aunque exista una portada equivalente.

    Returns:
        dict con las claves:
            - bundle_dir (Path): Carpeta del bundle.
            - title (str): Titular de la portada.
            - category (str): Sección oficial.
            - treatment (str): Tratamiento efectivo.
            - treatment_label (str): Nombre legible del tratamiento.
            - formats (list[dict]): Piezas con nombre, tamaño, ruta y error.
            - metadata_path (Path): Ruta del manifiesto.
            - alt_text (str): Texto alternativo.
            - warnings (list[str]): Advertencias editoriales.
            - skipped (bool): True si no se regeneró.
            - failed_count (int): Formatos que no se pudieron renderizar.

    Raises:
        CoverError: Si falta la configuración, el artículo no se puede parsear,
                    la sección o el tratamiento no son válidos, o ningún
                    formato se puede renderizar.
    """
    setup_logging(verbose)
    logger.info("=== Iniciando portada editorial ===")

    try:
        config = load_cover_config(config_path)
    except ConfigurationError as exc:
        raise CoverError(f"Error de configuración de portadas: {exc}") from exc

    specs = cover_specs(config)

    try:
        article = parse_article_file(article_path)
    except ArticleParseError as exc:
        raise CoverError(
            f"No se pudo leer el artículo de origen: {exc}"
        ) from exc

    try:
        resolved_category = category_for_article(
            article_path, specs, category
        )
        content = build_content(
            article,
            resolved_category,
            treatment,
            specs,
            brand_name=brand_name(config),
        )
    except ValueError as exc:
        raise CoverError(str(exc), code=2) from exc

    logger.info(
        "Artículo cargado: \"%s\" (%d palabras). Sección: %s. Tratamiento: %s.",
        content.title,
        article.word_count,
        content.category,
        content.treatment,
    )

    base_dir = (
        Path(output_dir) if output_dir else Path(DEFAULT_COVERS_OUTPUT_DIR)
    )
    when = article_date(article_path) or datetime.now(timezone.utc)
    bundle_dir = build_bundle_dir(
        base_dir, slug_for_article(article), when=when
    )
    logger.info("Bundle de portada: %s", bundle_dir)

    digest = source_sha256(article)
    existing = read_metadata(bundle_dir)
    if (
        existing is not None
        and not force
        and _matches_existing(
            existing, digest, content.category, content.treatment
        )
    ):
        logger.info(
            "La portada ya existe para este artículo y configuración: se "
            "omite el renderizado (usa --force para regenerar)."
        )
        return {
            "bundle_dir": bundle_dir,
            "title": str(existing.get("title", content.title)),
            "category": str(existing.get("category", content.category)),
            "treatment": str(existing.get("treatment", content.treatment)),
            "treatment_label": str(
                existing.get("treatment_label", content.treatment_label)
            ),
            "formats": list(existing.get("formats", [])),
            "metadata_path": metadata_path(bundle_dir),
            "alt_text": str(existing.get("alt_text", content.alt_text)),
            "warnings": list(existing.get("warnings", [])),
            "skipped": True,
            "failed_count": 0,
        }

    try:
        formats = format_specs(specs)
    except ValueError as exc:
        raise CoverError(str(exc)) from exc
    if not formats:
        raise CoverError(
            "La configuración de portadas no declara ningún formato de salida."
        )
    outputs: list[CoverOutput] = []
    render_warnings: list[str] = []

    for format_spec in formats:
        destination = bundle_dir / format_spec.filename
        try:
            image, warnings = render_cover(
                content, format_spec, config, specs
            )
            path = save_cover_image(image, destination)
        except (CoverRenderError, OSError) as exc:
            logger.error(
                "No se pudo renderizar la portada %s: %s",
                format_spec.name,
                exc,
            )
            outputs.append(
                CoverOutput(
                    format=format_spec,
                    path=None,
                    error=str(exc),
                )
            )
            continue
        except Exception as exc:  # noqa: BLE001 - un formato no rompe el lote
            logger.error(
                "Fallo inesperado al renderizar la portada %s: %s",
                format_spec.name,
                exc,
            )
            outputs.append(
                CoverOutput(
                    format=format_spec,
                    path=None,
                    error=str(exc),
                )
            )
            continue

        render_warnings.extend(warnings)
        logger.info(
            "Portada generada: %s (%dx%d).",
            destination.name,
            format_spec.width,
            format_spec.height,
        )
        outputs.append(
            CoverOutput(
                format=format_spec,
                path=path,
                error="",
            )
        )

    successful = [output for output in outputs if output.path is not None]
    if not successful:
        errors = "; ".join(
            output.error for output in outputs if output.error
        )
        raise CoverError(
            "No se pudo renderizar ninguna portada"
            + (f": {errors}" if errors else ".")
        )

    content.warnings = _merge_warnings(content.warnings, render_warnings)
    header_image = (
        _filename_for(outputs, "web")
        or _filename_for(outputs, "og")
        or _first_filename(outputs)
    )
    og_image = _filename_for(outputs, "og") or header_image

    metadata: dict[str, Any] = {
        "title": content.title,
        "category": content.category,
        "treatment": content.treatment,
        "treatment_label": content.treatment_label,
        "deck": content.deck,
        "quote": content.quote,
        "figure": content.figure,
        "caption": content.caption,
        "byline": content.byline,
        "alt_text": content.alt_text,
        "header_image": header_image,
        "og_image": og_image,
        "source_path": str(Path(article_path).resolve()),
        "source_sha256": digest,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "formats": [output.to_dict() for output in outputs],
        "warnings": content.warnings,
    }
    try:
        saved_metadata = save_metadata(metadata, bundle_dir)
    except OSError as exc:
        raise CoverError(
            f"No se pudo guardar el manifiesto de la portada: {exc}"
        ) from exc

    failed_count = sum(1 for output in outputs if output.path is None)

    return {
        "bundle_dir": bundle_dir,
        "title": content.title,
        "category": content.category,
        "treatment": content.treatment,
        "treatment_label": content.treatment_label,
        "formats": [output.to_dict() for output in outputs],
        "metadata_path": saved_metadata,
        "alt_text": content.alt_text,
        "warnings": content.warnings,
        "skipped": False,
        "failed_count": failed_count,
    }
