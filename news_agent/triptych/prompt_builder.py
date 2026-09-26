"""Construcción de los prompts del tríptico impreso.

Separa la identidad editorial (system prompt) de la tarea y el esquema de
salida (user prompt), igual que el resto del agente. Los números del prompt se
derivan de la configuración resuelta, de modo que el texto que se le pide al
modelo y la medición que se hace después nunca se separen.
"""

from __future__ import annotations

import logging
from typing import Any

from .pauta_source import TriptychSource
from .specs import (
    block_max_chars,
    chars_per_line,
    lines_per_column,
    triptych_specs,
)

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# Líneas de una columna que se reservan para el gancho de portada. No es un
# tope verificado: la portada no entra en el presupuesto de las notas.
_COVER_HOOK_LINES = 3

TRIPTYCH_SYSTEM_PROMPT = """\
Eres el editor de la edición impresa de {brand_name}, medio independiente de \
izquierda, crítico del modelo neoliberal, con foco territorial en Villarrica y \
La Araucanía y mirada antiimperialista desde el sur global.

Escribes para una hoja que se reparte en la calle y se lee de pie. Tu lector no \
sigue el noticiero ni lee el diario. Tu trabajo no es resumir la pauta: es \
traducirla. La misma información, contada de modo que la entienda cualquiera.

## Reglas de lenguaje (no negociables)

1. **Frases de {max_words} palabras o menos.** Una idea por frase. Si una frase \
trae dos ideas, pártela en dos. Quien se pierde no vuelve a leer.
2. **Ninguna sigla sin explicar.** La primera vez que aparece una institución, \
escribe su nombre completo y, si hace falta, la sigla entre paréntesis. Después \
ya puedes usar la sigla.
3. **Nada de jerga.** Fuera "hegemonía", "gobernanza", "corolario", \
"geopolítica", "multilateral" y "dispositivo". Si una palabra no la usa alguien \
en una conversación de almacén, busca otra.
4. **Trato directo.** Le hablas a quien lee, de tú: "te afecta", "vas a pagar", \
"tu bolsillo". No existe un lector abstracto.
5. **Cifras domésticas.** Redondea y compara: "unos 3 millones de dólares, como \
200 casas". Una cifra sola no dice nada.
6. Español neutro. Prohibidos el voseo, los modismos argentinos y el lunfardo.

## Estructura fija de cada nota

1. `body`: **qué pasó**. Los hechos en orden, sin adjetivos de más.
2. `why_it_matters`: **por qué te importa**. Qué cambia en la vida de quien lee.
3. `key_data`: **los datos que lo prueban**. {key_data_items} cifras o hechos \
concretos, tomados del material de origen.

## Reglas de fidelidad (no negociables)

1. Solo usas información del material de origen. No inventes cifras, nombres, \
cargos, fechas ni citas.
2. No conviertas hipótesis ni sospechas en afirmaciones. Si algo se investiga, \
lo dices así.
3. No atribuyas declaraciones a quien no las hizo según el material.
4. El título de cada nota puede reescribirse en lenguaje llano, pero debe \
seguir siendo reconocible como el tema de su propuesta.

## Reglas de largo

Cada nota se maqueta en una columna del tríptico y el bloque completo no puede \
pasar de una columna y media. El presupuesto exacto de caracteres se indica en \
la tarea, junto al material. Es un tope duro: si el texto no cabe, alguien \
tiene que rearmar el panel a mano, y eso no debe pasar.
"""


def build_triptych_system_prompt(config: dict[str, Any] | None = None) -> str:
    """Devuelve el system prompt del tríptico, alineado con la configuración.

    Args:
        config: Configuración cargada con ``load_triptych_config``, o None.

    Returns:
        str: System prompt completo.
    """
    specs = triptych_specs(config)
    brand = (config or {}).get("brand") or {}
    brand_name = brand.get("name") or "La Chispa Sur"

    return TRIPTYCH_SYSTEM_PROMPT.format(
        brand_name=brand_name,
        max_words=specs["style"]["max_words_per_sentence"],
        key_data_items=specs["layout"]["key_data_items"],
    )


def _render_budget(specs: dict[str, Any]) -> str:
    """Redacta el bloque de presupuesto de largo del prompt.

    Args:
        specs: Especificaciones resueltas.

    Returns:
        str: Lista de viñetas con las medidas y los topes.
    """
    page = specs["page"]
    limits = specs["limits"]
    typography = specs["typography"]
    cpl = chars_per_line(specs, 1.0)
    cpl_block = chars_per_line(specs, limits["block_max_columns"])

    return "\n".join(
        [
            (
                f"- Hoja de {page['width_mm']:.0f} x {page['height_mm']:.0f} "
                f"mm, {page['columns_per_side']} columnas por cara."
            ),
            (
                f"- Tipografía {typography['family']} de "
                f"{typography['size_pt']:.0f} pt: {cpl} caracteres por línea "
                f"y {lines_per_column(specs)} líneas por columna."
            ),
            (
                f"- El bloque de cada nota (título + cuerpo + datos + por qué "
                f"importa + fuentes) no puede pasar de "
                f"{limits['block_max_columns']} columnas: {cpl_block} "
                f"caracteres por línea y {block_max_chars(specs)} caracteres "
                "en total."
            ),
            (
                f"- Apunta a {limits['body_target_chars']} caracteres de "
                "`body`. Quedarse corto es mejor que pasarse."
            ),
        ]
    )


def _render_schema(specs: dict[str, Any], notes: int) -> str:
    """Redacta el esquema JSON que debe devolver el modelo.

    Args:
        specs: Especificaciones resueltas.
        notes: Cantidad de notas a generar.

    Returns:
        str: Esquema literal para el prompt.
    """
    hook_max = chars_per_line(specs, 1.0) * _COVER_HOOK_LINES

    return f"""\
{{
  "cover": {{
    "hook": "gancho de portada, máximo {hook_max} caracteres",
    "title": "título de la edición semanal"
  }},
  "notes": [
    {{
      "proposal_number": 1,
      "title": "título de la nota en lenguaje llano",
      "body": "qué pasó, en 2 o 3 párrafos cortos",
      "key_data": ["dato 1", "dato 2", "dato 3"],
      "why_it_matters": "por qué le importa a quien lee, 1 o 2 frases"
    }}
  ]
}}

- Exactamente {notes} notas, en el mismo orden que las propuestas de la pauta.
- `proposal_number` es el número de la propuesta, tal como aparece en el material.
- `key_data` lleva exactamente {specs["layout"]["key_data_items"]} elementos.
- Nada de campos extra y nada de texto fuera del objeto JSON."""


def build_triptych_user_prompt(
    source: TriptychSource,
    config: dict[str, Any] | None = None,
) -> str:
    """Construye el user prompt del tríptico.

    Args:
        source: Material de origen con las propuestas de la pauta.
        config: Configuración cargada con ``load_triptych_config``, o None.

    Returns:
        str: User prompt con la tarea, el presupuesto, el esquema y el material.
    """
    specs = triptych_specs(config)
    notes = min(specs["layout"]["notes"], len(source.proposals))

    material = "\n\n".join(
        f"### Propuesta {proposal.number}: {proposal.title}\n\n"
        f"{proposal.source_context()}"
        for proposal in source.proposals[:notes]
    )

    return f"""\
Vas a maquetar el tríptico impreso de la semana a partir de la pauta editorial.
Cada propuesta de la pauta se convierte en UNA mini-nota con su propio panel.

## Presupuesto de largo

{_render_budget(specs)}

## Tarea

Devuelve un objeto JSON con esta forma exacta:

{_render_schema(specs, notes)}

## Material de origen

{notes} propuestas de la pauta, con su enfoque, sus puntos clave y las noticias
que las respaldan. Redacta cada nota solo con este material.

{material}
"""
