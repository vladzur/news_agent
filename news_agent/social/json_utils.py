"""Utilidades para extraer y reparar JSON generado por el LLM.

El modelo puede devolver el JSON envuelto en un bloque de código Markdown,
precedido de texto explicativo o con comas finales sueltas. Este módulo
concentra la lógica defensiva de extracción para que los módulos que piden
JSON no dupliquen heurísticas de parseo.
"""

import json
import logging
import re
from collections.abc import Iterator
from typing import Any

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class JsonExtractionError(Exception):
    """Excepción para respuestas del LLM que no contienen un objeto JSON."""


# Bloques de código Markdown: ```json ... ``` o ``` ... ```
_FENCED_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

# Comas finales antes de un cierre de objeto o lista
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _iter_balanced_objects(text: str) -> Iterator[str]:
    """Genera los objetos JSON balanceados de nivel superior de un texto.

    Recorre el texto llevando la profundidad de llaves y respetando los
    literales de cadena, de modo que una llave dentro de un string no rompa
    el conteo. Es la heurística que permite rescatar el JSON cuando el modelo
    agrega texto antes o después.

    Args:
        text: Texto donde buscar objetos JSON.

    Yields:
        str: Cada substring que va desde una llave de apertura de nivel 0
             hasta su llave de cierre correspondiente.
    """
    depth = 0
    start = -1
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start != -1:
                yield text[start : index + 1]
                start = -1


def _repair_json(blob: str) -> str:
    """Aplica reparaciones mínimas y conservadoras a un JSON malformado.

    Solo elimina comas finales antes de un cierre, que es el defecto más
    frecuente y el que no altera el significado del documento.

    Args:
        blob: Texto JSON candidato.

    Returns:
        str: Texto con comas finales eliminadas.
    """
    return _TRAILING_COMMA_RE.sub(r"\1", blob)


def extract_json_object(text: str) -> dict[str, Any]:
    """Extrae el primer objeto JSON válido contenido en una respuesta del LLM.

    Estrategia, en orden de preferencia:
      1. Cada bloque de código Markdown (```json ... ```).
      2. El texto completo.
      3. Cada objeto balanceado hallado dentro de esos candidatos.
    Para cada candidato se intenta el parseo directo y, si falla, un parseo
    tras aplicar reparaciones mínimas.

    Args:
        text: Respuesta cruda del modelo.

    Returns:
        dict[str, Any]: El objeto JSON extraído.

    Raises:
        JsonExtractionError: Si no se encontró ningún objeto JSON válido.
    """
    if not text or not text.strip():
        raise JsonExtractionError(
            "La respuesta del modelo está vacía: no hay JSON que extraer."
        )

    candidates: list[str] = [
        match.group(1).strip() for match in _FENCED_BLOCK_RE.finditer(text)
    ]
    candidates.append(text.strip())

    attempts = 0
    for candidate in candidates:
        blobs = [candidate, *list(_iter_balanced_objects(candidate))]
        for blob in blobs:
            if not blob:
                continue
            for payload in (blob, _repair_json(blob)):
                attempts += 1
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    logger.debug(
                        "JSON extraído correctamente tras %d intento(s).", attempts
                    )
                    return parsed

    snippet = text.strip()[:200].replace("\n", " ")
    raise JsonExtractionError(
        "No se pudo extraer un objeto JSON válido de la respuesta del modelo. "
        f"Inicio de la respuesta: {snippet!r}"
    )
