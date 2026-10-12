"""Tests de la generación y validación del tríptico impreso.

Fijan las dos políticas del subsistema: lo estructural —cinco notas, cuerpo con
texto suficiente— es fatal y aborta la escritura del bundle; lo estilístico y
el desborde de columnas solo se advierten, porque el ajuste final lo hace una
persona.
"""

import json

import pytest

from news_agent.triptych.generator import (
    TriptychGenerationError,
    build_triptych,
    generate_triptych,
)
from news_agent.triptych.models import TriptychPackage

# Cuerpo de ejemplo: supera el mínimo exigido y sus oraciones son cortas.
BODY = (
    "Chile firmó un acuerdo con Estados Unidos. El texto no habla solo de "
    "delincuencia. También trata de inversiones y de litio. Nadie lo votó "
    "en el Congreso. Eso preocupa a los abogados. "
) * 3


class _QueuedClient:
    """Cliente que devuelve respuestas en cola y registra los prompts."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts: list[str] = []
        self.system_prompts: list[str] = []

    def generate_report(self, system_prompt: str, user_prompt: str) -> str:
        """Devuelve la siguiente respuesta de la cola.

        Args:
            system_prompt: Identidad editorial del prompt.
            user_prompt: Tarea enviada al modelo.

        Returns:
            str: Respuesta encolada.

        Raises:
            AssertionError: Si la cola se agotó.
        """
        self.system_prompts.append(system_prompt)
        self.prompts.append(user_prompt)
        if not self.responses:
            raise AssertionError("el cliente no tiene más respuestas")

        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _note(
    number: int,
    body: str = BODY,
    key_data: list[str] | None = None,
    **overrides,
) -> dict:
    """Construye una nota del payload con los valores por defecto del contrato.

    Args:
        number: Número de propuesta asociado.
        body: Cuerpo de la nota.
        key_data: Datos clave; por defecto, los tres del contrato.
        **overrides: Campos a sobrescribir.

    Returns:
        dict: Nota lista para el payload.
    """
    note = {
        "proposal_number": number,
        "title": f"Nota {number}",
        "body": body,
        "key_data": ["Uno", "Dos", "Tres"] if key_data is None else key_data,
        "why_it_matters": "Te afecta porque el litio es de todos.",
    }
    note.update(overrides)
    return note


def _payload(
    count: int = 5,
    body: str = BODY,
    key_data: list[str] | None = None,
    **overrides,
) -> dict:
    """Construye un payload completo para ``build_triptych``.

    Args:
        count: Cantidad de notas a incluir.
        body: Cuerpo que reciben todas las notas.
        key_data: Datos clave que reciben todas las notas.
        **overrides: Campos de nivel superior a sobrescribir.

    Returns:
        dict: Payload equivalente al que devolvería el modelo.
    """
    payload = {
        "cover": {"hook": "Gancho de portada", "title": "Título de la edición"},
        "notes": [
            _note(number, body=body, key_data=key_data)
            for number in range(1, count + 1)
        ],
    }
    payload.update(overrides)
    return payload


class TestModuleContract:
    """El módulo expone lo que declara."""

    @pytest.mark.parametrize(
        "name", ["build_triptych", "generate_triptych", "TriptychGenerationError"]
    )
    def test_exposes_symbol(self, name):
        import news_agent.triptych.generator as module

        assert hasattr(module, name)

    def test_generation_error_is_an_exception(self):
        assert issubclass(TriptychGenerationError, Exception)


class TestBuildTriptych:
    """Validación pura del payload del modelo."""

    def test_builds_the_cover(self, triptych_source, triptych_config):
        package = build_triptych(_payload(), triptych_source, triptych_config)

        assert package.cover.hook == "Gancho de portada"
        assert package.cover.title == "Título de la edición"

    def test_reserves_panel_one_for_the_cover(self, triptych_source, triptych_config):
        package = build_triptych(_payload(), triptych_source, triptych_config)

        assert [note.panel for note in package.notes] == [2, 3, 4, 5, 6]

    def test_takes_the_sources_from_the_pauta_proposal(
        self, triptych_source, triptych_config
    ):
        package = build_triptych(_payload(), triptych_source, triptych_config)

        assert package.notes[0].sources == [
            "Medio Uno [art. 1]: cobertura del caso.",
            "Medio Dos [art. 101]: contexto adicional.",
        ]

    def test_maps_each_note_to_its_proposal(self, triptych_source, triptych_config):
        package = build_triptych(_payload(), triptych_source, triptych_config)

        assert [note.proposal_number for note in package.notes] == [1, 2, 3, 4, 5]

    def test_measures_the_block_and_the_body(self, triptych_source, triptych_config):
        note = build_triptych(
            _payload(), triptych_source, triptych_config
        ).notes[0]

        assert note.measurement["chars"] > note.measurement["body"]["chars"]
        assert note.measurement["chars_per_line"] == 24
        assert note.measurement["block_max_columns"] == 1.5

    def test_reads_the_page_format_from_the_config(
        self, triptych_source, triptych_config
    ):
        package = build_triptych(_payload(), triptych_source, triptych_config)

        assert package.panels == 6
        assert package.sides == 2
        assert package.columns_per_side == 3
        assert package.fold == "roll"

    def test_records_the_generation_time(self, triptych_source, triptych_config):
        package = build_triptych(_payload(), triptych_source, triptych_config)

        assert package.generated_at.endswith("+00:00")

    def test_a_clean_payload_has_no_warnings(
        self, triptych_source, triptych_config
    ):
        package = build_triptych(_payload(), triptych_source, triptych_config)

        assert package.warnings == []
        assert all(note.warnings == [] for note in package.notes)
        assert package.overflowing_notes == []

    def test_serializes_to_a_json_ready_dictionary(
        self, triptych_source, triptych_config
    ):
        package = build_triptych(_payload(), triptych_source, triptych_config)

        data = package.to_dict()

        assert json.loads(json.dumps(data, ensure_ascii=False))
        assert isinstance(package, TriptychPackage)
        assert data["notes"][0]["panel"] == 2

    def test_builds_without_config(self, triptych_source):
        package = build_triptych(_payload(), triptych_source)

        assert len(package.notes) == 5


class TestStructuralErrors:
    """Fallos que abortan la escritura del bundle."""

    def test_missing_cover(self, triptych_source, triptych_config):
        with pytest.raises(TriptychGenerationError) as excinfo:
            build_triptych(_payload(cover=None), triptych_source, triptych_config)

        assert "'cover'" in str(excinfo.value)

    def test_empty_cover_hook(self, triptych_source, triptych_config):
        payload = _payload()
        payload["cover"]["hook"] = "   "

        with pytest.raises(TriptychGenerationError) as excinfo:
            build_triptych(payload, triptych_source, triptych_config)

        assert "cover.hook" in str(excinfo.value)

    def test_missing_notes_list(self, triptych_source, triptych_config):
        with pytest.raises(TriptychGenerationError) as excinfo:
            build_triptych(_payload(notes=None), triptych_source, triptych_config)

        assert "'notes'" in str(excinfo.value)

    def test_empty_notes_list(self, triptych_source, triptych_config):
        with pytest.raises(TriptychGenerationError):
            build_triptych(_payload(notes=[]), triptych_source, triptych_config)

    def test_wrong_number_of_notes(self, triptych_source, triptych_config):
        with pytest.raises(TriptychGenerationError) as excinfo:
            build_triptych(_payload(count=3), triptych_source, triptych_config)

        assert "Se esperaban 5 notas" in str(excinfo.value)
        assert "llegaron 3" in str(excinfo.value)

    def test_note_is_not_an_object(self, triptych_source, triptych_config):
        payload = _payload()
        payload["notes"][0] = "una nota en texto plano"

        with pytest.raises(TriptychGenerationError) as excinfo:
            build_triptych(payload, triptych_source, triptych_config)

        assert "no es un objeto JSON" in str(excinfo.value)

    def test_note_without_title(self, triptych_source, triptych_config):
        payload = _payload()
        payload["notes"][0]["title"] = ""

        with pytest.raises(TriptychGenerationError) as excinfo:
            build_triptych(payload, triptych_source, triptych_config)

        assert "notes[0].title" in str(excinfo.value)

    def test_body_below_the_minimum(self, triptych_source, triptych_config):
        payload = _payload(body="Muy corto.")

        with pytest.raises(TriptychGenerationError) as excinfo:
            build_triptych(payload, triptych_source, triptych_config)

        assert "por debajo del mínimo" in str(excinfo.value)


class TestWarnings:
    """Avisos que no abortan: el texto lo ajusta una persona."""

    def test_warns_when_the_block_exceeds_the_column_ceiling(
        self, triptych_source, triptych_config
    ):
        payload = _payload(body="Frase corta y simple. " * 200)

        package = build_triptych(payload, triptych_source, triptych_config)

        assert package.overflowing_notes
        assert "superan el tope de 1.5 columnas" in package.warnings[0]
        assert "no se recortó nada" in package.warnings[0].lower()

    def test_warns_per_note_about_the_overflow(
        self, triptych_source, triptych_config
    ):
        payload = _payload(body="Frase corta y simple. " * 200)

        package = build_triptych(payload, triptych_source, triptych_config)

        assert any(
            "hay que ajustarlo a mano" in warning
            for warning in package.notes[0].warnings
        )

    def test_warns_about_the_wrong_amount_of_key_data(
        self, triptych_source, triptych_config
    ):
        payload = _payload(key_data=["Uno", "Dos"])

        package = build_triptych(payload, triptych_source, triptych_config)

        assert any(
            "trae 2 datos clave en lugar de 3" in warning
            for warning in package.notes[0].warnings
        )

    def test_warns_about_unexplained_acronyms(
        self, triptych_source, triptych_config
    ):
        payload = _payload(body="El FMI presiona a Chile. " * 20)

        package = build_triptych(payload, triptych_source, triptych_config)

        assert any(
            "siglas sin explicar (FMI)" in warning
            for warning in package.notes[0].warnings
        )

    def test_warns_when_the_proposal_number_does_not_match(
        self, triptych_source, triptych_config
    ):
        payload = _payload()
        payload["notes"][1]["proposal_number"] = 99

        package = build_triptych(payload, triptych_source, triptych_config)

        assert any(
            "la marcó como propuesta 99" in warning
            for warning in package.notes[1].warnings
        )


class TestGenerateTriptych:
    """Llamada al modelo con reintentos."""

    def test_returns_the_validated_package(
        self, triptych_source, triptych_config
    ):
        client = _QueuedClient([json.dumps(_payload(), ensure_ascii=False)])

        package = generate_triptych(triptych_source, triptych_config, client)

        assert len(package.notes) == 5
        assert len(client.prompts) == 1

    def test_accepts_a_json_payload_wrapped_in_a_code_fence(
        self, triptych_source, triptych_config
    ):
        fenced = "```json\n" + json.dumps(_payload(), ensure_ascii=False) + "\n```"
        client = _QueuedClient([fenced])

        package = generate_triptych(triptych_source, triptych_config, client)

        assert len(package.notes) == 5

    def test_retries_when_the_response_is_not_json(
        self, triptych_source, triptych_config
    ):
        client = _QueuedClient(
            [
                "esto no es un objeto json",
                json.dumps(_payload(), ensure_ascii=False),
            ]
        )

        package = generate_triptych(triptych_source, triptych_config, client)

        assert len(package.notes) == 5
        assert len(client.prompts) == 2
        assert "Corrección obligatoria" in client.prompts[1]

    def test_retries_when_the_contract_is_broken(
        self, triptych_source, triptych_config
    ):
        client = _QueuedClient(
            [
                json.dumps(_payload(count=3), ensure_ascii=False),
                json.dumps(_payload(), ensure_ascii=False),
            ]
        )

        package = generate_triptych(triptych_source, triptych_config, client)

        assert len(package.notes) == 5
        assert "Se esperaban 5 notas" in client.prompts[1]

    def test_gives_up_after_the_configured_retries(
        self, triptych_source, triptych_config
    ):
        client = _QueuedClient(["no json", "no json", "no json"])

        with pytest.raises(TriptychGenerationError) as excinfo:
            generate_triptych(triptych_source, triptych_config, client)

        assert "tras 3 intento(s)" in str(excinfo.value)
        assert len(client.prompts) == 3

    def test_propagates_a_client_failure(self, triptych_source, triptych_config):
        from news_agent.llm_client import LLMClientError

        client = _QueuedClient([LLMClientError("la API no responde")])

        with pytest.raises(LLMClientError):
            generate_triptych(triptych_source, triptych_config, client)

    def test_uses_the_prompts_from_the_prompt_builder(
        self, triptych_source, triptych_config
    ):
        client = _QueuedClient([json.dumps(_payload(), ensure_ascii=False)])

        generate_triptych(triptych_source, triptych_config, client)

        assert "Frases de 15 palabras o menos." in client.system_prompts[0]
        assert "Exactamente 5 notas" in client.prompts[0]
