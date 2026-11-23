"""Editor periodístico: revisión y corrección del artículo antes de publicar.

Después de que el redactor escribe la nota y de que el editor de portada aplica
el titular y la bajada, este módulo hace una tercera llamada al modelo con el
rol de editor periodístico. Devuelve las tres piezas corregidas —titular,
bajada y cuerpo— y valida en código que la corrección conserve la estructura,
la extensión y los datos del artículo original.

La etapa es tolerante a fallos: el llamador conserva el artículo previo si la
llamada o la validación fallan, porque una revisión fallida nunca debe impedir
publicar la nota.
"""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .config import (
    DECK_MAX_WORDS,
    DECK_MIN_WORDS,
    EDITORIAL_REVIEW_JSON_MAX_RETRIES,
    EDITORIAL_REVIEW_MAX_BODY_RATIO,
    EDITORIAL_REVIEW_MAX_CHANGES_CHARS,
    EDITORIAL_REVIEW_MIN_BODY_RATIO,
    HEADLINE_MAX_WORDS,
    HEADLINE_MIN_WORDS,
)
from .headline_editor import (
    APPENDIX_HEADING,
    HeadlineProposal,
    apply_headline,
    count_words,
)
from .prompt_builder import (
    build_editorial_review_system_prompt,
    build_editorial_review_user_prompt,
)
from .social.json_utils import JsonExtractionError, extract_json_object

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class EditorialReviewError(Exception):
    """Excepción para revisiones que no se pueden aplicar con seguridad."""


# ---------------------------------------------------------------------------
# Marcas estructurales del artículo
# ---------------------------------------------------------------------------
# Mismas marcas que usa ``headline_editor.apply_headline``: H1, firma, bajada
# en cursiva y primer H2. Si el artículo no las trae, la revisión no se aplica.
_HEADLINE_RE = re.compile(r"^#\s+(?!#)(\S.*?)[ \t]*$", re.MULTILINE)

_BYLINE_RE = re.compile(
    r"^\s*[*_]{1,2}\s*Por\s+(.+?)\s*[*_]{1,2}\s*$",
    re.MULTILINE | re.IGNORECASE,
)

_ITALIC_LINE_RE = re.compile(r"^[*_](?!\*)(?!_)(.+?)[*_][ \t]*$", re.MULTILINE)

_SECTION_RE = re.compile(r"^##\s+(?!#)", re.MULTILINE)

# Referencias internas que nunca deben llegar al texto publicado.
_ARTICLE_REFERENCE_RE = re.compile(r"\s*\[art\.\s*\d+\]")

# Bloque de fuentes que el artículo original trae y la corrección no debe perder.
_SOURCES_RE = re.compile(r"\*\*Fuentes\s+consultadas", re.IGNORECASE)


@dataclass(frozen=True)
class ArticleParts:
    """Piezas separadas del artículo listo para revisar.

    Attributes:
        headline: Titular sin las marcas de Markdown.
        deck: Bajada sin el énfasis en cursiva.
        body: Cuerpo Markdown desde el lead hasta el bloque de fuentes.
        body_start: Posición del primer carácter del cuerpo en el artículo.
    """

    headline: str
    deck: str
    body: str
    body_start: int


@dataclass(frozen=True)
class EditorialReview:
    """Correcciones propuestas por el editor periodístico.

    Attributes:
        headline: Titular corregido.
        deck: Bajada corregida.
        body: Cuerpo corregido, sin H1, firma, bajada ni apéndice.
        changes: Síntesis breve de las correcciones aplicadas.
    """

    headline: str
    deck: str
    body: str
    changes: str = ""


# Nota que se agrega al prompt cuando la respuesta anterior no fue utilizable.
_RETRY_NOTE = (
    "\n\n## Corrección\n\n"
    "Tu respuesta anterior no sirvió ({reason}). Devuelve de nuevo el objeto "
    "JSON completo con las claves titular, bajada, cuerpo y resumen_cambios, "
    "sin texto adicional ni bloques de código Markdown. Conserva la estructura "
    "Markdown, el número de secciones y el bloque de fuentes del artículo "
    "original, y mantén su extensión."
)


def _collapse(value: Any) -> str:
    """Normaliza un valor a una sola línea de texto.

    Args:
        value: Valor devuelto por el modelo.

    Returns:
        str: Texto sin saltos de línea ni espacios repetidos.
    """
    return " ".join(str(value or "").split())


def split_article(article: str) -> ArticleParts:
    """Separa el artículo en titular, bajada y cuerpo.

    El artículo debe tener el formato que produce el redactor después del
    editor de portada y antes de anexar el apéndice: H1, firma, separador,
    bajada en cursiva y cuerpo con secciones.

    Args:
        article: Markdown del artículo.

    Returns:
        ArticleParts: Titular, bajada, cuerpo y posición inicial del cuerpo.

    Raises:
        EditorialReviewError: Si falta alguna marca estructural o el artículo
            ya incluye el apéndice de portada.
    """
    text = article or ""

    if APPENDIX_HEADING in text:
        raise EditorialReviewError(
            "El artículo ya incluye el apéndice de portada: la revisión debe "
            "aplicarse antes de anexarlo."
        )

    headline_match = _HEADLINE_RE.search(text)
    if headline_match is None:
        raise EditorialReviewError(
            "El artículo no tiene un titular de nivel 1 reconocible."
        )

    byline_match = _BYLINE_RE.search(text, headline_match.end())
    if byline_match is None:
        raise EditorialReviewError(
            "El artículo no tiene una firma reconocible después del titular."
        )

    next_section = _SECTION_RE.search(text, byline_match.end())
    region_end = next_section.start() if next_section is not None else len(text)

    deck_match = _ITALIC_LINE_RE.search(text, byline_match.end(), region_end)
    if deck_match is None:
        raise EditorialReviewError(
            "El artículo no tiene una bajada en cursiva entre la firma y la "
            "primera sección."
        )

    body_start = deck_match.end()
    while body_start < len(text) and text[body_start] in " \t\r\n":
        body_start += 1

    body = text[body_start:].strip()
    if not body:
        raise EditorialReviewError(
            "El artículo no tiene cuerpo después de la bajada."
        )

    return ArticleParts(
        headline=headline_match.group(1).strip(),
        deck=deck_match.group(1).strip(),
        body=body,
        body_start=body_start,
    )


def _strip_article_references(body: str) -> tuple[str, int]:
    """Elimina las referencias internas ``[art. N]`` del cuerpo corregido.

    Args:
        body: Cuerpo devuelto por el modelo.

    Returns:
        tuple[str, int]: Cuerpo limpio y cantidad de referencias eliminadas.
    """
    removed = len(_ARTICLE_REFERENCE_RE.findall(body))
    return _ARTICLE_REFERENCE_RE.sub("", body), removed


def _validate_body(body: str, original_body: str) -> None:
    """Comprueba que el cuerpo corregido conserve estructura y volumen.

    Args:
        body: Cuerpo corregido.
        original_body: Cuerpo del artículo previo a la revisión.

    Raises:
        EditorialReviewError: Si el cuerpo no es utilizable.
    """
    if _HEADLINE_RE.search(body):
        raise EditorialReviewError(
            "El cuerpo corregido no debe incluir un titular de nivel 1."
        )
    if APPENDIX_HEADING in body:
        raise EditorialReviewError(
            "El cuerpo corregido no debe incluir el apéndice de portada."
        )
    if _BYLINE_RE.search(body):
        raise EditorialReviewError(
            "El cuerpo corregido no debe incluir la firma del artículo."
        )

    corrected_sections = len(_SECTION_RE.findall(body))
    original_sections = len(_SECTION_RE.findall(original_body))
    if corrected_sections < 1:
        raise EditorialReviewError(
            "El cuerpo corregido no tiene secciones de nivel 2."
        )
    if corrected_sections != original_sections:
        raise EditorialReviewError(
            f"El cuerpo corregido tiene {corrected_sections} secciones y el "
            f"original tenía {original_sections}."
        )

    original_words = count_words(original_body)
    corrected_words = count_words(body)
    if original_words:
        ratio = corrected_words / original_words
        if not (
            EDITORIAL_REVIEW_MIN_BODY_RATIO
            <= ratio
            <= EDITORIAL_REVIEW_MAX_BODY_RATIO
        ):
            raise EditorialReviewError(
                f"El cuerpo corregido tiene {corrected_words} palabras frente "
                f"a {original_words} del original: se habría resumido o "
                "expandido fuera del rango permitido."
            )

    if _SOURCES_RE.search(original_body) and not _SOURCES_RE.search(body):
        raise EditorialReviewError(
            "El cuerpo corregido perdió el bloque de fuentes del original."
        )


def _repeats_the_deck(body: str, deck: str) -> bool:
    """Comprueba si el cuerpo empieza repitiendo la bajada en cursiva.

    Args:
        body: Cuerpo corregido.
        deck: Bajada corregida.

    Returns:
        bool: True si una de las primeras líneas es la bajada en cursiva.
    """
    if not deck:
        return False

    lines = [line.strip() for line in body.splitlines() if line.strip()][:3]
    deck_lines = {f"*{deck}*", f"_{deck}_"}
    return any(line in deck_lines for line in lines)



def build_review(payload: Any, current: ArticleParts) -> EditorialReview:
    """Convierte la respuesta del modelo en una revisión validada.

    Args:
        payload: Objeto JSON devuelto por el modelo.
        current: Piezas del artículo previo a la revisión.

    Returns:
        EditorialReview: Piezas corregidas y resumen de cambios.

    Raises:
        EditorialReviewError: Si el contrato o el cuerpo no son utilizables.
    """
    if not isinstance(payload, dict):
        raise EditorialReviewError(
            "La respuesta de la revisión no es un objeto JSON."
        )

    headline = _collapse(payload.get("titular"))
    deck = _collapse(payload.get("bajada"))
    body = str(payload.get("cuerpo") or "").strip()
    changes = _collapse(payload.get("resumen_cambios"))[
        :EDITORIAL_REVIEW_MAX_CHANGES_CHARS
    ]

    if not headline or not deck:
        raise EditorialReviewError(
            "La revisión no devolvió titular y bajada."
        )
    if not body:
        raise EditorialReviewError("La revisión devolvió un cuerpo vacío.")

    body, removed = _strip_article_references(body)
    if removed:
        logger.warning(
            "La revisión introdujo %d referencia(s) [art. N]; se eliminaron "
            "del cuerpo antes de guardar.",
            removed,
        )

    _validate_body(body, current.body)

    if not HEADLINE_MIN_WORDS <= count_words(headline) <= HEADLINE_MAX_WORDS:
        logger.warning(
            "El titular de la revisión tiene %d palabras (se esperaban %d a "
            "%d); se conserva el titular previo: %s",
            count_words(headline),
            HEADLINE_MIN_WORDS,
            HEADLINE_MAX_WORDS,
            current.headline,
        )
        headline = current.headline

    if not DECK_MIN_WORDS <= count_words(deck) <= DECK_MAX_WORDS:
        logger.warning(
            "La bajada de la revisión tiene %d palabras (se esperaban %d a "
            "%d); se conserva la bajada previa: %s",
            count_words(deck),
            DECK_MIN_WORDS,
            DECK_MAX_WORDS,
            current.deck,
        )
        deck = current.deck

    if _repeats_the_deck(body, deck):
        raise EditorialReviewError(
            "El cuerpo corregido repite la bajada al inicio."
        )

    return EditorialReview(
        headline=headline,
        deck=deck,
        body=body,
        changes=changes,
    )


def review_and_correct(
    article: str,
    client: Any,
    proposal: dict[str, Any] | None = None,
) -> EditorialReview:
    """Pide al editor periodístico la revisión de un artículo ya escrito.

    Reintenta una vez cuando la respuesta no es JSON válido o el cuerpo no
    cumple el contrato. Si el segundo intento tampoco es utilizable, lanza
    ``EditorialReviewError`` para que el llamador conserve el artículo previo.

    Args:
        article: Markdown del artículo con titular, bajada y cuerpo.
        client: Cliente LLM con el método ``generate_report``.
        proposal: Propuesta de pauta aprobada, opcional.

    Returns:
        EditorialReview: Piezas corregidas y resumen de cambios.

    Raises:
        EditorialReviewError: Si el artículo no se puede separar o ningún
            intento devuelve una revisión utilizable.
        LLMClientError: Si falla la comunicación con la API.
    """
    parts = split_article(article)

    system_prompt = build_editorial_review_system_prompt()
    base_user_prompt = build_editorial_review_user_prompt(
        parts.headline,
        parts.deck,
        parts.body,
        proposal,
    )

    attempts = EDITORIAL_REVIEW_JSON_MAX_RETRIES + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        user_prompt = base_user_prompt
        if attempt > 1:
            user_prompt += _RETRY_NOTE.format(reason=last_error)

        logger.info(
            "Solicitando revisión editorial al modelo (intento %d/%d).",
            attempt,
            attempts,
        )
        raw_response = client.generate_report(system_prompt, user_prompt)

        try:
            payload = extract_json_object(raw_response)
        except JsonExtractionError as exc:
            last_error = exc
            logger.warning(
                "Intento %d sin JSON válido en la revisión editorial: %s",
                attempt,
                exc,
            )
            continue

        try:
            return build_review(payload, parts)
        except EditorialReviewError as exc:
            last_error = exc
            logger.warning(
                "Intento %d con una revisión fuera de contrato: %s",
                attempt,
                exc,
            )

    raise EditorialReviewError(
        f"No se pudo aplicar la revisión editorial tras {attempts} intento(s). "
        f"Último error: {last_error}"
    )


def apply_review(article: str, review: EditorialReview) -> str:
    """Aplica las correcciones al artículo previo a la revisión.

    Reutiliza ``apply_headline`` para reemplazar el titular y la bajada, y
    sustituye el tramo del cuerpo conservando firma, separadores y formato.

    Args:
        article: Markdown del artículo previo (sin apéndice de portada).
        review: Correcciones validadas.

    Returns:
        str: Artículo con las tres piezas corregidas.

    Raises:
        EditorialReviewError: Si el artículo no se puede separar.
    """
    split_article(article)

    updated = apply_headline(
        article,
        [
            HeadlineProposal(
                enfoque="Revisión editorial",
                titular=review.headline,
                bajada=review.deck,
            )
        ],
    )
    updated_parts = split_article(updated)

    return f"{updated[:updated_parts.body_start]}{review.body.strip()}\n"


def update_applied_proposal(
    proposals: Sequence[HeadlineProposal],
    review: EditorialReview,
) -> list[HeadlineProposal]:
    """Sincroniza la propuesta de portada aplicada con la revisión.

    Las alternativas 2 y 3 se conservan tal como las generó el editor de
    portada; solo se actualiza la primera, que es la que quedó en el artículo.

    Args:
        proposals: Propuestas de portada generadas.
        review: Correcciones aplicadas.

    Returns:
        list[HeadlineProposal]: Propuestas con la primera actualizada.
    """
    if not proposals:
        return []

    first = proposals[0]
    return [
        HeadlineProposal(
            enfoque=first.enfoque,
            titular=review.headline,
            bajada=review.deck,
        ),
        *proposals[1:],
    ]
