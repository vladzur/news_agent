"""Módulo de configuración del agente de noticias.

Carga la configuración desde variables de entorno y archivos JSON externos.
También carga automáticamente un archivo .env del directorio del proyecto.
"""

import json
import logging
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de configuración del modelo DeepSeek
# ---------------------------------------------------------------------------
DEEPSEEK_MODEL = "deepseek-flash"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
TEMPERATURE = 0.1
# Pauta semanal: las cinco propuestas extensas y el razonamiento sobre cientos
# de noticias comparten este presupuesto de salida. Se amplió a 64K (muy por
# debajo del tope de 384K de salida del modelo) porque con 16K el razonamiento
# agotaba el cupo y la pauta quedaba truncada.
PAUTA_MAX_TOKENS = 65536
# Artículo ~1000 palabras en español (~2500 tokens) + razonamiento. El
# presupuesto es COMPARTIDO entre el razonamiento y el contenido final, así que
# debe dejar margen para ambos: con 8192, el razonamiento de un artículo
# complejo podía agotarlo y la respuesta llegaba sin contenido visible.
ARTICLE_MAX_TOKENS = 16384
# Presupuesto del reintento cuando la respuesta llega sin contenido visible.
# El reintento desactiva el razonamiento, por lo que todos estos tokens se
# destinan al texto final.
CONTENT_RETRY_MAX_TOKENS = 8192
# Razonamiento de la pauta: se mantiene "high" para preservar la profundidad
# del análisis. El truncamiento se evita con el presupuesto ampliado de
# PAUTA_MAX_TOKENS y con la detección de finish_reason en LLMClient.
# Opciones: "high", "medium", "max", o None para deshabilitar thinking mode.
PAUTA_REASONING_EFFORT = "high"
ARTICLE_REASONING_EFFORT = "high"  # Razonamiento para redacción de artículos individuales

# ---------------------------------------------------------------------------
# Constantes de la ventana de análisis y formato
# ---------------------------------------------------------------------------
TIME_WINDOW_HOURS = 96  # 4 días: noticias anteriores ya tienen desarrollos posteriores en la ventana
SUMMARY_MAX_CHARS = 500  # Suficiente para lead + cifras + atribuciones (reglas de precisión factual)

# ---------------------------------------------------------------------------
# Constantes de la pauta editorial
# ---------------------------------------------------------------------------
NUM_PROPOSALS = 5  # Propuestas por pauta: 3 nacionales + 2 internacionales

# ---------------------------------------------------------------------------
# Constantes de enriquecimiento de contenido
# ---------------------------------------------------------------------------
FULL_CONTENT_FETCH_ENABLED = True  # Control global de enriquecimiento
MIN_SUMMARY_LENGTH = 150  # Si el resumen RSS < esto, intentar extraer contenido completo
FULL_CONTENT_TIMEOUT = 15  # Timeout HTTP para cada extracción de artículo (segundos)
FULL_CONTENT_DELAY = 1.0  # Pausa entre peticiones al mismo dominio (segundos)
FULL_CONTENT_MAX_WORKERS = 4  # Hilos paralelos para extracción de contenido
FULL_CONTENT_CACHE_DIR = str(Path(__file__).resolve().parent.parent / "cache")  # Ruta absoluta al dir de caché

# ---------------------------------------------------------------------------
# Constantes de referencias a fuentes para escritura de artículos
# ---------------------------------------------------------------------------
# Máximo de caracteres de contenido fuente por artículo que se incluyen
# en el prompt del redactor, para no saturar la ventana de contexto del LLM.
SOURCE_ARTICLE_MAX_CHARS = 2000

# Máximo de artículos del mismo medio que se incluyen en el companion JSON
# de fuentes. Controla el volumen de material de origen que recibe el redactor.
COMPANION_MAX_ARTICLES_PER_SOURCE = 3

# ---------------------------------------------------------------------------
# Constantes del subsistema de repurposing para redes sociales (RRSS)
# ---------------------------------------------------------------------------
# Presupuesto y razonamiento del LLM para generar copys y prompts visuales.
# Se usan dos llamadas independientes: una para copys y otra para prompts.
SOCIAL_MAX_TOKENS = 8192
SOCIAL_REASONING_EFFORT = "high"
# Temperatura más alta que la pauta: el copy es creativo, pero debe seguir
# siendo fiel a los hechos del artículo de origen.
SOCIAL_TEMPERATURE = 0.4
# Presupuesto propio para la generación de prompts visuales en inglés.
SOCIAL_VISUAL_MAX_TOKENS = 4096
SOCIAL_VISUAL_REASONING_EFFORT = "high"
# Reintentos de la llamada al LLM cuando la respuesta no es JSON válido.
SOCIAL_JSON_MAX_RETRIES = 2

# Directorio de salida por defecto de los bundles de RRSS y archivo de
# configuración de marca/plantillas.
DEFAULT_SOCIAL_OUTPUT_DIR = "social"
SOCIAL_CONFIG_PATH = "social_config.json"

# Límites de plataforma. El límite de caracteres de X se verifica de forma
# determinista sobre el texto final (incluyendo hashtags y emojis).
SOCIAL_X_MAX_CHARS = 280
SOCIAL_X_THREAD_MIN_TWEETS = 5
SOCIAL_X_THREAD_MAX_TWEETS = 7
SOCIAL_X_MAX_HASHTAGS = 4
SOCIAL_FACEBOOK_POST_MAX_CHARS = 1200
SOCIAL_FACEBOOK_MAX_HASHTAGS = 5
SOCIAL_IG_CAPTION_MAX_CHARS = 2200
SOCIAL_IG_MAX_HASHTAGS = 25

# Cantidad de hooks alternativos y de bullets de síntesis ejecutiva.
SOCIAL_MIN_HOOKS = 3
SOCIAL_MAX_HOOKS = 5
SOCIAL_MIN_SUMMARY_BULLETS = 3
SOCIAL_MAX_SUMMARY_BULLETS = 5

# Guardia de entrada: por debajo de este largo el artículo no tiene material
# suficiente para derivar copys y banners con sentido.
SOCIAL_MIN_ARTICLE_WORDS = 150

# Ancho de referencia del diseño de banners. Cada plantilla se dibuja sobre
# esta base y luego se escala proporcionalmente al tamaño pedido, de modo que
# una sola implementación sirve para los cuatro formatos de plataforma.
SOCIAL_BANNER_BASE_WIDTH = 1080

# Rutas candidatas para resolver las fuentes tipográficas de los banners.
# Se recorren en orden y se usa la primera que exista. Si ninguna existe, se
# cae a la fuente por defecto de Pillow (con advertencia en el log). El
# directorio se puede sobrescribir con la variable de entorno SOCIAL_FONT_DIR.
SOCIAL_FONT_BOLD_CANDIDATES = (
    # DejaVu (Debian/Ubuntu, Fedora)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    # Liberation (RHEL/CentOS, algunas Debian)
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    # Noto
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    # Arch Linux y derivados
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)

SOCIAL_FONT_REGULAR_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)

# ---------------------------------------------------------------------------
# Constantes del subsistema de tríptico impreso
# ---------------------------------------------------------------------------
# El tríptico condensa la pauta completa (cinco propuestas) en una hoja oficio
# doblada en tres: cinco mini-notas, una por propuesta, más un panel de
# portada. Cada nota se mide contra el tope de una columna y media y, si se
# pasa, solo se advierte: el texto nunca se recorta de forma automática porque
# un recorte mutila la redacción.
TRIPTYCH_MAX_TOKENS = 8192
TRIPTYCH_REASONING_EFFORT = "high"
# Más baja que la del copy de RRSS: el texto impreso debe ser sobrio y fiel a
# la pauta, no ingenioso.
TRIPTYCH_TEMPERATURE = 0.3
# Reintentos cuando la respuesta del modelo no trae un objeto JSON válido.
TRIPTYCH_JSON_MAX_RETRIES = 2
# Bajo este largo la nota no tiene material suficiente para publicarse: es un
# error estructural y no una advertencia de estilo.
TRIPTYCH_NOTE_MIN_CHARS = 250

# Geometría por defecto: hoja oficio (21,59 x 33,02 cm) con margen de 15 mm.
TRIPTYCH_PAGE_WIDTH_MM = 215.9
TRIPTYCH_PAGE_HEIGHT_MM = 330.2
TRIPTYCH_MARGIN_MM = 15.0
TRIPTYCH_COLUMNS_PER_SIDE = 3
TRIPTYCH_SIDES = 2
TRIPTYCH_FOLD_TYPES = ("roll", "gate", "z")
TRIPTYCH_DEFAULT_FOLD = "roll"

# Tipografía: monospace de 12 pt. El avance de carácter se expresa en emes
# (DejaVu Sans Mono avanza 0,6025 em) porque es lo que convierte los puntos en
# ancho y permite derivar cuántos caracteres entran en cada columna.
TRIPTYCH_FONT_FAMILY = "monospace"
TRIPTYCH_FONT_SIZE_PT = 12.0
TRIPTYCH_CHAR_WIDTH_EM = 0.6025
TRIPTYCH_LINE_HEIGHT_RATIO = 1.2

# Tope de largo de cada nota y objetivo de redacción que se le pide al modelo.
TRIPTYCH_BLOCK_MAX_COLUMNS = 1.5
TRIPTYCH_BODY_TARGET_CHARS = 700
TRIPTYCH_KEY_DATA_ITEMS = 3
TRIPTYCH_MAX_WORDS_PER_SENTENCE = 15

# Directorio de salida y archivo de configuración del tríptico impreso.
DEFAULT_PRINT_OUTPUT_DIR = "impresos"
TRIPTYCH_CONFIG_PATH = "triptych_config.json"

# ---------------------------------------------------------------------------
# Directorios de salida por defecto del CLI por subcomandos
# ---------------------------------------------------------------------------
# El CLI de subcomandos (report/article/social/all/clean) usa estos
# directorios cuando no se indica --output. Coinciden con la estructura
# versionada del repositorio para que una ejecución sin argumentos escriba
# siempre en el mismo lugar.
DEFAULT_REPORTS_DIR = "reportes"
DEFAULT_ARTICLES_DIR = "articulos"

# Antigüedad máxima por defecto (en días) de los artefactos que elimina el
# subcomando ``clean``. La caché de contenido y los assets de la marca nunca
# se eliminan: el comando solo considera los patrones declarados en
# ``news_agent.cleanup.CLEAN_PATTERNS``.
DEFAULT_CLEAN_MAX_AGE_DAYS = 30

# ---------------------------------------------------------------------------
# Archivo de configuración de feeds RSS (por defecto)
# ---------------------------------------------------------------------------
DEFAULT_FEEDS_PATH = "rss_feeds.json"


class ConfigurationError(Exception):
    """Excepción personalizada para errores de configuración del agente."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def _find_dotenv() -> Path | None:
    """Busca el archivo .env en el directorio del proyecto.

    Recorre hacia arriba desde el directorio actual hasta encontrar un .env
    o llegar a la raíz del sistema de archivos.

    Returns:
        Path | None: Ruta al archivo .env, o None si no se encuentra.
    """
    current = Path.cwd()
    # También buscar en el directorio del paquete
    candidates = [
        current / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def _load_dotenv() -> None:
    """Carga variables de entorno desde un archivo .env si existe.

    Solo carga variables que aún no estén definidas en el entorno,
    respetando así cualquier valor ya establecido explícitamente.

    El formato esperado es KEY=VALUE por línea, con soporte para
    líneas en blanco y comentarios con #.
    """
    dotenv_path = _find_dotenv()
    if dotenv_path is None:
        return

    with open(dotenv_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            # Ignorar líneas vacías y comentarios
            if not line or line.startswith("#"):
                continue
            # Parsear KEY=VALUE
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Eliminar comillas alrededor del valor si las tiene
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            # Solo establecer si la variable no existe ya en el entorno
            if key and key not in os.environ:
                os.environ[key] = value


# Cargar .env automáticamente al importar el módulo
_load_dotenv()


def get_api_key() -> str:
    """Obtiene la clave API de DeepSeek desde la variable de entorno.

    Busca en el entorno (incluyendo variables cargadas desde .env).

    Returns:
        str: La clave API.

    Raises:
        ConfigurationError: Si la variable DEEPSEEK_API_KEY no está definida.
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ConfigurationError(
            "Variable de entorno DEEPSEEK_API_KEY no encontrada. "
            "Define tu clave API en el archivo .env o expórtala "
            "como variable de entorno antes de ejecutar el agente."
        )
    return api_key


def load_rss_feeds(path: str | Path | None = None) -> list[dict]:
    """Carga la matriz de canales RSS desde un archivo JSON.

    Args:
        path: Ruta al archivo JSON de configuración de feeds.
              Si es None, se usa DEFAULT_FEEDS_PATH.

    Returns:
        list[dict]: Lista de diccionarios con las claves 'name' y 'url'.

    Raises:
        ConfigurationError: Si el archivo no existe, no es JSON válido,
                            o no contiene una lista.
    """
    file_path = Path(path) if path else Path(DEFAULT_FEEDS_PATH)

    if not file_path.exists():
        raise ConfigurationError(
            f"Archivo de configuración de feeds no encontrado: {file_path.resolve()}"
        )

    try:
        with open(file_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"El archivo {file_path.resolve()} no contiene JSON válido: {exc}"
        ) from exc

    if not isinstance(data, list):
        raise ConfigurationError(
            f"Se esperaba una lista de feeds en {file_path.resolve()}, "
            f"pero se encontró {type(data).__name__}."
        )

    # Validar que cada entrada tenga los campos requeridos
    _validate_feed_entries(data)

    return data


def _validate_scraping_feed(feed: dict) -> None:
    """Valida la configuración de un feed que usa scraping web.

    Args:
        feed: Entrada de feed con ``method`` igual a "scraping".

    Raises:
        ConfigurationError: Si faltan los selectores obligatorios.
    """
    name = feed["name"]

    if "selectors" not in feed:
        raise ConfigurationError(
            f"Feed '{name}' usa method='scraping' pero "
            "no tiene el campo obligatorio 'selectors'."
        )

    selectors = feed["selectors"]
    if not isinstance(selectors, dict):
        raise ConfigurationError(
            f"Feed '{name}': 'selectors' debe ser un diccionario."
        )

    for required in ("article", "title"):
        if required not in selectors:
            raise ConfigurationError(
                f"Feed '{name}' usa method='scraping': "
                f"selectors requiere al menos la clave '{required}'."
            )


def _validate_feed_entries(data: list) -> None:
    """Valida cada entrada de la matriz de feeds.

    Args:
        data: Contenido del archivo de feeds.

    Raises:
        ConfigurationError: Si una entrada no es un diccionario, le faltan los
                            campos obligatorios, o declara un scraping sin los
                            selectores necesarios.
    """
    for idx, feed in enumerate(data):
        if not isinstance(feed, dict):
            raise ConfigurationError(
                f"Entrada de feed #{idx} no es un diccionario: {feed}"
            )

        for required in ("name", "url"):
            if required not in feed:
                raise ConfigurationError(
                    f"Entrada de feed #{idx} no tiene el campo obligatorio "
                    f"'{required}'."
                )

        method = feed.get("method", "rss")
        if method == "scraping":
            _validate_scraping_feed(feed)
        elif method != "rss":
            # Método desconocido: advertir pero no fallar (compatibilidad futura)
            logger.warning(
                "Feed '%s' tiene method='%s' (desconocido). "
                "Se tratará como RSS por defecto.",
                feed["name"],
                method,
            )


def _read_social_config_file(file_path: Path) -> dict:
    """Lee el archivo JSON de configuración de RRSS.

    Args:
        file_path: Ruta al archivo JSON.

    Returns:
        dict: Contenido del archivo.

    Raises:
        ConfigurationError: Si el archivo no existe, no es JSON válido o no
                            contiene un objeto.
    """
    if not file_path.exists():
        raise ConfigurationError(
            f"Archivo de configuración de RRSS no encontrado: "
            f"{file_path.resolve()}"
        )

    try:
        with open(file_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"El archivo {file_path.resolve()} no contiene JSON válido: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigurationError(
            f"Se esperaba un objeto JSON en {file_path.resolve()}, "
            f"pero se encontró {type(data).__name__}."
        )

    return data


def _validate_social_sections(data: dict) -> None:
    """Valida que estén las secciones obligatorias de la configuración RRSS.

    Args:
        data: Contenido del archivo de configuración.

    Raises:
        ConfigurationError: Si falta una sección o no es un objeto JSON.
    """
    for section in ("brand", "banners", "visual_prompts"):
        if section not in data:
            raise ConfigurationError(
                f"La configuración de RRSS no tiene la sección obligatoria "
                f"'{section}'."
            )
        if not isinstance(data[section], dict):
            raise ConfigurationError(
                f"La sección '{section}' de la configuración de RRSS debe ser "
                f"un objeto JSON, pero es {type(data[section]).__name__}."
            )


def _validate_brand_section(brand: dict) -> None:
    """Valida que la sección de marca tenga lo mínimo para dibujar banners.

    Args:
        brand: Sección 'brand' de la configuración.

    Raises:
        ConfigurationError: Si falta el nombre o la paleta de colores.
    """
    if "name" not in brand:
        raise ConfigurationError(
            "La sección 'brand' de la configuración de RRSS requiere 'name'."
        )

    colors = brand.get("colors")
    if not isinstance(colors, dict) or not colors:
        raise ConfigurationError(
            "La sección 'brand' de la configuración de RRSS requiere "
            "'colors' como objeto no vacío."
        )


def _validate_banner_sizes(sizes: dict) -> None:
    """Valida que cada formato declare un par [ancho, alto] válido.

    Args:
        sizes: Mapa formato → [ancho, alto].

    Raises:
        ConfigurationError: Si algún tamaño no son dos enteros positivos.
    """
    for name, size in sizes.items():
        if (
            not isinstance(size, (list, tuple))
            or len(size) != 2
            or not all(isinstance(value, int) and value > 0 for value in size)
        ):
            raise ConfigurationError(
                f"El tamaño '{name}' de la configuración de RRSS debe ser una "
                f"lista [ancho, alto] de enteros positivos, pero es {size!r}."
            )


def _validate_banner_templates(templates: dict, sizes: dict) -> None:
    """Valida que cada plantilla apunte a formatos declarados.

    Args:
        templates: Mapa plantilla → lista de formatos.
        sizes: Mapa formato → [ancho, alto].

    Raises:
        ConfigurationError: Si una plantilla no declara formatos o apunta a
                            un formato inexistente.
    """
    for template_name, targets in templates.items():
        if not isinstance(targets, (list, tuple)) or not targets:
            raise ConfigurationError(
                f"La plantilla '{template_name}' debe declarar una lista de "
                f"formatos de plataforma, pero es {targets!r}."
            )
        for target in targets:
            if target not in sizes:
                raise ConfigurationError(
                    f"La plantilla '{template_name}' apunta al formato "
                    f"'{target}', que no está declarado en 'sizes'."
                )


def _validate_banners_section(banners: dict) -> None:
    """Valida la sección de banners de la configuración RRSS.

    Args:
        banners: Sección 'banners' de la configuración.

    Raises:
        ConfigurationError: Si faltan las plantillas o los tamaños, o si la
                            matriz plantilla/formato es inconsistente.
    """
    templates = banners.get("templates")
    sizes = banners.get("sizes")

    if not isinstance(templates, dict) or not templates:
        raise ConfigurationError(
            "La sección 'banners' requiere 'templates' como objeto no vacío "
            "(nombre de plantilla → lista de formatos de plataforma)."
        )
    if not isinstance(sizes, dict) or not sizes:
        raise ConfigurationError(
            "La sección 'banners' requiere 'sizes' como objeto no vacío "
            "(formato de plataforma → [ancho, alto])."
        )

    _validate_banner_sizes(sizes)
    _validate_banner_templates(templates, sizes)


def load_social_config(path: str | Path | None = None) -> dict:
    """Carga la configuración de marca y plantillas del subsistema RRSS.

    El archivo define la identidad visual (colores, tipografías, logo),
    los límites de cada plataforma y la matriz de plantillas de banner.
    Mantenerlo en JSON permite ajustar la marca sin tocar código, del mismo
    modo que ``rss_feeds.json`` desacopla las fuentes de noticias.

    Args:
        path: Ruta al archivo JSON. Si es None, se usa SOCIAL_CONFIG_PATH.

    Returns:
        dict: Configuración completa con las claves 'brand', 'platforms',
              'banners' y 'visual_prompts'.

    Raises:
        ConfigurationError: Si el archivo no existe, no es JSON válido, o no
                            tiene la estructura mínima requerida.
    """
    file_path = Path(path) if path else Path(SOCIAL_CONFIG_PATH)
    data = _read_social_config_file(file_path)

    _validate_social_sections(data)
    _validate_brand_section(data["brand"])
    _validate_banners_section(data["banners"])

    return data


def _read_triptych_config_file(file_path: Path) -> dict:
    """Lee el archivo JSON de configuración del tríptico impreso.

    Args:
        file_path: Ruta al archivo JSON.

    Returns:
        dict: Contenido del archivo.

    Raises:
        ConfigurationError: Si el archivo no existe, no es JSON válido o no
                            contiene un objeto.
    """
    if not file_path.exists():
        raise ConfigurationError(
            f"Archivo de configuración del tríptico no encontrado: "
            f"{file_path.resolve()}"
        )

    try:
        with open(file_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"El archivo {file_path.resolve()} no contiene JSON válido: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigurationError(
            f"Se esperaba un objeto JSON en {file_path.resolve()}, "
            f"pero se encontró {type(data).__name__}."
        )

    return data


def _is_number(value: object) -> bool:
    """Comprueba que el valor sea un número, excluyendo los booleanos.

    Args:
        value: Valor a comprobar.

    Returns:
        bool: True si es un entero o un decimal real.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_positive_number(section: str, field: str, value: object) -> None:
    """Exige que un campo de configuración sea un número mayor que cero.

    Args:
        section: Nombre de la sección, para el mensaje de error.
        field: Nombre del campo, para el mensaje de error.
        value: Valor declarado.

    Raises:
        ConfigurationError: Si el valor no es un número positivo.
    """
    if not _is_number(value) or value <= 0:
        raise ConfigurationError(
            f"El campo '{field}' de la sección '{section}' del tríptico debe "
            f"ser un número mayor que cero, pero es {value!r}."
        )


def _require_positive_int(section: str, field: str, value: object) -> None:
    """Exige que un campo de configuración sea un entero mayor que cero.

    Args:
        section: Nombre de la sección, para el mensaje de error.
        field: Nombre del campo, para el mensaje de error.
        value: Valor declarado.

    Raises:
        ConfigurationError: Si el valor no es un entero positivo.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(
            f"El campo '{field}' de la sección '{section}' del tríptico debe "
            f"ser un entero mayor que cero, pero es {value!r}."
        )


def _validate_triptych_sections(data: dict) -> None:
    """Valida que estén las secciones obligatorias del tríptico.

    Args:
        data: Contenido del archivo de configuración.

    Raises:
        ConfigurationError: Si falta una sección o no es un objeto JSON.
    """
    for section in ("page", "typography", "limits", "style", "layout"):
        if section not in data:
            raise ConfigurationError(
                "La configuración del tríptico no tiene la sección "
                f"obligatoria '{section}'."
            )
        if not isinstance(data[section], dict):
            raise ConfigurationError(
                f"La sección '{section}' de la configuración del tríptico "
                f"debe ser un objeto JSON, pero es "
                f"{type(data[section]).__name__}."
            )


def _validate_triptych_page(page: dict) -> None:
    """Valida la sección 'page': geometría y pliegue de la hoja.

    Args:
        page: Sección 'page' de la configuración.

    Raises:
        ConfigurationError: Si falta una medida, el margen deja la hoja sin
                            área útil, o el pliegue es desconocido.
    """
    for field in ("width_mm", "height_mm", "margin_mm"):
        if field not in page:
            raise ConfigurationError(
                f"La sección 'page' del tríptico requiere el campo '{field}'."
            )
        _require_positive_number("page", field, page[field])

    if "columns_per_side" not in page:
        raise ConfigurationError(
            "La sección 'page' del tríptico requiere el campo "
            "'columns_per_side'."
        )
    _require_positive_int("page", "columns_per_side", page["columns_per_side"])

    sides = page.get("sides", TRIPTYCH_SIDES)
    if sides not in (1, 2):
        raise ConfigurationError(
            "El campo 'sides' de la sección 'page' del tríptico debe ser 1 o "
            f"2, pero es {sides!r}."
        )

    fold = page.get("fold", TRIPTYCH_DEFAULT_FOLD)
    if fold not in TRIPTYCH_FOLD_TYPES:
        raise ConfigurationError(
            "El campo 'fold' de la sección 'page' del tríptico debe ser uno "
            f"de {', '.join(TRIPTYCH_FOLD_TYPES)}, pero es {fold!r}."
        )

    # Un margen que se come la hoja haría imposible maquetar texto: se detecta
    # al cargar en lugar de producir un presupuesto de cero caracteres.
    usable_width = page["width_mm"] - 2 * page["margin_mm"]
    if usable_width <= 0:
        raise ConfigurationError(
            "El margen de la sección 'page' del tríptico es demasiado "
            f"grande: deja {usable_width:.1f} mm de ancho útil."
        )

    usable_height = page["height_mm"] - 2 * page["margin_mm"]
    if usable_height <= 0:
        raise ConfigurationError(
            "El margen de la sección 'page' del tríptico es demasiado "
            f"grande: deja {usable_height:.1f} mm de alto útil."
        )


def _validate_triptych_typography(typography: dict) -> None:
    """Valida la sección 'typography': familia y medidas del texto.

    Args:
        typography: Sección 'typography' de la configuración.

    Raises:
        ConfigurationError: Si falta un campo o su valor no es utilizable.
    """
    family = typography.get("family")
    if not isinstance(family, str) or not family.strip():
        raise ConfigurationError(
            "El campo 'family' de la sección 'typography' del tríptico debe "
            f"ser un texto no vacío, pero es {family!r}."
        )

    for field in ("size_pt", "char_width_em", "line_height_ratio"):
        if field not in typography:
            raise ConfigurationError(
                "La sección 'typography' del tríptico requiere el campo "
                f"'{field}'."
            )
        _require_positive_number("typography", field, typography[field])


def _validate_triptych_limits(limits: dict) -> None:
    """Valida la sección 'limits': topes de largo de cada nota.

    Args:
        limits: Sección 'limits' de la configuración.

    Raises:
        ConfigurationError: Si falta un campo o su valor no es utilizable.
    """
    if "block_max_columns" not in limits:
        raise ConfigurationError(
            "La sección 'limits' del tríptico requiere el campo "
            "'block_max_columns'."
        )
    if "body_target_chars" not in limits:
        raise ConfigurationError(
            "La sección 'limits' del tríptico requiere el campo "
            "'body_target_chars'."
        )

    _require_positive_number(
        "limits", "block_max_columns", limits["block_max_columns"]
    )
    _require_positive_int("limits", "body_target_chars", limits["body_target_chars"])


def _validate_triptych_style(style: dict) -> None:
    """Valida la sección 'style': reglas de lenguaje simple.

    Args:
        style: Sección 'style' de la configuración.

    Raises:
        ConfigurationError: Si falta un campo o su valor no es utilizable.
    """
    if "max_words_per_sentence" not in style:
        raise ConfigurationError(
            "La sección 'style' del tríptico requiere el campo "
            "'max_words_per_sentence'."
        )
    _require_positive_int(
        "style", "max_words_per_sentence", style["max_words_per_sentence"]
    )

    for field in ("acronym_allowlist", "forbidden_terms"):
        value = style.get(field, [])
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise ConfigurationError(
                f"El campo '{field}' de la sección 'style' del tríptico debe "
                f"ser una lista de textos, pero es {value!r}."
            )


def _validate_triptych_layout(layout: dict) -> None:
    """Valida la sección 'layout': paneles y bloques de cada nota.

    Args:
        layout: Sección 'layout' de la configuración.

    Raises:
        ConfigurationError: Si falta un campo o su valor no es utilizable.
    """
    for field in ("notes", "key_data_items"):
        if field not in layout:
            raise ConfigurationError(
                f"La sección 'layout' del tríptico requiere el campo '{field}'."
            )
        _require_positive_int("layout", field, layout[field])


def load_triptych_config(path: str | Path | None = None) -> dict:
    """Carga la configuración del tríptico impreso.

    El archivo declara la geometría de la hoja (oficio), la tipografía
    monospace, los topes de largo y las reglas de lenguaje simple. Mantenerlo
    en JSON permite ajustar la medida del papel o el tope de columnas sin
    tocar código, del mismo modo que ``social_config.json`` desacopla la
    identidad visual del subsistema de RRSS.

    Args:
        path: Ruta al archivo JSON. Si es None, se usa TRIPTYCH_CONFIG_PATH.

    Returns:
        dict: Configuración completa con las claves 'page', 'typography',
              'limits', 'style', 'layout' y, opcionalmente, 'brand'.

    Raises:
        ConfigurationError: Si el archivo no existe, no es JSON válido, o no
                            tiene la estructura mínima requerida.
    """
    file_path = Path(path) if path else Path(TRIPTYCH_CONFIG_PATH)
    data = _read_triptych_config_file(file_path)

    _validate_triptych_sections(data)
    _validate_triptych_page(data["page"])
    _validate_triptych_typography(data["typography"])
    _validate_triptych_limits(data["limits"])
    _validate_triptych_style(data["style"])
    _validate_triptych_layout(data["layout"])

    brand = data.get("brand")
    if brand is not None and not isinstance(brand, dict):
        raise ConfigurationError(
            "La sección 'brand' de la configuración del tríptico debe ser un "
            f"objeto JSON, pero es {type(brand).__name__}."
        )

    return data


def get_main_topics() -> list[str]:
    """Obtiene la lista de temas de interés prioritarios para la pauta.

    Lee la variable de entorno MAIN_TOPICS, que debe contener un array JSON
    de textos (con comillas dobles), por ejemplo:
        MAIN_TOPICS=["genocidio en Gaza", "Agenda de seguridad"]

    Returns:
        list[str]: Lista de temas normalizados (sin espacios sobrantes y sin
                   elementos vacíos). Vacía si la variable no está definida.

    Raises:
        ConfigurationError: Si el valor no es un array JSON válido de strings.
    """
    raw = os.environ.get("MAIN_TOPICS")
    if raw is None:
        return []

    raw = raw.strip()
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            "La variable de entorno MAIN_TOPICS no contiene JSON válido. "
            "Debe ser un array de textos con comillas dobles, por ejemplo: "
            'MAIN_TOPICS=["genocidio en Gaza", "Agenda de seguridad"]'
        ) from exc

    if not isinstance(data, list):
        raise ConfigurationError(
            "La variable de entorno MAIN_TOPICS debe ser un array JSON de "
            f"textos, pero se encontró {type(data).__name__}."
        )

    topics: list[str] = []
    for idx, topic in enumerate(data):
        if not isinstance(topic, str):
            raise ConfigurationError(
                f"El elemento #{idx} de MAIN_TOPICS no es un texto: {topic!r}"
            )
        cleaned = topic.strip()
        if cleaned:
            topics.append(cleaned)

    return topics
