"""Parseo del artículo Markdown de origen del subsistema RRSS.

Los artículos que produce el agente
(``articulos/articulo_N_AAAA_MM_DD_slug.md``) tienen una estructura estable:
titular de nivel 1, línea de fecha de creación, firma, separador horizontal,
lead, secciones de nivel 2 y un bloque final de fuentes. La fecha de creación
queda antes de la firma para que no se cuele en el cuerpo que alimenta los
prompts de redes sociales. Este módulo convierte ese Markdown en un
``ArticleSource`` con las piezas ya separadas, de modo que los prompts y los
banners trabajen con material limpio en lugar del archivo crudo.
"""

import logging
import re
import unicodedata
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

# Línea de metadatos con la fecha de creación del artículo. No es prosa: se
# excluye del cuerpo aunque el artículo no tenga firma y el parser no pueda
# saltarla junto con el encabezado.
_CREATION_DATE_RE = re.compile(
    r"^\s*\*\*Fecha de creación:\*\*.*$",
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

# Apéndice del editor de portada con las tres propuestas de titular y bajada.
# No es parte del artículo publicable, así que el cuerpo termina antes.
_PORTADA_APPENDIX_RE = re.compile(
    r"^\s*##\s+📰\s+Propuestas de portada",
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
        if line.strip()
        and not _RULE_RE.match(line)
        and not _CREATION_DATE_RE.match(line)
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

    # El cuerpo termina donde arranca la nota automática, el bloque de fuentes
    # o el apéndice de propuestas de portada (que no es publicable)
    tail_candidates = [
        match.start()
        for match in (
            _SOURCES_HEADING_RE.search(text, body_start),
            _GENERATED_NOTE_RE.search(text, body_start),
            _PORTADA_APPENDIX_RE.search(text, body_start),
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


# ---------------------------------------------------------------------------
# Anclas concretas del artículo
# ---------------------------------------------------------------------------

# El prompt visual debe representar el contenido real de la columna, no una
# escena genérica. Estas anclas —nombres propios, acrónimos y cifras— son la
# materia concreta que el prompt tiene que nombrar.
_ANCHOR_TOKEN_RE = re.compile(
    r"\b[A-ZÁÉÍÓÚÑÜ][\wÁÉÍÓÚÑÜáéíóúñü'’-]{2,}\b",
    re.UNICODE,
)
_NUMBER_TOKEN_RE = re.compile(r"\d[\d.,]*\s*%?")

# Palabras capitalizadas que no son anclas: artículos, pronombres,
# preposiciones, conjunciones y adverbios que suelen abrir una oración.
_ANCHOR_STOPWORDS = frozenset(
    {
        "aunque", "además", "ahora", "antes", "aquel", "aquella", "aquellas",
        "aquellos", "así", "aun", "aún", "bajo", "cada", "como", "contra",
        "cuando", "debe", "deben", "desde", "después", "dicha", "dichas",
        "dicho", "dichos", "donde", "durante", "el", "ella", "ellas", "ello",
        "ellos", "entre", "esa", "esas", "ese", "eso", "esos", "esta",
        "estamos", "estas", "este", "esto", "estos", "está", "están", "fue",
        "gran", "grandes", "ha", "hace", "han", "hay", "hacia", "hasta", "hoy",
        "la", "las", "luego", "los", "mañana", "más", "mediante", "menos",
        "mientras", "mismo", "misma", "mismos", "mismas", "muy", "nada",
        "ni", "no", "nuevo", "nueva", "nuevos", "nuevas", "nunca", "otra",
        "otras", "otro", "otros", "para", "pero", "poco", "por", "porque",
        "primer", "primera", "primero", "puede", "pueden", "quizá", "quizás",
        "segunda", "segundo", "según", "ser", "si", "sí", "siempre", "sin",
        "sobre", "solo", "sólo", "son", "tal", "tales", "tan", "tiene",
        "tienen", "todo", "toda", "todas", "todos", "tras", "un", "una",
        "unas", "uno", "unos", "ya",
    }
)


def _fold_accents(text: str) -> str:
    """Retira los acentos de un texto para comparaciones tolerantes.

    Args:
        text: Texto original.

    Returns:
        str: Texto sin diacríticos.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize_for_anchor_match(text: str) -> str:
    """Normaliza un texto para comparar anclas sin distinguir caja ni acentos.

    Args:
        text: Texto original.

    Returns:
        str: Texto en minúsculas, sin acentos y con espacios colapsados.
    """
    return " ".join(_fold_accents(text).lower().split())


def anchor_in_text(text: str, anchor: str) -> bool:
    """Indica si un ancla aparece en un texto.

    La comparación ignora mayúsculas y acentos. Cuando el ancla contiene una
    cifra, también se acepta la cifra sin su unidad: el prompt en inglés puede
    escribir "200" aunque el artículo diga "más de 200".

    Args:
        text: Texto donde se busca el ancla (por ejemplo, el prompt visual).
        anchor: Ancla concreta extraída del artículo.

    Returns:
        bool: True si el ancla está representada en el texto.
    """
    normalized_anchor = normalize_for_anchor_match(anchor)
    if not normalized_anchor:
        return False

    haystack = normalize_for_anchor_match(text)
    if normalized_anchor in haystack:
        return True

    numbers = [
        number
        for number in re.findall(r"\d[\d.,]*", anchor or "")
        if len(number) >= 2
    ]
    return any(number in haystack for number in numbers)


def _anchor_source_texts(article: ArticleSource) -> list[str]:
    """Devuelve los textos del artículo que pueden aportar anclas concretas.

    Se excluyen la firma, las fuentes y el apéndice de portada: no son el
    contenido publicable que la imagen debe representar.

    Args:
        article: Artículo de origen ya parseado.

    Returns:
        list[str]: Titular, lead, subtítulos y cuerpos de sección.
    """
    texts = [article.title, article.lead]
    for section in article.sections:
        texts.append(section.heading)
        texts.append(section.body)
    return texts


def extract_concrete_anchors(
    article: ArticleSource, limit: int | None = None
) -> list[str]:
    """Extrae las anclas concretas que un prompt debe nombrar.

    Las anclas son las cifras detectadas por el parser, los nombres propios y
    los acrónimos del titular, el lead y las secciones. Se filtran las palabras
    funcionales capitalizadas para no ofrecer ruido al modelo. Las anclas se
    ordenan por peso editorial —presencia en el titular, el lead y las
    cabeceras, más la frecuencia en el cuerpo— para que el recorte no deje
    fuera a los protagonistas de la columna.

    Args:
        article: Artículo de origen ya parseado.
        limit: Cantidad máxima de anclas a devolver. Si se omite, se devuelven
               todas las encontradas.

    Returns:
        list[str]: Anclas ordenadas por relevancia, sin duplicados.
    """
    # Cada candidato guarda su etiqueta visible, su peso y el orden de primera
    # aparición, que desempata sin volver aleatorio el resultado.
    candidates: dict[str, tuple[str, int, int]] = {}

    def add(candidate: str, weight: int = 1) -> None:
        cleaned = " ".join((candidate or "").split())
        key = normalize_for_anchor_match(cleaned)
        if not cleaned or not key:
            return
        entry = candidates.get(key)
        if entry is None:
            candidates[key] = (cleaned, weight, len(candidates))
        else:
            label, score, order = entry
            candidates[key] = (label, score + weight, order)

    for figure in article.key_figures:
        add(figure, weight=5)
        for number in _NUMBER_TOKEN_RE.findall(figure):
            add(number, weight=5)

    weighted_texts: list[tuple[str, int]] = [
        (article.title, 4),
        (article.lead, 2),
    ]
    for section in article.sections:
        weighted_texts.append((section.heading, 2))
        weighted_texts.append((section.body, 1))

    for text, weight in weighted_texts:
        for match in _ANCHOR_TOKEN_RE.finditer(text or ""):
            token = match.group(0)
            if token.lower() in _ANCHOR_STOPWORDS:
                continue
            add(token, weight)

    ranked = sorted(
        candidates.values(), key=lambda entry: (-entry[1], entry[2])
    )
    anchors = [label for label, _, _ in ranked]

    if limit is not None:
        return anchors[:limit]
    return anchors


def article_mentions(article: ArticleSource, name: str) -> bool:
    """Comprueba si un nombre aparece en el material publicable del artículo.

    Se tolera que el modelo use solo una parte del nombre: si el nombre
    completo no aparece, se prueban sus tokens de cuatro letras o más. Así
    "Gabriel Boric" se valida aunque el artículo diga solo "Boric", pero no se
    acepta una figura inventada.

    Args:
        article: Artículo de origen ya parseado.
        name: Nombre declarado por el modelo.

    Returns:
        bool: True si el nombre proviene del artículo.
    """
    reference = " ".join(_anchor_source_texts(article))
    if anchor_in_text(reference, name):
        return True

    tokens = [token for token in re.split(r"\s+", name or "") if len(token) >= 4]
    return any(anchor_in_text(reference, token) for token in tokens)
