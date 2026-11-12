"""Tests de la construcción de prompts del subsistema de RRSS."""

import copy as copy_module

from news_agent.social.prompt_builder import (
    build_copy_system_prompt,
    build_copy_user_prompt,
    build_visual_prompt_system_prompt,
    build_visual_prompt_user_prompt,
)
from news_agent.social.visual_prompts import enabled_aspects

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

    def test_forbids_markdown_fences_in_the_response(self, article, social_config):
        prompt = build_copy_user_prompt(article, social_config)

        assert "bloques de código Markdown" in prompt


# ---------------------------------------------------------------------------
# Prompts visuales
# ---------------------------------------------------------------------------


class TestVisualSystemPrompt:
    """Contenido del prompt de sistema del ingeniero de prompts visuales."""

    def test_demands_english_only(self, social_config):
        prompt = build_visual_prompt_system_prompt(social_config)

        assert "English only" in prompt

    def test_allows_short_labels_and_graphics(self, social_config):
        prompt = build_visual_prompt_system_prompt(social_config)

        assert "graphic and typographic elements" in prompt
        assert "stamps or dotted lines" in prompt

    def test_asks_for_short_labels_in_spanish(self, social_config):
        prompt = build_visual_prompt_system_prompt(social_config)

        assert "three or four words at most" in prompt
        assert "written in Spanish" in prompt

    def test_forbids_paragraphs_of_text(self, social_config):
        prompt = build_visual_prompt_system_prompt(social_config).lower()

        assert "never ask for paragraphs" in prompt

    def test_allows_caricaturing_named_public_figures(self, social_config):
        prompt = build_visual_prompt_system_prompt(social_config)

        assert "caricature" in prompt.lower()
        assert "People named in the article" in prompt

    def test_requires_named_within_the_article(self, social_config):
        prompt = build_visual_prompt_system_prompt(social_config)

        assert "named in the article" in prompt

    def test_forbids_photorealistic_portraits(self, social_config):
        prompt = build_visual_prompt_system_prompt(social_config).lower()

        assert "photorealistic" in prompt
        assert "deepfake" in prompt

    def test_protects_private_individuals(self, social_config):
        prompt = build_visual_prompt_system_prompt(social_config).lower()

        assert "private individuals" in prompt
        assert "victims" in prompt

    def test_forbids_explicit_violence(self, social_config):
        prompt = build_visual_prompt_system_prompt(social_config)

        assert "No explicit violence" in prompt

    def test_prefers_editorial_illustration_over_cartoons(self, social_config):
        prompt = build_visual_prompt_system_prompt(social_config).lower()

        assert "editorial illustration" in prompt
        assert "illustrations beat cartoons" in prompt

    def test_requires_a_named_colour_palette(self, social_config):
        prompt = build_visual_prompt_system_prompt(social_config)

        assert "Always name a saturated colour palette" in prompt


class TestVisualUserPrompt:
    """Contenido del prompt de usuario para los prompts visuales."""

    def test_includes_the_article_and_the_approved_hook(
        self, article, social_copy, social_config
    ):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert article.title in prompt
        assert social_copy.hook in prompt
        assert social_copy.quote_card.quote in prompt

    def test_offers_the_key_figures_as_big_numbers(
        self, article, social_copy, social_config
    ):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert "Key figures usable as big numbers in the artwork" in prompt
        assert article.key_figures
        assert article.key_figures[0] in prompt

    def test_includes_the_style_directive(self, article, social_copy, social_config):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        style = social_config["visual_prompts"]["style"]
        assert style[:40] in prompt

    def test_includes_the_negative_prompt(self, article, social_copy, social_config):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        negative = social_config["visual_prompts"]["negative_prompt"]
        assert negative[:40] in prompt

    def test_lists_every_configured_aspect(self, article, social_copy, social_config):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert "(16:9)" in prompt
        assert "(1:1)" in prompt
        assert "(9:16)" in prompt

    def test_restricts_to_the_passed_aspects(self, article, social_copy, social_config):
        aspects = enabled_aspects(social_config, ["instagram"])

        prompt = build_visual_prompt_user_prompt(
            article, social_copy, social_config, aspects=aspects
        )

        assert "(1:1)" in prompt
        assert "(9:16)" in prompt
        assert "(16:9)" not in prompt

    def test_describes_the_required_json_schema(
        self, article, social_copy, social_config
    ):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert '"prompts"' in prompt
        assert '"aspect"' in prompt
        assert '"extra_negative"' in prompt

    def test_forbids_markdown_fences(self, article, social_copy, social_config):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert "Markdown code fences" in prompt

    def test_states_what_the_illustration_must_do(
        self, article, social_copy, social_config
    ):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert "What the illustration must do" in prompt
        assert "Always name a saturated colour palette" in prompt

    def test_allows_labels_and_graphics(self, article, social_copy, social_config):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert "short Spanish labels in double quotes" in prompt
        assert "Keep every label under five words" in prompt

    def test_uses_illustration_over_caricature(
        self, article, social_copy, social_config
    ):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert "Illustrate, never photograph" in prompt

    def test_requests_stylised_characters_for_named_public_figures(
        self, article, social_copy, social_config
    ):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert "Named public figures may appear as stylised characters" in prompt

    def test_forbids_recognisable_private_individuals(
        self, article, social_copy, social_config
    ):
        prompt = build_visual_prompt_user_prompt(article, social_copy, social_config)

        assert "private individuals" in prompt
