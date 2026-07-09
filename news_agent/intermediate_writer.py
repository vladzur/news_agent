"""Módulo de escritura de archivos intermedios de depuración.

Genera un archivo JSON con los artículos procesados antes del llamado al LLM,
permitiendo comparar manualmente el resumen RSS original, el contenido extraído
y el resumen final enviado al modelo para ajustar el prompt.
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


def save_intermediate(
    items: list[dict[str, Any]],
    output_dir: str | Path,
) -> Path:
    """Guarda un archivo JSON con los artículos procesados para depuración.

    El archivo incluye para cada artículo:
    - Título, fuente y enlace
    - Resumen RSS original (summary_raw)
    - Contenido completo extraído (full_content, si está disponible)
    - Resumen final enviado al LLM (summary_clean)

    Args:
        items: Lista de artículos filtrados con campos de depuración.
        output_dir: Directorio base de salida (se crea subdirectorio debug/).

    Returns:
        Path a el archivo JSON generado.

    Raises:
        IOError: Si el directorio de salida no existe o no se puede escribir.
    """
    output_path = Path(output_dir)
    if not output_path.exists():
        raise IOError(
            f"El directorio de salida no existe: {output_path.resolve()}"
        )

    # Crear subdirectorio debug/
    debug_dir = output_path / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    # Generar nombre de archivo con fecha actual
    today_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    filename = f"articulos_procesados_{today_str}.json"
    file_path = debug_dir / filename

    # Contar artículos enriquecidos
    enriched_count = sum(1 for item in items if item.get("full_content"))

    # Construir estructura del JSON
    articles_data: list[dict[str, Any]] = []
    for item in items:
        entry: dict[str, Any] = {
            "title": item.get("title", ""),
            "source": item.get("source", ""),
            "link": item.get("link"),
            "summary_raw": item.get("summary_raw", ""),
            "full_content": item.get("full_content"),
            "summary_clean": item.get("summary_clean", ""),
            "summary_clean_length": len(item.get("summary_clean", "")),
        }
        articles_data.append(entry)

    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_articles": len(items),
            "enriched_articles": enriched_count,
        },
        "articles": articles_data,
    }

    # Escribir archivo JSON con formato legible
    with open(file_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)

    logger.info(
        "Archivo intermedio guardado: %s (%d artículos, %d enriquecidos).",
        file_path,
        len(items),
        enriched_count,
    )

    return file_path
