"""Reglas de lenguaje simple del tríptico impreso.

Funciones puras que revisan el texto ya generado y devuelven advertencias. El
tríptico nunca recorta ni reescribe: un recorte automático mutila la redacción.
Estas revisiones solo le dicen al equipo editorial qué conviene ajustar antes
de mandar la pieza a imprenta.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

# Las oraciones se separan por una puntuación de cierre seguida de espacio.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
# Palabras: secuencias con letras o dígitos. Permite contar sin la puntuación.
_WORD_RE = re.compile(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")
# Siglas: dos o más mayúsculas seguidas, con puntos internos y punto final
# opcionales (por ejemplo "EE.UU."). Se comparan sin el punto final.
_ACRONYM_RE = re.compile(r"\b[A-ZÁÉÍÓÚÑ]{2,}(?:\.[A-ZÁÉÍÓÚÑ]{2,})*\.?")

# Largo máximo de una oración citada en una advertencia, para que el mensaje
# no se vuelva más largo que el problema que describe.
_QUOTE_LIMIT = 60


def split_sentences(text: str) -> list[str]:
    """Divide un texto en oraciones.

    Args:
        text: Texto a dividir.

    Returns:
        list[str]: Oraciones sin espacios sobrantes. Vacía si no hay texto.
    """
    if not text:
        return []

    return [chunk.strip() for chunk in _SENTENCE_SPLIT_RE.split(text) if chunk.strip()]


def count_words(text: str) -> int:
    """Cuenta las palabras de un texto.

    Args:
        text: Texto a contar.

    Returns:
        int: Cantidad de palabras.
    """
    return len(_WORD_RE.findall(text or ""))


def longest_sentence_words(text: str) -> int:
    """Devuelve el largo de la oración más extensa, en palabras.

    Args:
        text: Texto a revisar.

    Returns:
        int: Palabras de la oración más larga. Cero si no hay oraciones.
    """
    sentences = split_sentences(text)
    if not sentences:
        return 0

    return max(count_words(sentence) for sentence in sentences)


def normalize_acronym(token: str) -> str:
    """Normaliza una sigla para poder compararla con la lista permitida.

    Args:
        token: Sigla tal como aparece en el texto, por ejemplo "EE.UU.".

    Returns:
        str: Sigla sin el punto final.
    """
    return token.strip().rstrip(".")


def find_acronyms(text: str, allowlist: Iterable[str] = ()) -> list[str]:
    """Busca siglas que no estén en la lista permitida.

    Solo detecta mayúsculas sostenidas de dos letras o más: es un heurístico
    para avisar, no un corrector ortográfico.

    Args:
        text: Texto a revisar.
        allowlist: Siglas aceptadas por la configuración de estilo.

    Returns:
        list[str]: Siglas detectadas, sin repetir y en orden alfabético.
    """
    allowed = {normalize_acronym(item) for item in allowlist if item}
    found: set[str] = set()

    for match in _ACRONYM_RE.findall(text or ""):
        normalized = normalize_acronym(match)
        if normalized not in allowed:
            found.add(normalized)

    return sorted(found)


def style_warnings(
    text: str,
    specs: dict[str, Any],
    label: str = "cuerpo",
) -> list[str]:
    """Revisa un bloque de texto contra las reglas de lenguaje simple.

    Args:
        text: Texto a revisar.
        specs: Especificaciones resueltas del tríptico.
        label: Nombre del bloque, para que la advertencia sea ubicable.

    Returns:
        list[str]: Advertencias detectadas. Lista vacía si el texto cumple.
    """
    warnings: list[str] = []
    style = specs.get("style", {})

    limit = style.get("max_words_per_sentence")
    if isinstance(limit, int) and limit > 0:
        for sentence in split_sentences(text):
            words = count_words(sentence)
            if words > limit:
                warnings.append(
                    f"{label}: oración de {words} palabras (máximo {limit}): "
                    f"«{shorten(sentence)}»"
                )

    acronyms = find_acronyms(text, style.get("acronym_allowlist", ()))
    if acronyms:
        warnings.append(
            f"{label}: siglas sin explicar ({', '.join(acronyms)}). "
            "Escribe el nombre completo la primera vez que aparecen."
        )

    for term in style.get("forbidden_terms", ()):
        if isinstance(term, str) and term and term.lower() in (text or "").lower():
            warnings.append(
                f"{label}: aparece «{term}», que está en la lista de términos "
                "a evitar."
            )

    return warnings


def shorten(text: str, limit: int = _QUOTE_LIMIT) -> str:
    """Recorta un texto para citarlo en una advertencia.

    Args:
        text: Texto a recortar.
        limit: Largo máximo del recorte.

    Returns:
        str: Texto recortado, con puntos suspensivos si se acortó.
    """
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned

    return cleaned[: limit - 1].rstrip() + "…"
