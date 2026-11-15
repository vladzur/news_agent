"""Tests del editor de portada: propuestas de titular y bajada."""

import json

import pytest

from news_agent.headline_editor import (
    APPENDIX_HEADING,
    ENFOQUES,
    HeadlineProposal,
    HeadlineValidationError,
    append_headline_appendix,
    apply_headline,
    build_appendix,
    build_proposals,
    count_words,
    fit_length,
    generate_headline_proposals,
)
from news_agent.social.article_source import parse_article_file

# ---------------------------------------------------------------------------
# Material de ejemplo
# ---------------------------------------------------------------------------

TITULAR_OK = (
    "No es el clima, es el bloqueo: muere un bebé por frío mientras "
    "miles de carpas"
)  # 16 palabras

BAJADA_OK = (
    "El Ministerio de Salud gazatí confirmó la muerte de Kinan Ahmed Raqiq "
    "por hipotermia en Jan Yunis, mientras casi dos millones de personas "
    "viven en carpas y la ayuda permanece frenada en la frontera."
)  # 34 palabras

ARTICULO = """\
# Titular original del redactor

**Por La Chispa Sur**

---

*Bajada original del redactor.*

Un primer párrafo con el lead del artículo.

## Una sección

Texto de la sección.
"""


def _payload(titular: str = TITULAR_OK, bajada: str = BAJADA_OK) -> dict:
    """Construye un payload JSON válido con tres propuestas iguales.

    Args:
        titular: Titular a repetir en las tres propuestas.
        bajada: Bajada a repetir en las tres propuestas.

    Returns:
        dict: Payload con la forma que devuelve el modelo.
    """
    return {
        "propuestas": [
            {"titular": titular, "bajada": bajada},
            {"titular": titular, "bajada": bajada},
            {"titular": titular, "bajada": bajada},
        ]
    }


class _FakeClient:
    """Cliente LLM que devuelve respuestas prefijadas y cuenta las llamadas."""

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls = 0

    def generate_report(self, system_prompt: str, user_prompt: str) -> str:
        """Devuelve la siguiente respuesta prefijada.

        Args:
            system_prompt: Ignorado.
            user_prompt: Ignorado.

        Returns:
            str: Respuesta del turno.
        """
        self.calls += 1
        return self.responses.pop(0)


# ---------------------------------------------------------------------------
# Largos
# ---------------------------------------------------------------------------


class TestLengths:
    """Conteo y ajuste de palabras."""

    def test_counts_words(self):
        assert count_words("uno dos tres") == 3

    def test_fit_length_keeps_a_text_in_range(self):
        assert fit_length("titular", TITULAR_OK, 12, 16) == TITULAR_OK

    def test_fit_length_trims_a_long_text_at_a_clause(self):
        text = (
            "Primera afirmación editorial muy contundente sobre el conflicto "
            "político: dato duro concreto que sostiene la tesis y suma "
            "contexto adicional"
        )

        result = fit_length("titular", text, 12, 16)

        assert count_words(result) <= 16
        assert result == (
            "Primera afirmación editorial muy contundente sobre el "
            "conflicto político"
        )

    def test_fit_length_keeps_a_short_text_and_warns(self, caplog):
        with caplog.at_level("WARNING"):
            result = fit_length("bajada", "Bajada demasiado corta.", 25, 45)

        assert result == "Bajada demasiado corta."
        assert "no se puede alargar" in caplog.text


# ---------------------------------------------------------------------------
# Validación del payload
# ---------------------------------------------------------------------------


class TestBuildProposals:
    """Validación de la respuesta del modelo."""

    def test_builds_three_proposals_with_the_fixed_enfoques(self):
        proposals = build_proposals(_payload())

        assert [p.enfoque for p in proposals] == list(ENFOQUES)
        assert all(p.titular == TITULAR_OK for p in proposals)

    def test_rejects_a_payload_without_three_proposals(self):
        payload = {"propuestas": [{"titular": TITULAR_OK, "bajada": BAJADA_OK}]}

        with pytest.raises(HeadlineValidationError, match="3 propuestas"):
            build_proposals(payload)

    def test_rejects_a_proposal_without_bajada(self):
        payload = _payload()
        payload["propuestas"][1]["bajada"] = ""

        with pytest.raises(HeadlineValidationError, match="sin bajada"):
            build_proposals(payload)

    def test_rejects_a_headline_out_of_range(self):
        payload = _payload(titular="Titular demasiado corto")

        with pytest.raises(HeadlineValidationError, match="titular"):
            build_proposals(payload)

    def test_rejects_a_deck_out_of_range(self):
        payload = _payload(bajada="Bajada corta.")

        with pytest.raises(HeadlineValidationError, match="bajada"):
            build_proposals(payload)

    def test_non_strict_mode_trims_instead_of_rejecting(self):
        long_title = (
            "No es el clima, es el bloqueo: muere un bebé por frío mientras "
            "miles de carpas siguen retenidas y la ayuda espera sin fecha"
        )

        proposals = build_proposals(_payload(titular=long_title), strict=False)

        assert count_words(proposals[0].titular) <= 16


# ---------------------------------------------------------------------------
# Llamada al modelo
# ---------------------------------------------------------------------------


class TestGenerateHeadlineProposals:
    """Reintentos y degradación controlada."""

    def test_returns_the_proposals_on_the_first_try(self):
        client = _FakeClient(json.dumps(_payload()))

        proposals = generate_headline_proposals("artículo", client)

        assert len(proposals) == 3
        assert client.calls == 1

    def test_retries_when_the_response_is_not_json(self):
        client = _FakeClient("esto no es JSON", json.dumps(_payload()))

        proposals = generate_headline_proposals("artículo", client)

        assert len(proposals) == 3
        assert client.calls == 2

    def test_retries_when_the_lengths_are_out_of_range(self):
        short = json.dumps(_payload(titular="Muy corto"))
        client = _FakeClient(short, json.dumps(_payload()))

        proposals = generate_headline_proposals("artículo", client)

        assert proposals[0].titular == TITULAR_OK
        assert client.calls == 2

    def test_adjusts_by_code_when_the_retry_also_breaks_the_rules(self):
        long_title = (
            "No es el clima, es el bloqueo: muere un bebé por frío mientras "
            "miles de carpas siguen retenidas y la ayuda espera sin fecha"
        )
        broken = json.dumps(_payload(titular=long_title))
        client = _FakeClient(broken, broken)

        proposals = generate_headline_proposals("artículo", client)

        assert count_words(proposals[0].titular) <= 16
        assert client.calls == 2

    def test_raises_when_no_attempt_returns_json(self):
        client = _FakeClient("nada", "tampoco")

        with pytest.raises(HeadlineValidationError, match="No se pudieron"):
            generate_headline_proposals("artículo", client)

    def test_sends_the_article_and_the_pauta_angle(self):
        client = _FakeClient(json.dumps(_payload()))

        captured: dict[str, str] = {}

        def _fake_generate(system_prompt: str, user_prompt: str) -> str:
            captured["system"] = system_prompt
            captured["user"] = user_prompt
            return json.dumps(_payload())

        client.generate_report = _fake_generate

        generate_headline_proposals(
            "CUERPO DEL ARTÍCULO",
            client,
            {"title": "Título de pauta", "enfoque": "Enfoque aprobado"},
        )

        assert "CUERPO DEL ARTÍCULO" in captured["user"]
        assert "Título de pauta" in captured["user"]
        assert "editor de portada" in captured["system"]


# ---------------------------------------------------------------------------
# Aplicación al artículo
# ---------------------------------------------------------------------------


class TestApplyHeadline:
    """Reemplazo del titular y de la bajada."""

    @pytest.fixture
    def proposals(self) -> list[HeadlineProposal]:
        """Propuestas de ejemplo."""
        return [
            HeadlineProposal(ENFOQUES[0], TITULAR_OK, BAJADA_OK),
            HeadlineProposal(ENFOQUES[1], TITULAR_OK, BAJADA_OK),
            HeadlineProposal(ENFOQUES[2], TITULAR_OK, BAJADA_OK),
        ]

    def test_replaces_the_title_and_the_existing_deck(self, proposals):
        result = apply_headline(ARTICULO, proposals)

        assert result.startswith(f"# {TITULAR_OK}")
        assert f"*{BAJADA_OK}*" in result
        assert "Titular original del redactor" not in result
        assert "Bajada original del redactor" not in result

    def test_keeps_a_blank_line_between_the_deck_and_the_lead(self, proposals):
        result = apply_headline(ARTICULO, proposals)

        assert f"*{BAJADA_OK}*\n\nUn primer párrafo" in result

    def test_inserts_the_deck_when_the_article_has_none(self, proposals):
        article = (
            "# Título\n\n**Por La Chispa Sur**\n\n---\n\nPrimer párrafo.\n"
        )

        result = apply_headline(article, proposals)

        assert f"---\n\n*{BAJADA_OK}*\n\nPrimer párrafo." in result

    def test_inserts_the_deck_without_a_rule(self, proposals):
        article = "# Título\n\n**Por La Chispa Sur**\n\nPrimer párrafo.\n"

        result = apply_headline(article, proposals)

        assert f"---\n\n*{BAJADA_OK}*\n\nPrimer párrafo." in result

    def test_without_proposals_returns_the_article_untouched(self):
        assert apply_headline(ARTICULO, []) == ARTICULO


# ---------------------------------------------------------------------------
# Apéndice
# ---------------------------------------------------------------------------


class TestAppendix:
    """Bloque con las tres propuestas al final del artículo."""

    @pytest.fixture
    def proposals(self) -> list[HeadlineProposal]:
        """Propuestas de ejemplo."""
        return [
            HeadlineProposal(ENFOQUES[0], TITULAR_OK, BAJADA_OK),
            HeadlineProposal(ENFOQUES[1], TITULAR_OK, BAJADA_OK),
            HeadlineProposal(ENFOQUES[2], TITULAR_OK, BAJADA_OK),
        ]

    def test_lists_the_three_proposals(self, proposals):
        result = build_appendix(proposals)

        assert APPENDIX_HEADING in result
        for enfoque in ENFOQUES:
            assert enfoque in result
        assert result.count("**Titular:**") == 3
        assert result.count("**Bajada:**") == 3

    def test_marks_only_the_first_as_applied(self, proposals):
        result = build_appendix(proposals)

        assert result.count("✅ aplicada al artículo") == 1
        assert f"### 1. {ENFOQUES[0]} — ✅ aplicada al artículo" in result

    def test_appends_the_block_to_the_article(self, proposals):
        result = append_headline_appendix(ARTICULO, proposals)

        assert result.startswith("# Titular original del redactor")
        assert APPENDIX_HEADING in result
        assert result.index(APPENDIX_HEADING) > result.index("Texto de la sección")

    def test_replaces_an_existing_appendix_instead_of_duplicating_it(
        self, proposals
    ):
        once = append_headline_appendix(ARTICULO, proposals)
        twice = append_headline_appendix(once, proposals)

        assert twice.count(APPENDIX_HEADING) == 1
        assert twice.count("---") == once.count("---")


# ---------------------------------------------------------------------------
# Integración con el parser de RRSS
# ---------------------------------------------------------------------------


class TestSocialParserIgnoresTheAppendix:
    """El apéndice no es material publicable para redes sociales."""

    def test_appendix_is_not_part_of_the_body(self, tmp_path):
        proposals = [
            HeadlineProposal(ENFOQUES[0], TITULAR_OK, BAJADA_OK),
            HeadlineProposal(ENFOQUES[1], TITULAR_OK, BAJADA_OK),
            HeadlineProposal(ENFOQUES[2], TITULAR_OK, BAJADA_OK),
        ]
        content = append_headline_appendix(ARTICULO, proposals)
        path = tmp_path / "articulo_1_portada.md"
        path.write_text(content, encoding="utf-8")

        article = parse_article_file(path)

        assert article.title == "Titular original del redactor"
        assert "Propuestas de portada" not in article.body_text()
        assert all("Propuestas" not in s.heading for s in article.sections)

    def test_appendix_does_not_pollute_the_sources(self, tmp_path):
        article_with_sources = (
            f"{ARTICULO}\n---\n\n**Fuentes consultadas / sugeridas:**\n"
            "- Radio Nuevo Mundo\n- La Tercera\n"
        )
        proposals = [HeadlineProposal(ENFOQUES[0], TITULAR_OK, BAJADA_OK)]
        content = append_headline_appendix(article_with_sources, proposals)
        path = tmp_path / "articulo_2_portada.md"
        path.write_text(content, encoding="utf-8")

        article = parse_article_file(path)

        assert article.sources == ["Radio Nuevo Mundo", "La Tercera"]
