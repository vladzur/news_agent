"""Construcción de los prompts del subsistema de RRSS.

Hay dos familias de prompts, con contratos deliberadamente distintos:

- **Copys**: salida en español neutro y JSON estructurado por plataforma. El
  esquema se genera desde la configuración para que el prompt y el validador
  nunca se separen.
- **Prompts visuales**: salida en inglés, pensada para Flux.1, SDXL y
  Midjourney, con ilustración editorial vívida como estilo por defecto y \
  paleta de color obligatoria. La imagen sí puede incluir gráficos y rótulos \
  breves en español que refuercen el mensaje, y las personas reales quedan \
  acotadas a personajes ilustrados de figuras públicas nombradas en el \
  artículo.

Ambas familias separan la identidad editorial (system prompt) de la tarea y el
esquema de salida (user prompt), igual que el resto del agente.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from ..config import SOCIAL_MAX_HOOKS, SOCIAL_MIN_HOOKS
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
You are the editorial illustrator of La Chispa Sur, an independent left-wing \
digital news outlet from southern Chile. You read one article and write the \
English prompt that a designer will paste into Flux.1, SDXL or Midjourney to \
illustrate it.

Describe one bold editorial illustration that captures the central idea of \
the article at a glance: the scene, the objects and the visual metaphor that \
a reader understands without reading the note. Illustrations beat cartoons: \
build a striking image, not a joke.

You may — and usually should — include graphic and typographic elements that \
reinforce the message: big numbers, short labels, banners, price tags, charts, \
arrows, stamps or dotted lines. Any text inside the image must be short (three \
or four words at most), written in Spanish, spelled correctly and quoted in \
the prompt, for example "PENSIONES" or "-10,39%". Never ask for paragraphs, \
fine print or long headlines.

Rules:
1. Write the prompt in English only; the text you request inside the image is \
in Spanish.
2. Illustration, never photography: editorial illustration, digital painting, \
screen print, collage, flat vector or graphic-novel ink. No photorealistic \
images and no deepfakes.
3. People named in the article (president, ministers, senators, mayors) may \
appear as stylised characters or caricatures. Victims, minors and private \
individuals appear as generic anonymous figures.
4. No explicit violence.
5. Always name a saturated colour palette and the technique.
6. Keep one shared concept and palette across every format; in the vertical one, leave the top and bottom clear of essential elements.

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
            '    "hashtags": ["Chile", "LaAraucania"]',
            "  }",
            "}",
            "",
            "Notas sobre el esquema:",
            "- `x.thread[0]` debe ser idéntico a `x.hook_tweet`.",
            ("- Los campos `hashtags` contienen palabras sueltas, sin el "
            "símbolo # y sin espacios internos."),
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
    aspects: dict[str, Any] | None = None,
) -> str:
    """Construye el user prompt para generar los prompts de imagen.

    Args:
        article: Artículo de origen ya parseado.
        copy: Copys ya generados, para alinear el concepto visual con el gancho.
        config: Configuración de marca cargada desde ``social_config.json``.
        aspects: Aspectos a cubrir, indexados por nombre. Si es None, se usan
                 todos los declarados en la configuración.

    Returns:
        str: El prompt de usuario listo para enviar al modelo.
    """
    visual_config = config.get("visual_prompts", {})
    style = str(visual_config.get("style", "")).strip()
    negative = str(visual_config.get("negative_prompt", "")).strip()
    if aspects is None:
        declared = visual_config.get("aspect_ratios", {})
        aspects = declared if isinstance(declared, dict) else {}

    parts: list[str] = [
        "## Task",
        "",
        ("Read the article material and write one English image-generation "
        "prompt per aspect ratio. Describe the illustration you would draw "
        "for this article, then adapt the same visual concept and colour "
        "palette to each frame."),
        "",
        "## Article material",
        "",
        f"**Headline:** {article.title}",
    ]

    if article.lead:
        parts.extend(["", f"**Lead:** {article.lead}"])

    if article.sections:
        parts.extend(["", "**Sections:**"])
        for section in article.sections:
            if section.body:
                parts.append(f"- {section.heading}: {section.body}")

    if article.key_figures:
        parts.extend(["", "**Key figures usable as big numbers in the artwork:**"])
        for figure in article.key_figures:
            parts.append(f"- {figure}")

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

    parts.extend(["", "## Style directive (apply to every prompt)", "", style])

    parts.extend(
        [
            "",
            "## What the illustration must do",
            "",
            ("1. Capture the central idea of the article in one image, using "
            "the people, places, objects and numbers it mentions; a reader "
            "should get it at a glance."),
            ("2. Include graphic and text elements when they reinforce the "
            "message: big numbers, short Spanish labels in double quotes, "
            "banners, charts, arrows or stamps. Keep every label under five "
            "words."),
            ("3. Illustrate, never photograph: editorial illustration, "
            "digital painting, screen print, collage, flat vector or "
            "graphic-novel ink."),
            ("4. Named public figures may appear as stylised characters or "
            "caricatures; victims, minors and private individuals appear as "
            "generic anonymous figures."),
            ("5. Always name a saturated colour palette and the technique, "
            "and keep one shared palette across every prompt."),
        ]
    )

    parts.extend(["", "## Aspect ratios", ""])
    if isinstance(aspects, dict):
        for name, spec in aspects.items():
            if not isinstance(spec, dict):
                continue
            ratio = spec.get("ratio", "")
            target_platforms = spec.get("platforms", [])
            platforms_text = ", ".join(str(item) for item in target_platforms)
            suffix = f" for {platforms_text}" if platforms_text else ""
            parts.append(f"- **{name}** ({ratio}){suffix}")

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
            '  "prompts": [',
            "    {",
            '      "aspect": "landscape",',
            '      "prompt": "English prompt with a named palette and medium",',
            ('      "extra_negative": "Comma-separated artefacts to avoid, '
            'may be an empty string"'),
            "    }",
            "  ]",
            "}",
            "",
            "Notes on the schema:",
            ('- Include exactly one entry per aspect ratio, using the aspect '
            "names listed above."),
            ("- `prompt` must be written in English. Quote any text that "
            'should appear inside the image, in Spanish and no longer than '
            'five words, e.g. "PENSIONES" or "-10,39%".'),
            ("- `prompt` must always name a saturated colour palette and a "
            "medium or technique, and must aim for 50 to 120 words."),
            ("- `extra_negative` adds article-specific artefacts to avoid on "
            "top of the standard negative prompt. Never repeat the standard "
            "negative prompt here."),
            f"- The standard negative prompt already in force is: {negative}",
        ]
    )

    return "\n".join(parts)
