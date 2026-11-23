"""Módulo de escritura del reporte final en formato Markdown.

Genera el archivo pauta_semanal_AAAA_MM_DD.md con el contenido
producido por el modelo DeepSeek y los artículos individuales con su
fecha de creación en el nombre y en una línea de metadatos.
"""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# Línea de metadatos que identifica la fecha de creación del artículo. Se
# escribe después del titular y antes de la firma para que el parser de RRSS,
# que arranca el cuerpo en la firma, no la incluya en el material de origen.
_ARTICLE_DATE_LINE = "**Fecha de creación:**"
_CREATION_DATE_RE = re.compile(
    r"(?m)^\s*\*\*Fecha de creación:\*\*.*(?:\n|$)"
)
_ARTICLE_HEADLINE_RE = re.compile(r"(?m)^#\s+(?!#).*$")


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

    La cabecera con fecha y cantidad de artículos se genera siempre desde
    el código para garantizar precisión. Si el LLM incluyó una cabecera
    propia, se descarta en favor de la cabecera automática con los datos
    correctos.

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

    # Construir la cabecera correcta con datos verificados
    correct_header = build_header(item_count)

    # Eliminar cabecera generada por el LLM si existe, para evitar datos
    # incorrectos de fecha o conteo de artículos. Detectamos la cabecera
    # por el marcador "# ⚡ Pauta Editorial Sugerida" y eliminamos todo
    # hasta el primer "## " (inicio de la primera propuesta) o el primer "---".
    header_marker = "# ⚡ Pauta Editorial Sugerida"
    stripped = content.strip()

    if stripped.startswith(header_marker):
        # El LLM generó una cabecera. Buscar dónde empieza el contenido real.
        # La cabecera del modelo típicamente termina en "---\n" seguido de "## 1."
        # o directamente en "## 1."
        first_proposal = stripped.find("\n## 1. ")
        if first_proposal == -1:
            # Fallback: buscar el primer "## " después del marcador
            first_proposal = stripped.find("\n## ", len(header_marker))

        if first_proposal != -1:
            body = stripped[first_proposal:].lstrip("\n")
        else:
            # Si no encontramos propuestas, buscar después del primer "---"
            sep = stripped.find("\n---\n", len(header_marker))
            if sep != -1:
                body = stripped[sep + len("\n---\n"):].lstrip("\n")
            else:
                # Último recurso: usar el contenido tal cual
                body = stripped

        final_content = correct_header + body
        logger.info(
            "Cabecera del LLM reemplazada por cabecera automática con datos "
            "verificados (fecha y conteo de %d artículos).",
            item_count,
        )
    else:
        # El LLM no generó cabecera — anteponemos la correcta
        final_content = correct_header + "\n" + stripped

    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(final_content)

    logger.info("Reporte guardado exitosamente en: %s", file_path.resolve())
    return file_path.resolve()


def _slugify(text: str, max_len: int = 50) -> str:
    """Convierte un texto en un slug apto para nombre de archivo.

    Args:
        text: Texto a convertir.
        max_len: Longitud máxima del slug resultante.

    Returns:
        str: Slug en minúsculas, solo caracteres alfanuméricos y guiones.
    """
    # Eliminar caracteres especiales, conservar letras, números y espacios
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    # Reemplazar espacios y guiones bajos por un solo guión
    slug = re.sub(r"[\s_]+", "-", slug)
    # Eliminar guiones repetidos
    slug = re.sub(r"-+", "-", slug)
    # Recortar al largo máximo sin cortar palabras
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug.strip("-")


def _inject_creation_date(content: str, date_str: str) -> str:
    """Inserta la fecha de creación después del titular del artículo.

    La línea se coloca entre el H1 y la firma. Así queda visible al abrir el
    archivo y el parser de RRSS, que arranca el cuerpo en la firma, la deja
    fuera del material de origen. Si el contenido ya trae una línea de fecha
    de creación, se reemplaza para no duplicarla.

    Args:
        content: Markdown del artículo.
        date_str: Fecha en formato AAAA-MM-DD.

    Returns:
        str: Artículo con la línea de fecha de creación.
    """
    cleaned = _CREATION_DATE_RE.sub("", content)
    date_line = f"{_ARTICLE_DATE_LINE} {date_str}"

    headline_match = _ARTICLE_HEADLINE_RE.search(cleaned)
    if headline_match is None:
        return f"{date_line}\n\n{cleaned.lstrip()}"

    tail = cleaned[headline_match.end():].lstrip("\n")
    updated = f"{cleaned[:headline_match.end()]}\n\n{date_line}\n\n{tail}"
    updated = re.sub(r"\n{3,}", "\n\n", updated)
    return updated.rstrip() + "\n"


def save_article(
    content: str,
    title: str,
    article_number: int,
    output_dir: str | Path = ".",
) -> Path:
    """Guarda un artículo individual como archivo Markdown.

    El nombre incluye la fecha de creación en formato AAAA_MM_DD y el archivo
    lleva una línea ``**Fecha de creación:** AAAA-MM-DD`` después del titular.
    La fecha se genera desde el código, nunca desde el modelo.

    Args:
        content: Texto completo del artículo generado por el LLM.
        title: Título del artículo (se usa para generar el slug del archivo).
        article_number: Número de artículo (1 a 5).
        output_dir: Directorio donde se guardará el archivo.

    Returns:
        Path: Ruta absoluta al archivo generado.

    Raises:
        IOError: Si el directorio de salida no existe.
    """
    output_path = Path(output_dir)
    if not output_path.exists():
        raise IOError(f"El directorio de salida no existe: {output_path.resolve()}")

    now = datetime.now(timezone.utc)
    file_date = now.strftime("%Y_%m_%d")
    display_date = now.strftime("%Y-%m-%d")

    slug = _slugify(title)
    filename = f"articulo_{article_number}_{file_date}_{slug}.md"
    file_path = output_path / filename

    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(_inject_creation_date(content, display_date))

    logger.info("Artículo guardado exitosamente en: %s", file_path.resolve())
    return file_path.resolve()
