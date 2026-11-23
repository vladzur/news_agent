"""Tests del subcomando ``cover`` (portadas editoriales)."""

from pathlib import Path
from typing import Any

import pytest

from news_agent.__main__ import main


def _cover_result(tmp_path: Path, skipped: bool = False) -> dict[str, Any]:
    """Resultado simulado de ``run_cover``.

    Args:
        tmp_path: Directorio base de la prueba.
        skipped: Si la portada se omitió por existir.

    Returns:
        dict[str, Any]: Resultado con el contrato del orquestador.
    """
    bundle = tmp_path / "portadas" / "2026_11_23_titular"
    return {
        "bundle_dir": bundle,
        "title": "Titular",
        "category": "Nacional",
        "treatment": "text_first",
        "treatment_label": "Editorial tipográfica",
        "formats": [
            {
                "name": "og",
                "width": 1200,
                "height": 630,
                "path": bundle / "portada_og.png",
                "error": None,
            },
            {
                "name": "web",
                "width": 1600,
                "height": 900,
                "path": bundle / "portada_web.png",
                "error": None,
            },
        ],
        "metadata_path": bundle / "portada.json",
        "alt_text": "Alt de prueba",
        "warnings": ["Una advertencia"],
        "skipped": skipped,
        "failed_count": 0,
    }


class TestCoverCommand:
    """Ejecución del subcomando ``cover``."""

    def _article(self, base: Path, number: int = 1) -> Path:
        """Crea un artículo de prueba.

        Args:
            base: Directorio base.
            number: Número editorial.

        Returns:
            Path: Ruta del artículo creado.
        """
        path = base / "articulos" / f"articulo_{number}_titular.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Titular\n", encoding="utf-8")
        return path

    def test_runs_the_cover_on_an_article(
        self, tmp_path, monkeypatch, capsys
    ):
        article = self._article(tmp_path)
        calls: dict[str, Any] = {}

        def _fake(**kwargs: Any) -> dict[str, Any]:
            calls.update(kwargs)
            return _cover_result(tmp_path)

        monkeypatch.setattr(
            "news_agent.cover.orchestrator.run_cover", _fake
        )

        main(
            [
                "cover",
                "--article",
                str(article),
                "--output",
                str(tmp_path / "portadas"),
                "--category",
                "Opinión",
                "--treatment",
                "quote",
                "--force",
            ]
        )

        assert calls["article_path"] == article
        assert calls["category"] == "Opinión"
        assert calls["treatment"] == "quote"
        assert calls["force"] is True
        output = capsys.readouterr().out
        assert "Portada editorial generada" in output
        assert "Nacional" in output
        assert "Una advertencia" in output

    def test_prints_the_skip_message(
        self, tmp_path, monkeypatch, capsys
    ):
        article = self._article(tmp_path)

        monkeypatch.setattr(
            "news_agent.cover.orchestrator.run_cover",
            lambda **kwargs: _cover_result(tmp_path, skipped=True),
        )

        main(
            [
                "cover",
                "--article",
                str(article),
                "--output",
                str(tmp_path / "portadas"),
            ]
        )

        output = capsys.readouterr().out
        assert "ya existente" in output
        assert "--force" in output

    def test_processes_every_article_with_all(
        self, tmp_path, monkeypatch, capsys
    ):
        self._article(tmp_path, 1)
        self._article(tmp_path, 2)
        calls: list[Path] = []

        def _fake(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs["article_path"])
            return _cover_result(tmp_path)

        monkeypatch.setattr(
            "news_agent.cover.orchestrator.run_cover", _fake
        )

        main(
            [
                "cover",
                "--all",
                "--articles-dir",
                str(tmp_path / "articulos"),
                "--output",
                str(tmp_path / "portadas"),
            ]
        )

        assert len(calls) == 2
        output = capsys.readouterr().out
        assert "Portada 1/2" in output
        assert "Portada 2/2" in output

    def test_continues_after_a_failed_article(
        self, tmp_path, monkeypatch, capsys
    ):
        self._article(tmp_path, 1)
        self._article(tmp_path, 2)
        calls: list[Path] = []

        def _fake(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs["article_path"])
            if kwargs["article_path"].name.startswith("articulo_1"):
                raise SystemExit(1)
            return _cover_result(tmp_path)

        monkeypatch.setattr(
            "news_agent.cover.orchestrator.run_cover", _fake
        )

        with pytest.raises(SystemExit) as excinfo:
            main(
                [
                    "cover",
                    "--all",
                    "--articles-dir",
                    str(tmp_path / "articulos"),
                    "--output",
                    str(tmp_path / "portadas"),
                ]
            )

        assert excinfo.value.code == 1
        assert len(calls) == 2
        assert "no se pudieron procesar" in capsys.readouterr().err
