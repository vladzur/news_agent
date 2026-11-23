"""Modelos de datos del subsistema de portadas editoriales.

Los artefactos que produce el subsistema —formatos, contenido y resultados—
se representan como dataclasses para que el resto de los módulos trabaje con
tipos explícitos y la serialización del manifiesto sea determinista.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CoverFormat:
    """Formato de salida de una portada.

    Attributes:
        name: Identificador del formato (``og`` o ``web``).
        width: Ancho en píxeles.
        height: Alto en píxeles.
        filename: Nombre del PNG dentro del bundle.
    """

    name: str
    width: int
    height: int
    filename: str


@dataclass
class CoverOutput:
    """Resultado del renderizado de un formato.

    Attributes:
        format: Formato al que corresponde la pieza.
        path: Ruta del PNG generado, o None si el render falló.
        error: Mensaje del fallo, vacío si la pieza se generó.
    """

    format: CoverFormat
    path: Path | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serializa la pieza para el manifiesto JSON.

        Returns:
            dict[str, Any]: Nombre, dimensiones, ruta y error del formato.
        """
        return {
            "name": self.format.name,
            "width": self.format.width,
            "height": self.format.height,
            "path": str(self.path) if self.path else None,
            "error": self.error or None,
        }


@dataclass
class CoverContent:
    """Contenido editorial que alimenta el renderizado.

    Attributes:
        title: Titular del artículo.
        category: Sección oficial del sitio.
        treatment: Tratamiento elegido (``text_first``, ``quote`` o ``data``).
        treatment_label: Nombre legible del tratamiento para el manifiesto.
        deck: Bajada o resumen breve.
        quote: Cita destacada, solo en el tratamiento ``quote``.
        figure: Cifra protagonista, solo en el tratamiento ``data``.
        caption: Leyenda que explica la cifra.
        byline: Firma del artículo.
        alt_text: Texto alternativo para accesibilidad.
        warnings: Advertencias editoriales detectadas al construir el contenido.
    """

    title: str
    category: str
    treatment: str
    treatment_label: str
    deck: str = ""
    quote: str = ""
    figure: str = ""
    caption: str = ""
    byline: str = ""
    alt_text: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class CoverPackage:
    """Resultado completo de una ejecución de portadas.

    Attributes:
        bundle_dir: Directorio del bundle generado.
        content: Contenido editorial usado en las piezas.
        outputs: Formatos renderizados, con su ruta o su error.
        metadata_path: Ruta del manifiesto JSON, o None si no se escribió.
        skipped: True si la portada ya existía y no se regeneró.
    """

    bundle_dir: Path
    content: CoverContent
    outputs: list[CoverOutput] = field(default_factory=list)
    metadata_path: Path | None = None
    skipped: bool = False
