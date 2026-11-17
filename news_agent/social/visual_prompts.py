"""Generación del prompt visual en inglés para ilustrar una columna.

El subsistema no genera imágenes: entrega al diseñador un único prompt listo
para Midjourney, con el prompt negativo de marca y los flags de versión y
proporción. El tratamiento se decide por columna: **fotorrealista documental**
cuando el texto describe hechos, lugares, objetos o escenas concretas, y
**caricatura** editorial solo cuando la columna es abstracta o no tiene una
escena documentable.

La ilustración puede incluir rótulos breves en español —cifras, etiquetas,
sellos— integrados en la escena, porque refuerzan la idea del artículo. Lo que
se verifica en código es que el prompt esté en inglés, que nombre una paleta de
color, que el tratamiento declarado coincida con la técnica descrita y que no
reproduzca párrafos de texto: los modelos de difusión convierten la tipografía
extensa en ruido.
"""

import logging
import re
from typing import Any

from ..config import SOCIAL_JSON_MAX_RETRIES
from .json_utils import JsonExtractionError, extract_json_object
from .models import ArticleSource, SocialCopy, VisualPrompt
from .prompt_builder import (
    build_visual_prompt_system_prompt,
    build_visual_prompt_user_prompt,
)

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class VisualPromptGenerationError(Exception):
    """Excepción para prompts visuales inválidos o ausentes."""


# Tratamientos admitidos, en orden de preferencia editorial
VISUAL_TREATMENTS = ("photorealistic", "caricature")


# Términos que delatan un bloque de texto real dentro de la imagen: párrafos,
# titulares largos, documentos con letra pequeña. Los modelos de difusión
# convierten la tipografía extensa en ruido, así que se rechazan; los rótulos
# breves y las cifras sí están permitidos.
_TEXT_BLOCK_RE = re.compile(
    r"\b(?:blocks?\s+of\s+text|columns?\s+of\s+text|paragraphs?\s+of\s+text|"
    r"pages?\s+of\s+text|body\s+copy|fine\s+print|dense\s+text|"
    r"paragraphs?|headlines?)\b",
    re.IGNORECASE,
)

# Frases en las que el término aparece negado y, por lo tanto, es legítimo:
# "no paragraphs of text", "without headlines".
_NEGATED_TERM_RE = re.compile(
    r"\b(?:no|without|free\s+of|devoid\s+of|zero)\s+(?:any\s+)?"
    r"(?:blocks?\s+of\s+text|columns?\s+of\s+text|paragraphs?\s+of\s+text|"
    r"pages?\s+of\s+text|body\s+copy|fine\s+print|dense\s+text|"
    r"paragraphs?|headlines?)\b",
    re.IGNORECASE,
)

# Rótulos dentro de la imagen. Midjourney no interpreta comillas escapadas y
# el prompt debe poder pegarse tal cual, así que el texto va sin comillas y se
# escribe en mayúsculas para distinguirlo de la descripción en inglés.
_QUOTED_LABEL_RE = re.compile(r"\"[^\"]*\"|“[^”]*”")
_UPPERCASE_LABEL_RE = re.compile(r"\b[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ0-9$%.,:+\-]*\b")

# Comillas que se retiran del prompt final: el comando de Midjourney es texto
# plano y los caracteres de escape del JSON lo ensucian al copiarlo.
_QUOTE_CHARS_RE = re.compile(r"[\\\"“”]")
# Largo admisible de un prompt positivo
_MIN_PROMPT_WORDS = 25
_MAX_PROMPT_WORDS = 200

# Palabras funcionales inequívocamente españolas. Se exige más de una para
# descartar un prompt, de modo que una palabra suelta no provoque un falso
# positivo en un prompt escrito en inglés.
_SPANISH_FUNCTION_WORDS = (
    "el",
    "la",
    "los",
    "las",
    "una",
    "para",
    "del",
    "por",
    "que",
    "como",
    "más",
    "pero",
    "sin",
    "sobre",
    "entre",
    "desde",
    "hacia",
    "cada",
    "todo",
    "sus",
    "bajo",
)

_SPANISH_WORD_RE = re.compile(
    r"\b(?:" + "|".join(_SPANISH_FUNCTION_WORDS) + r")\b",
    re.IGNORECASE,
)

# Cantidad de señales en español a partir de la cual se rechaza el prompt
_SPANISH_SIGNAL_THRESHOLD = 2

# Señales de color. Un prompt sin ninguna de estas palabras produce imágenes
# planas y desaturadas, así que su ausencia se rechaza.
_COLOUR_SIGNAL_RE = re.compile(
    r"\b(?:red|crimson|scarlet|vermilion|orange|amber|yellow|gold|golden|"
    r"lime|olive|emerald|green|teal|turquoise|cyan|blue|azure|navy|"
    r"indigo|violet|purple|magenta|pink|rose|brown|rust|sepia|terracotta|"
    r"beige|cream|black|white|grey|gray|charcoal|neon|pastel|"
    r"iridescent|rainbow|colou?rs?|colou?rful|vivid|saturated|palette)\b",
    re.IGNORECASE,
)

# Señales del tratamiento fotorrealista. Un prompt declarado como
# "photorealistic" debe describir una fotografía documental; si solo describe
# una ilustración, el tratamiento y el texto se contradicen.
_PHOTO_SIGNAL_RE = re.compile(
    r"\b(?:photograph|photographic|photography|photojournalism|"
    r"photojournalistic|reportage|documentary|35mm|50mm|lens|"
    r"depth\s+of\s+field|film\s+grain|natural\s+light|available\s+light|"
    r"shot\s+on|camera|telephoto|wide[- ]angle|photorealistic)\b",
    re.IGNORECASE,
)

# Señales del tratamiento de caricatura. Un prompt declarado como "caricature"
# debe nombrar una técnica ilustrada, no una fotografía.
_ILLUSTRATION_SIGNAL_RE = re.compile(
    r"\b(?:illustration|illustrated|digital\s+painting|vector|"
    r"screen\s+print|collage|ink|drawing|hand[- ]drawn|caricature|"
    r"cartoon|gouache|watercolou?r|comic|graphic[- ]novel|poster\s+art)\b",
    re.IGNORECASE,
)

# Nota que se agrega al prompt cuando la respuesta anterior no fue utilizable
_RETRY_NOTE = (
    "\n\n## Correction\n\nYour previous answer was not usable ({reason}). "
    "Respond again with the complete JSON object only, no extra text and no "
    "Markdown code fences."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collapse_whitespace(text: str) -> str:
    """Colapsa los espacios en blanco de un texto en una sola línea.

    Args:
        text: Texto original.

    Returns:
        str: Texto sin saltos de línea ni espacios repetidos.
    """
    return " ".join((text or "").split())


def _strip_quotes(text: str) -> str:
    """Retira comillas y escapes de un prompt para que sea texto plano.

    Midjourney recibe el comando pegado a mano: las comillas y los caracteres
    de escape que añade el JSON no se interpretan y ensucian el prompt, así que
    el texto dentro de la imagen se escribe sin comillas.

    Args:
        text: Prompt positivo o negativo.

    Returns:
        str: Texto sin comillas ni barras invertidas, con espacios colapsados.
    """
    return _collapse_whitespace(_QUOTE_CHARS_RE.sub("", text or ""))


def _find_text_blocks(prompt: str) -> list[str]:
    """Detecta menciones a bloques de texto dentro de un prompt positivo.

    Los rótulos breves y las cifras están permitidos; lo que se descarta son
    párrafos, titulares largos y documentos con letra pequeña, que los modelos
    de difusión renderizan como ruido.

    Args:
        prompt: Prompt positivo en inglés.

    Returns:
        list[str]: Términos detectados fuera de un contexto de negación.
    """
    without_negations = _NEGATED_TERM_RE.sub(" ", prompt)
    return sorted({match.group(0).lower() for match in _TEXT_BLOCK_RE.finditer(without_negations)})


def spanish_signal_count(text: str) -> int:
    """Cuenta las palabras funcionales españolas distintas de un texto.

    Args:
        text: Texto a analizar.

    Returns:
        int: Cantidad de palabras funcionales españolas distintas halladas.
    """
    return len({match.group(0).lower() for match in _SPANISH_WORD_RE.finditer(text or "")})


def looks_like_spanish(text: str) -> bool:
    """Heurística para detectar prompts escritos en español.

    Los prompts deben estar en inglés porque los generadores de imágenes
    rinden mejor con descripciones en ese idioma. Se exige más de una palabra
    funcional española distinta para evitar falsos positivos, y se ignoran los
    rótulos que irán dentro de la imagen —entre comillas o en mayúsculas—,
    porque sí deben ir en español.

    Args:
        text: Prompt a evaluar.

    Returns:
        bool: True si el texto parece estar en español.
    """
    without_labels = _QUOTED_LABEL_RE.sub(" ", text or "")
    without_labels = _UPPERCASE_LABEL_RE.sub(" ", without_labels)
    return spanish_signal_count(without_labels) >= _SPANISH_SIGNAL_THRESHOLD


def has_colour_signal(prompt: str) -> bool:
    """Indica si un prompt nombra alguna señal cromática.

    Los modelos de difusión devuelven ilustraciones planas y sin contraste
    cuando el prompt no menciona color. La marca pide arte digital vívido, así
    que se exige al menos una palabra de color, la palabra "palette" o un
    término de intensidad cromática.

    Args:
        prompt: Prompt positivo en inglés.

    Returns:
        bool: True si el prompt nombra color.
    """
    return _COLOUR_SIGNAL_RE.search(prompt or "") is not None


def has_photo_signal(prompt: str) -> bool:
    """Indica si un prompt describe una fotografía.

    Args:
        prompt: Prompt positivo en inglés.

    Returns:
        bool: True si el prompt nombra un recurso fotográfico.
    """
    return _PHOTO_SIGNAL_RE.search(prompt or "") is not None


def has_illustration_signal(prompt: str) -> bool:
    """Indica si un prompt describe una técnica ilustrada.

    Args:
        prompt: Prompt positivo en inglés.

    Returns:
        bool: True si el prompt nombra una técnica de ilustración.
    """
    return _ILLUSTRATION_SIGNAL_RE.search(prompt or "") is not None


def validate_visual_prompt(prompt: str, treatment: str) -> None:
    """Valida un prompt positivo contra las restricciones de marca.

    Args:
        prompt: Prompt positivo en inglés.
        treatment: Tratamiento declarado: "photorealistic" o "caricature".

    Raises:
        VisualPromptGenerationError: Si el tratamiento es desconocido, si el
                                     prompt está vacío, tiene un largo fuera de
                                     rango, no está en inglés, no nombra una
                                     paleta de color, pide bloques de texto en
                                     la imagen o no coincide con la técnica del
                                     tratamiento declarado.
    """
    if treatment not in VISUAL_TREATMENTS:
        raise VisualPromptGenerationError(
            f"Tratamiento visual desconocido: {treatment or '(vacío)'}. "
            f"Se esperaba uno de: {', '.join(VISUAL_TREATMENTS)}."
        )

    words = prompt.split()
    if not words:
        raise VisualPromptGenerationError("El prompt visual está vacío.")
    if not _MIN_PROMPT_WORDS <= len(words) <= _MAX_PROMPT_WORDS:
        raise VisualPromptGenerationError(
            f"El prompt visual tiene {len(words)} palabras; se esperaban entre "
            f"{_MIN_PROMPT_WORDS} y {_MAX_PROMPT_WORDS}."
        )

    if looks_like_spanish(prompt):
        raise VisualPromptGenerationError(
            "El prompt visual debe estar en inglés, pero se detectaron "
            "palabras funcionales en español."
        )

    if not has_colour_signal(prompt):
        raise VisualPromptGenerationError(
            "El prompt visual no nombra ninguna paleta de color; se rechaza "
            "porque produce ilustraciones planas y sin contraste."
        )

    text_blocks = _find_text_blocks(prompt)
    if text_blocks:
        raise VisualPromptGenerationError(
            "El prompt visual pide bloques de texto en la imagen "
            f"({', '.join(text_blocks)}); solo se permiten rótulos breves y "
            "cifras, porque la tipografía extensa se renderiza como ruido."
        )

    if treatment == "photorealistic" and not has_photo_signal(prompt):
        raise VisualPromptGenerationError(
            "El tratamiento es fotorrealista, pero el prompt no describe una "
            "fotografía (lente, luz natural, reportaje o realismo fotográfico)."
        )

    if treatment == "caricature" and not has_illustration_signal(prompt):
        raise VisualPromptGenerationError(
            "El tratamiento es caricatura, pero el prompt no nombra una "
            "técnica de ilustración ni caricaturiza a nadie."
        )


def _compose_negative_prompt(base: str, extra: str) -> str:
    """Compone el prompt negativo de marca con los agregados del modelo.

    Args:
        base: Prompt negativo definido en la configuración de marca.
        extra: Artefactos adicionales detectados por el modelo.

    Returns:
        str: Prompt negativo final, sin duplicar términos.
    """
    base_text = _collapse_whitespace(base)
    extra_text = _collapse_whitespace(extra)
    if not extra_text:
        return base_text

    seen = {term.strip().lower() for term in base_text.split(",") if term.strip()}
    additions = [
        term.strip()
        for term in extra_text.split(",")
        if term.strip() and term.strip().lower() not in seen
    ]

    if not additions:
        return base_text
    return f"{base_text}, {', '.join(additions)}"


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def build_visual_prompt(
    payload: dict[str, Any], config: dict[str, Any]
) -> VisualPrompt:
    """Construye el prompt visual a partir del JSON del modelo.

    Función pura: no invoca al modelo. Valida el tratamiento declarado, el
    prompt positivo y la coherencia entre ambos, y compone el prompt negativo
    definitivo y la variante lista para Midjourney.

    Args:
        payload: Objeto JSON devuelto por el modelo.
        config: Configuración de marca cargada desde ``social_config.json``.

    Returns:
        VisualPrompt: Prompt validado con su tratamiento.

    Raises:
        VisualPromptGenerationError: Si el payload no trae un prompt utilizable
                                     o el tratamiento no es válido.
    """
    visual_config = config.get("visual_prompts", {})
    base_negative = _strip_quotes(str(visual_config.get("negative_prompt", "")))
    midjourney_suffix = str(visual_config.get("midjourney_suffix", "")).strip()
    aspect_ratio = str(visual_config.get("aspect_ratio", "")).strip()

    treatment = payload.get("treatment")
    treatment = treatment.strip().lower() if isinstance(treatment, str) else ""

    rationale = payload.get("rationale")
    rationale = _collapse_whitespace(rationale) if isinstance(rationale, str) else ""

    prompt = payload.get("prompt")
    prompt = _strip_quotes(prompt) if isinstance(prompt, str) else ""
    if not prompt:
        raise VisualPromptGenerationError(
            "El modelo no entregó un 'prompt' visual utilizable."
        )

    validate_visual_prompt(prompt, treatment)

    if not rationale:
        raise VisualPromptGenerationError(
            "El modelo no explicó en 'rationale' por qué eligió el "
            "tratamiento visual."
        )

    extra_negative = payload.get("extra_negative")
    extra_negative = (
        _strip_quotes(extra_negative) if isinstance(extra_negative, str) else ""
    )
    negative = _compose_negative_prompt(base_negative, extra_negative)

    aspect_flag = f"--ar {aspect_ratio}" if aspect_ratio else ""
    negative_flag = f"--no {negative}" if negative else ""
    midjourney_prompt = " ".join(
        chunk
        for chunk in (prompt, aspect_flag, midjourney_suffix, negative_flag)
        if chunk
    )

    return VisualPrompt(
        treatment=treatment,
        rationale=rationale,
        prompt=prompt,
        negative_prompt=negative,
        midjourney_prompt=midjourney_prompt,
        aspect_ratio=aspect_ratio,
    )


def generate_visual_prompt(
    article: ArticleSource,
    copy: SocialCopy,
    config: dict[str, Any],
    client: Any,
) -> VisualPrompt:
    """Genera el prompt visual en inglés para una columna.

    Args:
        article: Artículo de origen ya parseado.
        copy: Copys ya generados, usados para alinear el concepto visual.
        config: Configuración de marca cargada desde ``social_config.json``.
        client: Cliente LLM con el método ``generate_report``.

    Returns:
        VisualPrompt: Prompt validado, con el tratamiento declarado.

    Raises:
        VisualPromptGenerationError: Si se agotan los intentos sin obtener un
                                     prompt utilizable.
    """
    system_prompt = build_visual_prompt_system_prompt(config)
    base_user_prompt = build_visual_prompt_user_prompt(article, copy, config)

    attempts = SOCIAL_JSON_MAX_RETRIES + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        user_prompt = base_user_prompt
        if attempt > 1:
            user_prompt += _RETRY_NOTE.format(reason=last_error)

        logger.info(
            "Solicitando el prompt visual al modelo (intento %d/%d).",
            attempt,
            attempts,
        )
        raw_response = client.generate_report(system_prompt, user_prompt)

        try:
            payload = extract_json_object(raw_response)
        except JsonExtractionError as exc:
            last_error = exc
            logger.warning(
                "Intento %d sin JSON válido en el prompt visual: %s",
                attempt,
                exc,
            )
            continue

        try:
            return build_visual_prompt(payload, config)
        except VisualPromptGenerationError as exc:
            last_error = exc
            logger.warning(
                "Intento %d sin prompt visual válido: %s", attempt, exc
            )
            continue

    raise VisualPromptGenerationError(
        f"No se pudo generar un prompt visual válido tras {attempts} "
        f"intento(s). Último error: {last_error}"
    )
