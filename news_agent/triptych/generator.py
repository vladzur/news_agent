"""Generación y validación del tríptico impreso.

``build_triptych`` es la validación pura: convierte la respuesta del modelo en
un ``TriptychPackage`` midiendo cada nota contra el presupuesto de su columna.
``generate_triptych`` hace la llamada al modelo y reintenta hasta obtener un
JSON que cumpla el contrato estructural.

El reparto de responsabilidades es deliberado: lo estructural (que haya cinco
notas, que el cuerpo tenga texto y no sea un telegrama) es un error que aborta
la escritura; lo estilístico (frases largas, siglas sin explicar, una nota que
se pasa de columnas) solo se advierte, porque el texto final lo decide el
equipo editorial y un recorte automático mutila la redacción.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from ..config import TRIPTYCH_JSON_MAX_RETRIES, TRIPTYCH_NOTE_MIN_CHARS
from ..social.json_utils import JsonExtractionError, extract_json_object
from .models import CoverBlock, PrintNote, TriptychPackage
from .pauta_source import SourceProposal, TriptychSource
from .prompt_builder import build_triptych_system_prompt, build_triptych_user_prompt
from .specs import budget_report, triptych_specs
from .text_utils import style_warnings

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# Nota de corrección que se agrega al prompt cuando el intento anterior falló.
_RETRY_NOTE = (
    "\n\n## Corrección obligatoria\n\n"
    "El intento anterior no sirvió: {reason}\n"
    "Vuelve a responder solo con el objeto JSON, sin texto alrededor."
)

# El panel 1 es la portada: las notas empiezan en el panel siguiente.
_FIRST_NOTE_PANEL = 2


class TriptychGenerationError(Exception):
    """Excepción para errores al generar o validar el tríptico."""


def _now_iso() -> str:
    """Devuelve la marca de tiempo de generación.

    Returns:
        str: Fecha y hora en UTC, en formato ISO 8601.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_text(value: object) -> str:
    """Normaliza un texto sin perder la separación entre párrafos.

    Args:
        value: Valor devuelto por el modelo.

    Returns:
        str: Texto limpio, o cadena vacía si no es un texto.
    """
    if not isinstance(value, str):
        return ""

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n")]

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _require_text(value: object, label: str) -> str:
    """Exige que un campo de la respuesta traiga texto utilizable.

    Args:
        value: Valor devuelto por el modelo.
        label: Nombre del campo, para el mensaje de error.

    Returns:
        str: Texto limpio.

    Raises:
        TriptychGenerationError: Si el campo está vacío o no es un texto.
    """
    text = _clean_text(value)
    if not text:
        raise TriptychGenerationError(
            f"Falta el texto obligatorio '{label}' en la respuesta del modelo."
        )

    return text


def _clean_list(value: object) -> list[str]:
    """Normaliza una lista de textos y descarta lo que no sirva.

    Args:
        value: Valor devuelto por el modelo.

    Returns:
        list[str]: Textos limpios, sin elementos vacíos.
    """
    if not isinstance(value, list):
        return []

    return [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]


def _build_cover(raw: object) -> CoverBlock:
    """Valida el bloque de portada de la respuesta.

    Args:
        raw: Valor del campo 'cover'.

    Returns:
        CoverBlock: Portada validada.

    Raises:
        TriptychGenerationError: Si falta la portada o alguno de sus textos.
    """
    if not isinstance(raw, dict):
        raise TriptychGenerationError(
            "La respuesta no trae el bloque 'cover' de la portada."
        )

    return CoverBlock(
        hook=_require_text(raw.get("hook"), "cover.hook"),
        title=_require_text(raw.get("title"), "cover.title"),
    )


def _build_note(
    raw: object,
    index: int,
    proposal: SourceProposal,
    specs: dict[str, Any],
) -> PrintNote:
    """Valida una nota, la mide contra su presupuesto y reúne advertencias.

    Args:
        raw: Valor del elemento correspondiente en 'notes'.
        index: Posición de la nota en la lista, empezando en 0.
        proposal: Propuesta de la pauta que le da origen.
        specs: Especificaciones resueltas.

    Returns:
        PrintNote: Nota validada, medida y con sus advertencias.

    Raises:
        TriptychGenerationError: Si falta un campo obligatorio o el cuerpo es
            demasiado corto para ser una pieza publicable.
    """
    panel = index + _FIRST_NOTE_PANEL

    if not isinstance(raw, dict):
        raise TriptychGenerationError(
            f"La nota del panel {panel} no es un objeto JSON."
        )

    title = _require_text(raw.get("title"), f"notes[{index}].title")
    body = _require_text(raw.get("body"), f"notes[{index}].body")
    why_it_matters = _clean_text(raw.get("why_it_matters"))
    key_data = _clean_list(raw.get("key_data"))

    if len(body) < TRIPTYCH_NOTE_MIN_CHARS:
        raise TriptychGenerationError(
            f"El cuerpo de la nota del panel {panel} tiene {len(body)} "
            f"caracteres, por debajo del mínimo de {TRIPTYCH_NOTE_MIN_CHARS}. "
            "La respuesta no es una nota publicable."
        )

    block = "\n\n".join([title, body, why_it_matters, *key_data])
    measurement = budget_report(block, specs)
    measurement["body"] = budget_report(body, specs)

    warnings = list(style_warnings(body, specs, f"nota {panel} (cuerpo)"))
    warnings += style_warnings(
        why_it_matters, specs, f"nota {panel} (por qué importa)"
    )
    warnings += _structural_warnings(
        raw, key_data, measurement, panel, proposal, specs
    )

    return PrintNote(
        panel=panel,
        proposal_number=proposal.number,
        title=title,
        body=body,
        key_data=key_data,
        why_it_matters=why_it_matters,
        sources=list(proposal.fuentes),
        measurement=measurement,
        warnings=warnings,
    )


def _structural_warnings(
    raw: dict[str, Any],
    key_data: list[str],
    measurement: dict[str, Any],
    panel: int,
    proposal: SourceProposal,
    specs: dict[str, Any],
) -> list[str]:
    """Reúne las advertencias que no dependen del estilo de redacción.

    Args:
        raw: Nota cruda devuelta por el modelo.
        key_data: Datos clave ya normalizados.
        measurement: Medición del bloque contra su presupuesto.
        panel: Número de panel de la nota.
        proposal: Propuesta de la pauta que le da origen.
        specs: Especificaciones resueltas.

    Returns:
        list[str]: Advertencias de largo, cantidad de datos y propuesta.
    """
    warnings: list[str] = []
    expected_data = specs["layout"]["key_data_items"]

    if not measurement["within_block_max"]:
        warnings.append(
            f"nota {panel}: el bloque ocupa {measurement['columns']} columnas "
            f"y el tope es {measurement['block_max_columns']}. No se recortó: "
            "hay que ajustarlo a mano."
        )

    if len(key_data) != expected_data:
        warnings.append(
            f"nota {panel}: trae {len(key_data)} datos clave en lugar de "
            f"{expected_data}."
        )

    declared = raw.get("proposal_number")
    if isinstance(declared, int) and declared != proposal.number:
        warnings.append(
            f"nota {panel}: el modelo la marcó como propuesta {declared} y se "
            f"maquetó con la propuesta {proposal.number} de la pauta."
        )

    return warnings


def build_triptych(
    payload: dict[str, Any],
    source: TriptychSource,
    config: dict[str, Any] | None = None,
) -> TriptychPackage:
    """Valida la respuesta del modelo y arma el tríptico medido.

    Args:
        payload: Objeto JSON devuelto por el modelo.
        source: Material de origen con las propuestas de la pauta.
        config: Configuración cargada con ``load_triptych_config``, o None.

    Returns:
        TriptychPackage: Tríptico con portada, notas medidas y advertencias.

    Raises:
        TriptychGenerationError: Si el payload no cumple el contrato
            estructural del tríptico.
    """
    specs = triptych_specs(config)
    page = specs["page"]

    cover = _build_cover(payload.get("cover"))

    raw_notes = payload.get("notes")
    if not isinstance(raw_notes, list) or not raw_notes:
        raise TriptychGenerationError(
            "La respuesta no trae la lista 'notes' con las mini-notas."
        )

    expected = min(specs["layout"]["notes"], len(source.proposals))
    if len(raw_notes) != expected:
        raise TriptychGenerationError(
            f"Se esperaban {expected} notas, una por propuesta de la pauta, y "
            f"llegaron {len(raw_notes)}."
        )

    notes = [
        _build_note(raw, index, source.proposals[index], specs)
        for index, raw in enumerate(raw_notes)
    ]

    warnings: list[str] = []
    overflowing = [note for note in notes if not note.within_block_max]
    if overflowing:
        panels = ", ".join(str(note.panel) for note in overflowing)
        warnings.append(
            f"{len(overflowing)} nota(s) superan el tope de "
            f"{specs['limits']['block_max_columns']} columnas (paneles "
            f"{panels}). No se recortó nada: hay que ajustarlas a mano."
        )

    return TriptychPackage(
        cover=cover,
        notes=notes,
        fold=page["fold"],
        sides=page["sides"],
        columns_per_side=page["columns_per_side"],
        generated_at=_now_iso(),
        warnings=warnings,
    )


def generate_triptych(
    source: TriptychSource,
    config: dict[str, Any] | None,
    client: Any,
) -> TriptychPackage:
    """Genera el tríptico llamando al modelo, con reintentos.

    Reintenta la llamada cuando la respuesta no es JSON válido o no cumple el
    contrato estructural, hasta agotar ``TRIPTYCH_JSON_MAX_RETRIES``.

    Args:
        source: Material de origen con las propuestas de la pauta.
        config: Configuración cargada, o None para la default.
        client: Cliente LLM con el método ``generate_report``.

    Returns:
        TriptychPackage: Tríptico validado y medido.

    Raises:
        TriptychGenerationError: Si se agotan los intentos sin obtener un JSON
            de tríptico utilizable.
    """
    system_prompt = build_triptych_system_prompt(config)
    base_user_prompt = build_triptych_user_prompt(source, config)

    attempts = TRIPTYCH_JSON_MAX_RETRIES + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        user_prompt = base_user_prompt
        if attempt > 1:
            user_prompt += _RETRY_NOTE.format(reason=last_error)

        logger.info(
            "Solicitando el tríptico al modelo (intento %d/%d).",
            attempt,
            attempts,
        )
        raw_response = client.generate_report(system_prompt, user_prompt)

        try:
            payload = extract_json_object(raw_response)
        except JsonExtractionError as exc:
            last_error = exc
            logger.warning(
                "Intento %d sin JSON válido para el tríptico: %s", attempt, exc
            )
            continue

        try:
            return build_triptych(payload, source, config)
        except TriptychGenerationError as exc:
            last_error = exc
            logger.warning(
                "Intento %d con tríptico inválido: %s", attempt, exc
            )

    raise TriptychGenerationError(
        f"No se pudo generar el tríptico tras {attempts} intento(s). "
        f"Último error: {last_error}"
    )
