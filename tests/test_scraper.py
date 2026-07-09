"""Tests para el módulo de scraping web."""

from unittest.mock import Mock, patch

import pytest
import requests

from news_agent.scraper import (
    ScrapingError,
    _extract_text,
    _parse_date,
    _resolve_url,
    scrape_feed,
)


# ---------------------------------------------------------------------------
# Tests de _resolve_url
# ---------------------------------------------------------------------------


class TestResolveUrl:
    """Pruebas para la resolución de URLs relativas y absolutas."""

    def test_absolute_url_returns_unchanged(self):
        """Las URLs absolutas deben devolverse sin cambios."""
        url = "https://example.com/noticia/123"
        assert _resolve_url(url) == url
        assert _resolve_url(url, "https://otro.cl") == url

    def test_relative_url_with_prefix(self):
        """Las URLs relativas deben resolverse con el prefijo configurado."""
        assert _resolve_url("/noticias/pais", "https://www.elmostrador.cl") == (
            "https://www.elmostrador.cl/noticias/pais"
        )

    def test_relative_url_without_slash_prefix(self):
        """El prefijo sin slash final debe agregarse correctamente."""
        assert _resolve_url("noticias/pais", "https://www.elmostrador.cl") == (
            "https://www.elmostrador.cl/noticias/pais"
        )

    def test_relative_url_without_prefix_returns_as_is(self):
        """Sin prefijo, la URL relativa se devuelve tal cual."""
        assert _resolve_url("/noticias/pais") == "/noticias/pais"

    def test_empty_link_returns_empty(self):
        """Un link vacío debe devolver cadena vacía."""
        assert _resolve_url("") == ""
        assert _resolve_url("  ") == ""


# ---------------------------------------------------------------------------
# Tests de _parse_date
# ---------------------------------------------------------------------------


class TestParseDate:
    """Pruebas para el parseo de fechas desde texto."""

    def test_parse_with_valid_format(self):
        """Debe parsear una fecha con el formato especificado."""
        result = _parse_date("04/07/2026", "%d/%m/%Y")
        assert result is not None
        assert result.tm_year == 2026
        assert result.tm_mon == 7
        assert result.tm_mday == 4

    def test_parse_iso_format_fallback(self):
        """Debe parsear fechas ISO 8601 como fallback sin formato explícito."""
        result = _parse_date("2026-07-04T15:30:00")
        assert result is not None
        assert result.tm_year == 2026
        assert result.tm_mon == 7
        assert result.tm_mday == 4

    def test_parse_date_only_iso(self):
        """Debe parsear fechas ISO solo con fecha (sin hora)."""
        result = _parse_date("2026-07-04")
        assert result is not None
        assert result.tm_year == 2026
        assert result.tm_mon == 7
        assert result.tm_mday == 4

    def test_parse_y_m_d_format_from_url(self):
        """Formato año/mes/día usado en URLs de scraping."""
        result = _parse_date("2026/07/04", "%Y/%m/%d")
        assert result is not None
        assert result.tm_year == 2026
        assert result.tm_mon == 7
        assert result.tm_mday == 4

    def test_parse_invalid_date_returns_none(self):
        """Un texto no parseable debe retornar None."""
        result = _parse_date("no es una fecha", "%d/%m/%Y")
        assert result is None

    def test_parse_none_text_returns_none(self):
        """None o vacío como entrada debe retornar None."""
        assert _parse_date(None) is None
        assert _parse_date("") is None
        assert _parse_date("   ") is None

    def test_parse_without_format_returns_none_for_unusual_format(self):
        """Sin formato, formatos no estándar deben fallar (retornar None)."""
        result = _parse_date("04 de julio de 2026")
        assert result is None


# ---------------------------------------------------------------------------
# Tests de _extract_text
# ---------------------------------------------------------------------------


class TestExtractText:
    """Pruebas para la extracción de texto y atributos vía selectores CSS."""

    def test_extract_text_from_element(self):
        """Debe extraer el texto de un elemento matcheado por el selector."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup('<div><h2 class="title">Título aquí</h2></div>', "html.parser")
        result = _extract_text(soup, ".title")
        assert result == "Título aquí"

    def test_extract_attribute_href(self):
        """Debe extraer el valor de un atributo si se especifica."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(
            '<div><a class="link" href="https://example.com">Click</a></div>',
            "html.parser",
        )
        result = _extract_text(soup, ".link", attribute="href")
        assert result == "https://example.com"

    def test_extract_returns_none_when_selector_not_found(self):
        """Si el selector no matchea, debe retornar None."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<div><p>Hola</p></div>", "html.parser")
        result = _extract_text(soup, ".no-existe")
        assert result is None

    def test_extract_text_strips_whitespace(self):
        """El texto extraído debe estar limpio de espacios sobrantes."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(
            "<div><span class='txt'>   Texto con espacios   </span></div>",
            "html.parser",
        )
        result = _extract_text(soup, ".txt")
        assert result == "Texto con espacios"


# ---------------------------------------------------------------------------
# Tests de scrape_feed
# ---------------------------------------------------------------------------


class TestScrapeFeed:
    """Pruebas para scrape_feed (obtención de artículos mediante scraping)."""

    def test_handles_network_timeout(self):
        """Un timeout de red debe lanzar ScrapingError."""
        with patch("requests.get", side_effect=requests.Timeout("Timeout")):
            with pytest.raises(ScrapingError, match="Test Feed"):
                scrape_feed(
                    "Test Feed",
                    "https://example.com",
                    {"selectors": {"article": ".x", "title": "h2"}},
                )

    def test_handles_http_error(self):
        """Un error HTTP (4xx/5xx) debe lanzar ScrapingError."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")

        with patch("requests.get", return_value=mock_response):
            with pytest.raises(ScrapingError, match="Test Feed"):
                scrape_feed(
                    "Test Feed",
                    "https://example.com",
                    {"selectors": {"article": ".x", "title": "h2"}},
                )


# ---------------------------------------------------------------------------
# Tests de ScrapingError
# ---------------------------------------------------------------------------


class TestScrapingError:
    """Pruebas para la excepción personalizada ScrapingError."""

    def test_error_has_feed_name_and_detail(self):
        """La excepción debe almacenar feed_name y detail como atributos."""
        error = ScrapingError("Mi Feed", "Error de conexión")
        assert error.feed_name == "Mi Feed"
        assert error.detail == "Error de conexión"

    def test_error_string_representation(self):
        """La representación como string debe incluir el nombre del feed."""
        error = ScrapingError("Feed X", "Timeout")
        assert "Feed X" in str(error)
        assert "Timeout" in str(error)
