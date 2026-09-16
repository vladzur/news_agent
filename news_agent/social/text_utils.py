"""Utilidades de texto para el subsistema RRSS.

Funciones puras y deterministas para todo lo que debe cumplir reglas de
plataforma: recortar un texto al límite de caracteres y normalizar hashtags.
Se aíslan aquí para poder probarlas sin invocar al modelo ni a Pillow.
"""

import re

# Cierres de oración, con cierre de comillas opcional
_SENTENCE_END_RE = re.compile(r"[.!?…][\"”'’)]?\s")

# Caracteres no admitidos en un hashtag (se conservan letras, dígitos y "_",
# incluidas las vocales acentuadas y la eñe por ser \w en modo Unicode)
_HASHTAG_CLEAN_RE = re.compile(r"[^\w]", re.UNICODE)

# Separadores de palabras dentro de un hashtag
_WORD_SPLIT_RE = re.compile(r"\s+")

# Hashtags al final de un texto, con los espacios que los preceden
_TRAILING_HASHTAGS_RE = re.compile(r"(?:\s*#[^\s#]+)+\s*$")


def strip_trailing_hashtags(text: str) -> str:
    """Quita los hashtags que el modelo haya dejado al final del texto.

    Los hashtags se publican desde el campo propio del contrato, no dentro del
    cuerpo del tweet o del post. Cuando el modelo los incluye igualmente en el
    texto, este se recorta para evitar que aparezcan duplicados.

    Args:
        text: Texto del copy.

    Returns:
        str: Texto sin la tanda final de hashtags.
    """
    return _TRAILING_HASHTAGS_RE.sub("", text or "").rstrip()


def fit_char_limit(text: str, limit: int) -> tuple[str, bool]:
    """Recorta un texto para que quepa en un límite de caracteres.

    Intenta cortar en el cierre de la última oración completa que quepa; si no
    hay ninguno, corta en el último espacio y agrega puntos suspensivos. Nunca
    devuelve un texto más largo que el límite.

    Args:
        text: Texto original.
        limit: Cantidad máxima de caracteres admitida.

    Returns:
        tuple[str, bool]: Texto ajustado y una marca de si hubo recorte.
    """
    if limit <= 0:
        return "", bool(text)
    if text is None:
        return "", False

    if len(text) <= limit:
        return text, False

    truncated = text[:limit]

    # Corte limpio en el final de la última oración completa
    for match in reversed(list(_SENTENCE_END_RE.finditer(truncated))):
        candidate = truncated[: match.end()].strip()
        if candidate:
            return candidate, True

    # Corte en el último espacio disponible
    stripped = truncated.rstrip()
    if " " in stripped:
        stripped = stripped[: stripped.rfind(" ")].rstrip()

    if not stripped:
        stripped = truncated

    if len(stripped) < limit:
        stripped = f"{stripped}…"

    return stripped[:limit], True


def sanitize_hashtag(raw: str) -> str:
    """Normaliza un hashtag suelto al formato publicable.

    Quita el símbolo #, une las palabras separadas por espacios en formato
    CamelCase ("La Araucania" → "LaAraucania") y descarta cualquier carácter
    que no sea letra, dígito o guion bajo.

    Args:
        raw: Hashtag tal como lo devolvió el modelo.

    Returns:
        str: Hashtag limpio, sin el símbolo #. Vacío si no queda nada usable.
    """
    text = (raw or "").strip().lstrip("#").strip()
    if not text:
        return ""

    words = [word for word in _WORD_SPLIT_RE.split(text) if word]
    if not words:
        return ""

    joined = words[0] + "".join(
        word[:1].upper() + word[1:] for word in words[1:]
    )
    return _HASHTAG_CLEAN_RE.sub("", joined)


def sanitize_hashtags(raw: object, limit: int) -> list[str]:
    """Normaliza una lista de hashtags y la recorta al máximo permitido.

    Args:
        raw: Valor crudo devuelto por el modelo. Si no es una lista, se
             devuelve una lista vacía.
        limit: Cantidad máxima de hashtags admitida.

    Returns:
        list[str]: Hashtags limpios, sin duplicados y en orden de aparición.
    """
    if not isinstance(raw, (list, tuple)) or limit <= 0:
        return []

    hashtags: list[str] = []
    seen: set[str] = set()

    for item in raw:
        if not isinstance(item, str):
            continue
        cleaned = sanitize_hashtag(item)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        hashtags.append(cleaned)
        if len(hashtags) >= limit:
            break

    return hashtags


def render_hashtags(hashtags: list[str]) -> str:
    """Compone la cadena de hashtags lista para publicar.

    Args:
        hashtags: Hashtags sin el símbolo #.

    Returns:
        str: Hashtags separados por espacio, cada uno con su #.
    """
    return " ".join(f"#{hashtag}" for hashtag in hashtags if hashtag)


def ensure_list_of_text(raw: object) -> list[str]:
    """Coacciona un valor crudo del modelo a una lista de textos limpios.

    Args:
        raw: Valor crudo devuelto por el modelo.

    Returns:
        list[str]: Lista de textos no vacíos, sin elementos en blanco.
    """
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if not isinstance(raw, (list, tuple)):
        return []

    items: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            items.append(item.strip())
    return items
