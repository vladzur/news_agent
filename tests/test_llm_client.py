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

    def test_handles_none_content_by_retrying(self, client):
        """Sin contenido visible debe reintentar la llamada, no devolver vacío."""
        empty = make_response(None)
        recovered = make_response("# Titular\n\n## Sección\n\nCuerpo.")

        with patch.object(
            client._client.chat.completions, "create", side_effect=[empty, recovered]
        ) as create:
            result = client.generate_report("sys", "usr")

        assert result.startswith("# Titular")
        assert create.call_count == 2


def make_response(content, reasoning=None):
    """Construye una respuesta simulada del SDK de OpenAI.

    Args:
        content: Contenido visible del mensaje.
        reasoning: Razonamiento interno del mensaje, si lo hay.

    Returns:
        Mock: Respuesta con una única choice y sin datos de uso.
    """
    message = Mock()
    message.content = content
    message.reasoning_content = reasoning

    choice = Mock()
    choice.message = message

    response = Mock()
    response.choices = [choice]
    response.usage = None
    return response


class TestEmptyContentRecovery:
    """Recuperación cuando el razonamiento agota el presupuesto de salida.

    Caso real que motivó estas pruebas: al escribir un artículo, el razonamiento
    interno consumió los 8192 tokens del presupuesto compartido, la respuesta
    llegó sin contenido visible y el texto de razonamiento terminó escrito en el
    archivo del artículo.
    """

    def test_retries_without_reasoning_when_content_is_empty(self, client):
        """Debe reintentar en lugar de devolver el razonamiento interno."""
        empty = make_response("", reasoning="notas internas de planificación")
        recovered = make_response("# Titular\n\n## Sección\n\nCuerpo del artículo.")

        with patch.object(
            client._client.chat.completions, "create", side_effect=[empty, recovered]
        ) as create:
            result = client.generate_report("sys", "usr")

        assert result.startswith("# Titular")
        assert create.call_count == 2

    def test_never_returns_the_internal_reasoning(self, client):
        """El razonamiento interno no debe llegar nunca al resultado."""
        response = make_response(
            "", reasoning="Let me plan the article. Facts from sources:"
        )

        with (
            patch.object(
                client._client.chat.completions, "create", return_value=response
            ),
            pytest.raises(LLMClientError, match="sin contenido visible"),
        ):
            client.generate_report("sys", "usr")

    def test_disables_thinking_on_the_retry(self, client):
        """El reintento debe desactivar el modo thinking."""
        empty = make_response("", reasoning="razonamiento extenso")
        recovered = make_response("# Titular\n\n## Sección\n\nCuerpo.")

        with patch.object(
            client._client.chat.completions, "create", side_effect=[empty, recovered]
        ) as create:
            client.generate_report("sys", "usr")

        first, second = create.call_args_list
        assert first.kwargs["extra_body"]["thinking"]["type"] == "enabled"
        assert second.kwargs["extra_body"]["thinking"]["type"] == "disabled"

    def test_widens_the_budget_on_the_retry(self, client):
        """El reintento debe reservar presupuesto suficiente para el contenido."""
        empty = make_response("", reasoning="razonamiento extenso")
        recovered = make_response("# Titular\n\n## Sección\n\nCuerpo.")

        with patch.object(
            client._client.chat.completions, "create", side_effect=[empty, recovered]
        ) as create:
            client.generate_report("sys", "usr")

        assert create.call_args_list[1].kwargs["max_tokens"] >= client.max_tokens

    def test_raises_when_both_attempts_come_back_empty(self, client):
        """Si el reintento también falla, debe lanzar un error explícito."""
        empty = make_response("", reasoning="razonamiento")

        with (
            patch.object(
                client._client.chat.completions, "create", return_value=empty
            ) as create,
            pytest.raises(LLMClientError, match="dos intentos"),
        ):
            client.generate_report("sys", "usr")

        assert create.call_count == 2

    def test_raises_when_the_retry_has_no_choices(self, client):
        """Un reintento sin choices debe fallar con un error claro."""
        empty = make_response("", reasoning="razonamiento")
        no_choices = Mock()
        no_choices.choices = []
        no_choices.usage = None

        with (
            patch.object(
                client._client.chat.completions,
                "create",
                side_effect=[empty, no_choices],
            ),
            pytest.raises(LLMClientError, match="sin choices"),
        ):
            client.generate_report("sys", "usr")

    def test_recovers_when_there_is_no_reasoning_at_all(self, client):
        """Sin razonamiento y sin contenido, igual se reintenta la llamada."""
        empty = make_response("")
        recovered = make_response("# Titular\n\n## Sección\n\nCuerpo.")

        with patch.object(
            client._client.chat.completions, "create", side_effect=[empty, recovered]
        ) as create:
            result = client.generate_report("sys", "usr")

        assert result.startswith("# Titular")
        assert create.call_count == 2
