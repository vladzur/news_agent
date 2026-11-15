"""Editor de portada: tres propuestas de titular y bajada por artículo.

Después de que el redactor escribe el artículo, este módulo hace una segunda
llamada al modelo con un rol distinto —editor de portada— para producir tres
propuestas diferenciadas de titular y bajada. La primera (denuncia / tesis
política) se aplica al artículo publicado y las tres quedan registradas en un
apéndice al final del archivo, de modo que el periodista pueda cambiarlas sin
volver a llamar al modelo.

Los largos se validan en código (12-16 palabras el titular, 25-45 la bajada)
porque son reglas de portada, no sugerencias: si el modelo se desvía se
reintenta una vez y, si vuelve a fallar, se ajusta el texto por código.
"""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .config import (
    DECK_MAX_WORDS,
    DECK_MIN_WORDS,
    HEADLINE_MAX_WORDS,
    HEADLINE_MIN_WORDS,
    PORTADA_JSON_MAX_RETRIES,
)
from .prompt_builder import build_portada_system_prompt, build_portada_user_prompt
from .social.json_utils import JsonExtractionError, extract_json_object

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class HeadlineValidationError(Exception):
    """Excepción para respuestas que no cumplen el contrato de portada."""


# ---------------------------------------------------------------------------
# Enfoques obligatorios, en el orden en que se piden
# ---------------------------------------------------------------------------

ENFOQUES: tuple[str, ...] = (
    "Denuncia / tesis política",
    "Enfoque narrativo / humano",
    "Enfoque analítico / geopolítico",
)

# Título que abre el apéndice. El parser de RRSS lo usa como marca de fin del
# cuerpo, así que las propuestas nunca llegan a los prompts de redes sociales.
APPENDIX_HEADING = "## 📰 Propuestas de portada"

APPENDIX_NOTE = (
    "> Bloque editorial no publicable: alternativas de titular y bajada "
    "generadas por el editor de portada."
)

# Nota que se agrega al prompt cuando la respuesta anterior no fue utilizable
_RETRY_NOTE = (
    "\n\n## Corrección\n\n"
    "Tu respuesta anterior no sirvió ({reason}). Cada titular debe tener "
    "entre 12 y 16 palabras y cada bajada entre 25 y 45. Responde de nuevo "
    "únicamente con el objeto JSON completo, sin texto adicional y sin "
    "bloques de código Markdown."
)

# Encabezado de nivel 1 del artículo
_H1_RE = re.compile(r"^#\s+(?!#)(\S.*?)[ \t]*$", re.MULTILINE)

# Firma del artículo: **Por La Chispa Sur**, _Por ..._, *Por ...*
_BYLINE_RE = re.compile(
    r"^\s*[*_]{1,2}\s*Por\s+(.+?)\s*[*_]{1,2}\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# Línea en cursiva suelta (la bajada que escribe el redactor)
_ITALIC_LINE_RE = re.compile(r"^[*_](?!\*)(?!_)(.+?)[*_][ \t]*$", re.MULTILINE)

# Separador horizontal
_RULE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", re.MULTILINE)

# Primer subtítulo de sección
_H2_RE = re.compile(r"^##\s+(?!#)", re.MULTILINE)

# Separador de cláusulas donde conviene recortar un titular demasiado largo
_CLAUSE_END_RE = re.compile(r"[,;:]\s|\s[—–-]\s")


@dataclass(frozen=True)
class HeadlineProposal:
    """Propuesta de portada: titular, bajada y el enfoque que la distingue.

    Attributes:
        enfoque: Etiqueta del enfoque editorial de la propuesta.
        titular: Titular propuesto.
        bajada: Bajada o copete propuesto.
    """

    enfoque: str
    titular: str
    bajada: str

    def as_dict(self) -> dict[str, str]:
        """Serializa la propuesta para mostrarla en el resumen del CLI.

        Returns:
            dict[str, str]: Enfoque, titular y bajada.
        """
        return {
            "enfoque": self.enfoque,
            "titular": self.titular,
            "bajada": self.bajada,
        }


# ---------------------------------------------------------------------------
# Largos
# ---------------------------------------------------------------------------


def count_words(text: str) -> int:
    """Cuenta palabras de un texto, igual que el resto del proyecto.

    Args:
        text: Texto a medir.

    Returns:
        int: Cantidad de secuencias alfanuméricas.
    """
    return len(re.findall(r"\w+", text or ""))


def _collapse(text: str) -> str:
    """Colapsa espacios y saltos de línea en una sola línea de texto.

    Args:
        text: Texto original.

    Returns:
        str: Texto normalizado.
    """
    return " ".join((text or "").split())


def _trim_to_clause(text: str, max_words: int) -> str:
    """Recorta un texto largo prefiriendo un límite de cláusula.

    Args:
        text: Texto ya normalizado.
        max_words: Cantidad máxima de palabras.

    Returns:
        str: Texto recortado, sin puntuación colgando.
    """
    words = text.split()
    if len(words) <= max_words:
        return text

    head = " ".join(words[:max_words])
    match = None
    for match in _CLAUSE_END_RE.finditer(head):
        pass
    if match is not None and count_words(head[: match.start()]) >= max_words // 2:
        head = head[: match.start()]

    return head.rstrip(" ,;:—–-").strip()


def fit_length(name: str, text: str, minimum: int, maximum: int) -> str:
    """Ajusta por código el largo de una pieza de portada.

    Recortar es seguro; alargar no lo es, porque obligaría a inventar. Cuando
    el texto queda corto se conserva tal cual y se advierte en el log.

    Args:
        name: Nombre de la pieza ("titular" o "bajada"), para los mensajes.
        text: Texto a ajustar.
        minimum: Mínimo de palabras exigido.
        maximum: Máximo de palabras exigido.

    Returns:
        str: Texto ajustado.
    """
    collapsed = _collapse(text)

    if count_words(collapsed) > maximum:
        trimmed = _trim_to_clause(collapsed, maximum)
        logger.warning(
            "El %s excedía %d palabras y se recortó a %d: %s",
            name,
            maximum,
            count_words(trimmed),
            trimmed,
        )
        return trimmed

    if count_words(collapsed) < minimum:
        logger.warning(
            "El %s quedó con %d palabras (mínimo %d) y no se puede alargar "
            "sin inventar contenido: %s",
            name,
            count_words(collapsed),
            minimum,
            collapsed,
        )

    return collapsed


# ---------------------------------------------------------------------------
# Validación de la respuesta del modelo
# ---------------------------------------------------------------------------


def _read_proposals(payload: Any) -> list[dict[str, str]]:
    """Extrae la lista de propuestas del payload y valida su estructura.

    Args:
        payload: Objeto JSON devuelto por el modelo.

    Returns:
        list[dict[str, str]]: Tres propuestas con titular y bajada.

    Raises:
        HeadlineValidationError: Si la estructura no es utilizable.
    """
    if not isinstance(payload, dict):
        raise HeadlineValidationError("La respuesta no es un objeto JSON.")

    raw = payload.get("propuestas")
    if not isinstance(raw, list) or len(raw) != len(ENFOQUES):
        raise HeadlineValidationError(
            f"Se esperaban {len(ENFOQUES)} propuestas y llegaron "
            f"{len(raw) if isinstance(raw, list) else 0}."
        )

    proposals: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise HeadlineValidationError("Cada propuesta debe ser un objeto.")
        titular = _collapse(str(item.get("titular", "")))
        bajada = _collapse(str(item.get("bajada", "")))
        if not titular or not bajada:
            raise HeadlineValidationError(
                "Hay una propuesta sin titular o sin bajada."
            )
        proposals.append({"titular": titular, "bajada": bajada})

    return proposals


def _check_lengths(proposals: Sequence[dict[str, str]]) -> list[str]:
    """Devuelve los problemas de extensión de un conjunto de propuestas.

    Args:
        proposals: Propuestas ya normalizadas.

    Returns:
        list[str]: Mensajes de los largos fuera de rango; vacía si todo está bien.
    """
    problems: list[str] = []
    for index, item in enumerate(proposals, start=1):
        title_words = count_words(item["titular"])
        deck_words = count_words(item["bajada"])
        if not HEADLINE_MIN_WORDS <= title_words <= HEADLINE_MAX_WORDS:
            problems.append(
                f"propuesta {index}: titular de {title_words} palabras"
            )
        if not DECK_MIN_WORDS <= deck_words <= DECK_MAX_WORDS:
            problems.append(f"propuesta {index}: bajada de {deck_words} palabras")
    return problems


def build_proposals(
    payload: Any, *, strict: bool = True
) -> list[HeadlineProposal]:
    """Convierte la respuesta del modelo en propuestas de portada.

    Args:
        payload: Objeto JSON devuelto por el modelo.
        strict: Si es True, exige que los largos estén dentro de rango. Si es
            False, ajusta por código y advierte.

    Returns:
        list[HeadlineProposal]: Tres propuestas, la primera marcada como
        aplicada al artículo.

    Raises:
        HeadlineValidationError: Si la estructura no es utilizable o, en modo
        estricto, si algún largo está fuera de rango.
    """
    raw = _read_proposals(payload)

    problems = _check_lengths(raw)
    if problems and strict:
        raise HeadlineValidationError(
            "Largos fuera de rango: " + "; ".join(problems) + "."
        )

    proposals: list[HeadlineProposal] = []
    for enfoque, item in zip(ENFOQUES, raw):
        proposals.append(
            HeadlineProposal(
                enfoque=enfoque,
                titular=fit_length(
                    "titular",
                    item["titular"],
                    HEADLINE_MIN_WORDS,
                    HEADLINE_MAX_WORDS,
                ),
                bajada=fit_length(
                    "bajada",
                    item["bajada"],
                    DECK_MIN_WORDS,
                    DECK_MAX_WORDS,
                ),
            )
        )

    return proposals


def generate_headline_proposals(
    article_content: str,
    client: Any,
    proposal: dict[str, Any] | None = None,
) -> list[HeadlineProposal]:
    """Genera las tres propuestas de portada para un artículo ya escrito.

    Reintenta una vez cuando la respuesta no es JSON válido o no respeta los
    largos. Si el segundo intento tampoco cumple, ajusta por código.

    Args:
        article_content: Markdown del artículo redactado.
        client: Cliente LLM con el método ``generate_report``.
        proposal: Propuesta de pauta de origen, opcional.

    Returns:
        list[HeadlineProposal]: Tres propuestas listas para aplicar.

    Raises:
        HeadlineValidationError: Si ningún intento devuelve JSON utilizable.
        LLMClientError: Si falla la comunicación con la API.
    """
    system_prompt = build_portada_system_prompt()
    base_user_prompt = build_portada_user_prompt(article_content, proposal)

    attempts = PORTADA_JSON_MAX_RETRIES + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        user_prompt = base_user_prompt
        if attempt > 1:
            user_prompt += _RETRY_NOTE.format(reason=last_error)

        logger.info(
            "Solicitando propuestas de portada al modelo (intento %d/%d).",
            attempt,
            attempts,
        )
        raw_response = client.generate_report(system_prompt, user_prompt)

        try:
            payload = extract_json_object(raw_response)
        except JsonExtractionError as exc:
            last_error = exc
            logger.warning(
                "Intento %d sin JSON válido en las propuestas de portada: %s",
                attempt,
                exc,
            )
            continue

        try:
            return build_proposals(payload, strict=True)
        except HeadlineValidationError as exc:
            last_error = exc
            if attempt == attempts:
                # Último intento: se ajusta por código lo que se pueda y se
                # conserva el texto del modelo en lugar de perder la portada.
                logger.warning(
                    "Las propuestas no cumplen los largos tras %d intento(s). "
                    "Se ajustan por código: %s",
                    attempt,
                    exc,
                )
                return build_proposals(payload, strict=False)
            logger.warning(
                "Intento %d con propuestas fuera de contrato: %s", attempt, exc
            )

    raise HeadlineValidationError(
        f"No se pudieron generar propuestas de portada válidas tras "
        f"{attempts} intento(s). Último error: {last_error}"
    )


# ---------------------------------------------------------------------------
# Aplicación al artículo
# ---------------------------------------------------------------------------


def _deck_region(article: str) -> tuple[int, int] | None:
    """Devuelve el tramo donde vive la bajada: entre la firma y el primer H2.

    Args:
        article: Markdown del artículo.

    Returns:
        tuple[int, int] | None: Posiciones de inicio y fin del tramo, o None
        si no hay firma reconocible.
    """
    byline = _BYLINE_RE.search(article)
    if byline is None:
        return None

    start = byline.end()
    next_section = _H2_RE.search(article, start)
    end = next_section.start() if next_section is not None else len(article)
    return start, end


def apply_headline(article: str, proposals: Sequence[HeadlineProposal]) -> str:
    """Aplica el titular y la bajada de la primera propuesta al artículo.

    Reemplaza el H1 y la línea en cursiva que hace de bajada. Si el artículo no
    trae bajada, la inserta después del separador que sigue a la firma.

    Args:
        article: Markdown del artículo.
        proposals: Propuestas generadas. Se usa la primera.

    Returns:
        str: Artículo con el titular y la bajada reemplazados.
    """
    if not proposals:
        return article

    chosen = proposals[0]
    updated = _H1_RE.sub(lambda _: f"# {chosen.titular}", article, count=1)

    region = _deck_region(updated)
    deck_line = f"*{chosen.bajada}*"
    if region is None:
        return updated

    start, end = region
    segment = updated[start:end]

    match = _ITALIC_LINE_RE.search(segment)
    if match is not None:
        absolute_start = start + match.start()
        absolute_end = start + match.end()
        updated = (
            updated[:absolute_start] + deck_line + updated[absolute_end:]
        )
    else:
        rule = _RULE_RE.search(segment)
        if rule is not None:
            insert_at = start + rule.end()
            updated = (
                updated[:insert_at] + f"\n\n{deck_line}" + updated[insert_at:]
            )
        else:
            updated = (
                updated[:start]
                + f"\n\n---\n\n{deck_line}\n\n"
                + updated[start:]
            )

    updated = re.sub(r"\n{3,}", "\n\n", updated)
    # La bajada siempre cierra con una línea en blanco antes del lead
    return re.sub(
        rf"(?m)^{re.escape(deck_line)}[ \t]*\n(?!\n)",
        f"{deck_line}\n\n",
        updated,
        count=1,
    )


def build_appendix(proposals: Sequence[HeadlineProposal]) -> str:
    """Construye el apéndice con las tres propuestas de portada.

    Args:
        proposals: Propuestas generadas.

    Returns:
        str: Bloque Markdown listo para anexar al final del artículo.
    """
    parts: list[str] = ["", "---", "", APPENDIX_HEADING, "", APPENDIX_NOTE, ""]

    for index, item in enumerate(proposals, start=1):
        # apply_headline siempre aplica la primera, así que la marca va por
        # posición y no depende de que quien construya la lista lo recuerde.
        suffix = " — ✅ aplicada al artículo" if index == 1 else ""
        parts.extend(
            [
                f"### {index}. {item.enfoque}{suffix}",
                "",
                f"**Titular:** {item.titular}",
                "",
                f"**Bajada:** {item.bajada}",
                "",
            ]
        )

    return "\n".join(parts).rstrip() + "\n"


def append_headline_appendix(
    article: str,
    proposals: Sequence[HeadlineProposal],
) -> str:
    """Anexa el bloque de propuestas al final del artículo.

    Si el artículo ya trae un apéndice de portada (por ejemplo, al regenerar
    sobre un texto previo), se reemplaza en lugar de duplicarlo.

    Args:
        article: Markdown del artículo.
        proposals: Propuestas generadas.

    Returns:
        str: Artículo con el apéndice agregado o actualizado.
    """
    if not proposals:
        return article

    without_appendix = re.sub(
        r"\n\s*---\s*\n\s*" + re.escape(APPENDIX_HEADING) + r".*\Z",
        "",
        article,
        flags=re.DOTALL,
    )
    body = without_appendix.rstrip()

    return f"{body}\n{build_appendix(proposals)}"
