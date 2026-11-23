"""Fixtures compartidas por los tests del subsistema de RRSS.

Se cargan aquí porque los distintos módulos del subsistema (parseo, copys,
prompt visual, banners y escritura) comparten el mismo material de origen:
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
def political_article_markdown() -> str:
    """Columna de ejemplo centrada en una figura pública política.

    Returns:
        str: Contenido Markdown del artículo.
    """
    return """\
# Boric y la reforma que se hunde en el Congreso

**Por La Chispa Sur**

---

El presidente Gabriel Boric volvió a La Moneda con una reforma tributaria que \
no logra avanzar en el Congreso. La oposición bloquea el debate mientras las \
cuentas fiscales se deterioran y los municipios de Chile, desde La Araucanía \
hasta Los Lagos, esperan recursos que nunca llegan. La pregunta es si el \
Gobierno insistirá en el acuerdo o dejará caer la reforma.

## La reunión en La Moneda

La ministra de Hacienda reconoció que el Ejecutivo no tiene los votos para \
aprobar el proyecto en el Senado. Según el último informe, el déficit fiscal \
alcanzó el 3,2% del producto y la recaudación cayó un 8% respecto del año \
anterior.

## El Congreso sin mayoría

El oficialismo necesita convencer a los independientes y a una parte de la \
oposición. Boric insistió en que la reforma es indispensable para financiar \
pensiones y salud, pero los senadores piden cambios en el gasto y en la \
administración tributaria.

---

*Artículo generado a partir de la pauta editorial de La Chispa Sur. Las fuentes \
utilizadas se listan a continuación.*

**Fuentes consultadas / sugeridas:**
- La Tercera: cobertura de la tramitación de la reforma tributaria.
- Radio Universidad de Chile: declaraciones desde La Moneda.
"""


@pytest.fixture
def political_article_file(tmp_path: Path, political_article_markdown: str) -> Path:
    """Escribe la columna política de ejemplo en un archivo temporal.

    Returns:
        Path: Ruta al archivo Markdown escrito.
    """
    path = tmp_path / "articulo_2_reforma-tributaria-boric.md"
    path.write_text(political_article_markdown, encoding="utf-8")
    return path


@pytest.fixture
def political_article(political_article_file: Path):
    """Columna política de ejemplo ya parseada.

    Returns:
        ArticleSource: Artículo con figuras públicas y anclas concretas.
    """
    return parse_article_file(political_article_file)


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
            "slides": [
                {
                    "text": (
                        "Un hombre de 44 años fue detenido en Cunco por "
                        "difundir imágenes editadas del ministro de Hacienda."
                    ),
                    "figure": "44 años",
                },
                {
                    "text": (
                        "El delito de amenaza exige anunciar un mal futuro que "
                        "constituya delito y un análisis de proporcionalidad."
                    ),
                    "figure": "",
                },
                {
                    "text": (
                        "El organismo cifra en más de 200 las causas de "
                        "criminalización de la protesta registradas desde 2019."
                    ),
                    "figure": "más de 200",
                },
            ],
        },
    }


@pytest.fixture
def visual_payload() -> dict:
    """Respuesta JSON de ejemplo del modelo para el prompt visual.

    Returns:
        dict: Payload con el tratamiento, su motivo y el prompt en inglés.
    """
    return {
        "treatment": "photorealistic",
        "political_figures": [],
        "rationale": (
            "La columna narra una detención concreta en Cunco, con lugar, "
            "fecha y actuación policial documentables."
        ),
        "prompt": (
            "Documentary photograph of a police van parked on a wet gravel "
            "street in southern Chile at dusk, two investigating officers in "
            "plain clothes walking towards a modest wooden house, a neighbour "
            "watching from a doorway, a hand-painted sign reading CUNCO, 35mm "
            "lens at eye level, natural available light, shallow depth of "
            "field, film grain, reportage palette of crimson red, warm amber "
            "and deep teal, wide composition with generous negative space, "
            "magazine cover quality"
        ),
        "extra_negative": "",
    }


@pytest.fixture
def representative_payload() -> dict:
    """Respuesta JSON de ejemplo con el tratamiento representativo.

    Returns:
        dict: Payload para una columna centrada en una figura pública política.
    """
    return {
        "treatment": "representative",
        "political_figures": ["Gabriel Boric"],
        "rationale": (
            "La columna gira en torno al presidente Gabriel Boric y su reforma "
            "tributaria, así que la imagen debe mostrarlo con un parecido "
            "reconocible dentro de una composición editorial que no pueda "
            "confundirse con una fotografía real."
        ),
        "prompt": (
            "Editorial representative composition, cut-paper collage with "
            "halftone screen print and painted poster panels, the clearly "
            "recognizable likeness of Gabriel Boric at the centre in flat "
            "posterised crimson red and warm amber blocks, bold ink outlines, "
            "a torn-paper facade of La Moneda behind him, a newspaper front "
            "page reading PENSIONES, deep teal background, visible paper "
            "grain, layered graphic panels, poster composition, magazine "
            "cover quality"
        ),
        "extra_negative": "",
    }


@pytest.fixture
def caricature_payload() -> dict:
    """Respuesta JSON de ejemplo con el tratamiento de caricatura.

    Returns:
        dict: Payload con una columna abstracta ilustrada.
    """
    return {
        "treatment": "caricature",
        "political_figures": [],
        "rationale": (
            "La columna es un ensayo sobre la erosión institucional, sin una "
            "escena concreta que pueda fotografiarse."
        ),
        "prompt": (
            "Bold editorial illustration of a colossal cracked marble column "
            "held up by a single matchstick, tiny suited figures pushing from "
            "opposite sides inside a Chilean public building, flat vector "
            "infographics mixed with textured digital painting, saturated "
            "teal and warm amber palette against crimson red, dramatic rim "
            "light, poster composition, magazine cover quality"
        ),
        "extra_negative": "crowds, banners",
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


# ---------------------------------------------------------------------------
# Fixtures del subsistema de tríptico impreso
# ---------------------------------------------------------------------------

# Ruta al archivo de configuración del tríptico versionado en el repositorio.
TRIPTYCH_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "triptych_config.json"
)


@pytest.fixture(scope="session")
def triptych_config() -> dict:
    """Carga la configuración real del tríptico del repositorio.

    Se usa el archivo versionado a propósito: así los tests fallan si alguien
    rompe la estructura de ``triptych_config.json``.

    Returns:
        dict: Configuración del tríptico.
    """
    from news_agent.config import load_triptych_config

    return load_triptych_config(TRIPTYCH_CONFIG_PATH)


@pytest.fixture
def triptych_pauta_markdown() -> str:
    """Pauta de ejemplo con las cinco propuestas que exige el parser.

    Returns:
        str: Contenido Markdown de la pauta.
    """
    lines = [
        "# ⚡ Pauta Editorial Sugerida - La Chispa Sur",
        "**Fecha de Generación:** 2026-09-24  ",
        "**Notas Procesadas:** 12",
        "",
        "---",
        "",
    ]
    for number in range(1, 6):
        lines.extend(
            [
                f"## {number}. Titular de la propuesta {number}",
                (
                    "*   **Enfoque Editorial:** El acuerdo oculta "
                    "compromisos económicos que nadie votó en el Congreso."
                ),
                "*   **Puntos Clave a Desarrollar:**",
                f"    1. Arista uno de la propuesta {number}",
                f"    2. Arista dos de la propuesta {number}",
                "*   **Fuentes Sugeridas para Ampliar:**",
                f"    *   Medio Uno [art. {number}]: cobertura del caso.",
                f"    *   Medio Dos [art. {number + 100}]: contexto adicional.",
                "",
            ]
        )
    return "\n".join(lines)


@pytest.fixture
def triptych_pauta_file(
    tmp_path: Path,
    triptych_pauta_markdown: str,
) -> Path:
    """Escribe la pauta y su companion en un directorio temporal.

    El companion replica la estructura real de ``build_companion_data``: una
    clave ``proposal_N`` por propuesta con su lista de noticias de respaldo.

    Returns:
        Path: Ruta al archivo Markdown de la pauta escrito.
    """
    reports = tmp_path / "reportes"
    reports.mkdir(parents=True, exist_ok=True)

    pauta = reports / "pauta_semanal_2026_09_24.md"
    pauta.write_text(triptych_pauta_markdown, encoding="utf-8")

    companion = {
        f"proposal_{number}": {
            "articles": [
                {
                    "title": f"Noticia de respaldo {number}",
                    "source": "Medio Uno",
                    "link": f"https://example.com/{number}",
                    "summary": "Resumen de la noticia de respaldo.",
                    "content": "Contenido de la noticia de respaldo. " * 60,
                }
            ]
        }
        for number in range(1, 6)
    }
    (reports / "pauta_semanal_2026_09_24_companion.json").write_text(
        json.dumps(companion, ensure_ascii=False), encoding="utf-8"
    )

    return pauta


@pytest.fixture
def triptych_source(triptych_pauta_file: Path):
    """Material de origen del tríptico ya cargado.

    Returns:
        TriptychSource: Propuestas de la pauta con su companion.
    """
    from news_agent.triptych.pauta_source import load_triptych_source

    return load_triptych_source(triptych_pauta_file)


@pytest.fixture
def triptych_payload() -> dict:
    """Respuesta JSON de ejemplo del modelo para el tríptico.

    Está construida para cumplir el contrato completo: portada, cinco notas en
    lenguaje simple, tres datos clave por nota y fuentes del material. Las
    oraciones quedan por debajo del tope de palabras para no ensuciar las
    pruebas de advertencias.

    Returns:
        dict: Payload equivalente al que devolvería el modelo.
    """
    body = (
        "Chile firmó un acuerdo con Estados Unidos. El texto no habla solo de "
        "delincuencia. También trata de inversiones y de litio. Nadie lo votó "
        "en el Congreso. Eso preocupa a los abogados. "
    ) * 3

    return {
        "cover": {
            "hook": "Lo que no te contaron del acuerdo",
            "title": "La letra chica de la semana",
        },
        "notes": [
            {
                "proposal_number": number,
                "title": f"Nota {number}",
                "body": body,
                "key_data": ["Dato uno", "Dato dos", "Dato tres"],
                "why_it_matters": "Te afecta porque el litio es de todos.",
            }
            for number in range(1, 6)
        ],
    }


@pytest.fixture
def triptych_config_file(triptych_config: dict, tmp_path: Path) -> Path:
    """Escribe la configuración del tríptico en un archivo temporal.

    Returns:
        Path: Ruta al archivo JSON escrito.
    """
    path = tmp_path / "triptych_config.json"
    path.write_text(
        json.dumps(triptych_config, ensure_ascii=False), encoding="utf-8"
    )
    return path


@pytest.fixture
def cover_article_markdown() -> str:
    """Artículo de ejemplo para las portadas editoriales.

    Incluye una cifra en el titular (``42 familias``), una cita atribuida y
    el apéndice de propuestas de portada, de modo que las pruebas cubran los
    tres tratamientos y la extracción de la bajada aplicada.

    Returns:
        str: Contenido Markdown del artículo.
    """
    return """\
# Cierre de la escuela rural: 42 familias quedan sin matrícula

**Fecha de creación:** 2026-11-23

**Por La Chispa Sur**

---

*La municipalidad de Villarrica confirmó el cierre de la escuela rural y 42 \
familias quedan sin matrícula para el próximo año.*

El concejo municipal aprobó el cierre con 56 votos a favor y seis en contra. \
La sesión duró cuatro horas y terminó con la sala dividida. "No vamos a \
permitir que nos arranquen la escuela", sostuvo.

## La votación que dejó a 42 familias sin escuela

La comunidad escolar llegó con carteles y pidió una nueva votación. El \
alcalde defendió la medida por el déficit del municipio, mientras las \
familias anunciaron un recurso ante la Contraloría.

## El futuro de las familias

El municipio ofrece traslado a una escuela del sector, pero las familias \
denuncian que el viaje diario supera las dos horas. La matrícula de la \
escuela llegó a 42 estudiantes este año.

---

*Artículo generado a partir de la pauta editorial de La Chispa Sur. Las fuentes \
utilizadas se listan a continuación.*

**Fuentes consultadas / sugeridas:**
- Radio Universidad de Chile: cobertura del cierre de la escuela rural.
- La Tercera: declaraciones del municipio de Villarrica.

## 📰 Propuestas de portada

### 1. Denuncia / tesis política — ✅ aplicada al artículo

**Titular:** Cierre de la escuela rural: 42 familias quedan sin matrícula

**Bajada:** La municipalidad de Villarrica confirmó el cierre de la escuela \
rural y 42 familias quedan sin matrícula para el próximo año.

### 2. Narrativo / humano

**Titular:** La escuela que se queda sin timbre

**Bajada:** Las familias de Villarrica se organizan para frenar el cierre.
"""


@pytest.fixture
def cover_article_file(tmp_path: Path, cover_article_markdown: str) -> Path:
    """Escribe el artículo de portadas en un archivo temporal.

    Returns:
        Path: Ruta al archivo Markdown escrito.
    """
    path = (
        tmp_path
        / "articulos"
        / "articulo_1_2026_11_23_cierre-de-la-escuela-rural.md"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cover_article_markdown, encoding="utf-8")
    return path


@pytest.fixture
def cover_article(cover_article_file: Path):
    """Artículo de portadas ya parseado.

    Returns:
        ArticleSource: Artículo listo para construir el contenido de portada.
    """
    return parse_article_file(cover_article_file)
