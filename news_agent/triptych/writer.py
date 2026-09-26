"""Escritura del bundle del tríptico impreso.

Cada ejecución produce una carpeta autocontenida con el tríptico en JSON, el
mismo contenido en Markdown —panel por panel, con el reporte de largo de cada
nota— y un manifiesto que registra la pauta de origen, las medidas del papel y
las advertencias que quedaron pendientes de ajuste manual.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import PrintNote, TriptychPackage
from .pauta_source import TriptychSource
from .specs import (
    block_max_chars,
    chars_per_line,
    column_max_chars,
    format_length_report,
    lines_per_column,
)

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# Nombres de los archivos del bundle.
TRIPTYCH_FILE_NAME = "triptych.json"
MARKDOWN_FILE_NAME = "triptych.md"
MANIFEST_FILE_NAME = "manifest.json"

# Sufijo de la carpeta del bundle: la edición se identifica por su pauta.
BUNDLE_SUFFIX = "pauta-semanal"

# Nombre legible de cada tipo de pliegue, para la nota de armado.
FOLD_LABELS: dict[str, str] = {
    "roll": "tríptico de cartera (roll fold)",
    "gate": "tríptico de puerta (gate fold)",
    "z": "tríptico en Z (z-fold)",
}

# Fecha de la pauta en el nombre del archivo (pauta_semanal_AAAA_MM_DD.md).
_PAUTA_DATE_RE = re.compile(r"\d{4}_\d{2}_\d{2}")


# ---------------------------------------------------------------------------
# Estructura del bundle
# ---------------------------------------------------------------------------


def date_from_pauta(pauta_path: str | Path) -> str | None:
    """Extrae la fecha de la edición desde el nombre de la pauta.

    Args:
        pauta_path: Ruta a la pauta semanal.

    Returns:
        str | None: Fecha en formato ``AAAA_MM_DD``, o None si el nombre no
        la incluye.
    """
    match = _PAUTA_DATE_RE.search(Path(pauta_path).stem)

    return match.group(0) if match else None


def build_bundle_dir(
    output_dir: str | Path,
    pauta_path: str | Path,
    when: datetime | None = None,
) -> Path:
    """Crea y devuelve el directorio del bundle del tríptico.

    El nombre usa la fecha de la pauta, no la de ejecución: así la carpeta
    corresponde a la edición que se imprime, aunque el tríptico se genere días
    después.

    Args:
        output_dir: Directorio base de salida (ej: "impresos").
        pauta_path: Ruta a la pauta de origen.
        when: Momento de la generación, usado si la pauta no trae fecha.

    Returns:
        Path: Ruta absoluta al directorio del bundle, ya creado.
    """
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)

    moment = when or datetime.now(timezone.utc)
    stamp = date_from_pauta(pauta_path) or moment.strftime("%Y_%m_%d")
    bundle_dir = (base / f"{stamp}_{BUNDLE_SUFFIX}").resolve()

    if bundle_dir.exists():
        logger.info("El bundle ya existía y será sobrescrito: %s", bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    return bundle_dir


# ---------------------------------------------------------------------------
# Escritura de archivos
# ---------------------------------------------------------------------------


def _dump_json(payload: Any, file_path: Path) -> Path:
    """Escribe un payload como JSON legible en UTF-8.

    Args:
        payload: Datos serializables.
        file_path: Ruta del archivo de destino.

    Returns:
        Path: Ruta absoluta del archivo escrito.
    """
    with open(file_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    logger.info("JSON guardado: %s", file_path.resolve())

    return file_path.resolve()


def save_triptych_json(package: TriptychPackage, bundle_dir: str | Path) -> Path:
    """Guarda el tríptico completo como JSON.

    Args:
        package: Tríptico generado.
        bundle_dir: Directorio del bundle.

    Returns:
        Path: Ruta absoluta del archivo escrito.
    """
    return _dump_json(package.to_dict(), Path(bundle_dir) / TRIPTYCH_FILE_NAME)


def save_markdown(content: str, bundle_dir: str | Path) -> Path:
    """Guarda el tríptico en Markdown legible.

    Args:
        content: Markdown del tríptico.
        bundle_dir: Directorio del bundle.

    Returns:
        Path: Ruta absoluta del archivo escrito.
    """
    file_path = Path(bundle_dir) / MARKDOWN_FILE_NAME
    file_path.write_text(content, encoding="utf-8")
    logger.info("Markdown guardado: %s", file_path.resolve())

    return file_path.resolve()


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _render_header(
    package: TriptychPackage,
    source: TriptychSource,
    specs: dict[str, Any],
) -> list[str]:
    """Redacta el encabezado del Markdown con los datos de la edición.

    Args:
        package: Tríptico generado.
        source: Material de origen.
        specs: Especificaciones resueltas.

    Returns:
        list[str]: Líneas del encabezado.
    """
    page = specs["page"]
    typography = specs["typography"]
    limits = specs["limits"]
    fold = FOLD_LABELS.get(package.fold, package.fold)
    stamp = date_from_pauta(source.pauta_path) or package.generated_at[:10]

    return [
        f"# Tríptico impreso: {package.cover.title}",
        "",
        f"**Edición:** {stamp}  ",
        f"**Pauta de origen:** `{source.pauta_path}`  ",
        (
            f"**Formato:** oficio {page['width_mm']:.1f} × "
            f"{page['height_mm']:.1f} mm · {package.panels} paneles "
            f"({package.sides} caras × {package.columns_per_side} columnas) · "
            f"{typography['family']} {typography['size_pt']:.0f} pt  "
        ),
        f"**Pliegue:** {fold}  ",
        f"**Tope por nota:** {limits['block_max_columns']} columnas  ",
        "",
        "## Cómo se arma",
        "",
        (
            "Orden lógico de los paneles: el 1 es la portada y del 2 al "
            f"{len(package.notes) + 1} van las notas, una por panel. La "
            "imposición definitiva (qué panel cae en cada cara de la hoja) "
            "se confirma con la imprenta según el tipo de pliegue."
        ),
        "",
    ]


def _render_cover(package: TriptychPackage) -> list[str]:
    """Redacta el panel de portada.

    Args:
        package: Tríptico generado.

    Returns:
        list[str]: Líneas del panel de portada.
    """
    return [
        "## Panel 1 — Portada",
        "",
        f"**Gancho:** {package.cover.hook}",
        "",
        f"**Título:** {package.cover.title}",
        "",
    ]


def _render_note(note: PrintNote) -> list[str]:
    """Redacta un panel de nota con sus bloques y su reporte de largo.

    Args:
        note: Nota a redactar.

    Returns:
        list[str]: Líneas del panel.
    """
    lines: list[str] = [
        f"## Panel {note.panel} — {note.title}",
        "",
        f"**Propuesta:** {note.proposal_number}  ",
        (
            f"**Largo:** {format_length_report(note.measurement)} "
            f"(tope {note.measurement['block_max_columns']} columnas)  "
        ),
    ]

    if note.sources:
        lines.append(f"**Fuentes:** {'; '.join(note.sources)}  ")

    lines += ["", note.body, ""]

    if note.key_data:
        lines.append(f"**En {len(note.key_data)} datos clave**")
        lines.append("")
        for index, item in enumerate(note.key_data, start=1):
            lines.append(f"{index}. {item}")
        lines.append("")

    if note.why_it_matters:
        lines += ["**Por qué te importa**", "", note.why_it_matters, ""]

    if note.warnings:
        lines.append("**Advertencias de esta nota**")
        lines.append("")
        lines += [f"- {warning}" for warning in note.warnings]
        lines.append("")

    return lines


def _render_warnings(package: TriptychPackage) -> list[str]:
    """Redacta el bloque final de advertencias pendientes.

    Args:
        package: Tríptico generado.

    Returns:
        list[str]: Líneas del bloque de advertencias, o lista vacía si no hay.
    """
    notes_warnings = [
        warning for note in package.notes for warning in note.warnings
    ]
    if not package.warnings and not notes_warnings:
        return []

    lines = ["---", "", "## Advertencias pendientes", ""]
    lines += [f"- {warning}" for warning in package.warnings]

    return lines + [f"- {warning}" for warning in notes_warnings] + [""]


def render_triptych_markdown(
    package: TriptychPackage,
    source: TriptychSource,
    specs: dict[str, Any],
) -> str:
    """Redacta el tríptico completo en Markdown, panel por panel.

    Args:
        package: Tríptico generado.
        source: Material de origen.
        specs: Especificaciones resueltas.

    Returns:
        str: Markdown listo para leer o pegar en la plantilla de diseño.
    """
    lines = _render_header(package, source, specs)
    lines += _render_cover(package)

    for note in package.notes:
        lines += _render_note(note)

    lines += _render_warnings(package)

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Manifiesto
# ---------------------------------------------------------------------------


def _note_summary(note: PrintNote) -> dict[str, Any]:
    """Resume una nota para el manifiesto.

    Args:
        note: Nota a resumir.

    Returns:
        dict[str, Any]: Panel, propuesta, título, mediciones y advertencias.
    """
    return {
        "panel": note.panel,
        "proposal_number": note.proposal_number,
        "title": note.title,
        "chars": note.measurement.get("chars"),
        "lines": note.measurement.get("lines"),
        "columns": note.measurement.get("columns"),
        "within_block_max": note.within_block_max,
        "body_chars": note.measurement.get("body", {}).get("chars"),
        "warnings": list(note.warnings),
    }


def save_manifest(
    package: TriptychPackage,
    source: TriptychSource,
    bundle_dir: str | Path,
    specs: dict[str, Any],
) -> Path:
    """Guarda el manifiesto con lo generado, lo medido y lo pendiente.

    Args:
        package: Tríptico generado.
        source: Material de origen.
        bundle_dir: Directorio del bundle.
        specs: Especificaciones resueltas.

    Returns:
        Path: Ruta absoluta del archivo escrito.
    """
    notes = [_note_summary(note) for note in package.notes]
    page = specs["page"]
    limits = specs["limits"]

    payload = {
        "generated_at": package.generated_at,
        "source": {
            "pauta_path": str(source.pauta_path),
            "proposal_count": len(source),
        },
        "format": {
            "preset": page.get("preset"),
            "width_mm": page["width_mm"],
            "height_mm": page["height_mm"],
            "columns_per_side": package.columns_per_side,
            "sides": package.sides,
            "panels": package.panels,
            "fold": package.fold,
            "font_family": specs["typography"]["family"],
            "font_size_pt": specs["typography"]["size_pt"],
        },
        "budget": {
            "chars_per_line": chars_per_line(specs, 1.0),
            "chars_per_line_block": chars_per_line(
                specs, limits["block_max_columns"]
            ),
            "lines_per_column": lines_per_column(specs),
            "column_max_chars": column_max_chars(specs),
            "block_max_chars": block_max_chars(specs),
            "block_max_columns": limits["block_max_columns"],
            "body_target_chars": limits["body_target_chars"],
        },
        "cover": package.cover.to_dict(),
        "notes": notes,
        "totals": {
            "notes": len(notes),
            "overflowing": len(package.overflowing_notes),
            "warnings": len(package.warnings)
            + sum(len(note.warnings) for note in package.notes),
        },
        "files": {
            "triptych": TRIPTYCH_FILE_NAME,
            "markdown": MARKDOWN_FILE_NAME,
        },
        "warnings": list(package.warnings),
    }

    return _dump_json(payload, Path(bundle_dir) / MANIFEST_FILE_NAME)
