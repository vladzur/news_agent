"""Tests para el módulo de referencias a fuentes (source_references)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from news_agent.source_references import (
    _build_companion_path,
    _extract_keywords,
    _score_article_match,
    _source_names_match,
    _truncate_content,
    build_companion_data,
    extract_proposal_sources,
    load_companion_data,
    match_sources_to_articles,
)


# ---------------------------------------------------------------------------
# Tests para extract_proposal_sources
# ---------------------------------------------------------------------------


class TestExtractProposalSources:
    """Pruebas para extract_proposal_sources."""

    def test_extracts_sources_from_valid_pauta(self):
        """Debe extraer fuentes correctamente desde una pauta válida."""
        pauta_text = """# ⚡ Pauta Editorial Sugerida - La Chispa Sur

---

## 1. Título de Propuesta 1
*   **Enfoque Editorial:** Análisis de prueba.
*   **Puntos Clave a Desarrollar:**
    1. Punto 1
    2. Punto 2
*   **Fuentes Sugeridas para Ampliar:**
    *   **CIPER Chile:** Su investigación sobre la sanción al proyecto en Villarrica.
    *   **DF Diario:** La cobertura de la condena judicial.

## 2. Título de Propuesta 2
*   **Enfoque Editorial:** Otro análisis.
*   **Fuentes Sugeridas para Ampliar:**
    *   **La Tercera:** Su nota sobre la megarreforma tributaria.
    *   **Cooperativa:** El reporte del sistema frontal en el sur.

## 3. Título de Propuesta 3
*   **Enfoque Editorial:** Tercer análisis.
*   **Fuentes Sugeridas para Ampliar:**
    *   **El Mostrador:** Su columna sobre educación.
"""
        result = extract_proposal_sources(pauta_text)

        assert len(result) == 3
        assert len(result[1]) == 2
        assert result[1][0]["source_name"] == "CIPER Chile"
        assert "sanción al proyecto en Villarrica" in result[1][0]["description"]
        assert result[1][1]["source_name"] == "DF Diario"
        assert len(result[2]) == 2
        assert len(result[3]) == 1

    def test_handles_pauta_without_fuentes_section(self):
        """Debe retornar vacío si no hay sección Fuentes Sugeridas."""
        pauta_text = """# Pauta

## 1. Sin fuentes
*   **Enfoque Editorial:** Algo.
*   **Puntos Clave a Desarrollar:**
    1. Punto
"""
        result = extract_proposal_sources(pauta_text)
        assert result == {}

    def test_handles_mixed_proposals(self):
        """Algunas propuestas con fuentes, otras sin."""
        pauta_text = """# Pauta

## 1. Con fuentes
*   **Fuentes Sugeridas para Ampliar:**
    *   **Medio A:** Descripción A.

## 2. Sin fuentes
*   **Enfoque Editorial:** Algo.

## 3. Con fuentes
*   **Fuentes Sugeridas para Ampliar:**
    *   **Medio B:** Descripción B.
"""
        result = extract_proposal_sources(pauta_text)
        assert len(result) == 2
        assert 1 in result
        assert 2 not in result
        assert 3 in result

    def test_extracts_fuentes_without_bold_markup(self):
        """Debe extraer fuentes aunque no usen negrita markdown."""
        pauta_text = """# Pauta

## 1. Propuesta
*   **Fuentes Sugeridas para Ampliar:**
    *   CIPER Chile: Investigación sobre corrupción.
    *   La Tercera: Nota sobre reforma.
"""
        result = extract_proposal_sources(pauta_text)
        assert len(result) == 1
        assert result[1][0]["source_name"] == "CIPER Chile"
        assert result[1][1]["source_name"] == "La Tercera"

    def test_deduplicates_same_source_name(self):
        """No debe duplicar entradas con el mismo nombre de medio."""
        pauta_text = """# Pauta

## 1. Propuesta
*   **Fuentes Sugeridas para Ampliar:**
    *   **CIPER Chile:** Investigación A.
    *   **CIPER Chile:** Investigación B (mismo medio).
    *   **DF Diario:** Cobertura judicial.
"""
        result = extract_proposal_sources(pauta_text)
        # CIPER Chile solo debe aparecer una vez
        assert len(result[1]) == 2

    def test_filters_noise_lines(self):
        """Debe ignorar líneas que no son fuentes reales."""
        pauta_text = """# Pauta

## 1. Propuesta
*   **Fuentes Sugeridas para Ampliar:**
    *   **CIPER Chile:** Investigación completa sobre el caso.
    *   No incluyas URLs inventadas.
    *   a: b
    *   **La Tercera:** Nota complementaria.
"""
        result = extract_proposal_sources(pauta_text)
        assert len(result[1]) == 2
        names = [e["source_name"] for e in result[1]]
        assert "CIPER Chile" in names
        assert "La Tercera" in names


# ---------------------------------------------------------------------------
# Tests para _source_names_match
# ---------------------------------------------------------------------------


class TestSourceNamesMatch:
    """Pruebas para _source_names_match."""

    def test_exact_match(self):
        """Coincidencia exacta insensible a mayúsculas."""
        assert _source_names_match("CIPER Chile", "Ciper Chile") is True

    def test_partial_match_pauta_in_item(self):
        """El nombre de la pauta está contenido en el source del item."""
        assert _source_names_match("CIPER", "Ciper Chile") is True

    def test_partial_match_item_in_pauta(self):
        """El source del item está contenido en el nombre de la pauta."""
        assert _source_names_match("CIPER Chile", "CIPER") is True

    def test_first_word_match(self):
        """Coincidencia por primera palabra."""
        assert _source_names_match("La Tercera", "La Tercera – Pulso") is True

    def test_no_match_different_sources(self):
        """Medios diferentes no deben coincidir."""
        assert _source_names_match("CIPER Chile", "Cooperativa") is False

    def test_short_strings_dont_false_match(self):
        """Strings muy cortos no deben generar falsos positivos."""
        # "DF" tiene solo 2 letras, menor al umbral de 4
        assert _source_names_match("DF", "DF Diario") is False


# ---------------------------------------------------------------------------
# Tests para match_sources_to_articles
# ---------------------------------------------------------------------------


class TestMatchSourcesToArticles:
    """Pruebas para match_sources_to_articles."""

    @pytest.fixture
    def sample_items(self):
        """Artículos de prueba simulando filtered_items."""
        return [
            {
                "title": "Condenan a empresa por tala de bosque nativo en Villarrica",
                "source": "CIPER Chile",
                "summary_clean": "La justicia condenó a Inversiones Ain Ltda. "
                "por cortar especies nativas protegidas en la zona lacustre.",
                "link": "https://example.com/1",
            },
            {
                "title": "Ley Lafkenche y salmonicultura: los datos",
                "source": "CIPER Chile",
                "summary_clean": "Análisis de los datos sobre la industria "
                "salmonera y las ECMPO en el sur de Chile.",
                "link": "https://example.com/2",
            },
            {
                "title": "Megarreforma: PPD anuncia acuerdo con ministro",
                "source": "La Tercera",
                "summary_clean": "El PPD alcanzó un acuerdo con el ministro "
                "Quiroz sobre la invariabilidad tributaria.",
                "link": "https://example.com/3",
            },
            {
                "title": "Sistema frontal: más de 100 viviendas dañadas",
                "source": "Cooperativa",
                "summary_clean": "Balance del sistema frontal que afectó "
                "desde Maule a Los Lagos.",
                "link": "https://example.com/4",
            },
            {
                "title": "Israelíes atacan Líbano",
                "source": "La Tercera",
                "summary_clean": "Amnistía pide investigar crímenes de guerra.",
                "link": "https://example.com/5",
            },
        ]

    def test_matches_by_source_and_keywords(self, sample_items):
        """Debe emparejar fuentes con artículos por medio y keywords."""
        proposal_sources = {
            1: [
                {
                    "source_name": "CIPER Chile",
                    "description": "Su investigación sobre la sanción al "
                    "proyecto en Villarrica por tala de bosque nativo.",
                },
                {
                    "source_name": "Cooperativa",
                    "description": "El reporte del sistema frontal en el sur.",
                },
            ]
        }

        result = match_sources_to_articles(proposal_sources, sample_items)

        assert 1 in result
        matched = result[1]
        # Debe matchear artículo 0 (Villarrica/bosque nativo) y artículo 3 (sistema frontal)
        assert 1 in matched  # CIPER Chile: tala bosque nativo Villarrica
        assert 4 in matched  # Cooperativa: sistema frontal

    def test_returns_empty_when_no_match(self, sample_items):
        """Debe retornar vacío si ninguna fuente coincide."""
        proposal_sources = {
            1: [
                {
                    "source_name": "El Siglo",
                    "description": "Cobertura sobre educación pública.",
                },
            ]
        }

        result = match_sources_to_articles(proposal_sources, sample_items)
        # El Siglo no está en los items de prueba
        assert result == {}

    def test_handles_multiple_proposals(self, sample_items):
        """Debe manejar múltiples propuestas correctamente."""
        proposal_sources = {
            1: [
                {
                    "source_name": "CIPER Chile",
                    "description": "investigación sanción proyecto Villarrica "
                    "tala bosque nativo condena",
                },
            ],
            2: [
                {
                    "source_name": "La Tercera",
                    "description": "nota sobre la megarreforma tributaria PPD "
                    "acuerdo invariabilidad",
                },
            ],
        }

        result = match_sources_to_articles(proposal_sources, sample_items)

        assert 1 in result
        assert 2 in result
        # Propuesta 1: artículo sobre tala en Villarrica (índice 1)
        assert 1 in result[1]
        # Propuesta 2: artículo sobre megarreforma (índice 3)
        assert 3 in result[2]


# ---------------------------------------------------------------------------
# Tests para _score_article_match
# ---------------------------------------------------------------------------


class TestScoreArticleMatch:
    """Pruebas para _score_article_match."""

    def test_high_score_for_relevant_article(self):
        """Debe dar score alto a artículos muy relevantes."""
        description = (
            "investigación sobre la sanción al proyecto inmobiliario "
            "en Villarrica por tala de bosque nativo protegido"
        )
        article = {
            "title": "Condenan a empresa por tala de bosque nativo en Villarrica",
            "summary_clean": "La justicia condenó a Inversiones Ain Ltda. "
            "por cortar especies nativas protegidas en proyecto inmobiliario.",
        }
        score = _score_article_match(description, article)
        assert score > 0.1

    def test_low_score_for_irrelevant_article(self):
        """Debe dar score bajo a artículos no relacionados."""
        description = (
            "investigación sobre la sanción al proyecto en Villarrica "
            "por tala de bosque nativo"
        )
        article = {
            "title": "Resultados del fútbol chileno",
            "summary_clean": "Colo Colo ganó el clásico contra la U.",
        }
        score = _score_article_match(description, article)
        assert score == 0.0

    def test_title_bonus_for_keyword_in_title(self):
        """Keywords que aparecen en el título deben dar bonus."""
        description = "reporte sobre sistema frontal daños viviendas"
        article_with_title_hit = {
            "title": "Sistema frontal: daños en viviendas del sur",
            "summary_clean": "Balance de la emergencia.",
        }
        article_without_title_hit = {
            "title": "Balance de emergencia climática",
            "summary_clean": "El sistema frontal causó daños en viviendas.",
        }

        score_with = _score_article_match(description, article_with_title_hit)
        score_without = _score_article_match(description, article_without_title_hit)

        # El artículo con keywords en el título debe tener mayor score
        assert score_with >= score_without


# ---------------------------------------------------------------------------
# Tests para _extract_keywords
# ---------------------------------------------------------------------------


class TestExtractKeywords:
    """Pruebas para _extract_keywords."""

    def test_extracts_meaningful_words(self):
        """Debe extraer palabras significativas filtrando stop words."""
        text = "sanción al proyecto inmobiliario en Villarrica sobre la reforma"
        result = _extract_keywords(text)
        assert "sanción" in result
        assert "proyecto" in result
        assert "inmobiliario" in result
        assert "villarrica" in result
        assert "reforma" in result
        # Stop words deben filtrarse
        assert "sobre" not in result
        assert "para" not in result

    def test_filters_short_words(self):
        """Debe filtrar palabras de menos de 4 caracteres."""
        text = "la sanción al proyecto de ley en el sur"
        result = _extract_keywords(text)
        assert "sanción" in result
        assert "proyecto" in result
        assert "ley" not in result  # 3 letras


# ---------------------------------------------------------------------------
# Tests para _truncate_content
# ---------------------------------------------------------------------------


class TestTruncateContent:
    """Pruebas para _truncate_content."""

    def test_short_text_unchanged(self):
        """Debe devolver el texto sin cambios si es más corto que max_chars."""
        text = "Texto corto."
        result = _truncate_content(text, max_chars=100)
        assert result == text

    def test_truncates_long_text_at_word_boundary(self):
        """Debe truncar texto largo en un límite de palabra."""
        text = "palabra1 palabra2 palabra3 palabra4 palabra5"
        result = _truncate_content(text, max_chars=25)
        assert len(result) <= 26
        assert result.endswith("…")

    def test_returns_empty_for_none(self):
        """Debe retornar cadena vacía para None."""
        assert _truncate_content(None) == ""

    def test_returns_empty_for_empty_string(self):
        """Debe retornar cadena vacía para string vacío."""
        assert _truncate_content("") == ""


# ---------------------------------------------------------------------------
# Tests para _build_companion_path
# ---------------------------------------------------------------------------


class TestBuildCompanionPath:
    """Pruebas para _build_companion_path."""

    def test_generates_correct_sibling_path(self):
        """Debe generar un archivo .json hermano del .md de la pauta."""
        pauta_path = Path("/some/dir/pauta_semanal_2026_07_09.md")
        result = _build_companion_path(pauta_path)
        assert result == Path("/some/dir/pauta_semanal_2026_07_09_companion.json")

    def test_handles_relative_path(self):
        """Debe funcionar con rutas relativas."""
        pauta_path = Path("reportes/pauta_semanal_2026_07_09.md")
        result = _build_companion_path(pauta_path)
        assert result.name == "pauta_semanal_2026_07_09_companion.json"


# ---------------------------------------------------------------------------
# Tests para build_companion_data
# ---------------------------------------------------------------------------


PAUTA_WITH_SOURCES = """# ⚡ Pauta Editorial Sugerida - La Chispa Sur

---

## 1. Título de Propuesta 1
*   **Enfoque Editorial:** Análisis de prueba.
*   **Puntos Clave a Desarrollar:**
    1. Punto 1
*   **Fuentes Sugeridas para Ampliar:**
    *   **CIPER Chile:** Investigación sobre sanción proyecto Villarrica tala bosque nativo.
    *   **Cooperativa:** Reporte sistema frontal daños viviendas sur.

## 2. Título de Propuesta 2
*   **Enfoque Editorial:** Otro análisis.
*   **Fuentes Sugeridas para Ampliar:**
    *   **La Tercera:** Nota sobre megarreforma tributaria invariabilidad PPD.

## 3. Título de Propuesta 3
*   **Enfoque Editorial:** Tercer análisis sin fuentes.
"""


class TestBuildCompanionData:
    """Pruebas para build_companion_data (con mocks)."""

    @pytest.fixture
    def filtered_items(self):
        """Fixture con artículos de prueba."""
        return [
            {
                "title": "Condenan a empresa por tala de bosque nativo en Villarrica",
                "source": "CIPER Chile",
                "link": "https://example.com/1",
                "summary_clean": "La justicia condenó a Inversiones Ain por "
                "cortar especies nativas protegidas en zona lacustre.",
                "full_content": None,
            },
            {
                "title": "Sistema frontal: más de 100 viviendas dañadas",
                "source": "Cooperativa",
                "link": "https://example.com/2",
                "summary_clean": "Balance del sistema frontal desde Maule a Los Lagos.",
                "full_content": "Contenido ya extraído del sistema frontal.",
            },
            {
                "title": "Megarreforma: PPD anuncia acuerdo con ministro Quiroz",
                "source": "La Tercera",
                "link": "https://example.com/3",
                "summary_clean": "El PPD alcanzó acuerdo sobre invariabilidad tributaria.",
                "full_content": None,
            },
        ]

    def test_builds_companion_from_pauta_text(self, tmp_path, filtered_items):
        """Debe crear el companion a partir del texto de la pauta."""
        pauta_path = tmp_path / "pauta_semanal_2026_07_09.md"
        pauta_path.write_text("# placeholder")

        with patch(
            "news_agent.source_references.fetch_single_article",
            return_value="Contenido extraído forzosamente.",
        ):
            result = build_companion_data(
                pauta_text=PAUTA_WITH_SOURCES,
                pauta_path=pauta_path,
                filtered_items=filtered_items,
            )

        assert result is not None
        assert result.exists()

        data = json.loads(result.read_text(encoding="utf-8"))
        assert "proposal_1" in data
        assert "proposal_2" in data
        assert "proposal_3" in data

        # Propuesta 1: debe matchear CIPER y Cooperativa
        arts_1 = data["proposal_1"]["articles"]
        assert len(arts_1) >= 1
        sources_1 = [a["source"] for a in arts_1]
        assert "CIPER Chile" in sources_1

        # Propuesta 2: debe matchear La Tercera
        arts_2 = data["proposal_2"]["articles"]
        assert len(arts_2) >= 1
        assert arts_2[0]["source"] == "La Tercera"

    def test_returns_none_when_pauta_has_no_sources(self, tmp_path, filtered_items):
        """Debe retornar None si la pauta no tiene fuentes sugeridas."""
        pauta_path = tmp_path / "pauta.md"
        pauta_path.write_text("# placeholder")

        result = build_companion_data(
            pauta_text="## 1. Sin fuentes\n\nSin sección de fuentes.",
            pauta_path=pauta_path,
            filtered_items=filtered_items,
        )
        assert result is None

    def test_uses_summary_as_fallback_when_enrichment_fails(
        self, tmp_path, filtered_items
    ):
        """Debe usar summary_clean si fetch_single_article retorna None."""
        pauta_path = tmp_path / "pauta.md"
        pauta_path.write_text("# placeholder")

        with patch(
            "news_agent.source_references.fetch_single_article",
            return_value=None,
        ):
            result = build_companion_data(
                pauta_text=PAUTA_WITH_SOURCES,
                pauta_path=pauta_path,
                filtered_items=filtered_items,
            )

        assert result is not None
        data = json.loads(result.read_text(encoding="utf-8"))
        # Artículo con full_content=None → fetch falló → debe usar summary_clean
        arts = data["proposal_1"]["articles"]
        cipier_art = [a for a in arts if a["source"] == "CIPER Chile"][0]
        assert cipier_art["content"] == cipier_art["summary"]


# ---------------------------------------------------------------------------
# Tests para load_companion_data
# ---------------------------------------------------------------------------


class TestLoadCompanionData:
    """Pruebas para load_companion_data."""

    @pytest.fixture
    def companion_data(self):
        """Fixture con datos de companion de prueba."""
        return {
            "metadata": {
                "generated_at": "2026-07-09T12:00:00",
                "total_articles_in_pipeline": 200,
            },
            "proposal_1": {
                "articles": [
                    {
                        "title": "Noticia A",
                        "source": "La Tercera",
                        "link": "https://example.com/a",
                        "summary": "Resumen A",
                        "content": "Contenido completo A",
                    },
                ]
            },
            "proposal_2": {
                "articles": [
                    {
                        "title": "Noticia B",
                        "source": "CIPER Chile",
                        "link": "https://example.com/b",
                        "summary": "Resumen B",
                        "content": "Contenido completo B",
                    }
                ]
            },
            "proposal_3": {"articles": []},
        }

    def test_loads_articles_for_valid_proposal(self, tmp_path, companion_data):
        """Debe cargar los artículos para una propuesta existente."""
        pauta_path = tmp_path / "pauta_semanal_2026_07_09.md"
        pauta_path.write_text("# placeholder")
        companion_path = tmp_path / "pauta_semanal_2026_07_09_companion.json"
        companion_path.write_text(
            json.dumps(companion_data, ensure_ascii=False),
            encoding="utf-8",
        )

        result = load_companion_data(pauta_path, article_number=1)
        assert result is not None
        assert len(result) == 1
        assert result[0]["title"] == "Noticia A"

    def test_returns_none_when_companion_missing(self, tmp_path):
        """Debe retornar None si el archivo companion no existe."""
        pauta_path = tmp_path / "pauta_semanal_2026_07_09.md"
        pauta_path.write_text("# placeholder")

        result = load_companion_data(pauta_path, article_number=1)
        assert result is None

    def test_returns_none_for_corrupt_json(self, tmp_path):
        """Debe retornar None si el companion tiene JSON inválido."""
        pauta_path = tmp_path / "pauta_semanal_2026_07_09.md"
        pauta_path.write_text("# placeholder")
        companion_path = tmp_path / "pauta_semanal_2026_07_09_companion.json"
        companion_path.write_text("esto no es json", encoding="utf-8")

        result = load_companion_data(pauta_path, article_number=1)
        assert result is None

    def test_returns_none_for_empty_articles(self, tmp_path, companion_data):
        """Debe retornar None si la propuesta tiene articles vacío."""
        pauta_path = tmp_path / "pauta_semanal_2026_07_09.md"
        pauta_path.write_text("# placeholder")
        companion_path = tmp_path / "pauta_semanal_2026_07_09_companion.json"
        companion_path.write_text(
            json.dumps(companion_data, ensure_ascii=False),
            encoding="utf-8",
        )

        result = load_companion_data(pauta_path, article_number=3)
        assert result is None
