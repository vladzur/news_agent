"""Tests del prompt visual en inglés para Midjourney."""

import copy as copy_module
import json

import pytest

from news_agent.config import SOCIAL_JSON_MAX_RETRIES
from news_agent.llm_client import LLMClientError
from news_agent.social.visual_prompts import (
    VISUAL_TREATMENTS,
    VisualPromptGenerationError,
    _find_text_blocks,
    build_visual_prompt,
    generate_visual_prompt,
    has_colour_signal,
    has_illustration_signal,
    has_photo_signal,
    looks_like_spanish,
    spanish_signal_count,
    validate_visual_prompt,
)
from tests.test_social_copy_generator import FakeClient

# Prompt válido: fotografía documental en inglés con paleta y rótulo breve
VALID_PHOTO_PROMPT = (
    "Documentary photograph of a police van parked on a wet gravel street in "
    "southern Chile at dusk, two officers walking towards a wooden house, a "
    "neighbour watching from a doorway, a hand-painted sign reading "
    "CUNCO, 35mm lens at eye level, natural available light, shallow "
    "depth of field, film grain, reportage palette of crimson red, warm amber "
    "and deep teal, wide composition, magazine cover quality"
)

# Prompt válido: caricatura editorial en inglés con paleta y técnica
VALID_CARICATURE_PROMPT = (
    "Bold editorial illustration of a colossal cracked marble column held up "
    "by a single matchstick, tiny suited figures pushing from opposite sides, "
    "flat vector infographics mixed with textured digital painting, saturated "
    "teal and warm amber palette against crimson red, dramatic rim light, "
    "poster composition, magazine cover quality"
)


# ---------------------------------------------------------------------------
# Contrato del módulo
# ---------------------------------------------------------------------------


class TestModuleContract:
    """Comprobaciones estructurales del módulo del prompt visual."""

    def test_public_functions_are_callable(self):
        assert callable(build_visual_prompt)
        assert callable(generate_visual_prompt)
        assert callable(validate_visual_prompt)
        assert callable(has_colour_signal)
        assert callable(has_photo_signal)
        assert callable(has_illustration_signal)

    def test_generation_error_is_an_exception(self):
        assert issubclass(VisualPromptGenerationError, Exception)

    def test_declares_the_two_treatments(self):
        assert VISUAL_TREATMENTS == ("photorealistic", "caricature")


# ---------------------------------------------------------------------------
# Validación de un prompt
# ---------------------------------------------------------------------------


class TestValidateVisualPrompt:
    """Reglas duras que debe cumplir un prompt positivo."""

    def test_accepts_a_photorealistic_prompt(self):
        validate_visual_prompt(VALID_PHOTO_PROMPT, "photorealistic")

    def test_accepts_a_caricature_prompt(self):
        validate_visual_prompt(VALID_CARICATURE_PROMPT, "caricature")

    def test_rejects_an_unknown_treatment(self):
        with pytest.raises(VisualPromptGenerationError, match="Tratamiento"):
            validate_visual_prompt(VALID_PHOTO_PROMPT, "watercolour")

    def test_rejects_an_empty_treatment(self):
        with pytest.raises(VisualPromptGenerationError, match="Tratamiento"):
            validate_visual_prompt(VALID_PHOTO_PROMPT, "")

    def test_rejects_a_photorealistic_prompt_without_a_photo_signal(self):
        with pytest.raises(VisualPromptGenerationError, match="fotorrealista"):
            validate_visual_prompt(VALID_CARICATURE_PROMPT, "photorealistic")

    def test_rejects_a_caricature_prompt_without_an_illustration_signal(self):
        with pytest.raises(VisualPromptGenerationError, match="caricatura"):
            validate_visual_prompt(VALID_PHOTO_PROMPT, "caricature")

    def test_rejects_a_prompt_without_colour(self):
        prompt = (
            "Documentary photograph of a lone wooden chair standing on a "
            "flooded street at dusk, its shadow stretching across the wet "
            "asphalt, an enormous concrete wall rising behind it, heavy "
            "overcast sky, 35mm lens, natural light, wide composition with "
            "generous negative space, subtle film grain, somber mood"
        )

        with pytest.raises(VisualPromptGenerationError, match="color"):
            validate_visual_prompt(prompt, "photorealistic")

    def test_rejects_an_empty_prompt(self):
        with pytest.raises(VisualPromptGenerationError, match="vacío"):
            validate_visual_prompt("   ", "photorealistic")

    def test_rejects_a_too_short_prompt(self):
        with pytest.raises(VisualPromptGenerationError, match="palabras"):
            validate_visual_prompt("a dark room with a chair", "photorealistic")

    def test_rejects_a_too_long_prompt(self):
        with pytest.raises(VisualPromptGenerationError, match="palabras"):
            validate_visual_prompt(" ".join(["shadow"] * 250), "photorealistic")

    def test_accepts_a_prompt_with_labels_and_figures(self):
        prompt = (
            VALID_PHOTO_PROMPT + ", a red placard reading NO ALCANZA and a "
            "chalked sign showing -10,39%"
        )

        validate_visual_prompt(prompt, "photorealistic")

    def test_rejects_a_prompt_that_asks_for_paragraphs_of_text(self):
        prompt = VALID_PHOTO_PROMPT + ", a newspaper filled with paragraphs of text"

        with pytest.raises(VisualPromptGenerationError, match="texto"):
            validate_visual_prompt(prompt, "photorealistic")

    def test_rejects_a_prompt_with_explicit_violence(self):
        prompt = VALID_PHOTO_PROMPT + ", explicit violence and blood on the street"

        with pytest.raises(VisualPromptGenerationError, match="violencia"):
            validate_visual_prompt(prompt, "photorealistic")

    def test_rejects_a_prompt_with_a_deepfake_scene(self):
        prompt = VALID_PHOTO_PROMPT + ", a deepfake face of the president"

        with pytest.raises(VisualPromptGenerationError, match="prohibido"):
            validate_visual_prompt(prompt, "photorealistic")

    def test_rejects_a_prompt_written_in_spanish(self):
        prompt = (
            "Una silla de madera sobre el agua, la sombra larga del muro de "
            "concreto, para los pueblos del sur, con luz fría del amanecer y "
            "el ruido del viento entre las casas vacías"
        )

        with pytest.raises(VisualPromptGenerationError, match="inglés"):
            validate_visual_prompt(prompt, "photorealistic")


# ---------------------------------------------------------------------------
# Detección de señales
# ---------------------------------------------------------------------------


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
        assert looks_like_spanish(VALID_PHOTO_PROMPT) is False

    def test_flags_a_spanish_prompt(self):
        assert looks_like_spanish("los muros del sur para la gente") is True

    def test_ignores_quoted_labels_written_in_spanish(self):
        prompt = (
            "editorial illustration of a cracked piggy bank with the labels "
            "\"LA DEUDA\" and \"EL PUEBLO\" painted in bold letters"
        )

        assert looks_like_spanish(prompt) is False

    def test_ignores_uppercase_labels_without_quotes(self):
        prompt = (
            "documentary photograph of a market stall with a cardboard sign "
            "reading LA DEUDA and a placard reading SIN TECHO PARA LOS PUEBLOS"
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


class TestTreatmentSignals:
    """Detección de la técnica que declara cada tratamiento."""

    def test_detects_a_photographic_treatment(self):
        assert has_photo_signal(VALID_PHOTO_PROMPT) is True

    def test_does_not_mistake_an_illustration_for_a_photograph(self):
        assert has_photo_signal(VALID_CARICATURE_PROMPT) is False

    def test_detects_an_illustrated_treatment(self):
        assert has_illustration_signal(VALID_CARICATURE_PROMPT) is True

    def test_does_not_mistake_a_photograph_for_an_illustration(self):
        assert has_illustration_signal(VALID_PHOTO_PROMPT) is False


# ---------------------------------------------------------------------------
# Construcción del prompt
# ---------------------------------------------------------------------------


class TestBuildVisualPrompt:
    """Construcción del prompt validado a partir del JSON del modelo."""

    def test_keeps_the_declared_treatment_and_rationale(
        self, visual_payload, social_config
    ):
        prompt = build_visual_prompt(visual_payload, social_config)

        assert prompt.treatment == "photorealistic"
        assert prompt.rationale == visual_payload["rationale"]

    def test_copies_the_configured_aspect_ratio(self, visual_payload, social_config):
        prompt = build_visual_prompt(visual_payload, social_config)

        assert prompt.aspect_ratio == social_config["visual_prompts"]["aspect_ratio"]

    def test_keeps_quoted_spanish_labels_without_rejecting_the_prompt(
        self, visual_payload, social_config
    ):
        visual_payload["prompt"] = (
            VALID_PHOTO_PROMPT + ', a hand-painted sign reading "para la gente"'
        )

        prompt = build_visual_prompt(visual_payload, social_config)

        assert "para la gente" in prompt.prompt
        assert '"' not in prompt.prompt

    def test_includes_the_brand_negative_prompt(self, visual_payload, social_config):
        prompt = build_visual_prompt(visual_payload, social_config)

        expected = social_config["visual_prompts"]["negative_prompt"]
        assert prompt.negative_prompt.startswith(expected[:40])

    def test_appends_the_extra_negative_terms(self, caricature_payload, social_config):
        prompt = build_visual_prompt(caricature_payload, social_config)

        assert "crowds" in prompt.negative_prompt
        assert "banners" in prompt.negative_prompt

    def test_does_not_duplicate_negatives_already_in_the_brand_prompt(
        self, visual_payload, social_config
    ):
        payload = copy_module.deepcopy(visual_payload)
        payload["extra_negative"] = "watermark, logo"

        prompt = build_visual_prompt(payload, social_config)

        assert prompt.negative_prompt.lower().count("watermark") == 1

    def test_composes_the_midjourney_prompt(self, visual_payload, social_config):
        prompt = build_visual_prompt(visual_payload, social_config)
        ratio = social_config["visual_prompts"]["aspect_ratio"]

        assert prompt.midjourney_prompt.startswith(prompt.prompt)
        assert f"--ar {ratio}" in prompt.midjourney_prompt
        assert "--no" in prompt.midjourney_prompt

    def test_includes_the_configured_version_flags(
        self, visual_payload, social_config
    ):
        prompt = build_visual_prompt(visual_payload, social_config)

        suffix = social_config["visual_prompts"]["midjourney_suffix"]
        assert suffix in prompt.midjourney_prompt

    def test_strips_quotes_from_the_prompt(self, visual_payload, social_config):
        payload = copy_module.deepcopy(visual_payload)
        payload["prompt"] += (
            ', a chalked sign reading \"CUNCO\" and a price board reading \"US$ 6\"'
        )

        prompt = build_visual_prompt(payload, social_config)

        assert '"' not in prompt.prompt
        assert "\\" not in prompt.prompt
        assert "CUNCO" in prompt.prompt
        assert "US$ 6" in prompt.prompt

    def test_strips_quotes_from_the_extra_negative(
        self, visual_payload, social_config
    ):
        payload = copy_module.deepcopy(visual_payload)
        payload["extra_negative"] = '"crowds", \"banners\"'

        prompt = build_visual_prompt(payload, social_config)

        assert '"' not in prompt.negative_prompt
        assert "crowds" in prompt.negative_prompt
        assert "banners" in prompt.negative_prompt

    def test_leaves_the_midjourney_command_free_of_escapes(
        self, visual_payload, social_config
    ):
        payload = copy_module.deepcopy(visual_payload)
        payload["prompt"] += ', a sign reading \"CUNCO\"'

        prompt = build_visual_prompt(payload, social_config)

        assert "\\" not in prompt.midjourney_prompt
        assert '"' not in prompt.midjourney_prompt
        assert "--ar" in prompt.midjourney_prompt

    def test_accepts_a_caricature_for_an_abstract_column(
        self, caricature_payload, social_config
    ):
        prompt = build_visual_prompt(caricature_payload, social_config)

        assert prompt.treatment == "caricature"

    def test_raises_when_the_prompt_is_missing(self, social_config):
        with pytest.raises(VisualPromptGenerationError, match="prompt"):
            build_visual_prompt({"treatment": "photorealistic"}, social_config)

    def test_raises_when_the_rationale_is_missing(self, visual_payload, social_config):
        payload = copy_module.deepcopy(visual_payload)
        payload["rationale"] = "   "

        with pytest.raises(VisualPromptGenerationError, match="rationale"):
            build_visual_prompt(payload, social_config)

    def test_raises_when_the_treatment_contradicts_the_prompt(
        self, visual_payload, social_config
    ):
        payload = copy_module.deepcopy(visual_payload)
        payload["treatment"] = "caricature"

        with pytest.raises(VisualPromptGenerationError, match="caricatura"):
            build_visual_prompt(payload, social_config)

    def test_raises_when_the_treatment_is_unknown(self, visual_payload, social_config):
        payload = copy_module.deepcopy(visual_payload)
        payload["treatment"] = "photojournalism"

        with pytest.raises(VisualPromptGenerationError, match="Tratamiento"):
            build_visual_prompt(payload, social_config)

    def test_raises_when_the_prompt_violates_the_rules(
        self, visual_payload, social_config
    ):
        payload = copy_module.deepcopy(visual_payload)
        payload["prompt"] = VALID_PHOTO_PROMPT + ", a wall of paragraphs of text"

        with pytest.raises(VisualPromptGenerationError, match="texto"):
            build_visual_prompt(payload, social_config)


# ---------------------------------------------------------------------------
# Generación con el modelo
# ---------------------------------------------------------------------------


class TestGenerateVisualPrompt:
    """Reintentos de la llamada al modelo para el prompt visual."""

    def test_returns_the_prompt_on_a_valid_response(
        self, visual_payload, article, social_copy, social_config
    ):
        client = FakeClient([json.dumps(visual_payload, ensure_ascii=False)])

        prompt = generate_visual_prompt(article, social_copy, social_config, client)

        assert prompt.treatment == "photorealistic"
        assert len(client.calls) == 1

    def test_retries_when_the_response_is_not_json(
        self, visual_payload, article, social_copy, social_config
    ):
        client = FakeClient(
            ["No puedo ayudar con eso.", json.dumps(visual_payload, ensure_ascii=False)]
        )

        prompt = generate_visual_prompt(article, social_copy, social_config, client)

        assert prompt.treatment == "photorealistic"
        assert len(client.calls) == 2

    def test_retries_when_the_treatment_contradicts_the_prompt(
        self, visual_payload, caricature_payload, article, social_copy, social_config
    ):
        broken = copy_module.deepcopy(visual_payload)
        broken["treatment"] = "caricature"
        client = FakeClient(
            [
                json.dumps(broken, ensure_ascii=False),
                json.dumps(caricature_payload, ensure_ascii=False),
            ]
        )

        prompt = generate_visual_prompt(article, social_copy, social_config, client)

        assert prompt.treatment == "caricature"
        assert len(client.calls) == 2

    def test_raises_after_exhausting_retries(self, article, social_copy, social_config):
        client = FakeClient(["sin json"] * (SOCIAL_JSON_MAX_RETRIES + 1))

        with pytest.raises(VisualPromptGenerationError, match="intento"):
            generate_visual_prompt(article, social_copy, social_config, client)

        assert len(client.calls) == SOCIAL_JSON_MAX_RETRIES + 1

    def test_propagates_client_errors(self, article, social_copy, social_config):
        client = FakeClient([LLMClientError("fallo de red")])

        with pytest.raises(LLMClientError):
            generate_visual_prompt(article, social_copy, social_config, client)
