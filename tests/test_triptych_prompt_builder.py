"""Tests de los prompts del tríptico impreso.

El prompt es el contrato con el modelo: si los números del presupuesto o el
esquema de salida se separan de la validación, el tríptico llega siempre
incompleto. Estos tests fijan esa correspondencia.
"""

import copy

import pytest

from news_agent.config import load_triptych_config
from news_agent.triptych.prompt_builder import (
    TRIPTYCH_SYSTEM_PROMPT,
    build_triptych_system_prompt,
    build_triptych_user_prompt,
)
from news_agent.triptych.specs import (
    block_max_chars,
    chars_per_line,
    lines_per_column,
    triptych_specs,
)

CONFIG_PATH = "triptych_config.json"


@pytest.fixture
def config() -> dict:
    """Configuración real del tríptico.

    Returns:
        dict: Configuración cargada desde el repositorio.
    """
    return load_triptych_config(CONFIG_PATH)


class TestModuleContract:
    """El módulo expone lo que declara."""

    @pytest.mark.parametrize(
        "name",
        [
            "build_triptych_system_prompt",
            "build_triptych_user_prompt",
            "TRIPTYCH_SYSTEM_PROMPT",
        ],
    )
    def test_exposes_symbol(self, name):
        import news_agent.triptych.prompt_builder as module

        assert hasattr(module, name)

    def test_system_prompt_is_not_empty(self):
        assert TRIPTYCH_SYSTEM_PROMPT.strip()


class TestSystemPrompt:
    """Identidad editorial y reglas de lenguaje."""

    def test_uses_the_brand_name_from_the_config(self, config):
        prompt = build_triptych_system_prompt(config)

        assert "La Chispa Sur" in prompt

    def test_encodes_the_sentence_limit_from_the_config(self, config):
        prompt = build_triptych_system_prompt(config)

        assert "Frases de 15 palabras o menos." in prompt

    def test_encodes_the_key_data_count_from_the_config(self, config):
        prompt = build_triptych_system_prompt(config)

        assert "3 cifras o hechos concretos" in prompt

    def test_states_the_four_simple_language_rules(self, config):
        prompt = build_triptych_system_prompt(config)

        assert "Ninguna sigla sin explicar." in prompt
        assert "Nada de jerga." in prompt
        assert "Trato directo." in prompt
        assert "Cifras domésticas." in prompt

    def test_forbids_regional_slang(self, config):
        prompt = build_triptych_system_prompt(config)

        assert "Prohibidos el voseo" in prompt

    def test_states_the_fixed_structure(self, config):
        prompt = build_triptych_system_prompt(config)

        assert "qué pasó" in prompt
        assert "por qué te importa" in prompt
        assert "los datos que lo prueban" in prompt

    def test_works_without_config(self):
        prompt = build_triptych_system_prompt()

        assert "La Chispa Sur" in prompt

    def test_follows_custom_config_values(self, config):
        custom = copy.deepcopy(config)
        custom["style"]["max_words_per_sentence"] = 9
        custom["layout"]["key_data_items"] = 4
        custom["brand"]["name"] = "Otro Medio"

        prompt = build_triptych_system_prompt(custom)

        assert "Frases de 9 palabras o menos." in prompt
        assert "4 cifras o hechos concretos" in prompt
        assert "Otro Medio" in prompt


class TestUserPrompt:
    """Tarea, presupuesto, esquema y material de origen."""

    def test_states_the_measured_budget(self, triptych_source, config):
        prompt = build_triptych_user_prompt(triptych_source, config)
        specs = triptych_specs(config)

        assert f"{chars_per_line(specs, 1.0)} caracteres por línea" in prompt
        assert f"{lines_per_column(specs)} líneas por columna" in prompt
        assert f"{block_max_chars(specs)} caracteres en total" in prompt
        assert "1.5 columnas" in prompt

    def test_states_the_body_target(self, triptych_source, config):
        prompt = build_triptych_user_prompt(triptych_source, config)

        assert "700 caracteres de `body`" in prompt

    def test_asks_for_one_note_per_proposal(self, triptych_source, config):
        prompt = build_triptych_user_prompt(triptych_source, config)

        assert "Exactamente 5 notas" in prompt

    def test_includes_the_json_schema(self, triptych_source, config):
        prompt = build_triptych_user_prompt(triptych_source, config)

        for key in ("cover", "hook", "notes", "proposal_number", "key_data"):
            assert f'"{key}"' in prompt
        assert "why_it_matters" in prompt

    def test_includes_every_proposal(self, triptych_source, config):
        prompt = build_triptych_user_prompt(triptych_source, config)

        for number in range(1, 6):
            assert f"### Propuesta {number}: Titular de la propuesta {number}" in prompt

    def test_includes_the_companion_material(self, triptych_source, config):
        prompt = build_triptych_user_prompt(triptych_source, config)

        assert "[Medio Uno] Noticia de respaldo 1" in prompt

    def test_follows_custom_limits(self, triptych_source, config):
        custom = copy.deepcopy(config)
        custom["limits"]["body_target_chars"] = 500
        custom["layout"]["notes"] = 3

        prompt = build_triptych_user_prompt(triptych_source, custom)

        assert "500 caracteres de `body`" in prompt
        assert "Exactamente 3 notas" in prompt
        assert "### Propuesta 4" not in prompt

    def test_works_without_config(self, triptych_source):
        prompt = build_triptych_user_prompt(triptych_source)

        assert "Exactamente 5 notas" in prompt
