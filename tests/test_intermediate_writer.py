"""Tests para el módulo de escritura de archivos intermedios."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from news_agent.intermediate_writer import save_intermediate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_items():
    """Artículos filtrados de prueba con campos de depuración."""
    return [
        {
            "title": "Noticia con contenido extraído",
            "source": "La Tercera",
            "link": "https://example.com/1",
            "summary_raw": "Resumen RSS breve.",
            "full_content": "Contenido completo del artículo extraído desde la URL.",
            "summary_clean": "Contenido completo del artículo extraído desde la URL.",
        },
        {
            "title": "Noticia sin enriquecer",
            "source": "BBC News Mundo",
            "link": "https://example.com/2",
            "summary_raw": "Un resumen RSS más largo con suficiente información.",
            "full_content": None,
            "summary_clean": "Un resumen RSS más largo con suficiente información.",
        },
    ]


# ---------------------------------------------------------------------------
# Tests de save_intermediate
# ---------------------------------------------------------------------------


class TestSaveIntermediate:
    """Pruebas para la función save_intermediate."""

    def test_creates_debug_directory(self, tmp_path, sample_items):
        """Debe crear el subdirectorio debug/ dentro del directorio de salida."""
        result_path = save_intermediate(sample_items, tmp_path)

        assert result_path.parent == tmp_path / "debug"
        assert result_path.parent.exists()

    def test_generates_correct_filename(self, tmp_path, sample_items):
        """El nombre del archivo debe incluir la fecha actual."""
        result_path = save_intermediate(sample_items, tmp_path)
        today_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
        expected_name = f"articulos_procesados_{today_str}.json"

        assert result_path.name == expected_name

    def test_save_includes_metadata(self, tmp_path, sample_items):
        """El JSON debe incluir metadata con generated_at, total y enriquecidos."""
        result_path = save_intermediate(sample_items, tmp_path)

        with open(result_path, encoding="utf-8") as fh:
            data = json.load(fh)

        assert "metadata" in data
        assert "generated_at" in data["metadata"]
        assert data["metadata"]["total_articles"] == 2
        assert data["metadata"]["enriched_articles"] == 1

    def test_save_includes_all_article_fields(self, tmp_path, sample_items):
        """Cada artículo debe incluir todos los campos esperados."""
        result_path = save_intermediate(sample_items, tmp_path)

        with open(result_path, encoding="utf-8") as fh:
            data = json.load(fh)

        article = data["articles"][0]
        assert article["title"] == "Noticia con contenido extraído"
        assert article["source"] == "La Tercera"
        assert article["link"] == "https://example.com/1"
        assert article["summary_raw"] == "Resumen RSS breve."
        assert article["full_content"] == "Contenido completo del artículo extraído desde la URL."
        assert article["summary_clean"] == "Contenido completo del artículo extraído desde la URL."
        assert article["summary_clean_length"] > 0

    def test_save_with_enriched_count_zero(self, tmp_path):
        """Cuando no hay artículos enriquecidos, enriched_articles debe ser 0."""
        items = [
            {
                "title": "Sin enriquecer",
                "source": "X",
                "summary_raw": "Resumen.",
                "full_content": None,
                "summary_clean": "Resumen.",
            }
        ]

        result_path = save_intermediate(items, tmp_path)

        with open(result_path, encoding="utf-8") as fh:
            data = json.load(fh)

        assert data["metadata"]["enriched_articles"] == 0

    def test_save_empty_list(self, tmp_path):
        """Una lista vacía debe generar JSON válido con total=0."""
        result_path = save_intermediate([], tmp_path)

        with open(result_path, encoding="utf-8") as fh:
            data = json.load(fh)

        assert data["metadata"]["total_articles"] == 0
        assert data["metadata"]["enriched_articles"] == 0
        assert data["articles"] == []

    def test_save_raises_on_nonexistent_output_dir(self):
        """Debe lanzar IOError si el directorio de salida no existe."""
        with pytest.raises(IOError):
            save_intermediate([], "/ruta/que/no/existe/")

    def test_overwrites_existing_file(self, tmp_path, sample_items):
        """Llamar dos veces debe sobrescribir el archivo sin error."""
        first_path = save_intermediate(sample_items, tmp_path)
        second_path = save_intermediate(sample_items, tmp_path)

        assert first_path == second_path
        assert second_path.exists()

    def test_json_is_valid_utf8(self, tmp_path):
        """El archivo debe ser JSON válido con codificación UTF-8."""
        items = [
            {
                "title": "Artículo con ñ y acentos",
                "source": "Fuente Épica",
                "link": "https://example.com/áéíóú",
                "summary_raw": "Reseña con caracteres especiales.",
                "full_content": None,
                "summary_clean": "Reseña con caracteres especiales.",
            }
        ]

        result_path = save_intermediate(items, tmp_path)

        with open(result_path, encoding="utf-8") as fh:
            data = json.load(fh)

        assert data["articles"][0]["title"] == "Artículo con ñ y acentos"
        assert data["articles"][0]["source"] == "Fuente Épica"
