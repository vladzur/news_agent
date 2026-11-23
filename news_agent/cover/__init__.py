"""Subsistema de portadas editoriales para notas sin imagen.

Genera de forma determinista, con Pillow, las piezas gráficas que sustituyen
la fotografía de cabecera: una portada 16:9 para el sitio, otra 1200x630 para
``og:image`` y un manifiesto JSON con la sección, el tratamiento y el texto
alternativo que el editor necesita para publicar la nota.
"""

from .orchestrator import CoverError, run_cover

__all__ = ["CoverError", "run_cover"]
