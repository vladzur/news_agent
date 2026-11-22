"""Generación del prompt visual en inglés para ilustrar una columna.

El subsistema no genera imágenes: entrega al diseñador un único prompt listo
para Midjourney, con el prompt negativo de marca y los flags de versión y
proporción. El tratamiento se decide por columna con una precedencia explícita:
**representativo** cuando la columna gira en torno a figuras públicas políticas
—las muestra con parecido reconocible dentro de una composición editorial que
no puede confundirse con una fotografía—, **fotorrealista documental** cuando
hay hechos, lugares, objetos o escenas concretas y ninguna figura pública
central, y **caricatura** editorial solo cuando la columna es abstracta, no
nombra figuras públicas y no tiene una escena documentable.

La ilustración puede incluir rótulos breves en español —cifras, etiquetas,
sellos— integrados en la escena, porque refuerzan la idea del artículo. Lo que
se verifica en código es que el prompt esté en inglés, que nombre una paleta de
color, que el tratamiento declarado coincida con la técnica descrita, que
incorpore anclas concretas del artículo y que no reproduzca párrafos de texto:
los modelos de difusión convierten la tipografía extensa en ruido.
"""

import logging
import re
from typing import Any

from ..config import SOCIAL_JSON_MAX_RETRIES, SOCIAL_VISUAL_TREATMENTS
from .article_source import (
    anchor_in_text,
    article_mentions,
    extract_concrete_anchors,
)
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


# Tratamientos admitidos. La precedencia editorial vive en la configuración:
# las figuras públicas políticas exigen la composición representativa.
VISUAL_TREATMENTS = SOCIAL_VISUAL_TREATMENTS


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

# Contenido que no debe aparecer en una imagen editorial: violencia explícita
# y escenas fabricadas o suplantaciones de identidad. Las reglas sobre figuras
# públicas y personas privadas se redactan en el prompt, pero estos términos sí
# se pueden detectar de forma determinista.
_VIOLENCE_TERMS_RE = re.compile(
    r"\b(?:explicit\s+violence|graphic\s+violence|blood|bloody|gore|gory|"
    r"corpse|corpses|wounded|mutilated|dismembered|beheaded|massacre)\b",
    re.IGNORECASE,
)
_FAKE_SCENE_TERMS_RE = re.compile(
    r"\b(?:deepfake|deep\s+fake|face\s*swap|staged\s+reenactment|"
    r"fabricated\s+scene|fake\s+photo(?:graph)?)\b",
    re.IGNORECASE,
)

# Menciones negadas de violencia o escenas fabricadas: "no deepfake", "sin
# violencia explícita". El prompt positivo puede descartarlas expresamente sin
# que eso cuente como una petición; el negativo del comando es el que las
# prohíbe de verdad.
_NEGATED_FORBIDDEN_RE = re.compile(
    r"\b(?:no|not|never|without|free\s+of)\s+(?:a\s+|an\s+|the\s+)?"
    r"(?:explicit\s+violence|graphic\s+violence|violence|blood|gore|"
    r"corpses?|deepfake|deep\s+fake|face\s*swap|staged\s+reenactment|"
    r"fabricated\s+scene|fake\s+photo(?:graph)?)\b",
    re.IGNORECASE,
)

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

# Señales del tratamiento representativo: una composición editorial construida
# que muestra figuras reconocibles sin parecer una fotografía.
_REPRESENTATIVE_SIGNAL_RE = re.compile(
    r"\b(?:cut[- ]paper|paper\s+collage|collage|halftone|semi[- ]?tone|"
    r"screen[- ]print|silkscreen|risograph|posterised|posterized|"
    r"poster\s+art|ink\s+outlines?|paper\s+grain|linocut|woodcut|"
    r"graphic\s+panels?|editorial\s+portrait)\b",
    re.IGNORECASE,
)

# Realismo fotográfico que se rechaza en el tratamiento representativo: la
# composición debe leerse como una ilustración, no como una foto de prensa.
_REALISM_TERMS_RE = re.compile(
    r"\b(?:photorealistic|hyperrealistic|hyper[- ]realistic|lifelike|"
    r"realistic\s+skin|photographic|press\s+photograph|news\s+photograph|"
    r"candid\s+photograph|paparazzi|film\s+still|cinematic\s+still)\b",
    re.IGNORECASE,
)

# Frases negadas que mencionan la fotografía para descartarla. El modelo puede
# escribir "not a photograph" o "without news-photo realism" al describir una
# composición representativa; esas menciones no deben contar como lenguaje
# fotográfico. Solo se aplican a la comprobación del tratamiento representativo.
_NEGATED_PHOTO_RE = re.compile(
    r"\b(?:no|not|never|without|free\s+of)\s+(?:a\s+|an\s+|the\s+)?"
    r"(?:\w+\s+){0,2}(?:photograph|photographic|photojournalism|"
    r"documentary|realism|paparazzi|film\s+still|news\s+photograph)\b",
    re.IGNORECASE,
)

# Tropos que delatan un prompt abstracto donde la columna pedía una escena
# documental. Solo se rechazan en el tratamiento fotorrealista.
_ABSTRACT_TROPE_RE = re.compile(
    r"\b(?:abstract\s+(?:composition|illustration|concept|image)|"
    r"purely\s+symbolic|symbolic\s+composition|"
    r"conceptual\s+(?:image|art|composition)|surreal|dreamlike|"
    r"generic\s+scene|visual\s+metaphor|metaphor\s+for|"
    r"floating\s+(?:shapes|orbs|symbols|elements)|"
    r"glowing\s+(?:lines|orbs|networks?)|digital\s+network|hologram|"
    r"double\s+exposure)\b",
    re.IGNORECASE,
)

# Términos negativos que prohíben a las figuras públicas. Se rechazan en
# cualquier tratamiento: la columna debe mostrar a sus protagonistas.
_PUBLIC_FIGURE_BAN_RE = re.compile(
    r"\b(?:recogni[sz]able\s+politicians?|public\s+figures?|"
    r"real\s+politicians?|identifiable\s+politicians?)\b",
    re.IGNORECASE,
)

# Términos negativos que borran el rostro o el parecido. Solo se rechazan en
# el tratamiento representativo, donde las figuras deben ser reconocibles.
_LIKENESS_BAN_RE = re.compile(
    r"\b(?:real\s+faces?|identifiable\s+faces?|no\s+faces?|"
    r"faces?\s+(?:hidden|obscured|cropped|turned\s+away)|"
    r"(?:no|without|avoid|hide|erase|obscure)\s+(?:the\s+)?likeness|"
    r"(?:no|without|avoid)\s+resemblance|"
    r"anonymi[sz]e[ds]?|anonymi[sz]ed\s+figures?)\b",
    re.IGNORECASE,
)

# Frases que esconden a la figura dentro del prompt positivo representativo.
_HIDDEN_FIGURE_RE = re.compile(
    r"\b(?:faces?\s+(?:turned\s+away|hidden|obscured|cropped)|"
    r"back\s+of\s+(?:his|her|their)\s+head|faceless|"
    r"silhouetted?\s+(?:figure|politician|president|minister))\b",
    re.IGNORECASE,
)

# Mínimo de anclas concretas por tratamiento. Las composiciones con figuras o
# con una escena documental necesitan dos; la caricatura admite una.
_MIN_ANCHORS_CONCRETE = 2
_MIN_ANCHORS_CARICATURE = 1

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


def _find_forbidden_scene_terms(prompt: str) -> list[str]:
    """Detecta violencia explícita y escenas fabricadas en el prompt positivo.

    Args:
        prompt: Prompt positivo en inglés.

    Returns:
        list[str]: Términos prohibidos encontrados, sin duplicados.
    """
    cleaned = _NEGATED_FORBIDDEN_RE.sub(" ", prompt)
    matches = _VIOLENCE_TERMS_RE.findall(cleaned)
    matches += _FAKE_SCENE_TERMS_RE.findall(cleaned)
    return sorted({match.lower() for match in matches})


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


def has_representative_signal(prompt: str) -> bool:
    """Indica si un prompt describe una composición editorial representativa.

    Args:
        prompt: Prompt positivo en inglés.

    Returns:
        bool: True si el prompt nombra una técnica de composición construida.
    """
    return _REPRESENTATIVE_SIGNAL_RE.search(prompt or "") is not None


def _matched_terms(pattern: re.Pattern[str], text: str) -> list[str]:
    """Devuelve los términos distintos de un patrón, en minúsculas.

    Args:
        pattern: Expresión regular compilada.
        text: Texto a analizar.

    Returns:
        list[str]: Coincidencias normalizadas y ordenadas.
    """
    return sorted({match.group(0).lower() for match in pattern.finditer(text or "")})


def _strip_anchor_terms(text: str, anchors: list[str]) -> str:
    """Retira del texto las anclas conocidas del artículo.

    Los nombres propios en español —La Moneda, La Araucanía— aportan palabras
    funcionales que la heurística de idioma confundiría con un prompt escrito
    en español. Se retiran las anclas y los artículos que las preceden antes
    de evaluar, solo para esa comprobación.

    Args:
        text: Prompt positivo.
        anchors: Anclas concretas del artículo.

    Returns:
        str: Texto sin las anclas conocidas ni sus artículos.
    """
    cleaned = text or ""

    # Artículos y contracciones que acompañan a un nombre propio capitalizado:
    # "La Moneda", "Los Lagos", "del Congreso". Se retiran antes que las anclas
    # para que la palabra funcional no quede suelta. El lookahead distingue
    # caja para no borrar "la crisis" ni otras palabras comunes.
    cleaned = re.sub(
        r"\b(?:El|La|Los|Las|Del|el|la|los|las|del)\s+(?=[A-ZÁÉÍÓÚÑÜ])",
        " ",
        cleaned,
    )

    for anchor in sorted(anchors, key=len, reverse=True):
        if anchor:
            cleaned = re.sub(re.escape(anchor), " ", cleaned, flags=re.IGNORECASE)

    return cleaned


def _require_concrete_anchors(
    prompt: str,
    treatment: str,
    article: ArticleSource | None,
) -> None:
    """Exige que el prompt nombre anclas concretas del artículo.

    La fuerza de representación se mide de forma determinista: un prompt que no
    nombra ningún lugar, institución, persona, objeto ni cifra del artículo es
    demasiado abstracto. Si el artículo no ofrece anclas utilizables, la
    comprobación se omite para no bloquear la generación.

    Args:
        prompt: Prompt positivo en inglés.
        treatment: Tratamiento declarado.
        article: Artículo de origen, o None si no se dispone de él.

    Raises:
        VisualPromptGenerationError: Si el prompt no alcanza el mínimo de anclas.
    """
    if article is None:
        return

    anchors = extract_concrete_anchors(article)
    if not anchors:
        logger.warning(
            "El artículo no produjo anclas concretas; se omite la comprobación "
            "de fuerza de representación del prompt visual."
        )
        return

    minimum = (
        _MIN_ANCHORS_CARICATURE
        if treatment == "caricature"
        else _MIN_ANCHORS_CONCRETE
    )
    required = min(minimum, len(anchors))
    matched = [anchor for anchor in anchors if anchor_in_text(prompt, anchor)]
    if len(matched) < required:
        raise VisualPromptGenerationError(
            "El prompt visual no representa el contenido del artículo: se "
            f"esperaban al menos {required} ancla(s) concreta(s) "
            f"({', '.join(anchors[:6])}) y solo se encontraron "
            f"{len(matched)}. Nombra personas, lugares, instituciones, objetos "
            "o cifras que el artículo mencione."
        )


def _figure_in_prompt(prompt: str, figure: str) -> bool:
    """Comprueba si una figura pública aparece nombrada en el prompt.

    Se acepta el nombre completo o un token suficientemente largo —por
    ejemplo, el apellido— para tolerar que el modelo abrevie el nombre.

    Args:
        prompt: Prompt positivo en inglés.
        figure: Nombre declarado por el modelo.

    Returns:
        bool: True si la figura aparece en el prompt.
    """
    if anchor_in_text(prompt, figure):
        return True
    tokens = [token for token in re.split(r"\s+", figure or "") if len(token) >= 4]
    return any(anchor_in_text(prompt, token) for token in tokens)


def validate_visual_subjects(
    political_figures: list[str],
    treatment: str,
    prompt: str,
    article: ArticleSource | None = None,
) -> None:
    """Valida la coherencia entre tratamiento, figuras públicas y prompt.

    Args:
        political_figures: Figuras declaradas por el modelo.
        treatment: Tratamiento declarado.
        prompt: Prompt positivo en inglés.
        article: Artículo de origen, o None si no se dispone de él.

    Raises:
        VisualPromptGenerationError: Si el tratamiento y las figuras no son
                                     coherentes, si una figura no proviene del
                                     artículo o si no aparece en el prompt.
    """
    if treatment == "representative":
        if not political_figures:
            raise VisualPromptGenerationError(
                "El tratamiento representativo exige al menos una figura "
                "pública política en 'political_figures'. Si la columna no "
                "nombra a ninguna, usa 'photorealistic' o 'caricature'."
            )
    elif political_figures:
        raise VisualPromptGenerationError(
            "La columna declara figuras públicas políticas "
            f"({', '.join(political_figures)}), así que el tratamiento debe "
            "ser 'representative' para mostrarlas sin confundirse con una "
            "fotografía real."
        )

    for figure in political_figures:
        if article is not None and not article_mentions(article, figure):
            raise VisualPromptGenerationError(
                f"La figura pública '{figure}' no aparece en el artículo; no "
                "se puede inventar una persona ni atribuirle una imagen."
            )
        if not _figure_in_prompt(prompt, figure):
            raise VisualPromptGenerationError(
                f"La figura pública '{figure}' no está nombrada en el prompt "
                "positivo. Debe aparecer con un parecido reconocible."
            )


def validate_extra_negative(extra_negative: str, treatment: str) -> None:
    """Valida que el prompt negativo no borre a las figuras públicas.

    Args:
        extra_negative: Términos negativos agregados por el modelo.
        treatment: Tratamiento declarado.

    Raises:
        VisualPromptGenerationError: Si el negativo prohíbe figuras públicas o,
                                     en el tratamiento representativo, su
                                     rostro o parecido.
    """
    banned = _matched_terms(_PUBLIC_FIGURE_BAN_RE, extra_negative)
    if banned:
        raise VisualPromptGenerationError(
            "El prompt negativo prohíbe figuras públicas "
            f"({', '.join(banned)}); las figuras políticas de la columna deben "
            "mostrarse en una composición representativa, no borrarse."
        )

    if treatment == "representative":
        banned = _matched_terms(_LIKENESS_BAN_RE, extra_negative)
        if banned:
            raise VisualPromptGenerationError(
                "El prompt negativo del tratamiento representativo oculta a "
                f"las figuras públicas ({', '.join(banned)}); su parecido debe "
                "ser reconocible."
            )


def validate_visual_prompt(
    prompt: str,
    treatment: str,
    article: ArticleSource | None = None,
) -> None:
    """Valida un prompt positivo contra las restricciones de marca.

    Args:
        prompt: Prompt positivo en inglés.
        treatment: Tratamiento declarado: "photorealistic", "representative" o
                   "caricature".
        article: Artículo de origen, usado para exigir anclas concretas. Si se
                 omite, esa comprobación no se aplica.

    Raises:
        VisualPromptGenerationError: Si el tratamiento es desconocido, si el
                                     prompt está vacío, tiene un largo fuera de
                                     rango, no está en inglés, no nombra una
                                     paleta de color, pide bloques de texto en
                                     la imagen, incluye violencia explícita o
                                     escenas fabricadas, no coincide con la
                                     técnica del tratamiento declarado o no
                                     representa el contenido concreto del
                                     artículo.
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

    anchors = extract_concrete_anchors(article) if article is not None else []
    if looks_like_spanish(_strip_anchor_terms(prompt, anchors)):
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

    forbidden_terms = _find_forbidden_scene_terms(prompt)
    if forbidden_terms:
        raise VisualPromptGenerationError(
            "El prompt visual incluye contenido prohibido "
            f"({', '.join(forbidden_terms)}): no se admite violencia explícita "
            "ni escenas fabricadas o suplantaciones de identidad."
        )

    if treatment == "photorealistic":
        if not has_photo_signal(prompt):
            raise VisualPromptGenerationError(
                "El tratamiento es fotorrealista, pero el prompt no describe "
                "una fotografía (lente, luz natural, reportaje o realismo "
                "fotográfico)."
            )
        illustration = _matched_terms(_ILLUSTRATION_SIGNAL_RE, prompt)
        if illustration:
            raise VisualPromptGenerationError(
                "El tratamiento es fotorrealista, pero el prompt declara una "
                f"técnica de ilustración ({', '.join(illustration)})."
            )
        abstract = _matched_terms(_ABSTRACT_TROPE_RE, prompt)
        if abstract:
            raise VisualPromptGenerationError(
                "El prompt fotorrealista es demasiado abstracto "
                f"({', '.join(abstract)}); debe describir una escena concreta "
                "del artículo."
            )

    if treatment == "representative":
        if not has_representative_signal(prompt):
            raise VisualPromptGenerationError(
                "El tratamiento es representativo, pero el prompt no nombra "
                "una composición editorial construida (collage, semitono, "
                "serigrafía, afiche o risografía)."
            )
        positive_claims = _NEGATED_PHOTO_RE.sub(" ", prompt)
        realism = _matched_terms(_PHOTO_SIGNAL_RE, positive_claims)
        realism += _matched_terms(_REALISM_TERMS_RE, positive_claims)
        if realism:
            raise VisualPromptGenerationError(
                "El tratamiento es representativo, pero el prompt usa lenguaje "
                f"fotográfico ({', '.join(sorted(set(realism)))}); la "
                "composición debe leerse como una ilustración."
            )
        hidden = _matched_terms(_HIDDEN_FIGURE_RE, prompt)
        if hidden:
            raise VisualPromptGenerationError(
                "El prompt representativo oculta a la figura pública "
                f"({', '.join(hidden)}); su rostro debe ser reconocible."
            )

    if treatment == "caricature":
        if not has_illustration_signal(prompt):
            raise VisualPromptGenerationError(
                "El tratamiento es caricatura, pero el prompt no nombra una "
                "técnica de ilustración ni caricaturiza a nadie."
            )
        positive_claims = _NEGATED_PHOTO_RE.sub(" ", prompt)
        realism = _matched_terms(_PHOTO_SIGNAL_RE, positive_claims)
        if realism:
            raise VisualPromptGenerationError(
                "El tratamiento es caricatura, pero el prompt usa lenguaje "
                f"fotográfico ({', '.join(realism)}); la caricatura debe "
                "leerse como una ilustración."
            )

    _require_concrete_anchors(prompt, treatment, article)


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
    payload: dict[str, Any],
    config: dict[str, Any],
    article: ArticleSource | None = None,
) -> VisualPrompt:
    """Construye el prompt visual a partir del JSON del modelo.

    Función pura: no invoca al modelo. Valida el tratamiento declarado, las
    figuras públicas, el prompt positivo y la coherencia entre todos ellos, y
    compone el prompt negativo definitivo y la variante lista para Midjourney.

    Args:
        payload: Objeto JSON devuelto por el modelo.
        config: Configuración de marca cargada desde ``social_config.json``.
        article: Artículo de origen, usado para verificar figuras y anclas. Si
                 se omite, esas comprobaciones no se aplican.

    Returns:
        VisualPrompt: Prompt validado con su tratamiento y sus figuras.

    Raises:
        VisualPromptGenerationError: Si el payload no trae un prompt utilizable,
                                     las figuras públicas no son válidas o el
                                     tratamiento no es coherente.
    """
    visual_config = config.get("visual_prompts", {})
    base_negative = _strip_quotes(str(visual_config.get("negative_prompt", "")))
    midjourney_suffix = str(visual_config.get("midjourney_suffix", "")).strip()
    aspect_ratio = str(visual_config.get("aspect_ratio", "")).strip()

    treatment_negatives = visual_config.get("treatment_negatives", {})
    if not isinstance(treatment_negatives, dict):
        treatment_negatives = {}

    treatment = payload.get("treatment")
    treatment = treatment.strip().lower() if isinstance(treatment, str) else ""

    rationale = payload.get("rationale")
    rationale = _collapse_whitespace(rationale) if isinstance(rationale, str) else ""

    raw_prompt = payload.get("prompt")
    raw_prompt = _collapse_whitespace(raw_prompt) if isinstance(raw_prompt, str) else ""
    if not raw_prompt:
        raise VisualPromptGenerationError(
            "El modelo no entregó un 'prompt' visual utilizable."
        )

    raw_figures = payload.get("political_figures")
    if not isinstance(raw_figures, list):
        raise VisualPromptGenerationError(
            "El modelo no entregó 'political_figures' como lista. Debe ser una "
            "lista de nombres, vacía si la columna no nombra figuras públicas."
        )

    political_figures: list[str] = []
    seen_figures: set[str] = set()
    for item in raw_figures:
        if not isinstance(item, str) or not item.strip():
            raise VisualPromptGenerationError(
                "Cada elemento de 'political_figures' debe ser un nombre no "
                "vacío."
            )
        cleaned = _collapse_whitespace(item)
        key = cleaned.lower()
        if key not in seen_figures:
            seen_figures.add(key)
            political_figures.append(cleaned)

    # Se valida antes de quitar comillas para que la heurística de español
    # pueda excluir los rótulos entrecomillados que sí van en español. El
    # prompt que se publica es el texto plano, sin comillas ni escapes.
    validate_visual_prompt(raw_prompt, treatment, article)
    prompt = _strip_quotes(raw_prompt)
    validate_visual_subjects(political_figures, treatment, prompt, article)

    if not rationale:
        raise VisualPromptGenerationError(
            "El modelo no explicó en 'rationale' por qué eligió el "
            "tratamiento visual."
        )

    extra_negative = payload.get("extra_negative")
    extra_negative = (
        _strip_quotes(extra_negative) if isinstance(extra_negative, str) else ""
    )
    validate_extra_negative(extra_negative, treatment)

    treatment_negative = _strip_quotes(
        str(treatment_negatives.get(treatment, ""))
    )
    negative = _compose_negative_prompt(base_negative, treatment_negative)
    negative = _compose_negative_prompt(negative, extra_negative)

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
        political_figures=political_figures,
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
            return build_visual_prompt(payload, config, article)
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
