"""Especificaciones de medida del tríptico impreso.

Traduce la geometría de la hoja (oficio, tres columnas por cara) y la
tipografía monospace a un presupuesto de caracteres verificable. Todo el
módulo es puro y no depende de Pillow: el tríptico se entrega como texto, así
que basta con contar caracteres y líneas para saber si una nota cabe en su
columna.
"""

from __future__ import annotations

import math
from typing import Any

from ..config import (
    NUM_PROPOSALS,
    TRIPTYCH_BLOCK_MAX_COLUMNS,
    TRIPTYCH_BODY_TARGET_CHARS,
    TRIPTYCH_CHAR_WIDTH_EM,
    TRIPTYCH_COLUMNS_PER_SIDE,
    TRIPTYCH_DEFAULT_FOLD,
    TRIPTYCH_FONT_FAMILY,
    TRIPTYCH_FONT_SIZE_PT,
    TRIPTYCH_KEY_DATA_ITEMS,
    TRIPTYCH_LINE_HEIGHT_RATIO,
    TRIPTYCH_MARGIN_MM,
    TRIPTYCH_MAX_WORDS_PER_SENTENCE,
    TRIPTYCH_PAGE_HEIGHT_MM,
    TRIPTYCH_PAGE_WIDTH_MM,
    TRIPTYCH_SIDES,
)

# Conversiones de unidades tipográficas a milímetros.
MM_PER_INCH = 25.4
POINTS_PER_INCH = 72.0

# Centinela que marca un valor de configuración descartado por inválido.
_UNSET = object()

# Especificaciones por defecto. Reflejan la estructura de ``triptych_config.json``
# para que la resolución de overrides sea una fusión sección por sección.
DEFAULT_SPECS: dict[str, Any] = {
    "page": {
        "preset": "oficio",
        "width_mm": TRIPTYCH_PAGE_WIDTH_MM,
        "height_mm": TRIPTYCH_PAGE_HEIGHT_MM,
        "margin_mm": TRIPTYCH_MARGIN_MM,
        "columns_per_side": TRIPTYCH_COLUMNS_PER_SIDE,
        "sides": TRIPTYCH_SIDES,
        "fold": TRIPTYCH_DEFAULT_FOLD,
    },
    "typography": {
        "family": TRIPTYCH_FONT_FAMILY,
        "size_pt": TRIPTYCH_FONT_SIZE_PT,
        "char_width_em": TRIPTYCH_CHAR_WIDTH_EM,
        "line_height_ratio": TRIPTYCH_LINE_HEIGHT_RATIO,
    },
    "limits": {
        "block_max_columns": TRIPTYCH_BLOCK_MAX_COLUMNS,
        "body_target_chars": TRIPTYCH_BODY_TARGET_CHARS,
    },
    "style": {
        "max_words_per_sentence": TRIPTYCH_MAX_WORDS_PER_SENTENCE,
        "acronym_allowlist": [],
        "forbidden_terms": [],
    },
    "layout": {
        "notes": NUM_PROPOSALS,
        "key_data_items": TRIPTYCH_KEY_DATA_ITEMS,
    },
}


def _is_number(value: object) -> bool:
    """Comprueba que el valor sea un número, excluyendo los booleanos.

    Args:
        value: Valor a comprobar.

    Returns:
        bool: True si es un entero o un decimal real.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _coerce_positive_int(value: object) -> object:
    """Acepta un entero mayor que cero y descarta cualquier otro valor.

    Args:
        value: Valor declarado en la configuración.

    Returns:
        object: El entero, o ``_UNSET`` si no sirve.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return _UNSET

    return value


def _coerce_positive_float(value: object) -> object:
    """Acepta un número mayor que cero y descarta cualquier otro valor.

    Args:
        value: Valor declarado en la configuración.

    Returns:
        object: El decimal, o ``_UNSET`` si no sirve.
    """
    if not _is_number(value) or value <= 0:
        return _UNSET

    return float(value)


def _coerce_text_list(value: object) -> object:
    """Acepta una lista de textos y descarta cualquier otro valor.

    Args:
        value: Valor declarado en la configuración.

    Returns:
        object: La lista copiada, o ``_UNSET`` si no es una lista de textos.
    """
    if not isinstance(value, list):
        return _UNSET
    if not all(isinstance(item, str) for item in value):
        return _UNSET

    return list(value)


def _coerce_override(base: object, value: object) -> object:
    """Acepta un valor de configuración solo si conserva el tipo esperado.

    Una errata en el JSON nunca debe romper el cálculo del presupuesto: si el
    valor no sirve, se descarta y sobrevive el default. El orden de los casos
    importa: ``bool`` es subclase de ``int``, así que se evalúa primero.

    Args:
        base: Valor por defecto, que define el tipo esperado.
        value: Valor declarado en la configuración.

    Returns:
        object: El valor aceptado, o ``_UNSET`` si debe descartarse.
    """
    match base:
        case bool():
            return value if isinstance(value, bool) else _UNSET
        case int():
            return _coerce_positive_int(value)
        case float():
            return _coerce_positive_float(value)
        case str():
            return value if isinstance(value, str) and value.strip() else _UNSET
        case list():
            return _coerce_text_list(value)

    return _UNSET


def _merge_section(
    defaults: dict[str, Any],
    override: object,
) -> dict[str, Any]:
    """Fusiona una sección de configuración sobre los valores por defecto.

    Args:
        defaults: Valores por defecto de la sección.
        override: Sección declarada en la configuración, si existe.

    Returns:
        dict[str, Any]: Sección resuelta.
    """
    merged = dict(defaults)
    if not isinstance(override, dict):
        return merged

    for key, value in override.items():
        if key not in merged:
            continue
        resolved = _coerce_override(merged[key], value)
        if resolved is not _UNSET:
            merged[key] = resolved

    return merged


def triptych_specs(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resuelve las especificaciones efectivas del tríptico.

    Args:
        config: Configuración cargada con ``load_triptych_config``, o None
            para usar solo los valores por defecto.

    Returns:
        dict[str, Any]: Especificaciones con las secciones 'page',
        'typography', 'limits', 'style' y 'layout'.
    """
    data = config or {}
    return {
        section: _merge_section(defaults, data.get(section))
        for section, defaults in DEFAULT_SPECS.items()
    }


# ---------------------------------------------------------------------------
# Geometría: de milímetros a caracteres
# ---------------------------------------------------------------------------


def char_width_mm(specs: dict[str, Any]) -> float:
    """Calcula el ancho de un carácter monospace en milímetros.

    Args:
        specs: Especificaciones resueltas.

    Returns:
        float: Ancho de avance del carácter, en milímetros.
    """
    typography = specs["typography"]
    points = typography["size_pt"] * typography["char_width_em"]

    return points / POINTS_PER_INCH * MM_PER_INCH


def usable_width_mm(specs: dict[str, Any]) -> float:
    """Calcula el ancho útil de la hoja, ya descontados los márgenes.

    Args:
        specs: Especificaciones resueltas.

    Returns:
        float: Ancho útil, en milímetros.
    """
    page = specs["page"]

    return page["width_mm"] - 2 * page["margin_mm"]


def usable_height_mm(specs: dict[str, Any]) -> float:
    """Calcula el alto útil de la hoja, ya descontados los márgenes.

    Args:
        specs: Especificaciones resueltas.

    Returns:
        float: Alto útil, en milímetros.
    """
    page = specs["page"]

    return page["height_mm"] - 2 * page["margin_mm"]


def column_width_mm(specs: dict[str, Any]) -> float:
    """Calcula el ancho de una columna del tríptico.

    Args:
        specs: Especificaciones resueltas.

    Returns:
        float: Ancho de una columna, en milímetros.
    """
    return usable_width_mm(specs) / specs["page"]["columns_per_side"]


def line_height_mm(specs: dict[str, Any]) -> float:
    """Calcula la altura de una línea de texto, con su interlínea.

    Args:
        specs: Especificaciones resueltas.

    Returns:
        float: Altura de línea, en milímetros.
    """
    typography = specs["typography"]
    points = typography["size_pt"] * typography["line_height_ratio"]

    return points / POINTS_PER_INCH * MM_PER_INCH


def chars_per_line(specs: dict[str, Any], columns: float = 1.0) -> int:
    """Calcula cuántos caracteres caben en un ancho expresado en columnas.

    Args:
        specs: Especificaciones resueltas.
        columns: Ancho disponible, medido en columnas del tríptico.

    Returns:
        int: Cantidad de caracteres por línea, redondeada hacia abajo.
    """
    return int(column_width_mm(specs) * columns / char_width_mm(specs))


def lines_per_column(specs: dict[str, Any]) -> int:
    """Calcula cuántas líneas caben en una columna completa.

    Args:
        specs: Especificaciones resueltas.

    Returns:
        int: Cantidad de líneas por columna, redondeada hacia abajo.
    """
    return int(usable_height_mm(specs) / line_height_mm(specs))


def max_chars_for_columns(specs: dict[str, Any], columns: float) -> int:
    """Calcula el techo de caracteres para un ancho en columnas.

    Args:
        specs: Especificaciones resueltas.
        columns: Ancho disponible, medido en columnas del tríptico.

    Returns:
        int: Caracteres que caben, suponiendo líneas llenas.
    """
    return chars_per_line(specs, columns) * lines_per_column(specs)


def column_max_chars(specs: dict[str, Any]) -> int:
    """Calcula el techo de caracteres de una columna completa.

    Args:
        specs: Especificaciones resueltas.

    Returns:
        int: Caracteres que caben en una columna.
    """
    return max_chars_for_columns(specs, 1.0)


def block_max_chars(specs: dict[str, Any]) -> int:
    """Calcula el techo de caracteres de un bloque de nota.

    El tope es el que fija la dirección editorial: una columna y media. Es la
    referencia contra la que se advierte, nunca la que recorta.

    Args:
        specs: Especificaciones resueltas.

    Returns:
        int: Caracteres que caben en el ancho máximo del bloque.
    """
    return max_chars_for_columns(specs, specs["limits"]["block_max_columns"])


# ---------------------------------------------------------------------------
# Medición de textos
# ---------------------------------------------------------------------------


def _lines_for_paragraph(paragraph: str, chars_per_line: int) -> int:
    """Cuenta las líneas que ocupa un párrafo dentro de una columna.

    Reparte las palabras igual que un procesador de textos y, si una palabra
    sola supera el ancho, la parte en varios trozos.

    Args:
        paragraph: Párrafo sin espacios sobrantes en los extremos.
        chars_per_line: Caracteres que caben en una línea.

    Returns:
        int: Líneas ocupadas por el párrafo.
    """
    total = 0
    current = 0

    for word in paragraph.split():
        if len(word) > chars_per_line:
            if current:
                total += 1
                current = 0
            chunks = math.ceil(len(word) / chars_per_line)
            total += chunks - 1
            current = len(word) - (chunks - 1) * chars_per_line
            continue

        needed = len(word) if current == 0 else len(word) + 1
        if current + needed <= chars_per_line:
            current += needed
            continue

        total += 1
        current = len(word)

    return total + 1


def estimate_lines(text: str, chars_per_line: int) -> int:
    """Cuenta las líneas que ocuparía un texto al envolverse en una columna.

    Los saltos de línea del texto se respetan como cortes duros y una línea
    vacía cuenta como un renglón en blanco.

    Args:
        text: Texto a medir.
        chars_per_line: Caracteres que caben en una línea.

    Returns:
        int: Cantidad de líneas ocupadas. Cero si no hay texto.

    Raises:
        ValueError: Si ``chars_per_line`` no es mayor que cero.
    """
    if chars_per_line <= 0:
        raise ValueError("chars_per_line debe ser mayor que cero.")

    total = 0
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            total += 1
            continue
        total += _lines_for_paragraph(stripped, chars_per_line)

    return total


def estimate_columns(text: str, specs: dict[str, Any]) -> float:
    """Estima cuántas columnas del tríptico ocupa un texto.

    Args:
        text: Texto a medir.
        specs: Especificaciones resueltas.

    Returns:
        float: Columnas ocupadas, con dos decimales.
    """
    lines = estimate_lines(text, chars_per_line(specs, 1.0))

    return round(lines / lines_per_column(specs), 2)


def budget_report(text: str, specs: dict[str, Any]) -> dict[str, Any]:
    """Resume la medición de un bloque de texto contra su presupuesto.

    Args:
        text: Texto a medir.
        specs: Especificaciones resueltas.

    Returns:
        dict[str, Any]: Caracteres, líneas, columnas ocupadas, los topes
        vigentes y si el bloque cabe o no.
    """
    limits = specs["limits"]
    lines_per_col = lines_per_column(specs)
    lines = estimate_lines(text, chars_per_line(specs, 1.0))
    columns = round(lines / lines_per_col, 2)
    max_columns = limits["block_max_columns"]

    return {
        "chars": len(text),
        "lines": lines,
        "columns": columns,
        "chars_per_line": chars_per_line(specs, 1.0),
        "lines_per_column": lines_per_col,
        "column_max_chars": column_max_chars(specs),
        "block_max_chars": block_max_chars(specs),
        "body_target_chars": limits["body_target_chars"],
        "block_max_columns": max_columns,
        "within_column": columns <= 1.0,
        "within_block_max": columns <= max_columns,
        "columns_excess": round(max(0.0, columns - max_columns), 2),
    }


def format_length_report(report: dict[str, Any]) -> str:
    """Redacta el resumen de medición de un bloque en una línea.

    Args:
        report: Resultado de ``budget_report``.

    Returns:
        str: Texto legible, por ejemplo
        ``700 caracteres, 30 líneas, 0.51 columnas``.
    """
    return (
        f"{report['chars']} caracteres, {report['lines']} líneas, "
        f"{report['columns']} columnas"
    )
