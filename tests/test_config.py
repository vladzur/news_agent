"""Tests para el módulo de configuración."""

import json
import os
from pathlib import Path

import pytest

from news_agent.config import (
    ConfigurationError,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    MAX_TOKENS,
    REASONING_EFFORT,
    SUMMARY_MAX_CHARS,
    TEMPERATURE,
    TIME_WINDOW_HOURS,
    get_api_key,
    load_rss_feeds,
)


class TestConstants:
    """Pruebas de las constantes del módulo de configuración."""

    def test_expected_model_name(self):
        """Verifica que el modelo sea el especificado en los requisitos."""
        assert DEEPSEEK_MODEL == "deepseek-v4-pro"

    def test_expected_base_url(self):
        """Verifica que la URL base sea la especificada en los requisitos."""
        assert DEEPSEEK_BASE_URL == "https://api.deepseek.com/v1"

    def test_expected_temperature(self):
        """Verifica que la temperatura sea 0.5 según especificaciones."""
        assert TEMPERATURE == 0.5

    def test_expected_time_window(self):
        """Verifica que la ventana de tiempo sea 168 horas (7 días)."""
        assert TIME_WINDOW_HOURS == 168

    def test_expected_summary_chars(self):
        """Verifica que el truncado de resumen sea de 200 caracteres."""
        assert SUMMARY_MAX_CHARS == 200

    def test_expected_max_tokens(self):
        """Verifica que max_tokens sea 16384 para pauta semanal."""
        assert MAX_TOKENS == 16384

    def test_expected_reasoning_effort(self):
        """Verifica que el esfuerzo de razonamiento sea 'high'."""
        assert REASONING_EFFORT == "high"


class TestGetApiKey:
    """Pruebas para la función get_api_key."""

    def test_raises_when_env_var_not_set(self, monkeypatch):
        """Debe lanzar ConfigurationError si DEEPSEEK_API_KEY no existe."""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        # Aseguramos que la variable no exista
        if "DEEPSEEK_API_KEY" in os.environ:
            del os.environ["DEEPSEEK_API_KEY"]

        with pytest.raises(ConfigurationError, match="DEEPSEEK_API_KEY"):
            get_api_key()

    def test_returns_key_when_env_var_is_set(self, monkeypatch):
        """Debe devolver la clave cuando la variable de entorno está definida."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key-123")
        assert get_api_key() == "sk-test-key-123"

    def test_raises_when_key_is_empty_string(self, monkeypatch):
        """Debe lanzar ConfigurationError si la variable está vacía."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "")
        with pytest.raises(ConfigurationError, match="DEEPSEEK_API_KEY"):
            get_api_key()


class TestLoadRssFeeds:
    """Pruebas para la función load_rss_feeds."""

    def test_loads_valid_feeds_file(self, tmp_path):
        """Debe cargar correctamente un archivo JSON válido con feeds."""
        feeds = [
            {"name": "Medio Uno", "url": "https://example.com/rss"},
            {"name": "Medio Dos", "url": "https://other.com/feed.xml"},
        ]
        file_path = tmp_path / "feeds.json"
        file_path.write_text(json.dumps(feeds), encoding="utf-8")

        result = load_rss_feeds(str(file_path))
        assert result == feeds
        assert len(result) == 2

    def test_raises_when_file_not_found(self, tmp_path):
        """Debe lanzar ConfigurationError si el archivo no existe."""
        missing = tmp_path / "no_existe.json"
        with pytest.raises(ConfigurationError, match="no encontrado"):
            load_rss_feeds(str(missing))

    def test_raises_when_file_not_valid_json(self, tmp_path):
        """Debe lanzar ConfigurationError si el archivo no es JSON válido."""
        file_path = tmp_path / "bad.json"
        file_path.write_text("esto no es json{{{", encoding="utf-8")

        with pytest.raises(ConfigurationError, match="JSON válido"):
            load_rss_feeds(str(file_path))

    def test_raises_when_not_a_list(self, tmp_path):
        """Debe lanzar ConfigurationError si el contenido no es una lista."""
        file_path = tmp_path / "obj.json"
        file_path.write_text('{"name": "no soy lista"}', encoding="utf-8")

        with pytest.raises(ConfigurationError, match="lista"):
            load_rss_feeds(str(file_path))

    def test_raises_when_entry_missing_name(self, tmp_path):
        """Debe lanzar ConfigurationError si una entrada no tiene 'name'."""
        feeds = [{"url": "https://example.com/rss"}]
        file_path = tmp_path / "nofield.json"
        file_path.write_text(json.dumps(feeds), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="'name'"):
            load_rss_feeds(str(file_path))

    def test_raises_when_entry_missing_url(self, tmp_path):
        """Debe lanzar ConfigurationError si una entrada no tiene 'url'."""
        feeds = [{"name": "Medio Uno"}]
        file_path = tmp_path / "nofield.json"
        file_path.write_text(json.dumps(feeds), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="'url'"):
            load_rss_feeds(str(file_path))

    def test_raises_when_entry_not_a_dict(self, tmp_path):
        """Debe lanzar ConfigurationError si una entrada no es un dict."""
        feeds = ["soy un string, no un dict"]
        file_path = tmp_path / "badentry.json"
        file_path.write_text(json.dumps(feeds), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="no es un diccionario"):
            load_rss_feeds(str(file_path))

    def test_empty_feeds_list_is_valid(self, tmp_path):
        """Una lista vacía de feeds debe ser válida."""
        file_path = tmp_path / "empty.json"
        file_path.write_text("[]", encoding="utf-8")

        result = load_rss_feeds(str(file_path))
        assert result == []

    # -------------------------------------------------------------------
    # Tests de validación de configuración de scraping
    # -------------------------------------------------------------------

    def test_scraping_method_requires_selectors(self, tmp_path):
        """Un feed con method='scraping' sin 'selectors' debe lanzar error."""
        feeds = [
            {"name": "Medio", "url": "https://x.com", "method": "scraping"},
        ]
        file_path = tmp_path / "feeds.json"
        file_path.write_text(json.dumps(feeds), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="selectors"):
            load_rss_feeds(str(file_path))

    def test_scraping_method_requires_selectors_article(self, tmp_path):
        """Un feed scraping sin 'article' en selectors debe lanzar error."""
        feeds = [
            {
                "name": "Medio",
                "url": "https://x.com",
                "method": "scraping",
                "selectors": {"title": "h2"},
            },
        ]
        file_path = tmp_path / "feeds.json"
        file_path.write_text(json.dumps(feeds), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="'article'"):
            load_rss_feeds(str(file_path))

    def test_scraping_method_requires_selectors_title(self, tmp_path):
        """Un feed scraping sin 'title' en selectors debe lanzar error."""
        feeds = [
            {
                "name": "Medio",
                "url": "https://x.com",
                "method": "scraping",
                "selectors": {"article": ".card"},
            },
        ]
        file_path = tmp_path / "feeds.json"
        file_path.write_text(json.dumps(feeds), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="'title'"):
            load_rss_feeds(str(file_path))

    def test_scraping_method_with_valid_selectors_passes(self, tmp_path):
        """Un feed scraping con selectors válidos debe cargar sin error."""
        feeds = [
            {
                "name": "Medio",
                "url": "https://x.com",
                "method": "scraping",
                "selectors": {"article": ".card", "title": "h2"},
            },
        ]
        file_path = tmp_path / "feeds.json"
        file_path.write_text(json.dumps(feeds), encoding="utf-8")

        result = load_rss_feeds(str(file_path))
        assert len(result) == 1
        assert result[0]["method"] == "scraping"

    def test_selectors_must_be_dict_when_scraping(self, tmp_path):
        """Si 'selectors' no es un dict, debe lanzar ConfigurationError."""
        feeds = [
            {
                "name": "Medio",
                "url": "https://x.com",
                "method": "scraping",
                "selectors": "no soy un dict",
            },
        ]
        file_path = tmp_path / "feeds.json"
        file_path.write_text(json.dumps(feeds), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="diccionario"):
            load_rss_feeds(str(file_path))

    def test_unknown_method_does_not_raise(self, tmp_path):
        """Un método desconocido debe advertir pero no lanzar error."""
        feeds = [
            {
                "name": "Medio",
                "url": "https://x.com",
                "method": "metodo_futuro",
            },
        ]
        file_path = tmp_path / "feeds.json"
        file_path.write_text(json.dumps(feeds), encoding="utf-8")

        # No debe lanzar error (compatibilidad hacia adelante)
        result = load_rss_feeds(str(file_path))
        assert len(result) == 1

    def test_feed_without_method_loads_normally(self, tmp_path):
        """Un feed sin 'method' debe cargar sin error (RSS por defecto)."""
        feeds = [
            {"name": "Medio", "url": "https://x.com/rss"},
        ]
        file_path = tmp_path / "feeds.json"
        file_path.write_text(json.dumps(feeds), encoding="utf-8")

        result = load_rss_feeds(str(file_path))
        assert len(result) == 1
        # Compatibilidad hacia atrás: sin cambios en el dict retornado
        assert result[0]["name"] == "Medio"
