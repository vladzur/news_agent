"""Tests de la carga del material de origen del tríptico.

El tríptico parte de la pauta completa y de su companion, no de un artículo
publicado. Estos tests fijan que el material se arme igual que para el
redactor de notas y que un companion ausente o corrupto no interrumpa el flujo.
"""

from pathlib import Path

import pytest

from news_agent.triptych.pauta_source import (
    SourceProposal,
    TriptychSource,
    TriptychSourceError,
    load_triptych_source,
)

# Pauta con las cinco propuestas pero sin enfoque, puntos ni fuentes.
EMPTY_PAUTA = (
    "# ⚡ Pauta Editorial Sugerida - La Chispa Sur\n\n"
    + "".join(f"## {number}. Titular {number}\n" for number in range(1, 6))
)


class TestModuleContract:
    """El módulo expone lo que declara."""

    @pytest.mark.parametrize(
        "name", ["load_triptych_source", "SourceProposal", "TriptychSource"]
    )
    def test_exposes_symbol(self, name):
        import news_agent.triptych.pauta_source as module

        assert hasattr(module, name)

    def test_source_error_is_an_exception(self):
        assert issubclass(TriptychSourceError, Exception)

    def test_loader_is_callable(self):
        assert callable(load_triptych_source)


class TestLoadTriptychSource:
    """Carga de las propuestas y su companion."""

    def test_loads_every_proposal(self, triptych_source):
        assert len(triptych_source) == 5
        assert triptych_source.titles == [
            f"Titular de la propuesta {number}" for number in range(1, 6)
        ]

    def test_keeps_the_pauta_path(self, triptych_source, triptych_pauta_file):
        assert triptych_source.pauta_path == triptych_pauta_file

    def test_extracts_the_proposal_material(self, triptych_source):
        first = triptych_source.proposals[0]

        assert first.number == 1
        assert first.enfoque.startswith("El acuerdo oculta compromisos")
        assert first.puntos == [
            "Arista uno de la propuesta 1",
            "Arista dos de la propuesta 1",
        ]
        assert first.fuentes == [
            "Medio Uno [art. 1]: cobertura del caso.",
            "Medio Dos [art. 101]: contexto adicional.",
        ]

    def test_loads_the_companion_articles(self, triptych_source):
        first = triptych_source.proposals[0]

        assert len(first.articles) == 1
        assert first.articles[0]["source"] == "Medio Uno"
        assert first.articles[0]["title"] == "Noticia de respaldo 1"

    def test_limits_the_notes_to_the_requested_count(self, triptych_pauta_file):
        source = load_triptych_source(triptych_pauta_file, notes=2)

        assert len(source) == 2
        assert source.titles == [
            "Titular de la propuesta 1",
            "Titular de la propuesta 2",
        ]

    def test_tolerates_a_missing_companion(self, triptych_pauta_file):
        companion = triptych_pauta_file.with_name(
            "pauta_semanal_2026_09_24_companion.json"
        )
        companion.unlink()

        source = load_triptych_source(triptych_pauta_file)

        assert len(source) == 5
        assert source.proposals[0].articles == []
        assert source.proposals[0].has_material is True

    def test_tolerates_a_corrupt_companion(self, triptych_pauta_file):
        companion = triptych_pauta_file.with_name(
            "pauta_semanal_2026_09_24_companion.json"
        )
        companion.write_text("{roto", encoding="utf-8")

        source = load_triptych_source(triptych_pauta_file)

        assert source.proposals[0].articles == []

    def test_rejects_a_pauta_that_is_not_a_pauta(self, tmp_path):
        broken = tmp_path / "pauta_semanal_2026_09_24.md"
        broken.write_text("# Otra cosa\n\n## 1. Algo\n", encoding="utf-8")

        with pytest.raises(TriptychSourceError):
            load_triptych_source(broken)

    def test_rejects_a_pauta_without_usable_material(self, tmp_path):
        reports = tmp_path / "reportes"
        reports.mkdir(parents=True, exist_ok=True)
        empty = reports / "pauta_semanal_2026_09_24.md"
        empty.write_text(EMPTY_PAUTA, encoding="utf-8")

        with pytest.raises(TriptychSourceError) as excinfo:
            load_triptych_source(empty)

        assert "material suficiente" in str(excinfo.value)


class TestSourceProposal:
    """Contexto de una propuesta para el prompt."""

    def test_has_material_with_only_the_focus(self):
        assert SourceProposal(number=1, title="T", enfoque="Algo").has_material

    def test_without_material(self):
        assert not SourceProposal(number=1, title="T", enfoque="").has_material

    def test_source_context_includes_every_block(self, triptych_source):
        context = triptych_source.proposals[0].source_context()

        assert "TÍTULO DE LA PROPUESTA: Titular de la propuesta 1" in context
        assert "ENFOQUE EDITORIAL:" in context
        assert "PUNTOS CLAVE:" in context
        assert "MATERIAL DE LAS NOTICIAS:" in context
        assert "[Medio Uno] Noticia de respaldo 1" in context
        assert "FUENTES SUGERIDAS:" in context

    def test_source_context_trims_long_content(self, triptych_source):
        context = triptych_source.proposals[0].source_context(max_chars=50)

        # El contenido se recorta al presupuesto pedido y se marca con puntos
        # suspensivos, para que el prompt no crezca sin control.
        assert "…" in context
        assert "Contenido de la noticia de respaldo. " * 10 not in context

    def test_source_context_without_articles(self):
        proposal = SourceProposal(
            number=1,
            title="Solo título",
            enfoque="",
            puntos=[],
            fuentes=[],
        )

        context = proposal.source_context()

        assert context == "TÍTULO DE LA PROPUESTA: Solo título"


class TestTriptychSource:
    """Contenedor de las propuestas seleccionadas."""

    def test_len_counts_the_proposals(self, tmp_path):
        source = TriptychSource(pauta_path=Path("p.md"), proposals=[])

        assert len(source) == 0

    def test_titles_follow_the_proposal_order(self):
        proposals = [
            SourceProposal(number=2, title="Dos", enfoque=""),
            SourceProposal(number=1, title="Uno", enfoque=""),
        ]
        source = TriptychSource(pauta_path=Path("p.md"), proposals=proposals)

        assert source.titles == ["Dos", "Uno"]
