"""Generación y validación de los copys de redes sociales.

El modelo entrega el material creativo, pero las reglas duras de cada
plataforma se aplican aquí de forma determinista: límites de caracteres,
largo del hilo, topes de hashtags, cifras verificadas contra el artículo y
cita literal. Así el resultado es publicable aunque el modelo se desvíe del
contrato.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from ..config import (
    SOCIAL_JSON_MAX_RETRIES,
    SOCIAL_MAX_HOOKS,
    SOCIAL_MIN_HOOKS,
)
from ..report_writer import _slugify
from .json_utils import JsonExtractionError, extract_json_object
from .models import (
    ArticleSource,
    FacebookCopy,
    InstagramCopy,
    QuoteCard,
    SocialCopy,
    XCopy,
    normalize_for_match,
)
from .platform_specs import ALL_PLATFORMS, platform_spec, thread_bounds
from .prompt_builder import build_copy_system_prompt, build_copy_user_prompt
from .text_utils import (
    ensure_list_of_text,
    fit_char_limit,
    render_hashtags,
    sanitize_hashtags,
    strip_trailing_hashtags,
)

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class SocialCopyValidationError(Exception):
    """Excepción para respuestas del modelo que no cumplen el contrato de copys."""


# Topes de los campos auxiliares del copy
_HOOK_MAX_CHARS = 200
_BULLET_MAX_CHARS = 180
_CTA_MAX_CHARS = 90

# Largo máximo del texto alternativo según las restricciones de cada plataforma
_ALT_TEXT_LIMITS: dict[str, int] = {
    "x": 300,
    "facebook": 200,
    "instagram": 100,
}

# Nota que se agrega al prompt cuando la respuesta anterior no fue utilizable
_RETRY_NOTE = (
    "\n\n## Corrección\n\n"
    "Tu respuesta anterior no sirvió ({reason}). Responde de nuevo "
    "únicamente con el objeto JSON completo, sin texto adicional y sin "
    "bloques de código Markdown."
)


# ---------------------------------------------------------------------------
# Helpers de construcción
# ---------------------------------------------------------------------------


def _brand_name(config: dict[str, Any] | None) -> str:
    """Obtiene el nombre de marca desde la configuración.

    Args:
        config: Configuración de marca cargada desde ``social_config.json``.

    Returns:
        str: Nombre de marca, o un valor por defecto si no está declarado.
    """
    brand = (config or {}).get("brand")
    if isinstance(brand, dict):
        name = brand.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "La Chispa Sur"


def _collapse_whitespace(text: str) -> str:
    """Colapsa los espacios en blanco de un texto en una sola línea.

    Args:
        text: Texto original.

    Returns:
        str: Texto sin saltos de línea ni espacios repetidos.
    """
    return " ".join((text or "").split())


def _build_quote_card(
    raw: object,
    article: ArticleSource,
    config: dict[str, Any] | None,
) -> QuoteCard:
    """Construye la tarjeta de cita verificando que la cita sea literal.

    Args:
        raw: Valor crudo del campo ``quote_card``.
        article: Artículo de origen.
        config: Configuración de marca.

    Returns:
        QuoteCard: Cita verificada y su atribución.
    """
    data = raw if isinstance(raw, dict) else {}
    quote = data.get("quote")
    quote = _collapse_whitespace(quote) if isinstance(quote, str) else ""
    attribution = data.get("attribution")
    attribution = _collapse_whitespace(attribution) if isinstance(attribution, str) else ""

    verbatim = bool(quote) and article.contains_verbatim(quote)

    if not verbatim:
        fallback = article.quote_candidates[0] if article.quote_candidates else ""
        if not fallback:
            # Sin candidatas: se abre con el lead, que es material verificado,
            # antes que publicar una cita que no se pudo comprobar.
            fallback = article.lead.split(". ")[0].strip()

        if fallback:
            logger.warning(
                "La cita del modelo no aparece literalmente en el artículo; "
                "se usa material verificado del propio artículo."
            )
            quote = fallback
            verbatim = True
        else:
            logger.warning(
                "No se pudo verificar la cita contra el artículo y no hay "
                "material alternativo: se conserva la del modelo marcada "
                "como no literal."
            )

    if not attribution:
        attribution = _brand_name(config)

    return QuoteCard(quote=quote, attribution=attribution, verbatim=verbatim)


def _filter_key_figures(raw: object, article: ArticleSource) -> list[str]:
    """Conserva solo las cifras que existen realmente en el artículo.

    Args:
        raw: Valor crudo del campo ``key_figures``.
        article: Artículo de origen.

    Returns:
        list[str]: Cifras verificadas contra el texto del artículo.
    """
    candidates = ensure_list_of_text(raw)
    haystack = normalize_for_match(article.raw_text)

    figures: list[str] = []
    for candidate in candidates:
        normalized = normalize_for_match(candidate)
        if normalized and normalized in haystack:
            figures.append(candidate)
        else:
            logger.debug(
                "Cifra descartada por no aparecer en el artículo: %s", candidate
            )

    if not figures and article.key_figures:
        logger.warning(
            "Ninguna de las cifras propuestas por el modelo se pudo verificar "
            "contra el artículo (%s); se usan las %d detectadas directamente "
            "en el texto.",
            ", ".join(candidates) if candidates else "sin propuestas",
            len(article.key_figures),
        )
        figures = list(article.key_figures)

    return figures


def _build_alt_text(
    raw: object,
    platforms: list[str],
    article: ArticleSource,
) -> dict[str, str]:
    """Construye los textos alternativos por plataforma.

    Args:
        raw: Valor crudo del campo ``alt_text``.
        platforms: Plataformas habilitadas.
        article: Artículo de origen, usado como respaldo.

    Returns:
        dict[str, str]: Texto alternativo por plataforma, dentro del límite
                        de cada una.
    """
    data = raw if isinstance(raw, dict) else {}
    fallback = f"Ilustración editorial: {article.title}"
    alt_text: dict[str, str] = {}

    for platform in platforms:
        limit = _ALT_TEXT_LIMITS.get(platform, 200)
        value = data.get(platform)
        text = _collapse_whitespace(value) if isinstance(value, str) else ""
        if not text:
            text = fallback
        alt_text[platform] = fit_char_limit(text, limit)[0]

    return alt_text


def _build_x_copy(raw: object, spec: dict[str, Any]) -> XCopy:
    """Construye y normaliza el copy de X/Twitter.

    Args:
        raw: Valor crudo del campo ``x``.
        spec: Límites resueltos de la plataforma.

    Returns:
        XCopy: Hilo ajustado a los límites de la plataforma.

    Raises:
        SocialCopyValidationError: Si no hay ningún tweet utilizable.
    """
    data = raw if isinstance(raw, dict) else {}
    limit = int(spec.get("max_chars", 280))
    minimum, maximum = thread_bounds(spec)
    max_hashtags = int(spec.get("max_hashtags", 0))

    thread = ensure_list_of_text(data.get("thread"))
    hook_tweet = data.get("hook_tweet")
    hook_tweet = _collapse_whitespace(hook_tweet) if isinstance(hook_tweet, str) else ""

    # El contrato exige que el primer tweet sea el gancho
    if hook_tweet and thread:
        thread[0] = hook_tweet
    elif hook_tweet and not thread:
        thread = [hook_tweet]
    elif not hook_tweet and thread:
        hook_tweet = thread[0]

    if not thread:
        raise SocialCopyValidationError(
            "El copy de X no incluye ningún tweet ('x.thread' está vacío)."
        )

    if len(thread) > maximum:
        logger.warning(
            "Hilo de X recortado de %d a %d tweets.", len(thread), maximum
        )
        thread = thread[:maximum]

    if len(thread) < minimum:
        logger.warning(
            "El hilo de X tiene %d tweets, por debajo del mínimo de %d.",
            len(thread),
            minimum,
        )

    fitted_thread: list[str] = []
    for tweet in thread:
        fitted, trimmed = fit_char_limit(_collapse_whitespace(tweet), limit)
        if trimmed:
            logger.warning(
                "Tweet recortado al límite de %d caracteres.", limit
            )
        fitted_thread.append(fitted)

    hashtags = sanitize_hashtags(data.get("hashtags"), max_hashtags)
    # El modelo puede haber incluido los hashtags dentro del propio texto: se
    # recortan antes de anexarlos desde el campo del contrato.
    fitted_thread[-1] = _fit_closing_tweet(
        strip_trailing_hashtags(fitted_thread[-1]), hashtags, limit
    )

    return XCopy(
        hook_tweet=fitted_thread[0],
        thread=fitted_thread,
        hashtags=hashtags,
    )


def _fit_closing_tweet(text: str, hashtags: list[str], limit: int) -> str:
    """Ajusta el tweet de cierre para que los hashtags quepan dentro.

    Args:
        text: Texto del tweet de cierre.
        hashtags: Hashtags que se anexarán.
        limit: Límite de caracteres de la plataforma.

    Returns:
        str: Tweet de cierre, con hashtags si caben.
    """
    rendered = render_hashtags(hashtags)
    if not rendered:
        return text

    available = limit - len(rendered) - 1
    if available <= 0:
        logger.warning(
            "Los hashtags no caben en el tweet de cierre: quedan solo como "
            "sugerencia aparte."
        )
        return text

    fitted, trimmed = fit_char_limit(text, available)
    if trimmed:
        logger.warning(
            "Tweet de cierre recortado para dejar espacio a los hashtags."
        )
    return f"{fitted} {rendered}"


def _build_facebook_copy(raw: object, spec: dict[str, Any]) -> FacebookCopy:
    """Construye y normaliza el copy de Facebook.

    Args:
        raw: Valor crudo del campo ``facebook``.
        spec: Límites resueltos de la plataforma.

    Returns:
        FacebookCopy: Post ajustado a los límites de la plataforma.

    Raises:
        SocialCopyValidationError: Si no hay texto de post.
    """
    data = raw if isinstance(raw, dict) else {}
    post = data.get("post")
    post = strip_trailing_hashtags(post.strip()) if isinstance(post, str) else ""

    if not post:
        raise SocialCopyValidationError(
            "El copy de Facebook no incluye el texto del post "
            "('facebook.post' está vacío)."
        )

    limit = int(spec.get("max_chars", 1200))
    post, trimmed = fit_char_limit(post, limit)
    if trimmed:
        logger.warning(
            "Post de Facebook recortado al límite de %d caracteres.", limit
        )

    hashtags = sanitize_hashtags(
        data.get("hashtags"), int(spec.get("max_hashtags", 0))
    )
    return FacebookCopy(post=post, hashtags=hashtags)


def _build_instagram_copy(raw: object, spec: dict[str, Any]) -> InstagramCopy:
    """Construye y normaliza el copy de Instagram.

    Args:
        raw: Valor crudo del campo ``instagram``.
        spec: Límites resueltos de la plataforma.

    Returns:
        InstagramCopy: Caption ajustada a los límites de la plataforma.

    Raises:
        SocialCopyValidationError: Si no hay texto de caption.
    """
    data = raw if isinstance(raw, dict) else {}
    caption = data.get("caption")
    caption = (
        strip_trailing_hashtags(caption.strip()) if isinstance(caption, str) else ""
    )

    if not caption:
        raise SocialCopyValidationError(
            "El copy de Instagram no incluye el texto de la publicación "
            "('instagram.caption' está vacía)."
        )

    limit = int(spec.get("caption_max_chars", 2200))
    caption, trimmed = fit_char_limit(caption, limit)
    if trimmed:
        logger.warning(
            "Caption de Instagram recortada al límite de %d caracteres.", limit
        )

    hashtags = sanitize_hashtags(
        data.get("hashtags"), int(spec.get("max_hashtags", 0))
    )
    return InstagramCopy(caption=caption, hashtags=hashtags)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def build_social_copy(
    payload: dict[str, Any],
    article: ArticleSource,
    config: dict[str, Any] | None = None,
    platforms: list[str] | None = None,
) -> SocialCopy:
    """Construye el paquete de copys a partir del JSON del modelo.

    Función pura: no invoca al modelo. Toda la validación y el ajuste a los
    límites de plataforma ocurre aquí.

    Args:
        payload: Objeto JSON devuelto por el modelo.
        article: Artículo de origen.
        config: Configuración de marca cargada desde ``social_config.json``.
        platforms: Plataformas a conservar. Por defecto, todas.

    Returns:
        SocialCopy: Copys validados y listos para publicar.

    Raises:
        SocialCopyValidationError: Si faltan campos obligatorios del contrato.
    """
    selected = list(platforms) if platforms else list(ALL_PLATFORMS)

    hooks = ensure_list_of_text(payload.get("hooks"))[:SOCIAL_MAX_HOOKS]
    if not hooks:
        raise SocialCopyValidationError(
            "El modelo no entregó ningún gancho ('hooks' está vacío)."
        )
    if len(hooks) < SOCIAL_MIN_HOOKS:
        logger.warning(
            "Solo se recibieron %d gancho(s); se esperaban al menos %d.",
            len(hooks),
            SOCIAL_MIN_HOOKS,
        )
    hooks = [fit_char_limit(_collapse_whitespace(item), _HOOK_MAX_CHARS)[0] for item in hooks]

    summary = ensure_list_of_text(payload.get("summary"))
    if not summary:
        raise SocialCopyValidationError(
            "El modelo no entregó síntesis ejecutiva ('summary' está vacío)."
        )
    summary = [
        fit_char_limit(_collapse_whitespace(item), _BULLET_MAX_CHARS)[0]
        for item in summary
    ]

    hook = payload.get("hook")
    hook = _collapse_whitespace(hook) if isinstance(hook, str) else ""
    if not hook:
        logger.warning(
            "El modelo no entregó 'hook': se usa el primer gancho de la lista."
        )
        hook = hooks[0]
    hook = fit_char_limit(hook, _HOOK_MAX_CHARS)[0]

    cta = payload.get("cta")
    cta = _collapse_whitespace(cta) if isinstance(cta, str) else ""
    cta = fit_char_limit(cta, _CTA_MAX_CHARS)[0]

    return SocialCopy(
        title=article.title,
        slug=_slugify(article.title),
        source_path=str(article.path),
        generated_at=datetime.now(timezone.utc).isoformat(),
        hooks=hooks,
        summary=summary,
        hook=hook,
        quote_card=_build_quote_card(payload.get("quote_card"), article, config),
        key_figures=_filter_key_figures(payload.get("key_figures"), article),
        cta=cta,
        alt_text=_build_alt_text(payload.get("alt_text"), selected, article),
        x=_build_x_copy(payload.get("x"), platform_spec(config, "x")),
        facebook=_build_facebook_copy(
            payload.get("facebook"), platform_spec(config, "facebook")
        ),
        instagram=_build_instagram_copy(
            payload.get("instagram"), platform_spec(config, "instagram")
        ),
    )


def generate_social_copy(
    article: ArticleSource,
    config: dict[str, Any],
    client: Any,
    platforms: list[str] | None = None,
) -> SocialCopy:
    """Genera los copys de redes sociales para un artículo.

    Reintenta la llamada al modelo cuando la respuesta no es JSON válido o no
    cumple el contrato, hasta agotar ``SOCIAL_JSON_MAX_RETRIES``.

    Args:
        article: Artículo de origen ya parseado.
        config: Configuración de marca cargada desde ``social_config.json``.
        client: Cliente LLM con el método ``generate_report``.
        platforms: Plataformas a conservar. Por defecto, todas.

    Returns:
        SocialCopy: Copys validados y listos para publicar.

    Raises:
        SocialCopyValidationError: Si se agotan los intentos sin obtener un
                                   JSON de copys utilizable.
    """
    system_prompt = build_copy_system_prompt(config)
    base_user_prompt = build_copy_user_prompt(article, config)

    attempts = SOCIAL_JSON_MAX_RETRIES + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        user_prompt = base_user_prompt
        if attempt > 1:
            user_prompt += _RETRY_NOTE.format(reason=last_error)

        logger.info(
            "Solicitando copys de RRSS al modelo (intento %d/%d).",
            attempt,
            attempts,
        )
        raw_response = client.generate_report(system_prompt, user_prompt)

        try:
            payload = extract_json_object(raw_response)
        except JsonExtractionError as exc:
            last_error = exc
            logger.warning(
                "Intento %d sin JSON válido en la respuesta de copys: %s",
                attempt,
                exc,
            )
            continue

        try:
            return build_social_copy(payload, article, config, platforms=platforms)
        except SocialCopyValidationError as exc:
            last_error = exc
            logger.warning(
                "Intento %d con copys incompletos: %s", attempt, exc
            )

    raise SocialCopyValidationError(
        f"No se pudieron generar copys válidos tras {attempts} intento(s). "
        f"Último error: {last_error}"
    )
