"""Resolución de límites por plataforma para el subsistema RRSS.

Los límites viven en ``social_config.json`` para poder ajustarlos sin tocar
código, pero el subsistema debe seguir funcionando si el archivo no los
declara. Este módulo combina ambas fuentes: los defaults de ``config.py`` y
la sobrescritura opcional del archivo de configuración de marca.
"""

from typing import Any

from ..config import (
    SOCIAL_FACEBOOK_MAX_HASHTAGS,
    SOCIAL_FACEBOOK_POST_MAX_CHARS,
    SOCIAL_IG_CAPTION_MAX_CHARS,
    SOCIAL_IG_MAX_HASHTAGS,
    SOCIAL_X_MAX_CHARS,
    SOCIAL_X_MAX_HASHTAGS,
    SOCIAL_X_THREAD_MAX_TWEETS,
    SOCIAL_X_THREAD_MIN_TWEETS,
)

# Plataformas soportadas, en el orden editorial habitual de publicación
ALL_PLATFORMS: tuple[str, ...] = ("x", "facebook", "instagram")

# Límites por defecto, usados cuando la configuración no los sobrescribe
DEFAULT_SPECS: dict[str, dict[str, Any]] = {
    "x": {
        "label": "X",
        "max_chars": SOCIAL_X_MAX_CHARS,
        "thread_min_tweets": SOCIAL_X_THREAD_MIN_TWEETS,
        "thread_max_tweets": SOCIAL_X_THREAD_MAX_TWEETS,
        "max_hashtags": SOCIAL_X_MAX_HASHTAGS,
    },
    "facebook": {
        "label": "Facebook",
        "max_chars": SOCIAL_FACEBOOK_POST_MAX_CHARS,
        "max_hashtags": SOCIAL_FACEBOOK_MAX_HASHTAGS,
    },
    "instagram": {
        "label": "Instagram",
        "caption_max_chars": SOCIAL_IG_CAPTION_MAX_CHARS,
        "max_hashtags": SOCIAL_IG_MAX_HASHTAGS,
    },
}


def platform_specs(config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Devuelve los límites de cada plataforma ya resueltos.

    Solo se aceptan sobrescrituras de claves conocidas, con enteros positivos
    o textos no vacíos, de modo que un valor mal escrito en el JSON no pueda
    romper la validación de los copys.

    Args:
        config: Configuración de marca cargada desde ``social_config.json``.

    Returns:
        dict[str, dict[str, Any]]: Mapa plataforma → límites resueltos.
    """
    specs = {name: dict(spec) for name, spec in DEFAULT_SPECS.items()}

    platforms = (config or {}).get("platforms")
    if not isinstance(platforms, dict):
        return specs

    for name, spec in specs.items():
        override = platforms.get(name)
        if not isinstance(override, dict):
            continue
        for key, value in override.items():
            if key not in spec or isinstance(value, bool):
                continue
            # Solo se acepta el valor si respeta el tipo del default, de modo
            # que un texto mal ubicado no pueda romper la validación de copys.
            default = spec[key]
            if isinstance(default, int) and isinstance(value, int) and value > 0:
                spec[key] = value
            elif (
                isinstance(default, str)
                and isinstance(value, str)
                and value.strip()
            ):
                spec[key] = value.strip()

    return specs


def platform_of_format(format_name: str) -> str:
    """Deriva la plataforma a partir del nombre de un formato.

    Los formatos se nombran con el prefijo de su plataforma
    ("instagram_feed", "instagram_story", "x", "facebook"), lo que permite
    filtrar plantillas y aspectos visuales sin mantener un mapa adicional.

    Args:
        format_name: Nombre del formato de plataforma.

    Returns:
        str: Identificador de plataforma.
    """
    return str(format_name).split("_", 1)[0].strip().lower()


def platform_spec(config: dict[str, Any] | None, platform: str) -> dict[str, Any]:
    """Devuelve los límites de una plataforma concreta.

    Args:
        config: Configuración de marca cargada desde ``social_config.json``.
        platform: Identificador de plataforma ("x", "facebook", "instagram").

    Returns:
        dict[str, Any]: Límites resueltos de la plataforma.

    Raises:
        ValueError: Si la plataforma no está soportada.
    """
    specs = platform_specs(config)
    if platform not in specs:
        raise ValueError(
            f"Plataforma no soportada: {platform!r}. "
            f"Opciones válidas: {', '.join(sorted(specs))}."
        )
    return specs[platform]


def thread_bounds(spec: dict[str, Any]) -> tuple[int, int]:
    """Extrae los límites de largo del hilo garantizando un rango coherente.

    Si la configuración quedó invertida (mínimo mayor que máximo), se ordena
    el rango en lugar de fallar, porque un hilo fuera de rango es un detalle
    de estilo y no debe abortar la generación.

    Args:
        spec: Límites resueltos de la plataforma X.

    Returns:
        tuple[int, int]: Cantidad mínima y máxima de tweets del hilo.
    """
    minimum = int(spec.get("thread_min_tweets", SOCIAL_X_THREAD_MIN_TWEETS))
    maximum = int(spec.get("thread_max_tweets", SOCIAL_X_THREAD_MAX_TWEETS))
    if minimum > maximum:
        minimum, maximum = maximum, minimum
    return max(1, minimum), max(1, maximum)


def parse_platforms(raw: str | None) -> list[str]:
    """Interpreta la lista de plataformas pedida por línea de comandos.

    Args:
        raw: Texto con plataformas separadas por comas (ej: "x,instagram").
             Si es None o está vacío, se devuelven todas las plataformas.

    Returns:
        list[str]: Plataformas solicitadas, sin duplicados y en el orden
                   editorial de ``ALL_PLATFORMS``.

    Raises:
        ValueError: Si se pide una plataforma desconocida.
    """
    if raw is None or not raw.strip():
        return list(ALL_PLATFORMS)

    requested: list[str] = []
    unknown: list[str] = []

    for chunk in raw.split(","):
        name = chunk.strip().lower()
        if not name:
            continue
        if name not in ALL_PLATFORMS:
            unknown.append(name)
        elif name not in requested:
            requested.append(name)

    if unknown:
        raise ValueError(
            f"Plataforma(s) desconocida(s): {', '.join(unknown)}. "
            f"Opciones válidas: {', '.join(ALL_PLATFORMS)}."
        )

    if not requested:
        return list(ALL_PLATFORMS)

    return [name for name in ALL_PLATFORMS if name in requested]
