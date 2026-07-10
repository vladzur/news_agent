"""Tests para el módulo de referencias a fuentes (source_references)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from news_agent.source_references import (
    _build_companion_path,
    _extract_keywords,
    _extract_media_mentions_from_body,
    _score_article_match,
    _source_names_match,
    _truncate_content,
    build_companion_data,
    extract_article_references,
    extract_media_sources_from_pauta,
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
# Tests para _extract_media_mentions_from_body
# ---------------------------------------------------------------------------


class TestExtractMediaMentionsFromBody:
    """Pruebas para _extract_media_mentions_from_body."""

    def test_extracts_known_sources_from_narrative_text(self):
        """Debe extraer menciones de medios conocidos del cuerpo narrativo."""
        block = (
            "## 1. Reforma tributaria en crisis\n"
            "CIPER Chile reporta que el cobro de garantías del CAE alcanzó "
            "un récord histórico este trimestre. Según La Tercera, la deuda "
            "pública sobrepasaría los umbrales deseables. Cooperativa informa "
            "que expertos advierten sobre el impacto inflacionario."
        )
        known = {"CIPER Chile", "La Tercera", "Cooperativa", "DF Diario"}

        result = _extract_media_mentions_from_body(block, known)

        assert len(result) == 3
        names = {m["source_name"] for m in result}
        assert names == {"CIPER Chile", "La Tercera", "Cooperativa"}

        # Cada descripción debe contener el nombre del medio
        for mention in result:
            assert mention["source_name"].lower() in mention["description"].lower()

    def test_skips_mentions_in_fuentes_sugeridas_section(self):
        """No debe extraer menciones que están dentro de Fuentes Sugeridas."""
        block = (
            "## 1. Propuesta\n"
            "Análisis del sistema frontal en el sur.\n"
            "*   **Fuentes Sugeridas para Ampliar:**\n"
            "    *   **La Tercera:** Su nota sobre el temporal.\n"
        )
        known = {"La Tercera"}

        result = _extract_media_mentions_from_body(block, known)

        # La Tercera solo aparece en la sección Fuentes Sugeridas, debe ignorarse
        assert len(result) == 0

    def test_handles_no_known_sources_in_block(self):
        """Debe retornar lista vacía si no hay menciones en el bloque."""
        block = "Un análisis de política nacional sin mencionar medios específicos."
        known = {"CIPER Chile", "La Tercera"}

        result = _extract_media_mentions_from_body(block, known)

        assert result == []

    def test_only_one_mention_per_source(self):
        """Debe capturar solo la primera mención de cada medio."""
        block = (
            "CIPER Chile publicó una investigación. Más adelante, "
            "CIPER Chile también reportó sobre otro caso."
        )
        known = {"CIPER Chile"}

        result = _extract_media_mentions_from_body(block, known)

        assert len(result) == 1

    def test_requires_minimum_context_length(self):
        """Debe ignorar contextos demasiado cortos (ruido)."""
        block = "Según DF. Eso sería todo."
        known = {"DF Diario", "DF"}

        result = _extract_media_mentions_from_body(block, known)

        # "DF" tiene < 3 caracteres, se ignora directamente
        # "DF Diario" no aparece
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Tests para extract_media_sources_from_pauta
# ---------------------------------------------------------------------------


class TestExtractMediaSourcesFromPauta:
    """Pruebas para extract_media_sources_from_pauta."""

    def test_extracts_media_per_proposal(self):
        """Debe extraer menciones de medios agrupadas por número de propuesta."""
        pauta_text = """# Pauta Editorial

## 1. Reforma y deuda
CIPER Chile reporta que las garantías del CAE alcanzaron un récord.
La Tercera advierte sobre el umbral de deuda pública. El debate
legislativo continúa en el Congreso.

## 2. Emergencia climática en el sur
Cooperativa informa sobre el sistema frontal que afecta a La Araucanía.
Las lluvias han dañado más de 100 viviendas en la zona lacustre.

## 3. Panorama internacional
BBC Mundo reporta sobre la escalada del conflicto. Sin embargo,
las repercusiones en Chile son limitadas.
"""
        known = {"CIPER Chile", "La Tercera", "Cooperativa", "BBC Mundo", "DF Diario"}

        result = extract_media_sources_from_pauta(pauta_text, known)

        assert len(result) == 3
        assert len(result[1]) == 2  # CIPER Chile + La Tercera
        assert len(result[2]) == 1  # Cooperativa
        assert len(result[3]) == 1  # BBC Mundo

        names_1 = {m["source_name"] for m in result[1]}
        assert names_1 == {"CIPER Chile", "La Tercera"}

    def test_returns_empty_when_no_media_mentioned_in_body(self):
        """Debe retornar vacío si el cuerpo no menciona ningún medio conocido."""
        pauta_text = """# Pauta

## 1. Propuesta sin medios
El gobierno anunció nuevas medidas económicas. La oposición criticó
la falta de diálogo. Expertos debaten sobre el impacto fiscal.

## 2. Otra propuesta sin menciones
Análisis de la situación política nacional.
"""
        known = {"CIPER Chile", "La Tercera", "Cooperativa"}

        result = extract_media_sources_from_pauta(pauta_text, known)

        assert result == {}

    def test_handles_pauta_without_standard_proposal_format(self):
        """Debe manejar pautas que no tienen el formato ## N. esperado."""
        pauta_text = "Un texto sin estructura de propuestas."
        known = {"La Tercera"}

        result = extract_media_sources_from_pauta(pauta_text, known)

        assert result == {}


# ---------------------------------------------------------------------------
# Tests para extract_article_references
# ---------------------------------------------------------------------------


class TestExtractArticleReferences:
    """Pruebas para extract_article_references."""

    def test_extracts_references_from_pauta(self):
        """Debe extraer referencias [art. N] agrupadas por propuesta."""
        pauta_text = """# Pauta Editorial

## 1. Reforma tributaria
El debate fiscal continúa. Según CIPER Chile [art. 3], las garantías
del CAE alcanzaron un récord. La Tercera [art. 7] también reporta
sobre la deuda pública.

## 2. Emergencia en el sur
Cooperativa [art. 12] informa sobre el sistema frontal. Las lluvias
han dañado viviendas en La Araucanía [art. 15].

## 3. Panorama internacional
El dólar cayó según DF Diario [art. 8]. BBC Mundo [art. 20] cubre
los ataques en Medio Oriente.
"""
        # filtered_items solo necesita tener suficientes elementos para validar índices
        dummy_items = [{}] * 50

        result = extract_article_references(pauta_text, dummy_items)

        assert len(result) == 3
        assert result[1] == [3, 7]
        assert result[2] == [12, 15]
        assert result[3] == [8, 20]

    def test_deduplicates_repeated_references(self):
        """Debe deduplicar referencias repetidas al mismo artículo."""
        pauta_text = """## 1. Propuesta
CIPER Chile [art. 5] publicó una investigación. Más adelante,
CIPER Chile [art. 5] también reportó sobre otro caso.
"""
        result = extract_article_references(pauta_text, [{}] * 20)

        assert result[1] == [5]

    def test_ignores_out_of_range_references(self):
        """Debe ignorar referencias a números de artículo que no existen."""
        pauta_text = """## 1. Propuesta
CIPER Chile [art. 5] reporta algo. También [art. 999] está fuera de rango.
"""
        result = extract_article_references(pauta_text, [{}] * 10)

        assert result[1] == [5]  # 999 ignorado

    def test_returns_empty_when_no_references(self):
        """Debe retornar vacío si la pauta no tiene referencias [art. N]."""
        pauta_text = """## 1. Propuesta
CIPER Chile reporta algo sin usar el formato de referencia.
"""
        result = extract_article_references(pauta_text, [{}] * 10)

        assert result == {}

    def test_handles_various_spacing(self):
        """Debe manejar variaciones de espaciado en el formato [art. N]."""
        pauta_text = """## 1. Propuesta
Referencia normal [art. 1], con más espacios [art.  2], y [art.3].
"""
        result = extract_article_references(pauta_text, [{}] * 20)

        assert result[1] == [1, 2, 3]

    def test_extracts_multiple_numbers_in_single_bracket(self):
        """Debe extraer todos los números de un bracket con múltiples referencias.

        El LLM puede agrupar varias referencias: [art. 60, 174, 178, 182].
        """
        pauta_text = """## 1. Propuesta
El acuerdo [art. 60, 174, 178, 182] fue criticado por la oposición.
Además, [art. 143] y [art. 303, 311] complementan el análisis.
"""
        result = extract_article_references(pauta_text, [{}] * 500)

        assert result[1] == [60, 143, 174, 178, 182, 303, 311]


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

    def test_filters_very_short_words(self):
        """Debe filtrar palabras de menos de 3 caracteres."""
        text = "la sanción al proyecto de ley en el sur"
        result = _extract_keywords(text)
        assert "sanción" in result
        assert "proyecto" in result
        assert "ley" in result  # 3 letras: ahora se incluye (acrónimos como CAE, CPI, SII)
        assert "sur" in result  # 3 letras


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

    def test_extracts_media_from_body_when_fuentes_sugeridas_has_institutions(
        self, tmp_path
    ):
        """Debe extraer medios del cuerpo aunque Fuentes Sugeridas solo tenga
        instituciones (CPI, Dipres, Senapred) que no están en los feeds RSS.

        Este es el escenario real del bug: el LLM puebla 'Fuentes Sugeridas'
        con organismos e instituciones, pero cita los medios reales en el
        texto narrativo de cada propuesta.
        """
        # Artículos que sí coinciden temáticamente con lo que el LLM menciona
        realistic_items = [
            {
                "title": "Cobro de garantías del CAE a morosos alcanza récord histórico",
                "source": "CIPER Chile",
                "link": "https://example.com/1",
                "summary_clean": "El cobro estatal de garantías del CAE "
                "alcanzó un récord en el último trimestre según cifras oficiales.",
                "full_content": None,
            },
            {
                "title": "Deuda pública chilena superaría umbrales recomendados",
                "source": "La Tercera",
                "link": "https://example.com/2",
                "summary_clean": "Informes del Ministerio de Hacienda revelan "
                "que la deuda pública sobrepasaría los niveles considerados "
                "prudentes por los organismos internacionales.",
                "full_content": None,
            },
            {
                "title": "Sistema frontal: más de 100 viviendas dañadas en La Araucanía",
                "source": "Cooperativa",
                "link": "https://example.com/3",
                "summary_clean": "Balance del sistema frontal que afectó "
                "desde Maule a Los Lagos con lluvias intensas y vientos.",
                "full_content": "Contenido ya extraído del sistema frontal.",
            },
            {
                "title": "Dólar cae bajo los $930 por recuperación del cobre",
                "source": "DF Diario",
                "link": "https://example.com/4",
                "summary_clean": "El tipo de cambio retrocedió favorecido por "
                "el avance en el precio del cobre y la calma en los mercados.",
                "full_content": None,
            },
        ]

        pauta_with_body_mentions = """# Pauta Editorial

## 1. La invariabilidad tributaria como síntoma
*   **Enfoque Editorial:** CIPER Chile reporta que el cobro de garantías
    del CAE alcanzó un récord. La Tercera publicó que la deuda pública
    sobrepasaría los umbrales deseables. El debate fiscal continúa.
*   **Puntos Clave a Desarrollar:**
    1. Contexto fiscal y deuda pública.
    2. El rol de los senadores de zonas mineras.
*   **Fuentes Sugeridas para Ampliar:**
    *   **Consejo de Políticas de Infraestructura (CPI):** Para profundizar
      en su informe sobre inversión pública.
    *   **Dipres:** Para obtener cifras oficiales de ejecución presupuestaria.

## 2. Emergencia climática en La Araucanía
*   **Enfoque Editorial:** Cooperativa informa sobre el sistema frontal
    que afecta a la zona lacustre. Las lluvias dañaron viviendas en Pucón.
*   **Fuentes Sugeridas para Ampliar:**
    *   **Senapred:** Para obtener el detalle de alertas vigentes.
    *   **Sernageomin:** Para reportes sobre riesgo de remociones en masa.

## 3. Conflicto en Medio Oriente y economía chilena
*   **Enfoque Editorial:** DF Diario reporta que el dólar cayó bajo los $930
    por la recuperación del cobre. BBC Mundo cubre los ataques en la región.
*   **Fuentes Sugeridas para Ampliar:**
    *   **CNE:** Para analizar la dependencia de combustibles fósiles.
"""

        pauta_path = tmp_path / "pauta_semanal.md"
        pauta_path.write_text("# placeholder")

        with patch(
            "news_agent.source_references.fetch_single_article",
            return_value=None,
        ):
            result = build_companion_data(
                pauta_text=pauta_with_body_mentions,
                pauta_path=pauta_path,
                filtered_items=realistic_items,
            )

        assert result is not None
        data = json.loads(result.read_text(encoding="utf-8"))

        # Propuesta 1: CIPER Chile y La Tercera desde el cuerpo
        arts_1 = data["proposal_1"]["articles"]
        sources_1 = [a["source"] for a in arts_1]
        assert "CIPER Chile" in sources_1
        assert "La Tercera" in sources_1

        # Propuesta 2: Cooperativa desde el cuerpo
        arts_2 = data["proposal_2"]["articles"]
        sources_2 = [a["source"] for a in arts_2]
        assert "Cooperativa" in sources_2

        # Propuesta 3: DF Diario desde el cuerpo (BBC Mundo no está en items)
        arts_3 = data["proposal_3"]["articles"]
        sources_3 = [a["source"] for a in arts_3]
        assert "DF Diario" in sources_3

    def test_uses_deterministic_references_when_available(self, tmp_path):
        """Debe usar referencias [art. N] como método principal cuando existen.

        Si el LLM incluyó referencias [art. N] en la pauta, el companion debe
        resolverse determinísticamente sin depender de fuzzy matching.
        """
        items = [
            {
                "title": "Noticia sobre el CAE",
                "source": "CIPER Chile",
                "link": "https://example.com/1",
                "summary_clean": "Cobro de garantías del CAE.",
                "full_content": None,
            },
            {
                "title": "Noticia sobre la reforma",
                "source": "La Tercera",
                "link": "https://example.com/2",
                "summary_clean": "Reforma tributaria en el Congreso.",
                "full_content": None,
            },
            {
                "title": "Noticia sobre el clima",
                "source": "Cooperativa",
                "link": "https://example.com/3",
                "summary_clean": "Sistema frontal en La Araucanía.",
                "full_content": None,
            },
        ]

        pauta_with_refs = """# Pauta Editorial

## 1. Reforma tributaria
Según CIPER Chile [art. 1], las garantías del CAE alcanzaron un récord.
La Tercera [art. 2] también reporta sobre el debate en el Congreso.
*   **Fuentes Sugeridas para Ampliar:**
    *   **CPI:** Informe de inversión pública.

## 2. Emergencia climática
Cooperativa [art. 3] informa sobre daños en viviendas por el temporal.
"""

        pauta_path = tmp_path / "pauta.md"
        pauta_path.write_text("# placeholder")

        with patch(
            "news_agent.source_references.fetch_single_article",
            return_value=None,
        ):
            result = build_companion_data(
                pauta_text=pauta_with_refs,
                pauta_path=pauta_path,
                filtered_items=items,
            )

        assert result is not None
        data = json.loads(result.read_text(encoding="utf-8"))

        # Propuesta 1: artículos 1 y 2 resueltos determinísticamente
        arts_1 = data["proposal_1"]["articles"]
        assert len(arts_1) == 2
        titles_1 = [a["title"] for a in arts_1]
        assert "Noticia sobre el CAE" in titles_1
        assert "Noticia sobre la reforma" in titles_1

        # Propuesta 2: artículo 3
        arts_2 = data["proposal_2"]["articles"]
        assert len(arts_2) == 1
        assert arts_2[0]["title"] == "Noticia sobre el clima"


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
