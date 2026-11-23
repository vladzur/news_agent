"""Utilidades de texto del subsistema de portadas editoriales.

Concentra la limpieza de marcas de Markdown y el manejo de oraciones y
recortes que comparten la extracción de contenido y la resolución de
categorías. No depende de Pillow.
"""

import re
import unicodedata

# Enlace de Markdown: se conserva el texto visible y se descarta la URL.
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")

# Marcas de énfasis y código en línea que no deben llegar al lienzo.
_EMPHASIS_RE = re.compile(r"[*_`]+")

# Corte de oraciones tras un cierre de oración seguido de espacio.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def fold_text(text: str) -> str:
    """Normaliza un texto para comparar sin caja ni acentos.

    Args:
        text: Texto original.

    Returns:
        str: Texto en minúsculas, sin diacríticos y con espacios colapsados.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    folded = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(folded.casefold().split())


def clean_inline(text: str) -> str:
    """Convierte un fragmento de Markdown en una línea de prosa.

    Elimina enlaces, énfasis, código en línea y colapsa los espacios. No toca
    el contenido semántico del texto.

    Args:
        text: Fragmento original.

    Returns:
        str: Texto limpio en una sola línea.
    """
    cleaned = _MARKDOWN_LINK_RE.sub(r"\1", text or "")
    cleaned = _EMPHASIS_RE.sub("", cleaned)
    return " ".join(cleaned.split())


def split_sentences(text: str) -> list[str]:
    """Divide un párrafo en oraciones.

    Args:
        text: Texto de entrada.

    Returns:
        list[str]: Oraciones no vacías, en orden de aparición.
    """
    return [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT_RE.split(text or "")
        if sentence.strip()
    ]


def truncate_words(text: str, max_chars: int) -> str:
    """Recorta un texto por palabras sin superar el máximo de caracteres.

    Args:
        text: Texto original.
        max_chars: Cantidad máxima de caracteres.

    Returns:
        str: Texto recortado, con puntos suspensivos si se perdió contenido.
    """
    cleaned = " ".join((text or "").split())
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned

    cut = cleaned[: max_chars - 1].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0].rstrip()
    return f"{cut}…" if cut else ""


def sentence_with(text: str, needle: str) -> str:
    """Busca la oración que contiene una expresión concreta.

    La comparación ignora caja, acentos y espacios repetidos, de modo que una
    cifra como ``56`` se encuentra aunque el texto la escriba dentro de otra
    frase.

    Args:
        text: Texto donde buscar.
        needle: Expresión buscada.

    Returns:
        str: Primera oración que contiene la expresión, o cadena vacía.
    """
    target = fold_text(needle)
    if not target:
        return ""

    for sentence in split_sentences(text):
        if target in fold_text(sentence):
            return sentence.strip()
    return ""
