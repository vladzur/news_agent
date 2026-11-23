"""Resolución de secciones, tratamientos y formatos de las portadas.

La sección ``covers`` de ``social_config.json`` es la fuente de verdad para la
taxonomía, los acentos y los tamaños. Este módulo fusiona esa configuración
con los defaults del código, de modo que una configuración parcial siga siendo
utilizable y que el resto del subsistema no repita reglas de negocio.
"""

import re
from pathlib import Path
from typing import Any

from ..config import (
    COVER_CATEGORIES,
    COVER_DEFAULT_CATEGORY,
    COVER_DEFAULT_TREATMENT,
    COVER_FORMATS,
    COVER_LIMITS,
    COVER_PROPOSAL_CATEGORIES,
    COVER_TEXTURE_INTENSITY,
    COVER_TREATMENT_LABELS,
    COVER_TREATMENTS,
)
from .models import CoverFormat
from .text_utils import fold_text

# Orden editorial de los formatos en el manifiesto y en el resumen del CLI.
_FORMAT_ORDER = ("og", "web")

# Tratamiento al que se cae cuando falta la materia prima del tratamiento
# pedido. La portada tipográfica siempre está disponible.
FALLBACK_TREATMENT = "text_first"


def cover_specs(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Devuelve las especificaciones de portada ya resueltas.

    Args:
        config: Configuración cargada con ``load_cover_config``. Si es None o
            no trae la sección ``covers``, se usan los defaults del código.

    Returns:
        dict[str, Any]: Categorías, formatos, límites, textura, categoría por
        defecto y mapa propuesta → categoría.
    """
    covers = config.get("covers") if isinstance(config, dict) else None
    covers = covers if isinstance(covers, dict) else {}

    categories = {
        name: dict(spec) for name, spec in COVER_CATEGORIES.items()
    }
    declared_categories = covers.get("categories")
    if isinstance(declared_categories, dict):
        for name, spec in declared_categories.items():
            if not isinstance(spec, dict):
                continue
            default_accent = categories.get(name, {}).get("accent", "#DF3224")
            categories[name] = {
                "label": str(spec.get("label", name)),
                "accent": str(spec.get("accent", default_accent)),
            }

    formats = {name: dict(spec) for name, spec in COVER_FORMATS.items()}
    declared_formats = covers.get("formats")
    if isinstance(declared_formats, dict):
        for name, spec in declared_formats.items():
            if not isinstance(spec, dict):
                continue
            base = formats.get(name, {})
            formats[name] = {
                "width": int(spec.get("width", base.get("width", 0))),
                "height": int(spec.get("height", base.get("height", 0))),
                "filename": str(
                    spec.get("filename", base.get("filename", ""))
                ),
            }

    limits = {key: int(value) for key, value in COVER_LIMITS.items()}
    declared_limits = covers.get("limits")
    if isinstance(declared_limits, dict):
        limits.update(
            {
                key: int(value)
                for key, value in declared_limits.items()
                if key in limits
            }
        )

    texture = {"intensity": COVER_TEXTURE_INTENSITY}
    declared_texture = covers.get("texture")
    if isinstance(declared_texture, dict):
        texture["intensity"] = float(
            declared_texture.get("intensity", COVER_TEXTURE_INTENSITY)
        )

    proposal_categories = covers.get("proposal_categories")
    if (
        not isinstance(proposal_categories, (list, tuple))
        or not proposal_categories
    ):
        proposal_categories = list(COVER_PROPOSAL_CATEGORIES)

    return {
        "categories": categories,
        "formats": formats,
        "limits": limits,
        "texture": texture,
        "default_category": covers.get(
            "default_category", COVER_DEFAULT_CATEGORY
        ),
        "proposal_categories": list(proposal_categories),
    }


def format_specs(specs: dict[str, Any]) -> list[CoverFormat]:
    """Construye los formatos de salida en orden editorial.

    Args:
        specs: Especificaciones resueltas.

    Returns:
        list[CoverFormat]: Formatos con nombre, tamaño y archivo.

    Raises:
        ValueError: Si un formato no declara dimensiones positivas.
    """
    formats = specs.get("formats", {})
    ordered = [name for name in _FORMAT_ORDER if name in formats]
    ordered.extend(sorted(name for name in formats if name not in _FORMAT_ORDER))

    result: list[CoverFormat] = []
    for name in ordered:
        spec = formats[name]
        width = int(spec.get("width", 0))
        height = int(spec.get("height", 0))
        filename = str(spec.get("filename", "")).strip()
        if width <= 0 or height <= 0 or not filename:
            raise ValueError(
                f"El formato de portada '{name}' no tiene dimensiones o "
                "nombre de archivo válidos."
            )
        result.append(
            CoverFormat(
                name=name,
                width=width,
                height=height,
                filename=filename,
            )
        )
    return result


def resolve_category(name: str, specs: dict[str, Any]) -> str:
    """Resuelve el nombre de una sección contra la taxonomía oficial.

    La comparación ignora mayúsculas y acentos, pero devuelve la clave oficial
    que el sitio espera.

    Args:
        name: Nombre pedido por el editor.
        specs: Especificaciones resueltas.

    Returns:
        str: Clave oficial de la categoría.

    Raises:
        ValueError: Si la categoría no existe en la taxonomía.
    """
    categories = specs.get("categories", {})
    target = fold_text(name)
    for key in categories:
        if fold_text(key) == target:
            return key

    raise ValueError(
        f"Sección desconocida: {name!r}. Opciones válidas: "
        f"{', '.join(sorted(categories))}."
    )


def category_for_article(
    article_path: str | Path,
    specs: dict[str, Any],
    requested: str | None = None,
) -> str:
    """Determina la sección de una nota.

    Prioridad: la sección pedida por el editor, el número editorial del
    artículo (1–3 nacionales, 4–5 internacionales) y, por último, la sección
    por defecto.

    Args:
        article_path: Ruta del artículo, de donde se toma el número editorial.
        specs: Especificaciones resueltas.
        requested: Sección pedida con ``--category``, o None.

    Returns:
        str: Clave oficial de la categoría.
    """
    if requested:
        return resolve_category(requested, specs)

    match = re.match(r"articulo_(\d+)", Path(article_path).name)
    if match is not None:
        index = int(match.group(1)) - 1
        proposals = specs.get("proposal_categories", [])
        if 0 <= index < len(proposals):
            return str(proposals[index])

    return str(specs.get("default_category", COVER_DEFAULT_CATEGORY))


def treatment_label(treatment: str) -> str:
    """Devuelve el nombre legible de un tratamiento.

    Args:
        treatment: Identificador del tratamiento.

    Returns:
        str: Etiqueta en español; el identificador si no hay etiqueta.
    """
    return COVER_TREATMENT_LABELS.get(treatment, treatment)


def resolve_treatment(
    requested: str | None,
    category: str,
    has_quote: bool,
    has_figure: bool,
    strong_figure: bool = False,
) -> tuple[str, list[str]]:
    """Elige el tratamiento de la portada y registra las caídas.

    Reglas automáticas: ``Opinión`` con cita utilizable usa ``quote``; una
    cifra en el titular o en el arranque del lead usa ``data``; el resto usa
    ``text_first``. Un tratamiento pedido a mano se respeta, salvo que falte
    la materia prima: en ese caso se cae a ``text_first`` con advertencia.

    Args:
        requested: Tratamiento pedido (``auto`` o uno de COVER_TREATMENTS).
        category: Sección oficial de la nota.
        has_quote: True si hay una cita extraíble.
        has_figure: True si hay una cifra extraíble.
        strong_figure: True si la cifra aparece en el titular o en el arranque
            del lead, no solo en el cuerpo.

    Returns:
        tuple[str, list[str]]: Tratamiento efectivo y advertencias.

    Raises:
        ValueError: Si el tratamiento pedido no existe.
    """
    warnings: list[str] = []
    selected = (requested or COVER_DEFAULT_TREATMENT).strip().lower()

    if selected not in ("auto", *COVER_TREATMENTS):
        raise ValueError(
            f"Tratamiento desconocido: {requested!r}. Opciones válidas: "
            f"auto, {', '.join(COVER_TREATMENTS)}."
        )

    if selected != "auto":
        if selected == "quote" and not has_quote:
            warnings.append(
                "Se pidió el tratamiento de cita, pero el artículo no tiene "
                "una cita utilizable: se usa la portada tipográfica."
            )
            return FALLBACK_TREATMENT, warnings
        if selected == "data" and not has_figure:
            warnings.append(
                "Se pidió el tratamiento de dato duro, pero el artículo no "
                "tiene una cifra utilizable: se usa la portada tipográfica."
            )
            return FALLBACK_TREATMENT, warnings
        return selected, warnings

    if fold_text(category) == fold_text("Opinión"):
        if has_quote:
            return "quote", warnings
        warnings.append(
            "La sección es Opinión, pero el artículo no tiene una cita "
            "utilizable: se usa la portada tipográfica."
        )
        return FALLBACK_TREATMENT, warnings

    if strong_figure:
        return "data", warnings

    return FALLBACK_TREATMENT, warnings
