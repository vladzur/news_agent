"""Tests de la construcción de prompts del subsistema de RRSS."""

import copy as copy_module

from news_agent.social.prompt_builder import (
    build_copy_system_prompt,
    build_copy_user_prompt,
    build_visual_prompt_system_prompt,
    build_visual_prompt_user_prompt,
)
from news_agent.social.visual_prompts import looks_like_spanish

# ---------------------------------------------------------------------------
# Prompts de copys
# ---------------------------------------------------------------------------


class TestCopySystemPrompt:
    """Contenido del prompt de sistema del editor de redes."""

    def test_returns_a_non_empty_prompt(self, social_config):
        prompt = build_copy_system_prompt(social_config)

        assert len(prompt) > 500

    def test_defines_the_editorial_identity(self, social_config):
        prompt = build_copy_system_prompt(social_config)

        assert "La Chispa Sur" in prompt

    def test_forbids_regional_spanish_variants(self, social_config):
        prompt = build_copy_system_prompt(social_config)

        assert "Español neutro" in prompt
        assert "voseo" in prompt
        assert "argentino" in prompt

    def test_demands_verbatim_quotes_and_factual_fidelity(self, social_config):
        prompt = build_copy_system_prompt(social_config)

        assert "literal" in prompt
        assert "No inventes cifras" in prompt

    def test_explains_each_platform(self, social_config):
        prompt = build_copy_system_prompt(social_config)

        assert "X/Twitter" in prompt
        assert "Facebook" in prompt
        assert "Instagram" in prompt

    def test_forbids_hashtags_inside_the_copy_text(self, social_config):
        prompt = build_copy_system_prompt(social_config)

        assert "No incluyas hashtags dentro del texto" in prompt

    def test_describes_the_instagram_carousel(self, social_config):
        prompt = build_copy_system_prompt(social_config)

        assert "carrusel vertical" in prompt
        assert "tres slides" in prompt
        assert "portada" in prompt
        assert "firma de marca" in prompt


class TestCopyUserPrompt:
    """Contenido del prompt de usuario con el material de origen."""

    def test_includes_the_article_material(self, article, social_config):
        prompt = build_copy_user_prompt(article, social_config)

        assert article.title in prompt
        assert "## Material de origen" in prompt
        assert article.lead[:60] in prompt

    def test_includes_every_section_heading(self, article, social_config):
        prompt = build_copy_user_prompt(article, social_config)

        for section in article.sections:
            assert section.heading in prompt

    def test_includes_sources_and_key_figures(self, article, social_config):
        prompt = build_copy_user_prompt(article, social_config)

        assert article.sources[0][:40] in prompt
        for figure in article.key_figures:
            assert figure in prompt

    def test_includes_quote_candidates(self, article, social_config):
        prompt = build_copy_user_prompt(article, social_config)

        assert "Oraciones candidatas" in prompt
        assert article.quote_candidates[0] in prompt

    def test_states_the_resolved_platform_limits(self, article, social_config):
        prompt = build_copy_user_prompt(article, social_config)

        assert "280 caracteres" in prompt
        assert "1200" in prompt
        assert "2200" in prompt

    def test_honours_the_configured_limits(self, article, social_config):
        config = copy_module.deepcopy(social_config)
        config["platforms"]["x"]["max_chars"] = 320

        prompt = build_copy_user_prompt(article, config)

        assert "320 caracteres" in prompt

    def test_states_the_thread_bounds(self, article, social_config):
        prompt = build_copy_user_prompt(article, social_config)
        spec = social_config["platforms"]["x"]

        assert (
            f"{spec['thread_min_tweets']} a {spec['thread_max_tweets']} tweets"
            in prompt
        )

    def test_describes_the_required_json_schema(self, article, social_config):
        prompt = build_copy_user_prompt(article, social_config)

        for key in (
            "hooks",
            "summary",
            "hook",
            "quote_card",
            "key_figures",
            "cta",
            "alt_text",
            "facebook",
            "instagram",
        ):
            assert f'"{key}"' in prompt

    def test_requires_thread_to_start_with_the_hook(self, article, social_config):
        prompt = build_copy_user_prompt(article, social_config)

        assert "x.thread[0]" in prompt

    def test_describes_the_three_instagram_slides(self, article, social_config):
        prompt = build_copy_user_prompt(article, social_config)

        assert '"slides"' in prompt
        assert "exactamente" in prompt
        assert "3 slides" in prompt or "tres slides" in prompt

    def test_states_the_instagram_slide_limits(self, article, social_config):
        prompt = build_copy_user_prompt(article, social_config)

        assert "70 caracteres" in prompt
        assert "240 caracteres" in prompt

    def test_forbids_markdown_fences_in_the_response(self, article, social_config):
        prompt = build_copy_user_prompt(article, social_config)

        assert "bloques de código Markdown" in prompt


# ---------------------------------------------------------------------------
# Prompts visuales
# ---------------------------------------------------------------------------


class TestVisualSystemPrompt:
    """Invariantes del prompt de sistema, sin atarse a su redacción.

    La prosa del prompt de sistema se ajusta a menudo, así que estos tests
    verifican solo contratos estables: idioma, herramienta destino y que cada
    tratamiento declarado en la configuración quede nombrado.
    """

    def test_is_written_in_english(self, social_config):
        prompt = build_visual_prompt_system_prompt(social_config)

        assert looks_like_spanish(prompt) is False

    def test_targets_midjourney(self, social_config):
        prompt = build_visual_prompt_system_prompt(social_config)

        assert "Midjourney" in prompt
        assert "Flux" not in prompt
        assert "SDXL" not in prompt

    def test_names_every_configured_treatment(self, social_config):
        prompt = build_visual_prompt_system_prompt(social_config).lower()

        for treatment in social_config["visual_prompts"]["treatments"]:
            assert treatment in prompt


class TestVisualUserPrompt:
    """Contenido del prompt de usuario para el prompt visual."""

    def test_includes_the_column_and_the_approved_hook(
        self, article, social_copy, social_config
    ):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert article.title in prompt
        assert article.byline in prompt
        assert social_copy.hook in prompt
        assert social_copy.quote_card.quote in prompt

    def test_includes_the_column_sections_and_sources(
        self, article, social_copy, social_config
    ):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert article.sections[0].heading in prompt
        assert article.sources[0] in prompt

    def test_offers_the_key_figures_of_the_column(
        self, article, social_copy, social_config
    ):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert article.key_figures
        assert article.key_figures[0] in prompt

    def test_includes_the_treatment_rules(self, article, social_copy, social_config):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        rules = social_config["visual_prompts"]["treatment_rules"]
        assert rules[:40] in prompt

    def test_includes_both_treatment_styles(self, article, social_copy, social_config):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        treatments = social_config["visual_prompts"]["treatments"]
        assert treatments["photorealistic"][:40] in prompt
        assert treatments["caricature"][:40] in prompt

    def test_includes_the_negative_prompt(self, article, social_copy, social_config):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        negative = social_config["visual_prompts"]["negative_prompt"]
        assert negative[:40] in prompt

    def test_asks_for_a_single_prompt_without_aspect_variants(
        self, article, social_copy, social_config
    ):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert "Aspect ratios" not in prompt
        assert '"prompts"' not in prompt

    def test_states_that_midjourney_flags_are_appended(
        self, article, social_copy, social_config
    ):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        ratio = social_config["visual_prompts"]["aspect_ratio"]
        assert f"--ar {ratio}" in prompt

    def test_describes_the_required_json_schema(
        self, article, social_copy, social_config
    ):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        for key in ("treatment", "rationale", "prompt", "extra_negative"):
            assert f'"{key}"' in prompt

    def test_forbids_markdown_fences(self, article, social_copy, social_config):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert "Markdown code fences" in prompt
