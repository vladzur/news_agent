"""Tests para el módulo de ingesta RSS y scraping."""

import time
from unittest.mock import Mock, patch

import pytest

from news_agent.rss_fetcher import FeedFetchError, fetch_all, fetch_feed
from news_agent.scraper import ScrapingError


# ---------------------------------------------------------------------------
# Fixtures de datos simulados de feedparser
# ---------------------------------------------------------------------------

def _make_mock_entry(title, source, summary, published_parsed, link):
    """Helper para construir un dict de entrada simulada de feedparser."""
    return {
        "title": title,
        "summary": summary,
        "published_parsed": published_parsed,
        "link": link,
    }


def _make_mock_parsed(entries, bozo=0, bozo_exception=None):
    """Helper para construir un objeto simulado como el retorno de feedparser.parse."""
    parsed = Mock()
    parsed.bozo = bozo
    parsed.bozo_exception = bozo_exception
    parsed.get.return_value = entries
    return parsed


# ---------------------------------------------------------------------------
# Tests de fetch_feed
# ---------------------------------------------------------------------------

class TestFetchFeed:
    """Pruebas para fetch_feed (obtención de un único feed)."""

    def test_returns_entries_for_valid_feed(self, monkeypatch):
        """Debe devolver los artículos parseados de un feed válido."""
        now = time.gmtime()
        mock_parsed = _make_mock_parsed(
            entries=[
                _make_mock_entry("Título 1", "", "Resumen 1", now, "https://a.com/1"),
                _make_mock_entry("Título 2", "", "Resumen 2", now, "https://a.com/2"),
            ]
        )

        with patch("feedparser.parse", return_value=mock_parsed):
            result = fetch_feed("Test Feed", "https://example.com/rss")

        assert len(result) == 2
        assert result[0]["title"] == "Título 1"
        assert result[0]["source"] == "Test Feed"
        assert result[0]["summary"] == "Resumen 1"
        assert result[0]["link"] == "https://a.com/1"

    def test_returns_empty_list_when_no_entries(self, monkeypatch):
        """Debe devolver lista vacía cuando el feed no tiene entradas."""
        mock_parsed = _make_mock_parsed(entries=[])

        with patch("feedparser.parse", return_value=mock_parsed):
            result = fetch_feed("Empty Feed", "https://example.com/rss")

        assert result == []

    def test_handles_bozo_feed_with_entries(self, monkeypatch):
        """Debe intentar extraer entradas incluso si el feed tiene errores (bozo=1)."""
        now = time.gmtime()
        mock_parsed = _make_mock_parsed(
            entries=[
                _make_mock_entry("Título", "", "Resumen", now, "https://a.com/1"),
            ],
            bozo=1,
            bozo_exception=Exception("XML malformado"),
        )

        with patch("feedparser.parse", return_value=mock_parsed):
            result = fetch_feed("Bozo Feed", "https://example.com/rss")

        # Debe devolver las entradas a pesar del bozo
        assert len(result) == 1

    def test_network_error_raises_feed_fetch_error(self, monkeypatch):
        """Debe lanzar FeedFetchError cuando feedparser lanza una excepción de red."""
        with patch("feedparser.parse", side_effect=ConnectionError("Timeout")):
            with pytest.raises(FeedFetchError, match="Test Feed"):
                fetch_feed("Test Feed", "https://example.com/rss")

    def test_entry_with_missing_fields_uses_defaults(self, monkeypatch):
        """Las entradas con campos ausentes deben usar valores por defecto."""
        mock_parsed = _make_mock_parsed(
            entries=[{"title": "  Solo título  "}],
        )

        with patch("feedparser.parse", return_value=mock_parsed):
            result = fetch_feed("Min", "https://example.com/rss")

        assert result[0]["title"] == "Solo título"
        assert result[0]["summary"] is None
        assert result[0]["published_parsed"] is None
        assert result[0]["link"] is None


# ---------------------------------------------------------------------------
# Tests de fetch_all
# ---------------------------------------------------------------------------

class TestFetchAll:
    """Pruebas para fetch_all (consolidación de múltiples feeds)."""

    FEEDS = [
        {"name": "Feed A", "url": "https://a.com/rss"},
        {"name": "Feed B", "url": "https://b.com/rss"},
    ]

    def test_consolidates_items_from_all_feeds(self, monkeypatch):
        """Debe consolidar artículos de todos los feeds exitosos."""
        now = time.gmtime()

        def mock_parse(url):
            if "a.com" in url:
                return _make_mock_parsed(
                    entries=[_make_mock_entry("A1", "", "SA1", now, "https://a.com/1")],
                )
            return _make_mock_parsed(
                entries=[_make_mock_entry("B1", "", "SB1", now, "https://b.com/1")],
            )

        with patch("feedparser.parse", side_effect=mock_parse):
            result = fetch_all(self.FEEDS)

        assert len(result) == 2
        assert {r["source"] for r in result} == {"Feed A", "Feed B"}

    def test_skips_failing_feed_and_continues(self, monkeypatch):
        """Si un feed falla, debe registrarlo y continuar con el siguiente."""
        now = time.gmtime()

        def mock_parse(url):
            if "a.com" in url:
                raise ConnectionError("Servidor caído")
            return _make_mock_parsed(
                entries=[_make_mock_entry("B1", "", "SB1", now, "https://b.com/1")],
            )

        with patch("feedparser.parse", side_effect=mock_parse):
            result = fetch_all(self.FEEDS)

        # Solo debe tener los artículos del feed B
        assert len(result) == 1
        assert result[0]["source"] == "Feed B"

    def test_all_feeds_fail_returns_empty(self, monkeypatch):
        """Si todos los feeds fallan, debe devolver lista vacía sin lanzar excepción."""
        with patch("feedparser.parse", side_effect=ConnectionError("Timeout global")):
            result = fetch_all(self.FEEDS)

        assert result == []
        assert isinstance(result, list)

    def test_handles_empty_feeds_list(self):
        """Una lista de feeds vacía debe devolver lista vacía."""
        result = fetch_all([])
        assert result == []

    # -------------------------------------------------------------------
    # Tests de despacho por método (scraping vs RSS)
    # -------------------------------------------------------------------

    def test_dispatches_to_scrape_feed_when_method_scraping(self):
        """Un feed con method='scraping' debe delegar en scrape_feed."""
        feeds = [
            {"name": "Feed Scraping", "url": "https://x.com",
             "method": "scraping",
             "selectors": {"article": ".a", "title": "h2"}},
        ]

        mock_item = {
            "title": "Título scrapeado",
            "source": "Feed Scraping",
            "summary": None,
            "published_parsed": None,
            "link": "https://x.com/1",
        }

        with patch("news_agent.rss_fetcher.scrape_feed",
                   return_value=[mock_item]) as mock_scrape:
            result = fetch_all(feeds)

        assert len(result) == 1
        assert result[0]["title"] == "Título scrapeado"
        assert result[0]["source"] == "Feed Scraping"
        mock_scrape.assert_called_once_with(
            "Feed Scraping", "https://x.com", feeds[0]
        )

    def test_dispatches_to_fetch_feed_when_no_method(self):
        """Un feed sin 'method' debe usar RSS (comportamiento por defecto)."""
        now = time.gmtime()
        mock_parsed = _make_mock_parsed(
            entries=[
                _make_mock_entry("Título RSS", "", "Resumen", now, "https://a.com/1"),
            ],
        )

        feeds = [{"name": "Feed RSS", "url": "https://a.com/rss"}]

        with patch("feedparser.parse", return_value=mock_parsed):
            result = fetch_all(feeds)

        assert len(result) == 1
        assert result[0]["title"] == "Título RSS"

    def test_dispatches_to_fetch_feed_when_method_rss(self):
        """Un feed con method='rss' explícito debe usar feedparser."""
        now = time.gmtime()
        mock_parsed = _make_mock_parsed(
            entries=[
                _make_mock_entry("Título RSS", "", "Resumen", now, "https://a.com/1"),
            ],
        )

        feeds = [{"name": "Feed RSS", "url": "https://a.com/rss", "method": "rss"}]

        with patch("feedparser.parse", return_value=mock_parsed):
            result = fetch_all(feeds)

        assert len(result) == 1

    def test_handles_scrape_error_gracefully(self):
        """Si scrape_feed lanza ScrapingError, debe loguear y continuar."""
        feeds = [
            {"name": "Feed Scraping", "url": "https://x.com",
             "method": "scraping",
             "selectors": {"article": ".a", "title": "h2"}},
            {"name": "Feed RSS", "url": "https://b.com/rss"},
        ]

        now = time.gmtime()
        mock_parsed = _make_mock_parsed(
            entries=[
                _make_mock_entry("Título B", "", "Resumen B", now, "https://b.com/1"),
            ],
        )

        with patch("news_agent.rss_fetcher.scrape_feed",
                   side_effect=ScrapingError("Feed Scraping", "Timeout")):
            with patch("feedparser.parse", return_value=mock_parsed):
                result = fetch_all(feeds)

        # Debe continuar con el feed RSS después del fallo del scraping
        assert len(result) == 1
        assert result[0]["source"] == "Feed RSS"

    def test_combined_rss_and_scraping_feeds(self):
        """Debe consolidar artículos de feeds RSS y scraping en una sola lista."""
        now = time.gmtime()
        mock_parsed = _make_mock_parsed(
            entries=[
                _make_mock_entry("Título RSS", "", "R1", now, "https://a.com/1"),
            ],
        )

        mock_scraped = [
            {
                "title": "Título Scraping",
                "source": "Feed Scraping",
                "summary": "S1",
                "published_parsed": now,
                "link": "https://x.com/1",
            },
        ]

        feeds = [
            {"name": "Feed RSS", "url": "https://a.com/rss"},
            {"name": "Feed Scraping", "url": "https://x.com",
             "method": "scraping",
             "selectors": {"article": ".a", "title": "h2"}},
        ]

        with patch("feedparser.parse", return_value=mock_parsed):
            with patch("news_agent.rss_fetcher.scrape_feed",
                       return_value=mock_scraped) as mock_scrape:
                result = fetch_all(feeds)

        assert len(result) == 2
        sources = {r["source"] for r in result}
        assert sources == {"Feed RSS", "Feed Scraping"}
