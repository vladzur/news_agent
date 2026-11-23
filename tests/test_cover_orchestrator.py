"""Tests del orquestador de portadas editoriales."""

import json
from pathlib import Path

import pytest

from news_agent.cover import orchestrator
from news_agent.cover.orchestrator import CoverError, run_cover
from news_agent.cover.renderer import CoverRenderError

CONFIG_PATH = Path(__file__).resolve().parent.parent / "social_config.json"


def _run(article_path: Path, output_dir: Path, **overrides) -> dict:
    """Ejecuta ``run_cover`` con la configuración real del repositorio.

    Args:
        article_path: Artículo de entrada.
        output_dir: Directorio de salida.
        **overrides: Parámetros que se quieren reemplazar.

    Returns:
        dict: Resultado del orquestador.
    """
    params = {
        "article_path": article_path,
        "output_dir": output_dir,
        "config_path": CONFIG_PATH,
    }
    params.update(overrides)
    return run_cover(**params)


class TestRunCover:
    """Flujo completo sobre un artículo válido."""

    def test_returns_the_documented_contract(
        self, cover_article_file, tmp_path
    ):
        result = _run(cover_article_file, tmp_path / "portadas")

        assert {
            "bundle_dir",
            "title",
            "category",
            "treatment",
            "treatment_label",
            "formats",
            "metadata_path",
            "alt_text",
            "warnings",
            "skipped",
            "failed_count",
        } <= set(result)
        assert result["skipped"] is False
        assert result["failed_count"] == 0

    def test_creates_the_bundle_with_the_two_png_and_the_manifest(
        self, cover_article_file, tmp_path
    ):
        result = _run(cover_article_file, tmp_path / "portadas")
        bundle = result["bundle_dir"]

        assert bundle.is_dir()
        assert (bundle / "portada_og.png").is_file()
        assert (bundle / "portada_web.png").is_file()
        assert (bundle / "portada.json").is_file()
        assert bundle.name.startswith(
            "2026_11_23_cierre-de-la-escuela-rural"
        )

    def test_infers_the_section_from_the_article_number(
        self, cover_article_file, tmp_path
    ):
        result = _run(cover_article_file, tmp_path / "portadas")

        assert result["category"] == "Nacional"

    def test_writes_the_manifest_with_the_expected_fields(
        self, cover_article_file, tmp_path
    ):
        result = _run(cover_article_file, tmp_path / "portadas")
        metadata = json.loads(
            Path(result["metadata_path"]).read_text(encoding="utf-8")
        )

        assert metadata["title"].startswith("Cierre de la escuela rural")
        assert metadata["category"] == "Nacional"
        assert metadata["treatment"] == "data"
        assert metadata["figure"] == "42 familias"
        assert metadata["header_image"] == "portada_web.png"
        assert metadata["og_image"] == "portada_og.png"
        assert metadata["alt_text"]
        assert metadata["source_sha256"]
        assert [item["name"] for item in metadata["formats"]] == ["og", "web"]

    def test_uses_the_article_date_in_the_bundle_name(
        self, cover_article_file, tmp_path
    ):
        result = _run(cover_article_file, tmp_path / "portadas")

        assert result["bundle_dir"].name.startswith("2026_11_23_")

    def test_respects_an_explicit_category(
        self, cover_article_file, tmp_path
    ):
        result = _run(
            cover_article_file,
            tmp_path / "portadas",
            category="Opinión",
        )

        assert result["category"] == "Opinión"
        assert result["treatment"] == "quote"

    def test_respects_an_explicit_treatment(
        self, cover_article_file, tmp_path
    ):
        result = _run(
            cover_article_file,
            tmp_path / "portadas",
            category="Política",
            treatment="text_first",
        )

        assert result["treatment"] == "text_first"


class TestIdempotency:
    """Omisión y regeneración de portadas existentes."""

    def test_skips_an_equivalent_cover(self, cover_article_file, tmp_path):
        output = tmp_path / "portadas"
        first = _run(cover_article_file, output)
        second = _run(cover_article_file, output)

        assert first["skipped"] is False
        assert second["skipped"] is True
        assert second["metadata_path"] == first["metadata_path"]

    def test_force_regenerates_the_cover(self, cover_article_file, tmp_path):
        output = tmp_path / "portadas"
        _run(cover_article_file, output)
        forced = _run(cover_article_file, output, force=True)

        assert forced["skipped"] is False

    def test_regenerates_when_the_treatment_changes(
        self, cover_article_file, tmp_path
    ):
        output = tmp_path / "portadas"
        _run(cover_article_file, output)
        changed = _run(
            cover_article_file, output, category="Opinión"
        )

        assert changed["skipped"] is False
        assert changed["treatment"] == "quote"


class TestErrors:
    """Errores fatales y tolerancia a fallos."""

    def test_aborts_when_the_article_does_not_exist(self, tmp_path):
        with pytest.raises(CoverError) as excinfo:
            _run(tmp_path / "no-existe.md", tmp_path / "portadas")

        assert excinfo.value.code == 1
        assert "no se pudo leer" in str(excinfo.value).lower()

    def test_aborts_with_code_two_for_an_unknown_category(
        self, cover_article_file, tmp_path
    ):
        with pytest.raises(CoverError) as excinfo:
            _run(
                cover_article_file,
                tmp_path / "portadas",
                category="Deportes",
            )

        assert excinfo.value.code == 2
        assert "Sección desconocida" in str(excinfo.value)

    def test_aborts_with_code_two_for_an_unknown_treatment(
        self, cover_article_file, tmp_path
    ):
        with pytest.raises(CoverError) as excinfo:
            _run(
                cover_article_file,
                tmp_path / "portadas",
                treatment="collage",
            )

        assert excinfo.value.code == 2

    def test_aborts_when_the_config_is_invalid(self, cover_article_file, tmp_path):
        config = tmp_path / "config.json"
        config.write_text("{}", encoding="utf-8")

        with pytest.raises(CoverError) as excinfo:
            _run(
                cover_article_file,
                tmp_path / "portadas",
                config_path=config,
            )

        assert excinfo.value.code == 1
        assert "configuración" in str(excinfo.value).lower()

    def test_keeps_the_other_format_when_one_fails(
        self, cover_article_file, tmp_path, monkeypatch
    ):
        original = orchestrator.render_cover

        def _flaky(content, format_spec, config, specs):
            if format_spec.name == "og":
                raise CoverRenderError("fallo simulado")
            return original(content, format_spec, config, specs)

        monkeypatch.setattr(orchestrator, "render_cover", _flaky)

        result = _run(cover_article_file, tmp_path / "portadas")
        failed = [
            item for item in result["formats"] if item["path"] is None
        ]

        assert result["failed_count"] == 1
        assert len(failed) == 1
        assert failed[0]["name"] == "og"
        assert (result["bundle_dir"] / "portada_web.png").is_file()
        assert (result["bundle_dir"] / "portada.json").is_file()
