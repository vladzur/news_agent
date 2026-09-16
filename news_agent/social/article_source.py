"""Parseo del artículo Markdown de origen del subsistema RRSS.

Los artículos que produce el agente (``articulos/articulo_N_slug.md``) tienen
una estructura estable: titular de nivel 1, firma, separador horizontal,
lead, secciones de nivel 2 y un bloque final de fuentes. Este módulo convierte
ese Markdown en un ``ArticleSource`` con las piezas ya separadas, de modo que
los prompts y los banners trabajen con material limpio en lugar del archivo
crudo.
"""

import logging
import re
from pathlib import Path

from .models import ArticleSection, ArticleSource

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class ArticleParseError(Exception):
    """Excepción para errores al parsear el artículo de origen."""


# ---------------------------------------------------------------------------
# Expresiones regulares de estructura
# ---------------------------------------------------------------------------

# Titular: primer encabezado de nivel 1
_H1_RE = re.compile(r"^#\s+(?!#)(\S.*?)\s*$", re.MULTILINE)

# Subtítulo: encabezados de nivel 2
_H2_RE = re.compile(r"^##\s+(?!#)(\S.*?)\s*$", re.MULTILINE)

# Firma del artículo: **Por La Chispa Sur**, _Por ..._, *Por ...*
_BYLINE_RE = re.compile(
    r"^\s*[*_]{1,2}\s*Por\s+(.+?)\s*[*_]{1,2}\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# Inicio del bloque de fuentes al pie del artículo
_SOURCES_HEADING_RE = re.compile(
    r"^\s*[*_#\s]*Fuentes\s+(?:consultadas|sugeridas)",
    re.MULTILINE | re.IGNORECASE,
)

# Nota automática que cierra el cuerpo del artículo
_GENERATED_NOTE_RE = re.compile(
    r"^\s*[*_]*\s*Art[íi]culo generado",
    re.MULTILINE | re.IGNORECASE,
)

# Items de lista con viñeta
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(\S.*?)\s*$", re.MULTILINE)

# Separadores horizontales de Markdown
_RULE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")

# Corte de oraciones: tras un cierre de oración seguido de espacio
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")

# Muletillas que restan valor a una cita de portada
_CONNECTOR_STARTS = (
    "según",
    "sin embargo",
    "no se trata",
    "por su parte",
    "asimismo",
    "además",
    "por otro lado",
    "al mismo tiempo",
    "aquí cabe",
    "el punto no es",
    "es decir",
    "en ese sentido",
    "en cambio",
    "por eso",
)

# Patrones de cifras relevantes para destacar en banners y copys
_KEY_FIGURE_PATTERNS = (
    re.compile(r"\$\s?\d[\d.,]*(?:\s*(?:millones|mil|billones|pesos))?"),
    re.compile(r"\d[\d.,]*\s*%"),
    re.compile(
        r"\d[\d.,]*\s*(?:años|meses|días|semanas|horas|"
        r"detenidos|detenidas|funcionarios|funcionarias|estudiantes|"
        r"kilómetros|km|hectáreas|millones|mil millones|"
        r"puntos porcentuales|grados)"
    ),
)

# Topes de extracción de material derivado
_MAX_QUOTE_CANDIDATES = 5
_MAX_KEY_FIGURES = 12


# ---------------------------------------------------------------------------
# Limpieza de bloques
# ---------------------------------------------------------------------------


def _clean_block(block: str) -> str:
    """Normaliza un bloque de texto Markdown a una sola línea de prosa.

    Elimina separadores horizontales y colapsa los saltos de línea internos,
    que en Markdown solo separan líneas de un mismo párrafo.

    Args:
        block: Bloque de texto crudo.

    Returns:
        str: Bloque limpio, sin espacios sobrantes.
    """
    lines = [
        line.strip()
        for line in block.split("\n")
        if line.strip() and not _RULE_RE.match(line)
    ]
    return " ".join(lines).strip()


def _split_paragraphs(text: str) -> list[str]:
    """Divide un fragmento de Markdown en párrafos limpios.

    Args:
        text: Fragmento de Markdown.

    Returns:
        list[str]: Párrafos no vacíos, en orden de aparición.
    """
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        cleaned = _clean_block(block)
        if cleaned:
            paragraphs.append(cleaned)
    return paragraphs


# ---------------------------------------------------------------------------
# Extracción de material derivado
# ---------------------------------------------------------------------------


def _extract_sources(text: str, heading_pos: int) -> list[str]:
    """Extrae la lista de fuentes desde el bloque final del artículo.

    Args:
        text: Texto completo del artículo.
        heading_pos: Posición donde comienza el encabezado de fuentes.

    Returns:
        list[str]: Fuentes listadas, sin viñetas.
    """
    tail = text[heading_pos:]
    sources: list[str] = []
    for match in _BULLET_RE.finditer(tail):
        entry = match.group(1).strip()
        if entry:
            sources.append(entry)
    return sources


def _extract_quote_candidates(paragraphs: list[str]) -> list[str]:
    """Selecciona oraciones del cuerpo aptas para una tarjeta de cita.

    Prioriza oraciones autocontenidas con valor editorial: las que contienen
    una cita textual o una cifra, y descarta las que arrancan con muletillas
    de transición, porque no se sostienen fuera del hilo argumental.

    Args:
        paragraphs: Párrafos del cuerpo del artículo.

    Returns:
        list[str]: Hasta cinco oraciones ordenadas por potencial decreciente.
    """
    scored: list[tuple[int, int, str]] = []
    position = 0

    for paragraph in paragraphs:
        for sentence in _SENTENCE_SPLIT_RE.split(paragraph):
            sentence = sentence.strip()
            position += 1

            if "requiere investigación" in sentence.lower():
                continue

            # Solo oraciones completas, dentro de un rango legible en un banner
            if not sentence.endswith((".", "!", "?", "…")):
                continue
            if not 60 <= len(sentence) <= 240:
                continue

            score = 0
            if '"' in sentence or "“" in sentence:
                score += 2
            if re.search(r"\d", sentence):
                score += 1
            if 80 <= len(sentence) <= 200:
                score += 2

            lowered = sentence.lower()
            if any(lowered.startswith(connector) for connector in _CONNECTOR_STARTS):
                score -= 3

            if score > 0:
                scored.append((score, -position, sentence))

    # Mayor puntaje primero; a igual puntaje, la oración que aparece antes
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [sentence for _, _, sentence in scored[:_MAX_QUOTE_CANDIDATES]]


def _extract_key_figures(paragraphs: list[str]) -> list[str]:
    """Extrae cifras y datos duros del cuerpo del artículo.

    Args:
        paragraphs: Párrafos del cuerpo del artículo.

    Returns:
        list[str]: Expresiones numéricas únicas, en orden de aparición.
    """
    figures: list[str] = []
    seen: set[str] = set()

    for paragraph in paragraphs:
        for pattern in _KEY_FIGURE_PATTERNS:
            for match in pattern.finditer(paragraph):
                figure = match.group(0).strip()
                normalized = figure.lower()
                if normalized in seen:
                    continue
                seen.add(normalized)
                figures.append(figure)
                if len(figures) >= _MAX_KEY_FIGURES:
                    return figures

    return figures


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def parse_article_file(filepath: str | Path) -> ArticleSource:
    """Parsea un artículo Markdown y extrae sus piezas reutilizables.

    Args:
        filepath: Ruta al archivo Markdown del artículo.

    Returns:
        ArticleSource: Artículo parseado, listo para alimentar los prompts.

    Raises:
        ArticleParseError: Si el archivo no existe, está vacío o no tiene el
                           titular de nivel 1 que identifica el formato.
    """
    path = Path(filepath)
    if not path.exists():
        raise ArticleParseError(f"Artículo no encontrado: {path.resolve()}")
    if not path.is_file():
        raise ArticleParseError(f"La ruta no es un archivo: {path.resolve()}")

    text = path.read_text(encoding="utf-8").lstrip("\ufeff")
    if not text.strip():
        raise ArticleParseError(f"El artículo está vacío: {path.resolve()}")

    title_match = _H1_RE.search(text)
    if title_match is None:
        raise ArticleParseError(
            "El archivo no parece un artículo válido: falta el titular de "
            f"nivel 1 ('# Título') en {path.resolve()}."
        )
    title = title_match.group(1).strip()

    # Firma del artículo (opcional)
    byline = ""
    byline_match = _BYLINE_RE.search(text)
    if byline_match is not None:
        byline = f"Por {byline_match.group(1).strip()}"

    # El cuerpo arranca tras el titular y, si existe, tras la firma. La firma
    # puede empezar en el mismo índice donde termina el titular (el patrón
    # consume los saltos de línea previos), por eso la comparación es >=.
    body_start = title_match.end()
    if byline_match is not None and byline_match.start() >= body_start:
        body_start = byline_match.end()

    # El cuerpo termina donde arranca la nota automática o el bloque de fuentes
    tail_candidates = [
        match.start()
        for match in (
            _SOURCES_HEADING_RE.search(text, body_start),
            _GENERATED_NOTE_RE.search(text, body_start),
        )
        if match is not None
    ]
    body_end = min(tail_candidates) if tail_candidates else len(text)

    body = text[body_start:body_end]

    # Fuentes sugeridas al pie del artículo
    sources: list[str] = []
    sources_match = _SOURCES_HEADING_RE.search(text, body_start)
    if sources_match is not None:
        sources = _extract_sources(text, sources_match.start())

    # Secciones de nivel 2 y lead previo al primer subtítulo
    heading_matches = list(_H2_RE.finditer(body))
    sections: list[ArticleSection] = []

    if heading_matches:
        lead = _clean_block(body[: heading_matches[0].start()])
        for index, heading_match in enumerate(heading_matches):
            section_start = heading_match.end()
            section_end = (
                heading_matches[index + 1].start()
                if index + 1 < len(heading_matches)
                else len(body)
            )
            sections.append(
                ArticleSection(
                    heading=heading_match.group(1).strip(),
                    body=_clean_block(body[section_start:section_end]),
                )
            )
    else:
        lead = _clean_block(body)
        logger.warning(
            "El artículo %s no tiene subtítulos de nivel 2: se tratará todo "
            "el cuerpo como lead.",
            path.name,
        )

    paragraphs = _split_paragraphs(body)
    word_count = len(re.findall(r"\w+", " ".join(paragraphs)))
    quote_candidates = _extract_quote_candidates(paragraphs)
    key_figures = _extract_key_figures(paragraphs)

    logger.info(
        "Artículo parseado: %d palabra(s), %d sección(es), %d fuente(s), "
        "%d cita(s) candidata(s).",
        word_count,
        len(sections),
        len(sources),
        len(quote_candidates),
    )

    return ArticleSource(
        path=path.resolve(),
        title=title,
        byline=byline,
        lead=lead,
        sections=sections,
        paragraphs=paragraphs,
        sources=sources,
        quote_candidates=quote_candidates,
        key_figures=key_figures,
        word_count=word_count,
        raw_text=text,
    )
