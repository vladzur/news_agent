"""Tests para el módulo de escritura de reportes."""

import re
from pathlib import Path

import pytest

from news_agent.report_writer import build_filename, build_header, save_report


class TestBuildFilename:
    """Pruebas para build_filename."""

    def test_filename_pattern(self):
        """Debe generar un nombre con el formato pauta_semanal_YYYY_MM_DD.md."""
        filename = build_filename()
        pattern = r"^pauta_semanal_\d{4}_\d{2}_\d{2}\.md$"
        assert re.match(pattern, filename), f"'{filename}' no coincide con {pattern}"

    def test_ends_with_md_extension(self):
        """Debe terminar con extensión .md."""
        assert build_filename().endswith(".md")

    def test_contains_current_year(self):
        """Debe contener el año actual."""
        assert "2026" in build_filename()


class TestBuildHeader:
    """Pruebas para build_header."""

    def test_contains_la_chispa_sur_title(self):
        """Debe incluir el título de La Chispa Sur."""
        header = build_header(42)
        assert "# ⚡ Pauta Editorial Sugerida - La Chispa Sur" in header

    def test_contains_item_count(self):
        """Debe incluir la cantidad de artículos procesados."""
        header = build_header(42)
        assert "**Notas Procesadas:** 42" in header

    def test_contains_today_date(self):
        """Debe incluir la fecha de generación."""
        header = build_header(10)
        assert "**Fecha de Generación:**" in header
        assert "2026" in header


class TestSaveReport:
    """Pruebas para save_report."""

    def test_saves_file_with_correct_name(self, tmp_path):
        """Debe guardar el archivo con el nombre correcto."""
        content = "# ⚡ Pauta Editorial Sugerida - La Chispa Sur\n\nContenido de prueba."
        file_path = save_report(content, 15, output_dir=tmp_path)

        assert file_path.exists()
        assert file_path.name.startswith("pauta_semanal_")
        assert file_path.name.endswith(".md")

    def test_content_is_written_to_file(self, tmp_path):
        """El contenido debe escribirse correctamente en el archivo."""
        content = "# ⚡ Pauta Editorial Sugerida\n\nTexto de prueba."
        file_path = save_report(content, 5, output_dir=tmp_path)

        saved = file_path.read_text(encoding="utf-8")
        assert "Texto de prueba" in saved

    def test_does_not_duplicate_header(self, tmp_path):
        """No debe duplicar la cabecera si el contenido ya la incluye."""
        content = "# ⚡ Pauta Editorial Sugerida - La Chispa Sur\n\nMás contenido."
        file_path = save_report(content, 10, output_dir=tmp_path)

        saved = file_path.read_text(encoding="utf-8")
        # La cabecera debe aparecer solo una vez
        assert saved.count("# ⚡ Pauta Editorial Sugerida") == 1

    def test_adds_header_when_missing(self, tmp_path):
        """Debe añadir la cabecera si el contenido no la incluye."""
        content = "## 1. Título de prueba\n\nContenido sin cabecera."
        file_path = save_report(content, 8, output_dir=tmp_path)

        saved = file_path.read_text(encoding="utf-8")
        assert saved.count("# ⚡ Pauta Editorial Sugerida") == 1
        assert "**Notas Procesadas:** 8" in saved

    def test_raises_when_output_dir_not_found(self):
        """Debe lanzar IOError si el directorio no existe."""
        content = "Test"
        with pytest.raises(IOError, match="no existe"):
            save_report(content, 1, output_dir="/tmp/no_existe_directorio_xyz_123")

    def test_file_path_is_absolute(self, tmp_path):
        """La ruta devuelta debe ser absoluta."""
        content = "Contenido"
        file_path = save_report(content, 3, output_dir=tmp_path)

        assert file_path.is_absolute()

    def test_empty_content_saves_empty_file(self, tmp_path):
        """Un contenido vacío debe guardarse sin errores."""
        file_path = save_report("", 0, output_dir=tmp_path)

        saved = file_path.read_text(encoding="utf-8")
        assert saved  # Al menos tiene la cabecera
