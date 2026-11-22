"""Construcción de los prompts del subsistema de RRSS.

Hay dos familias de prompts, con contratos deliberadamente distintos:

- **Copys**: salida en español neutro y JSON estructurado por plataforma. El
  esquema se genera desde la configuración para que el prompt y el validador
  nunca se separen.
- **Prompts visuales**: salida en inglés, pensada para Midjourney, con dos
  tratamientos posibles —fotorrealista documental o caricatura editorial— y \
  paleta de color obligatoria. El fotorrealismo es el tratamiento por defecto \
  cuando la columna tiene hechos, lugares o escenas concretas; la caricatura \
  queda reservada para columnas abstractas o sin una escena documentable. La \
  imagen puede incluir rótulos breves en español integrados en la escena.

Ambas familias separan la identidad editorial (system prompt) de la tarea y el
esquema de salida (user prompt), igual que el resto del agente.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from ..config import (
    SOCIAL_IG_CAROUSEL_SLIDES,
    SOCIAL_IG_SLIDE_FIGURE_MAX_CHARS,
    SOCIAL_IG_SLIDE_TEXT_MAX_CHARS,
    SOCIAL_MAX_HOOKS,
    SOCIAL_MIN_HOOKS,
)
from .models import ArticleSource, SocialCopy
from .platform_specs import ALL_PLATFORMS, platform_specs, thread_bounds

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt: generación de copys
# ---------------------------------------------------------------------------

SOCIAL_COPY_SYSTEM_PROMPT = """\
Eres el editor de redes sociales de La Chispa Sur, medio digital independiente \
de izquierda, crítico del modelo neoliberal, con foco territorial en Villarrica \
y La Araucanía y mirada antiimperialista desde el sur global.

Tu tarea es adaptar un artículo ya publicado a las redes sociales. No eres un \
resumidor neutral: eres quien decide qué conflicto se destaca, con qué frase se \
detiene el scroll y qué conversación se abre. El tono es incisivo, analítico y \
de lectura ágil.

## Reglas de fidelidad (no negociables)

1. Solo puedes usar información presente en el artículo de origen. No inventes \
cifras, nombres, cargos, fechas, citas ni atribuciones.
2. La cita de `quote_card` debe ser **literal**: cópiala palabra por palabra \
desde el artículo, sin reescribirla ni corregirla. Prioriza las oraciones \
candidatas que se entregan en el material de origen.
3. Toda cifra que incluyas debe existir en el artículo. Si el artículo no tiene \
cifras, deja `key_figures` como lista vacía en lugar de inventar datos.
4. No conviertas hipótesis, preguntas o sospechas del artículo en afirmaciones \
categóricas. Si el artículo dice que algo se investiga, tú también lo dices así.
5. No atribuyas declaraciones a personas que el artículo no menciona.

## Reglas de estilo

1. Español neutro. Prohibido el voseo, los modismos argentinos, el lunfardo y \
las expresiones coloquiales regionales.
2. Frases cortas, voz activa, verbos concretos. Nada de relleno corporativo.
3. Los emojis son opcionales y escasos: máximo tres por copy, nunca \
reemplazando una palabra clave.
4. No uses comillas decorativas alrededor de frases completas ni arrobas \
inventadas.
5. No incluyas hashtags dentro del texto de los tweets, del post ni de la \
caption: van siempre y únicamente en el campo `hashtags` del JSON.
6. No numeres los tweets ni agregues etiquetas como "Hilo:" o "1/7": el texto \
de cada tweet debe ser el contenido final, listo para publicar.

## Reglas por plataforma

### X/Twitter
- El hilo desarrolla el conflicto central del artículo en varios tweets, con \
progresión: gancho, contexto, datos, implicancias y cierre.
- El primer tweet del hilo es el gancho y debe funcionar de forma autónoma.
- Cada tweet debe caber en el límite de caracteres indicado en la tarea, \
contando espacios, signos y emojis.
- `hashtags`: solo palabras, sin el símbolo #, sin espacios dentro de una \
misma etiqueta.

### Facebook
- El post empieza con un gancho de una o dos líneas, porque es lo único que se \
ve antes del "ver más".
- Después desarrolla en párrafos separados por saltos de línea, y cierra con \
una pregunta que invite a comentar.
- Nada de jerga de X: aquí el registro puede ser más explicativo.

### Instagram
- La primera línea es el gancho y debe funcionar sola, antes del "más".
- El cuerpo es breve, con saltos de línea para respirar y máximo un emoji por \
línea.
- Cierra con un llamado a la acción (leer la nota completa, opinar, compartir).
- Los hashtags van separados del texto, como palabras sueltas sin #.
- Además de la caption, la publicación es un **carrusel vertical** de cinco \
piezas: portada, tres slides de resumen y una firma de marca. Los tres slides \
son el corazón de la pieza: quien los lee debe quedar informado de lo esencial \
sin abrir la nota.
- `instagram.slides` trae **exactamente tres** objetos, en orden de lectura. \
Cada slide cubre un punto distinto y complementario: el primero sitúa el \
conflicto, el segundo aporta el dato o el detalle que lo prueba, y el tercero \
explica la consecuencia o lo que está en juego. No repitas el titular de la \
portada ni el mismo argumento con otras palabras.
- Cada slide tiene un solo campo de texto, `text`, **sin titular aparte**. El \
texto es la idea completa y debe entenderse solo, como si fuera la única frase \
de la pantalla. Escríbelo en una o dos oraciones, con máximo 240 caracteres.
- `figure` es opcional: si lo usas, debe ser una cifra o un dato presente en \
el artículo, no una estimación.
- Los slides no llevan emojis, hashtags, comillas decorativas, números de \
slide ni el prefijo "Slide 1".

## Prohibiciones

- No menciones que el texto fue generado por una IA ni que proviene de una pauta.
- No pidas datos personales ni promuevas acciones fuera de la ley.
- No ridiculices a víctimas ni a personas vulnerables mencionadas en el artículo.
- No uses lenguaje que estigmatice a pueblos, comunidades o colectivos.
"""


# ---------------------------------------------------------------------------
# System prompt: generación de prompts visuales
# ---------------------------------------------------------------------------

VISUAL_PROMPT_SYSTEM_PROMPT = """\
You are the picture editor of La Chispa Sur, an independent left-wing \
digital news outlet from southern Chile. You read one column and write the \
single English prompt that a designer pastes into Midjourney to illustrate it.

Decide the treatment first, then write the prompt.

## Treatment

Photorealistic is the default. Choose it when the column reports concrete, \
recognisable facts — a place, an event, an object, a person or a scene — that \
can be shown as one plausible documentary photograph: a street, a courtroom, \
a market, a picket line, a signed document, a public figure at a podium.

Choose caricature — a bold editorial illustration — only when the column is \
abstract: an argument, an economic or institutional trend, a metaphor or a \
critique with no single scene that can be documented. Caricature is never the \
default and never a way to dodge a fact that can be photographed.

## Rules
1. Write the prompt in English only; the text you request inside the image is \
in Spanish.
2. A photorealistic prompt reads like a documentary photograph: subject, \
action, place, light, lens and framing. Never invent an event the column does \
not report; the scene must be plausible and faithful to its facts.
3. In the photorealistic treatment, public figures named in the column appear \
only inside a documentary scene: no deepfake, no invented gesture and no \
invented setting. Victims, minors and private individuals appear unidentified.
4. In the caricature treatment, named public figures may appear as stylised \
characters; victims, minors and private individuals appear as anonymous \
figures.
5. Short in-image text is welcome when it belongs to the scene — signs, \
placards, banners, price tags, screens — and reinforces the message. Keep it \
to three or four words at most, write it in Spanish and in capitals, and never \
use quotation marks or backslashes: write PENSIONES or -10,39%, not \
"-10,39%". The prompt is pasted into Midjourney as plain text, so escaped \
quotes break it. Never ask for paragraphs, fine print or long headlines.
6. Always name a technique and a colour palette: the medium plus palette for \
caricature, the photographic treatment plus palette for photorealistic work.
7. No explicit violence.

Write comma-separated descriptors, never commands such as "generate" or \
"create an image". Aim for 50 to 120 words.
"""


# ---------------------------------------------------------------------------
# Helpers de renderizado
# ---------------------------------------------------------------------------


def _render_article_material(parts: list[str], article: ArticleSource) -> None:
    """Añade el material del artículo al prompt.

    Args:
        parts: Lista de líneas del prompt que se está construyendo.
        article: Artículo de origen ya parseado.
    """
    parts.extend(["", "## Material de origen", ""])
    parts.append(f"**Titular:** {article.title}")
    if article.byline:
        parts.append(f"**Firma:** {article.byline}")
    parts.append(f"**Extensión:** {article.word_count} palabras")

    if article.lead:
        parts.extend(["", "**Lead:**", article.lead])

    if article.sections:
        parts.extend(["", "**Secciones:**"])
        for index, section in enumerate(article.sections, start=1):
            parts.append(f"{index}. {section.heading}")
            if section.body:
                parts.append(f"   {section.body}")

    if article.key_figures:
        parts.extend(["", "**Cifras detectadas en el artículo:**"])
        for figure in article.key_figures:
            parts.append(f"- {figure}")

    if article.quote_candidates:
        parts.extend(
            [
                "",
                ("**Oraciones candidatas para la tarjeta de cita** "
                "(cópialas literalmente si eliges una):"),
            ]
        )
        for candidate in article.quote_candidates:
            parts.append(f"- “{candidate}”")

    if article.sources:
        parts.extend(["", "**Fuentes citadas en el artículo:**"])
        for source in article.sources:
            parts.append(f"- {source}")


def _render_platform_limits(parts: list[str], config: dict[str, Any]) -> None:
    """Añade los límites de cada plataforma al prompt.

    Args:
        parts: Lista de líneas del prompt que se está construyendo.
        config: Configuración de marca cargada desde ``social_config.json``.
    """
    specs = platform_specs(config)
    minimum, maximum = thread_bounds(specs["x"])

    parts.extend(
        [
            "## Límites por plataforma",
            "",
            (f"- **X**: hilo de {minimum} a {maximum} tweets. Cada tweet debe "
            f"caber en {specs['x']['max_chars']} caracteres, incluidos "
            f"espacios, signos y emojis. Máximo "
            f"{specs['x']['max_hashtags']} hashtags."),
            (f"- **Facebook**: post de máximo {specs['facebook']['max_chars']} "
            f"caracteres. Máximo {specs['facebook']['max_hashtags']} hashtags."),
            (f"- **Instagram**: caption de máximo "
            f"{specs['instagram']['caption_max_chars']} caracteres. Máximo "
            f"{specs['instagram']['max_hashtags']} hashtags."),
            ("- **Carrusel de Instagram**: exactamente "
            f"{SOCIAL_IG_CAROUSEL_SLIDES} slides de resumen, sin titular. Cada "
            f"`text` de máximo {SOCIAL_IG_SLIDE_TEXT_MAX_CHARS} caracteres y "
            f"cada `figure` de máximo {SOCIAL_IG_SLIDE_FIGURE_MAX_CHARS} "
            "caracteres."),
            (f"- **hooks**: entre {SOCIAL_MIN_HOOKS} y {SOCIAL_MAX_HOOKS} "
            "variantes, cada una de máximo 120 caracteres."),
            ("- **summary**: entre 3 y 5 bullets de síntesis ejecutiva, cada "
            "uno de máximo 180 caracteres."),
            "- **cta**: máximo 90 caracteres.",
        ]
    )


def _render_copy_schema(parts: list[str]) -> None:
    """Añade el esquema JSON exacto que debe devolver el modelo.

    Args:
        parts: Lista de líneas del prompt que se está construyendo.
    """
    parts.extend(
        [
            "## Formato de salida",
            "",
            ("Responde **únicamente** con un objeto JSON válido, sin texto "
            "explicativo antes ni después y sin bloques de código Markdown."),
            "El objeto debe tener exactamente esta forma:",
            "",
            "{",
            '  "hooks": ["Gancho alternativo 1", "Gancho alternativo 2"],',
            '  "summary": ["Bullet de síntesis 1", "Bullet de síntesis 2"],',
            '  "hook": "Gancho transversal de máximo 200 caracteres",',
            '  "quote_card": {',
            '    "quote": "Cita literal copiada del artículo",',
            '    "attribution": "Atribución breve"',
            "  },",
            '  "key_figures": ["Cifra o dato duro presente en el artículo"],',
            '  "cta": "Llamado a la acción",',
            '  "alt_text": {',
            '    "x": "Descripción visual breve para accesibilidad",',
            '    "facebook": "Descripción visual breve para accesibilidad",',
            '    "instagram": "Descripción visual breve para accesibilidad"',
            "  },",
            '  "x": {',
            '    "hook_tweet": "Primer tweet del hilo",',
            '    "thread": ["Primer tweet del hilo", "Segundo tweet", "..."],',
            '    "hashtags": ["Chile", "LaAraucania"]',
            "  },",
            '  "facebook": {',
            '    "post": "Texto del post, con saltos de línea entre párrafos",',
            '    "hashtags": ["Chile", "LaAraucania"]',
            "  },",
            '  "instagram": {',
            '    "caption": "Texto de la publicación",',
            '    "hashtags": ["Chile", "LaAraucania"],',
            '    "slides": [',
            "      {",
            '        "text": "Idea principal del primer punto, en una o dos oraciones.",',
            '        "figure": "44 años"',
            "      },",
            "      {",
            '        "text": "Idea principal del segundo punto, en una o dos oraciones.",',
            '        "figure": ""',
            "      },",
            "      {",
            '        "text": "Idea principal del tercer punto, en una o dos oraciones.",',
            '        "figure": "más de 200"',
            "      }",
            "    ]",
            "  }",
            "}",
            "",
            "Notas sobre el esquema:",
            "- `x.thread[0]` debe ser idéntico a `x.hook_tweet`.",
            ("- Los campos `hashtags` contienen palabras sueltas, sin el "
            "símbolo # y sin espacios internos."),
            (f"- `instagram.slides` debe traer exactamente "
            f"{SOCIAL_IG_CAROUSEL_SLIDES} objetos, en el orden en que se leerán "
            "en el carrusel. Cada objeto lleva solo `text` y `figure`: no hay "
            "`title` ni `body`."),
            ("- Cada `figure` puede quedar vacío; si se completa, la cifra debe "
            "existir textualmente en el artículo."),
            ("- `alt_text` describe la imagen promocional que acompañará al "
            "copy, pensando en lectores con discapacidad visual."),
            (f"- El JSON debe cubrir las plataformas: "
            f"{', '.join(ALL_PLATFORMS)}."),
        ]
    )


# ---------------------------------------------------------------------------
# API pública: prompts de copys
# ---------------------------------------------------------------------------


def build_copy_system_prompt(config: dict[str, Any] | None = None) -> str:
    """Devuelve el system prompt para generar los copys de redes sociales.

    Args:
        config: Configuración de marca. Se acepta por simetría con el resto de
                builders; la identidad editorial no depende de ella.

    Returns:
        str: El prompt de sistema del editor de redes sociales.
    """
    return SOCIAL_COPY_SYSTEM_PROMPT


def build_copy_user_prompt(
    article: ArticleSource,
    config: dict[str, Any] | None = None,
) -> str:
    """Construye el user prompt para generar los copys de un artículo.

    Args:
        article: Artículo de origen ya parseado.
        config: Configuración de marca cargada desde ``social_config.json``.

    Returns:
        str: El prompt de usuario listo para enviar al modelo.
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    parts: list[str] = [
        f"Fecha: {today_str}",
        "",
        "## Tarea",
        "",
        ("Adapta el siguiente artículo a X, Facebook e Instagram. Genera "
        "primero el ángulo de la pieza (hooks y síntesis) y luego los copys "
        "de cada plataforma, manteniendo coherencia entre todos ellos."),
        "",
    ]

    _render_article_material(parts, article)
    parts.append("")
    _render_platform_limits(parts, config)
    parts.append("")
    _render_copy_schema(parts)

    parts.extend(
        [
            "",
            "## Recordatorio final",
            "",
            ("Verifica antes de responder: cada tweet dentro del límite de "
            "caracteres, la cita copiada literalmente del artículo, las cifras "
            "existentes en el material de origen, y todas las claves del "
            "esquema presentes."),
        ]
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# API pública: prompts visuales
# ---------------------------------------------------------------------------


def build_visual_prompt_system_prompt(config: dict[str, Any] | None = None) -> str:
    """Devuelve el system prompt para generar los prompts visuales.

    Args:
        config: Configuración de marca. Se acepta por simetría con el resto de
                builders.

    Returns:
        str: El prompt de sistema del ingeniero de prompts visuales.
    """
    return VISUAL_PROMPT_SYSTEM_PROMPT


def build_visual_prompt_user_prompt(
    article: ArticleSource,
    copy: SocialCopy,
    config: dict[str, Any],
) -> str:
    """Construye el user prompt para generar el prompt de imagen.

    Args:
        article: Artículo de origen ya parseado.
        copy: Copys ya generados, para alinear el concepto visual con el gancho.
        config: Configuración de marca cargada desde ``social_config.json``.

    Returns:
        str: El prompt de usuario listo para enviar al modelo.
    """
    visual_config = config.get("visual_prompts", {})
    treatments = visual_config.get("treatments", {})
    if not isinstance(treatments, dict):
        treatments = {}
    photorealistic_style = str(treatments.get("photorealistic", "")).strip()
    caricature_style = str(treatments.get("caricature", "")).strip()
    treatment_rules = str(visual_config.get("treatment_rules", "")).strip()
    negative = str(visual_config.get("negative_prompt", "")).strip()
    aspect_ratio = str(visual_config.get("aspect_ratio", "")).strip()

    parts: list[str] = [
        "## Task",
        "",
        ("Read the column and write one English Midjourney prompt that "
        "illustrates it. Decide the treatment first, then describe the "
        "image."),
        "",
        "## Treatment decision",
        "",
        treatment_rules,
        "",
        f"- **photorealistic** — {photorealistic_style}",
        f"- **caricature** — {caricature_style}",
        "",
        "## Column material",
        "",
        f"**Headline:** {article.title}",
    ]

    if article.byline:
        parts.append(f"**Byline:** {article.byline}")

    if article.lead:
        parts.extend(["", f"**Lead:** {article.lead}"])

    if article.sections:
        parts.extend(["", "**Sections:**"])
        for section in article.sections:
            if section.body:
                parts.append(f"- {section.heading}: {section.body}")

    if article.key_figures:
        parts.extend(["", "**Key figures quoted in the column:**"])
        for figure in article.key_figures:
            parts.append(f"- {figure}")

    if article.sources:
        parts.extend(["", "**Sources cited in the column:**"])
        for source in article.sources:
            parts.append(f"- {source}")

    parts.extend(
        [
            "",
            "## Editorial angle already approved for social media",
            "",
            f"**Hook:** {copy.hook}",
        ]
    )
    if copy.quote_card.quote:
        parts.append(f"**Pull quote:** {copy.quote_card.quote}")
    if copy.summary:
        parts.extend(["", "**Synthesis:**"])
        for bullet in copy.summary:
            parts.append(f"- {bullet}")

    parts.extend(
        [
            "",
            "## What the image must do",
            "",
            ("1. Show the central idea of the column in one image, using the "
            "people, places, objects and figures it actually mentions; a "
            "reader should get it at a glance."),
            ("2. Choose photorealistic whenever those facts can be shown as "
            "a plausible documentary photograph; fall back to caricature "
            "only for abstract columns with no documentable scene."),
            ("3. Keep the scene faithful to the column: never turn a "
            "hypothesis, an investigation or a suspicion into a depicted "
            "fact, and never invent an event the column does not report."),
            ("4. Integrate short Spanish text only when it belongs to the "
            'scene —signs, placards, banners, screens or price tags—, in '
            "capitals and under five words, with no quotation marks and no "
            "escaped characters."),
            ("5. Name the technique and a colour palette, and keep the "
            "palette consistent with La Chispa Sur: crimson red, warm amber "
            "and deep teal."),
        ]
    )

    if aspect_ratio:
        parts.append(
            "6. Do not add Midjourney flags: the system appends "
            f"--ar {aspect_ratio} and the version flags."
        )

    parts.extend(
        [
            "",
            "## Output format",
            "",
            ("Respond **only** with a valid JSON object, with no explanatory "
            "text before or after and no Markdown code fences."),
            "The object must have exactly this shape:",
            "",
            "{",
            '  "treatment": "photorealistic",',
            '  "rationale": "Motivo editorial en español",',
            '  "prompt": "English prompt with a named technique and palette",',
            ('  "extra_negative": "Comma-separated artefacts to avoid, '
            'may be an empty string"'),
            "}",
            "",
            "Notes on the schema:",
            ('- `treatment` must be exactly "photorealistic" or '
            '"caricature".'),
            ("- `rationale` explains in Spanish, in one or two sentences, "
            "which concrete facts of the column support a documentary "
            "photograph or which abstract argument forces a caricature."),
            ("- `prompt` must be written in English. Any text that should "
            "appear inside the image goes in Spanish, in capitals and "
            "without quotation marks or backslashes, no longer than five "
            "words, e.g. PENSIONES or -10,39%. The prompt is copied verbatim "
            "into Midjourney, so it must stay plain text."),
            ("- `prompt` must name the technique and a colour palette and "
            "aim for 50 to 120 words."),
            ("- `extra_negative` adds column-specific artefacts to avoid on "
            "top of the standard negative prompt. Never repeat the standard "
            "negative prompt here."),
            f"- The standard negative prompt already in force is: {negative}",
        ]
    )

    return "\n".join(parts)
