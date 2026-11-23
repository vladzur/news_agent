"""Escritura del bundle de portadas editoriales.

Cada ejecución produce una carpeta autocontenida con las dos piezas PNG y el
manifiesto JSON que el editor usa para publicar la nota: sección, tratamiento,
texto alternativo y rutas de las imágenes.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# Nombre del manifiesto dentro del bundle.
METADATA_FILE_NAME = "portada.json"


def build_bundle_dir(
    output_dir: str | Path,
    slug: str,
    when: datetime | None = None,
) -> Path:
    """Crea y devuelve el directorio del bundle de una portada.

    El nombre combina la fecha del artículo y el slug del titular, igual que
    los bundles de RRSS, para que la carpeta sea identificable y ordenable.

    Args:
        output_dir: Directorio base de salida (ej: "portadas").
        slug: Slug del titular del artículo.
        when: Fecha de la portada. Por defecto, la actual en UTC.

    Returns:
        Path: Ruta absoluta al directorio del bundle, ya creado.
    """
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)

    moment = when or datetime.now(timezone.utc)
    folder = f"{moment.strftime('%Y_%m_%d')}_{slug or 'sin-titulo'}"
    bundle_dir = (base / folder).resolve()

    if bundle_dir.exists():
        logger.info("El bundle de portada ya existía: %s", bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    return bundle_dir


def metadata_path(bundle_dir: str | Path) -> Path:
    """Devuelve la ruta del manifiesto de un bundle.

    Args:
        bundle_dir: Directorio del bundle.

    Returns:
        Path: Ruta al archivo ``portada.json``.
    """
    return Path(bundle_dir).resolve() / METADATA_FILE_NAME


def read_metadata(bundle_dir: str | Path) -> dict[str, Any] | None:
    """Lee el manifiesto de un bundle, si existe y es válido.

    Args:
        bundle_dir: Directorio del bundle.

    Returns:
        dict[str, Any] | None: Contenido del manifiesto, o None si no existe
        o no se puede leer como objeto JSON.
    """
    path = metadata_path(bundle_dir)
    if not path.is_file():
        return None

    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("No se pudo leer el manifiesto %s: %s", path, exc)
        return None

    if not isinstance(data, dict):
        logger.warning("El manifiesto %s no es un objeto JSON.", path)
        return None

    return data


def save_metadata(metadata: dict[str, Any], bundle_dir: str | Path) -> Path:
    """Escribe el manifiesto del bundle como JSON legible.

    Args:
        metadata: Datos serializables de la portada.
        bundle_dir: Directorio del bundle.

    Returns:
        Path: Ruta absoluta del archivo escrito.

    Raises:
        OSError: Si no se puede escribir el archivo.
    """
    destination = metadata_path(bundle_dir)
    with open(destination, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    logger.info("Manifiesto de portada guardado: %s", destination)
    return destination
