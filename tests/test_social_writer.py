"""Tests de la escritura del bundle de artefactos de RRSS."""

import copy as copy_module
import json
from datetime import datetime, timezone

from news_agent.social.writer import (
    ASSETS_DIR_NAME,
    COPY_FILE_NAME,
    INSTAGRAM_DIR_NAME,
    MANIFEST_FILE_NAME,
    MARKDOWN_FILE_NAMES,
    PROMPT_TEXT_FILE_NAME,
    PROMPTS_FILE_NAME,
    assets_dir,
    build_bundle_dir,
    instagram_dir,
    render_facebook_markdown,
    render_instagram_markdown,
    render_x_thread_markdown,
    save_copy_json,
    save_manifest,
    save_platform_markdown,
    save_visual_prompt_json,
    save_visual_prompt_text,
    slug_for_title,
)

# ---------------------------------------------------------------------------
# Estructura del bundle
# ---------------------------------------------------------------------------


class TestBuildBundleDir:
    """Creación del directorio del bundle."""

    def test_combines_date_and_slug(self, tmp_path):
        when = datetime(2026, 9, 14, tzinfo=timezone.utc)

        bundle = build_bundle_dir(tmp_path, "mi-titular", when=when)

        assert bundle.name == "2026_09_14_mi-titular"
        assert bundle.is_dir()

    def test_creates_missing_parents(self, tmp_path):
        bundle = build_bundle_dir(tmp_path / "social" / "anidado", "titular")

        assert bundle.is_dir()

    def test_returns_an_absolute_path(self, tmp_path):
        assert build_bundle_dir(tmp_path, "titular").is_absolute()

    def test_reuses_an_existing_bundle_without_failing(self, tmp_path):
        first = build_bundle_dir(tmp_path, "titular")
        second = build_bundle_dir(tmp_path, "titular")

        assert first == second

    def test_uses_a_fallback_slug_when_empty(self, tmp_path):
        bundle = build_bundle_dir(tmp_path, "")

        assert bundle.name.endswith("sin-titulo")


class TestAssetsDir:
    """Carpeta de assets del bundle."""

    def test_creates_the_assets_subfolder(self, tmp_path):
        path = assets_dir(tmp_path)

        assert path.name == ASSETS_DIR_NAME
        assert path.is_dir()

    def test_returns_an_absolute_path(self, tmp_path):
        assert assets_dir(tmp_path).is_absolute()


class TestInstagramDir:
    """Subdirectorio exclusivo del carrusel de Instagram."""

    def test_creates_the_instagram_subfolder(self, tmp_path):
        path = instagram_dir(tmp_path)

        assert path.name == INSTAGRAM_DIR_NAME
        assert path.is_dir()

    def test_returns_an_absolute_path(self, tmp_path):
        assert instagram_dir(tmp_path).is_absolute()

    def test_is_separate_from_the_generic_assets_folder(self, tmp_path):
        assert instagram_dir(tmp_path) != assets_dir(tmp_path)


class TestSlugForTitle:
    """Slug del bundle a partir del titular."""

    def test_slugifies_the_title(self):
        assert slug_for_title("Disparo simbólico, cárcel real") == (
            "disparo-simbólico-cárcel-real"
        )

    def test_returns_a_fallback_for_an_empty_title(self):
        assert slug_for_title("!!!") == "sin-titulo"


# ---------------------------------------------------------------------------
# Archivos JSON
# ---------------------------------------------------------------------------


class TestJsonFiles:
    """Escritura de los JSON del bundle."""

    def test_saves_the_copy_json(self, tmp_path, social_copy):
        path = save_copy_json(social_copy, tmp_path)

        assert path.name == COPY_FILE_NAME
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["title"] == social_copy.title
        assert payload["x"]["thread"] == social_copy.x.thread

    def test_saves_the_visual_prompt_json(
        self, tmp_path, visual_payload, social_config
    ):
        from news_agent.social.visual_prompts import build_visual_prompt

        prompt = build_visual_prompt(visual_payload, social_config)

        path = save_visual_prompt_json(prompt, tmp_path)

        assert path.name == PROMPTS_FILE_NAME
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["treatment"] == "photorealistic"
        assert payload["prompt"] == prompt.prompt
        assert payload["midjourney_prompt"] == prompt.midjourney_prompt
        assert payload["political_figures"] == prompt.political_figures

    def test_saves_the_midjourney_command_as_plain_text(
        self, tmp_path, visual_payload, social_config
    ):
        from news_agent.social.visual_prompts import build_visual_prompt

        prompt = build_visual_prompt(visual_payload, social_config)

        path = save_visual_prompt_text(prompt, tmp_path)

        assert path.name == PROMPT_TEXT_FILE_NAME
        content = path.read_text(encoding="utf-8")
        assert content.strip() == prompt.midjourney_prompt
        assert not content.lstrip().startswith("{")
        assert "\\" not in content
        assert '"' not in content


# ---------------------------------------------------------------------------
# Markdown por plataforma
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    """Composición del Markdown listo para copiar y pegar."""

    def test_x_thread_includes_every_tweet(self, social_copy):
        content = render_x_thread_markdown(social_copy)

        for tweet in social_copy.x.thread:
            assert tweet in content

    def test_x_thread_shows_the_character_count(self, social_copy):
        content = render_x_thread_markdown(social_copy)

        assert f"1 · {len(social_copy.x.thread[0])}/280 caracteres" in content

    def test_x_thread_reports_the_tweet_count(self, social_copy):
        content = render_x_thread_markdown(social_copy)

        assert f"**Cantidad de tweets:** {len(social_copy.x.thread)}" in content

    def test_x_thread_includes_hashtags_and_alternatives(self, social_copy):
        content = render_x_thread_markdown(social_copy)

        assert "#" + social_copy.x.hashtags[0] in content
        assert "Ganchos alternativos" in content
        assert "Síntesis ejecutiva" in content

    def test_x_thread_includes_the_source_path(self, social_copy):
        content = render_x_thread_markdown(social_copy)

        assert social_copy.source_path in content

    def test_facebook_markdown_includes_post_and_hashtags(self, social_copy):
        content = render_facebook_markdown(social_copy)

        assert social_copy.facebook.post in content
        assert "#" + social_copy.facebook.hashtags[0] in content
        assert social_copy.alt_text["facebook"] in content

    def test_instagram_markdown_includes_caption_and_hashtags(self, social_copy):
        content = render_instagram_markdown(social_copy)

        assert social_copy.instagram.caption in content
        assert "#" + social_copy.instagram.hashtags[0] in content

    def test_instagram_markdown_includes_the_quote_card(self, social_copy):
        content = render_instagram_markdown(social_copy)

        assert social_copy.quote_card.quote in content
        assert social_copy.quote_card.attribution in content

    def test_instagram_markdown_warns_about_unverified_quotes(self, social_copy):
        social_copy.quote_card.verbatim = False

        content = render_instagram_markdown(social_copy)

        assert "no se pudo verificar" in content

    def test_instagram_markdown_lists_the_carousel_slides(self, social_copy):
        content = render_instagram_markdown(social_copy)

        assert "Carrusel vertical" in content
        assert "instagram/" in content
        for slide in social_copy.instagram.slides:
            assert slide.text in content

    def test_instagram_markdown_includes_the_slide_figure(self, social_copy):
        social_copy.instagram.slides[0].figure = "44 años"

        content = render_instagram_markdown(social_copy)

        assert "**Dato clave:** 44 años" in content


class TestSavePlatformMarkdown:
    """Escritura de un Markdown por plataforma habilitada."""

    def test_writes_one_file_per_platform(self, tmp_path, social_copy):
        written = save_platform_markdown(
            social_copy, tmp_path, ["x", "facebook", "instagram"]
        )

        assert set(written) == {"x", "facebook", "instagram"}
        for platform, path in written.items():
            assert path.name == MARKDOWN_FILE_NAMES[platform]
            assert path.read_text(encoding="utf-8")

    def test_writes_only_the_requested_platforms(self, tmp_path, social_copy):
        written = save_platform_markdown(social_copy, tmp_path, ["facebook"])

        assert list(written) == ["facebook"]
        assert not (tmp_path / MARKDOWN_FILE_NAMES["x"]).exists()

    def test_skips_an_unknown_platform(self, tmp_path, social_copy):
        written = save_platform_markdown(social_copy, tmp_path, ["tiktok"])

        assert written == {}

    def test_uses_the_configured_x_limit_in_the_character_count(
        self, tmp_path, social_copy, social_config
    ):
        config = copy_module.deepcopy(social_config)
        config["platforms"]["x"]["max_chars"] = 260

        written = save_platform_markdown(
            social_copy, tmp_path, ["x"], config=config
        )

        content = written["x"].read_text(encoding="utf-8")
        assert "/260 caracteres" in content
        assert "/280 caracteres" not in content


# ---------------------------------------------------------------------------
# Manifiesto
# ---------------------------------------------------------------------------


class TestSaveManifest:
    """Registro de lo generado y de lo que quedó pendiente."""

    def _manifest(self, tmp_path, social_copy, article, **overrides):
        defaults = {
            "prompt": None,
            "banners": [],
            "markdown_files": {},
            "platforms": ["x"],
        }
        defaults.update(overrides)
        path = save_manifest(
            bundle_dir=tmp_path,
            copy=social_copy,
            article=article,
            **defaults,
        )
        return json.loads(path.read_text(encoding="utf-8"))

    def test_writes_the_manifest_file(self, tmp_path, social_copy, article):
        path = save_manifest(
            bundle_dir=tmp_path,
            copy=social_copy,
            prompt=None,
            banners=[],
            markdown_files={},
            platforms=["x"],
            article=article,
        )

        assert path.name == MANIFEST_FILE_NAME
        assert path.is_file()

    def test_records_the_article_metadata(self, tmp_path, social_copy, article):
        payload = self._manifest(tmp_path, social_copy, article)

        assert payload["article"]["title"] == article.title
        assert payload["article"]["word_count"] == article.word_count

    def test_records_the_markdown_file_names(self, tmp_path, social_copy, article):
        markdown = save_platform_markdown(social_copy, tmp_path, ["x"])

        payload = self._manifest(
            tmp_path, social_copy, article, markdown_files=markdown
        )

        assert payload["files"]["markdown"] == {"x": MARKDOWN_FILE_NAMES["x"]}

    def test_reports_missing_prompts_as_null(self, tmp_path, social_copy, article):
        payload = self._manifest(tmp_path, social_copy, article)

        assert payload["files"]["visual_prompts"] is None
        assert payload["files"]["visual_prompt_text"] is None
        assert payload["visual_prompts"]["status"] == "skipped"
        assert payload["visual_prompts"]["error"] is None
        assert payload["visual_prompts"]["count"] == 0
        assert payload["visual_prompts"]["treatment"] is None

    def test_records_a_failed_prompt_status(self, tmp_path, social_copy, article):
        payload = self._manifest(
            tmp_path,
            social_copy,
            article,
            prompt_status="failed",
            prompt_error="no es json",
        )

        assert payload["visual_prompts"]["status"] == "failed"
        assert payload["visual_prompts"]["error"] == "no es json"
        assert payload["visual_prompts"]["count"] == 0

    def test_records_the_visual_treatment(
        self, tmp_path, social_copy, article, visual_payload, social_config
    ):
        from news_agent.social.visual_prompts import build_visual_prompt

        prompt = build_visual_prompt(visual_payload, social_config)

        payload = self._manifest(tmp_path, social_copy, article, prompt=prompt)

        assert payload["files"]["visual_prompts"] == PROMPTS_FILE_NAME
        assert payload["files"]["visual_prompt_text"] == PROMPT_TEXT_FILE_NAME
        assert payload["visual_prompts"]["status"] == "generated"
        assert payload["visual_prompts"]["error"] is None
        assert payload["visual_prompts"]["count"] == 1
        assert payload["visual_prompts"]["treatment"] == "photorealistic"
        assert payload["visual_prompts"]["aspect_ratio"] == prompt.aspect_ratio
        assert payload["visual_prompts"]["political_figures"] == []

    def test_counts_rendered_and_failed_banners(self, tmp_path, social_copy, article):
        from news_agent.social.models import BannerSpec

        banners = [
            BannerSpec("headline_card", "x", 1600, 900, tmp_path / "a.png"),
            BannerSpec("headline_card", "facebook", 1200, 630, None),
        ]

        payload = self._manifest(tmp_path, social_copy, article, banners=banners)

        assert payload["banners"]["rendered"] == 1
        assert payload["banners"]["failed"] == 1
        assert payload["banners"]["items"][1]["path"] is None

    def test_reports_a_missing_carousel_as_skipped(
        self, tmp_path, social_copy, article
    ):
        payload = self._manifest(tmp_path, social_copy, article)

        assert payload["files"]["instagram_carousel"] is None
        assert payload["instagram_carousel"]["status"] == "skipped"
        assert payload["instagram_carousel"]["slides"] == 0
        assert payload["instagram_carousel"]["directory"] is None

    def test_records_the_rendered_carousel(self, tmp_path, social_copy, article):
        from news_agent.social.models import InstagramSlideSpec

        carousel = [
            InstagramSlideSpec(1, "cover", social_copy.title, 1080, 1440, tmp_path / "01.png"),
            InstagramSlideSpec(2, "summary", "Punto", 1080, 1440, tmp_path / "02.png"),
            InstagramSlideSpec(5, "signature", "La Chispa Sur", 1080, 1440, None),
        ]
        directory = instagram_dir(tmp_path)

        payload = self._manifest(
            tmp_path,
            social_copy,
            article,
            carousel_slides=carousel,
            carousel_dir_path=directory,
            carousel_format="instagram_portrait",
        )

        assert payload["files"]["instagram_carousel"] == INSTAGRAM_DIR_NAME
        assert payload["instagram_carousel"]["status"] == "partial"
        assert payload["instagram_carousel"]["directory"] == INSTAGRAM_DIR_NAME
        assert payload["instagram_carousel"]["format"] == "instagram_portrait"
        assert payload["instagram_carousel"]["width"] == 1080
        assert payload["instagram_carousel"]["height"] == 1440
        assert payload["instagram_carousel"]["slides"] == 3
        assert payload["instagram_carousel"]["rendered"] == 2
        assert payload["instagram_carousel"]["failed"] == 1

    def test_records_a_fully_rendered_carousel(
        self, tmp_path, social_copy, article
    ):
        from news_agent.social.models import InstagramSlideSpec

        carousel = [
            InstagramSlideSpec(
                index, "summary", "Punto", 1080, 1440, tmp_path / f"{index}.png"
            )
            for index in range(1, 4)
        ]

        payload = self._manifest(
            tmp_path,
            social_copy,
            article,
            carousel_slides=carousel,
            carousel_dir_path=instagram_dir(tmp_path),
            carousel_format="instagram_portrait",
        )

        assert payload["instagram_carousel"]["status"] == "generated"
        assert payload["instagram_carousel"]["failed"] == 0

    def test_records_whether_the_quote_was_verified(self, tmp_path, social_copy, article):
        payload = self._manifest(tmp_path, social_copy, article)

        assert payload["verified_quote"] is social_copy.quote_card.verbatim

    def test_records_the_platforms(self, tmp_path, social_copy, article):
        payload = self._manifest(
            tmp_path, social_copy, article, platforms=["x", "instagram"]
        )

        assert payload["platforms"] == ["x", "instagram"]


# ---------------------------------------------------------------------------
# Integración mínima del bundle
# ---------------------------------------------------------------------------


class TestBundleIntegration:
    """Comprobación de que el bundle queda autocontenido."""

    def test_bundle_contains_every_expected_artifact(self, tmp_path, social_copy, article):
        bundle = build_bundle_dir(tmp_path, "prueba")

        copy_path = save_copy_json(social_copy, bundle)
        markdown = save_platform_markdown(social_copy, bundle, ["x", "facebook", "instagram"])
        manifest = save_manifest(
            bundle_dir=bundle,
            copy=social_copy,
            prompt=None,
            banners=[],
            markdown_files=markdown,
            platforms=["x", "facebook", "instagram"],
            article=article,
        )

        assert copy_path.is_file()
        assert manifest.is_file()
        assert len(list(bundle.iterdir())) == 5  # copy, manifest y 3 markdown

    def test_no_temporary_file_is_left_behind(self, tmp_path, social_copy):
        bundle = build_bundle_dir(tmp_path, "prueba")

        save_copy_json(social_copy, bundle)

        assert [path.suffix for path in bundle.iterdir()] == [".json"]
