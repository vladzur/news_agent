"""Tests para el módulo de escritura de artículos."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from news_agent.article_writer import (
    PautaParseError,
    _extract_list_items,
    _extract_section,
    parse_pauta_file,
    write_article,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_pauta_content():
    """Contenido de una pauta semanal válida con 3 propuestas."""
    return """\
# ⚡ Pauta Editorial Sugerida - La Chispa Sur
**Fecha de Generación:** 2026-07-04
**Notas Procesadas:** 200

---

## 1. Título del Primer Artículo
*   **Enfoque Editorial:** Este es el enfoque del primer artículo con análisis crítico.
*   **Puntos Clave a Desarrollar:**
    1. Primer punto clave del artículo uno.
    2. Segundo punto clave del artículo uno.
    3. Tercer punto clave con pregunta abierta.
*   **Fuentes Sugeridas para Ampliar:**
    *   Fuente A: Descripción de la fuente A.
    *   Fuente B: Descripción de la fuente B.

## 2. Título del Segundo Artículo
*   **Enfoque Editorial:** Enfoque del segundo artículo sobre otro tema relevante.
*   **Puntos Clave a Desarrollar:**
    1. Punto uno del segundo artículo.
    2. Punto dos del segundo artículo.
    3. Punto tres del segundo artículo.
*   **Fuentes Sugeridas para Ampliar:**
    *   Fuente C: Descripción de la fuente C.

## 3. Título del Tercer Artículo
*   **Enfoque Editorial:** Enfoque del tercer artículo con perspectiva internacional.
*   **Puntos Clave a Desarrollar:**
    1. Punto uno internacional.
    2. Punto dos internacional.
*   **Fuentes Sugeridas para Ampliar:**
    *   Fuente D: Descripción de la fuente D.
    *   Fuente E: Descripción de la fuente E.
"""


@pytest.fixture
def sample_pauta_file(tmp_path, sample_pauta_content):
    """Archivo de pauta temporal válido."""
    file_path = tmp_path / "pauta_semanal_2026_07_04.md"
    file_path.write_text(sample_pauta_content, encoding="utf-8")
    return file_path


# ---------------------------------------------------------------------------
# Tests de _extract_section
# ---------------------------------------------------------------------------


class TestExtractSection:
    """Pruebas para la función auxiliar _extract_section."""

    def test_extracts_between_markers(self):
        """Debe extraer texto entre dos marcadores."""
        text = "Inicio\n*   **Enfoque Editorial:** Contenido importante.\n*   **Puntos Clave:**"
        result = _extract_section(text, "Enfoque Editorial", "Puntos Clave")
        assert "Contenido importante" in result

    def test_returns_empty_when_start_not_found(self):
        """Debe devolver vacío si no encuentra el marcador de inicio."""
        text = "Sin el marcador esperado."
        result = _extract_section(text, "Marcador Inexistente", "Fin")
        assert result == ""

    def test_extracts_to_end_when_no_end_marker(self):
        """Debe extraer hasta el final si no hay marcador de fin."""
        text = "## Sección\n*   **Enfoque Editorial:** Va hasta el final del texto."
        result = _extract_section(text, "Enfoque Editorial", None)
        assert "Va hasta el final" in result


# ---------------------------------------------------------------------------
# Tests de _extract_list_items
# ---------------------------------------------------------------------------


class TestExtractListItems:
    """Pruebas para _extract_list_items."""

    def test_extracts_numbered_items(self):
        """Debe extraer items numerados."""
        text = "**Puntos Clave a Desarrollar:**\n    1. Primer punto.\n    2. Segundo punto.\n    3. Tercer punto."
        items = _extract_list_items(text, "Puntos Clave", "Fuentes")
        assert len(items) == 3
        assert items[0] == "Primer punto."

    def test_extracts_bullet_items(self):
        """Debe extraer items con bullet markdown."""
        text = "**Fuentes Sugeridas:**\n    *   Fuente 1: Descripción.\n    *   Fuente 2: Descripción."
        items = _extract_list_items(text, "Fuentes Sugeridas", None)
        assert len(items) == 2
        assert "Fuente 1" in items[0]


# ---------------------------------------------------------------------------
# Tests de parse_pauta_file
# ---------------------------------------------------------------------------


class TestParsePautaFile:
    """Pruebas para parse_pauta_file."""

    def test_parses_three_proposals(self, sample_pauta_file):
        """Debe extraer exactamente 3 propuestas de una pauta válida."""
        proposals = parse_pauta_file(sample_pauta_file)
        assert len(proposals) == 3
        assert proposals[0]["number"] == 1
        assert proposals[1]["number"] == 2
        assert proposals[2]["number"] == 3

    def test_extracts_title_correctly(self, sample_pauta_file):
        """Debe extraer el título de cada propuesta."""
        proposals = parse_pauta_file(sample_pauta_file)
        assert proposals[0]["title"] == "Título del Primer Artículo"
        assert proposals[1]["title"] == "Título del Segundo Artículo"

    def test_extracts_enfoque(self, sample_pauta_file):
        """Debe extraer el enfoque editorial."""
        proposals = parse_pauta_file(sample_pauta_file)
        assert "enfoque del primer artículo" in proposals[0]["enfoque"]

    def test_extracts_puntos_clave(self, sample_pauta_file):
        """Debe extraer los puntos clave."""
        proposals = parse_pauta_file(sample_pauta_file)
        assert len(proposals[0]["puntos"]) == 3
        assert "Primer punto clave" in proposals[0]["puntos"][0]

    def test_extracts_fuentes(self, sample_pauta_file):
        """Debe extraer las fuentes sugeridas."""
        proposals = parse_pauta_file(sample_pauta_file)
        assert len(proposals[0]["fuentes"]) == 2
        assert "Fuente A" in proposals[0]["fuentes"][0]

    def test_raises_when_file_not_found(self, tmp_path):
        """Debe lanzar PautaParseError si el archivo no existe."""
        missing = tmp_path / "no_existe.md"
        with pytest.raises(PautaParseError, match="no encontrado"):
            parse_pauta_file(missing)

    def test_raises_when_not_a_pauta_file(self, tmp_path):
        """Debe lanzar PautaParseError si falta la cabecera de pauta."""
        file_path = tmp_path / "fake.md"
        file_path.write_text("# Esto no es una pauta", encoding="utf-8")
        with pytest.raises(PautaParseError, match="cabecera"):
            parse_pauta_file(file_path)

    def test_raises_when_wrong_number_of_proposals(self, tmp_path):
        """Debe lanzar PautaParseError si no hay 3 propuestas."""
        content = """# ⚡ Pauta Editorial Sugerida - La Chispa Sur
---
## 1. Solo una propuesta
*   **Enfoque Editorial:** Algo.
"""
        file_path = tmp_path / "bad_pauta.md"
        file_path.write_text(content, encoding="utf-8")
        with pytest.raises(PautaParseError, match="3 propuestas"):
            parse_pauta_file(file_path)

    def test_handles_fewer_puntos_in_last_proposal(self, sample_pauta_file):
        """La tercera propuesta tiene solo 2 puntos — debe manejarlo bien."""
        proposals = parse_pauta_file(sample_pauta_file)
        assert len(proposals[2]["puntos"]) == 2


# ---------------------------------------------------------------------------
# Tests de write_article
# ---------------------------------------------------------------------------


class TestWriteArticle:
    """Pruebas de integración para write_article."""

    @pytest.fixture
    def mock_api_key(self, monkeypatch):
        """Establece una API key de prueba."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-article-key")

    @pytest.fixture
    def mock_article_response(self):
        """Respuesta simulada del LLM para un artículo."""
        return (
            "# Título del Primer Artículo\n\n"
            "**Por La Chispa Sur**\n"
            "**2026-07-04**\n\n"
            "---\n\n"
            "Este es el lead del artículo. Contiene aproximadamente "
            "cien palabras de introducción al tema con el tono crítico "
            "característico de La Chispa Sur.\n\n"
            "## Desarrollo\n\n"
            "Aquí va el cuerpo del artículo desarrollando los puntos clave "
            "con análisis y datos de las fuentes proporcionadas.\n\n"
            "---\n\n"
            "**Fuentes consultadas:**\n"
            "- Fuente A\n"
            "- Fuente B\n"
        )

    def test_write_article_success(
        self, mock_api_key, sample_pauta_file, tmp_path, mock_article_response
    ):
        """Debe escribir un artículo exitosamente desde una pauta."""
        with patch("news_agent.article_writer.LLMClient") as mock_client_class:
            mock_client = Mock()
            mock_client.generate_report.return_value = mock_article_response
            mock_client_class.return_value = mock_client

            result = write_article(
                pauta_path=sample_pauta_file,
                article_number=1,
                output_dir=tmp_path,
            )

        assert result["proposal_number"] == 1
        assert result["title"] == "Título del Primer Artículo"
        assert result["article_path"].exists()
        assert "articulo_1_" in result["article_path"].name

    def test_write_article_invalid_number(self, mock_api_key, sample_pauta_file):
        """Debe lanzar ValueError si el número de artículo no es 1, 2 o 3."""
        with pytest.raises(ValueError, match="inválido"):
            write_article(
                pauta_path=sample_pauta_file,
                article_number=5,
                output_dir=".",
            )

    def test_write_second_article(
        self, mock_api_key, sample_pauta_file, tmp_path, mock_article_response
    ):
        """Debe poder escribir el artículo #2."""
        with patch("news_agent.article_writer.LLMClient") as mock_client_class:
            mock_client = Mock()
            mock_client.generate_report.return_value = mock_article_response
            mock_client_class.return_value = mock_client

            result = write_article(
                pauta_path=sample_pauta_file,
                article_number=2,
                output_dir=tmp_path,
            )

        assert result["proposal_number"] == 2
        assert result["title"] == "Título del Segundo Artículo"
        assert "articulo_2_" in result["article_path"].name
