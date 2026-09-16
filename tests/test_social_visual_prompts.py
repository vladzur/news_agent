"""Tests de los prompts visuales en inglés para generadores de imágenes."""

import copy as copy_module

import pytest

from news_agent.config import SOCIAL_JSON_MAX_RETRIES
from news_agent.llm_client import LLMClientError
from news_agent.social.visual_prompts import (
    VisualPromptGenerationError,
    _find_text_artifacts,
    build_visual_prompts,
    enabled_aspects,
    generate_visual_prompts,
    looks_like_spanish,
    spanish_signal_count,
    validate_visual_prompt,
)
from tests.test_social_copy_generator import FakeClient

# Prompt válido, en inglés y sin referencias a texto
VALID_PROMPT = (
    "A lone wooden chair standing on a flooded street at dusk, its shadow "
    "stretching into the water, an enormous concrete wall rising behind it, "
    "cold blue-grey palette with a single ember-red glow on the horizon, "
    "heavy overcast sky, wide composition with generous negative space, "
    "muted desaturated tones, subtle film grain, editorial conceptual "
    "photography style, dramatic chiaroscuro lighting"
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

    def test_accepts_a_conceptual_english_prompt(self):
        validate_visual_prompt(VALID_PROMPT)

    def test_rejects_an_empty_prompt(self):
        with pytest.raises(VisualPromptGenerationError, match="vacío"):
            validate_visual_prompt("   ")

    def test_rejects_a_too_short_prompt(self):
        with pytest.raises(VisualPromptGenerationError, match="palabras"):
            validate_visual_prompt("a dark room with a chair")

    def test_rejects_a_too_long_prompt(self):
        with pytest.raises(VisualPromptGenerationError, match="palabras"):
            validate_visual_prompt(" ".join(["shadow"] * 250))

    def test_rejects_a_prompt_that_describes_text(self):
        prompt = VALID_PROMPT + ", a poster with the word FREEDOM painted on it"

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


class TestTextArtifactDetection:
    """Detección de menciones a texto en un prompt positivo."""

    def test_detects_the_word_text(self):
        assert _find_text_artifacts("a wall with text painted on it") == ["text"]

    def test_allows_negated_mentions(self):
        assert _find_text_artifacts("a wall without text, no letters anywhere") == []

    def test_does_not_flag_texture(self):
        assert _find_text_artifacts("rich paper texture and film grain") == []


class TestSpanishHeuristic:
    """Heurística de detección de prompts en español."""

    def test_counts_distinct_function_words(self):
        assert spanish_signal_count("la casa del pueblo para todos") >= 3

    def test_does_not_flag_an_english_prompt(self):
        assert looks_like_spanish(VALID_PROMPT) is False

    def test_flags_a_spanish_prompt(self):
        assert looks_like_spanish("los muros del sur para la gente") is True


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
        payload["prompts"][0]["prompt"] = VALID_PROMPT + ", a sign with text"
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
