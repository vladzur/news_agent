"""Extracción del contenido editorial que alimenta una portada.

A partir del artículo ya parseado por ``social.article_source`` se obtienen
las piezas que el diseño necesita: bajada, cita, cifra protagonista, leyenda,
firma y texto alternativo. Todo es determinista y no consume LLM.
"""

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..report_writer import _slugify
from ..social.article_source import ArticleSource
from .models import CoverContent
from .specs import resolve_treatment, treatment_label
from .text_utils import (
    clean_inline,
    fold_text,
    split_sentences,
    truncate_words,
)

# Bajada aplicada que el editor de portada deja en el apéndice del artículo.
_APPENDIX_DECK_RE = re.compile(
    r"^\s*\*\*Bajada:\*\*\s*(.+?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# Línea en cursiva que hace de bajada en el cuerpo del artículo.
_ITALIC_LINE_RE = re.compile(r"^\s*\*(?!\*)(.+?)\*\s*$", re.MULTILINE)

# Primer subtítulo de nivel 2: la bajada vive antes de esa marca.
_H2_RE = re.compile(r"^##\s+(?!#)", re.MULTILINE)

# Fecha AAAA_MM_DD dentro del nombre del artículo.
_DATE_IN_NAME_RE = re.compile(r"(?<!\d)(\d{4})_(\d{2})_(\d{2})(?!\d)")

# Rango de una cita legible en una pieza gráfica.
_MIN_QUOTE_CHARS = 60
_MAX_QUOTE_CHARS = 240

# Expresiones numéricas con valor editorial para una portada. Es más amplio
# que el extractor de cifras de RRSS: una nota de fiscalización suele girar en
# torno a "189 páginas" o "56 condenados", unidades que el copy social no
# necesariamente destaca.
_COVER_FIGURE_RE = re.compile(
    r"(?:[$]\s?\d[\d.,]*(?:\s*(?:millones|mil|billones|pesos))?"
    r"|\d[\d.,]*\s*%"
    r"|\d[\d.,]*\s+(?:páginas|paginas|condenados|condenadas|casos|votos|"
    r"capítulos|capitulos|decretos|funcionarios|funcionarias|detenidos|"
    r"detenidas|estudiantes|personas|familias|hectáreas|hectareas|"
    r"kilómetros|kilometros|km|millones|mil millones|años|meses|días|dias|"
    r"semanas|horas|puntos porcentuales|grados|veces))",
    re.IGNORECASE,
)

# Atribución que suele acompañar a una cita textual en el cuerpo y que no
# debe aparecer dentro de la comilla destacada.
_QUOTE_ATTRIBUTION_RE = re.compile(
    r'^["“«]?(.+?)["”»]\s*,\s*'
    r"(?:sostuvo|sostiene|dijo|dice|señaló|señala|afirmó|afirma|explicó|"
    r"explica|agregó|agrega|declaró|declara|indicó|indica|aseguró|asegura|"
    r"comentó|comenta|relató|relata|expresó|expresa|advirtió|advierte|"
    r"puntualizó|puntualiza)\.?\s*$",
    re.IGNORECASE | re.DOTALL,
)

# Tope del texto alternativo que se publica en el manifiesto.
_MAX_ALT_CHARS = 300


def extract_deck(article: ArticleSource) -> str:
    """Extrae la bajada del artículo.

    Prioriza la propuesta de portada aplicada en el apéndice; si no existe,
    usa la primera línea en cursiva del cuerpo y, por último, la primera
    oración del lead.

    Args:
        article: Artículo ya parseado.

    Returns:
        str: Bajada limpia, o cadena vacía si no hay una utilizable.
    """
    appendix_match = _APPENDIX_DECK_RE.search(article.raw_text)
    if appendix_match is not None:
        deck = clean_inline(appendix_match.group(1))
        if deck:
            return deck

    body = article.raw_text
    heading = _H2_RE.search(body)
    if heading is not None:
        body = body[: heading.start()]

    for match in _ITALIC_LINE_RE.finditer(body):
        candidate = clean_inline(match.group(1))
        if candidate and not candidate.lower().startswith("artículo generado"):
            return candidate

    for paragraph in article.paragraphs:
        text = clean_inline(paragraph)
        if not text or text.lower().startswith(("por ", "fecha de creación")):
            continue
        for sentence in split_sentences(text):
            if len(sentence) >= 40:
                return sentence.strip()

    return ""


def _clean_quote(text: str) -> str:
    """Limpia una cita de comillas envolventes y atribuciones.

    Una cita de portada debe leerse sola: se retira la atribución externa
    (``", sostuvo."``) y las comillas que envuelven el texto completo. Las
    comillas internas de una frase citada dentro de la cita se conservan.

    Args:
        text: Cita original.

    Returns:
        str: Cita limpia.
    """
    cleaned = clean_inline(text)
    attribution = _QUOTE_ATTRIBUTION_RE.match(cleaned)
    if attribution is not None:
        cleaned = attribution.group(1).strip()

    cleaned = re.sub(r'^["“«]\s*', "", cleaned)
    cleaned = re.sub(r'\s*["”»]$', "", cleaned)
    return cleaned.strip()


def extract_quote(article: ArticleSource) -> str:
    """Extrae la cita más útil para una columna de opinión.

    Usa las candidatas que ya rankea el parser de RRSS. Si no hay ninguna,
    busca la oración entrecomillada más larga del cuerpo y, en último término,
    la oración autocontenida más larga del arranque del artículo.

    Args:
        article: Artículo ya parseado.

    Returns:
        str: Cita limpia, o cadena vacía si no hay una utilizable.
    """
    for candidate in article.quote_candidates:
        quote = _clean_quote(candidate)
        if quote:
            return quote

    quoted: list[str] = []
    fallback: list[str] = []
    for paragraph in article.paragraphs:
        for sentence in split_sentences(clean_inline(paragraph)):
            if not _MIN_QUOTE_CHARS <= len(sentence) <= _MAX_QUOTE_CHARS:
                continue
            fallback.append(sentence)
            if '"' in sentence or "“" in sentence or "”" in sentence:
                quoted.append(sentence)

    if quoted:
        return _clean_quote(max(quoted, key=len))
    if fallback:
        return _clean_quote(max(fallback, key=len))
    return ""


def _figure_pattern(figure: str) -> re.Pattern[str] | None:
    """Construye el patrón que localiza una cifra como expresión completa.

    El lookbehind y el lookahead evitan aceptar fragmentos: un ``00 horas``
    que en realidad forma parte de ``16:00 horas`` no debe convertirse en la
    cifra protagonista de la portada.

    Args:
        figure: Expresión numérica detectada por el parser.

    Returns:
        re.Pattern[str] | None: Patrón sobre texto normalizado, o None si la
        cifra está vacía.
    """
    target = fold_text(figure)
    if not target:
        return None
    return re.compile(r"(?<![\d:])" + re.escape(target) + r"(?![\d])")


def _figure_in_text(figure: str, text: str) -> bool:
    """Comprueba si una cifra aparece como expresión completa en un texto.

    Args:
        figure: Expresión numérica detectada por el parser.
        text: Texto donde buscar.

    Returns:
        bool: True si la cifra, o su token numérico, está presente y no es
        parte de otra expresión (por ejemplo, los minutos de una hora).
    """
    pattern = _figure_pattern(figure)
    if pattern is None:
        return False

    haystack = fold_text(text)
    if pattern.search(haystack):
        return True

    for number in re.findall(r"\d[\d.,]*", figure or ""):
        if len(number) < 2:
            continue
        token_pattern = re.compile(
            r"(?<![\d:])" + re.escape(number) + r"(?![\d])"
        )
        if token_pattern.search(haystack):
            return True
    return False


def _short_figure(figure: str, max_chars: int) -> str:
    """Reduce una cifra a una expresión que quepa en el lienzo.

    Args:
        figure: Expresión original.
        max_chars: Largo máximo admitido.

    Returns:
        str: Cifra original o su token numérico, o cadena vacía si ninguna
        cabe.
    """
    cleaned = clean_inline(figure)
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned

    for number in re.findall(r"\d[\d.,]*", cleaned):
        if len(number) <= max_chars:
            return number
    return ""


def _extract_cover_figures(article: ArticleSource) -> list[str]:
    """Extrae las cifras con valor editorial para la portada.

    Recorre el titular y los párrafos en orden de aparición y conserva, sin
    duplicados, las expresiones numéricas que llevan una unidad significativa
    (páginas, condenados, porcentajes, montos, etc.). Descarta los fragmentos
    de una expresión mayor, como los minutos de una hora.

    Args:
        article: Artículo ya parseado.

    Returns:
        list[str]: Cifras limpias en orden de aparición.
    """
    figures: list[str] = []
    seen: set[str] = set()

    for text in (article.title, *article.paragraphs):
        for match in _COVER_FIGURE_RE.finditer(text or ""):
            start = match.start()
            if start > 0 and (text[start - 1].isdigit() or text[start - 1] == ":"):
                continue
            figure = clean_inline(match.group(0))
            key = fold_text(figure)
            if not figure or key in seen:
                continue
            seen.add(key)
            figures.append(figure)

    return figures


def _caption_for_figure(article: ArticleSource, figure: str) -> str:
    """Elige la oración más compacta que explica una cifra.

    Cuando la cifra aparece en varias oraciones se prefiere la más corta que
    siga siendo autocontenida: una leyenda de portada no debe arrastrar un
    párrafo completo si existe una formulación más breve.

    Args:
        article: Artículo ya parseado.
        figure: Cifra protagonista.

    Returns:
        str: Leyenda limpia, o cadena vacía si no se encontró.
    """
    candidates: list[str] = []
    for paragraph in article.paragraphs:
        for sentence in split_sentences(clean_inline(paragraph)):
            if not _figure_in_text(figure, sentence):
                continue
            cleaned = sentence.strip()
            if len(cleaned) >= 40:
                candidates.append(cleaned)

    if not candidates:
        return ""
    return min(candidates, key=len)


def select_figure(
    article: ArticleSource, limits: dict[str, int]
) -> tuple[str, str, bool]:
    """Elige la cifra protagonista y su leyenda.

    Una cifra en el titular, o en las dos primeras oraciones del lead, marca
    el tratamiento ``data`` automático. Una cifra que solo aparece en el
    cuerpo se conserva para cuando el editor fuerza el tratamiento.

    Args:
        article: Artículo ya parseado.
        limits: Topes de texto resueltos.

    Returns:
        tuple[str, str, bool]: Cifra, leyenda y si la cifra es "fuerte" (está
        en el titular o en el arranque del lead).
    """
    candidates = _extract_cover_figures(article)
    if not candidates:
        return "", "", False

    max_chars = int(limits.get("figure_max_chars", 24))
    caption_max = int(limits.get("caption_max_chars", 220))

    strong_figure = ""
    for candidate in candidates:
        if _figure_in_text(candidate, article.title):
            strong_figure = candidate
            break

    if not strong_figure:
        lead_sentences = split_sentences(article.lead)[:2]
        for candidate in candidates:
            if any(_figure_in_text(candidate, sentence) for sentence in lead_sentences):
                strong_figure = candidate
                break

    figure = strong_figure or candidates[0]
    short = _short_figure(figure, max_chars)
    if not short:
        return "", "", False

    caption = _caption_for_figure(article, figure)
    if not caption:
        caption = extract_deck(article)

    return (
        short,
        truncate_words(clean_inline(caption), caption_max),
        bool(strong_figure),
    )


def build_alt_text(content: CoverContent) -> str:
    """Construye el texto alternativo de la portada.

    Args:
        content: Contenido ya resuelto.

    Returns:
        str: Texto alternativo apto para ``headerImageAlt``.
    """
    if content.treatment == "quote" and content.quote:
        text = (
            f"Cita destacada: «{content.quote}» — "
            f"{content.byline or 'La Chispa Sur'}."
        )
    elif content.treatment == "data" and content.figure:
        caption = content.caption.rstrip(".")
        text = (
            f"{content.figure}. {caption}. Portada de la sección "
            f"{content.category} de La Chispa Sur."
        )
    else:
        text = (
            f"{content.title}. Portada de la sección {content.category} "
            "de La Chispa Sur."
        )

    return truncate_words(" ".join(text.split()), _MAX_ALT_CHARS)


def build_content(
    article: ArticleSource,
    category: str,
    requested_treatment: str | None,
    specs: dict[str, Any],
    brand_name: str = "La Chispa Sur",
) -> CoverContent:
    """Construye el contenido editorial y resuelve el tratamiento.

    Args:
        article: Artículo ya parseado.
        category: Sección oficial de la nota.
        requested_treatment: Tratamiento pedido (``auto`` o uno concreto).
        specs: Especificaciones resueltas.
        brand_name: Nombre de la marca, usado cuando falta la firma.

    Returns:
        CoverContent: Contenido listo para el renderizador.
    """
    limits = specs.get("limits", {})
    warnings: list[str] = []

    deck = truncate_words(
        extract_deck(article), int(limits.get("deck_max_chars", 260))
    )
    quote = extract_quote(article)
    figure, caption, strong_figure = select_figure(article, limits)

    treatment, treatment_warnings = resolve_treatment(
        requested=requested_treatment,
        category=category,
        has_quote=bool(quote),
        has_figure=bool(figure),
        strong_figure=strong_figure,
    )
    warnings.extend(treatment_warnings)

    byline = clean_inline(article.byline) or f"Por {brand_name}"

    if not deck:
        warnings.append(
            "El artículo no tiene una bajada utilizable: la portada se "
            "compone solo con el titular."
        )
    if treatment == "quote" and not quote:
        warnings.append(
            "La portada de cita no encontró una cita: se usa el titular como "
            "texto principal."
        )
    if treatment == "data" and not figure:
        warnings.append(
            "La portada de dato duro no encontró una cifra: se usa el "
            "titular como texto principal."
        )

    content = CoverContent(
        title=clean_inline(article.title),
        category=category,
        treatment=treatment,
        treatment_label=treatment_label(treatment),
        deck=deck,
        quote=quote if treatment == "quote" else "",
        figure=figure if treatment == "data" else "",
        caption=caption if treatment == "data" else "",
        byline=byline,
        warnings=warnings,
    )
    content.alt_text = build_alt_text(content)
    return content


def source_sha256(article: ArticleSource) -> str:
    """Calcula la huella del texto de origen.

    Args:
        article: Artículo ya parseado.

    Returns:
        str: SHA-256 en hexadecimal del Markdown completo.
    """
    return hashlib.sha256(article.raw_text.encode("utf-8")).hexdigest()


def article_date(path: str | Path) -> datetime | None:
    """Extrae la fecha de creación del nombre del artículo.

    Args:
        path: Ruta del artículo.

    Returns:
        datetime | None: Fecha en UTC, o None si el nombre no la incluye.
    """
    match = _DATE_IN_NAME_RE.search(Path(path).name)
    if match is None:
        return None
    try:
        return datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None


def slug_for_article(article: ArticleSource) -> str:
    """Genera el slug del bundle a partir del titular.

    Args:
        article: Artículo ya parseado.

    Returns:
        str: Slug apto para nombre de carpeta.
    """
    return _slugify(article.title) or "sin-titulo"
