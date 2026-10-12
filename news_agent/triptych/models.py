"""Modelos de datos del tríptico impreso.

Definen el contrato entre la generación, la validación y la escritura: qué
debe devolver el modelo, qué se verifica en código y qué termina en disco.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CoverBlock:
    """Portada del tríptico: el gancho y el título de la edición."""

    hook: str
    title: str

    def to_dict(self) -> dict[str, Any]:
        """Serializa la portada a un diccionario.

        Returns:
            dict[str, Any]: Portada serializada.
        """
        return asdict(self)


@dataclass
class PrintNote:
    """Una mini-nota del tríptico, con su medición y sus advertencias."""

    panel: int
    proposal_number: int
    title: str
    body: str
    key_data: list[str] = field(default_factory=list)
    why_it_matters: str = ""
    sources: list[str] = field(default_factory=list)
    measurement: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def columns(self) -> float:
        """Devuelve las columnas que ocupa la nota.

        Returns:
            float: Columnas medidas.
        """
        return float(self.measurement.get("columns", 0.0))

    @property
    def within_block_max(self) -> bool:
        """Indica si la nota respeta el tope de columnas.

        Returns:
            bool: True si la nota cabe dentro del tope.
        """
        return bool(self.measurement.get("within_block_max", True))

    def to_dict(self) -> dict[str, Any]:
        """Serializa la nota a un diccionario.

        Returns:
            dict[str, Any]: Nota serializada.
        """
        return asdict(self)


@dataclass
class TriptychPackage:
    """Tríptico completo: portada, notas y referencia del pliegue."""

    cover: CoverBlock
    notes: list[PrintNote]
    fold: str
    sides: int
    columns_per_side: int
    generated_at: str
    warnings: list[str] = field(default_factory=list)

    @property
    def panels(self) -> int:
        """Cuenta los paneles disponibles del tríptico.

        Returns:
            int: Paneles del tríptico, caras por columnas.
        """
        return self.sides * self.columns_per_side

    @property
    def overflowing_notes(self) -> list[PrintNote]:
        """Devuelve las notas que superan el tope de columnas.

        Returns:
            list[PrintNote]: Notas excedidas, en orden de panel.
        """
        return [note for note in self.notes if not note.within_block_max]

    def to_dict(self) -> dict[str, Any]:
        """Serializa el tríptico a un diccionario.

        Returns:
            dict[str, Any]: Tríptico serializado.
        """
        return asdict(self)
