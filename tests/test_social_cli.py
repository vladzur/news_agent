"""Tests del CLI para el modo de repurposing de RRSS."""

from pathlib import Path

import pytest

from news_agent.__main__ import build_parser, main

ARGS = ["--socialize", "articulos/articulo_1_slug.md"]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Argumentos del modo --socialize."""

    def test_socialize_is_optional(self):
        args = build_parser().parse_args([])

        assert args.socialize is None

    def test_parses_the_article_path(self):
        args = build_parser().parse_args(ARGS)

        assert args.socialize == "articulos/articulo_1_slug.md"

    def test_social_flags_default_to_off(self):
        args = build_parser().parse_args(ARGS)

        assert args.platforms is None
        assert args.social_config is None
        assert args.skip_banners is False
        assert args.skip_prompts is False

    def test_parses_the_platform_list(self):
        args = build_parser().parse_args(ARGS + ["--platforms", "x,instagram"])

        assert args.platforms == "x,instagram"

    def test_parses_the_skip_flags(self):
        args = build_parser().parse_args(ARGS + ["--skip-banners", "--skip-prompts"])

        assert args.skip_banners is True
        assert args.skip_prompts is True

    def test_parses_the_brand_config_path(self):
        args = build_parser().parse_args(ARGS + ["--social-config", "marca.json"])

        assert args.social_config == "marca.json"

    def test_keeps_the_existing_modes_available(self):
        args = build_parser().parse_args(["--feeds", "rss_feeds.json"])

        assert args.feeds == "rss_feeds.json"
        assert args.socialize is None


# ---------------------------------------------------------------------------
# Validación de combinaciones
# ---------------------------------------------------------------------------


class TestArgumentValidation:
    """Exclusión mutua entre modos y banderas huérfanas."""

    def test_rejects_socialize_with_write_article(self):
        with pytest.raises(SystemExit) as excinfo:
            main(ARGS + ["--write-article", "reportes/pauta.md", "--article", "1"])

        assert excinfo.value.code == 2

    def test_rejects_socialize_with_feeds(self):
        with pytest.raises(SystemExit) as excinfo:
            main(ARGS + ["--feeds", "rss_feeds.json"])

        assert excinfo.value.code == 2

    def test_rejects_socialize_with_debug(self):
        with pytest.raises(SystemExit) as excinfo:
            main(ARGS + ["--debug"])

        assert excinfo.value.code == 2

    def test_rejects_socialize_with_article(self):
        with pytest.raises(SystemExit) as excinfo:
            main(ARGS + ["--article", "1"])

        assert excinfo.value.code == 2

    def test_rejects_platforms_without_socialize(self):
        with pytest.raises(SystemExit) as excinfo:
            main(["--platforms", "x"])

        assert excinfo.value.code == 2

    def test_rejects_skip_banners_without_socialize(self):
        with pytest.raises(SystemExit) as excinfo:
            main(["--skip-banners"])

        assert excinfo.value.code == 2

    def test_rejects_skip_prompts_without_socialize(self):
        with pytest.raises(SystemExit) as excinfo:
            main(["--skip-prompts"])

        assert excinfo.value.code == 2

    def test_rejects_an_unknown_platform(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(ARGS + ["--platforms", "tiktok"])

        assert excinfo.value.code == 2
        assert "tiktok" in capsys.readouterr().err

    def test_requires_article_number_for_the_article_mode(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["--write-article", "reportes/pauta.md"])

        assert excinfo.value.code == 1
        assert "--article" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Ejecución del modo social
# ---------------------------------------------------------------------------


class TestSocializeMode:
    """Invocación del orquestador desde el CLI."""

    @pytest.fixture
    def fake_result(self, tmp_path: Path) -> dict:
        """Resultado simulado del orquestador de RRSS."""
        bundle = tmp_path / "social" / "2026_09_14_titular"
        bundle.mkdir(parents=True)
        return {
            "bundle_dir": bundle,
            "copy_path": bundle / "social_copy.json",
            "prompts_path": bundle / "visual_prompts.json",
            "manifest_path": bundle / "manifest.json",
            "asset_paths": [bundle / "assets" / "headline_card_x.png"],
            "markdown_paths": {"x": bundle / "x_thread.md"},
            "platforms": ["x"],
            "title": "Titular de prueba",
            "prompt_count": 1,
            "banner_count": 1,
            "banner_failed": 0,
        }

    @pytest.fixture
    def captured(self, monkeypatch, fake_result):
        """Captura los argumentos con que el CLI invoca al orquestador."""
        calls: dict = {}

        def _fake_run_socialize(**kwargs):
            calls.update(kwargs)
            return fake_result

        monkeypatch.setattr(
            "news_agent.social.orchestrator.run_socialize", _fake_run_socialize
        )
        return calls

    def test_passes_the_article_and_output_directory(self, capsys, captured):
        main(ARGS + ["--output", "./social"])

        assert captured["article_path"] == "articulos/articulo_1_slug.md"
        assert captured["output_dir"] == "./social"

    def test_parses_the_platform_list_before_calling(self, captured):
        main(ARGS + ["--platforms", "instagram,x"])

        assert captured["platforms"] == ["x", "instagram"]

    def test_defaults_to_every_platform(self, captured):
        main(ARGS)

        assert captured["platforms"] == ["x", "facebook", "instagram"]

    def test_propagates_the_skip_flags(self, captured):
        main(ARGS + ["--skip-banners", "--skip-prompts"])

        assert captured["skip_banners"] is True
        assert captured["skip_prompts"] is True

    def test_does_not_skip_anything_by_default(self, captured):
        main(ARGS)

        assert captured["skip_banners"] is False
        assert captured["skip_prompts"] is False

    def test_propagates_the_verbose_flag(self, captured):
        main(ARGS + ["--verbose"])

        assert captured["verbose"] is True

    def test_propagates_the_brand_config_path(self, captured):
        main(ARGS + ["--social-config", "marca.json"])

        assert captured["config_path"] == "marca.json"

    def test_prints_the_bundle_summary(self, capsys, captured, fake_result):
        main(ARGS)

        output = capsys.readouterr().out
        assert "Bundle de RRSS generado" in output
        assert str(fake_result["bundle_dir"]) in output
        assert fake_result["title"] in output
        assert str(fake_result["copy_path"]) in output

    def test_reports_failed_banners(self, capsys, monkeypatch, fake_result):
        failed = {**fake_result, "banner_failed": 2, "banner_count": 4}
        monkeypatch.setattr(
            "news_agent.social.orchestrator.run_socialize",
            lambda **kwargs: failed,
        )

        main(ARGS)

        assert "Banners fallidos: 2" in capsys.readouterr().out

    def test_handles_a_keyboard_interrupt(self, monkeypatch, capsys):
        def _interrupt(**kwargs):
            raise KeyboardInterrupt

        monkeypatch.setattr(
            "news_agent.social.orchestrator.run_socialize", _interrupt
        )

        with pytest.raises(SystemExit) as excinfo:
            main(ARGS)

        assert excinfo.value.code == 130
        assert "cancelada" in capsys.readouterr().err
