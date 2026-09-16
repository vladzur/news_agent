"""Tests de la generación y validación de copys para redes sociales."""

import copy as copy_module
from pathlib import Path

import pytest

from news_agent.config import SOCIAL_JSON_MAX_RETRIES, SOCIAL_X_MAX_CHARS
from news_agent.llm_client import LLMClientError
from news_agent.social.copy_generator import (
    SocialCopyValidationError,
    build_social_copy,
    generate_social_copy,
)
from news_agent.social.models import SocialCopy

# ---------------------------------------------------------------------------
# Cliente LLM falso
# ---------------------------------------------------------------------------


class FakeClient:
    """Cliente LLM falso que devuelve respuestas predefinidas en orden."""

    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def generate_report(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if not self.responses:
            raise AssertionError("El cliente falso se quedó sin respuestas")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def article_without_quote_candidates(tmp_path: Path):
    """Artículo breve cuyas oraciones no alcanzan a ser candidatas a cita.

    Returns:
        ArticleSource: Artículo sin candidatas para la tarjeta de cita.
    """
    from news_agent.social.article_source import parse_article_file

    path = tmp_path / "breve.md"
    path.write_text(
        "# Titular breve\n\n**Por La Chispa Sur**\n\n---\n\n"
        "El cuerpo es corto y no ofrece ninguna cita destacable.\n",
        encoding="utf-8",
    )
    return parse_article_file(path)


# ---------------------------------------------------------------------------
# Contrato del módulo
# ---------------------------------------------------------------------------


class TestModuleContract:
    """Comprobaciones estructurales del módulo de copys."""

    def test_public_functions_are_callable(self):
        assert callable(build_social_copy)
        assert callable(generate_social_copy)

    def test_validation_error_is_an_exception(self):
        assert issubclass(SocialCopyValidationError, Exception)


# ---------------------------------------------------------------------------
# Copys válidos
# ---------------------------------------------------------------------------


class TestBuildSocialCopy:
    """Construcción de copys a partir de un payload conforme al contrato."""

    def test_returns_social_copy(self, copy_payload, article, social_config):
        result = build_social_copy(copy_payload, article, social_config)

        assert isinstance(result, SocialCopy)

    def test_keeps_the_article_title_and_path(self, copy_payload, article, social_config):
        result = build_social_copy(copy_payload, article, social_config)

        assert result.title == article.title
        assert result.source_path == str(article.path)
        assert result.slug

    def test_records_a_generation_timestamp(self, copy_payload, article, social_config):
        result = build_social_copy(copy_payload, article, social_config)

        assert result.generated_at.startswith("20")

    def test_thread_starts_with_the_hook_tweet(self, copy_payload, article, social_config):
        result = build_social_copy(copy_payload, article, social_config)

        assert result.x.thread[0] == result.x.hook_tweet

    def test_thread_respects_the_configured_bounds(self, copy_payload, article, social_config):
        result = build_social_copy(copy_payload, article, social_config)
        spec = social_config["platforms"]["x"]
        limit = len(result.x.thread)

        assert spec["thread_min_tweets"] <= limit <= spec["thread_max_tweets"]

    def test_every_tweet_fits_the_character_limit(self, copy_payload, article, social_config):
        result = build_social_copy(copy_payload, article, social_config)

        for tweet in result.x.thread:
            assert len(tweet) <= SOCIAL_X_MAX_CHARS

    def test_hashtags_have_no_hash_symbol(self, copy_payload, article, social_config):
        result = build_social_copy(copy_payload, article, social_config)

        for hashtag in (
            result.x.hashtags + result.facebook.hashtags + result.instagram.hashtags
        ):
            assert not hashtag.startswith("#")
            assert " " not in hashtag

    def test_hashtags_respect_the_platform_caps(self, copy_payload, article, social_config):
        result = build_social_copy(copy_payload, article, social_config)

        assert len(result.x.hashtags) <= social_config["platforms"]["x"]["max_hashtags"]
        assert len(result.instagram.hashtags) <= (
            social_config["platforms"]["instagram"]["max_hashtags"]
        )

    def test_closing_tweet_includes_the_hashtags(self, copy_payload, article, social_config):
        result = build_social_copy(copy_payload, article, social_config)

        if result.x.hashtags:
            assert "#" + result.x.hashtags[0] in result.x.thread[-1]

    def test_alt_text_covers_every_platform(self, copy_payload, article, social_config):
        result = build_social_copy(copy_payload, article, social_config)

        assert set(result.alt_text) == {"x", "facebook", "instagram"}
        assert result.alt_text["instagram"]

    def test_alt_text_respects_the_instagram_limit(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload["alt_text"]["instagram"] = "palabra " * 100

        result = build_social_copy(payload, article, social_config)

        assert len(result.alt_text["instagram"]) <= 100

    def test_hooks_are_capped_and_trimmed(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload["hooks"] = [" ".join(["palabra"] * 60) for _ in range(9)]

        result = build_social_copy(payload, article, social_config)

        assert len(result.hooks) <= 5
        for hook in result.hooks:
            assert len(hook) <= 200

    def test_hook_falls_back_to_the_first_hook_variant(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload.pop("hook")

        result = build_social_copy(payload, article, social_config)

        assert result.hook == result.hooks[0]

    def test_platform_copies_are_indexed_by_platform(self, social_copy):
        copies = social_copy.platform_copies()

        assert set(copies) == {"x", "facebook", "instagram"}

    def test_to_dict_is_json_serializable(self, social_copy):
        import json

        json.dumps(social_copy.to_dict(), ensure_ascii=False)


# ---------------------------------------------------------------------------
# Verificación de la cita
# ---------------------------------------------------------------------------


class TestQuoteCard:
    """Verificación de la cita destacada contra el artículo."""

    def test_accepts_a_literal_quote(self, copy_payload, article, social_config):
        result = build_social_copy(copy_payload, article, social_config)

        assert result.quote_card.verbatim is True
        assert "comunicación amenazante" in result.quote_card.quote

    def test_replaces_a_fabricated_quote_with_a_real_candidate(
        self, copy_payload, article, social_config
    ):
        payload = copy_module.deepcopy(copy_payload)
        payload["quote_card"]["quote"] = (
            "El gobierno anunció la creación de una comisión especial para "
            "revisar todos los casos pendientes."
        )

        result = build_social_copy(payload, article, social_config)

        assert result.quote_card.verbatim is True
        assert result.quote_card.quote in article.quote_candidates

    def test_uses_lead_material_when_there_are_no_candidates(
        self, copy_payload, article_without_quote_candidates, social_config
    ):
        payload = copy_module.deepcopy(copy_payload)
        payload["quote_card"]["quote"] = "Una frase inventada por el modelo."

        result = build_social_copy(
            payload, article_without_quote_candidates, social_config
        )

        assert result.quote_card.verbatim is True
        assert "corto" in result.quote_card.quote

    def test_falls_back_to_the_brand_name_as_attribution(
        self, copy_payload, article, social_config
    ):
        payload = copy_module.deepcopy(copy_payload)
        payload["quote_card"]["attribution"] = ""

        result = build_social_copy(payload, article, social_config)

        assert result.quote_card.attribution == social_config["brand"]["name"]


# ---------------------------------------------------------------------------
# Verificación de cifras
# ---------------------------------------------------------------------------


class TestKeyFigures:
    """Filtrado de cifras contra el texto del artículo."""

    def test_keeps_only_figures_present_in_the_article(self, copy_payload, article, social_config):
        result = build_social_copy(copy_payload, article, social_config)

        assert "44 años" in result.key_figures

    def test_drops_fabricated_figures(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload["key_figures"] = ["98 por ciento de aprobación"]

        result = build_social_copy(payload, article, social_config)

        assert result.key_figures == article.key_figures

    def test_handles_a_missing_field(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload.pop("key_figures")

        result = build_social_copy(payload, article, social_config)

        assert result.key_figures == article.key_figures


# ---------------------------------------------------------------------------
# Ajuste a los límites de plataforma
# ---------------------------------------------------------------------------


class TestPlatformLimits:
    """Recorte determinista al límite de caracteres de cada plataforma."""

    def test_trims_a_tweet_that_exceeds_the_limit(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload["x"]["thread"][1] = " ".join(["palabra"] * 80)
        payload["x"]["hashtags"] = []

        result = build_social_copy(payload, article, social_config)

        assert len(result.x.thread[1]) <= SOCIAL_X_MAX_CHARS

    def test_trims_a_thread_longer_than_allowed(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload["x"]["thread"] = [f"Tweet número {index} del hilo" for index in range(12)]

        result = build_social_copy(payload, article, social_config)

        assert len(result.x.thread) <= social_config["platforms"]["x"]["thread_max_tweets"]

    def test_trims_facebook_post_to_the_limit(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload["facebook"]["post"] = " ".join(["palabra"] * 400)

        result = build_social_copy(payload, article, social_config)

        assert len(result.facebook.post) <= social_config["platforms"]["facebook"]["max_chars"]

    def test_trims_instagram_caption_to_the_limit(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload["instagram"]["caption"] = " ".join(["palabra"] * 700)

        result = build_social_copy(payload, article, social_config)

        assert len(result.instagram.caption) <= (
            social_config["platforms"]["instagram"]["caption_max_chars"]
        )

    def test_caps_hashtags_to_the_platform_limit(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload["instagram"]["hashtags"] = [f"Etiqueta{index}" for index in range(40)]

        result = build_social_copy(payload, article, social_config)

        assert len(result.instagram.hashtags) <= (
            social_config["platforms"]["instagram"]["max_hashtags"]
        )

    def test_reserves_room_for_hashtags_in_the_closing_tweet(
        self, copy_payload, article, social_config
    ):
        payload = copy_module.deepcopy(copy_payload)
        payload["x"]["thread"][-1] = " ".join(["palabra"] * 60)
        payload["x"]["hashtags"] = ["Chile", "LaAraucania", "DerechosHumanos"]

        result = build_social_copy(payload, article, social_config)

        assert len(result.x.thread[-1]) <= SOCIAL_X_MAX_CHARS
        assert "#DerechosHumanos" in result.x.thread[-1]

    def test_does_not_duplicate_hashtags_that_the_model_put_in_the_text(
        self, copy_payload, article, social_config
    ):
        payload = copy_module.deepcopy(copy_payload)
        payload["x"]["thread"][-1] = "Cierre del hilo. #Chile #LaAraucania"
        payload["x"]["hashtags"] = ["Chile", "LaAraucania"]

        result = build_social_copy(payload, article, social_config)

        closing = result.x.thread[-1]
        assert closing.count("#Chile") == 1
        assert closing.count("#LaAraucania") == 1

    def test_strips_hashtags_from_the_facebook_post(
        self, copy_payload, article, social_config
    ):
        payload = copy_module.deepcopy(copy_payload)
        payload["facebook"]["post"] = "Cierre con pregunta.\n\n#Chile #Protesta"

        result = build_social_copy(payload, article, social_config)

        assert "#" not in result.facebook.post
        assert result.facebook.post.endswith("Cierre con pregunta.")

    def test_strips_hashtags_from_the_instagram_caption(
        self, copy_payload, article, social_config
    ):
        payload = copy_module.deepcopy(copy_payload)
        payload["instagram"]["caption"] = "Lee la nota completa.\n\n#Chile #Medios"

        result = build_social_copy(payload, article, social_config)

        assert "#" not in result.instagram.caption

    def test_rejects_a_post_made_only_of_hashtags(
        self, copy_payload, article, social_config
    ):
        payload = copy_module.deepcopy(copy_payload)
        payload["facebook"]["post"] = "#Chile #Protesta"

        with pytest.raises(SocialCopyValidationError, match="Facebook"):
            build_social_copy(payload, article, social_config)


# ---------------------------------------------------------------------------
# Guardas del contrato
# ---------------------------------------------------------------------------


class TestBuildSocialCopyGuards:
    """Rechazo de respuestas que no cumplen el contrato."""

    def test_rejects_missing_hooks(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload["hooks"] = []

        with pytest.raises(SocialCopyValidationError, match="gancho"):
            build_social_copy(payload, article, social_config)

    def test_rejects_missing_summary(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload.pop("summary")

        with pytest.raises(SocialCopyValidationError, match="síntesis"):
            build_social_copy(payload, article, social_config)

    def test_rejects_empty_thread(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload["x"] = {"hook_tweet": "", "thread": [], "hashtags": []}

        with pytest.raises(SocialCopyValidationError, match="tweet"):
            build_social_copy(payload, article, social_config)

    def test_rejects_missing_x_block(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload.pop("x")

        with pytest.raises(SocialCopyValidationError):
            build_social_copy(payload, article, social_config)

    def test_rejects_empty_facebook_post(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload["facebook"] = {"post": ""}

        with pytest.raises(SocialCopyValidationError, match="Facebook"):
            build_social_copy(payload, article, social_config)

    def test_rejects_empty_instagram_caption(self, copy_payload, article, social_config):
        payload = copy_module.deepcopy(copy_payload)
        payload["instagram"] = {"caption": None}

        with pytest.raises(SocialCopyValidationError, match="Instagram"):
            build_social_copy(payload, article, social_config)


# ---------------------------------------------------------------------------
# Generación con el modelo
# ---------------------------------------------------------------------------


class TestGenerateSocialCopy:
    """Reintentos de la llamada al modelo hasta obtener copys válidos."""

    def test_returns_copy_on_the_first_valid_response(
        self, copy_payload, article, social_config
    ):
        import json

        client = FakeClient([json.dumps(copy_payload, ensure_ascii=False)])

        result = generate_social_copy(article, social_config, client)

        assert isinstance(result, SocialCopy)
        assert len(client.calls) == 1

    def test_retries_when_the_response_is_not_json(self, copy_payload, article, social_config):
        import json

        client = FakeClient(
            [
                "Lo siento, no puedo generar el contenido.",
                json.dumps(copy_payload, ensure_ascii=False),
            ]
        )

        result = generate_social_copy(article, social_config, client)

        assert isinstance(result, SocialCopy)
        assert len(client.calls) == 2

    def test_retries_when_the_payload_is_incomplete(self, copy_payload, article, social_config):
        import json

        incomplete = copy_module.deepcopy(copy_payload)
        incomplete["hooks"] = []
        client = FakeClient(
            [
                json.dumps(incomplete, ensure_ascii=False),
                json.dumps(copy_payload, ensure_ascii=False),
            ]
        )

        result = generate_social_copy(article, social_config, client)

        assert isinstance(result, SocialCopy)
        assert len(client.calls) == 2

    def test_raises_after_exhausting_retries(self, article, social_config):
        client = FakeClient(["sin json"] * (SOCIAL_JSON_MAX_RETRIES + 1))

        with pytest.raises(SocialCopyValidationError, match="intento"):
            generate_social_copy(article, social_config, client)

        assert len(client.calls) == SOCIAL_JSON_MAX_RETRIES + 1

    def test_includes_a_correction_note_on_retry(self, copy_payload, article, social_config):
        import json

        client = FakeClient(["sin json", json.dumps(copy_payload, ensure_ascii=False)])

        generate_social_copy(article, social_config, client)

        assert "Corrección" in client.calls[1][1]
        assert "Corrección" not in client.calls[0][1]

    def test_propagates_client_errors(self, article, social_config):
        client = FakeClient([LLMClientError("fallo de red")])

        with pytest.raises(LLMClientError):
            generate_social_copy(article, social_config, client)

    def test_sends_the_article_material_in_the_prompt(self, copy_payload, article, social_config):
        import json

        client = FakeClient([json.dumps(copy_payload, ensure_ascii=False)])

        generate_social_copy(article, social_config, client)

        _, user_prompt = client.calls[0]
        assert article.title in user_prompt
        assert "Límites por plataforma" in user_prompt
