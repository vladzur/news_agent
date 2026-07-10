"""Módulo de configuración del agente de noticias.

Carga la configuración desde variables de entorno y archivos JSON externos.
También carga automáticamente un archivo .env del directorio del proyecto.
"""

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes de configuración del modelo DeepSeek
# ---------------------------------------------------------------------------
DEEPSEEK_MODEL = "deepseek-v4-pro"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
TEMPERATURE = 0.1
PAUTA_MAX_TOKENS = 16384  # Pauta semanal: ~1000+ noticias requieren más presupuesto de razonamiento
ARTICLE_MAX_TOKENS = 8192  # Artículo ~1000 palabras en español (~2500 tokens) + razonamiento
REASONING_EFFORT = "high"  # "high" o "max" para razonamiento profundo; None para deshabilitar thinking mode
ARTICLE_REASONING_EFFORT = "high"  # Razonamiento para redacción de artículos individuales

# ---------------------------------------------------------------------------
# Constantes de la ventana de análisis y formato
# ---------------------------------------------------------------------------
TIME_WINDOW_HOURS = 168  # 7 días: cubre la semana completa (lunes a domingo)
SUMMARY_MAX_CHARS = 700  # Suficiente para lead + cifras + atribuciones (reglas de precisión factual)

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
    for idx, feed in enumerate(data):
        if not isinstance(feed, dict):
            raise ConfigurationError(
                f"Entrada de feed #{idx} no es un diccionario: {feed}"
            )
        if "name" not in feed:
            raise ConfigurationError(
                f"Entrada de feed #{idx} no tiene el campo obligatorio 'name'."
            )
        if "url" not in feed:
            raise ConfigurationError(
                f"Entrada de feed #{idx} no tiene el campo obligatorio 'url'."
            )

        # Validación adicional para feeds con método "scraping"
        method = feed.get("method", "rss")
        if method == "scraping":
            if "selectors" not in feed:
                raise ConfigurationError(
                    f"Feed '{feed['name']}' usa method='scraping' pero "
                    "no tiene el campo obligatorio 'selectors'."
                )
            selectors = feed["selectors"]
            if not isinstance(selectors, dict):
                raise ConfigurationError(
                    f"Feed '{feed['name']}': 'selectors' debe ser un diccionario."
                )
            if "article" not in selectors:
                raise ConfigurationError(
                    f"Feed '{feed['name']}' usa method='scraping': "
                    "selectors requiere al menos la clave 'article'."
                )
            if "title" not in selectors:
                raise ConfigurationError(
                    f"Feed '{feed['name']}' usa method='scraping': "
                    "selectors requiere al menos la clave 'title'."
                )
        elif method != "rss":
            # Método desconocido: advertir pero no fallar (compatibilidad futura)
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(
                "Feed '%s' tiene method='%s' (desconocido). "
                "Se tratará como RSS por defecto.",
                feed["name"],
                method,
            )

    return data
