"""Tests para el módulo cliente de DeepSeek."""

from unittest.mock import Mock, patch

import pytest
from openai import APIError, AuthenticationError

from news_agent.llm_client import LLMClient, LLMClientError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Devuelve una instancia de LLMClient con una API key de prueba."""
    return LLMClient(api_key="sk-test-key")


@pytest.fixture
def mock_response():
    """Construye un objeto de respuesta simulado del SDK de OpenAI."""
    choice = Mock()
    choice.message.content = "# ⚡ Pauta Editorial Sugerida - La Chispa Sur\n\n..."

    usage = Mock()
    usage.prompt_tokens = 1500
    usage.completion_tokens = 800
    usage.total_tokens = 2300

    response = Mock()
    response.choices = [choice]
    response.usage = usage
    return response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLLMClientConstruction:
    """Pruebas de construcción del cliente."""

    def test_custom_values(self):
        """Debe aceptar valores personalizados."""
        client = LLMClient(
            api_key="sk-test",
            model="custom-model",
            temperature=0.8,
            max_tokens=1024,
            base_url="https://custom.api.com",
        )
        assert client.model == "custom-model"
        assert client.temperature == 0.8
        assert client.max_tokens == 1024


class TestGenerateReport:
    """Pruebas para generate_report."""

    def test_returns_content_on_success(self, client, mock_response):
        """Debe devolver el contenido de la respuesta en un caso exitoso."""
        with patch.object(client._client.chat.completions, "create", return_value=mock_response):
            result = client.generate_report(
                system_prompt="Eres un editor.",
                user_prompt="Analiza estos artículos.",
            )

        assert result == mock_response.choices[0].message.content

    def test_raises_on_authentication_error(self, client):
        """Debe lanzar LLMClientError con mensaje de autenticación."""
        with patch.object(
            client._client.chat.completions,
            "create",
            side_effect=AuthenticationError(
                "Invalid API key",
                response=Mock(),
                body=None,
            ),
        ):
            with pytest.raises(LLMClientError, match="autenticación"):
                client.generate_report("sys", "usr")

    def test_raises_on_api_error(self, client):
        """Debe lanzar LLMClientError con mensaje de API."""
        with patch.object(
            client._client.chat.completions,
            "create",
            side_effect=APIError(
                "Server error",
                request=Mock(),
                body=None,
            ),
        ):
            with pytest.raises(LLMClientError, match="API"):
                client.generate_report("sys", "usr")

    def test_raises_on_unexpected_error(self, client):
        """Debe lanzar LLMClientError para errores inesperados."""
        with patch.object(
            client._client.chat.completions,
            "create",
            side_effect=RuntimeError("Algo explotó"),
        ):
            with pytest.raises(LLMClientError, match="inesperado"):
                client.generate_report("sys", "usr")

    def test_raises_when_response_has_no_choices(self, client):
        """Debe lanzar LLMClientError si la respuesta no tiene choices."""
        bad_response = Mock()
        bad_response.choices = []
        bad_response.usage = None

        with patch.object(client._client.chat.completions, "create", return_value=bad_response):
            with pytest.raises(LLMClientError, match="sin choices"):
                client.generate_report("sys", "usr")

    def test_handles_none_content(self, client):
        """Debe devolver cadena vacía si el contenido del mensaje es None."""
        choice = Mock()
        choice.message.content = None
        response = Mock()
        response.choices = [choice]
        response.usage = None

        with patch.object(client._client.chat.completions, "create", return_value=response):
            result = client.generate_report("sys", "usr")

        assert result == ""
