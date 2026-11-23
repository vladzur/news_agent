"""Tests del editor periodístico: revisión y corrección del artículo."""

import json

import pytest

from news_agent.article_writer import looks_like_article
from news_agent.editorial_review import (
    ArticleParts,
    EditorialReview,
    EditorialReviewError,
    apply_review,
    build_review,
    review_and_correct,
    split_article,
    update_applied_proposal,
)
from news_agent.headline_editor import (
    APPENDIX_HEADING,
    ENFOQUES,
    HeadlineProposal,
)
from news_agent.llm_client import LLMClientError

# ---------------------------------------------------------------------------
# Material de ejemplo
# ---------------------------------------------------------------------------

HEADLINE = (
    "No es el clima, es el bloqueo: muere un bebé por frío mientras "
    "miles de carpas"
)  # 16 palabras

DECK = (
    "El Ministerio de Salud gazatí confirmó la muerte de Kinan Ahmed Raqiq "
    "por hipotermia en Jan Yunis, mientras casi dos millones de personas "
    "viven en carpas y la ayuda permanece frenada en la frontera."
)  # 34 palabras

ARTICLE = f"""\
# {HEADLINE}

**Por La Chispa Sur**

---

*{DECK}*

Un primer párrafo con el lead del artículo y la tesis principal del caso.

## Primera sección

Texto de la primera sección con datos y contexto del análisis.

## Segunda sección

Texto de la segunda sección que cierra el argumento y conecta con el territorio.

---

*Artículo generado a partir de la pauta editorial de La Chispa Sur.*

**Fuentes consultadas / sugeridas:**
- Fuente A
- Fuente B
"""

REVIEWED_HEADLINE = (
    "El bloqueo mata en silencio: un bebé muere por frío mientras la ayuda "
    "sigue retenida en la frontera"
)  # 17 palabras: se usa solo donde no se valida el largo

REVIEWED_DECK = (
    "La muerte de Kinan Ahmed Raqiq por hipotermia en Jan Yunis expone el "
    "costo humano del bloqueo, mientras casi dos millones de personas "
    "sobreviven en carpas y la ayuda espera sin fecha."
)  # 30 palabras


def _payload(
    headline: str = HEADLINE,
    deck: str = DECK,
    body: str | None = None,
    changes: str = "Se corrigió una transición.",
) -> dict:
    """Construye un payload válido de revisión.

    Args:
        headline: Titular corregido.
        deck: Bajada corregida.
        body: Cuerpo corregido; por defecto, el cuerpo del artículo de ejemplo.
        changes: Resumen de correcciones.

    Returns:
        dict: Payload con la forma que devuelve el modelo.
    """
    parts = split_article(ARTICLE)
    return {
        "titular": headline,
        "bajada": deck,
        "cuerpo": body if body is not None else parts.body,
        "resumen_cambios": changes,
    }


def _corrected_body() -> str:
    """Devuelve el cuerpo del artículo con una corrección mínima."""
    return split_article(ARTICLE).body.replace(
        "Un primer párrafo", "El primer párrafo"
    )


class _FakeClient:
    """Cliente LLM que devuelve respuestas prefijadas y cuenta las llamadas."""

    def __init__(self, *responses: str | Exception) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.system_prompts: list[str] = []
        self.user_prompts: list[str] = []

    def generate_report(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        self.system_prompts.append(system_prompt)
        self.user_prompts.append(user_prompt)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


# ---------------------------------------------------------------------------
# Separación de las piezas
# ---------------------------------------------------------------------------


class TestSplitArticle:
    """Pruebas de la separación de titular, bajada y cuerpo."""

    def test_splits_the_three_pieces(self):
        parts = split_article(ARTICLE)

        assert parts.headline == HEADLINE
        assert parts.deck == DECK
        assert parts.body.startswith("Un primer párrafo")
        assert "**Fuentes consultadas / sugeridas:**" in parts.body

    def test_keeps_the_body_offset_inside_the_article(self):
        parts = split_article(ARTICLE)

        assert ARTICLE[parts.body_start:].startswith("Un primer párrafo")

    def test_rejects_an_article_with_the_portada_appendix(self):
        with pytest.raises(EditorialReviewError, match="apéndice"):
            split_article(f"{ARTICLE}\n\n{APPENDIX_HEADING}\n")

    def test_rejects_an_article_without_headline(self):
        article = ARTICLE.replace(f"# {HEADLINE}\n\n", "", 1)

        with pytest.raises(EditorialReviewError, match="titular"):
            split_article(article)

    def test_rejects_an_article_without_byline(self):
        article = ARTICLE.replace("**Por La Chispa Sur**\n\n", "", 1)

        with pytest.raises(EditorialReviewError, match="firma"):
            split_article(article)

    def test_rejects_an_article_without_deck(self):
        article = ARTICLE.replace(f"*{DECK}*", DECK, 1)

        with pytest.raises(EditorialReviewError, match="bajada"):
            split_article(article)


# ---------------------------------------------------------------------------
# Validación de la respuesta
# ---------------------------------------------------------------------------


class TestBuildReview:
    """Pruebas del contrato y de las guardas del cuerpo."""

    def test_accepts_a_valid_response(self):
        review = build_review(_payload(), split_article(ARTICLE))

        assert review.headline == HEADLINE
        assert review.deck == DECK
        assert review.body.startswith("Un primer párrafo")
        assert review.changes == "Se corrigió una transición."

    def test_rejects_a_response_that_is_not_an_object(self):
        with pytest.raises(EditorialReviewError, match="objeto JSON"):
            build_review(["no", "es", "json"], split_article(ARTICLE))

    def test_rejects_a_response_without_body(self):
        payload = _payload()
        payload["cuerpo"] = ""

        with pytest.raises(EditorialReviewError, match="cuerpo vacío"):
            build_review(payload, split_article(ARTICLE))

    def test_rejects_a_body_with_a_level_one_headline(self):
        body = f"# Otro titular\n\n{_corrected_body()}"

        with pytest.raises(EditorialReviewError, match="nivel 1"):
            build_review(_payload(body=body), split_article(ARTICLE))

    def test_rejects_a_body_with_the_portada_appendix(self):
        body = f"{_corrected_body()}\n\n{APPENDIX_HEADING}\n"

        with pytest.raises(EditorialReviewError, match="apéndice"):
            build_review(_payload(body=body), split_article(ARTICLE))

    def test_rejects_a_body_with_the_byline(self):
        body = f"**Por La Chispa Sur**\n\n{_corrected_body()}"

        with pytest.raises(EditorialReviewError, match="firma"):
            build_review(_payload(body=body), split_article(ARTICLE))

    def test_rejects_a_body_with_a_different_section_count(self):
        body = _corrected_body().replace("## Segunda sección\n\n", "", 1)

        with pytest.raises(EditorialReviewError, match="secciones"):
            build_review(_payload(body=body), split_article(ARTICLE))

    def test_rejects_a_body_that_summarized_the_article(self):
        body = (
            "Corto.\n\n## Primera sección\n\nTexto.\n\n"
            "## Segunda sección\n\nTexto.\n\n"
            "**Fuentes consultadas / sugeridas:**\n- Fuente A"
        )

        with pytest.raises(EditorialReviewError, match="resumido o expandido"):
            build_review(_payload(body=body), split_article(ARTICLE))

    def test_rejects_a_body_that_expanded_the_article(self):
        body = f"{_corrected_body()}\n\n{'relleno ' * 120}"

        with pytest.raises(EditorialReviewError, match="resumido o expandido"):
            build_review(_payload(body=body), split_article(ARTICLE))

    def test_rejects_a_body_without_the_sources_block(self):
        body = _corrected_body().replace(
            "**Fuentes consultadas / sugeridas:**", "**Otras fuentes:**", 1
        )

        with pytest.raises(EditorialReviewError, match="fuentes"):
            build_review(_payload(body=body), split_article(ARTICLE))

    def test_rejects_a_body_that_repeats_the_deck(self):
        body = (
            f"*{DECK}*\n\nCorto.\n\n## Primera sección\n\nTexto.\n\n"
            "## Segunda sección\n\nTexto.\n\n"
            "**Fuentes consultadas / sugeridas:**\n- Fuente A"
        )

        with pytest.raises(EditorialReviewError, match="repite la bajada"):
            build_review(_payload(body=body), split_article(ARTICLE))

    def test_removes_internal_article_references(self, caplog):
        body = _corrected_body().replace(
            "el caso.", "el caso [art. 7].", 1
        )

        review = build_review(_payload(body=body), split_article(ARTICLE))

        assert "[art. 7]" not in review.body
        assert "referencia" in caplog.text

    def test_keeps_the_previous_headline_when_the_review_breaks_the_range(self):
        review = build_review(
            _payload(headline="Titular demasiado corto"),
            split_article(ARTICLE),
        )

        assert review.headline == HEADLINE

    def test_keeps_the_previous_deck_when_the_review_breaks_the_range(self):
        review = build_review(
            _payload(deck="Bajada corta"),
            split_article(ARTICLE),
        )

        assert review.deck == DECK

    def test_truncates_the_changes_summary(self):
        review = build_review(
            _payload(changes="x" * 500),
            split_article(ARTICLE),
        )

        assert len(review.changes) == 400


# ---------------------------------------------------------------------------
# Llamada al modelo
# ---------------------------------------------------------------------------


class TestReviewAndCorrect:
    """Reintentos y propagación de errores."""

    def test_returns_the_review_on_the_first_try(self):
        client = _FakeClient(json.dumps(_payload(body=_corrected_body())))

        review = review_and_correct(ARTICLE, client)

        assert review.body.startswith("El primer párrafo")
        assert client.calls == 1

    def test_retries_when_the_response_is_not_json(self):
        client = _FakeClient(
            "esto no es JSON",
            json.dumps(_payload(body=_corrected_body())),
        )

        review = review_and_correct(ARTICLE, client)

        assert review.body.startswith("El primer párrafo")
        assert client.calls == 2
        assert "Corrección" in client.user_prompts[1]

    def test_retries_when_the_body_breaks_the_contract(self):
        broken = _corrected_body().replace("## Segunda sección\n\n", "", 1)
        client = _FakeClient(
            json.dumps(_payload(body=broken)),
            json.dumps(_payload(body=_corrected_body())),
        )

        review = review_and_correct(ARTICLE, client)

        assert review.body.startswith("El primer párrafo")
        assert client.calls == 2

    def test_raises_when_no_attempt_is_usable(self):
        client = _FakeClient("nada", "tampoco")

        with pytest.raises(EditorialReviewError, match="No se pudo aplicar"):
            review_and_correct(ARTICLE, client)

    def test_propagates_llm_errors(self):
        client = _FakeClient(LLMClientError("sin conexión"))

        with pytest.raises(LLMClientError):
            review_and_correct(ARTICLE, client)

    def test_sends_the_pieces_and_the_approved_angle(self):
        client = _FakeClient(json.dumps(_payload(body=_corrected_body())))

        review_and_correct(
            ARTICLE,
            client,
            {"title": "Título de pauta", "enfoque": "Enfoque aprobado"},
        )

        user_prompt = client.user_prompts[0]
        assert "editor periodístico" in client.system_prompts[0]
        assert HEADLINE in user_prompt
        assert DECK in user_prompt
        assert "Un primer párrafo" in user_prompt
        assert "Título de pauta" in user_prompt
        assert "Enfoque aprobado" in user_prompt

    def test_rejects_an_unparseable_article_without_calling_the_model(self):
        client = _FakeClient("")

        with pytest.raises(EditorialReviewError, match="firma"):
            review_and_correct("# Solo un titular", client)

        assert client.calls == 0


# ---------------------------------------------------------------------------
# Aplicación al artículo
# ---------------------------------------------------------------------------


class TestApplyReview:
    """Reensamblado del artículo con las piezas corregidas."""

    def test_replaces_the_three_pieces(self):
        review = EditorialReview(
            headline=REVIEWED_HEADLINE,
            deck=REVIEWED_DECK,
            body=_corrected_body(),
            changes="Corrección de una transición.",
        )

        content = apply_review(ARTICLE, review)

        assert content.startswith(f"# {REVIEWED_HEADLINE}\n")
        assert f"*{REVIEWED_DECK}*" in content
        assert "El primer párrafo" in content
        assert "**Por La Chispa Sur**" in content
        assert "**Fuentes consultadas / sugeridas:**" in content
        assert looks_like_article(content)

    def test_keeps_the_original_separators_and_byline(self):
        review = EditorialReview(
            headline=REVIEWED_HEADLINE,
            deck=REVIEWED_DECK,
            body=_corrected_body(),
        )

        content = apply_review(ARTICLE, review)

        assert content.count("---") == 2
        assert content.count("**Por La Chispa Sur**") == 1

    def test_rejects_an_article_with_the_appendix(self):
        review = EditorialReview(
            headline=REVIEWED_HEADLINE,
            deck=REVIEWED_DECK,
            body=_corrected_body(),
        )

        with pytest.raises(EditorialReviewError, match="apéndice"):
            apply_review(f"{ARTICLE}\n\n{APPENDIX_HEADING}\n", review)


# ---------------------------------------------------------------------------
# Sincronización del apéndice
# ---------------------------------------------------------------------------


class TestUpdateAppliedProposal:
    """Actualización de la propuesta de portada aplicada."""

    @pytest.fixture
    def proposals(self) -> list[HeadlineProposal]:
        return [
            HeadlineProposal(ENFOQUES[0], HEADLINE, DECK),
            HeadlineProposal(ENFOQUES[1], "Titular alternativo uno", DECK),
            HeadlineProposal(ENFOQUES[2], "Titular alternativo dos", DECK),
        ]

    def test_updates_the_first_and_keeps_the_alternatives(self, proposals):
        review = EditorialReview(
            headline=REVIEWED_HEADLINE,
            deck=REVIEWED_DECK,
            body=_corrected_body(),
        )

        updated = update_applied_proposal(proposals, review)

        assert updated[0].titular == REVIEWED_HEADLINE
        assert updated[0].bajada == REVIEWED_DECK
        assert updated[0].enfoque == ENFOQUES[0]
        assert updated[1] == proposals[1]
        assert updated[2] == proposals[2]

    def test_returns_an_empty_list_without_proposals(self):
        review = EditorialReview(
            headline=REVIEWED_HEADLINE,
            deck=REVIEWED_DECK,
            body=_corrected_body(),
        )

        assert update_applied_proposal([], review) == []


# ---------------------------------------------------------------------------
# Tipos auxiliares
# ---------------------------------------------------------------------------


def test_article_parts_and_review_are_frozen():
    """Los resultados de la revisión no deben mutarse por accidente."""
    parts = ArticleParts("h", "d", "b", 0)
    review = EditorialReview("h", "d", "b")

    with pytest.raises(AttributeError):
        parts.body = "otro"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        review.body = "otro"  # type: ignore[misc]
