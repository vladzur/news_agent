"""Módulo de escritura del reporte final en formato Markdown.

Genera el archivo pauta_semanal_AAAA_MM_DD.md con el contenido
producido por el modelo DeepSeek.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


def build_filename() -> str:
    """Construye el nombre del archivo de salida con la fecha actual.

    Returns:
        str: Nombre de archivo en formato 'pauta_semanal_YYYY_MM_DD.md'.
    """
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    return f"pauta_semanal_{today}.md"


def build_header(item_count: int) -> str:
    """Construye la cabecera del reporte con estadísticas de procesamiento.

    Args:
        item_count: Cantidad de artículos procesados.

    Returns:
        str: Bloque de cabecera en formato Markdown.
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return (
        f"# ⚡ Pauta Editorial Sugerida - La Chispa Sur\n"
        f"**Fecha de Generación:** {today_str}  \n"
        f"**Notas Procesadas:** {item_count}\n"
        f"\n---\n"
    )


def save_report(
    content: str,
    item_count: int,
    output_dir: str | Path = ".",
) -> Path:
    """Guarda el reporte editorial en un archivo Markdown.

    Si el contenido ya incluye una cabecera con el formato de La Chispa Sur,
    se usa tal cual. En caso contrario, se antepone la cabecera automática.

    Args:
        content: Texto completo generado por el LLM.
        item_count: Cantidad de artículos que fueron analizados.
        output_dir: Directorio donde se guardará el archivo (por defecto ".").

    Returns:
        Path: Ruta absoluta al archivo generado.

    Raises:
        IOError: Si el directorio de salida no existe o no se puede escribir.
    """
    output_path = Path(output_dir)
    if not output_path.exists():
        raise IOError(f"El directorio de salida no existe: {output_path.resolve()}")

    filename = build_filename()
    file_path = output_path / filename

    # Si el LLM ya incluyó la cabecera, no la duplicamos
    header_marker = "# ⚡ Pauta Editorial Sugerida"
    if content.strip().startswith(header_marker):
        final_content = content
    else:
        final_content = build_header(item_count) + "\n" + content

    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(final_content)

    logger.info("Reporte guardado exitosamente en: %s", file_path.resolve())
    return file_path.resolve()
