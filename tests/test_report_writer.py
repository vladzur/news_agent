"""Tests para el módulo de escritura de reportes."""

import re
from pathlib import Path

import pytest

from news_agent.report_writer import (
    build_filename,
    build_header,
    save_article,
    save_report,
)


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


class TestSaveArticle:
    """Pruebas para save_article."""

    def test_saves_article_with_correct_filename(self, tmp_path):
        """Debe guardar el artículo con nombre basado en número y slug del título."""
        content = "# Título del Artículo\n\nContenido de prueba."
        file_path = save_article(content, "Título del Artículo", 1, output_dir=tmp_path)

        assert file_path.exists()
        assert file_path.name.startswith("articulo_1_")
        assert file_path.name.endswith(".md")

    def test_slug_includes_title_words(self, tmp_path):
        """El slug debe contener palabras del título."""
        content = "Contenido."
        file_path = save_article(
            content, "El Ministerio de las Comisiones", 1, output_dir=tmp_path
        )

        assert "ministerio" in file_path.name.lower()
        assert "comisiones" in file_path.name.lower()

    def test_writes_content_correctly(self, tmp_path):
        """El contenido debe escribirse correctamente en el archivo."""
        content = "# Mi Artículo\n\nDesarrollo del tema."
        file_path = save_article(content, "Mi Artículo", 2, output_dir=tmp_path)

        saved = file_path.read_text(encoding="utf-8")
        assert "Mi Artículo" in saved
        assert "Desarrollo del tema" in saved

    def test_different_article_numbers(self, tmp_path):
        """Debe generar nombres distintos para diferentes números de artículo."""
        content = "Test"
        path1 = save_article(content, "Tema Uno", 1, output_dir=tmp_path)
        path2 = save_article(content, "Tema Dos", 2, output_dir=tmp_path)

        assert "articulo_1_" in path1.name
        assert "articulo_2_" in path2.name

    def test_raises_when_dir_not_found(self):
        """Debe lanzar IOError si el directorio no existe."""
        with pytest.raises(IOError, match="no existe"):
            save_article("Test", "Título", 1, output_dir="/tmp/no_existe_dir_xyz")

    def test_handles_special_characters_in_title(self, tmp_path):
        """Debe manejar caracteres especiales en el título al generar el slug."""
        content = "Test"
        file_path = save_article(
            content,
            "¿Cómo afecta el 5% a las AFP? — Análisis crítico",
            3,
            output_dir=tmp_path,
        )

        assert file_path.exists()
        # El slug no debe tener caracteres especiales
        slug_part = file_path.name.replace("articulo_3_", "").replace(".md", "")
        assert "?" not in slug_part
        assert "%" not in slug_part
        assert "—" not in slug_part
