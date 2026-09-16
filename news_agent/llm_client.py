"""Módulo cliente de la API de DeepSeek.

Gestiona la conexión con el modelo deepseek-v4-pro a través del SDK
de OpenAI en modo compatible.
"""

import logging
from typing import Any

from openai import APIError, AuthenticationError, OpenAI

from .config import (
    CONTENT_RETRY_MAX_TOKENS,
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


def _reasoning_length(message: Any) -> int:
    """Devuelve el largo del razonamiento interno de una respuesta.

    Args:
        message: Mensaje devuelto por el SDK de OpenAI.

    Returns:
        int: Cantidad de caracteres de razonamiento, o 0 si no hay.
    """
    reasoning = getattr(message, "reasoning_content", None)
    return len(reasoning) if isinstance(reasoning, str) else 0


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
        response_format: dict[str, Any] | None = None,
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
            response_format: Formato de respuesta solicitado a la API, por
                             ejemplo ``{"type": "json_object"}`` para forzar
                             JSON. Si es None, se usa texto libre (comportamiento
                             histórico). Cuando el modelo no soporta el formato
                             pedido, el cliente reintenta automáticamente sin él.
        """
        self.model = model or DEEPSEEK_MODEL
        self.temperature = temperature if temperature is not None else TEMPERATURE
        self.max_tokens = max_tokens if max_tokens is not None else PAUTA_MAX_TOKENS
        self.reasoning_effort = (
            reasoning_effort if reasoning_effort is not None else REASONING_EFFORT
        )
        self.response_format = response_format

        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url or DEEPSEEK_BASE_URL,
        )

    def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int | None = None,
        disable_reasoning: bool = False,
    ) -> Any:
        """Ejecuta la llamada cruda al endpoint de chat completions.

        Args:
            system_prompt: Prompt de sistema.
            user_prompt: Prompt de usuario.
            max_tokens: Presupuesto de salida de esta llamada. Si es None, se
                        usa el del cliente.
            disable_reasoning: Si es True, desactiva el modo thinking en esta
                               llamada, de modo que todo el presupuesto se
                               destine al contenido visible.

        Returns:
            Any: La respuesta cruda del SDK de OpenAI.
        """
        effort = None if disable_reasoning else self.reasoning_effort

        params: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "extra_body": {
                "thinking": {
                    "type": "disabled" if effort is None else "enabled",
                    "reasoning_effort": effort,
                }
            },
        }

        if self.response_format is not None:
            params["response_format"] = self.response_format

        return self._client.chat.completions.create(**params)

    def _request(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int | None = None,
        disable_reasoning: bool = False,
    ) -> Any:
        """Ejecuta la llamada gestionando errores y el respaldo de formato.

        Si se pidió un formato de respuesta que el modelo no soporta, reintenta
        una vez sin él antes de abortar: los módulos que piden JSON parsean la
        respuesta de forma defensiva, por lo que una respuesta en texto libre
        sigue siendo recuperable.

        Args:
            system_prompt: Prompt de sistema.
            user_prompt: Prompt de usuario.
            max_tokens: Presupuesto de salida de esta llamada.
            disable_reasoning: Si es True, desactiva el modo thinking.

        Returns:
            Any: La respuesta cruda del SDK de OpenAI.

        Raises:
            LLMClientError: Si la llamada falla y no hay respaldo disponible.
        """
        try:
            return self._call_api(
                system_prompt,
                user_prompt,
                max_tokens=max_tokens,
                disable_reasoning=disable_reasoning,
            )
        except AuthenticationError as exc:
            raise self._as_client_error(exc) from exc
        except APIError as exc:
            if self.response_format is None:
                raise self._as_client_error(exc) from exc

            logger.warning(
                "La API rechazó response_format=%s (%s). "
                "Se reintenta la llamada sin JSON mode.",
                self.response_format,
                exc,
            )
            self.response_format = None
            try:
                return self._call_api(system_prompt, user_prompt)
            except (AuthenticationError, APIError) as retry_exc:
                raise self._as_client_error(retry_exc) from retry_exc
        except Exception as exc:
            raise self._as_client_error(exc) from exc

    @staticmethod
    def _as_client_error(exc: Exception) -> LLMClientError:
        """Traduce una excepción del SDK a un error del cliente.

        Args:
            exc: Excepción original.

        Returns:
            LLMClientError: Error del cliente con el mensaje correspondiente.
        """
        if isinstance(exc, AuthenticationError):
            return LLMClientError(
                "Error de autenticación con la API de DeepSeek. "
                "Verifica que tu DEEPSEEK_API_KEY sea válida y no haya expirado.",
                original_error=exc,
            )
        if isinstance(exc, APIError):
            return LLMClientError(
                f"Error en la API de DeepSeek: {exc}",
                original_error=exc,
            )
        return LLMClientError(
            f"Error inesperado al comunicarse con DeepSeek: {exc}",
            original_error=exc,
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
            "max_tokens=%d, reasoning=%s, response_format=%s).",
            self.model,
            self.temperature,
            self.max_tokens,
            self.reasoning_effort,
            self.response_format,
        )

        response = self._request(system_prompt, user_prompt)

        # Extraer el contenido de la respuesta
        if not response.choices:
            raise LLMClientError(
                "La API de DeepSeek devolvió una respuesta sin choices."
            )

        message = response.choices[0].message
        content = (message.content or "").strip()

        if not content:
            # El razonamiento interno NO es un resultado publicable: usarlo como
            # respaldo terminó escribiendo las notas de planificación del modelo
            # dentro del archivo del artículo. Se reintenta sin razonamiento y,
            # si tampoco hay contenido, se falla de forma explícita.
            content = self._recover_empty_content(
                system_prompt,
                user_prompt,
                reasoning_length=_reasoning_length(message),
            )

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

    def _recover_empty_content(
        self,
        system_prompt: str,
        user_prompt: str,
        reasoning_length: int,
    ) -> str:
        """Recupera la respuesta cuando llegó sin contenido visible.

        En modo thinking, ``max_tokens`` es un presupuesto compartido entre el
        razonamiento y la respuesta final: si el modelo agota el presupuesto
        pensando, la respuesta llega vacía. El reintento desactiva el
        razonamiento y amplía el presupuesto, de modo que todos los tokens
        disponibles se destinen al contenido.

        Args:
            system_prompt: Prompt de sistema.
            user_prompt: Prompt de usuario.
            reasoning_length: Caracteres de razonamiento de la primera respuesta.

        Returns:
            str: Contenido visible de la respuesta recuperada.

        Raises:
            LLMClientError: Si el reintento tampoco devuelve contenido visible.
        """
        logger.warning(
            "La respuesta llegó sin contenido visible (razonamiento: %d "
            "caracteres, presupuesto: %d tokens). Se reintenta sin razonamiento.",
            reasoning_length,
            self.max_tokens,
        )

        retry_response = self._request(
            system_prompt,
            user_prompt,
            max_tokens=max(self.max_tokens, CONTENT_RETRY_MAX_TOKENS),
            disable_reasoning=True,
        )

        if not retry_response.choices:
            raise LLMClientError(
                "La API de DeepSeek devolvió una respuesta sin choices en el "
                "reintento sin razonamiento."
            )

        recovered = (retry_response.choices[0].message.content or "").strip()
        if not recovered:
            raise LLMClientError(
                "La API devolvió una respuesta sin contenido visible en dos "
                "intentos (con y sin razonamiento). El razonamiento interno se "
                "descarta como resultado porque no es publicable."
            )

        logger.info(
            "Reintento sin razonamiento exitoso: %d caracteres de contenido.",
            len(recovered),
        )
        return recovered
