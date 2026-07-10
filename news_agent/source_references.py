"""Módulo de referencias a fuentes para la escritura de artículos.

Extrae las fuentes sugeridas desde el texto de la pauta editorial — analizando
la sección "Fuentes Sugeridas para Ampliar" de cada propuesta — y las empareja
determinísticamente con los artículos recolectados del pipeline RSS.

A diferencia del enfoque anterior (bloque <!-- REFERENCIAS_INTERNAS -->),
este método no depende de que el LLM auto-reporte números de artículo correctos.
En su lugar, cruza nombres de medios y palabras clave del texto de la pauta
contra los artículos filtrados para encontrar las coincidencias más probables.
"""

import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import COMPANION_MAX_ARTICLES_PER_SOURCE, SOURCE_ARTICLE_MAX_CHARS
from .content_enricher import fetch_single_article

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Palabras vacías en español que no aportan a la búsqueda temática
_STOP_WORDS: set[str] = {
    "para", "como", "más", "una", "por", "del", "los", "las", "que",
    "con", "sus", "esa", "ese", "eso", "este", "esta", "esto", "cada",
    "entre", "desde", "hasta", "sobre", "todo", "muy", "han", "fue",
    "era", "son", "ser", "tiene", "haber", "hace", "dijo", "hizo",
    "tras", "ayer", "hoy", "ante", "bajo", "cabe", "cuando", "donde",
    "durante", "excepto", "hacia", "mediante", "según", "también",
    "porque", "puede", "sido", "está", "están", "será", "serán",
    "el", "la", "lo", "le", "se", "su", "al", "un", "de", "en",
    "a", "e", "i", "o", "u", "y", "ni", "no", "sí", "ya", "me",
    "te", "nos", "os", "es", "ha", "he", "da", "va", "ir",
    # Palabras específicas de la pauta que no son contenido
    "fuente", "fuentes", "sugeridas", "ampliar", "consultar",
    "investigación", "original", "cobertura", "análisis", "nota",
    "reportaje", "artículo", "información", "datos", "informe",
}

# Mínimo de caracteres para considerar una palabra como keyword
_MIN_WORD_LENGTH = 4


# Score mínimo para considerar un artículo como match relevante
_MIN_MATCH_SCORE = 0.05


# ---------------------------------------------------------------------------
# Extracción de fuentes desde el texto de la pauta
# ---------------------------------------------------------------------------


def extract_proposal_sources(
    pauta_text: str,
) -> dict[int, list[dict[str, str]]]:
    """Extrae las fuentes sugeridas de cada propuesta desde el texto de la pauta.

    Busca la sección "Fuentes Sugeridas para Ampliar" dentro de cada propuesta
    (## 1., ## 2., ## 3.) y extrae cada entrada como un dict con el nombre
    del medio y la descripción completa.

    Args:
        pauta_text: Texto completo de la pauta editorial en Markdown.

    Returns:
        Diccionario {número_propuesta: [{"source_name": str, "description": str}]}.
        Solo incluye propuestas con al menos una fuente extraída.
    """
    result: dict[int, list[dict[str, str]]] = {}

    # Dividir el texto en propuestas (## 1., ## 2., ## 3.)
    proposal_pattern = r"##\s+(\d+)\.\s+(.+?)(?=\n##\s+\d+\.\s+|$)"
    for match in re.finditer(proposal_pattern, pauta_text, re.DOTALL):
        try:
            prop_num = int(match.group(1))
        except (ValueError, IndexError):
            continue

        block = match.group(0)

        # Buscar la sección "Fuentes Sugeridas"
        sources = _extract_source_entries(block)
        if sources:
            result[prop_num] = sources

    if result:
        total = sum(len(v) for v in result.values())
        logger.info(
            "Fuentes extraídas de la pauta: %d propuesta(s) con %d fuente(s) en total.",
            len(result),
            total,
        )
    else:
        logger.warning(
            "No se pudieron extraer fuentes sugeridas desde la pauta. "
            "No se generará archivo companion."
        )

    return result


# ---------------------------------------------------------------------------
# Extracción de menciones de medios desde el cuerpo narrativo de la pauta
# ---------------------------------------------------------------------------


def _extract_media_mentions_from_body(
    proposal_block: str,
    known_sources: set[str],
) -> list[dict[str, str]]:
    """Extrae menciones de medios conocidos desde el cuerpo narrativo de una propuesta.

    A diferencia de _extract_source_entries, que solo busca en la sección
    "Fuentes Sugeridas para Ampliar", esta función escanea todo el bloque
    de la propuesta en busca de nombres de medios presentes en known_sources.

    Args:
        proposal_block: Bloque de texto completo de una propuesta individual.
        known_sources: Conjunto de nombres de medios conocidos (desde filtered_items).

    Returns:
        Lista de dicts con 'source_name' y 'description' (la oración donde
        aparece la mención). Sin duplicados por nombre de medio.
    """
    mentions: list[dict[str, str]] = []
    seen_sources: set[str] = set()

    # Ordenar por longitud descendente para evitar que "La Tercera" haga match
    # antes que "La Tercera – Pulso" (coincidencia parcial)
    sorted_sources = sorted(known_sources, key=len, reverse=True)

    for source in sorted_sources:
        source_lower = source.lower().strip()
        if source_lower in seen_sources:
            continue
        if len(source) < 3:
            continue

        # Buscar menciones del medio en el bloque (case-insensitive)
        # Capturamos la oración completa que contiene la mención
        pattern = re.compile(
            r"([^.]*?\b" + re.escape(source) + r"[^.]*\.)",
            re.IGNORECASE,
        )

        for match in pattern.finditer(proposal_block):
            context = match.group(1).strip()

            # Filtrar contextos triviales o que pertenecen a la sección Fuentes
            if len(context) < 20:
                continue
            if "Fuentes Sugeridas" in context:
                continue

            mentions.append(
                {
                    "source_name": source,
                    "description": context,
                }
            )
            seen_sources.add(source_lower)
            break  # Una mención por medio por propuesta es suficiente

    return mentions


def extract_media_sources_from_pauta(
    pauta_text: str,
    known_sources: set[str],
) -> dict[int, list[dict[str, str]]]:
    """Extrae menciones de medios conocidos del texto narrativo de cada propuesta.

    Complementa a extract_proposal_sources: donde esta solo busca en la sección
    "Fuentes Sugeridas para Ampliar" (que el LLM puebla con instituciones y
    organismos), extract_media_sources_from_pauta escanea el cuerpo completo
    de cada propuesta —enfoque editorial, puntos clave, etc.— en busca de
    nombres de medios que sí están en los feeds RSS.

    Args:
        pauta_text: Texto completo de la pauta editorial en Markdown.
        known_sources: Conjunto de nombres de medios conocidos.

    Returns:
        Diccionario {número_propuesta: [{"source_name": str, "description": str}]}.
    """
    result: dict[int, list[dict[str, str]]] = {}

    proposal_pattern = r"##\s+(\d+)\.\s+(.+?)(?=\n##\s+\d+\.\s+|$)"
    for match in re.finditer(proposal_pattern, pauta_text, re.DOTALL):
        try:
            prop_num = int(match.group(1))
        except (ValueError, IndexError):
            continue

        block = match.group(0)
        mentions = _extract_media_mentions_from_body(block, known_sources)
        if mentions:
            result[prop_num] = mentions

    if result:
        total = sum(len(v) for v in result.values())
        logger.info(
            "Menciones de medios extraídas del cuerpo: %d propuesta(s) con %d medio(s).",
            len(result),
            total,
        )
    else:
        logger.info(
            "No se encontraron menciones de medios conocidos en el cuerpo de la pauta."
        )

    return result


def _extract_source_entries(proposal_block: str) -> list[dict[str, str]]:
    """Extrae las entradas individuales de la sección Fuentes Sugeridas.

    Busca el marcador "Fuentes Sugeridas" y extrae cada ítem de lista
    (numerado o con bullet) que comience con un nombre de medio en negrita.

    Args:
        proposal_block: Bloque de texto de una propuesta individual.

    Returns:
        Lista de dicts con 'source_name' y 'description'.
    """
    # Encontrar la sección: desde "Fuentes Sugeridas" hasta el final del bloque
    # o hasta un marcador de fin de sección
    sources_start = _find_section_start(proposal_block, "Fuentes Sugeridas")
    if sources_start == -1:
        return []

    section = proposal_block[sources_start:]

    entries: list[dict[str, str]] = []
    # Patrón para items tipo: "*   **Nombre Medio:** descripción"
    # o "*   Nombre Medio: descripción"
    # o "1. **Nombre Medio:** descripción"

    # Buscar patrones de "Medio: descripción"
    entry_pattern = re.compile(
        r"(?:^\s*[\*\-\d\.]+\s*)?"  # bullet/número opcional al inicio de línea
        r"\*{0,2}"                   # negrita opcional (0, 1 o 2 asteriscos)
        r"([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\s\-\.&]+?)"  # nombre del medio
        r"\*{0,2}"                   # cierre de negrita opcional
        r"\s*:\s*"                   # dos puntos
        r"(.+?)$",                   # descripción (hasta fin de línea)
        re.MULTILINE,
    )

    for match in entry_pattern.finditer(section):
        source_name = match.group(1).strip()
        description = match.group(2).strip()

        # Filtrar líneas que no son realmente entradas de fuente
        if len(source_name) < 2 or len(description) < 10:
            continue

        # Ignorar si parece una URL o instrucción
        if source_name.startswith("http") or "No incluyas" in description:
            continue

        entries.append({
            "source_name": source_name,
            "description": description,
        })

    # Dedicar: no incluir más de COMPANION_MAX_ARTICLES_PER_SOURCE entradas por fuente
    # para evitar saturar el companion con matches poco relevantes
    seen_names: set[str] = set()
    deduped: list[dict[str, str]] = []
    for entry in entries:
        key = entry["source_name"].lower()
        if key not in seen_names:
            seen_names.add(key)
            deduped.append(entry)

    return deduped


def _find_section_start(text: str, marker: str) -> int:
    """Encuentra la posición donde empieza el contenido de una sección.

    Busca el marcador (case-insensitive), luego el ':' más cercano,
    y devuelve la posición después de ese ':'.

    Args:
        text: Texto donde buscar.
        marker: Marcador de sección (ej: "Fuentes Sugeridas").

    Returns:
        Índice del primer carácter después del ':' del marcador, o -1.
    """
    text_lower = text.lower()
    marker_lower = marker.lower()
    marker_pos = text_lower.find(marker_lower)

    if marker_pos == -1:
        return -1

    colon_pos = text.find(":", marker_pos)
    if colon_pos == -1:
        return -1

    return colon_pos + 1


# ---------------------------------------------------------------------------
# Emparejamiento de fuentes con artículos
# ---------------------------------------------------------------------------


def match_sources_to_articles(
    proposal_sources: dict[int, list[dict[str, str]]],
    filtered_items: list[dict[str, Any]],
) -> dict[int, list[int]]:
    """Empareja fuentes extraídas de la pauta con artículos del pipeline.

    Para cada fuente mencionada en la pauta, busca los artículos en
    filtered_items que coincidan por:
    1. Nombre del medio (comparación insensible a mayúsculas y parcial)
    2. Solapamiento de palabras clave entre la descripción de la fuente
       y el título + contenido del artículo.

    Args:
        proposal_sources: Fuentes extraídas por propuesta (de extract_proposal_sources).
        filtered_items: Artículos filtrados del pipeline (cada uno con
                       title, source, summary_clean, etc.).

    Returns:
        Diccionario {número_propuesta: [índices_artículo]} donde los índices
        son 1-based (igual que en el prompt original). Solo incluye propuestas
        con al menos un artículo emparejado.
    """
    result: dict[int, list[int]] = {}

    for prop_num, sources in proposal_sources.items():
        matched_indices: set[int] = set()

        for src in sources:
            source_name = src["source_name"]
            description = src["description"]

            # Puntuar todos los artículos contra esta fuente
            scored: list[tuple[int, float]] = []
            for idx, item in enumerate(filtered_items):
                item_source = item.get("source", "")
                if not _source_names_match(source_name, item_source):
                    continue

                score = _score_article_match(description, item)
                if score >= _MIN_MATCH_SCORE:
                    scored.append((idx, score))

            # Ordenar por score descendente, tomar los mejores
            scored.sort(key=lambda x: x[1], reverse=True)
            top_n = scored[:COMPANION_MAX_ARTICLES_PER_SOURCE]

            for idx, score in top_n:
                matched_indices.add(idx)
                logger.debug(
                    "Match: '%s' → artículo #%d '%s' (score=%.2f)",
                    source_name,
                    idx + 1,
                    filtered_items[idx].get("title", "?")[:60],
                    score,
                )

        if matched_indices:
            # Convertir a 1-based y ordenar
            result[prop_num] = sorted([idx + 1 for idx in matched_indices])

    if result:
        total = sum(len(v) for v in result.values())
        logger.info(
            "Emparejamiento completado: %d propuesta(s) con %d artículo(s) en total.",
            len(result),
            total,
        )
    else:
        logger.warning(
            "No se encontraron artículos que coincidan con las fuentes "
            "mencionadas en la pauta."
        )

    return result


def _source_names_match(pauta_name: str, item_source: str) -> bool:
    """Determina si un nombre de medio en la pauta coincide con un item source.

    Comparación insensible a mayúsculas/minúsculas y tolerante a variaciones
    como "CIPER Chile" vs "Ciper Chile", "DF Diario" vs "DF", etc.

    Args:
        pauta_name: Nombre del medio tal como aparece en la pauta.
        item_source: Campo 'source' del artículo en filtered_items.

    Returns:
        True si los nombres se consideran equivalentes.
    """
    p = pauta_name.lower().strip()
    i = item_source.lower().strip()

    if p == i:
        return True

    # Coincidencia parcial significativa (al menos 4 caracteres en común)
    # Ej: "CIPER Chile" contiene "ciper", "DF Diario" contiene "df"
    if len(p) >= 4 and p in i:
        return True
    if len(i) >= 4 and i in p:
        return True

    # Coincidencia por primer palabra significativa
    # Ej: "La Tercera – Pulso" y "La Tercera"
    p_first = p.split()[0] if p.split() else ""
    i_first = i.split()[0] if i.split() else ""
    if len(p_first) >= 3 and p_first == i_first:
        return True

    return False


def _score_article_match(
    description: str,
    article: dict[str, Any],
) -> float:
    """Puntúa un artículo según su relevancia para una descripción de fuente.

    Extrae palabras clave de la descripción (después de los ':') y calcula
    el solapamiento con el título y resumen del artículo.

    Args:
        description: Texto descriptivo de la fuente (ej: "Su investigación
                    sobre la sanción al proyecto en Villarrica...").
        article: Artículo con 'title' y 'summary_clean'.

    Returns:
        Score entre 0.0 (sin relación) y 1.0 (match perfecto).
    """
    # Extraer keywords de la descripción
    desc_keywords = _extract_keywords(description)

    # Construir texto del artículo para comparar
    article_text = (
        (article.get("title") or "") + " " + (article.get("summary_clean") or "")
    )
    article_keywords = _extract_keywords(article_text)

    if not desc_keywords:
        return 0.0

    # Calcular solapamiento: intersección / unión (Jaccard)
    desc_set = set(desc_keywords)
    art_set = set(article_keywords)
    intersection = desc_set & art_set

    if not intersection:
        return 0.0

    # Jaccard modificado: peso doble a la intersección para favorecer
    # matches con varios keywords en común
    jaccard = len(intersection) / len(desc_set | art_set)

    # Bonus por keywords que aparecen en el título
    title_lower = (article.get("title") or "").lower()
    title_hits = sum(1 for kw in intersection if kw in title_lower)
    title_bonus = title_hits * 0.1

    return min(jaccard + title_bonus, 1.0)


def _extract_keywords(text: str) -> list[str]:
    """Extrae palabras clave significativas de un texto.

    Filtra stop words, palabras cortas, números y caracteres especiales.
    Retorna las palabras en minúsculas.

    Args:
        text: Texto del cual extraer keywords.

    Returns:
        Lista de palabras clave, preservando el orden de aparición.
    """
    # Tokenizar: solo letras y vocales acentuadas
    words = re.findall(r"[a-záéíóúñ]+", text.lower())
    return [
        w for w in words
        if len(w) >= _MIN_WORD_LENGTH and w not in _STOP_WORDS
    ]


# ---------------------------------------------------------------------------
# Utilidades de contenido
# ---------------------------------------------------------------------------


def _truncate_content(
    text: str | None,
    max_chars: int = SOURCE_ARTICLE_MAX_CHARS,
) -> str:
    """Trunca un texto en un límite de palabras cercano a max_chars.

    Args:
        text: Texto a truncar. Puede ser None.
        max_chars: Cantidad máxima de caracteres.

    Returns:
        Texto truncado con "…" al final si fue necesario, o cadena vacía
        si text es None o está vacío.
    """
    if not text:
        return ""

    text = text.strip()
    if len(text) <= max_chars:
        return text

    # Buscar el último espacio antes del límite para no cortar palabras
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.7:
        truncated = truncated[:last_space]

    return truncated.rstrip() + "…"


# ---------------------------------------------------------------------------
# Construcción del archivo companion
# ---------------------------------------------------------------------------


def build_companion_data(
    pauta_text: str,
    pauta_path: Path,
    filtered_items: list[dict[str, Any]],
) -> Path | None:
    """Construye y guarda el archivo JSON companion con las fuentes enriquecidas.

    Flujo:
    1. Extrae las fuentes sugeridas desde el texto de la pauta.
    2. Empareja cada fuente con artículos del pipeline por nombre de medio
       y similitud temática (keywords).
    3. Enriquece los artículos emparejados con contenido completo.
    4. Guarda el companion JSON junto al archivo de pauta.

    A diferencia del enfoque anterior, NO depende de que el LLM reporte
    números de artículo — deriva el mapeo del contenido textual de la pauta.

    Args:
        pauta_text: Texto completo de la pauta generada por el LLM.
        pauta_path: Ruta al archivo de pauta markdown ya guardado.
        filtered_items: Lista de artículos filtrados del pipeline (cada uno
                        con title, source, link, summary_clean, full_content, etc.).

    Returns:
        Path al archivo companion JSON generado, o None si no se pudo generar.
    """
    # Paso 1a: Extraer fuentes desde la sección "Fuentes Sugeridas para Ampliar"
    proposal_sources = extract_proposal_sources(pauta_text)

    # Paso 1b: Extraer menciones de medios del cuerpo narrativo de la pauta.
    # El LLM cita medios reales (CIPER Chile, La Tercera, DF Diario, etc.) en el
    # texto de cada propuesta, pero en "Fuentes Sugeridas" suele poner instituciones
    # (CPI, Dipres, Senapred) que no están en los feeds RSS.
    known_sources = {
        item.get("source", "") for item in filtered_items if item.get("source")
    }
    known_sources.discard("")
    media_mentions = extract_media_sources_from_pauta(pauta_text, known_sources)

    # Mezclar ambas fuentes: las de "Fuentes Sugeridas" tienen prioridad;
    # las del cuerpo se agregan solo si el medio no fue capturado ya.
    for prop_num, sources in media_mentions.items():
        if prop_num not in proposal_sources:
            proposal_sources[prop_num] = []
        existing_names = {
            s["source_name"].lower() for s in proposal_sources[prop_num]
        }
        for src in sources:
            if src["source_name"].lower() not in existing_names:
                proposal_sources[prop_num].append(src)
                existing_names.add(src["source_name"].lower())

    if not proposal_sources:
        return None

    # Paso 2: Emparejar fuentes con artículos del pipeline
    matched = match_sources_to_articles(proposal_sources, filtered_items)
    if not matched:
        return None

    # Paso 3: Construir datos enriquecidos por propuesta
    companion_data: dict[str, Any] = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_articles_in_pipeline": len(filtered_items),
        },
    }

    total_enriched = 0
    total_failed = 0

    # Incluir las 3 propuestas, incluso si alguna no tiene artículos
    for prop_num in range(1, 4):
        article_indices = matched.get(prop_num, [])
        articles: list[dict[str, Any]] = []

        for article_idx in article_indices:
            # filtered_items usa índice 0-based
            item = filtered_items[article_idx - 1]

            title = item.get("title", "Sin título")
            source = item.get("source", "Fuente desconocida")
            link = item.get("link", "")
            summary = item.get("summary_clean", "")

            # Intentar obtener contenido completo
            full_content = item.get("full_content")

            if not full_content and link:
                logger.info(
                    "Forzando extracción de contenido para artículo emparejado: "
                    "%s (%s)",
                    title[:60],
                    source,
                )
                full_content = fetch_single_article(link)

            if full_content:
                content = _truncate_content(full_content)
                total_enriched += 1
            else:
                content = summary
                total_failed += 1
                logger.info(
                    "Sin contenido completo para artículo emparejado "
                    "'%s' (%s). Se usará resumen como fallback.",
                    title[:60],
                    source,
                )

            articles.append(
                {
                    "title": title,
                    "source": source,
                    "link": link,
                    "summary": summary,
                    "content": content,
                }
            )

        companion_data[f"proposal_{prop_num}"] = {"articles": articles}

    # Paso 4: Guardar archivo companion
    companion_path = _build_companion_path(pauta_path)
    try:
        companion_path.parent.mkdir(parents=True, exist_ok=True)
        with open(companion_path, "w", encoding="utf-8") as fh:
            json.dump(companion_data, fh, ensure_ascii=False, indent=2)

        logger.info(
            "Archivo companion guardado: %s (%d artículos enriquecidos, "
            "%d con fallback).",
            companion_path,
            total_enriched,
            total_failed,
        )
    except IOError as exc:
        logger.warning(
            "No se pudo guardar el archivo companion %s: %s",
            companion_path,
            exc,
        )
        return None

    return companion_path


def _build_companion_path(pauta_path: Path) -> Path:
    """Construye la ruta al archivo companion a partir de la ruta de la pauta.

    Ejemplo: pauta_semanal_2026_07_08.md → pauta_semanal_2026_07_08_companion.json

    Args:
        pauta_path: Ruta al archivo .md de la pauta.

    Returns:
        Ruta al archivo companion JSON.
    """
    stem = pauta_path.stem
    return pauta_path.with_name(f"{stem}_companion.json")


# ---------------------------------------------------------------------------
# Carga del companion para el redactor de artículos
# ---------------------------------------------------------------------------


def load_companion_data(
    pauta_path: str | Path,
    article_number: int,
) -> list[dict[str, Any]] | None:
    """Carga los artículos fuente desde el archivo companion de una pauta.

    Args:
        pauta_path: Ruta al archivo .md de la pauta semanal.
        article_number: Número de propuesta a cargar (1, 2 o 3).

    Returns:
        Lista de diccionarios con los datos de cada artículo fuente
        (title, source, link, summary, content), o None si:
        - El archivo companion no existe
        - El archivo está corrupto (JSON inválido)
        - La propuesta solicitada no tiene artículos en el companion
    """
    pauta = Path(pauta_path)
    companion_path = _build_companion_path(pauta)

    if not companion_path.exists():
        logger.info(
            "Archivo companion no encontrado: %s. "
            "El artículo se escribirá sin material de origen.",
            companion_path,
        )
        return None

    try:
        with open(companion_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning(
            "Archivo companion corrupto o ilegible (%s): %s. "
            "El artículo se escribirá sin material de origen.",
            companion_path,
            exc,
        )
        return None

    proposal_key = f"proposal_{article_number}"
    proposal_data = data.get(proposal_key)
    if proposal_data is None:
        logger.info(
            "La propuesta %d no tiene datos en el archivo companion.",
            article_number,
        )
        return None

    articles: list[dict[str, Any]] = proposal_data.get("articles", [])
    if not articles:
        logger.info(
            "La propuesta %d tiene una entrada en el companion pero sin artículos.",
            article_number,
        )
        return None

    logger.info(
        "Material de origen cargado desde companion: %d artículo(s) para "
        "la propuesta #%d.",
        len(articles),
        article_number,
    )

    return articles
