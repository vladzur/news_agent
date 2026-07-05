"""Módulo de escritura de artículos completos desde la pauta editorial.

Permite tomar una propuesta específica de la pauta semanal y desarrollarla
como artículo completo (~1000 palabras) manteniendo el tono editorial
de La Chispa Sur.
"""

import logging
import re
from pathlib import Path
from typing import Any

from .config import ARTICLE_MAX_TOKENS, get_api_key
from .llm_client import LLMClient, LLMClientError
from .prompt_builder import build_article_system_prompt, build_article_user_prompt
from .report_writer import save_article

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class PautaParseError(Exception):
    """Excepción para errores al parsear el archivo de pauta."""


def parse_pauta_file(filepath: str | Path) -> list[dict[str, Any]]:
    """Parsea un archivo de pauta editorial y extrae las propuestas.

    Espera el formato Markdown generado por el agente:
    - Cabecera con # ⚡ Pauta Editorial Sugerida
    - Propuestas numeradas como ## 1. [TÍTULO], ## 2. [TÍTULO], ## 3. [TÍTULO]
    - Cada propuesta tiene Enfoque Editorial, Puntos Clave, y Fuentes Sugeridas.

    Args:
        filepath: Ruta al archivo .md de pauta semanal.

    Returns:
        list[dict]: Lista de propuestas, cada una con:
            - title (str)
            - enfoque (str)
            - puntos (list[str])
            - fuentes (list[str])

    Raises:
        PautaParseError: Si el archivo no existe, no es una pauta válida,
                         o no contiene exactamente 3 propuestas.
    """
    path = Path(filepath)
    if not path.exists():
        raise PautaParseError(f"Archivo de pauta no encontrado: {path.resolve()}")

    content = path.read_text(encoding="utf-8")

    # Verificar que es un archivo de pauta válido
    if "# ⚡ Pauta Editorial Sugerida" not in content:
        raise PautaParseError(
            f"El archivo no parece ser una pauta editorial válida: "
            f"falta la cabecera '# ⚡ Pauta Editorial Sugerida'."
        )

    # Dividir por propuestas (## 1., ## 2., ## 3.)
    # Usamos regex para capturar cada sección de propuesta
    proposal_pattern = r"##\s+(\d+)\.\s+(.+?)(?=\n##\s+\d+\.\s+|$)"
    matches = list(re.finditer(proposal_pattern, content, re.DOTALL))

    if len(matches) != 3:
        raise PautaParseError(
            f"Se esperaban 3 propuestas en la pauta, pero se encontraron "
            f"{len(matches)}."
        )

    proposals: list[dict[str, Any]] = []

    for match in matches:
        number = int(match.group(1))
        block = match.group(0)

        # Extraer título (primera línea después de "## N. ")
        title_match = re.match(r"##\s+\d+\.\s+(.+?)$", block, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else f"Propuesta {number}"

        # Extraer enfoque editorial
        enfoque = _extract_section(block, "Enfoque Editorial", "Puntos Clave")

        # Extraer puntos clave
        puntos = _extract_list_items(block, "Puntos Clave", "Fuentes Sugeridas")

        # Extraer fuentes sugeridas
        fuentes = _extract_list_items(block, "Fuentes Sugeridas", None)

        proposals.append(
            {
                "number": number,
                "title": title,
                "enfoque": enfoque,
                "puntos": puntos,
                "fuentes": fuentes,
            }
        )

    return proposals


def _extract_section(text: str, start_marker: str, end_marker: str | None) -> str:
    """Extrae el texto entre dos marcadores de sección.

    Busca el marcador de inicio como subcadena (ignorando mayúsculas/minúsculas
    y caracteres de formato markdown como ** y *). Luego extrae desde el `:`
    más cercano después del marcador hasta el marcador de fin.

    Args:
        text: Texto completo donde buscar.
        start_marker: Texto identificador de la sección (ej: "Enfoque Editorial").
        end_marker: Texto identificador de la siguiente sección, o None.

    Returns:
        str: Texto extraído y limpiado.
    """
    # Buscar el marcador como subcadena (ignorando case)
    text_lower = text.lower()
    marker_lower = start_marker.lower()
    marker_pos = text_lower.find(marker_lower)

    if marker_pos == -1:
        return ""

    # Encontrar el ':' más cercano después del marcador
    colon_pos = text.find(":", marker_pos)
    if colon_pos == -1:
        return ""
    start_pos = colon_pos + 1

    # Buscar el marcador de fin
    if end_marker:
        end_marker_lower = end_marker.lower()
        end_pos = text_lower.find(end_marker_lower, start_pos)
        if end_pos == -1:
            end_pos = len(text)
    else:
        end_pos = len(text)

    extracted = text[start_pos:end_pos].strip()
    # Limpiar marcadores de formato markdown residuales al inicio
    extracted = re.sub(r"^\*{1,3}\s*", "", extracted)
    # Normalizar saltos de línea (colapsar 3+ saltos en 2)
    extracted = re.sub(r"\n\s*\n\s*\n+", "\n\n", extracted)

    return extracted.strip()


def _extract_list_items(
    text: str, start_marker: str, end_marker: str | None
) -> list[str]:
    """Extrae items de una lista desde una sección del texto.

    Args:
        text: Texto completo.
        start_marker: Marcador de inicio de sección (ej: "Puntos Clave").
        end_marker: Marcador de fin de sección, o None.

    Returns:
        list[str]: Lista de items extraídos.
    """
    section = _extract_section(text, start_marker, end_marker)
    if not section:
        return []

    items: list[str] = []
    # Buscar items numerados (1. texto) o con bullet (* texto)
    for line in section.split("\n"):
        line = line.strip()
        # Ignorar líneas que son solo formato markdown (**, #, etc.)
        if not line or line in ("**", "*", "---", "***"):
            continue
        # Item numerado: "1. texto" o "1) texto"
        match = re.match(r"^\d+[\.\)]\s+(.+)", line)
        if match:
            items.append(match.group(1).strip())
        # Item con bullet: "* texto" o "- texto"
        elif line.startswith("* ") or line.startswith("- "):
            item_text = line[2:].strip()
            # Filtrar items que son solo formato residual
            if item_text and item_text not in ("*", "**"):
                items.append(item_text)

    return items


def write_article(
    pauta_path: str | Path,
    article_number: int,
    output_dir: str | Path = ".",
    verbose: bool = False,
) -> dict[str, Any]:
    """Escribe un artículo completo a partir de una propuesta de la pauta.

    Args:
        pauta_path: Ruta al archivo de pauta semanal.
        article_number: Número de propuesta a desarrollar (1, 2 o 3).
        output_dir: Directorio donde guardar el artículo generado.
        verbose: Si es True, activa logging DEBUG.

    Returns:
        dict con:
            - article_path (Path): Ruta al archivo generado.
            - title (str): Título del artículo.
            - proposal_number (int): Número de propuesta.

    Raises:
        PautaParseError: Si el archivo de pauta no es válido.
        ValueError: Si el número de artículo no es 1, 2 o 3.
        LLMClientError: Si falla la comunicación con la API.
        SystemExit: Si falta la API key.
    """
    import sys

    from .orchestrator import setup_logging

    setup_logging(verbose)

    if article_number not in (1, 2, 3):
        raise ValueError(
            f"Número de artículo inválido: {article_number}. Debe ser 1, 2 o 3."
        )

    logger.info(
        "=== Iniciando escritura de artículo #%d desde pauta ===", article_number
    )

    # -------------------------------------------------------------------
    # Paso 1: Validar API Key
    # -------------------------------------------------------------------
    try:
        api_key = get_api_key()
    except Exception as exc:
        logger.error("Error de configuración: %s", exc)
        sys.exit(1)

    # -------------------------------------------------------------------
    # Paso 2: Parsear archivo de pauta
    # -------------------------------------------------------------------
    logger.info("Parseando archivo de pauta: %s", pauta_path)
    proposals = parse_pauta_file(pauta_path)

    # Buscar la propuesta solicitada
    proposal = None
    for prop in proposals:
        if prop["number"] == article_number:
            proposal = prop
            break

    if proposal is None:
        raise PautaParseError(
            f"No se encontró la propuesta #{article_number} en la pauta. "
            f"Propuestas disponibles: {[p['number'] for p in proposals]}"
        )

    logger.info(
        "Propuesta seleccionada: #%d — %s", article_number, proposal["title"]
    )

    # -------------------------------------------------------------------
    # Paso 3: Construir prompts
    # -------------------------------------------------------------------
    system_prompt = build_article_system_prompt()
    user_prompt = build_article_user_prompt(proposal)

    logger.info(
        "Prompts construidos: system=%d chars, user=%d chars.",
        len(system_prompt),
        len(user_prompt),
    )

    # -------------------------------------------------------------------
    # Paso 4: Llamar a la API de DeepSeek
    # -------------------------------------------------------------------
    # Usar un límite de tokens más alto que el de pauta: el modo thinking
    # consume parte del presupuesto en razonamiento interno antes de producir
    # el contenido final del artículo (~1000 palabras).
    client = LLMClient(api_key=api_key, max_tokens=ARTICLE_MAX_TOKENS)

    try:
        article_content = client.generate_report(system_prompt, user_prompt)
    except LLMClientError as exc:
        logger.error("Fallo al generar el artículo con DeepSeek: %s", exc)
        sys.exit(1)

    if not article_content or not article_content.strip():
        logger.error("La API devolvió un artículo vacío.")
        sys.exit(1)

    logger.info(
        "Artículo generado: %d caracteres (~%d palabras).",
        len(article_content),
        len(article_content.split()),
    )

    # -------------------------------------------------------------------
    # Paso 5: Guardar artículo
    # -------------------------------------------------------------------
    try:
        article_path = save_article(
            article_content, proposal["title"], article_number, output_dir
        )
    except IOError as exc:
        logger.error("Error al guardar el artículo: %s", exc)
        sys.exit(1)

    logger.info("=== Artículo #%d escrito exitosamente ===", article_number)
    logger.info("Archivo: %s", article_path)

    return {
        "article_path": article_path,
        "title": proposal["title"],
        "proposal_number": article_number,
    }
