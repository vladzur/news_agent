"""Tests del CLI por subcomandos (report/article/social/all/clean)."""

import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from news_agent import cli
from news_agent.__main__ import main
from news_agent.article_writer import PautaParseError
from news_agent.cli import build_cli_parser

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_file(path: Path, when: datetime | None = None) -> Path:
    """Crea un archivo y, si se indica, le fija la fecha de modificación.

    Args:
        path: Ruta del archivo a crear.
        when: Fecha de modificación a fijar, o None para dejarla actual.

    Returns:
        Path: La ruta del archivo creado.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("contenido de prueba", encoding="utf-8")
    if when is not None:
        timestamp = when.timestamp()
        os.utime(path, (timestamp, timestamp))
    return path


def _capturing(
    calls: dict[str, Any],
    result: dict[str, Any],
) -> Callable[..., dict[str, Any]]:
    """Construye un reemplazo que registra los argumentos recibidos.

    Args:
        calls: Diccionario donde se guardan los argumentos.
        result: Resultado que devuelve el reemplazo.

    Returns:
        Callable[..., dict[str, Any]]: Función de reemplazo para monkeypatch.
    """

    def _fake(**kwargs: Any) -> dict[str, Any]:
        calls.update(kwargs)
        return result

    return _fake


def _pauta_markdown(proposals: int = 5) -> str:
    """Construye una pauta mínima parseable por ``parse_pauta_file``.

    Args:
        proposals: Cantidad de propuestas a incluir.

    Returns:
        str: Contenido Markdown de la pauta.
    """
    lines = [
        "# ⚡ Pauta Editorial Sugerida - La Chispa Sur",
        "**Fecha de Generación:** 2026-09-23  ",
        "**Notas Procesadas:** 10",
        "",
        "---",
        "",
    ]
    for number in range(1, proposals + 1):
        lines.extend(
            [
                f"## {number}. Titular {number}",
                "*   **Enfoque Editorial:** Enfoque de prueba.",
                "*   **Puntos Clave a Desarrollar:**",
                "    1. Punto uno",
                "*   **Fuentes Sugeridas para Ampliar:**",
                "    *   Medio: Aporte",
                "",
            ]
        )
    return "\n".join(lines)


def _proposals(count: int = 5) -> list[dict[str, Any]]:
    """Construye propuestas parseadas para probar la selección interactiva."""
    return [{"number": number, "title": f"Titular {number}"} for number in range(1, count + 1)]


def _report_result(tmp_path: Path) -> dict[str, Any]:
    """Resultado simulado de ``run_pipeline`` con una pauta válida en disco."""
    report = tmp_path / "reportes" / "pauta_semanal_2026_09_23.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_pauta_markdown(), encoding="utf-8")
    return {
        "report_path": report,
        "item_count": 42,
        "feed_count": 7,
        "debug_path": None,
        "companion_path": None,
    }


def _article_result(tmp_path: Path) -> dict[str, Any]:
    """Resultado simulado de ``write_article``."""
    article = tmp_path / "articulos" / "articulo_1_titular.md"
    return {
        "article_path": article,
        "title": "Titular",
        "proposal_number": 1,
    }


def _social_result(tmp_path: Path) -> dict[str, Any]:
    """Resultado simulado de ``run_socialize``."""
    bundle = tmp_path / "social" / "2026_09_23_titular"
    return {
        "bundle_dir": bundle,
        "copy_path": bundle / "social_copy.json",
        "prompts_path": bundle / "visual_prompts.json",
        "manifest_path": bundle / "manifest.json",
        "asset_paths": [],
        "markdown_paths": {},
        "platforms": ["x"],
        "title": "Titular",
        "prompt_count": 0,
        "banner_count": 0,
        "banner_failed": 0,
    }


class _FakeStdin:
    """Entrada estándar simulada para forzar el camino interactivo."""

    def isatty(self) -> bool:
        """Indica que la entrada es una terminal.

        Returns:
            bool: Siempre True.
        """
        return True


def _raise_pauta_error(**kwargs: Any) -> dict[str, Any]:
    """Simula una pauta que no se puede parsear.

    Raises:
        PautaParseError: Siempre.
    """
    raise PautaParseError("pauta rota")


def _must_not_be_called(**kwargs: Any) -> dict[str, Any]:
    """Simula un paso que no debe ejecutarse.

    Raises:
        AssertionError: Siempre, para que el test falle si se llegó a llamar.
    """
    raise AssertionError(f"no debía ejecutarse; recibió: {kwargs}")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class TestParser:
    """Estructura de los subcomandos."""

    def test_exposes_five_commands(self):
        assert cli.COMMANDS == ("report", "article", "social", "all", "clean")

    def test_describes_every_command(self):
        assert set(cli.COMMAND_DESCRIPTIONS) == set(cli.COMMANDS)

    def test_report_defaults(self):
        args = build_cli_parser().parse_args(["report"])

        assert args.command == "report"
        assert args.feeds is None
        assert args.output == "reportes"
        assert args.debug is False
        assert args.verbose is False

    def test_article_defaults(self):
        args = build_cli_parser().parse_args(["article"])

        assert args.pauta is None
        assert args.number is None
        assert args.output == "articulos"

    def test_social_defaults(self):
        args = build_cli_parser().parse_args(["social"])

        assert args.article is None
        assert args.output == "social"
        assert args.platforms is None
        assert args.social_config is None
        assert args.skip_banners is False
        assert args.skip_prompts is False

    def test_all_defaults(self):
        args = build_cli_parser().parse_args(["all"])

        assert args.base == "."
        assert args.number is None
        assert args.platforms is None
        assert args.debug is False

    def test_clean_defaults(self):
        args = build_cli_parser().parse_args(["clean"])

        assert args.base == "."
        assert args.target == "all"
        assert args.days == 30
        assert args.dry_run is False
        assert args.yes is False

    def test_clean_accepts_an_alternative_target(self):
        args = build_cli_parser().parse_args(["clean", "--target", "social"])

        assert args.target == "social"

    def test_clean_rejects_an_unknown_target(self):
        parser = build_cli_parser()

        with pytest.raises(SystemExit) as excinfo:
            parser.parse_args(["clean", "--target", "todo"])

        assert excinfo.value.code == 2

    def test_requires_a_command(self):
        parser = build_cli_parser()

        with pytest.raises(SystemExit) as excinfo:
            parser.parse_args([])

        assert excinfo.value.code == 2

    def test_rejects_an_unknown_command(self):
        parser = build_cli_parser()

        with pytest.raises(SystemExit) as excinfo:
            parser.parse_args(["explotar"])

        assert excinfo.value.code == 2

    def test_rejects_an_out_of_range_proposal_number(self):
        parser = build_cli_parser()

        with pytest.raises(SystemExit) as excinfo:
            parser.parse_args(["article", "--number", "9"])

        assert excinfo.value.code == 2

    @pytest.mark.parametrize(
        "command", ["report", "article", "social", "all", "clean"]
    )
    def test_every_command_has_a_handler(self, command):
        args = build_cli_parser().parse_args([command])

        assert callable(args.handler)


# ---------------------------------------------------------------------------
# Localización de entradas recientes
# ---------------------------------------------------------------------------


class TestFindLatest:
    """Localización de la pauta y el artículo más recientes."""

    def test_finds_the_newest_report_by_name(self, tmp_path):
        reports = tmp_path / "reportes"
        _create_file(reports / "pauta_semanal_2026_08_01.md")
        newest = _create_file(reports / "pauta_semanal_2026_09_16.md")

        assert cli.find_latest_report(reports) == newest

    def test_ignores_the_companion_json(self, tmp_path):
        reports = tmp_path / "reportes"
        _create_file(reports / "pauta_semanal_2026_09_16_companion.json")

        assert cli.find_latest_report(reports) is None

    def test_returns_none_for_a_missing_directory(self, tmp_path):
        assert cli.find_latest_report(tmp_path / "no-existe") is None

    def test_finds_the_newest_article_by_modification_date(self, tmp_path):
        articles = tmp_path / "articulos"
        _create_file(articles / "articulo_1_viejo.md", NOW - timedelta(days=5))
        newest = _create_file(articles / "articulo_2_nuevo.md", NOW)

        assert cli.find_latest_article(articles) == newest

    def test_returns_none_without_articles(self, tmp_path):
        (tmp_path / "articulos").mkdir()

        assert cli.find_latest_article(tmp_path / "articulos") is None


# ---------------------------------------------------------------------------
# Selección interactiva de la propuesta
# ---------------------------------------------------------------------------


class TestPromptForProposal:
    """Pregunta por consola qué propuesta desarrollar."""

    def test_returns_the_chosen_number(self):
        assert cli.prompt_for_proposal(_proposals(), ask=lambda _: "3") == 3

    def test_prints_the_titles(self, capsys):
        cli.prompt_for_proposal(_proposals(), ask=lambda _: "1")

        output = capsys.readouterr().out
        assert "¿Qué propuesta quieres desarrollar?" in output
        assert "1. Titular 1" in output
        assert "5. Titular 5" in output

    def test_retries_after_an_invalid_answer(self, capsys):
        answers = iter(["abc", "99", "2"])

        chosen = cli.prompt_for_proposal(
            _proposals(), ask=lambda _: next(answers)
        )

        assert chosen == 2
        assert "Opción inválida" in capsys.readouterr().out

    def test_cancels_with_q(self):
        proposals = _proposals()

        with pytest.raises(KeyboardInterrupt):
            cli.prompt_for_proposal(proposals, ask=lambda _: "q")


class TestResolveArticleNumber:
    """Resolución del número de propuesta a desarrollar."""

    def test_uses_the_given_number(self, tmp_path):
        assert cli.resolve_article_number(4, tmp_path / "pauta.md") == 4

    def test_requires_a_terminal_when_the_number_is_missing(
        self, tmp_path, capsys
    ):
        with pytest.raises(SystemExit) as excinfo:
            cli.resolve_article_number(None, tmp_path / "pauta.md")

        assert excinfo.value.code == 2
        assert "--number" in capsys.readouterr().err

    def test_reads_the_pauta_when_the_terminal_is_interactive(
        self, tmp_path, monkeypatch
    ):
        pauta = tmp_path / "pauta_semanal_2026_09_23.md"
        pauta.write_text(_pauta_markdown(), encoding="utf-8")
        monkeypatch.setattr("sys.stdin", _FakeStdin())
        monkeypatch.setattr(
            cli, "prompt_for_proposal", lambda proposals, ask=None: 2
        )

        assert cli.resolve_article_number(None, pauta) == 2

    def test_reports_a_broken_pauta(self, tmp_path, monkeypatch, capsys):
        pauta = tmp_path / "pauta.md"
        pauta.write_text("no es una pauta", encoding="utf-8")
        monkeypatch.setattr("sys.stdin", _FakeStdin())

        with pytest.raises(SystemExit) as excinfo:
            cli.resolve_article_number(None, pauta)

        assert excinfo.value.code == 1
        assert "Error al leer la pauta" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Comando report
# ---------------------------------------------------------------------------


class TestReportCommand:
    """Ejecución del subcomando ``report``."""

    def test_creates_the_output_directory_and_calls_the_pipeline(
        self, tmp_path, monkeypatch, capsys
    ):
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            cli, "run_pipeline", _capturing(calls, _report_result(tmp_path))
        )
        output = tmp_path / "salidas" / "reportes"

        main(["report", "--output", str(output)])

        assert output.is_dir()
        assert calls["output_dir"] == output
        assert calls["feeds_path"] is None
        assert calls["save_intermediate_data"] is False
        assert "Reporte generado" in capsys.readouterr().out

    def test_propagates_the_feeds_path_and_verbose(self, tmp_path, monkeypatch):
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            cli, "run_pipeline", _capturing(calls, _report_result(tmp_path))
        )

        main(
            [
                "report",
                "--feeds",
                "mis_feeds.json",
                "--output",
                str(tmp_path),
                "--verbose",
            ]
        )

        assert calls["feeds_path"] == "mis_feeds.json"
        assert calls["verbose"] is True

    def test_propagates_the_debug_flag(self, tmp_path, monkeypatch):
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            cli, "run_pipeline", _capturing(calls, _report_result(tmp_path))
        )

        main(["report", "--debug", "--output", str(tmp_path)])

        assert calls["save_intermediate_data"] is True

    def test_shows_the_companion_path_when_present(
        self, tmp_path, monkeypatch, capsys
    ):
        result = {
            **_report_result(tmp_path),
            "companion_path": tmp_path / "companion.json",
        }
        monkeypatch.setattr(cli, "run_pipeline", _capturing({}, result))

        main(["report", "--output", str(tmp_path)])

        assert "Fuentes acompañantes" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Comando article
# ---------------------------------------------------------------------------


class TestArticleCommand:
    """Ejecución del subcomando ``article``."""

    def test_uses_the_explicit_pauta_and_number(
        self, tmp_path, monkeypatch, capsys
    ):
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            cli, "write_article", _capturing(calls, _article_result(tmp_path))
        )
        output = tmp_path / "articulos"

        main(
            [
                "article",
                "--pauta",
                "reportes/pauta.md",
                "--number",
                "2",
                "--output",
                str(output),
            ]
        )

        assert calls["pauta_path"] == Path("reportes/pauta.md")
        assert calls["article_number"] == 2
        assert calls["output_dir"] == output
        assert output.is_dir()
        assert "Artículo escrito" in capsys.readouterr().out

    def test_discovers_the_latest_pauta(self, tmp_path, monkeypatch, capsys):
        _create_file(tmp_path / "reportes" / "pauta_semanal_2026_09_16.md")
        latest = _create_file(tmp_path / "reportes" / "pauta_semanal_2026_09_23.md")
        monkeypatch.chdir(tmp_path)
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            cli, "write_article", _capturing(calls, _article_result(tmp_path))
        )

        main(["article", "--number", "1", "--output", str(tmp_path / "articulos")])

        assert Path(calls["pauta_path"]).resolve() == latest.resolve()
        assert "Usando la pauta más reciente" in capsys.readouterr().out

    def test_fails_when_there_is_no_pauta(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as excinfo:
            main(
                [
                    "article",
                    "--number",
                    "1",
                    "--output",
                    str(tmp_path / "articulos"),
                ]
            )

        assert excinfo.value.code == 1
        assert "--pauta" in capsys.readouterr().err

    def test_reports_a_broken_pauta(self, tmp_path, monkeypatch, capsys):
        broken = tmp_path / "pauta.md"
        broken.write_text("no es una pauta", encoding="utf-8")
        monkeypatch.setattr(cli, "write_article", _raise_pauta_error)

        with pytest.raises(SystemExit) as excinfo:
            main(
                [
                    "article",
                    "--pauta",
                    str(broken),
                    "--number",
                    "1",
                    "--output",
                    str(tmp_path),
                ]
            )

        assert excinfo.value.code == 1
        assert "Error al leer la pauta" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Comando social
# ---------------------------------------------------------------------------


class TestSocialCommand:
    """Ejecución del subcomando ``social``."""

    def test_discovers_the_latest_article(self, tmp_path, monkeypatch, capsys):
        _create_file(
            tmp_path / "articulos" / "articulo_1_viejo.md",
            NOW - timedelta(days=2),
        )
        latest = _create_file(tmp_path / "articulos" / "articulo_2_nuevo.md", NOW)
        monkeypatch.chdir(tmp_path)
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            "news_agent.social.orchestrator.run_socialize",
            _capturing(calls, _social_result(tmp_path)),
        )

        main(["social"])

        assert Path(calls["article_path"]).resolve() == latest.resolve()
        assert calls["output_dir"] == Path("social")
        assert "Bundle de RRSS generado" in capsys.readouterr().out

    def test_fails_when_there_is_no_article(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit) as excinfo:
            main(["social"])

        assert excinfo.value.code == 1
        assert "--article" in capsys.readouterr().err

    def test_parses_the_platform_list(self, tmp_path, monkeypatch):
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            "news_agent.social.orchestrator.run_socialize",
            _capturing(calls, _social_result(tmp_path)),
        )

        main(
            [
                "social",
                "--article",
                "articulos/a.md",
                "--output",
                str(tmp_path),
                "--platforms",
                "instagram,x",
            ]
        )

        assert calls["platforms"] == ["x", "instagram"]

    def test_defaults_to_every_platform(self, tmp_path, monkeypatch):
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            "news_agent.social.orchestrator.run_socialize",
            _capturing(calls, _social_result(tmp_path)),
        )

        main(["social", "--article", "articulos/a.md", "--output", str(tmp_path)])

        assert calls["platforms"] == ["x", "facebook", "instagram"]

    def test_rejects_an_unknown_platform(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(
                [
                    "social",
                    "--article",
                    "articulos/a.md",
                    "--output",
                    str(tmp_path),
                    "--platforms",
                    "tiktok",
                ]
            )

        assert excinfo.value.code == 2
        assert "tiktok" in capsys.readouterr().err

    def test_propagates_the_skip_flags_and_brand_config(
        self, tmp_path, monkeypatch
    ):
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            "news_agent.social.orchestrator.run_socialize",
            _capturing(calls, _social_result(tmp_path)),
        )

        main(
            [
                "social",
                "--article",
                "articulos/a.md",
                "--output",
                str(tmp_path),
                "--skip-banners",
                "--skip-prompts",
                "--social-config",
                "marca.json",
            ]
        )

        assert calls["skip_banners"] is True
        assert calls["skip_prompts"] is True
        assert calls["config_path"] == "marca.json"


# ---------------------------------------------------------------------------
# Comando all
# ---------------------------------------------------------------------------


class TestAllCommand:
    """Ejecución del subcomando ``all`` (secuencia completa)."""

    @pytest.fixture
    def steps(self, tmp_path, monkeypatch) -> dict[str, Any]:
        """Registra el orden y los argumentos de los tres pasos.

        Returns:
            dict[str, Any]: Registro de llamadas y resultados simulados.
        """
        calls: dict[str, Any] = {"order": []}
        report = _report_result(tmp_path)
        article = _article_result(tmp_path)

        def _fake_pipeline(**kwargs: Any) -> dict[str, Any]:
            calls["order"].append("report")
            calls["report"] = kwargs
            return report

        def _fake_write(**kwargs: Any) -> dict[str, Any]:
            calls["order"].append("article")
            calls["article"] = kwargs
            return article

        def _fake_socialize(**kwargs: Any) -> dict[str, Any]:
            calls["order"].append("social")
            calls["social"] = kwargs
            return _social_result(tmp_path)

        monkeypatch.setattr(cli, "run_pipeline", _fake_pipeline)
        monkeypatch.setattr(cli, "write_article", _fake_write)
        monkeypatch.setattr(
            "news_agent.social.orchestrator.run_socialize", _fake_socialize
        )

        calls["report_result"] = report
        calls["article_result"] = article
        return calls

    def test_runs_the_three_steps_in_order(self, tmp_path, steps, capsys):
        main(["all", "--base", str(tmp_path), "--number", "1"])

        assert steps["order"] == ["report", "article", "social"]
        output = capsys.readouterr().out
        assert "Paso 1/3" in output
        assert "Paso 3/3" in output
        assert "Secuencia completa finalizada" in output

    def test_chains_the_generated_artifacts(self, tmp_path, steps):
        main(["all", "--base", str(tmp_path), "--number", "1"])

        assert (
            steps["article"]["pauta_path"]
            == steps["report_result"]["report_path"]
        )
        assert (
            steps["social"]["article_path"]
            == steps["article_result"]["article_path"]
        )

    def test_creates_the_three_output_directories(self, tmp_path, steps):
        main(["all", "--base", str(tmp_path), "--number", "1"])

        assert (tmp_path / "reportes").is_dir()
        assert (tmp_path / "articulos").is_dir()
        assert (tmp_path / "social").is_dir()

    def test_uses_the_requested_proposal_number(self, tmp_path, steps):
        main(["all", "--base", str(tmp_path), "--number", "3"])

        assert steps["article"]["article_number"] == 3

    def test_propagates_the_social_options(self, tmp_path, steps):
        main(
            [
                "all",
                "--base",
                str(tmp_path),
                "--number",
                "1",
                "--platforms",
                "x",
                "--skip-banners",
            ]
        )

        assert steps["social"]["platforms"] == ["x"]
        assert steps["social"]["skip_banners"] is True
        assert steps["social"]["skip_prompts"] is False

    def test_prompts_when_the_number_is_missing(
        self, tmp_path, steps, monkeypatch
    ):
        monkeypatch.setattr("sys.stdin", _FakeStdin())
        monkeypatch.setattr(
            cli, "prompt_for_proposal", lambda proposals, ask=None: 2
        )

        main(["all", "--base", str(tmp_path)])

        assert steps["article"]["article_number"] == 2

    def test_requires_a_number_without_a_terminal(self, tmp_path, steps, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["all", "--base", str(tmp_path)])

        assert excinfo.value.code == 2
        assert "--number" in capsys.readouterr().err
        assert steps["order"] == ["report"]


# ---------------------------------------------------------------------------
# Comando clean
# ---------------------------------------------------------------------------


class TestCleanCommand:
    """Ejecución del subcomando ``clean``."""

    def _old_report(self, base: Path) -> Path:
        """Crea una pauta antigua respecto de HOY."""
        return _create_file(
            base / "reportes" / "pauta_semanal_2026_08_01.md"
        )

    def _old_article(self, base: Path) -> Path:
        """Crea un artículo antiguo respecto de HOY."""
        return _create_file(
            base / "articulos" / "articulo_1_slug.md",
            datetime.now(timezone.utc) - timedelta(days=90),
        )

    def test_dry_run_lists_the_candidates_without_deleting(self, tmp_path, capsys):
        old = self._old_report(tmp_path)

        main(["clean", "--base", str(tmp_path), "--dry-run"])

        output = capsys.readouterr().out
        assert "pauta_semanal_2026_08_01.md" in output
        assert "Modo simulación" in output
        assert old.exists()

    def test_yes_deletes_the_old_artifacts(self, tmp_path, capsys):
        old = self._old_report(tmp_path)

        main(["clean", "--base", str(tmp_path), "--yes"])

        assert not old.exists()
        assert "Artefactos eliminados: 1" in capsys.readouterr().out

    def test_confirmation_can_abort(self, tmp_path, monkeypatch, capsys):
        old = self._old_report(tmp_path)
        monkeypatch.setattr("builtins.input", lambda _: "n")

        main(["clean", "--base", str(tmp_path)])

        assert old.exists()
        assert "Limpieza cancelada" in capsys.readouterr().out

    def test_confirmation_accepts_an_affirmative_answer(self, tmp_path, monkeypatch):
        old = self._old_report(tmp_path)
        monkeypatch.setattr("builtins.input", lambda _: "s")

        main(["clean", "--base", str(tmp_path)])

        assert not old.exists()

    def test_informs_when_there_is_nothing_to_delete(self, tmp_path, capsys):
        _create_file(tmp_path / "reportes" / "pauta_semanal_2026_09_23.md")

        main(["clean", "--base", str(tmp_path)])

        assert "No hay artefactos" in capsys.readouterr().out

    def test_rejects_a_non_positive_days_value(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["clean", "--base", str(tmp_path), "--days", "0"])

        assert excinfo.value.code == 2
        assert "--days" in capsys.readouterr().err

    def test_limits_the_scope_with_target(self, tmp_path):
        report = self._old_report(tmp_path)
        article = self._old_article(tmp_path)

        main(["clean", "--base", str(tmp_path), "--target", "reports", "--yes"])

        assert not report.exists()
        assert article.exists()

    def test_keeps_the_brand_assets_and_the_cache(self, tmp_path):
        _create_file(
            tmp_path / "social" / "2026_01_01_titular" / "assets" / "card.png",
            datetime.now(timezone.utc) - timedelta(days=365),
        )
        cache = _create_file(
            tmp_path / "cache" / "enriched_content.json",
            datetime.now(timezone.utc) - timedelta(days=365),
        )

        main(["clean", "--base", str(tmp_path), "--yes"])

        assert cache.exists()


# ---------------------------------------------------------------------------
# Interrupción y enrutado
# ---------------------------------------------------------------------------


class TestBareInvocation:
    """Invocación sin argumentos: nunca ejecuta el pipeline."""

    def test_shows_the_help_and_exits_with_a_usage_error(self, monkeypatch, capsys):
        monkeypatch.setattr(
            "news_agent.__main__.run_pipeline", _must_not_be_called
        )

        with pytest.raises(SystemExit) as excinfo:
            main([])

        assert excinfo.value.code == 2
        output = capsys.readouterr().out
        assert "Comandos simplificados" in output
        assert "report" in output

    def test_explains_the_command_syntax(self, capsys):
        with pytest.raises(SystemExit):
            main([])

        assert "Usa '-h' después de un comando" in capsys.readouterr().out


class TestOutputDirectory:
    """El CLI nunca escribe en el directorio actual."""

    def test_report_defaults_to_the_reports_folder(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            cli, "run_pipeline", _capturing(calls, _report_result(tmp_path))
        )

        main(["report"])

        assert calls["output_dir"] == Path("reportes")
        assert (tmp_path / "reportes").is_dir()

    def test_article_defaults_to_the_articles_folder(self, tmp_path, monkeypatch):
        _create_file(tmp_path / "reportes" / "pauta_semanal_2026_09_23.md")
        monkeypatch.chdir(tmp_path)
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            cli, "write_article", _capturing(calls, _article_result(tmp_path))
        )

        main(["article", "--number", "1"])

        assert calls["output_dir"] == Path("articulos")
        assert (tmp_path / "articulos").is_dir()

    def test_social_defaults_to_the_social_folder(self, tmp_path, monkeypatch):
        _create_file(tmp_path / "articulos" / "articulo_1_slug.md", NOW)
        monkeypatch.chdir(tmp_path)
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            "news_agent.social.orchestrator.run_socialize",
            _capturing(calls, _social_result(tmp_path)),
        )

        main(["social"])

        assert calls["output_dir"] == Path("social")
        assert (tmp_path / "social").is_dir()

    def test_legacy_pipeline_defaults_to_the_reports_folder(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            "news_agent.__main__.run_pipeline",
            _capturing(calls, _report_result(tmp_path)),
        )

        main(["--feeds", "rss_feeds.json"])

        assert calls["output_dir"] == Path("reportes")
        assert (tmp_path / "reportes").is_dir()

    def test_rejects_the_current_directory_as_output(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(cli, "run_pipeline", _must_not_be_called)

        with pytest.raises(SystemExit) as excinfo:
            main(["report", "--output", "."])

        assert excinfo.value.code == 2
        assert "directorio actual" in capsys.readouterr().err

    def test_rejects_the_current_directory_in_the_legacy_mode(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "news_agent.__main__.run_pipeline", _must_not_be_called
        )

        with pytest.raises(SystemExit) as excinfo:
            main(["--feeds", "rss_feeds.json", "--output", "."])

        assert excinfo.value.code == 2
        assert "directorio actual" in capsys.readouterr().err

    def test_rejects_the_current_directory_in_the_article_mode(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(cli, "write_article", _must_not_be_called)

        with pytest.raises(SystemExit) as excinfo:
            main(
                [
                    "article",
                    "--pauta",
                    "reportes/pauta.md",
                    "--number",
                    "1",
                    "--output",
                    ".",
                ]
            )

        assert excinfo.value.code == 2
        assert "directorio actual" in capsys.readouterr().err

    def test_resolve_output_dir_rejects_the_current_directory(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)

        with pytest.raises(cli.OutputDirectoryError):
            cli.resolve_output_dir(".")

    def test_resolve_output_dir_requires_a_path_or_a_default(self):
        with pytest.raises(cli.OutputDirectoryError):
            cli.resolve_output_dir(None)

    def test_resolve_output_dir_creates_the_folder(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        resolved = cli.resolve_output_dir(None, "reportes")

        assert resolved == Path("reportes")
        assert (tmp_path / "reportes").is_dir()


class TestInterrupt:
    """Interrupción con Ctrl+C."""

    def test_reports_a_keyboard_interrupt(self, tmp_path, monkeypatch, capsys):
        def _interrupt(**kwargs: Any) -> dict[str, Any]:
            raise KeyboardInterrupt

        monkeypatch.setattr(cli, "run_pipeline", _interrupt)

        with pytest.raises(SystemExit) as excinfo:
            cli.run(["report", "--output", str(tmp_path)])

        assert excinfo.value.code == 130
        assert "cancelada" in capsys.readouterr().err


class TestMainDispatch:
    """Enrutado entre el CLI simplificado y los modos clásicos."""

    def test_routes_a_subcommand_to_the_new_cli(self, tmp_path, monkeypatch):
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            cli, "run_pipeline", _capturing(calls, _report_result(tmp_path))
        )

        main(["report", "--output", str(tmp_path / "reportes")])

        assert calls["output_dir"] == tmp_path / "reportes"

    def test_rejects_an_unknown_command(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["explotar"])

        assert excinfo.value.code == 2
        err = capsys.readouterr().err
        assert "comando desconocido" in err
        assert "clean" in err

    def test_keeps_the_legacy_flag_interface(self, tmp_path, monkeypatch):
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            "news_agent.__main__.run_pipeline",
            _capturing(calls, _report_result(tmp_path)),
        )

        main(["--feeds", "rss_feeds.json", "--output", str(tmp_path)])

        assert calls["feeds_path"] == "rss_feeds.json"

    def test_does_not_confuse_an_output_value_with_a_command(
        self, tmp_path, monkeypatch
    ):
        # '--output social' debe seguir siendo el modo clásico, no el
        # subcomando 'social'.
        monkeypatch.chdir(tmp_path)
        calls: dict[str, Any] = {}
        monkeypatch.setattr(
            "news_agent.__main__.run_pipeline",
            _capturing(calls, _report_result(tmp_path)),
        )

        main(["--output", "social"])

        assert calls["output_dir"] == Path("social")
