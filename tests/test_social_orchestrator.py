"""Tests del orquestador del subsistema de RRSS."""

import json

import pytest

from news_agent.config import ConfigurationError
from news_agent.social import orchestrator
from news_agent.social.orchestrator import normalize_platforms, run_socialize

# ---------------------------------------------------------------------------
# Doble del cliente LLM
# ---------------------------------------------------------------------------


class FakeLLMClient:
    """Cliente LLM falso que responde según el tipo de prompt recibido.

    El orquestador hace dos llamadas con system prompts distintos (copys y
    prompts visuales), así que el doble despacha por el contenido del prompt.
    """

    def __init__(
        self,
        copy_response: str,
        visual_response: str,
        response_format: dict | None = None,
    ) -> None:
        self.copy_response = copy_response
        self.visual_response = visual_response
        # El orquestador hereda este atributo para no volver a pedir un
        # formato de respuesta que la API ya rechazó.
        self.response_format = response_format
        self.system_prompts: list[str] = []

    def generate_report(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompts.append(system_prompt)
        if "prompt engineer" in system_prompt.lower():
            return self.visual_response
        return self.copy_response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api_key(monkeypatch):
    """Sustituye la validación de la API key por una clave de prueba."""
    monkeypatch.setattr(orchestrator, "get_api_key", lambda: "clave-de-prueba")


@pytest.fixture
def llm(monkeypatch, copy_payload, visual_payload):
    """Instala un cliente LLM falso que responde a ambas etapas."""
    fake = FakeLLMClient(
        copy_response=json.dumps(copy_payload, ensure_ascii=False),
        visual_response=json.dumps(visual_payload, ensure_ascii=False),
    )
    monkeypatch.setattr(orchestrator, "LLMClient", lambda **kwargs: fake)
    return fake


@pytest.fixture
def run(api_key, llm, article_file, config_file, tmp_path):
    """Ejecuta el flujo completo sobre un artículo de ejemplo.

    Returns:
        tuple: (resultado del orquestador, directorio base de salida).
    """
    output_dir = tmp_path / "salida"

    def _run(**overrides):
        params = {
            "article_path": article_file,
            "output_dir": output_dir,
            "config_path": config_file,
        }
        params.update(overrides)
        return run_socialize(**params)

    return _run, output_dir


# ---------------------------------------------------------------------------
# Normalización de plataformas
# ---------------------------------------------------------------------------


class TestNormalizePlatforms:
    """Validación de la lista de plataformas."""

    def test_returns_every_platform_by_default(self):
        assert normalize_platforms(None) == ["x", "facebook", "instagram"]

    def test_keeps_the_editorial_order(self):
        assert normalize_platforms(["instagram", "x"]) == ["x", "instagram"]

    def test_raises_for_an_unknown_platform(self):
        with pytest.raises(ValueError, match="desconocida"):
            normalize_platforms(["tiktok"])


# ---------------------------------------------------------------------------
# Ejecución correcta
# ---------------------------------------------------------------------------


class TestRunSocialize:
    """Flujo completo sobre un artículo válido."""

    def test_returns_the_documented_contract(self, run):
        runner, _ = run

        result = runner()

        assert {
            "bundle_dir",
            "copy_path",
            "prompts_path",
            "manifest_path",
            "asset_paths",
            "markdown_paths",
            "platforms",
            "title",
            "prompt_count",
            "banner_count",
            "banner_failed",
        } <= set(result)

    def test_creates_the_bundle_inside_the_output_directory(self, run):
        runner, output_dir = run

        result = runner()

        assert result["bundle_dir"].is_dir()
        assert output_dir in result["bundle_dir"].parents

    def test_bundle_name_combines_date_and_title_slug(self, run, article):
        runner, _ = run

        result = runner()

        assert result["bundle_dir"].name.startswith("20")
        assert "disparo" in result["bundle_dir"].name

    def test_keeps_the_article_title(self, run, article):
        runner, _ = run

        result = runner()

        assert result["title"] == article.title

    def test_writes_the_copy_and_prompt_json(self, run):
        runner, _ = run

        result = runner()

        assert result["copy_path"].is_file()
        assert result["prompts_path"] is not None
        assert result["prompts_path"].is_file()
        assert result["prompt_count"] == 3

    def test_copy_json_has_the_full_thread(self, run):
        runner, _ = run

        result = runner()

        payload = json.loads(result["copy_path"].read_text(encoding="utf-8"))
        assert len(payload["x"]["thread"]) >= 5
        assert payload["quote_card"]["verbatim"] is True

    def test_writes_one_markdown_per_platform(self, run):
        runner, _ = run

        result = runner()

        assert set(result["markdown_paths"]) == {"x", "facebook", "instagram"}
        for path in result["markdown_paths"].values():
            assert path.is_file()

    def test_renders_the_banners(self, run):
        runner, _ = run

        result = runner()

        assert result["banner_count"] == 6
        assert result["banner_failed"] == 0
        for path in result["asset_paths"]:
            assert path.is_file()
            assert path.suffix == ".png"

    def test_writes_the_manifest(self, run):
        runner, _ = run

        result = runner()

        payload = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
        assert payload["banners"]["rendered"] == 6
        assert payload["visual_prompts"]["count"] == 3

    def test_uses_both_llm_stages(self, run, llm):
        runner, _ = run

        runner()

        assert len(llm.system_prompts) == 2

    def test_creates_the_output_directory_when_missing(self, run):
        runner, output_dir = run
        assert not output_dir.exists()

        runner()

        assert output_dir.is_dir()

    def test_limits_the_platforms_on_request(self, run):
        runner, _ = run

        result = runner(platforms=["x"])

        assert result["platforms"] == ["x"]
        assert set(result["markdown_paths"]) == {"x"}
        assert result["banner_count"] == 1

    def test_can_skip_the_banners(self, run):
        runner, _ = run

        result = runner(skip_banners=True)

        assert result["banner_count"] == 0
        assert result["asset_paths"] == []
        assert result["copy_path"].is_file()

    def test_can_skip_the_visual_prompts(self, run):
        runner, _ = run

        result = runner(skip_prompts=True)

        assert result["prompts_path"] is None
        assert result["prompt_count"] == 0
        assert result["copy_path"].is_file()

    def test_reuses_the_same_bundle_for_the_same_article(self, run):
        runner, _ = run

        first = runner()
        second = runner()

        assert first["bundle_dir"] == second["bundle_dir"]


# ---------------------------------------------------------------------------
# Guardas
# ---------------------------------------------------------------------------


class TestRunSocializeGuards:
    """Abortos controlados antes de gastar tokens."""

    def test_aborts_when_the_article_does_not_exist(self, run, tmp_path):
        runner, _ = run

        with pytest.raises(SystemExit) as excinfo:
            runner(article_path=tmp_path / "inexistente.md")

        assert excinfo.value.code == 1

    def test_aborts_when_the_article_is_too_short(self, run, tmp_path):
        runner, _ = run
        short = tmp_path / "corto.md"
        short.write_text(
            "# Titular\n\n**Por La Chispa Sur**\n\n---\n\nCuerpo demasiado breve.\n",
            encoding="utf-8",
        )

        with pytest.raises(SystemExit) as excinfo:
            runner(article_path=short)

        assert excinfo.value.code == 1

    def test_does_not_call_the_model_when_the_article_is_too_short(
        self, run, tmp_path, llm
    ):
        runner, _ = run
        short = tmp_path / "corto.md"
        short.write_text(
            "# Titular\n\n---\n\nCuerpo demasiado breve.\n", encoding="utf-8"
        )

        with pytest.raises(SystemExit):
            runner(article_path=short)

        assert llm.system_prompts == []

    def test_aborts_when_the_api_key_is_missing(self, run, monkeypatch):
        runner, _ = run

        def _raise() -> str:
            raise ConfigurationError("Falta DEEPSEEK_API_KEY.")

        monkeypatch.setattr(orchestrator, "get_api_key", _raise)

        with pytest.raises(SystemExit) as excinfo:
            runner()

        assert excinfo.value.code == 1

    def test_aborts_when_the_brand_config_does_not_exist(self, run, tmp_path):
        runner, _ = run

        with pytest.raises(SystemExit) as excinfo:
            runner(config_path=tmp_path / "inexistente.json")

        assert excinfo.value.code == 1

    def test_aborts_when_the_copys_cannot_be_generated(self, run, monkeypatch, tmp_path):
        runner, _ = run
        monkeypatch.setattr(
            orchestrator,
            "LLMClient",
            lambda **kwargs: FakeLLMClient("no es json", "no es json"),
        )

        with pytest.raises(SystemExit) as excinfo:
            runner()

        assert excinfo.value.code == 1


# ---------------------------------------------------------------------------
# Tolerancia a fallos por etapa
# ---------------------------------------------------------------------------


class TestRunSocializeFailSafe:
    """Etapas posteriores a los copys que no deben romper el bundle."""

    def test_keeps_the_bundle_when_the_visual_prompts_fail(
        self, run, monkeypatch, copy_payload
    ):
        runner, _ = run
        good = json.dumps(copy_payload, ensure_ascii=False)

        class _Mixed:
            """Responde bien a los copys y mal a los prompts visuales."""

            response_format = None

            def generate_report(self, system_prompt: str, user_prompt: str) -> str:
                if "prompt engineer" in system_prompt.lower():
                    return "no es json"
                return good

        monkeypatch.setattr(orchestrator, "LLMClient", lambda **kwargs: _Mixed())

        result = runner()

        assert result["prompts_path"] is None
        assert result["copy_path"].is_file()
        assert result["manifest_path"].is_file()

    def test_keeps_the_bundle_when_the_banners_fail(self, run, monkeypatch):
        runner, _ = run

        def _raise(*args, **kwargs):
            raise OSError("no se puede escribir en disco")

        monkeypatch.setattr(orchestrator, "render_all_banners", _raise)

        result = runner()

        assert result["banner_count"] == 0
        assert result["copy_path"].is_file()
