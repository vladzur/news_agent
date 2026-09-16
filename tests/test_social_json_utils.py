"""Tests de la extracción defensiva de JSON del subsistema de RRSS."""

import pytest

from news_agent.social.json_utils import JsonExtractionError, extract_json_object


class TestExtractJsonObject:
    """Extracción de objetos JSON desde respuestas crudas del modelo."""

    def test_parses_plain_json_object(self):
        result = extract_json_object('{"a": 1, "b": "dos"}')

        assert result == {"a": 1, "b": "dos"}

    def test_parses_json_inside_markdown_fence(self):
        raw = 'Aquí está el resultado:\n```json\n{"a": 1}\n```\nSaludos.'

        assert extract_json_object(raw) == {"a": 1}

    def test_parses_json_inside_unlabelled_fence(self):
        raw = "```\n{\"a\": 1}\n```"

        assert extract_json_object(raw) == {"a": 1}

    def test_ignores_text_before_and_after(self):
        raw = 'Claro, este es el JSON: {"a": 1, "b": {"c": 2}} Eso es todo.'

        assert extract_json_object(raw) == {"a": 1, "b": {"c": 2}}

    def test_repairs_trailing_commas(self):
        raw = '{"a": 1, "b": [1, 2,], }'

        assert extract_json_object(raw) == {"a": 1, "b": [1, 2]}

    def test_braces_inside_strings_do_not_break_matching(self):
        raw = '{"texto": "una llave } suelta", "n": 1}'

        assert extract_json_object(raw) == {"texto": "una llave } suelta", "n": 1}

    def test_ignores_non_dict_json_and_raises(self):
        with pytest.raises(JsonExtractionError):
            extract_json_object("[1, 2, 3]")

    def test_raises_on_empty_response(self):
        with pytest.raises(JsonExtractionError):
            extract_json_object("")

    def test_raises_on_whitespace_only_response(self):
        with pytest.raises(JsonExtractionError):
            extract_json_object("   \n  ")

    def test_raises_when_there_is_no_json(self):
        with pytest.raises(JsonExtractionError):
            extract_json_object("No pude generar el contenido solicitado.")

    def test_keeps_nested_structures_intact(self):
        raw = '{"prompts": [{"aspect": "square", "prompt": "a b c"}]}'

        result = extract_json_object(raw)

        assert result["prompts"][0]["aspect"] == "square"
