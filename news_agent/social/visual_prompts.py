"""Generación de prompts visuales en inglés para generadores de imágenes.

Los prompts alimentan Flux.1, SDXL o Midjourney. El subsistema no genera
imágenes: entrega al diseñador un prompt positivo en inglés, el prompt
negativo de marca y una variante lista para Midjourney.

La restricción central es que la imagen no contenga texto ni personas reales
identificables. Esa regla se verifica en código, no solo en el prompt, porque
los modelos de difusión tienden a inventar tipografía y a reproducir rostros
de figuras públicas.
"""

import logging
import re
from typing import Any

from ..config import SOCIAL_JSON_MAX_RETRIES
from .json_utils import JsonExtractionError, extract_json_object
from .models import ArticleSource, SocialCopy, VisualPrompt
from .platform_specs import platform_of_format
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


# Términos que delatan la presencia de texto en la imagen. La revisión usa
# límites de palabra para no marcar palabras legítimas como "texture".
_TEXT_ARTIFACT_RE = re.compile(
    r"\b(?:text|texts|letters?|words?|typography|typographic|captions?|"
    r"subtitles?|logos?|watermarks?|numbers?|numerals|writing|written|"
    r"readable|legible|headlines?|signage)\b",
    re.IGNORECASE,
)

# Frases en las que el término aparece negado y, por lo tanto, es legítimo:
# "no text", "without letters", "free of typography".
_NEGATED_TERM_RE = re.compile(
    r"\b(?:no|without|free\s+of|devoid\s+of|zero)\s+(?:any\s+)?"
    r"(?:text|texts|letters?|words?|typography|typographic|captions?|"
    r"subtitles?|logos?|watermarks?|numbers?|numerals|writing|written|"
    r"readable|legible|headlines?|signage)\b",
    re.IGNORECASE,
)

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


def _find_text_artifacts(prompt: str) -> list[str]:
    """Detecta menciones a texto en un prompt positivo.

    Args:
        prompt: Prompt positivo en inglés.

    Returns:
        list[str]: Términos detectados fuera de un contexto de negación.
    """
    without_negations = _NEGATED_TERM_RE.sub(" ", prompt)
    return sorted({match.group(0).lower() for match in _TEXT_ARTIFACT_RE.finditer(without_negations)})


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
    funcional española distinta para evitar falsos positivos.

    Args:
        text: Prompt a evaluar.

    Returns:
        bool: True si el texto parece estar en español.
    """
    return spanish_signal_count(text) >= _SPANISH_SIGNAL_THRESHOLD


def validate_visual_prompt(prompt: str) -> None:
    """Valida un prompt positivo contra las restricciones de marca.

    Args:
        prompt: Prompt positivo en inglés.

    Raises:
        VisualPromptGenerationError: Si el prompt está vacío, tiene un largo
                                     fuera de rango, no está en inglés o
                                     describe texto.
    """
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

    artifacts = _find_text_artifacts(prompt)
    if artifacts:
        raise VisualPromptGenerationError(
            "El prompt visual describe texto en la imagen "
            f"({', '.join(artifacts)}), lo que produce artefactos de "
            "tipografía en los modelos de difusión."
        )


def enabled_aspects(
    config: dict[str, Any],
    platforms: list[str],
) -> dict[str, dict[str, Any]]:
    """Selecciona los aspectos aplicables a las plataformas pedidas.

    Args:
        config: Configuración de marca cargada desde ``social_config.json``.
        platforms: Plataformas habilitadas en esta ejecución.

    Returns:
        dict[str, dict[str, Any]]: Aspectos cuyo destino intersecta con las
                                   plataformas pedidas.
    """
    declared = config.get("visual_prompts", {}).get("aspect_ratios", {})
    if not isinstance(declared, dict):
        return {}

    selected: dict[str, dict[str, Any]] = {}
    for name, spec in declared.items():
        if not isinstance(spec, dict):
            continue
        targets = spec.get("platforms", [])
        if not isinstance(targets, (list, tuple)):
            continue
        # Los aspectos declaran formatos ("instagram_feed"), así que se compara
        # contra la plataforma base de cada formato.
        if any(platform_of_format(target) in platforms for target in targets):
            selected[str(name)] = spec

    return selected


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


def build_visual_prompts(
    payload: dict[str, Any],
    config: dict[str, Any],
    aspects: dict[str, dict[str, Any]],
) -> list[VisualPrompt]:
    """Construye los prompts visuales a partir del JSON del modelo.

    Función pura: no invoca al modelo. Valida cada prompt y compone el prompt
    negativo definitivo y la variante para Midjourney.

    Args:
        payload: Objeto JSON devuelto por el modelo.
        config: Configuración de marca cargada desde ``social_config.json``.
        aspects: Aspectos esperados, indexados por nombre.

    Returns:
        list[VisualPrompt]: Prompts validados, en orden de aparición.

    Raises:
        VisualPromptGenerationError: Si no se obtuvo ningún prompt utilizable.
    """
    visual_config = config.get("visual_prompts", {})
    base_negative = str(visual_config.get("negative_prompt", ""))
    midjourney_suffix = str(visual_config.get("midjourney_suffix", "")).strip()
    settings = visual_config.get("default_settings", {})
    if not isinstance(settings, dict):
        settings = {}

    raw_prompts = payload.get("prompts")
    if not isinstance(raw_prompts, (list, tuple)):
        raise VisualPromptGenerationError(
            "El modelo no entregó la lista 'prompts' en el JSON visual."
        )

    prompts: list[VisualPrompt] = []
    seen_aspects: set[str] = set()

    for entry in raw_prompts:
        if not isinstance(entry, dict):
            continue

        aspect = entry.get("aspect")
        aspect = str(aspect).strip().lower() if aspect is not None else ""
        if aspect not in aspects or aspect in seen_aspects:
            if aspect:
                logger.debug("Aspecto ignorado por no ser requerido: %s", aspect)
            continue

        spec = aspects[aspect]
        prompt = entry.get("prompt")
        prompt = _collapse_whitespace(prompt) if isinstance(prompt, str) else ""
        if not prompt:
            logger.warning("El aspecto '%s' llegó sin prompt: se omite.", aspect)
            continue

        try:
            validate_visual_prompt(prompt)
        except VisualPromptGenerationError as exc:
            logger.warning("Prompt del aspecto '%s' descartado: %s", aspect, exc)
            continue

        extra_negative = entry.get("extra_negative")
        extra_negative = extra_negative if isinstance(extra_negative, str) else ""
        negative = _compose_negative_prompt(base_negative, extra_negative)

        ratio = str(spec.get("ratio", "")).strip()
        flag = str(spec.get("midjourney_flag", "")).strip()
        targets = [str(item) for item in spec.get("platforms", [])]

        negative_flag = f"--no {negative}" if negative else ""
        midjourney_prompt = " ".join(
            chunk
            for chunk in (prompt, flag, midjourney_suffix, negative_flag)
            if chunk
        )

        prompts.append(
            VisualPrompt(
                aspect=aspect,
                aspect_ratio=ratio,
                platforms=targets,
                prompt=prompt,
                negative_prompt=negative,
                midjourney_prompt=midjourney_prompt,
                settings=dict(settings),
            )
        )
        seen_aspects.add(aspect)

    missing = sorted(set(aspects) - seen_aspects)
    if missing:
        logger.warning(
            "Faltan prompts visuales para los aspectos: %s.", ", ".join(missing)
        )

    if not prompts:
        raise VisualPromptGenerationError(
            "No se obtuvo ningún prompt visual válido en la respuesta del modelo."
        )

    return prompts


def generate_visual_prompts(
    article: ArticleSource,
    copy: SocialCopy,
    config: dict[str, Any],
    client: Any,
    platforms: list[str],
) -> list[VisualPrompt]:
    """Genera los prompts visuales en inglés para un artículo.

    Args:
        article: Artículo de origen ya parseado.
        copy: Copys ya generados, usados para alinear el concepto visual.
        config: Configuración de marca cargada desde ``social_config.json``.
        client: Cliente LLM con el método ``generate_report``.
        platforms: Plataformas habilitadas en esta ejecución.

    Returns:
        list[VisualPrompt]: Prompts validados. Lista vacía si no hay aspectos
                            aplicables a las plataformas pedidas.

    Raises:
        VisualPromptGenerationError: Si se agotan los intentos sin obtener
                                     ningún prompt utilizable.
    """
    aspects = enabled_aspects(config, platforms)
    if not aspects:
        logger.info(
            "No hay aspectos visuales aplicables a las plataformas pedidas: "
            "se omiten los prompts de imagen."
        )
        return []

    system_prompt = build_visual_prompt_system_prompt(config)
    base_user_prompt = build_visual_prompt_user_prompt(
        article, copy, config, aspects=aspects
    )

    attempts = SOCIAL_JSON_MAX_RETRIES + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        user_prompt = base_user_prompt
        if attempt > 1:
            user_prompt += _RETRY_NOTE.format(reason=last_error)

        logger.info(
            "Solicitando prompts visuales al modelo (intento %d/%d).",
            attempt,
            attempts,
        )
        raw_response = client.generate_report(system_prompt, user_prompt)

        try:
            payload = extract_json_object(raw_response)
        except JsonExtractionError as exc:
            last_error = exc
            logger.warning(
                "Intento %d sin JSON válido en los prompts visuales: %s",
                attempt,
                exc,
            )
            continue

        try:
            prompts = build_visual_prompts(payload, config, aspects)
        except VisualPromptGenerationError as exc:
            last_error = exc
            logger.warning(
                "Intento %d sin prompts visuales válidos: %s", attempt, exc
            )
            continue

        return prompts

    raise VisualPromptGenerationError(
        f"No se pudieron generar prompts visuales válidos tras {attempts} "
        f"intento(s). Último error: {last_error}"
    )
