"""Tests de la carga y validación de ``triptych_config.json``.

Validan que el archivo versionado del repositorio tenga la estructura que el
resto del subsistema espera y que cada campo mal declarado se detecte al
cargar, con un mensaje que nombre el campo culpable.
"""

import copy
import json
from pathlib import Path

import pytest

from news_agent.config import ConfigurationError, load_triptych_config

CONFIG_PATH = Path(__file__).resolve().parent.parent / "triptych_config.json"


@pytest.fixture
def raw_config() -> dict:
    """Contenido del archivo de configuración real del repositorio.

    Returns:
        dict: Configuración cruda, lista para mutar en los tests.
    """
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def mutate(raw_config):
    """Devuelve una copia de la configuración con una sección modificada."""

    def _mutate(section: str, **changes) -> dict:
        data = copy.deepcopy(raw_config)
        data[section].update(changes)
        return data

    return _mutate


def _write(tmp_path: Path, data) -> Path:
    """Escribe una configuración en un archivo temporal.

    Args:
        tmp_path: Directorio temporal del test.
        data: Contenido a serializar.

    Returns:
        Path: Ruta al archivo escrito.
    """
    path = tmp_path / "triptych_config.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _assert_invalid(tmp_path: Path, data, fragment: str) -> None:
    """Comprueba que la carga falle nombrando el campo culpable.

    Args:
        tmp_path: Directorio temporal del test.
        data: Configuración inválida.
        fragment: Texto que debe aparecer en el mensaje de error.
    """
    with pytest.raises(ConfigurationError) as excinfo:
        load_triptych_config(_write(tmp_path, data))

    assert fragment in str(excinfo.value)


class TestModuleContract:
    """El módulo expone el cargador que declara."""

    def test_exposes_loader(self):
        assert callable(load_triptych_config)

    def test_configuration_error_is_an_exception(self):
        assert issubclass(ConfigurationError, Exception)


class TestValidConfig:
    """El archivo versionado del repositorio es válido."""

    def test_loads_every_required_section(self, raw_config):
        config = load_triptych_config(CONFIG_PATH)

        assert set(config) >= {
            "page",
            "typography",
            "limits",
            "style",
            "layout",
        }
        assert config["page"]["preset"] == "oficio"

    def test_keeps_the_brand_section(self, raw_config):
        config = load_triptych_config(CONFIG_PATH)

        assert config["brand"]["name"] == "La Chispa Sur"

    def test_brand_is_optional(self, raw_config, tmp_path):
        data = copy.deepcopy(raw_config)
        data.pop("brand")

        config = load_triptych_config(_write(tmp_path, data))

        assert "brand" not in config


class TestFileErrors:
    """Errores de archivo."""

    def test_missing_file(self, tmp_path):
        with pytest.raises(ConfigurationError) as excinfo:
            load_triptych_config(tmp_path / "no-existe.json")

        assert "no encontrado" in str(excinfo.value)

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "triptych_config.json"
        path.write_text("{esto no es json", encoding="utf-8")

        with pytest.raises(ConfigurationError) as excinfo:
            load_triptych_config(path)

        assert "JSON válido" in str(excinfo.value)

    def test_top_level_must_be_an_object(self, tmp_path):
        _assert_invalid(tmp_path, ["page"], "objeto JSON")


class TestSectionErrors:
    """Secciones obligatorias."""

    @pytest.mark.parametrize(
        "section", ["page", "typography", "limits", "style", "layout"]
    )
    def test_missing_section(self, raw_config, tmp_path, section):
        data = copy.deepcopy(raw_config)
        data.pop(section)

        _assert_invalid(tmp_path, data, f"obligatoria '{section}'")

    def test_section_must_be_an_object(self, raw_config, tmp_path):
        data = copy.deepcopy(raw_config)
        data["page"] = "oficio"

        _assert_invalid(tmp_path, data, "sección 'page'")

    def test_brand_must_be_an_object(self, raw_config, tmp_path):
        data = copy.deepcopy(raw_config)
        data["brand"] = "La Chispa Sur"

        _assert_invalid(tmp_path, data, "'brand'")


class TestPageSection:
    """Geometría de la hoja."""

    @pytest.mark.parametrize(
        "field", ["width_mm", "height_mm", "margin_mm", "columns_per_side"]
    )
    def test_requires_each_field(self, raw_config, tmp_path, field):
        data = copy.deepcopy(raw_config)
        data["page"].pop(field)

        _assert_invalid(tmp_path, data, f"'{field}'")

    def test_rejects_non_positive_width(self, mutate, tmp_path):
        _assert_invalid(
            tmp_path, mutate("page", width_mm=0), "'width_mm'"
        )

    def test_rejects_booleans_as_measurements(self, mutate, tmp_path):
        _assert_invalid(
            tmp_path, mutate("page", width_mm=True), "número mayor que cero"
        )

    def test_rejects_zero_columns(self, mutate, tmp_path):
        _assert_invalid(
            tmp_path, mutate("page", columns_per_side=0), "entero mayor que cero"
        )

    def test_rejects_unknown_sides(self, mutate, tmp_path):
        _assert_invalid(tmp_path, mutate("page", sides=3), "'sides'")

    def test_rejects_unknown_fold(self, mutate, tmp_path):
        _assert_invalid(tmp_path, mutate("page", fold="raro"), "'fold'")

    def test_rejects_a_margin_that_eats_the_page(self, mutate, tmp_path):
        _assert_invalid(
            tmp_path, mutate("page", margin_mm=110.0), "ancho útil"
        )


class TestTypographySection:
    """Tipografía del tríptico."""

    def test_rejects_empty_family(self, mutate, tmp_path):
        _assert_invalid(tmp_path, mutate("typography", family="  "), "'family'")

    @pytest.mark.parametrize(
        "field", ["size_pt", "char_width_em", "line_height_ratio"]
    )
    def test_requires_each_measurement(self, raw_config, tmp_path, field):
        data = copy.deepcopy(raw_config)
        data["typography"].pop(field)

        _assert_invalid(tmp_path, data, f"'{field}'")

    def test_rejects_negative_size(self, mutate, tmp_path):
        _assert_invalid(
            tmp_path, mutate("typography", size_pt=-1), "mayor que cero"
        )


class TestLimitsSection:
    """Topes de largo."""

    @pytest.mark.parametrize("field", ["block_max_columns", "body_target_chars"])
    def test_requires_each_field(self, raw_config, tmp_path, field):
        data = copy.deepcopy(raw_config)
        data["limits"].pop(field)

        _assert_invalid(tmp_path, data, f"'{field}'")

    def test_rejects_zero_columns_limit(self, mutate, tmp_path):
        _assert_invalid(
            tmp_path, mutate("limits", block_max_columns=0), "'block_max_columns'"
        )

    def test_rejects_a_text_as_a_char_budget(self, mutate, tmp_path):
        _assert_invalid(
            tmp_path,
            mutate("limits", body_target_chars="muchos"),
            "'body_target_chars'",
        )


class TestStyleSection:
    """Reglas de lenguaje simple."""

    def test_requires_the_sentence_limit(self, raw_config, tmp_path):
        data = copy.deepcopy(raw_config)
        data["style"].pop("max_words_per_sentence")

        _assert_invalid(tmp_path, data, "'max_words_per_sentence'")

    def test_rejects_zero_sentence_limit(self, mutate, tmp_path):
        _assert_invalid(
            tmp_path, mutate("style", max_words_per_sentence=0), "entero mayor"
        )

    def test_rejects_a_text_as_the_allowlist(self, mutate, tmp_path):
        _assert_invalid(
            tmp_path, mutate("style", acronym_allowlist="ONU"), "'acronym_allowlist'"
        )

    def test_rejects_non_text_items_in_the_allowlist(self, mutate, tmp_path):
        _assert_invalid(
            tmp_path, mutate("style", acronym_allowlist=["ONU", 7]), "lista de textos"
        )

    def test_rejects_non_text_forbidden_terms(self, mutate, tmp_path):
        _assert_invalid(
            tmp_path,
            mutate("style", forbidden_terms=[1, 2]),
            "'forbidden_terms'",
        )

    def test_list_fields_are_optional(self, raw_config, tmp_path):
        data = copy.deepcopy(raw_config)
        data["style"].pop("acronym_allowlist")
        data["style"].pop("forbidden_terms")

        config = load_triptych_config(_write(tmp_path, data))

        assert "acronym_allowlist" not in config["style"]


class TestLayoutSection:
    """Paneles y bloques de cada nota."""

    @pytest.mark.parametrize("field", ["notes", "key_data_items"])
    def test_requires_each_field(self, raw_config, tmp_path, field):
        data = copy.deepcopy(raw_config)
        data["layout"].pop(field)

        _assert_invalid(tmp_path, data, f"'{field}'")

    def test_rejects_zero_notes(self, mutate, tmp_path):
        _assert_invalid(tmp_path, mutate("layout", notes=0), "'notes'")

    def test_rejects_zero_key_data_items(self, mutate, tmp_path):
        _assert_invalid(
            tmp_path, mutate("layout", key_data_items=0), "'key_data_items'"
        )
