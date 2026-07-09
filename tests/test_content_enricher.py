"""Tests para el módulo de enriquecimiento de contenido."""

from unittest.mock import Mock, patch

import pytest

from news_agent.config import MIN_SUMMARY_LENGTH
from news_agent.content_enricher import (
    ContentEnricherError,
    _fetch_article_content,
    _get_feed_min_length,
    _is_feed_enabled,
    _should_enrich,
    enrich_items,
)


# ---------------------------------------------------------------------------
# Helper para simular respuesta de requests.get
# ---------------------------------------------------------------------------


def _mock_response(text, status_code=200):
    """Construye un mock de requests.Response con .text y .raise_for_status()."""
    resp = Mock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = Mock()
    if status_code >= 400:
        from requests.exceptions import HTTPError
        resp.raise_for_status.side_effect = HTTPError(
            f"HTTP {status_code}", response=resp
        )
    return resp


# ---------------------------------------------------------------------------
# Tests de _should_enrich
# ---------------------------------------------------------------------------


class TestShouldEnrich:
    """Pruebas para la función de decisión de enriquecimiento."""

    def test_none_summary_returns_true(self):
        """Un resumen None debe gatillar enriquecimiento."""
        assert _should_enrich(None) is True

    def test_empty_summary_returns_true(self):
        """Un resumen vacío debe gatillar enriquecimiento."""
        assert _should_enrich("") is True

    def test_whitespace_only_returns_true(self):
        """Un resumen solo con espacios debe gatillar enriquecimiento."""
        assert _should_enrich("   ") is True

    def test_short_summary_returns_true(self):
        """Un resumen bajo el umbral debe gatillar enriquecimiento."""
        assert _should_enrich("Noticia breve.", MIN_SUMMARY_LENGTH) is True

    def test_long_summary_returns_false(self):
        """Un resumen sobre el umbral NO debe gatillar enriquecimiento."""
        long_text = "X" * (MIN_SUMMARY_LENGTH + 10)
        assert _should_enrich(long_text) is False

    def test_exact_threshold_returns_false(self):
        """Un resumen justo en el umbral NO debe gatillar enriquecimiento."""
        exact = "X" * MIN_SUMMARY_LENGTH
        assert _should_enrich(exact) is False

    def test_custom_threshold(self):
        """Debe respetar umbral personalizado."""
        text = "Hello World"
        assert _should_enrich(text, min_length=20) is True
        assert _should_enrich(text, min_length=5) is False

    def test_strips_whitespace_before_checking(self):
        """Debe hacer strip antes de comparar longitud."""
        text = "   Hola   "
        assert _should_enrich(text, min_length=10) is True


# ---------------------------------------------------------------------------
# Tests de _fetch_article_content
# ---------------------------------------------------------------------------


class TestFetchArticleContent:
    """Pruebas para la función de extracción de contenido."""

    def test_successful_extraction(self, monkeypatch):
        """Debe retornar el texto extraído cuando requests + trafilatura funcionan."""
        mock_html = "<html><body><p>Artículo completo de prueba.</p></body></html>"

        def mock_get(url, timeout, headers):
            return _mock_response(mock_html)

        def mock_extract(html, **kwargs):
            return "Artículo completo de prueba."

        monkeypatch.setattr(
            "news_agent.content_enricher.requests.get", mock_get
        )
        monkeypatch.setattr(
            "news_agent.content_enricher.trafilatura.extract", mock_extract
        )

        result = _fetch_article_content("https://example.com/article")

        assert result == "Artículo completo de prueba."

    def test_http_error_returns_none(self, monkeypatch):
        """Si requests.get lanza HTTPError, la función debe retornar None."""

        def mock_get(url, timeout, headers):
            return _mock_response("Not Found", status_code=404)

        monkeypatch.setattr(
            "news_agent.content_enricher.requests.get", mock_get
        )

        result = _fetch_article_content("https://example.com/article")

        assert result is None

    def test_extract_returns_none(self, monkeypatch):
        """Si extract devuelve None, la función debe retornar None."""
        mock_html = "<html>...</html>"

        def mock_get(url, timeout, headers):
            return _mock_response(mock_html)

        def mock_extract(html, **kwargs):
            return None

        monkeypatch.setattr(
            "news_agent.content_enricher.requests.get", mock_get
        )
        monkeypatch.setattr(
            "news_agent.content_enricher.trafilatura.extract", mock_extract
        )

        result = _fetch_article_content("https://example.com/article")

        assert result is None

    def test_handles_exception_gracefully(self, monkeypatch):
        """Cualquier excepción durante la extracción debe capturarse y retornar None."""

        def mock_get(url, timeout, headers):
            raise ConnectionError("Timeout simulado")

        monkeypatch.setattr(
            "news_agent.content_enricher.requests.get", mock_get
        )

        result = _fetch_article_content("https://example.com/article")

        assert result is None

    def test_strips_extracted_content(self, monkeypatch):
        """El texto extraído debe ir sin espacios al inicio ni al final."""
        mock_html = "<html>...</html>"

        def mock_get(url, timeout, headers):
            return _mock_response(mock_html)

        def mock_extract(html, **kwargs):
            return "  \n  Contenido con espacios  \n  "

        monkeypatch.setattr(
            "news_agent.content_enricher.requests.get", mock_get
        )
        monkeypatch.setattr(
            "news_agent.content_enricher.trafilatura.extract", mock_extract
        )

        result = _fetch_article_content("https://example.com/article")

        assert result == "Contenido con espacios"


# ---------------------------------------------------------------------------
# Tests de _is_feed_enabled
# ---------------------------------------------------------------------------


class TestIsFeedEnabled:
    """Pruebas para la verificación de habilitación por feed."""

    def test_none_config_uses_global_default(self):
        """Sin configuración de feed, debe usar el default global (True)."""
        assert _is_feed_enabled(None) is True

    def test_missing_enrich_key_uses_global_default(self):
        """Si el feed no tiene clave 'enrich', usa el default global."""
        assert _is_feed_enabled({"name": "Test"}) is True

    def test_explicit_enrich_false(self):
        """Si el feed tiene enrich=false, no se debe enriquecer."""
        assert _is_feed_enabled({"name": "Test", "enrich": False}) is False

    def test_explicit_enrich_true(self):
        """Si el feed tiene enrich=true, debe enriquecer."""
        assert _is_feed_enabled({"name": "Test", "enrich": True}) is True


# ---------------------------------------------------------------------------
# Tests de _get_feed_min_length
# ---------------------------------------------------------------------------


class TestGetFeedMinLength:
    """Pruebas para obtener umbral por feed."""

    def test_none_config_returns_none(self):
        """Sin configuración, retorna None (usar default global)."""
        assert _get_feed_min_length(None) is None

    def test_missing_key_returns_none(self):
        """Si no hay min_summary_length, retorna None."""
        assert _get_feed_min_length({"name": "Test"}) is None

    def test_custom_threshold(self):
        """Debe retornar el umbral configurado por feed."""
        assert _get_feed_min_length({"min_summary_length": 200}) == 200


# ---------------------------------------------------------------------------
# Tests de enrich_items
# ---------------------------------------------------------------------------


class TestEnrichItems:
    """Pruebas de integración para la función principal enrich_items."""

    @pytest.fixture
    def sample_feeds(self):
        """Configuración mínima de feeds para pruebas."""
        return [
            {"name": "La Tercera"},
            {"name": "BBC News Mundo", "enrich": True, "min_summary_length": 200},
            {"name": "Feed Deshabilitado", "enrich": False},
        ]

    @pytest.fixture
    def sample_items(self):
        """Artículos crudos de prueba."""
        return [
            {
                "title": "Noticia con buen resumen",
                "source": "La Tercera",
                "summary": "Un resumen bastante completo que describe "
                "la noticia con suficiente detalle como para no "
                "necesitar enriquecimiento adicional alguno "
                "y además incluye contexto extra que lo hace "
                "más extenso de lo normal.",
                "link": "https://example.com/1",
            },
            {
                "title": "Noticia con resumen corto",
                "source": "La Tercera",
                "summary": "Resumen breve.",
                "link": "https://example.com/2",
            },
            {
                "title": "Noticia sin link",
                "source": "BBC News Mundo",
                "summary": "Corto.",
                "link": None,
            },
            {
                "title": "Noticia en feed deshabilitado",
                "source": "Feed Deshabilitado",
                "summary": "Corto.",
                "link": "https://example.com/4",
            },
        ]

    @pytest.fixture(autouse=True)
    def _mock_cache(self, monkeypatch):
        """Deshabilita el caché en todos los tests para aislamiento."""
        monkeypatch.setattr(
            "news_agent.content_enricher._load_cache", lambda _: {}
        )
        monkeypatch.setattr(
            "news_agent.content_enricher._save_cache", lambda _p, _c: None
        )

    def test_empty_input_returns_empty(self):
        """Lista vacía debe retornar lista vacía."""
        assert enrich_items([], []) == []

    def test_preserves_original_fields(self, sample_items, sample_feeds, monkeypatch):
        """Los campos originales de cada artículo deben preservarse."""
        # Usar resumen largo para que no se intente enriquecer
        items = [dict(sample_items[0])]
        items[0]["summary"] = "X" * 300

        result = enrich_items(items, sample_feeds)

        assert len(result) == 1
        assert result[0]["title"] == items[0]["title"]
        assert result[0]["source"] == items[0]["source"]
        assert result[0]["summary"] == items[0]["summary"]
        assert result[0]["link"] == items[0]["link"]

    def test_adds_full_content_when_extraction_succeeds(
        self, sample_items, sample_feeds, monkeypatch
    ):
        """Al extraer contenido exitosamente, debe agregar 'full_content'."""
        items = [dict(sample_items[1])]

        def mock_get(url, timeout, headers):
            return _mock_response("<html>...</html>")

        def mock_extract(html, **kwargs):
            return "Contenido completo del artículo de prueba."

        monkeypatch.setattr(
            "news_agent.content_enricher.requests.get", mock_get
        )
        monkeypatch.setattr(
            "news_agent.content_enricher.trafilatura.extract", mock_extract
        )
        # Deshabilitar sleep dentro de los workers
        monkeypatch.setattr("news_agent.content_enricher.time.sleep", lambda _: None)

        result = enrich_items(items, sample_feeds)

        assert len(result) == 1
        assert result[0]["full_content"] == "Contenido completo del artículo de prueba."
        assert result[0]["summary"] == "Resumen breve."

    def test_does_not_modify_when_extraction_fails(
        self, sample_items, sample_feeds, monkeypatch
    ):
        """Si la extracción falla, el ítem se conserva sin full_content."""
        items = [dict(sample_items[1])]

        def mock_get(url, timeout, headers):
            return _mock_response("Not Found", status_code=404)

        monkeypatch.setattr(
            "news_agent.content_enricher.requests.get", mock_get
        )
        monkeypatch.setattr("news_agent.content_enricher.time.sleep", lambda _: None)

        result = enrich_items(items, sample_feeds)

        assert len(result) == 1
        assert "full_content" not in result[0]

    def test_skips_long_summaries(self, sample_items, sample_feeds, monkeypatch):
        """Artículos con resumen largo no deben ser enriquecidos."""
        items = [dict(sample_items[0])]  # Resumen largo

        fetch_called = []

        def mock_get(url, timeout, headers):
            fetch_called.append(url)
            return _mock_response("<html>...</html>")

        monkeypatch.setattr(
            "news_agent.content_enricher.requests.get", mock_get
        )

        result = enrich_items(items, sample_feeds)

        assert len(fetch_called) == 0
        assert "full_content" not in result[0]

    def test_skips_items_without_link(self, sample_items, sample_feeds, monkeypatch):
        """Artículos sin link no deben intentar enriquecerse."""
        items = [dict(sample_items[2])]  # Sin link

        fetch_called = []

        def mock_get(url, timeout, headers):
            fetch_called.append(url)
            return _mock_response("<html>...</html>")

        monkeypatch.setattr(
            "news_agent.content_enricher.requests.get", mock_get
        )
        monkeypatch.setattr("news_agent.content_enricher.time.sleep", lambda _: None)

        result = enrich_items(items, sample_feeds)

        assert len(fetch_called) == 0
        assert "full_content" not in result[0]

    def test_respects_feed_disabled(self, sample_items, sample_feeds, monkeypatch):
        """Feeds con enrich=false no deben enriquecerse."""
        items = [dict(sample_items[3])]  # Feed Deshabilitado

        fetch_called = []

        def mock_get(url, timeout, headers):
            fetch_called.append(url)
            return _mock_response("<html>...</html>")

        monkeypatch.setattr(
            "news_agent.content_enricher.requests.get", mock_get
        )

        result = enrich_items(items, sample_feeds)

        assert len(fetch_called) == 0
        assert "full_content" not in result[0]

    def test_respects_custom_threshold(self, sample_feeds, monkeypatch):
        """Debe usar el umbral configurado por feed."""
        items = [
            {
                "title": "Noticia BBC",
                "source": "BBC News Mundo",
                "summary": "X" * 180,
                "link": "https://example.com/5",
            }
        ]

        def mock_get(url, timeout, headers):
            return _mock_response("<html>...</html>")

        def mock_extract(html, **kwargs):
            return "Contenido extraído."

        monkeypatch.setattr(
            "news_agent.content_enricher.requests.get", mock_get
        )
        monkeypatch.setattr(
            "news_agent.content_enricher.trafilatura.extract", mock_extract
        )
        monkeypatch.setattr("news_agent.content_enricher.time.sleep", lambda _: None)

        result = enrich_items(items, sample_feeds)

        assert len(result) == 1
        assert result[0]["full_content"] == "Contenido extraído."

    def test_parallel_processing(self, sample_feeds, monkeypatch):
        """Debe procesar múltiples artículos y mantener el orden original."""
        items = [
            {
                "title": "Primero",
                "source": "La Tercera",
                "summary": "Corto.",
                "link": "https://example.com/1",
            },
            {
                "title": "Segundo",
                "source": "La Tercera",
                "summary": "Largo " + "X" * 200,
                "link": "https://example.com/2",
            },
            {
                "title": "Tercero",
                "source": "La Tercera",
                "summary": "Corto.",
                "link": "https://example.com/3",
            },
        ]

        def mock_get(url, timeout, headers):
            return _mock_response("<html>...</html>")

        def mock_extract(html, **kwargs):
            return "Contenido para " + html

        monkeypatch.setattr(
            "news_agent.content_enricher.requests.get", mock_get
        )
        monkeypatch.setattr(
            "news_agent.content_enricher.trafilatura.extract", mock_extract
        )
        monkeypatch.setattr("news_agent.content_enricher.time.sleep", lambda _: None)

        result = enrich_items(items, sample_feeds)

        # Debe preservar el orden original
        assert len(result) == 3
        assert result[0]["title"] == "Primero"
        assert result[1]["title"] == "Segundo"
        assert result[2]["title"] == "Tercero"
        # Primero y Tercero deben tener full_content, Segundo no
        assert "full_content" in result[0]
        assert "full_content" not in result[1]
        assert "full_content" in result[2]

    def test_partial_failure_some_succeed(self, sample_feeds, monkeypatch):
        """Si algunos enriquecimientos fallan, los exitosos deben tener full_content."""
        items = [
            {
                "title": "Éxito",
                "source": "La Tercera",
                "summary": "Corto.",
                "link": "https://example.com/ok",
            },
            {
                "title": "Fallo",
                "source": "La Tercera",
                "summary": "Corto.",
                "link": "https://example.com/fail",
            },
        ]

        def mock_get(url, timeout, headers):
            if "fail" in url:
                return _mock_response("Not Found", status_code=404)
            return _mock_response("<html>...</html>")

        def mock_extract(html, **kwargs):
            return "Contenido exitoso."

        monkeypatch.setattr(
            "news_agent.content_enricher.requests.get", mock_get
        )
        monkeypatch.setattr(
            "news_agent.content_enricher.trafilatura.extract", mock_extract
        )
        monkeypatch.setattr("news_agent.content_enricher.time.sleep", lambda _: None)

        result = enrich_items(items, sample_feeds)

        assert len(result) == 2
        assert result[0]["full_content"] == "Contenido exitoso."
        assert "full_content" not in result[1]


# ---------------------------------------------------------------------------
# Tests de ContentEnricherError
# ---------------------------------------------------------------------------


class TestContentEnricherError:
    """Pruebas para la excepción personalizada."""

    def test_error_str_representation(self):
        """La representación en string debe incluir la URL y el detalle."""
        error = ContentEnricherError("https://example.com", "Timeout")
        error_str = str(error)
        assert "https://example.com" in error_str
        assert "Timeout" in error_str

    def test_error_attributes(self):
        """Los atributos url y detail deben ser accesibles."""
        error = ContentEnricherError("https://x.com", "Error genérico")
        assert error.url == "https://x.com"
        assert error.detail == "Error genérico"
