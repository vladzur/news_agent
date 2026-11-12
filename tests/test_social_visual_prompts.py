"""Tests de los prompts visuales en inglés para generadores de imágenes."""

import copy as copy_module

import pytest

from news_agent.config import SOCIAL_JSON_MAX_RETRIES
from news_agent.llm_client import LLMClientError
from news_agent.social.visual_prompts import (
    VisualPromptGenerationError,
    _find_text_blocks,
    build_visual_prompts,
    enabled_aspects,
    generate_visual_prompts,
    has_colour_signal,
    looks_like_spanish,
    spanish_signal_count,
    validate_visual_prompt,
)
from tests.test_social_copy_generator import FakeClient

# Prompt válido: ilustración editorial en inglés con rótulos breves y cifras
VALID_PROMPT = (
    "Bold editorial illustration of a colossal piggy bank cracking open over a "
    "tiny flooded city street at dusk, a giant red arrow piercing it from "
    "above, the number \"-10,39%\" and the label \"PENSIONES\" rendered in "
    "thick vintage lettering on a floating stamp, flat vector infographics "
    "mixed with textured digital painting, saturated teal and warm amber "
    "palette against crimson red, dramatic rim light, wide composition, "
    "critical and urgent mood, high detail, magazine cover quality"
)


# ---------------------------------------------------------------------------
# Contrato del módulo
# ---------------------------------------------------------------------------


class TestModuleContract:
    """Comprobaciones estructurales del módulo de prompts visuales."""

    def test_public_functions_are_callable(self):
        assert callable(build_visual_prompts)
        assert callable(generate_visual_prompts)
        assert callable(enabled_aspects)
        assert callable(validate_visual_prompt)
        assert callable(has_colour_signal)

    def test_generation_error_is_an_exception(self):
        assert issubclass(VisualPromptGenerationError, Exception)


# ---------------------------------------------------------------------------
# Selección de aspectos
# ---------------------------------------------------------------------------


class TestEnabledAspects:
    """Filtrado de aspectos según las plataformas pedidas."""

    def test_all_platforms_enable_every_aspect(self, social_config):
        aspects = enabled_aspects(social_config, ["x", "facebook", "instagram"])

        assert set(aspects) == {"landscape", "square", "portrait"}

    def test_x_only_enables_the_landscape_aspect(self, social_config):
        aspects = enabled_aspects(social_config, ["x"])

        assert set(aspects) == {"landscape"}

    def test_instagram_enables_square_and_portrait(self, social_config):
        aspects = enabled_aspects(social_config, ["instagram"])

        assert set(aspects) == {"square", "portrait"}

    def test_facebook_enables_the_landscape_aspect(self, social_config):
        aspects = enabled_aspects(social_config, ["facebook"])

        assert set(aspects) == {"landscape"}

    def test_returns_empty_without_configuration(self):
        assert enabled_aspects({}, ["x"]) == {}


# ---------------------------------------------------------------------------
# Validación de un prompt
# ---------------------------------------------------------------------------


class TestValidateVisualPrompt:
    """Reglas duras que debe cumplir un prompt positivo."""

    def test_accepts_a_colourful_english_prompt(self):
        validate_visual_prompt(VALID_PROMPT)

    def test_rejects_a_prompt_without_colour(self):
        prompt = (
            "A lone wooden chair standing on a flooded street at dusk, its "
            "shadow stretching across the wet asphalt, an enormous concrete "
            "wall rising behind it, heavy overcast sky, wide composition with "
            "generous negative space, subtle film grain, somber mood, "
            "editorial photography style, dramatic side lighting"
        )

        with pytest.raises(VisualPromptGenerationError, match="color"):
            validate_visual_prompt(prompt)

    def test_rejects_an_empty_prompt(self):
        with pytest.raises(VisualPromptGenerationError, match="vacío"):
            validate_visual_prompt("   ")

    def test_rejects_a_too_short_prompt(self):
        with pytest.raises(VisualPromptGenerationError, match="palabras"):
            validate_visual_prompt("a dark room with a chair")

    def test_rejects_a_too_long_prompt(self):
        with pytest.raises(VisualPromptGenerationError, match="palabras"):
            validate_visual_prompt(" ".join(["shadow"] * 250))

    def test_accepts_a_prompt_with_labels_and_figures(self):
        prompt = (
            VALID_PROMPT + ", a red banner reading \"NO ALCANZA\" and a chart "
            "with arrows showing -10,39%"
        )

        validate_visual_prompt(prompt)

    def test_rejects_a_prompt_that_asks_for_paragraphs_of_text(self):
        prompt = VALID_PROMPT + ", a newspaper filled with paragraphs of text"

        with pytest.raises(VisualPromptGenerationError, match="texto"):
            validate_visual_prompt(prompt)

    def test_rejects_a_prompt_written_in_spanish(self):
        prompt = (
            "Una silla de madera sobre el agua, la sombra larga del muro de "
            "concreto, para los pueblos del sur, con luz fría del amanecer y "
            "el ruido del viento entre las casas vacías"
        )

        with pytest.raises(VisualPromptGenerationError, match="inglés"):
            validate_visual_prompt(prompt)


class TestTextBlockDetection:
    """Detección de bloques de texto: los rótulos breves están permitidos."""

    def test_detects_paragraphs_of_text(self):
        assert _find_text_blocks("a wall covered with paragraphs of text") == [
            "paragraphs of text"
        ]

    def test_detects_fine_print(self):
        assert _find_text_blocks("a contract with fine print") == ["fine print"]

    def test_allows_short_labels_and_numbers(self):
        assert _find_text_blocks('a sign reading "PENSIONES" and "-10,39%"') == []

    def test_allows_negated_mentions(self):
        assert _find_text_blocks("a wall without paragraphs of text") == []


class TestSpanishHeuristic:
    """Heurística de detección de prompts en español."""

    def test_counts_distinct_function_words(self):
        assert spanish_signal_count("la casa del pueblo para todos") >= 3

    def test_does_not_flag_an_english_prompt(self):
        assert looks_like_spanish(VALID_PROMPT) is False

    def test_flags_a_spanish_prompt(self):
        assert looks_like_spanish("los muros del sur para la gente") is True

    def test_ignores_quoted_labels_written_in_spanish(self):
        prompt = (
            "editorial illustration of a cracked piggy bank with the labels "
            "\"LA DEUDA\" and \"EL PUEBLO\" painted in bold letters"
        )

        assert looks_like_spanish(prompt) is False


class TestColourSignal:
    """Detección de señales cromáticas en un prompt positivo."""

    def test_detects_a_named_colour(self):
        assert has_colour_signal("a red flag over a grey wall") is True

    def test_detects_the_word_palette(self):
        assert has_colour_signal("soft palette with gentle contrast") is True

    def test_ignores_a_colourless_prompt(self):
        assert has_colour_signal("a dark room with a single chair") is False


# ---------------------------------------------------------------------------
# Construcción de los prompts
# ---------------------------------------------------------------------------


class TestBuildVisualPrompts:
    """Construcción de los prompts validados a partir del JSON del modelo."""

    def test_returns_one_prompt_per_aspect(self, visual_payload, social_config):
        aspects = enabled_aspects(social_config, ["x", "facebook", "instagram"])

        prompts = build_visual_prompts(visual_payload, social_config, aspects)

        assert [prompt.aspect for prompt in prompts] == [
            "landscape",
            "square",
            "portrait",
        ]

    def test_copies_the_aspect_ratio_and_platforms(self, visual_payload, social_config):
        aspects = enabled_aspects(social_config, ["instagram"])

        prompts = build_visual_prompts(visual_payload, social_config, aspects)

        ratios = {prompt.aspect: prompt.aspect_ratio for prompt in prompts}
        assert ratios == {"square": "1:1", "portrait": "9:16"}
        assert prompts[0].platforms == ["instagram_feed"]

    def test_includes_the_brand_negative_prompt(self, visual_payload, social_config):
        aspects = enabled_aspects(social_config, ["x"])

        prompts = build_visual_prompts(visual_payload, social_config, aspects)

        expected = social_config["visual_prompts"]["negative_prompt"]
        assert prompts[0].negative_prompt.startswith(expected[:40])

    def test_appends_the_extra_negative_terms(self, visual_payload, social_config):
        aspects = enabled_aspects(social_config, ["instagram"])

        prompts = build_visual_prompts(visual_payload, social_config, aspects)
        square = next(prompt for prompt in prompts if prompt.aspect == "square")

        assert "crowds" in square.negative_prompt
        assert "banners" in square.negative_prompt

    def test_does_not_duplicate_negatives_already_in_the_brand_prompt(
        self, visual_payload, social_config
    ):
        payload = copy_module.deepcopy(visual_payload)
        payload["prompts"][0]["extra_negative"] = "watermark, logo"
        aspects = enabled_aspects(social_config, ["x"])

        prompts = build_visual_prompts(payload, social_config, aspects)

        assert prompts[0].negative_prompt.lower().count("watermark") == 1

    def test_composes_the_midjourney_variant(self, visual_payload, social_config):
        aspects = enabled_aspects(social_config, ["x"])

        prompts = build_visual_prompts(visual_payload, social_config, aspects)
        prompt = prompts[0]

        assert "--ar 16:9" in prompt.midjourney_prompt
        assert prompt.midjourney_prompt.startswith(prompt.prompt)
        assert "--no" in prompt.midjourney_prompt

    def test_copies_the_suggested_settings(self, visual_payload, social_config):
        aspects = enabled_aspects(social_config, ["x"])

        prompts = build_visual_prompts(visual_payload, social_config, aspects)

        assert prompts[0].settings == social_config["visual_prompts"]["default_settings"]

    def test_ignores_unknown_aspects(self, visual_payload, social_config):
        payload = copy_module.deepcopy(visual_payload)
        payload["prompts"].append({"aspect": "panoramic", "prompt": VALID_PROMPT})
        aspects = enabled_aspects(social_config, ["x"])

        prompts = build_visual_prompts(payload, social_config, aspects)

        assert [prompt.aspect for prompt in prompts] == ["landscape"]

    def test_skips_entries_without_a_prompt(self, visual_payload, social_config):
        payload = copy_module.deepcopy(visual_payload)
        payload["prompts"][0]["prompt"] = ""
        aspects = enabled_aspects(social_config, ["x", "facebook", "instagram"])

        prompts = build_visual_prompts(payload, social_config, aspects)

        assert [prompt.aspect for prompt in prompts] == ["square", "portrait"]

    def test_skips_prompts_that_violate_the_rules(self, visual_payload, social_config):
        payload = copy_module.deepcopy(visual_payload)
        payload["prompts"][0]["prompt"] = (
            VALID_PROMPT + ", a newspaper filled with paragraphs of text"
        )
        aspects = enabled_aspects(social_config, ["x", "facebook", "instagram"])

        prompts = build_visual_prompts(payload, social_config, aspects)

        assert "landscape" not in [prompt.aspect for prompt in prompts]

    def test_raises_when_no_prompt_is_usable(self, social_config):
        aspects = enabled_aspects(social_config, ["x"])

        with pytest.raises(VisualPromptGenerationError, match="ningún prompt"):
            build_visual_prompts({"prompts": [{"aspect": "landscape"}]}, social_config, aspects)

    def test_raises_when_the_prompts_key_is_missing(self, social_config):
        aspects = enabled_aspects(social_config, ["x"])

        with pytest.raises(VisualPromptGenerationError, match="prompts"):
            build_visual_prompts({}, social_config, aspects)


# ---------------------------------------------------------------------------
# Generación con el modelo
# ---------------------------------------------------------------------------


class TestGenerateVisualPrompts:
    """Reintentos de la llamada al modelo para los prompts visuales."""

    def test_returns_prompts_on_a_valid_response(
        self, visual_payload, article, social_copy, social_config
    ):
        import json

        client = FakeClient([json.dumps(visual_payload, ensure_ascii=False)])

        prompts = generate_visual_prompts(
            article, social_copy, social_config, client, ["x", "facebook", "instagram"]
        )

        assert len(prompts) == 3
        assert len(client.calls) == 1

    def test_retries_when_the_response_is_not_json(
        self, visual_payload, article, social_copy, social_config
    ):
        import json

        client = FakeClient(
            ["No puedo ayudar con eso.", json.dumps(visual_payload, ensure_ascii=False)]
        )

        prompts = generate_visual_prompts(
            article, social_copy, social_config, client, ["x", "facebook", "instagram"]
        )

        assert len(prompts) == 3
        assert len(client.calls) == 2

    def test_raises_after_exhausting_retries(self, article, social_copy, social_config):
        client = FakeClient(["sin json"] * (SOCIAL_JSON_MAX_RETRIES + 1))

        with pytest.raises(VisualPromptGenerationError, match="intento"):
            generate_visual_prompts(
                article, social_copy, social_config, client, ["x"]
            )

        assert len(client.calls) == SOCIAL_JSON_MAX_RETRIES + 1

    def test_propagates_client_errors(self, article, social_copy, social_config):
        client = FakeClient([LLMClientError("fallo de red")])

        with pytest.raises(LLMClientError):
            generate_visual_prompts(article, social_copy, social_config, client, ["x"])

    def test_skips_the_call_when_there_are_no_applicable_aspects(
        self, article, social_copy, social_config
    ):
        client = FakeClient([])

        prompts = generate_visual_prompts(
            article, social_copy, social_config, client, []
        )

        assert prompts == []
        assert client.calls == []
