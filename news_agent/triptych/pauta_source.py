"""Material de origen del tríptico: la pauta semanal y su companion.

El tríptico no parte de un artículo publicado sino de la pauta completa. De
cada propuesta se toman el título, el enfoque, los puntos clave y las fuentes
sugeridas; y del archivo companion se toma el contenido de las noticias que la
respaldan, para que el modelo no tenga que inventar contexto.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..article_writer import PautaParseError, parse_pauta_file
from ..config import NUM_PROPOSALS, SOURCE_ARTICLE_MAX_CHARS
from ..source_references import load_companion_data

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class TriptychSourceError(Exception):
    """Excepción para errores al cargar el material de origen del tríptico."""


@dataclass
class SourceProposal:
    """Una propuesta de la pauta con el material que la respalda."""

    number: int
    title: str
    enfoque: str
    puntos: list[str] = field(default_factory=list)
    fuentes: list[str] = field(default_factory=list)
    articles: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_material(self) -> bool:
        """Indica si la propuesta tiene algo con qué redactar la nota.

        Returns:
            bool: True si hay enfoque, puntos o noticias de respaldo.
        """
        return bool(self.enfoque or self.puntos or self.articles)

    def source_context(self, max_chars: int = SOURCE_ARTICLE_MAX_CHARS) -> str:
        """Arma el bloque de contexto de la propuesta para el prompt.

        Args:
            max_chars: Máximo de caracteres de contenido por noticia fuente.

        Returns:
            str: Contexto en texto plano con enfoque, puntos y material.
        """
        blocks: list[str] = [f"TÍTULO DE LA PROPUESTA: {self.title}"]

        if self.enfoque:
            blocks.append(f"ENFOQUE EDITORIAL: {self.enfoque}")

        if self.puntos:
            bullets = "\n".join(f"- {item}" for item in self.puntos)
            blocks.append(f"PUNTOS CLAVE:\n{bullets}")

        if self.articles:
            blocks.append(
                "MATERIAL DE LAS NOTICIAS:\n"
                + "\n\n".join(
                    self._render_article(article, max_chars)
                    for article in self.articles
                )
            )

        if self.fuentes:
            bullets = "\n".join(f"- {item}" for item in self.fuentes)
            blocks.append(f"FUENTES SUGERIDAS:\n{bullets}")

        return "\n\n".join(blocks)

    @staticmethod
    def _render_article(article: dict[str, Any], max_chars: int) -> str:
        """Redacta el encabezado y el contenido recortado de una noticia.

        Args:
            article: Noticia del archivo companion.
            max_chars: Máximo de caracteres del contenido.

        Returns:
            str: Bloque de texto de la noticia.
        """
        source = article.get("source") or "Fuente desconocida"
        title = article.get("title") or "Sin título"
        content = (article.get("content") or "").strip()

        if len(content) > max_chars:
            content = content[:max_chars].rstrip() + "…"

        header = f"[{source}] {title}"

        return f"{header}\n{content}" if content else header


@dataclass
class TriptychSource:
    """Conjunto de propuestas que se van a maquetar en el tríptico."""

    pauta_path: Path
    proposals: list[SourceProposal]

    def __len__(self) -> int:
        """Cuenta las propuestas cargadas.

        Returns:
            int: Cantidad de propuestas.
        """
        return len(self.proposals)

    @property
    def titles(self) -> list[str]:
        """Lista los títulos de las propuestas cargadas.

        Returns:
            list[str]: Títulos, en orden de la pauta.
        """
        return [proposal.title for proposal in self.proposals]


def load_triptych_source(
    pauta_path: str | Path,
    notes: int = NUM_PROPOSALS,
) -> TriptychSource:
    """Carga las propuestas de la pauta y su material de respaldo.

    Args:
        pauta_path: Ruta a la pauta semanal en Markdown.
        notes: Cuántas propuestas se van a maquetar, en orden. Si es menor que
            las propuestas disponibles, se toman las primeras.

    Returns:
        TriptychSource: Propuestas seleccionadas con su companion asociado.

    Raises:
        TriptychSourceError: Si la pauta no se puede parsear o ninguna de las
            propuestas seleccionadas tiene material suficiente.
    """
    path = Path(pauta_path)

    try:
        proposals = parse_pauta_file(path)
    except PautaParseError as exc:
        raise TriptychSourceError(str(exc)) from exc

    selected = proposals[:notes] if notes > 0 else proposals

    loaded: list[SourceProposal] = []
    for proposal in selected:
        # El companion puede faltar o estar corrupto: en ese caso la nota se
        # redacta solo con el enfoque y los puntos de la pauta.
        articles = load_companion_data(path, proposal["number"]) or []
        loaded.append(
            SourceProposal(
                number=proposal["number"],
                title=proposal["title"],
                enfoque=proposal["enfoque"],
                puntos=list(proposal["puntos"]),
                fuentes=list(proposal["fuentes"]),
                articles=articles,
            )
        )

    if not any(proposal.has_material for proposal in loaded):
        raise TriptychSourceError(
            f"La pauta {path.resolve()} no tiene propuestas con material "
            "suficiente para armar un tríptico."
        )

    logger.info(
        "Material de origen cargado: %d propuesta(s) desde %s",
        len(loaded),
        path,
    )

    return TriptychSource(pauta_path=path, proposals=loaded)
