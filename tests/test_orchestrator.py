"""Tests para el módulo orquestador del agente."""

import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from news_agent.orchestrator import run_pipeline, setup_logging


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_api_key(monkeypatch):
    """Establece una API key de prueba en el entorno."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-mock-key")


@pytest.fixture
def feeds_file(tmp_path):
    """Crea un archivo JSON de feeds de prueba."""
    feeds = [
        {"name": "Feed Uno", "url": "https://example.com/rss"},
        {"name": "Feed Dos", "url": "https://other.com/feed.xml"},
    ]
    file_path = tmp_path / "test_feeds.json"
    file_path.write_text(json.dumps(feeds), encoding="utf-8")
    return str(file_path)


@pytest.fixture
def empty_feeds_file(tmp_path):
    """Crea un archivo JSON con una lista vacía de feeds."""
    file_path = tmp_path / "empty_feeds.json"
    file_path.write_text("[]", encoding="utf-8")
    return str(file_path)


# ---------------------------------------------------------------------------
# Tests de setup_logging
# ---------------------------------------------------------------------------

class TestSetupLogging:
    """Pruebas para la configuración de logging."""

    def test_setup_default_level(self):
        """No debe lanzar excepciones con la configuración por defecto."""
        setup_logging(verbose=False)  # No debe fallar

    def test_setup_verbose_level(self):
        """No debe lanzar excepciones en modo verbose."""
        setup_logging(verbose=True)  # No debe fallar


# ---------------------------------------------------------------------------
# Tests de run_pipeline (flujo completo simulado)
# ---------------------------------------------------------------------------

class TestRunPipeline:
    """Pruebas de integración del pipeline completo con dependencias mockeadas."""

    def _mock_raw_items(self):
        """Crea items crudos simulados como los que devuelve fetch_all."""
        import time
        from datetime import datetime, timedelta, timezone

        recent = (datetime.now(timezone.utc) - timedelta(hours=2)).timetuple()
        return [
            {
                "title": "Noticia 1",
                "source": "Feed Uno",
                "summary": "Resumen <b>HTML</b> de prueba",
                "published_parsed": recent,
                "link": "https://example.com/1",
            },
            {
                "title": "Noticia 2",
                "source": "Feed Dos",
                "summary": "Otro resumen",
                "published_parsed": recent,
                "link": "https://example.com/2",
            },
        ]

    def _mock_llm_response(self):
        """Respuesta simulada del LLM."""
        return (
            "# ⚡ Pauta Editorial Sugerida - La Chispa Sur\n"
            "**Fecha de Generación:** 2026-07-04  \n"
            "**Notas Procesadas:** 2\n\n"
            "---\n\n"
            "## 1. Título de Prueba\n"
            "*   **Enfoque Editorial:** Análisis de prueba.\n"
            "*   **Puntos Clave a Desarrollar:**\n"
            "    1. Punto 1\n"
            "    2. Punto 2\n"
            "    3. Punto 3\n\n"
            "## 2. Segundo Título\n"
            "*   **Enfoque Editorial:** Otro análisis.\n"
            "*   **Puntos Clave a Desarrollar:**\n"
            "    1. Punto A\n"
            "    2. Punto B\n"
            "    3. Punto C\n\n"
            "## 3. Tercer Título\n"
            "*   **Enfoque Editorial:** Tercer análisis.\n"
            "*   **Puntos Clave a Desarrollar:**\n"
            "    1. Punto X\n"
            "    2. Punto Y\n"
            "    3. Punto Z\n"
        )

    def test_full_pipeline_success(self, mock_api_key, feeds_file, tmp_path):
        """Debe ejecutar el pipeline completo y generar un reporte."""
        raw_items = self._mock_raw_items()
        llm_response = self._mock_llm_response()

        with patch("news_agent.orchestrator.fetch_all", return_value=raw_items):
            with patch("news_agent.orchestrator.LLMClient") as mock_client_class:
                mock_client = Mock()
                mock_client.generate_report.return_value = llm_response
                mock_client_class.return_value = mock_client

                result = run_pipeline(
                    feeds_path=feeds_file,
                    output_dir=tmp_path,
                )

        assert result["item_count"] == 2
        assert result["feed_count"] == 2
        assert result["report_path"].exists()
        assert result["report_path"].name.startswith("pauta_semanal_")

    def test_empty_feeds_exits_gracefully(self, mock_api_key, empty_feeds_file):
        """Debe salir sin error cuando no hay feeds configurados."""
        with pytest.raises(SystemExit) as exc_info:
            run_pipeline(feeds_path=empty_feeds_file)

        assert exc_info.value.code == 0

    def test_missing_api_key_exits_with_error(self, monkeypatch, feeds_file):
        """Debe salir con código 1 si no hay API key."""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        if "DEEPSEEK_API_KEY" in os.environ:
            del os.environ["DEEPSEEK_API_KEY"]

        with pytest.raises(SystemExit) as exc_info:
            run_pipeline(feeds_path=feeds_file)

        assert exc_info.value.code == 1

    def test_zero_filtered_items_skips_api_call(self, mock_api_key, feeds_file):
        """Si no hay noticias tras filtrar, no debe llamar a la API."""
        with patch("news_agent.orchestrator.fetch_all", return_value=[]):
            with patch("news_agent.orchestrator.LLMClient") as mock_client_class:
                with pytest.raises(SystemExit) as exc_info:
                    run_pipeline(feeds_path=feeds_file)

                # No debe haberse instanciado el cliente LLM
                mock_client_class.assert_not_called()
                assert exc_info.value.code == 0

    def test_llm_client_error_exits_with_error(self, mock_api_key, feeds_file, tmp_path):
        """Debe salir con código 1 si la API de DeepSeek falla."""
        raw_items = self._mock_raw_items()

        with patch("news_agent.orchestrator.fetch_all", return_value=raw_items):
            with patch("news_agent.orchestrator.LLMClient") as mock_client_class:
                mock_client = Mock()
                from news_agent.llm_client import LLMClientError

                mock_client.generate_report.side_effect = LLMClientError(
                    "Error simulado de API", original_error=Exception("API Error")
                )
                mock_client_class.return_value = mock_client

                with pytest.raises(SystemExit) as exc_info:
                    run_pipeline(feeds_path=feeds_file, output_dir=tmp_path)

                assert exc_info.value.code == 1

    def test_empty_llm_response_exits_with_error(self, mock_api_key, feeds_file, tmp_path):
        """Debe salir con código 1 si la API devuelve contenido vacío."""
        raw_items = self._mock_raw_items()

        with patch("news_agent.orchestrator.fetch_all", return_value=raw_items):
            with patch("news_agent.orchestrator.LLMClient") as mock_client_class:
                mock_client = Mock()
                mock_client.generate_report.return_value = ""
                mock_client_class.return_value = mock_client

                with pytest.raises(SystemExit) as exc_info:
                    run_pipeline(feeds_path=feeds_file, output_dir=tmp_path)

                assert exc_info.value.code == 1

    def test_all_old_items_filtered_out(self, mock_api_key, feeds_file):
        """Debe saltar la API si todos los artículos están fuera de la ventana."""
        import time

        # Crear items con fecha de hace 200 horas (fuera de la ventana de 168h)
        old_time = time.localtime(time.time() - 200 * 3600)
        old_items = [
            {
                "title": f"Old {i}",
                "source": "Old Feed",
                "summary": "Old",
                "published_parsed": old_time,
                "link": None,
            }
            for i in range(3)
        ]

        with patch("news_agent.orchestrator.fetch_all", return_value=old_items):
            with patch("news_agent.orchestrator.LLMClient") as mock_client_class:
                with pytest.raises(SystemExit) as exc_info:
                    run_pipeline(feeds_path=feeds_file)

                mock_client_class.assert_not_called()
                assert exc_info.value.code == 0

    def test_output_dir_created_if_exists(self, mock_api_key, feeds_file, tmp_path):
        """El directorio de salida debe existir (el test usa tmp_path que existe)."""
        raw_items = self._mock_raw_items()
        llm_response = self._mock_llm_response()

        with patch("news_agent.orchestrator.fetch_all", return_value=raw_items):
            with patch("news_agent.orchestrator.LLMClient") as mock_client_class:
                mock_client = Mock()
                mock_client.generate_report.return_value = llm_response
                mock_client_class.return_value = mock_client

                result = run_pipeline(feeds_path=feeds_file, output_dir=tmp_path)

        assert result["report_path"].parent == tmp_path

    # -------------------------------------------------------------------
    # Tests de enriquecimiento de contenido en el pipeline
    # -------------------------------------------------------------------

    def test_pipeline_calls_enrich_items(self, mock_api_key, feeds_file, tmp_path):
        """El pipeline debe llamar a enrich_items entre fetch_all y filter_items."""
        raw_items = self._mock_raw_items()
        llm_response = self._mock_llm_response()

        with patch("news_agent.orchestrator.fetch_all", return_value=raw_items):
            with patch(
                "news_agent.orchestrator.enrich_items"
            ) as mock_enrich:
                mock_enrich.return_value = raw_items  # Sin cambios

                with patch("news_agent.orchestrator.LLMClient") as mock_client_class:
                    mock_client = Mock()
                    mock_client.generate_report.return_value = llm_response
                    mock_client_class.return_value = mock_client

                    run_pipeline(feeds_path=feeds_file, output_dir=tmp_path)

                # enrich_items debe haberse llamado con los items y la config
                mock_enrich.assert_called_once()
                args = mock_enrich.call_args[0]
                assert args[0] == raw_items
                assert len(args[1]) == 2  # feeds config

    def test_pipeline_with_debug_flag_creates_file(
        self, mock_api_key, feeds_file, tmp_path
    ):
        """Con save_intermediate_data=True, debe guardar archivo de depuración."""
        raw_items = self._mock_raw_items()
        llm_response = self._mock_llm_response()

        with patch("news_agent.orchestrator.fetch_all", return_value=raw_items):
            with patch(
                "news_agent.orchestrator.enrich_items"
            ) as mock_enrich:
                mock_enrich.return_value = raw_items

                with patch("news_agent.orchestrator.LLMClient") as mock_client_class:
                    mock_client = Mock()
                    mock_client.generate_report.return_value = llm_response
                    mock_client_class.return_value = mock_client

                    result = run_pipeline(
                        feeds_path=feeds_file,
                        output_dir=tmp_path,
                        save_intermediate_data=True,
                    )

        # Debe incluir debug_path en el resultado
        assert result["debug_path"] is not None
        assert result["debug_path"].exists()
        assert result["debug_path"].name.startswith("articulos_procesados_")

    def test_pipeline_without_debug_flag_no_debug_file(
        self, mock_api_key, feeds_file, tmp_path
    ):
        """Sin save_intermediate_data, no debe crear archivo de depuración."""
        raw_items = self._mock_raw_items()
        llm_response = self._mock_llm_response()

        with patch("news_agent.orchestrator.fetch_all", return_value=raw_items):
            with patch(
                "news_agent.orchestrator.enrich_items"
            ) as mock_enrich:
                mock_enrich.return_value = raw_items

                with patch("news_agent.orchestrator.LLMClient") as mock_client_class:
                    mock_client = Mock()
                    mock_client.generate_report.return_value = llm_response
                    mock_client_class.return_value = mock_client

                    result = run_pipeline(
                        feeds_path=feeds_file,
                        output_dir=tmp_path,
                        save_intermediate_data=False,
                    )

        assert result["debug_path"] is None
