"""Tests del cálculo de medidas del tríptico impreso.

Comprueban que la geometría de la hoja oficio y la tipografía monospace se
traduzcan al presupuesto de caracteres que después se le exige al modelo. Si
estos números cambian sin querer, el prompt y la validación se desalinean.
"""

import re
from pathlib import Path

import pytest

from news_agent.config import load_triptych_config
from news_agent.triptych.specs import (
    DEFAULT_SPECS,
    block_max_chars,
    budget_report,
    char_width_mm,
    chars_per_line,
    column_max_chars,
    column_width_mm,
    estimate_columns,
    estimate_lines,
    format_length_report,
    line_height_mm,
    lines_per_column,
    max_chars_for_columns,
    triptych_specs,
    usable_height_mm,
    usable_width_mm,
)

# Configuración versionada del repositorio.
CONFIG_PATH = Path(__file__).resolve().parent.parent / "triptych_config.json"


@pytest.fixture
def specs() -> dict:
    """Especificaciones resueltas desde la configuración real del repositorio.

    Returns:
        dict: Especificaciones con todas sus secciones.
    """
    return triptych_specs(load_triptych_config(CONFIG_PATH))


class TestModuleContract:
    """El módulo expone las funciones que declara."""

    @pytest.mark.parametrize(
        "name",
        [
            "triptych_specs",
            "char_width_mm",
            "usable_width_mm",
            "usable_height_mm",
            "column_width_mm",
            "line_height_mm",
            "chars_per_line",
            "lines_per_column",
            "max_chars_for_columns",
            "column_max_chars",
            "block_max_chars",
            "estimate_lines",
            "estimate_columns",
            "budget_report",
            "format_length_report",
        ],
    )
    def test_exposes_helper(self, name):
        import news_agent.triptych.specs as module

        assert callable(getattr(module, name))

    def test_default_specs_declare_every_section(self):
        assert set(DEFAULT_SPECS) == {
            "page",
            "typography",
            "limits",
            "style",
            "layout",
        }


class TestGeometry:
    """Geometría derivada de la hoja oficio y del monospace de 12 pt."""

    def test_char_width_matches_monospace_advance(self, specs):
        # 12 pt * 0,6025 em = 7,23 pt = 2,5506 mm
        assert char_width_mm(specs) == pytest.approx(2.5506, abs=1e-4)

    def test_usable_width_discounts_both_margins(self, specs):
        assert usable_width_mm(specs) == pytest.approx(185.9, abs=1e-6)

    def test_usable_height_discounts_both_margins(self, specs):
        assert usable_height_mm(specs) == pytest.approx(300.2, abs=1e-6)

    def test_column_width_divides_by_columns_per_side(self, specs):
        assert column_width_mm(specs) == pytest.approx(61.9667, abs=1e-3)

    def test_line_height_includes_leading(self, specs):
        # 12 pt * 1,2 de interlínea = 14,4 pt = 5,08 mm
        assert line_height_mm(specs) == pytest.approx(5.08, abs=1e-6)

    def test_chars_per_line_for_one_and_a_half_columns(self, specs):
        assert chars_per_line(specs, 1.0) == 24
        assert chars_per_line(specs, 1.5) == 36

    def test_lines_per_column(self, specs):
        assert lines_per_column(specs) == 59

    def test_character_budgets(self, specs):
        assert column_max_chars(specs) == 1416
        assert block_max_chars(specs) == 2124

    def test_max_chars_for_one_column_equals_column_budget(self, specs):
        assert max_chars_for_columns(specs, 1.0) == column_max_chars(specs)


class TestConfigOverrides:
    """La fusión de configuración es defensiva: una errata no rompe la medida."""

    def test_rejects_invalid_values_and_keeps_defaults(self):
        specs = triptych_specs(
            {
                "page": {"width_mm": "mucho", "columns_per_side": -3},
                "limits": {"block_max_columns": 0},
                "layout": {"notes": 0, "extra": 1},
                "style": {"acronym_allowlist": "ONU"},
            }
        )

        assert specs["page"]["width_mm"] == DEFAULT_SPECS["page"]["width_mm"]
        assert specs["page"]["columns_per_side"] == 3
        assert specs["limits"]["block_max_columns"] == 1.5
        assert specs["layout"]["notes"] == 5
        assert specs["style"]["acronym_allowlist"] == []
        assert "extra" not in specs["layout"]

    def test_accepts_valid_overrides(self):
        specs = triptych_specs(
            {
                "page": {"width_mm": 300.0, "columns_per_side": 4},
                "limits": {"block_max_columns": 2},
                "layout": {"notes": 7},
            }
        )

        assert specs["page"]["width_mm"] == 300.0
        assert specs["page"]["columns_per_side"] == 4
        assert specs["limits"]["block_max_columns"] == 2.0
        assert specs["layout"]["notes"] == 7

    def test_ignores_booleans_where_numbers_are_expected(self):
        specs = triptych_specs({"page": {"width_mm": True}})

        assert specs["page"]["width_mm"] == DEFAULT_SPECS["page"]["width_mm"]

    def test_without_config_uses_defaults(self):
        assert triptych_specs()["page"] == DEFAULT_SPECS["page"]


class TestEstimateLines:
    """Conteo de líneas de un bloque de texto."""

    def test_empty_text_occupies_no_lines(self):
        assert estimate_lines("", 24) == 0

    def test_single_short_line(self):
        assert estimate_lines("hola", 24) == 1

    def test_wraps_words_that_do_not_fit(self):
        # "uno dos tres cuatro" en 6 caracteres: uno / dos / tres / cuatro
        assert estimate_lines("uno dos tres cuatro", 6) == 4

    def test_word_longer_than_the_column_is_split(self):
        assert estimate_lines("x" * 30, 24) == 2

    def test_blank_line_counts_as_one_row(self):
        assert estimate_lines("a\n\nb", 10) == 3

    def test_rejects_non_positive_column_width(self):
        with pytest.raises(ValueError):
            estimate_lines("hola", 0)


class TestBudgetReport:
    """Resumen de medición contra el presupuesto del bloque."""

    def test_reports_the_measured_values(self, specs):
        report = budget_report("hola", specs)

        assert report["chars"] == 4
        assert report["lines"] == 1
        assert report["columns"] == pytest.approx(0.02, abs=0.01)
        assert report["chars_per_line"] == 24
        assert report["lines_per_column"] == 59
        assert report["block_max_chars"] == 2124

    def test_short_text_stays_within_budget(self, specs):
        report = budget_report("Frase corta. " * 20, specs)

        assert report["within_column"] is True
        assert report["within_block_max"] is True
        assert report["columns_excess"] == 0.0

    def test_long_text_exceeds_the_block_budget(self, specs):
        report = budget_report("Frase corta. " * 400, specs)

        assert report["within_column"] is False
        assert report["within_block_max"] is False
        assert report["columns_excess"] > 0


class TestEstimateColumns:
    """Estimación de columnas ocupadas."""

    def test_returns_the_lines_over_lines_per_column(self, specs):
        text = "Frase corta. " * 30
        columns = estimate_columns(text, specs)
        lines = estimate_lines(text, chars_per_line(specs, 1.0))

        assert isinstance(columns, float)
        assert columns == pytest.approx(
            round(lines / lines_per_column(specs), 2), abs=1e-6
        )

    def test_a_single_row_is_a_fraction_of_a_column(self, specs):
        assert estimate_columns("hola", specs) == pytest.approx(0.02, abs=0.01)


class TestFormatLengthReport:
    """Redacción del resumen de medición."""

    def test_renders_a_readable_line(self, specs):
        text = format_length_report(budget_report("Frase corta. " * 30, specs))

        assert re.fullmatch(
            r"\d+ caracteres, \d+ líneas, \d+\.\d+ columnas", text
        )
