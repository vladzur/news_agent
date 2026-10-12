"""Tests del subcomando ``print`` (tríptico impreso).

Cubren el parser, el handler, la guarda de directorio de salida y el resumen
que ve el usuario, además de la integración como cuarto paso de ``all``.
"""

from pathlib import Path
from typing import Any

import pytest

from news_agent import cli
from news_agent.__main__ import main
from news_agent.cli import (
    build_cli_parser,
    print_triptych_summary,
    run_print_step,
)
from news_agent.triptych.orchestrator import TriptychError


def _print_result(tmp_path: Path) -> dict[str, Any]:
    """Resultado simulado de ``run_print``.

    Args:
        tmp_path: Directorio temporal del test.

    Returns:
        dict[str, Any]: Resumen equivalente al del orquestador.
    """
    bundle = tmp_path / "impresos" / "2026_09_24_pauta-semanal"
    return {
        "bundle_dir": bundle,
        "triptych_path": bundle / "triptych.json",
        "markdown_path": bundle / "triptych.md",
        "manifest_path": bundle / "manifest.json",
        "title": "La letra chica",
        "notes": 5,
        "panels": 6,
        "fold": "roll",
        "overflowing": 0,
        "warnings": 0,
    }


def _capturing(calls: dict[str, Any], result: dict[str, Any]):
    """Construye un reemplazo que registra los argumentos recibidos.

    Args:
        calls: Diccionario donde se guardan los argumentos.
        result: Resultado que devuelve el reemplazo.

    Returns:
        Callable: Función de reemplazo para monkeypatch.
    """

    def _fake(**kwargs: Any) -> dict[str, Any]:
        calls.update(kwargs)
        return result

    return _fake


def _pauta(tmp_path: Path) -> Path:
    """Escribe una pauta mínima en disco.

    Args:
        tmp_path: Directorio temporal del test.

    Returns:
        Path: Ruta a la pauta escrita.
    """
    reports = tmp_path / "reportes"
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / "pauta_semanal_2026_09_24.md"
    path.write_text("# ⚡ Pauta Editorial Sugerida - La Chispa Sur\n", encoding="utf-8")
    return path


class TestParser:
    """Estructura del subcomando."""

    def test_registers_the_command(self):
        assert "print" in cli.COMMANDS
        assert cli.COMMAND_DESCRIPTIONS["print"] == (
            "Genera el tríptico impreso desde la pauta semanal."
        )

    def test_defaults(self):
        args = build_cli_parser().parse_args(["print"])

        assert args.command == "print"
        assert args.pauta is None
        assert args.output == "impresos"
        assert args.triptych_config is None
        assert args.verbose is False

    def test_routes_to_its_handler(self):
        args = build_cli_parser().parse_args(["print"])

        assert args.handler is cli._handle_print

    def test_accepts_every_option(self):
        args = build_cli_parser().parse_args(
            [
                "print",
                "--pauta",
                "reportes/pauta_semanal_2026_09_24.md",
                "--output",
                "salida",
                "--triptych-config",
                "otra.json",
                "--verbose",
            ]
        )

        assert args.pauta == "reportes/pauta_semanal_2026_09_24.md"
        assert args.output == "salida"
        assert args.triptych_config == "otra.json"
        assert args.verbose is True


class TestHandler:
    """Ejecución del comando."""

    def test_forwards_the_resolved_paths(self, tmp_path, monkeypatch):
        calls: dict[str, Any] = {}
        monkeypatch.setattr(cli, "run_print", _capturing(calls, _print_result(tmp_path)))
        pauta = _pauta(tmp_path)
        output = tmp_path / "impresos"

        main(
            [
                "print",
                "--pauta",
                str(pauta),
                "--output",
                str(output),
                "--triptych-config",
                "otra.json",
            ]
        )

        assert calls["pauta_path"] == pauta
        assert calls["output_dir"] == output
        assert calls["config_path"] == "otra.json"
        assert calls["verbose"] is False

    def test_uses_the_latest_report_when_no_pauta_is_given(
        self, tmp_path, monkeypatch
    ):
        calls: dict[str, Any] = {}
        monkeypatch.setattr(cli, "run_print", _capturing(calls, _print_result(tmp_path)))
        latest = _pauta(tmp_path)
        monkeypatch.setattr(cli, "find_latest_report", lambda *args, **kwargs: latest)

        main(["print", "--output", str(tmp_path / "impresos")])

        assert calls["pauta_path"] == latest

    def test_refuses_to_write_in_the_current_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pauta = _pauta(tmp_path)

        with pytest.raises(SystemExit) as excinfo:
            main(["print", "--pauta", str(pauta), "--output", "."])

        assert excinfo.value.code == 2


class TestRunPrintStep:
    """Traducción de errores del orquestador."""

    def test_returns_the_summary(self, tmp_path, monkeypatch):
        expected = _print_result(tmp_path)
        monkeypatch.setattr(cli, "run_print", lambda **_: expected)

        result = run_print_step(tmp_path, tmp_path, None, False)

        assert result is expected

    def test_turns_a_triptych_error_into_exit_code_one(
        self, tmp_path, monkeypatch
    ):
        def _raise(**kwargs: Any) -> dict[str, Any]:
            raise TriptychError("el modelo no devolvió un tríptico válido")

        monkeypatch.setattr(cli, "run_print", _raise)

        with pytest.raises(SystemExit) as excinfo:
            run_print_step(tmp_path, tmp_path, None, False)

        assert excinfo.value.code == 1


class TestSummary:
    """Resumen que ve el usuario."""

    def test_shows_the_generated_files(self, tmp_path, capsys):
        result = _print_result(tmp_path)

        print_triptych_summary(result)

        output = capsys.readouterr().out
        assert "Tríptico impreso generado exitosamente" in output
        assert str(result["bundle_dir"]) in output
        assert "Paneles: 6 · Notas: 5 · Pliegue: roll" in output
        assert "triptych.json" in output
        assert "manifest.json" in output

    def test_hides_the_warning_lines_when_there_is_nothing_pending(
        self, tmp_path, capsys
    ):
        print_triptych_summary(_print_result(tmp_path))

        assert "superan el tope" not in capsys.readouterr().out

    def test_reports_notes_over_the_column_ceiling(self, tmp_path, capsys):
        result = _print_result(tmp_path)
        result["overflowing"] = 2

        print_triptych_summary(result)

        assert "2 nota(s) superan el tope de columnas" in capsys.readouterr().out

    def test_reports_style_warnings(self, tmp_path, capsys):
        result = _print_result(tmp_path)
        result["warnings"] = 3

        print_triptych_summary(result)

        assert "Advertencias de estilo: 3" in capsys.readouterr().out


class TestAllIntegration:
    """El tríptico es el cuarto paso de ``all``."""

    @pytest.fixture
    def chained(self, tmp_path, monkeypatch) -> dict[str, Any]:
        """Reemplaza los cuatro pasos de ``all`` por dobles.

        Returns:
            dict[str, Any]: Registro de llamadas y resultados simulados.
        """
        calls: dict[str, Any] = {"order": []}
        pauta = _pauta(tmp_path)
        article = tmp_path / "articulos" / "articulo_1_titular.md"

        def _fake_pipeline(**kwargs: Any) -> dict[str, Any]:
            calls["order"].append("report")
            return {
                "report_path": pauta,
                "item_count": 1,
                "feed_count": 1,
                "debug_path": None,
                "companion_path": None,
            }

        def _fake_write(**kwargs: Any) -> dict[str, Any]:
            calls["order"].append("article")
            return {
                "article_path": article,
                "title": "Titular",
                "proposal_number": 1,
            }

        def _fake_socialize(**kwargs: Any) -> dict[str, Any]:
            calls["order"].append("social")
            return {
                "bundle_dir": tmp_path / "social",
                "copy_path": tmp_path / "social" / "social_copy.json",
                "prompts_path": None,
                "manifest_path": tmp_path / "social" / "manifest.json",
                "asset_paths": [],
                "markdown_paths": {},
                "platforms": ["x"],
                "title": "Titular",
                "prompt_count": 0,
                "banner_count": 0,
                "banner_failed": 0,
            }

        def _fake_print(**kwargs: Any) -> dict[str, Any]:
            calls["order"].append("print")
            calls["print"] = kwargs
            return _print_result(tmp_path)

        monkeypatch.setattr(cli, "run_pipeline", _fake_pipeline)
        monkeypatch.setattr(cli, "write_article", _fake_write)
        monkeypatch.setattr(
            "news_agent.social.orchestrator.run_socialize", _fake_socialize
        )
        monkeypatch.setattr(cli, "run_print", _fake_print)

        return calls

    def test_runs_the_triptych_as_the_last_step(self, tmp_path, chained):
        main(["all", "--base", str(tmp_path), "--number", "1"])

        assert chained["order"] == ["report", "article", "social", "print"]

    def test_feeds_the_triptych_with_the_generated_pauta(self, tmp_path, chained):
        main(
            [
                "all",
                "--base",
                str(tmp_path),
                "--number",
                "1",
                "--triptych-config",
                "otra.json",
            ]
        )

        assert chained["print"]["pauta_path"].name == "pauta_semanal_2026_09_24.md"
        assert chained["print"]["config_path"] == "otra.json"
        assert chained["print"]["output_dir"].name == "impresos"
