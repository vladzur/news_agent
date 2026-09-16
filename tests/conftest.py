"""Fixtures compartidas por los tests del subsistema de RRSS.

Se cargan aquí porque los distintos módulos del subsistema (parseo, copys,
prompts visuales, banners y escritura) comparten el mismo material de origen:
un artículo real ya publicado y la configuración de marca del repositorio.
"""

import json
from pathlib import Path

import pytest

from news_agent.social.article_source import parse_article_file

# Ruta al archivo de configuración de marca versionado en el repositorio
SOCIAL_CONFIG_PATH = Path(__file__).resolve().parent.parent / "social_config.json"


@pytest.fixture(scope="session")
def social_config() -> dict:
    """Carga la configuración de marca real del repositorio.

    Se usa el archivo versionado a propósito: así los tests fallan si alguien
    rompe la estructura de ``social_config.json``.

    Returns:
        dict: Configuración de marca.
    """
    from news_agent.config import load_social_config

    return load_social_config(SOCIAL_CONFIG_PATH)


@pytest.fixture
def article_markdown() -> str:
    """Artículo de ejemplo con la estructura real de ``articulos/*.md``.

    Returns:
        str: Contenido Markdown del artículo.
    """
    return """\
# Disparo simbólico, cárcel real: la criminalización de la disidencia digital

**Por La Chispa Sur**

---

Un hombre de 44 años fue detenido en Cunco, Región de La Araucanía, acusado de \
difundir en redes sociales imágenes editadas del ministro de Hacienda. La \
Brigada de Investigaciones Policiales Especiales ejecutó una orden de captura \
del Juzgado de Garantía de Temuco. La pregunta incómoda es dónde termina la \
amenaza punible y dónde comienza el castigo a la crítica política.

Según reportó Radio Universidad de Chile, la indagatoria comenzó con una \
denuncia ingresada en la plataforma virtual del Ministerio Público. La alerta \
advertía sobre una publicación violenta difundida en un grupo de redes sociales \
llamado “Los Laureles Chile”.

## La captura en Cunco: ¿amenaza grave o intolerancia penalizada?

No se trata de negar la gravedad de una comunicación amenazante contra una \
autoridad pública. El ministro tiene derecho a la protección de su integridad y \
a no ser objeto de hostigamiento. El problema es otro: la imposición de una \
línea punitiva que trata como atentado contra la autoridad hechos que no \
pasaron de una publicación en un grupo privado.

En Chile, el delito de amenaza exige anunciarle a la víctima un mal futuro que \
constituya delito. La aplicación de estos tipos penales a imágenes editadas \
difundidas en redes sociales no es un terreno pacífico: exige un análisis \
riguroso de proporcionalidad.

## Ampliar el delito de opinión

El Instituto Nacional de Derechos Humanos ha documentado de manera sostenida el \
uso del sistema penal frente a expresiones sociales y políticas. Ese organismo \
cifra en más de 200 las causas de criminalización de la protesta registradas \
desde 2019.

---

*Artículo generado a partir de la pauta editorial de La Chispa Sur. Las fuentes \
utilizadas se listan a continuación.*

**Fuentes consultadas / sugeridas:**
- Radio Universidad de Chile: cobertura original de la detención en Cunco.
- Instituto Nacional de Derechos Humanos (INDH): informes sobre criminalización \
de la protesta.
"""


@pytest.fixture
def article_file(tmp_path: Path, article_markdown: str) -> Path:
    """Escribe el artículo de ejemplo en un archivo temporal.

    Returns:
        Path: Ruta al archivo Markdown escrito.
    """
    path = tmp_path / "articulo_1_criminalizacion-de-la-disidencia.md"
    path.write_text(article_markdown, encoding="utf-8")
    return path


@pytest.fixture
def article(article_file: Path):
    """Artículo de ejemplo ya parseado.

    Returns:
        ArticleSource: Artículo listo para alimentar los prompts.
    """
    return parse_article_file(article_file)


@pytest.fixture
def copy_payload() -> dict:
    """Respuesta JSON de ejemplo del modelo para los copys.

    Está construida para cumplir el contrato completo: cita literal del
    artículo, cinco tweets dentro del límite, cifras verificables y hashtags
    sin el símbolo #.

    Returns:
        dict: Payload equivalente al que devolvería el modelo.
    """
    quote = (
        "No se trata de negar la gravedad de una comunicación amenazante "
        "contra una autoridad pública."
    )
    return {
        "hooks": [
            ("Una imagen editada y una orden de captura: la crítica política "
            "entra a tribunales"),
            "Cunco: detenido por difundir un meme contra el ministro",
            ("El delito de opinión se amplía mientras la desinformación "
            "organizada camina impune"),
        ],
        "summary": [
            ("Un hombre de 44 años fue detenido en Cunco por difundir imágenes "
            "editadas del ministro de Hacienda."),
            ("El delito de amenaza exige un mal futuro verosímil y un análisis "
            "riguroso de proporcionalidad."),
            ("El INDH documenta un uso sostenido del sistema penal contra "
            "expresiones políticas."),
        ],
        "hook": (
            "Una imagen editada basta para activar el aparato penal mientras "
            "la desinformación financiada avanza sin sanción"
        ),
        "quote_card": {
            "quote": quote,
            "attribution": "La Chispa Sur",
        },
        "key_figures": ["44 años", "más de 200"],
        "cta": "Lee la investigación completa en lachispasur.cl",
        "alt_text": {
            "x": "Ilustración editorial de un teléfono iluminando una sala vacía",
            "facebook": "Ilustración editorial sobre la criminalización digital",
            "instagram": "Ilustración editorial de la crítica digital",
        },
        "x": {
            "hook_tweet": (
                "Una imagen editada en un grupo de redes sociales bastó para "
                "activar un operativo policial en Cunco."
            ),
            "thread": [
                ("Una imagen editada en un grupo de redes sociales bastó para "
                "activar un operativo policial en Cunco."),
                ("La Brigada de Investigaciones Policiales Especiales detuvo a "
                "un hombre de 44 años acusado de amenazas y atentado contra "
                "la autoridad."),
                ("El delito de amenaza exige un mal futuro verosímil. La "
                "pregunta es si una publicación digital alcanza ese estándar."),
                ("El Instituto Nacional de Derechos Humanos documenta un uso "
                "sostenido del sistema penal contra expresiones políticas."),
                ("¿Cuánta crítica política puede sobrevivir cuando el Estado "
                "responde con órdenes de captura?"),
            ],
            "hashtags": ["Chile", "LaAraucania"],
        },
        "facebook": {
            "post": (
                "Una imagen editada en un grupo de redes sociales bastó para "
                "que la policía detuviera a un hombre en Cunco.\n\n"
                "El delito de amenaza exige un mal futuro verosímil y un "
                "análisis riguroso de proporcionalidad. Vale la pena "
                "preguntarse qué se está protegiendo de verdad.\n\n"
                "¿Dónde termina la amenaza punible y dónde empieza el castigo "
                "a la crítica política?"
            ),
            "hashtags": ["Chile", "LibertadDeExpresion"],
        },
        "instagram": {
            "caption": (
                "Una imagen editada, una orden de captura.\n\n"
                "El caso de Cunco abre una pregunta incómoda sobre los límites "
                "del delito de opinión en la era digital.\n\n"
                "Lee la investigación completa en lachispasur.cl"
            ),
            "hashtags": ["Chile", "DerechosHumanos", "LaAraucania"],
        },
    }


@pytest.fixture
def visual_payload() -> dict:
    """Respuesta JSON de ejemplo del modelo para los prompts visuales.

    Returns:
        dict: Payload con un prompt por aspecto declarado.
    """
    base = (
        "A lone wooden chair standing on a flooded city street at dusk, its "
        "shadow stretching into the water, an enormous concrete wall rising "
        "behind it, cold blue-grey palette with a single ember-red glow on the "
        "horizon, heavy overcast sky, wide composition with generous negative "
        "space, muted desaturated tones, subtle film grain, editorial "
        "conceptual photography style, dramatic chiaroscuro lighting"
    )
    return {
        "prompts": [
            {"aspect": "landscape", "prompt": base, "extra_negative": ""},
            {
                "aspect": "square",
                "prompt": base.replace("wide composition", "centred square composition"),
                "extra_negative": "crowds, banners",
            },
            {
                "aspect": "portrait",
                "prompt": base.replace("wide composition", "vertical composition"),
                "extra_negative": "",
            },
        ]
    }


@pytest.fixture
def social_copy(article, social_config, copy_payload):
    """Copys ya validados a partir del payload de ejemplo.

    Returns:
        SocialCopy: Copys listos para renderizar banners y escribir el bundle.
    """
    from news_agent.social.copy_generator import build_social_copy

    return build_social_copy(copy_payload, article, social_config)


@pytest.fixture
def config_file(social_config: dict, tmp_path: Path) -> Path:
    """Escribe la configuración de marca en un archivo temporal.

    Returns:
        Path: Ruta al archivo JSON escrito.
    """
    path = tmp_path / "social_config.json"
    path.write_text(
        json.dumps(social_config, ensure_ascii=False), encoding="utf-8"
    )
    return path
