"""Tests de la escritura del bundle del tríptico impreso.

El bundle es lo que recibe el equipo de diseño: el JSON con el contrato, el
Markdown panel por panel con el reporte de largo y el manifiesto con lo que
quedó pendiente. Estos tests fijan los tres archivos y su contenido.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from news_agent.triptych.generator import build_triptych
from news_agent.triptych.specs import triptych_specs
from news_agent.triptych.writer import (
    BUNDLE_SUFFIX,
    FOLD_LABELS,
    MANIFEST_FILE_NAME,
    MARKDOWN_FILE_NAME,
    TRIPTYCH_FILE_NAME,
    build_bundle_dir,
    date_from_pauta,
    render_triptych_markdown,
    save_manifest,
    save_markdown,
    save_triptych_json,
)

BODY = (
    "Chile firmó un acuerdo con Estados Unidos. El texto no habla solo de "
    "delincuencia. También trata de inversiones y de litio. Nadie lo votó "
    "en el Congreso. Eso preocupa a los abogados. "
) * 3


def _payload(body: str = BODY) -> dict:
    """Construye un payload válido de cinco notas.

    Args:
        body: Cuerpo que reciben todas las notas.

    Returns:
        dict: Payload equivalente al que devolvería el modelo.
    """
    return {
        "cover": {"hook": "Gancho de portada", "title": "La letra chica"},
        "notes": [
            {
                "proposal_number": number,
                "title": f"Nota {number}",
                "body": body,
                "key_data": ["Uno", "Dos", "Tres"],
                "why_it_matters": "Te afecta porque el litio es de todos.",
            }
            for number in range(1, 6)
        ],
    }


@pytest.fixture
def package(triptych_source, triptych_config):
    """Tríptico validado a partir del payload de ejemplo.

    Returns:
        TriptychPackage: Tríptico listo para escribir.
    """
    return build_triptych(_payload(), triptych_source, triptych_config)


@pytest.fixture
def species(triptych_config) -> dict:
    """Especificaciones resueltas del tríptico.

    Returns:
        dict: Especificaciones con todas sus secciones.
    """
    return triptych_specs(triptych_config)


class TestModuleContract:
    """El módulo expone lo que declara."""

    @pytest.mark.parametrize(
        "name",
        [
            "date_from_pauta",
            "build_bundle_dir",
            "save_triptych_json",
            "save_markdown",
            "render_triptych_markdown",
            "save_manifest",
        ],
    )
    def test_exposes_helper(self, name):
        import news_agent.triptych.writer as module

        assert callable(getattr(module, name))

    def test_declares_the_bundle_file_names(self):
        assert TRIPTYCH_FILE_NAME == "triptych.json"
        assert MARKDOWN_FILE_NAME == "triptych.md"
        assert MANIFEST_FILE_NAME == "manifest.json"
        assert set(FOLD_LABELS) == {"roll", "gate", "z"}


class TestDateFromPauta:
    """Fecha de la edición tomada del nombre de la pauta."""

    def test_extracts_the_stamp(self):
        pauta = Path("reportes/pauta_semanal_2026_09_24.md")

        assert date_from_pauta(pauta) == "2026_09_24"

    def test_returns_none_without_a_date(self):
        assert date_from_pauta(Path("pauta.md")) is None


class TestBuildBundleDir:
    """Carpeta del bundle."""

    def test_names_the_bundle_after_the_pauta_date(self, tmp_path):
        bundle = build_bundle_dir(
            tmp_path / "impresos",
            Path("reportes/pauta_semanal_2026_09_24.md"),
        )

        assert bundle.name == f"2026_09_24_{BUNDLE_SUFFIX}"
        assert bundle.is_dir()

    def test_creates_the_base_directory(self, tmp_path):
        base = tmp_path / "salida" / "anidada"

        build_bundle_dir(base, Path("pauta_semanal_2026_09_24.md"))

        assert base.is_dir()

    def test_reuses_an_existing_bundle(self, tmp_path):
        base = tmp_path / "impresos"
        first = build_bundle_dir(base, Path("pauta_semanal_2026_09_24.md"))
        (first / "sobrante.txt").write_text("x", encoding="utf-8")

        second = build_bundle_dir(base, Path("pauta_semanal_2026_09_24.md"))

        assert first == second
        assert (second / "sobrante.txt").exists()

    def test_falls_back_to_the_execution_date(self, tmp_path):
        moment = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)

        bundle = build_bundle_dir(
            tmp_path, Path("reportes/pauta_semanal.md"), when=moment
        )

        assert bundle.name == f"2026_01_02_{BUNDLE_SUFFIX}"


class TestSaveFiles:
    """Escritura de los archivos del bundle."""

    def test_saves_the_triptych_json(self, package, tmp_path):
        path = save_triptych_json(package, tmp_path)

        data = json.loads(path.read_text(encoding="utf-8"))

        assert path.name == TRIPTYCH_FILE_NAME
        assert data["cover"]["title"] == "La letra chica"
        assert len(data["notes"]) == 5
        assert data["notes"][0]["panel"] == 2

    def test_saves_the_markdown(self, package, tmp_path):
        path = save_markdown("# Tríptico\n", tmp_path)

        assert path.name == MARKDOWN_FILE_NAME
        assert path.read_text(encoding="utf-8") == "# Tríptico\n"


class TestRenderMarkdown:
    """Markdown panel por panel."""

    def test_includes_the_edition_header(self, package, triptych_source, species):
        markdown = render_triptych_markdown(package, triptych_source, species)

        assert "# Tríptico impreso: La letra chica" in markdown
        assert "**Edición:** 2026_09_24" in markdown
        assert "**Pliegue:** tríptico de cartera (roll fold)" in markdown
        assert "monospace 12 pt" in markdown
        assert "**Tope por nota:** 1.5 columnas" in markdown

    def test_explains_the_assembly_order(self, package, triptych_source, species):
        markdown = render_triptych_markdown(package, triptych_source, species)

        assert "## Cómo se arma" in markdown
        assert "del 2 al 6" in markdown
        assert "se confirma con la imprenta" in markdown

    def test_renders_the_cover_panel(self, package, triptych_source, species):
        markdown = render_triptych_markdown(package, triptych_source, species)

        assert "## Panel 1 — Portada" in markdown
        assert "**Gancho:** Gancho de portada" in markdown

    def test_renders_every_note_panel(self, package, triptych_source, species):
        markdown = render_triptych_markdown(package, triptych_source, species)

        assert "## Panel 2 — Nota 1" in markdown
        assert "## Panel 6 — Nota 5" in markdown

    def test_reports_the_measured_length_per_note(
        self, package, triptych_source, species
    ):
        markdown = render_triptych_markdown(package, triptych_source, species)

        assert "**Largo:** " in markdown
        assert "caracteres, " in markdown
        assert "columnas (tope 1.5 columnas)" in markdown

    def test_renders_the_blocks_of_each_note(
        self, package, triptych_source, species
    ):
        markdown = render_triptych_markdown(package, triptych_source, species)

        assert "**En 3 datos clave**" in markdown
        assert "1. Uno" in markdown
        assert "**Por qué te importa**" in markdown
        assert "**Fuentes:** Medio Uno [art. 1]" in markdown

    def test_has_no_warnings_block_when_everything_fits(
        self, package, triptych_source, species
    ):
        markdown = render_triptych_markdown(package, triptych_source, species)

        assert "Advertencias pendientes" not in markdown

    def test_lists_pending_warnings(
        self, triptych_source, triptych_config, species
    ):
        package = build_triptych(
            _payload(body="Frase corta y simple. " * 200),
            triptych_source,
            triptych_config,
        )

        markdown = render_triptych_markdown(package, triptych_source, species)

        assert "## Advertencias pendientes" in markdown
        assert "superan el tope de 1.5 columnas" in markdown
        assert "hay que ajustarlo a mano" in markdown


class TestSaveManifest:
    """Manifiesto del bundle."""

    def test_records_the_source_and_format(
        self, package, triptych_source, species, tmp_path
    ):
        path = save_manifest(package, triptych_source, tmp_path, species)

        data = json.loads(path.read_text(encoding="utf-8"))

        assert path.name == MANIFEST_FILE_NAME
        assert data["source"]["proposal_count"] == 5
        assert data["source"]["pauta_path"].endswith("pauta_semanal_2026_09_24.md")
        assert data["format"]["preset"] == "oficio"
        assert data["format"]["panels"] == 6
        assert data["format"]["fold"] == "roll"

    def test_records_the_derived_budget(
        self, package, triptych_source, species, tmp_path
    ):
        path = save_manifest(package, triptych_source, tmp_path, species)

        budget = json.loads(path.read_text(encoding="utf-8"))["budget"]

        assert budget["chars_per_line"] == 24
        assert budget["chars_per_line_block"] == 36
        assert budget["lines_per_column"] == 59
        assert budget["block_max_chars"] == 2124
        assert budget["body_target_chars"] == 700

    def test_records_every_note_with_its_measurement(
        self, package, triptych_source, species, tmp_path
    ):
        path = save_manifest(package, triptych_source, tmp_path, species)

        notes = json.loads(path.read_text(encoding="utf-8"))["notes"]

        assert len(notes) == 5
        assert notes[0]["panel"] == 2
        assert notes[0]["proposal_number"] == 1
        assert notes[0]["within_block_max"] is True
        assert notes[0]["columns"] > 0
        assert notes[0]["body_chars"] > 0

    def test_counts_the_pending_warnings(
        self, triptych_source, triptych_config, species, tmp_path
    ):
        package = build_triptych(
            _payload(body="Frase corta y simple. " * 200),
            triptych_source,
            triptych_config,
        )

        path = save_manifest(package, triptych_source, tmp_path, species)

        data = json.loads(path.read_text(encoding="utf-8"))

        assert data["totals"]["overflowing"] == 5
        assert data["totals"]["warnings"] > 0
        assert data["files"] == {
            "triptych": TRIPTYCH_FILE_NAME,
            "markdown": MARKDOWN_FILE_NAME,
        }
