"""Módulo cliente de la API de DeepSeek.

Gestiona la conexión con el modelo deepseek-v4-pro a través del SDK
de OpenAI en modo compatible.
"""

import logging
from typing import Any

from openai import APIError, AuthenticationError, OpenAI

from .config import (
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    PAUTA_MAX_TOKENS,
    REASONING_EFFORT,
    TEMPERATURE,
)

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """Excepción personalizada para errores en la comunicación con el LLM."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class LLMClient:
    """Cliente para interactuar con la API de DeepSeek vía SDK de OpenAI.

    Attributes:
        model: Identificador del modelo a utilizar.
        temperature: Temperatura de sampling (0.0 - 2.0).
        max_tokens: Máximo de tokens en la respuesta.
    """

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        base_url: str | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        """Inicializa el cliente de DeepSeek.

        Args:
            api_key: Clave API de DeepSeek.
            model: Modelo a usar. Por defecto DEEPSEEK_MODEL.
            temperature: Temperatura de sampling. Por defecto TEMPERATURE (0.5).
            max_tokens: Límite de tokens de salida. Por defecto PAUTA_MAX_TOKENS (16384).
            base_url: URL base de la API. Por defecto DEEPSEEK_BASE_URL.
            reasoning_effort: Esfuerzo de razonamiento ("high", "max", o None).
                              Por defecto REASONING_EFFORT ("high").
        """
        self.model = model or DEEPSEEK_MODEL
        self.temperature = temperature if temperature is not None else TEMPERATURE
        self.max_tokens = max_tokens if max_tokens is not None else PAUTA_MAX_TOKENS
        self.reasoning_effort = (
            reasoning_effort if reasoning_effort is not None else REASONING_EFFORT
        )

        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url or DEEPSEEK_BASE_URL,
        )

    def generate_report(self, system_prompt: str, user_prompt: str) -> str:
        """Envía los prompts al modelo y devuelve la respuesta generada.

        Args:
            system_prompt: Prompt de sistema con la identidad editorial.
            user_prompt: Prompt de usuario con los artículos a analizar.

        Returns:
            str: Texto de la pauta editorial generada por el modelo.

        Raises:
            LLMClientError: Si ocurre un error de autenticación, conexión
                            o cualquier error de la API.
        """
        logger.info(
            "Enviando solicitud a DeepSeek API (modelo=%s, temperature=%.1f, "
            "max_tokens=%d, reasoning=%s).",
            self.model,
            self.temperature,
            self.max_tokens,
            self.reasoning_effort,
        )

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                extra_body={
                    "thinking": {
                        "type": "disabled" if self.reasoning_effort is None else "enabled",
                        "reasoning_effort": self.reasoning_effort,
                    }
                },
            )
        except AuthenticationError as exc:
            raise LLMClientError(
                "Error de autenticación con la API de DeepSeek. "
                "Verifica que tu DEEPSEEK_API_KEY sea válida y no haya expirado.",
                original_error=exc,
            ) from exc
        except APIError as exc:
            raise LLMClientError(
                f"Error en la API de DeepSeek: {exc}",
                original_error=exc,
            ) from exc
        except Exception as exc:
            raise LLMClientError(
                f"Error inesperado al comunicarse con DeepSeek: {exc}",
                original_error=exc,
            ) from exc

        # Extraer el contenido de la respuesta
        if not response.choices:
            raise LLMClientError(
                "La API de DeepSeek devolvió una respuesta sin choices."
            )

        message = response.choices[0].message
        content: str = message.content or ""

        # Fallback: en modo thinking, el modelo puede consumir todos los tokens
        # de salida en reasoning_content y dejar content vacío. En ese caso,
        # usamos reasoning_content como último recurso.
        if not content.strip():
            reasoning = getattr(message, "reasoning_content", None)
            if reasoning and isinstance(reasoning, str) and reasoning.strip():
                logger.warning(
                    "Content vacío — usando reasoning_content como fallback "
                    "(%d caracteres de razonamiento).",
                    len(reasoning),
                )
                content = reasoning

        # Registrar estadísticas de uso
        usage: Any = response.usage
        if usage:
            logger.info(
                "Respuesta recibida: %d tokens de entrada, %d tokens de salida, "
                "%d tokens totales.",
                usage.prompt_tokens or 0,
                usage.completion_tokens or 0,
                usage.total_tokens or 0,
            )
        else:
            logger.info("Respuesta recibida (sin datos de uso disponibles).")

        return content
