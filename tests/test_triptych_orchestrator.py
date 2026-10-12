"""Tests del orquestador del tríptico impreso.

El flujo no tiene etapas tolerantes: si el modelo no devuelve un tríptico que
cumpla el contrato estructural, no se escribe nada. Estos tests fijan ese
comportamiento, el resumen que recibe el CLI y las guardas de configuración.
"""

import json
from typing import Any

import pytest

from news_agent.config import ConfigurationError
from news_agent.llm_client import LLMClientError
from news_agent.triptych import orchestrator
from news_agent.triptych.orchestrator import TriptychError, run_print

BODY = (
    "Chile firmó un acuerdo con Estados Unidos. El texto no habla solo de "
    "delincuencia. También trata de inversiones y de litio. Nadie lo votó "
    "en el Congreso. Eso preocupa a los abogados. "
) * 3


class _FakeClient:
    """Cliente LLM falso que responde siempre el mismo texto."""

    def __init__(self, response: str):
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate_report(self, system_prompt: str, user_prompt: str) -> str:
        """Devuelve la respuesta fija y registra la llamada.

        Args:
            system_prompt: Identidad editorial del prompt.
            user_prompt: Tarea enviada al modelo.

        Returns:
            str: Respuesta fija.
        """
        self.calls.append((system_prompt, user_prompt))
        return self.response


def _payload(body: str = BODY) -> dict:
    """Construye un payload válido de cinco notas.

    Args:
        body: Cuerpo que reciben todas las notas.

    Returns:
        dict: Payload equivalente al que devolvería el modelo.
    """
    return {
        "cover": {"hook": "Gancho de portada", "title": "La letra chica"},
        "notes": [
            {
                "proposal_number": number,
                "title": f"Nota {number}",
                "body": body,
                "key_data": ["Uno", "Dos", "Tres"],
                "why_it_matters": "Te afecta porque el litio es de todos.",
            }
            for number in range(1, 6)
        ],
    }


class _Installed:
    """Estado del cliente falso instalado en el orquestador."""

    def __init__(self) -> None:
        self.client = _FakeClient("")
        self.kwargs: dict[str, Any] = {}


@pytest.fixture
def installed(monkeypatch, triptych_payload) -> _Installed:
    """Instala un cliente falso y una API key simulada.

    Args:
        monkeypatch: Fixture de pytest para reemplazar atributos.
        triptych_payload: Payload de ejemplo del modelo.

    Returns:
        _Installed: Estado con el cliente y los argumentos capturados.
    """
    state = _Installed()
    state.client = _FakeClient(json.dumps(triptych_payload, ensure_ascii=False))

    def _factory(**kwargs: Any) -> _FakeClient:
        state.kwargs.update(kwargs)
        return state.client

    monkeypatch.setattr(orchestrator, "LLMClient", _factory)
    monkeypatch.setattr(orchestrator, "get_api_key", lambda: "clave-de-prueba")

    return state


class TestModuleContract:
    """El módulo expone lo que declara."""

    def test_exposes_the_entry_point(self):
        assert callable(run_print)

    def test_triptych_error_is_an_exception(self):
        assert issubclass(TriptychError, Exception)


class TestRunPrint:
    """Flujo completo con un modelo simulado."""

    def test_writes_the_bundle(
        self, installed, triptych_pauta_file, triptych_config_file, tmp_path
    ):
        result = run_print(
            pauta_path=triptych_pauta_file,
            output_dir=tmp_path / "impresos",
            config_path=triptych_config_file,
        )

        bundle = result["bundle_dir"]
        assert bundle.name == "2026_09_24_pauta-semanal"
        assert (bundle / "triptych.json").is_file()
        assert (bundle / "triptych.md").is_file()
        assert (bundle / "manifest.json").is_file()

    def test_returns_a_summary_for_the_cli(
        self,
        installed,
        triptych_pauta_file,
        triptych_config_file,
        triptych_payload,
        tmp_path,
    ):
        result = run_print(
            pauta_path=triptych_pauta_file,
            output_dir=tmp_path,
            config_path=triptych_config_file,
        )

        assert result["title"] == triptych_payload["cover"]["title"]
        assert result["notes"] == 5
        assert result["panels"] == 6
        assert result["fold"] == "roll"
        assert result["overflowing"] == 0
        assert result["warnings"] == 0
        assert result["triptych_path"].is_file()
        assert result["markdown_path"].is_file()
        assert result["manifest_path"].is_file()

    def test_defaults_the_output_directory_to_impresos(
        self,
        installed,
        triptych_pauta_file,
        triptych_config_file,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)

        result = run_print(
            pauta_path=triptych_pauta_file,
            config_path=triptych_config_file,
        )

        assert result["bundle_dir"].parent.name == "impresos"

    def test_configures_the_client_with_the_triptych_budget(
        self, installed, triptych_pauta_file, triptych_config_file, tmp_path
    ):
        run_print(
            pauta_path=triptych_pauta_file,
            output_dir=tmp_path,
            config_path=triptych_config_file,
        )

        assert installed.kwargs["max_tokens"] == orchestrator.TRIPTYCH_MAX_TOKENS
        assert (
            installed.kwargs["reasoning_effort"]
            == orchestrator.TRIPTYCH_REASONING_EFFORT
        )
        assert installed.kwargs["temperature"] == orchestrator.TRIPTYCH_TEMPERATURE
        assert installed.kwargs["response_format"] == {"type": "json_object"}

    def test_sends_the_pauta_material_to_the_model(
        self, installed, triptych_pauta_file, triptych_config_file, tmp_path
    ):
        run_print(
            pauta_path=triptych_pauta_file,
            output_dir=tmp_path,
            config_path=triptych_config_file,
        )

        _, user_prompt = installed.client.calls[0]
        assert "Titular de la propuesta 1" in user_prompt
        assert "Noticia de respaldo 1" in user_prompt

    def test_counts_the_notes_that_overflow(
        self,
        monkeypatch,
        triptych_pauta_file,
        triptych_config_file,
        tmp_path,
    ):
        client = _FakeClient(json.dumps(_payload("Frase corta. " * 200)))
        monkeypatch.setattr(orchestrator, "LLMClient", lambda **_: client)
        monkeypatch.setattr(orchestrator, "get_api_key", lambda: "clave")

        result = run_print(
            pauta_path=triptych_pauta_file,
            output_dir=tmp_path,
            config_path=triptych_config_file,
        )

        assert result["overflowing"] == 5
        assert result["warnings"] > 0


class TestFatals:
    """Guardas que abortan el flujo."""

    def test_invalid_configuration_exits(
        self, installed, triptych_pauta_file, tmp_path
    ):
        with pytest.raises(SystemExit):
            run_print(
                pauta_path=triptych_pauta_file,
                output_dir=tmp_path,
                config_path=tmp_path / "no-existe.json",
            )

    def test_missing_api_key_exits(
        self, monkeypatch, triptych_pauta_file, triptych_config_file, tmp_path
    ):
        def _raise() -> str:
            raise ConfigurationError("falta DEEPSEEK_API_KEY")

        monkeypatch.setattr(orchestrator, "get_api_key", _raise)

        with pytest.raises(SystemExit):
            run_print(
                pauta_path=triptych_pauta_file,
                output_dir=tmp_path,
                config_path=triptych_config_file,
            )

    def test_unreadable_pauta_exits(
        self, installed, triptych_config_file, tmp_path
    ):
        broken = tmp_path / "pauta_semanal_2026_09_24.md"
        broken.write_text("# Otra cosa\n", encoding="utf-8")

        with pytest.raises(SystemExit):
            run_print(
                pauta_path=broken,
                output_dir=tmp_path,
                config_path=triptych_config_file,
            )

    def test_generation_failure_becomes_a_triptych_error(
        self,
        monkeypatch,
        triptych_pauta_file,
        triptych_config_file,
        tmp_path,
    ):
        monkeypatch.setattr(
            orchestrator, "LLMClient", lambda **_: _FakeClient("no es json")
        )
        monkeypatch.setattr(orchestrator, "get_api_key", lambda: "clave")

        with pytest.raises(TriptychError) as excinfo:
            run_print(
                pauta_path=triptych_pauta_file,
                output_dir=tmp_path,
                config_path=triptych_config_file,
            )

        assert "No se pudo generar el tríptico" in str(excinfo.value)

    def test_client_failure_becomes_a_triptych_error(
        self,
        monkeypatch,
        triptych_pauta_file,
        triptych_config_file,
        tmp_path,
    ):
        class _Broken:
            def generate_report(self, system_prompt: str, user_prompt: str) -> str:
                raise LLMClientError("la API no responde")

        monkeypatch.setattr(orchestrator, "LLMClient", lambda **_: _Broken())
        monkeypatch.setattr(orchestrator, "get_api_key", lambda: "clave")

        with pytest.raises(TriptychError):
            run_print(
                pauta_path=triptych_pauta_file,
                output_dir=tmp_path,
                config_path=triptych_config_file,
            )

    def test_nothing_is_written_when_generation_fails(
        self,
        monkeypatch,
        triptych_pauta_file,
        triptych_config_file,
        tmp_path,
    ):
        monkeypatch.setattr(
            orchestrator, "LLMClient", lambda **_: _FakeClient("no es json")
        )
        monkeypatch.setattr(orchestrator, "get_api_key", lambda: "clave")
        output = tmp_path / "impresos"

        with pytest.raises(TriptychError):
            run_print(
                pauta_path=triptych_pauta_file,
                output_dir=output,
                config_path=triptych_config_file,
            )

        assert not output.exists()
